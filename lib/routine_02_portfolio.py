"""
Routine 02 — Portfolio Manager (logica deterministica).

Legge state/market_research.json, seleziona le posizioni da aprire, ripartisce il
capitale e calcola i target entry. NESSUN ordine inviato (sola lettura account).
Scrive state/target_orders.json.

Uso:  python -m lib.routine_02_portfolio [--dry-run]
"""
from __future__ import annotations

import argparse
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
)
from . import capital as cap_mod
from . import gitsync

log = logging.getLogger("routine02")


def run(dry_run: bool = False) -> dict | None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    metric = cfg["allocation"]["selection_metric"]
    retr = cfg["allocation"]["entry_retracement_pct"]
    in_path = cfg["state"]["files"]["market_research"]
    out_path = cfg["state"]["files"]["target_orders"]
    session_date = today_session_date()

    # --- Input non pronto = ATTESA (no-op, exit 0), non errore. ---
    if not Path(in_path).exists() or read_json(in_path).get("session_date") != session_date:
        log.info("Input 01 non ancora pronto per oggi (%s): no-op, riprovo al prossimo trigger.", session_date)
        return None

    existing = None
    if Path(out_path).exists() and read_json(out_path).get("session_date") == session_date:
        existing = read_json(out_path)
    research = read_json(in_path)
    candidates = research.get("candidates", [])
    if not candidates:
        log.warning("Nessun candidato in input. Scrivo orders vuoto.")
        candidates = []

    client = AlpacaClient(max_consecutive_errors=cfg["guardrails"]["max_consecutive_api_errors"])
    try:
        acct = client.account()
        positions = client.list_positions()
    except GuardrailR5:
        log.error("R5: troppi errori broker leggendo l'account. Stop.")
        sys.exit(1)

    # --- Capitale operativo e fascia attiva ---
    capital, simulated = cap_mod.effective_capital(cfg, float(acct["equity"]), client)
    tier = cap_mod.resolve_tier(cfg, capital)
    n_open = int(tier["positions_to_open"])
    log.info("%s", cap_mod.describe(tier, capital, simulated))

    # --- Capitale gia' impegnato: in swing le posizioni restano aperte piu'
    # giorni, quindi vanno scalate dal capitale disponibile e dagli slot liberi.
    held = {p["symbol"]: abs(float(p.get("market_value", 0))) for p in positions}
    committed = sum(held.values())
    available = max(0.0, capital - committed)
    slots = max(0, n_open - len(held))
    if held:
        log.info("Posizioni gia' aperte: %s | capitale impegnato %.2f | disponibile %.2f | slot liberi %d",
                 list(held), committed, available, slots)

    # --- Titoli gia' operati OGGI: esclusi da nuovi piani. Rientrare sullo stesso
    # titolo in giornata creerebbe un round-trip intragiornaliero (day trade, che
    # consuma crediti PDT) e produrrebbe churn senza vantaggio atteso.
    try:
        traded_today = {o["symbol"] for o in client.list_orders(status="all")
                        if (o.get("submitted_at") or o.get("created_at") or "")[:10] >= session_date}
    except GuardrailR5:
        log.error("R5: troppi errori broker. Stop.")
        sys.exit(1)

    # --- RIPIANIFICAZIONE INFRAGIORNALIERA ---
    # Non si salta piu' "perche' esiste gia' un piano di oggi": si salta solo se il
    # piano corrente copre gia' tutti gli slot liberi. Cosi', quando una posizione
    # chiude e libera capitale, il bot ripianifica invece di restare fermo fino a domani.
    if existing is not None:
        pendenti = [o for o in existing.get("orders", [])
                    if o["ticker"] not in held and o["ticker"] not in traded_today]
        if slots <= 0:
            log.info("Piano di oggi presente e nessuno slot libero: skip.")
            return existing
        if len(pendenti) >= slots:
            log.info("Piano di oggi gia' copre gli %d slot liberi (%s): skip.",
                     slots, [o["ticker"] for o in pendenti])
            return existing
        log.info("RIPIANIFICO: slot liberi=%d, ordini ancora validi nel piano=%d.",
                 slots, len(pendenti))

    orders = []
    per_pos_cap = capital * float(tier["max_position_size_pct"])
    if not candidates:
        log.warning("Nessun candidato in input -> giornata in stand-by.")
    elif slots == 0:
        log.info("Tutti gli slot (%d) sono gia' occupati: nessun nuovo ordine.", n_open)
    elif available < 1.0:
        log.warning("Capitale disponibile insufficiente (%.2f) -> stand-by.", available)
    else:
        per_pos = min(per_pos_cap, available / slots)
        # Esclude i titoli gia' in portafoglio o gia' operati oggi
        pool = [c for c in candidates
                if c["ticker"] not in held and c["ticker"] not in traded_today]
        if not pool:
            log.info("Nessun candidato disponibile (tutti gia' in portafoglio o gia' operati oggi).")
        chosen = sorted(pool, key=lambda c: c.get(metric, 0), reverse=True)[:slots]
        # Prezzi FRESCHI: ripianificando a meta' giornata, il prezzo delle 14:30
        # sarebbe obsoleto e il target d'ingresso non avrebbe piu' senso.
        for c in chosen:
            action = "buy" if c["trend"] == "Bullish" else "sell_short"
            if action == "sell_short" and not tier.get("allow_short"):
                log.info("%s scartato: short non consentito nella fascia '%s'.", c["ticker"], tier["name"])
                continue
            try:
                live = client.latest_trade(c["ticker"])
            except GuardrailR5:
                log.error("R5: troppi errori broker. Stop.")
                sys.exit(1)
            last = float(live or c["last_price"])
            target = last * (1 - retr) if action == "buy" else last * (1 + retr)
            if per_pos < last:
                log.warning("%s scartato: quota %.2f < prezzo azione %.2f (serve 1 azione intera).",
                            c["ticker"], per_pos, last)
                continue
            orders.append({
                "ticker": c["ticker"],
                "sector": c["sector"],
                "action": action,
                "reference_price": round(last, 2),
                "target_entry_price": round(target, 2),
                "allocated_capital": round(per_pos, 2),
            })

    payload = {
        "generated_at": now_cet().isoformat(timespec="seconds"),
        "session_date": session_date,
        "capital_usd": capital,
        "capital_simulated": simulated,
        "tier": tier["name"],
        "mode": tier["mode"],
        "available_usd": round(available, 2),
        "free_slots": slots,
        "orders": orders,
    }

    log.info("Capitale=%.2f | disponibile=%.2f | nuove posizioni=%d", capital, available, len(orders))
    for o in orders:
        log.info("  %-5s %-22s %-10s entry=%.2f cap=%.2f",
                 o["ticker"], o["sector"], o["action"], o["target_entry_price"], o["allocated_capital"])

    if dry_run:
        log.info("DRY-RUN: nessun file scritto.")
        return payload
    atomic_write_json(out_path, payload)
    log.info("Scritto %s", out_path)
    gitsync.sync(f"routine 02 portfolio {session_date}")
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
