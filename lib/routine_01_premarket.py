"""
Routine 01 — Premarket Analyst (logica deterministica).

Scansiona l'universo, calcola il gap pre-market, seleziona i top candidati momentum
e scrive state/market_research.json secondo docs/01_state_contracts.md.

La STRATEGIA (cosa significa "momentum", soglie) e' definita nei doc/config; qui c'e'
solo l'esecuzione meccanica e deterministica delle regole. Fail-loud: in caso di
input/dati mancanti logga ERROR e termina con stato d'errore, senza inventare dati.

Uso:  python -m lib.routine_01_premarket            (esegue e scrive il file)
      python -m lib.routine_01_premarket --dry-run  (calcola e stampa, NON scrive)
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

from .alpaca_rest import (
    AlpacaClient,
    GuardrailR5,
    atomic_write_json,
    load_config,
    now_cet,
    read_json,
    today_session_date,
    US_EASTERN,
)
from .sectors import sector_of
from . import gitsync
from . import ai_client
from .ai_client import AIUnavailable

log = logging.getLogger("routine01")

# Oltre questa soglia un "gap" e' quasi sempre un print IEX sporco o un titolo
# sospeso/split: si scarta per non operare su dati spazzatura (fail-loud sul singolo).
SANITY_MAX_GAP_PCT = 50.0


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _prev_close_from_bars(client: AlpacaClient, symbols: list[str], session_date: str) -> dict:
    """Ultima chiusura giornaliera *completata* (data < session_date) per ticker."""
    start = (dt.date.fromisoformat(session_date) - dt.timedelta(days=12)).isoformat()
    out: dict[str, float] = {}
    for i in range(0, len(symbols), 100):
        chunk = symbols[i : i + 100]
        res = client._request(  # plumbing GET; conta gli errori R5
            "GET",
            client._d("/v2/stocks/bars"),
            params={
                "symbols": ",".join(chunk),
                "timeframe": "1Day",
                "start": start,
                "feed": "iex",
                "limit": 1000,
            },
        )
        for sym, bars in res.get("bars", {}).items():
            completed = [b for b in bars if b["t"][:10] < session_date]
            if completed:
                out[sym] = completed[-1]["c"]
    return out


def _premarket_volume(client: AlpacaClient, symbols: list[str], session_date: str) -> dict:
    """Volume scambiato oggi (pre-market incluso): somma delle barre 1-min odierne."""
    start = session_date  # mezzanotte ET del giorno di sessione
    out: dict[str, int] = {s: 0 for s in symbols}
    for i in range(0, len(symbols), 100):
        chunk = symbols[i : i + 100]
        res = client._request(
            "GET",
            client._d("/v2/stocks/bars"),
            params={
                "symbols": ",".join(chunk),
                "timeframe": "1Min",
                "start": start,
                "feed": "iex",
                "limit": 10000,
            },
        )
        for sym, bars in res.get("bars", {}).items():
            out[sym] = sum(b.get("v", 0) for b in bars)
    return out


_AI_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "analysis": {"type": "string"},
        "selection": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ticker": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["ticker", "rationale"],
            },
        },
    },
    "required": ["analysis", "selection"],
}


def _ai_select(rows: list[dict], top_n: int, model: str | None):
    """Fa selezionare a Claude i top_n candidati momentum, con motivazione.
    Ritorna (lista candidati ordinata con campo ai_rationale, testo analisi).
    Solleva AIUnavailable se l'AI non è usabile o restituisce dati incoerenti."""
    by_ticker = {r["ticker"]: r for r in rows}
    table = "\n".join(
        f"{r['ticker']:5} sector={r['sector']:22} gap={r['gap_pct']:+.2f}% "
        f"vol={r['premarket_volume']:>10} trend={r['trend']} last={r['last_price']}"
        for r in rows
    )
    system = (
        "Sei un analista quantitativo di un piccolo hedge fund. Strategia: momentum "
        "intraday con filtro di ritracciamento (si entra su titoli con forte "
        "direzionalità e alti volumi, dopo un piccolo ritracciamento). Operatività "
        "solo intraday su azioni USA liquide. Scegli i candidati più promettenti per "
        "OGGI dai dati forniti. Rispondi solo nel formato JSON richiesto, in italiano."
    )
    user = (
        f"Dati pre-market di oggi ({len(rows)} titoli):\n{table}\n\n"
        f"Seleziona ESATTAMENTE i {top_n} migliori candidati momentum per oggi "
        f"(usa solo ticker presenti nella lista). Per ciascuno una breve motivazione "
        f"(forza del gap, volume, settore). Aggiungi una breve 'analysis' d'insieme."
    )
    data = ai_client.ask_json(system, user, _AI_SCHEMA,
                              model=model, max_tokens=2000)
    sel = data.get("selection") or []
    out = []
    for item in sel:
        tkr = (item.get("ticker") or "").upper()
        if tkr in by_ticker and tkr not in {c["ticker"] for c in out}:
            row = dict(by_ticker[tkr])
            row["ai_rationale"] = item.get("rationale", "")
            out.append(row)
        if len(out) >= top_n:
            break
    if not out:
        raise AIUnavailable("l'AI non ha restituito ticker validi")
    return out, data.get("analysis")


