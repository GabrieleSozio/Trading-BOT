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
from . import capital as cap_mod
from . import insider
from .ai_client import AIUnavailable

log = logging.getLogger("routine01")

# Oltre questa soglia un "gap" e' quasi sempre un print IEX sporco o un titolo
# sospeso/split: si scarta per non operare su dati spazzatura (fail-loud sul singolo).
SANITY_MAX_GAP_PCT = 50.0
# Sotto questo scarto il titolo si considera FERMO, non ribassista: con il feed
# consolidato uno zero esatto e' quasi impossibile, quindi resta come sentinella.
FLAT_GAP_PCT = 0.02


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _prev_close_from_bars(client: AlpacaClient, symbols: list[str], session_date: str) -> dict:
    """Ultima chiusura giornaliera *completata* (data < session_date) per ticker.

    Dal nastro consolidato (SIP): e' la chiusura ufficiale di tutte le borse,
    non quella parziale vista dalla sola IEX.
    """
    start = (dt.date.fromisoformat(session_date) - dt.timedelta(days=12)).isoformat()
    bars = client.bars(symbols, "1Day", start, feed="sip", limit=1000)
    out: dict[str, float] = {}
    for sym, rows in bars.items():
        completed = [b for b in rows if b["t"][:10] < session_date]
        if completed:
            out[sym] = completed[-1]["c"]
    return out


def _premarket_volume(client: AlpacaClient, symbols: list[str], session_date: str) -> dict:
    """Volume scambiato oggi (pre-apertura inclusa): somma delle barre da 1 minuto.

    Qui il feed consolidato non e' un miglioramento marginale ma la differenza
    fra avere e non avere il dato: in pre-apertura IEX registra una manciata di
    scambi, il consolidato centinaia di migliaia. Con IEX questa misura era
    sostanzialmente vuota, e il volume e' il criterio con cui il Portfolio
    Manager sceglie fra i candidati.
    """
    bars = client.bars(symbols, "1Min", session_date, feed="sip", limit=10000)
    out: dict[str, int] = {s: 0 for s in symbols}
    for sym, rows in bars.items():
        out[sym] = sum(b.get("v", 0) for b in rows)
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


def _lessons_block(cfg: dict, tickers: list[str]) -> str:
    """Lezioni dalle decisioni passate di cui ora si conosce l'esito.

    Serve a non ripetere lo stesso errore senza accorgersene: l'AI vedeva ogni
    giorno i dati da zero, senza memoria di cosa avesse gia' provato e come
    fosse andata.
    """
    try:
        from . import decisions
        reg = decisions.DecisionLog(Path(cfg["state"]["dir"]) / "decisions_log.json")
        pezzi = []
        visti = set()
        for t in tickers[:5]:
            testo = reg.recent_lessons(ticker=t, n_same=2, n_other=0)
            if testo and testo not in visti:
                visti.add(testo)
                pezzi.append(testo)
        generali = reg.recent_lessons(ticker=None, n_same=0, n_other=4)
        if generali:
            pezzi.append(generali)
        if not pezzi:
            return ""
        return ("Esperienza passata di questo stesso sistema, con esiti gia' noti. "
                "Usala per non ripetere errori, NON come regola assoluta: le "
                "condizioni di mercato cambiano.\n" + "\n".join(pezzi) + "\n\n")
    except Exception as e:  # noqa: BLE001 — la memoria e' un di piu'
        log.warning("Lezioni passate non disponibili: %s", e)
        return ""


