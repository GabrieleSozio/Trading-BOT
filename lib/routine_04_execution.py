"""
Routine 04 — Execution Desk (logica deterministica, idempotente).

UNICA routine che invia ordini reali. Ogni invocazione (CRON ~ogni minuto) e' un
*tick*. Lo stato persistente vive su Alpaca (ordini/posizioni reali) e in
state/daily_executions_log.json. All'avvio di ogni tick lo stato viene ricostruito
dal broker -> idempotente e sicura ai riavvii.

Sequenza di ogni tick:
  1. Determina fase oraria (CET).
  2. Ricostruisci stato dal broker (equity, posizioni, ordini).
  3. R1 Kill Switch (per primo).
  4. Esecuzione sul ritracciamento (15:30 -> 21:45) con Bracket Order (R3).
  5. Liquidazione EOD flat (>= 21:45).
  6. >= 21:46: scrive closing_balance ed esce.

R5 (3 errori broker consecutivi) e' gestita dall'AlpacaClient che solleva GuardrailR5.

Uso:  python -m lib.routine_04_execution            (LIVE: puo' inviare ordini)
      python -m lib.routine_04_execution --dry-run  (simula, NON invia nulla)
      ... --force-phase execute|eod|close           (test off-hours)
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import math
import sys
from pathlib import Path

from .alpaca_rest import (
    AlpacaClient,
    BrokerError,
    GuardrailR5,
    atomic_write_json,
    load_config,
    now_cet,
    read_json,
    today_session_date,
)
from . import gitsync

log = logging.getLogger("routine04")


def _hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def _phase(now: dt.datetime, cfg: dict, force_phase: str | None) -> str:
    if force_phase:
        return force_phase
    sched = cfg["schedule_cet"]
    start = _hhmm(sched["execution_start"])
    eod = _hhmm(sched["execution_eod_flat"])
    stop = _hhmm(sched["execution_stop"])
    t = now.time()
    if t >= stop:
        return "close"
    if t >= eod:
        return "eod"
    if t >= start:
        return "execute"
    return "idle"


def _load_or_init_log(path: str, session_date: str, opening_balance: float) -> dict:
    p = Path(path)
    if p.exists():
        data = read_json(p)
        if data.get("session_date") == session_date:
            return data
    # nuovo giorno (o file assente): primo tick -> registra opening_balance
    return {
        "session_date": session_date,
        "opening_balance": round(opening_balance, 2),
        "closing_balance": None,
        "kill_switch_triggered": False,
        "events": [],
    }


def _event(state: dict, etype: str, **fields):
    ev = {"ts": now_cet().isoformat(timespec="seconds"), "type": etype}
    ev.update(fields)
    state["events"].append(ev)
    log.info("EVENT %s %s", etype, {k: v for k, v in fields.items()})


def run(dry_run: bool = False, force_phase: str | None = None) -> dict | None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    g = cfg["guardrails"]
    max_dd = g["max_daily_drawdown_pct"]
    log_path = cfg["state"]["files"]["executions_log"]
    approved_path = cfg["state"]["files"]["approved_orders"]
    session_date = today_session_date()
    now = now_cet()
    phase = _phase(now, cfg, force_phase)
    log.info("TICK %s CET | fase=%s | dry_run=%s", now.isoformat(timespec="seconds"), phase, dry_run)

    if phase == "idle":
        log.info("Prima di execution_start: nessuna azione.")
        return None

    client = AlpacaClient(max_consecutive_errors=g["max_consecutive_api_errors"])

    # --- 2. Stato dal broker ---
    try:
        acct = client.account()
        positions = client.list_positions()
        open_orders = client.list_orders(status="open")
    except GuardrailR5:
        log.error("R5: troppi errori broker consecutivi. Sospensione tick.")
        sys.exit(1)
    equity = float(acct["equity"])

    state = _load_or_init_log(log_path, session_date, equity)
    opening_balance = state["opening_balance"]
    events_before = len(state["events"])

    # Se gia' ibernato dal kill switch oggi: non fare piu' nulla.
    if state.get("kill_switch_triggered"):
        log.warning("Kill switch gia' attivo oggi: iberno, nessuna azione.")
        if phase == "close":
            state["closing_balance"] = round(equity, 2)
            if not dry_run:
                atomic_write_json(log_path, state)
                gitsync.sync(f"routine 04 execution close {session_date}")
        return state

    pos_symbols = {p["symbol"] for p in positions}
    open_order_symbols = {o["symbol"] for o in open_orders}

    # --- 3. R1 Kill Switch (per primo) ---
    pnl = (equity - opening_balance) / opening_balance if opening_balance else 0.0
    log.info("equity=%.2f opening=%.2f PnL=%+.3f%%", equity, opening_balance, pnl * 100)
    if pnl <= -max_dd:
        log.error("R1 KILL SWITCH: PnL %.3f%% <= -%.1f%%. Chiudo tutto e iberno.", pnl * 100, max_dd * 100)
        if not dry_run:
            try:
                client.close_all_positions(cancel_orders=True)
                client.cancel_all_orders()
            except BrokerError as e:
                log.error("Errore durante kill switch: %s", e)
        _event(state, "KILL_SWITCH", pnl_pct=round(pnl * 100, 3), equity=round(equity, 2))
        state["kill_switch_triggered"] = True
        state["closing_balance"] = round(equity, 2)
        if not dry_run:
            atomic_write_json(log_path, state)
            gitsync.sync(f"routine 04 KILL_SWITCH {session_date}")
        return state

    # --- 5. Liquidazione EOD ---
    if phase in ("eod", "close"):
        if pos_symbols or open_order_symbols:
            log.info("EOD flat: chiudo %d posizioni, cancello ordini.", len(pos_symbols))
            if not dry_run:
                try:
                    client.close_all_positions(cancel_orders=True)
                    client.cancel_all_orders()
                except BrokerError as e:
                    log.error("Errore durante liquidazione EOD: %s", e)
            _event(state, "LIQUIDATE_ALL", reason="EOD flat", positions=sorted(pos_symbols))
        else:
            log.info("EOD: nessuna posizione/ordine da chiudere.")
        if phase == "close":
            state["closing_balance"] = round(equity, 2)
            log.info("Sessione chiusa. closing_balance=%.2f", equity)
        if not dry_run:
            atomic_write_json(log_path, state)
            gitsync.sync(f"routine 04 execution {phase} {session_date}")
        return state

    # --- 1. Carica ordini approvati (fase execute) ---
    if not Path(approved_path).exists():
        log.error("approved_orders.json assente: niente da eseguire. Esco senza inviare.")
        sys.exit(1)
    approved = read_json(approved_path)
    if approved.get("session_date") != session_date:
        log.error("approved_orders obsoleto (%s != %s). Esco senza inviare.",
                  approved.get("session_date"), session_date)
        sys.exit(1)
    authorized = approved.get("orders", [])
    auth_tickers = {o["ticker"] for o in authorized}

    # ordini gia' visti oggi (qualsiasi stato) -> idempotenza
    try:
        all_today = client.list_orders(status="all")
    except GuardrailR5:
        log.error("R5: stop.")
        sys.exit(1)
    today_iso = now.date().isoformat()
    seen_symbols = {o["symbol"] for o in all_today
                    if (o.get("submitted_at") or o.get("created_at") or "")[:10] >= today_iso}
    handled = pos_symbols | open_order_symbols | seen_symbols

    # --- 4. Esecuzione sul ritracciamento ---
    submitted = 0
    for o in authorized:
        tkr = o["ticker"]
        if tkr not in auth_tickers:
            continue  # difensivo: mai operare fuori lista
        if tkr in handled:
            log.info("%s gia' gestito oggi (posizione/ordine esistente): skip.", tkr)
            continue
        try:
            price = client.latest_trade(tkr)
        except GuardrailR5:
            log.error("R5: stop.")
            sys.exit(1)
        if not price:
            log.warning("%s: prezzo non disponibile, salto questo tick.", tkr)
            continue
        target = o["target_entry_price"]
        action = o["action"]
        crossed = (action == "buy" and price <= target) or (action == "sell_short" and price >= target)
        if not crossed:
            log.info("%s %s: prezzo %.2f non ha incrociato target %.2f.", tkr, action, price, target)
            continue
        qty = math.floor(o["allocated_capital"] / price)
        if qty < 1:
            log.warning("%s: qty<1 (cap %.2f / prezzo %.2f), salto.", tkr, o["allocated_capital"], price)
            continue
        side = "buy" if action == "buy" else "sell"
        coid = f"bot-{session_date}-{tkr}"  # client_order_id stabile -> doppia idempotenza
        log.info("%s: incrocio target. Invio BRACKET %s qty=%d entry~%.2f sl=%.2f tp=%.2f",
                 tkr, side, qty, price, o["stop_loss_price"], o["take_profit_price"])
        if dry_run:
            _event(state, "ORDER_SUBMITTED", ticker=tkr, dry_run=True, qty=qty,
                   entry=price, stop_loss=o["stop_loss_price"], take_profit=o["take_profit_price"])
            submitted += 1
            continue
        try:
            res = client.submit_bracket_order(
                symbol=tkr, qty=qty, side=side,
                take_profit_price=o["take_profit_price"],
                stop_loss_price=o["stop_loss_price"],
                client_order_id=coid,
            )
            _event(state, "ORDER_SUBMITTED", ticker=tkr, alpaca_order_id=res.get("id"),
                   qty=qty, entry=price, stop_loss=o["stop_loss_price"], take_profit=o["take_profit_price"])
            submitted += 1
        except BrokerError as e:
            log.error("%s: invio ordine fallito: %s", tkr, e)
            _event(state, "API_ERROR", ticker=tkr, detail=str(e)[:200])

    log.info("Tick completato: ordini inviati=%d", submitted)
    if not dry_run:
        atomic_write_json(log_path, state)
        if len(state["events"]) > events_before:  # push solo se e' successo qualcosa
            gitsync.sync(f"routine 04 execution tick {session_date}")
    return state


def loop(dry_run: bool = False, interval: int = 60):
    """Esegue un tick ogni `interval` secondi finche' la sessione non e' chiusa.
    Pensato per essere lanciato una volta al giorno (es. 15:30 CET) come singolo
    processo, evitando ~420 sessioni schedulate/giorno con jitter di dispatch."""
    import time
    cfg = load_config()
    while True:
        phase = _phase(now_cet(), cfg, None)
        run(dry_run=dry_run, force_phase=None)
        if phase == "close":
            log.info("Fase di chiusura raggiunta: loop terminato.")
            break
        time.sleep(interval)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="simula senza inviare ordini")
    ap.add_argument("--loop", action="store_true", help="cicla ogni 60s fino a chiusura sessione")
    ap.add_argument("--force-phase", choices=["idle", "execute", "eod", "close"], default=None)
    args = ap.parse_args()
    if args.loop:
        loop(dry_run=args.dry_run)
    else:
        run(dry_run=args.dry_run, force_phase=args.force_phase)
