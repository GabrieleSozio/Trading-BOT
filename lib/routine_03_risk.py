"""
Routine 03 — Risk Manager / Chief Risk Officer (logica deterministica).

Applica le Guardrails inviolabili agli ordini teorici del Portfolio Manager e
produce solo ordini approvati. In caso di dubbio: blocca, non approvare.
Scrive state/approved_orders.json.

Guardrails applicate, in ordine:
  R2 — Max position size 5% del portfolio_value
  R3 — Stop loss obbligatorio (-1.5% long / +1.5% short)
  TP — Take profit (+3% long / -3% short)
  R4 — Cap di settore 15% del portfolio_value

Uso:  python -m lib.routine_03_risk [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
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

log = logging.getLogger("routine03")

# Capitale minimo sotto cui un ordine ridotto da R4 non vale la pena: si scarta.
MIN_ALLOC_USD = 1.0


def run(dry_run: bool = False) -> dict | None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    g = cfg["guardrails"]
    max_pos = g["max_position_size_pct"]
    sl_pct = g["stop_loss_pct"]
    tp_pct = g["take_profit_pct"]
    max_sector = g["max_sector_exposure_pct"]
    in_path = cfg["state"]["files"]["target_orders"]
    out_path = cfg["state"]["files"]["approved_orders"]
    session_date = today_session_date()

    # --- Idempotenza: output di oggi gia' presente -> non rifare. ---
    if Path(out_path).exists() and read_json(out_path).get("session_date") == session_date:
        log.info("approved_orders di oggi gia' presente: skip (idempotente).")
        return read_json(out_path)

    # --- Input non pronto = ATTESA (no-op, exit 0), non errore. ---
    if not Path(in_path).exists() or read_json(in_path).get("session_date") != session_date:
        log.info("Input 02 non ancora pronto per oggi (%s): no-op, riprovo al prossimo trigger.", session_date)
        return None
    target = read_json(in_path)
    in_orders = target.get("orders", [])

    # --- portfolio_value REALE dal broker: senza, non si applicano le guardrail ---
    client = AlpacaClient(max_consecutive_errors=g["max_consecutive_api_errors"])
    try:
        acct = client.account()
    except GuardrailR5:
        log.error("R5: troppi errori broker leggendo l'account. Stop.")
        sys.exit(1)
    portfolio_value = float(acct["portfolio_value"])
    if portfolio_value <= 0:
        log.error("portfolio_value non valido (%.2f). Stop senza output.", portfolio_value)
        sys.exit(1)

    pos_cap = portfolio_value * max_pos
    sector_cap = portfolio_value * max_sector
    guardrails_applied = ["R2_max_size", "R3_stop_loss", "take_profit", "R4_sector_cap"]

    approved = []
    sector_used = defaultdict(float)
    n_r2 = 0
    discarded = []

    # Processa per allocazione decrescente: i piu' grandi competono per primi sul cap settore.
    for o in sorted(in_orders, key=lambda x: x["allocated_capital"], reverse=True):
        alloc = float(o["allocated_capital"])
        # R2
        if alloc > pos_cap:
            log.info("R2: %s ridotto da %.2f a %.2f (5%% di %.2f)", o["ticker"], alloc, pos_cap, portfolio_value)
            alloc = pos_cap
            n_r2 += 1
        # R4 — spazio rimanente nel settore
        sector = o["sector"]
        room = sector_cap - sector_used[sector]
        if room <= MIN_ALLOC_USD:
            discarded.append((o["ticker"], sector, "R4_sector_cap", alloc))
            log.info("R4: %s SCARTATO (settore %s saturo, room=%.2f)", o["ticker"], sector, room)
            continue
        if alloc > room:
            log.info("R4: %s ridotto da %.2f a %.2f (cap settore %s %.2f)", o["ticker"], alloc, room, sector, sector_cap)
            alloc = room
        sector_used[sector] += alloc

        entry = float(o["target_entry_price"])
        if o["action"] == "buy":
            stop = entry * (1 - sl_pct)
            tp = entry * (1 + tp_pct)
        else:  # sell_short
            stop = entry * (1 + sl_pct)
            tp = entry * (1 - tp_pct)

        approved.append({
            "ticker": o["ticker"],
            "sector": sector,
            "action": o["action"],
            "target_entry_price": round(entry, 2),
            "allocated_capital": round(alloc, 2),
            "stop_loss_price": round(stop, 2),
            "take_profit_price": round(tp, 2),
        })

    payload = {
        "generated_at": now_cet().isoformat(timespec="seconds"),
        "session_date": session_date,
        "portfolio_value": round(portfolio_value, 2),
        "guardrails_applied": guardrails_applied,
        "orders": approved,
    }

    log.info("portfolio_value=%.2f | in=%d approvati=%d | R2 ridotti=%d | scartati R4=%d",
             portfolio_value, len(in_orders), len(approved), n_r2, len(discarded))
    for s, used in sector_used.items():
        log.info("  esposizione settore %-22s = %.2f / cap %.2f", s, used, sector_cap)

    if dry_run:
        log.info("DRY-RUN: nessun file scritto.")
        return payload
    atomic_write_json(out_path, payload)
    log.info("Scritto %s", out_path)
    gitsync.sync(f"routine 03 risk {session_date}")
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
