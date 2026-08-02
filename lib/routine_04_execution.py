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
from . import capital as cap_mod
from . import gitsync
from . import pdt

log = logging.getLogger("routine04")

# Oltre questa distanza fra due tick si considera che il bot sia stato fermo
# (riavvio, black-out, sospensione) e lo si registra come interruzione.
GAP_ALERT_MINUTES = 5


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


def _holdings_path(cfg: dict) -> Path:
    return Path(cfg["state"]["dir"]) / "holdings.json"


def _load_holdings(cfg: dict) -> dict:
    """Mappa ticker -> data di apertura, per far rispettare max_hold_days in swing."""
    p = _holdings_path(cfg)
    if p.exists():
        try:
            return read_json(p)
        except Exception:  # noqa: BLE001 — file corrotto: si riparte pulito
            log.warning("holdings.json illeggibile: lo rigenero.")
    return {}


def _save_holdings(cfg: dict, holdings: dict, current: set, session_date: str) -> None:
    """Registra le nuove posizioni con la data odierna e dimentica quelle chiuse."""
    updated = {s: holdings.get(s, {"opened_session_date": session_date}) for s in current}
    atomic_write_json(_holdings_path(cfg), updated)


def _trading_days_between(client, start_date: str, end_date: str) -> int:
    """Giorni di borsa trascorsi DALL'apertura (esclusa) a oggi (incluso)."""
    if start_date >= end_date:
        return 0
    try:
        cal = client.calendar(start_date, end_date)
        return max(0, len(cal) - 1)
    except Exception:  # noqa: BLE001 — se il calendario non risponde, non forzare chiusure
        log.warning("Calendario broker non disponibile: salto il controllo giorni.")
        return 0


def _stale_positions(client, cfg: dict, holdings: dict, symbols: set,
                     max_hold: int, session_date: str) -> list:
    """Posizioni aperte da piu' di max_hold giorni di borsa."""
    if max_hold <= 0:
        return []
    out = []
    for s in sorted(symbols):
        opened = (holdings.get(s) or {}).get("opened_session_date")
        if not opened:
            continue  # sconosciuta: la registriamo oggi, conta da adesso
        if _trading_days_between(client, opened, session_date) >= max_hold:
            out.append(s)
    return out


def _event(state: dict, etype: str, **fields):
    ev = {"ts": now_cet().isoformat(timespec="seconds"), "type": etype}
    ev.update(fields)
    state["events"].append(ev)
    log.info("EVENT %s %s", etype, {k: v for k, v in fields.items()})