def _ai_select(rows: list[dict], top_n: int, model: str | None, tier: dict,
               insider_data: dict | None = None, lessons: str = ""):
    """Fa selezionare a Claude i top_n candidati, con motivazione, adattando il
    mandato alla strategia della fascia di capitale attiva (swing o intraday).
    Ritorna (lista candidati con campo ai_rationale, testo analisi).
    Solleva AIUnavailable se l'AI non è usabile o restituisce dati incoerenti."""
    by_ticker = {r["ticker"]: r for r in rows}
    table = "\n".join(
        f"{r['ticker']:5} sector={r['sector']:22} gap={r['gap_pct']:+.2f}% "
        f"vol={r['premarket_volume']:>10} trend={r['trend']} last={r['last_price']}"
        for r in rows
    )
    if cap_mod.is_intraday(tier):
        mandate = (
            "Strategia: MOMENTUM INTRADAY con filtro di ritracciamento. Le posizioni "
            "vengono apert e chiuse nella stessa giornata (flat obbligatorio la sera). "
            "Privilegia forte direzionalità odierna e volumi elevati: conta il movimento "
            "delle prossime ore, non dei prossimi giorni."
        )
    else:
        mandate = (
            f"Strategia: SWING TRADING su piu' giorni (posizioni tenute fino a "
            f"{tier.get('max_hold_days', 5)} giorni di borsa, stop -{tier['stop_loss_pct']*100:.0f}% "
            f"/ target +{tier['take_profit_pct']*100:.0f}%). NON e' intraday: privilegia "
            "titoli con un movimento che abbia ragionevoli probabilita' di PROSEGUIRE nei "
            "giorni successivi (trend solido, volume convincente, catalizzatore plausibile), "
            "evitando picchi isolati che rientrano subito. Considera che le posizioni "
            "resteranno aperte durante la notte."
        )
    system = (
        "Sei un analista quantitativo di un piccolo fondo che opera su azioni USA liquide. "
        f"{mandate} Scegli i candidati piu' promettenti dai dati forniti. "
        "Rispondi solo nel formato JSON richiesto, in italiano."
    )
    only_long = "" if tier.get("allow_short") else (
        " Tutti i candidati in lista sono rialzisti perche' questa fascia opera solo al rialzo."
    )
    # Segnale accessorio: cosa hanno fatto gli insider con i propri soldi.
    ins_block = ""
    if insider_data:
        in_lista = {r["ticker"] for r in rows}
        righe = insider.summarize({k: v for k, v in insider_data.items() if k in in_lista})
        if righe.strip():
            ins_block = (
                "Operazioni degli INSIDER dichiarate alla SEC (Form 4). Gli ACQUISTI sul "
                "mercato aperto indicano che dirigenti o amministratori hanno investito "
                "denaro proprio: e' un segnale di fiducia. Le vendite sono piu' ambigue "
                "(spesso pianificate o per esigenze personali). Consideralo UNO dei "
                "criteri, non quello principale:\n" + righe + "\n\n")
    user = (
        f"Capitale operativo: {tier['positions_to_open']} posizioni da "
        f"{tier['max_position_size_pct']*100:.0f}% ciascuna (fascia '{tier['name']}').{only_long}\n\n"
        f"Dati pre-market di oggi ({len(rows)} titoli gia' filtrati per accessibilita'):\n{table}\n\n"
        f"{ins_block}"
        f"{lessons}"
        f"Seleziona ESATTAMENTE i {top_n} migliori candidati (usa solo ticker presenti "
        f"nella lista). Per ciascuno una breve motivazione (forza del movimento, volume, "
        f"settore, tenuta attesa). Aggiungi una breve 'analysis' d'insieme."
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

    # --- Capitale operativo e fascia di rischio attiva ---
    try:
        acct = client.account()
    except GuardrailR5:
        log.error("R5: troppi errori broker leggendo l'account. Stop.")
        sys.exit(1)
    capital, simulated = cap_mod.effective_capital(cfg, float(acct["equity"]), client)
    tier = cap_mod.resolve_tier(cfg, capital)
    max_price = cap_mod.max_affordable_price(capital, tier)
    log.info("%s", cap_mod.describe(tier, capital, simulated))
    log.info("Prezzo massimo per azione operabile: %.2f USD", max_price)

    # --- Dati di mercato ---
    try:
        # Feed consolidato differito: l'Analista gira alle 14:30 e gli ordini
        # partono alle 15:30, quindi 15 minuti di ritardo non cambiano nulla,
        # mentre la completezza del dato cambia tutto.
        snap = client.snapshots(tickers, feed="delayed_sip")
        prev_close = _prev_close_from_bars(client, tickers, session_date)
        pm_vol = _premarket_volume(client, tickers, session_date)
    except GuardrailR5:
        log.error("R5: troppi errori broker consecutivi durante il fetch dati. Stop senza output.")
        sys.exit(1)

    analyzed, skipped = 0, 0
    # Conteggio dei motivi di scarto: se un giorno l'universo si svuota, il log
    # deve dire PERCHE'. Senza questo, una giornata in stand-by per dati mancanti
    # e una per mercato in ribasso sono indistinguibili.
    motivi = {"dati assenti": 0, "gap anomalo": 0, "troppo caro": 0,
              "in ribasso": 0, "fermo": 0}
    rows = []
    for t in tickers:
        d = snap.get(t) or {}
        last = (d.get("latestTrade") or {}).get("p")
        pc = prev_close.get(t)
        if last is None or not pc:
            log.warning("%s: dati insufficienti (last=%s prev_close=%s) -> scartato", t, last, pc)
            skipped += 1
            motivi["dati assenti"] += 1
            continue
        gap = (last - pc) / pc * 100.0
        if abs(gap) > SANITY_MAX_GAP_PCT:
            log.warning("%s: gap %.1f%% oltre soglia di sanita' (%.0f%%): probabile dato sporco -> scartato",
                        t, gap, SANITY_MAX_GAP_PCT)
            skipped += 1
            motivi["gap anomalo"] += 1
            continue
        # --- Filtro di ACCESSIBILITA': con azioni intere serve prezzo <= quota
        # allocabile, altrimenti il titolo non e' operabile con questo capitale.
        if last > max_price:
            skipped += 1
            motivi["troppo caro"] += 1
            continue
        # --- Filtro DIREZIONE: se la fascia non ammette short, niente ribassisti.
        # Un titolo FERMO non e' ribassista: va distinto, altrimenti un giorno
        # senza dati (in cui ogni scarto risulta zero) sembra un mercato in
        # ribasso. E' esattamente cio' che accadeva leggendo il feed IEX in
        # pre-apertura, dove spesso non c'erano scambi e l'ultimo prezzo noto
        # coincideva al centesimo con la chiusura del giorno prima.
        if abs(gap) < FLAT_GAP_PCT:
            trend = "Flat"
            skipped += 1
            motivi["fermo"] += 1
            continue
        trend = "Bullish" if gap > 0 else "Bearish"
        if trend == "Bearish" and not tier.get("allow_short"):
            skipped += 1
            motivi["in ribasso"] += 1
            continue
        rows.append({
            "ticker": t,
            "sector": sector_of(t),
            "last_price": round(last, 4),
            "prev_close": round(pc, 4),
            "gap_pct": round(gap, 4),
            "premarket_volume": int(pm_vol.get(t, 0)),
            "trend": trend,
        })
        analyzed += 1

    if not rows:
        log.error("Nessun candidato operabile con %.2f USD (prezzo max/azione %.2f, short %s). "
                  "Scrivo lista vuota: giornata in stand-by.",
                  capital, max_price, tier.get("allow_short"))
        log.error("Motivi dello scarto su %d titoli: %s", len(tickers),
                  ", ".join(f"{k}={v}" for k, v in motivi.items() if v))
        if motivi["fermo"] > len(tickers) * 0.5:
            log.error("Oltre meta' dell'universo risulta FERMO: e' il sintomo di dati "
                      "di mercato mancanti, non di un mercato immobile. Controllare il feed.")
        payload = {
            "generated_at": now_cet().isoformat(timespec="seconds"),
            "session_date": session_date,
            "universe_size": len(tickers),
            "capital_usd": capital,
            "tier": tier["name"],
            "mode": tier["mode"],
            "selected_by": "nessuno",
            "ai_analysis": None,
            "candidates": [],
        }
        if not dry_run:
            atomic_write_json(out_path, payload)
            gitsync.sync(f"routine 01 premarket {session_date} (nessun candidato)")
        return payload

    # Fallback deterministico: |gap| desc, poi volume pre-market.
    rows.sort(key=lambda r: (abs(r["gap_pct"]), r["premarket_volume"]), reverse=True)

    # --- Segnale aggiuntivo: operazioni degli insider (SEC Form 4) ---
    # Non decide nulla da solo: entra fra gli elementi che l'AI valuta. Limitato ai
    # primi candidati per non allungare la routine (cache di 12 ore).
    ins_cfg = cfg.get("insider") or {}
    insider_data = {}
    if ins_cfg.get("enabled", True):
        top = [r["ticker"] for r in rows[: int(ins_cfg.get("max_tickers", 12))]]
        try:
            insider_data = insider.activity(top, cache_dir=cfg["state"]["dir"],
                                            days=int(ins_cfg.get("window_days", 90)))
            for r in rows:
                d = insider_data.get(r["ticker"])
                if d and d.get("available"):
                    r["insider_buys"], r["insider_sells"] = d["n_buys"], d["n_sells"]
                    r["insider_buy_usd"] = d["buy_value_usd"]
        except Exception as e:  # noqa: BLE001 — accessorio, mai bloccante
            log.warning("Analisi insider non disponibile (%s): proseguo senza.", e)

    # --- Selezione: l'AI fa la ricerca; se non disponibile, fallback deterministico ---
    ai_cfg = cfg.get("ai", {})
    analysis = None
    selected_by = "deterministico"
    candidates = rows[:top_n]
    if ai_cfg.get("enabled") and ai_client.ai_enabled():
        try:
            lessons = _lessons_block(cfg, [r["ticker"] for r in rows])
            candidates, analysis = _ai_select(rows, top_n, ai_cfg.get("research_model"),
                                              tier, insider_data, lessons)
            selected_by = "AI (Claude)"
        except AIUnavailable as e:
            log.warning("AI non disponibile (%s): uso selezione deterministica.", e)

    payload = {
        "generated_at": now_cet().isoformat(timespec="seconds"),
        "session_date": session_date,
        "universe_size": len(tickers),
        "capital_usd": capital,
        "capital_simulated": simulated,
        "tier": tier["name"],
        "mode": tier["mode"],
        "max_price_per_share": round(max_price, 2),
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
