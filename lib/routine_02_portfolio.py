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
from . import gitsync

log = logging.getLogger("routine02")


def run(dry_run: bool = False) -> dict | None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    n_open = cfg["allocation"]["positions_to_open"]
    metric = cfg["allocation"]["selection_metric"]
    retr = cfg["allocation"]["entry_retracement_pct"]
    in_path = cfg["state"]["files"]["market_research"]
    out_path = cfg["state"]["files"]["target_orders"]
    session_date = today_session_date()

    # --- Input + validazione anti-staffetta-rotta ---
    if not Path(in_path).exists():
        log.error("Input mancante: %s. Staffetta rotta, stop.", in_path)
        sys.exit(1)
    research = read_json(in_path)
    if research.get("session_date") != session_date:
        log.error("Input obsoleto: session_date=%s != oggi=%s. Stop.",
                  research.get("session_date"), session_date)
        sys.exit(1)
    candidates = research.get("candidates", [])
    if not candidates:
        log.warning("Nessun candidato in input. Scrivo orders vuoto.")
        candidates = []

    client = AlpacaClient(max_consecutive_errors=cfg["guardrails"]["max_consecutive_api_errors"])
    try:
        acct = client.account()
    except GuardrailR5:
        log.error("R5: troppi errori broker leggendo l'account. Stop.")
        sys.exit(1)
    buying_power = float(acct["buying_power"])

    orders = []
    if buying_power <= 1.0 or not candidates:
        log.warning("Buying power insufficiente (%.2f) o nessun candidato -> giornata in stand-by.", buying_power)
    else:
        # Seleziona i top-N per metrica (default: premarket_volume)
        chosen = sorted(candidates, key=lambda c: c.get(metric, 0), reverse=True)[:n_open]
        per_pos = buying_power / n_open
        for c in chosen:
            action = "buy" if c["trend"] == "Bullish" else "sell_short"
            last = c["last_price"]
            if action == "buy":
                target = last * (1 - retr)
            else:
                target = last * (1 + retr)
            orders.append({
                "ticker": c["ticker"],
                "sector": c["sector"],
                "action": action,
                "target_entry_price": round(target, 2),
                "allocated_capital": round(per_pos, 2),
            })

    payload = {
        "generated_at": now_cet().isoformat(timespec="seconds"),
        "session_date": session_date,
        "buying_power": round(buying_power, 2),
        "orders": orders,
    }

    log.info("Buying power=%.2f | posizioni scelte=%d", buying_power, len(orders))
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