def run(dry_run: bool = False, force_phase: str | None = None) -> dict | None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    g = cfg["guardrails"]
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

    # --- Capitale operativo e fascia attiva (determinano rischio e strategia) ---
    capital, simulated = cap_mod.effective_capital(cfg, equity, client)
    tier = cap_mod.resolve_tier(cfg, capital)
    max_dd = float(tier["max_daily_drawdown_pct"])
    intraday = cap_mod.is_intraday(tier)
    max_hold = int(tier.get("max_hold_days", 0) or 0)
    log.info("%s", cap_mod.describe(tier, capital, simulated))

    state = _load_or_init_log(log_path, session_date, equity)
    opening_balance = state["opening_balance"]
    events_before = len(state["events"])

    # --- Rilevatore di interruzioni ---
    # Il bot gira su una macchina fisica: un'assenza di corrente, un riavvio o una
    # sospensione lo fermano senza preavviso. Le posizioni restano protette (stop e
    # take profit vivono sul broker), ma in quella finestra non si opera. Qui il
    # buco viene registrato, cosi' resta visibile nell'audit invece di passare inosservato.
    prev_tick = state.get("last_tick_at")
    if prev_tick:
        try:
            gap_min = (now - dt.datetime.fromisoformat(prev_tick)).total_seconds() / 60.0
            if gap_min > GAP_ALERT_MINUTES:
                log.warning("INTERRUZIONE RILEVATA: %.0f minuti senza tick (ultimo: %s). "
                            "Il bot non ha operato in quella finestra.", gap_min, prev_tick[11:19])
                _event(state, "GAP_DETECTED", minutes=round(gap_min), last_tick=prev_tick)
        except ValueError:
            pass
    state["last_tick_at"] = now.isoformat(timespec="seconds")

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
    holdings = _load_holdings(cfg)

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

    # --- 5. Fine giornata: il comportamento dipende dalla STRATEGIA della fascia ---
    if phase in ("eod", "close"):
        if intraday:
            # INTRADAY: flat obbligatorio, nessuna posizione overnight.
            if pos_symbols or open_order_symbols:
                log.info("EOD flat (intraday): chiudo %d posizioni, cancello ordini.", len(pos_symbols))
                if not dry_run:
                    try:
                        client.close_all_positions(cancel_orders=True)
                        client.cancel_all_orders()
                    except BrokerError as e:
                        log.error("Errore durante liquidazione EOD: %s", e)
                _event(state, "LIQUIDATE_ALL", reason="EOD flat", positions=sorted(pos_symbols))
            else:
                log.info("EOD: nessuna posizione/ordine da chiudere.")
        else:
            # SWING: le posizioni restano aperte (protette dal bracket GTC sul
            # broker). Si chiudono solo quelle che superano il limite di giorni.
            stale = _stale_positions(client, cfg, holdings, pos_symbols, max_hold, session_date)
            if stale:
                log.info("SWING: %d posizioni oltre %d giorni di borsa -> chiudo: %s",
                         len(stale), max_hold, stale)
                for sym in stale:
                    if dry_run:
                        continue
                    try:
                        client.close_position(sym)
                        _event(state, "LIQUIDATE_ALL", reason=f"max_hold_days {max_hold}", ticker=sym)
                    except BrokerError as e:
                        log.error("%s: chiusura per scadenza fallita: %s", sym, e)
            else:
                log.info("SWING: %d posizioni mantenute overnight (nessuna oltre %d giorni).",
                         len(pos_symbols), max_hold)
        first_close = False
        if phase == "close":
            first_close = state.get("closing_balance") is None
            state["closing_balance"] = round(equity, 2)
            log.info("Sessione chiusa. closing_balance=%.2f", equity)
        if not dry_run:
            _save_holdings(cfg, holdings, pos_symbols, session_date)
            atomic_write_json(log_path, state)
            # Si pubblica solo se e' successo qualcosa (o alla prima chiusura):
            # la fase di chiusura dura diversi minuti e altrimenti genererebbe
            # un commit al minuto tutti identici.
            if len(state["events"]) > events_before or first_close:
                gitsync.sync(f"routine 04 execution {phase} {session_date}")
        return state

    # --- 1. Carica ordini approvati (fase execute) ---
    # Se non sono pronti (staffetta non ancora completata oggi) NON e' un errore:
    # no-op silenzioso (exit 0) e si riprova al tick successivo. La liquidazione EOD
    # qui sopra avviene comunque, quindi eventuali posizioni vengono chiuse a fine giornata.
    if not Path(approved_path).exists() or read_json(approved_path).get("session_date") != session_date:
        log.info("approved_orders di oggi non ancora pronto: no-op, attendo la staffetta.")
        return None
    approved = read_json(approved_path)
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

    # --- 3-bis. Guard Pattern Day Trader ---
    # Anche operando in swing puo' capitare un round-trip in giornata (una posizione
    # aperta stamattina che colpisce il take profit nel pomeriggio): e' un day trade
    # a tutti gli effetti. Sotto i 25k USD se ne possono fare solo 3 ogni 5 giorni,
    # pena il blocco del conto. Qui ci fermiamo PRIMA di arrivarci.
    # Si valuta sul CAPITALE OPERATIVO (eventualmente simulato): cosi' il test in
    # paper riproduce fedelmente cio' che accadra' sul conto reale da ~220 USD.
    pdt_ok, pdt_msg = pdt.can_open_new_position(client, capital)
    log.info("%s", pdt_msg)
    if not pdt_ok:
        _event(state, "SUSPENDED", reason="PDT_limit", detail=pdt_msg[:180])
        log.warning("Nessuna nuova apertura: le posizioni esistenti restano gestite normalmente.")
        if not dry_run:
            atomic_write_json(log_path, state)
        return state

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

        # --- Protezioni ancorate al prezzo REALE d'ingresso ---
        # Il Risk Manager calcola stop e target sul prezzo PIANIFICATO delle 14:30.
        # Se il titolo si muove molto prima dell'ingresso, quelle soglie diventano
        # sbagliate: si e' visto uno stop finire a distanza zero dall'acquisto e
        # scattare dopo 3 minuti. Le percentuali di rischio restano quelle della
        # fascia (decise dal Risk Manager), ma vanno applicate al prezzo di adesso.
        sl_pct = float(tier["stop_loss_pct"])
        tp_pct = float(tier["take_profit_pct"])
        if action == "buy":
            stop_px, tp_px = price * (1 - sl_pct), price * (1 + tp_pct)
        else:
            stop_px, tp_px = price * (1 + sl_pct), price * (1 - tp_pct)
        stop_px, tp_px = round(stop_px, 2), round(tp_px, 2)
        if abs(stop_px - o["stop_loss_price"]) > 0.01:
            log.info("%s: protezioni ricalcolate sul prezzo reale %.2f -> stop %.2f / target %.2f "
                     "(da piano erano %.2f / %.2f)", tkr, price, stop_px, tp_px,
                     o["stop_loss_price"], o["take_profit_price"])
        # In swing la posizione resta aperta piu' giorni: stop e take profit devono
        # sopravvivere alla notte -> GTC. In intraday basta 'day' (si chiude comunque).
        tif = "day" if intraday else "gtc"
        log.info("%s: incrocio target. Invio BRACKET %s qty=%d entry~%.2f sl=%.2f tp=%.2f (tif=%s)",
                 tkr, side, qty, price, stop_px, tp_px, tif)
        if dry_run:
            _event(state, "ORDER_SUBMITTED", ticker=tkr, dry_run=True, qty=qty,
                   entry=price, stop_loss=stop_px, take_profit=tp_px)
            submitted += 1
            continue
        try:
            res = client.submit_bracket_order(
                symbol=tkr, qty=qty, side=side,
                take_profit_price=tp_px,
                stop_loss_price=stop_px,
                tif=tif,
                client_order_id=coid,
            )
            _event(state, "ORDER_SUBMITTED", ticker=tkr, alpaca_order_id=res.get("id"),
                   qty=qty, entry=price, stop_loss=stop_px, take_profit=tp_px, tif=tif)
            holdings.setdefault(tkr, {"opened_session_date": session_date})
            submitted += 1
        except BrokerError as e:
            log.error("%s: invio ordine fallito: %s", tkr, e)
            _event(state, "API_ERROR", ticker=tkr, detail=str(e)[:200])

    log.info("Tick completato: ordini inviati=%d", submitted)
    if not dry_run:
        # Registra le posizioni correnti + quelle appena aperte (per max_hold_days)
        _save_holdings(cfg, holdings, pos_symbols | {o["ticker"] for o in authorized
                                                    if o["ticker"] in holdings}, session_date)
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