def run(dry_run: bool = False, force: bool = False) -> dict | None:
    _setup_logging()
    cfg = load_config()
    tickers = [t.upper() for t in cfg["universe"]["tickers"]]
    top_n = cfg["universe"]["top_candidates"]
    client = AlpacaClient(
        max_consecutive_errors=cfg["guardrails"]["max_consecutive_api_errors"]
    )

    session_date = today_session_date()
    out_path = cfg["state"]["files"]["market_research"]

    # --- Idempotenza: ricerca di oggi gia' fatta -> non rifare. ---
    if not force and Path(out_path).exists() and read_json(out_path).get("session_date") == session_date:
        log.info("market_research di oggi gia' presente: skip (idempotente).")
        return read_json(out_path)

    # --- Giorno di borsa? (--force salta il gate, solo per validazione off-hours) ---
    try:
        if not force and not client.is_trading_day():
            log.info("Mercato chiuso oggi (%s): nessun file scritto, uscita OK.", session_date)
            return None
    except GuardrailR5:
        log.error("R5: troppi errori broker durante il check calendario. Stop.")
        sys.exit(1)

    # --- Dati di mercato ---
    try:
        snap = client.snapshots(tickers)
        prev_close = _prev_close_from_bars(client, tickers, session_date)
        pm_vol = _premarket_volume(client, tickers, session_date)
    except GuardrailR5:
        log.error("R5: troppi errori broker consecutivi durante il fetch dati. Stop senza output.")
        sys.exit(1)

    analyzed, skipped = 0, 0
    rows = []
    for t in tickers:
        d = snap.get(t) or {}
        last = (d.get("latestTrade") or {}).get("p")
        pc = prev_close.get(t)
        if last is None or not pc:
            log.warning("%s: dati insufficienti (last=%s prev_close=%s) -> scartato", t, last, pc)
            skipped += 1
            continue
        gap = (last - pc) / pc * 100.0
        if abs(gap) > SANITY_MAX_GAP_PCT:
            log.warning("%s: gap %.1f%% oltre soglia di sanita' (%.0f%%): probabile dato sporco -> scartato",
                        t, gap, SANITY_MAX_GAP_PCT)
            skipped += 1
            continue
        rows.append({
            "ticker": t,
            "sector": sector_of(t),
            "last_price": round(last, 4),
            "prev_close": round(pc, 4),
            "gap_pct": round(gap, 4),
            "premarket_volume": int(pm_vol.get(t, 0)),
            "trend": "Bullish" if gap > 0 else "Bearish",
        })
        analyzed += 1

    if not rows:
        log.error("Nessun ticker con dati validi: staffetta non avviabile. Stop senza output.")
        sys.exit(1)

    # Fallback deterministico: |gap| desc, poi volume pre-market.
    rows.sort(key=lambda r: (abs(r["gap_pct"]), r["premarket_volume"]), reverse=True)

    # --- Selezione: l'AI fa la ricerca; se non disponibile, fallback deterministico ---
    ai_cfg = cfg.get("ai", {})
    analysis = None
    selected_by = "deterministico"
    candidates = rows[:top_n]
    if ai_cfg.get("enabled") and ai_client.ai_enabled():
        try:
            candidates, analysis = _ai_select(rows, top_n, ai_cfg.get("research_model"))
            selected_by = "AI (Claude)"
        except AIUnavailable as e:
            log.warning("AI non disponibile (%s): uso selezione deterministica.", e)

    payload = {
        "generated_at": now_cet().isoformat(timespec="seconds"),
        "session_date": session_date,
        "universe_size": len(tickers),
        "selected_by": selected_by,
        "ai_analysis": analysis,
        "candidates": candidates,
    }
    log.info("Selezione candidati: %s", selected_by)

    log.info("Analizzati=%d scartati=%d. Top %d candidati:", analyzed, skipped, len(candidates))
    for c in candidates:
        log.info("  %-5s %-22s gap=%+.2f%% vol=%d %s",
                 c["ticker"], c["sector"], c["gap_pct"], c["premarket_volume"], c["trend"])

    if dry_run:
        log.info("DRY-RUN: nessun file scritto.")
        return payload

    out_path = load_config()["state"]["files"]["market_research"]
    atomic_write_json(out_path, payload)
    log.info("Scritto %s", out_path)
    gitsync.sync(f"routine 01 premarket {session_date}")
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="calcola e stampa senza scrivere file")
    ap.add_argument("--force", action="store_true", help="salta il check giorno di borsa (solo validazione)")
    args = ap.parse_args()
    run(dry_run=args.dry_run, force=args.force)
