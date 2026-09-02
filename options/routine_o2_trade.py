"""
routine_o2_trade.py — OPZIONI / Esecuzione e gestione.

L'UNICA routine della divisione opzioni che invia ordini. Gira ogni 15 minuti
durante la sessione americana.

Ordine delle operazioni a ogni giro, e non e' casuale:
  1. verifica del conto e del freno di emergenza
  2. registra cio' che si e' chiuso da solo (scadenza, esecuzione di un limite)
  3. GESTISCE le posizioni aperte: uscite per livello, per tempo, per fine giornata
  4. ENTRA sui contratti selezionati, se c'e' capienza

Si esce PRIMA di entrare: non si apre rischio nuovo mentre quello vecchio e'
ancora da valutare.

Tre cose rendono questo strumento diverso da azioni e cripto:

  * LO SPREAD E' ENORME (1-8% invece dello 0,05%). Un ordine a mercato regala
    meta' dello spread alla controparte a ogni passaggio. Qui si usano ordini a
    LIMITE, calcolati fra denaro e lettera.
  * IL VALORE DECADE. Una posizione giusta sulla direzione puo' perdere lo
    stesso se il movimento arriva tardi. Non e' un difetto: e' il prezzo della
    convessita'.
  * LA PERDITA E' LIMITATA AL PREMIO. Non serve uno stop depositato sul broker
    come sulle cripto: il peggio che puo' capitare e' gia' definito all'acquisto.
    Gli stop qui servono a uscire PRIMA di perdere tutto, non a evitare la rovina.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

from lib.alpaca_rest import atomic_write_json, read_json, now_cet, BrokerError
from lib import pdt
from options.broker import OptionsClient, load_config, MOLTIPLICATORE

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("options.o2")

REPO = Path(__file__).resolve().parent.parent
FILL_POLL_SECONDS = 3
FILL_POLL_TRIES = 6


# =====================================================================
#  Stato
# =====================================================================
def _load_state(cfg: dict) -> dict:
    try:
        return read_json(REPO / cfg["state"]["files"]["positions"])
    except Exception:  # noqa: BLE001 — primo avvio
        return {"positions": {}, "peak_equity": 0.0, "events": [], "closed_trades": []}


def _save_state(cfg: dict, st: dict) -> None:
    st["updated_at"] = now_cet().isoformat(timespec="seconds")
    st["events"] = st.get("events", [])[-200:]
    atomic_write_json(REPO / cfg["state"]["files"]["positions"], st)


def _event(st: dict, kind: str, **f) -> None:
    st.setdefault("events", []).append(
        {"at": now_cet().isoformat(timespec="seconds"), "event": kind, **f})


def _safe(st: dict, chi: str, cosa: str, fn, *a, **k) -> int:
    """Contiene l'errore su UNA posizione: le altre devono essere gestite comunque.

    Sulle cripto un guasto su una singola coppia uccideva l'intera routine per
    ore. Qui l'errore viene registrato e si prosegue.
    """
    try:
        return int(fn(*a, **k) or 0)
    except Exception as e:  # noqa: BLE001 — deliberato
        log.error("%s: %s fallita (%s: %s). Proseguo.", chi, cosa, type(e).__name__, str(e)[:180])
        _event(st, "errore_isolato", soggetto=chi, fase=cosa, errore=str(e)[:180])
        return 0


# =====================================================================
#  Prezzi limite
# =====================================================================
def _limite_acquisto(cli, snap: dict, quota: float = 0.6) -> float | None:
    """Prezzo a cui comprare: fra denaro e lettera, spostato verso la lettera.

    Comprare alla lettera significa pagare tutto lo spread; offrire al denaro
    spesso non riempie. Con 0,6 si paga il 60% dello spread in cambio di una
    ragionevole probabilita' di esecuzione.
    """
    q = (snap or {}).get("latestQuote") or {}
    bid, ask = float(q.get("bp") or 0), float(q.get("ap") or 0)
    if bid <= 0 or ask <= 0:
        return None
    return round(bid + (ask - bid) * quota, 2)


def _limite_vendita(cli, snap: dict) -> float | None:
    """Prezzo a cui vendere: al denaro. In uscita conta riempire, non spuntare
    il centesimo — una posizione che non si chiude e' un rischio aperto."""
    q = (snap or {}).get("latestQuote") or {}
    bid = float(q.get("bp") or 0)
    return round(bid, 2) if bid > 0 else None


# =====================================================================
#  Chiusure
# =====================================================================
def _registra_chiusa(st: dict, sym: str, rec: dict, uscita: float,
                     motivo: str) -> None:
    """Operazione conclusa, con il rischio assunto (per i fattori di rischio).

    Il rischio di riferimento e' la perdita che ci si aspetta alla rete di
    sicurezza sul premio, non l'intero premio: uscire a -50% e' l'esito normale
    di una tesi sbagliata, perdere il 100% e' il caso in cui non si e' usciti.
    """
    entrata = float(rec.get("entry_premium") or 0)
    qty = int(rec.get("qty") or 1)
    pl = (uscita - entrata) * MOLTIPLICATORE * qty
    rischio = entrata * MOLTIPLICATORE * qty * float(rec.get("premium_stop_pct") or 0.5)
    st.setdefault("closed_trades", []).append({
        "symbol": sym, "ticker": rec.get("ticker"), "modo": rec.get("modo"),
        "opened_at": rec.get("opened_at"),
        "closed_at": now_cet().isoformat(timespec="seconds"),
        "entry_premium": entrata, "exit_premium": round(uscita, 4), "qty": qty,
        "pl_usd": round(pl, 2),
        "pl_pct": round((uscita / entrata - 1) * 100, 2) if entrata else None,
        "risk_usd": round(rischio, 2) if rischio else None,
        "r_multiple": round(pl / rischio, 2) if rischio > 0 else None,
        "underlying_entry": rec.get("underlying_entry"),
        "motivo": motivo,
    })
    st["closed_trades"] = st["closed_trades"][-300:]


def _riconcilia(cli, st: dict, aperte: dict) -> None:
    """Posizioni sparite dal broker senza che le abbiamo chiuse noi.

    Sulle opzioni capita per scadenza o per un limite eseguito fra un giro e
    l'altro. Senza questo, il risultato non verrebbe mai contato e lo stato
    conserverebbe posizioni inesistenti.
    """
    for sym in list(st.get("positions", {})):
        if sym in aperte:
            continue
        rec = st["positions"].pop(sym)
        uscita = 0.0
        try:
            ordini = [o for o in cli.list_orders(status="closed", symbols=[sym])
                      if o.get("side") == "sell" and o.get("status") == "filled"
                      and o.get("filled_avg_price")]
            if ordini:
                ordini.sort(key=lambda o: o.get("filled_at") or "")
                uscita = float(ordini[-1]["filled_avg_price"])
        except BrokerError as e:
            log.warning("%s: uscita non ricostruibile (%s).", sym, str(e)[:120])
        motivo = "chiusa fuori dal bot" if uscita else "scaduta senza valore"
        log.info("%s: %s a %.2f", sym, motivo, uscita)
        _registra_chiusa(st, sym, rec, uscita, motivo)
        _event(st, "chiusa_esterna", symbol=sym, uscita=uscita, motivo=motivo)


def _chiudi(cli, cfg: dict, st: dict, sym: str, pos: dict, snap: dict,
            motivo: str, dry: bool) -> int:
    qty = abs(int(float(pos["qty"])))
    lim = _limite_vendita(cli, snap)
    pl = float(pos.get("unrealized_pl") or 0)
    log.info("%s: USCITA (%s) — %d contratti, P&L $%+.2f", sym, motivo, qty, pl)
    if dry:
        return 1
    try:
        cli.sell_to_close(sym, qty, limit_price=lim)
    except BrokerError as e:
        log.error("%s: ordine di uscita rifiutato (%s).", sym, str(e)[:160])
        _event(st, "uscita_fallita", symbol=sym, errore=str(e)[:160])
        return 1
    rec = st["positions"].pop(sym, None)
    if rec:
        _registra_chiusa(st, sym, rec, lim or 0.0, motivo)
    _event(st, "uscita", symbol=sym, motivo=motivo, pl_usd=round(pl, 2))
    return 1


def _valuta_uscita(cli, cfg: dict, st: dict, sym: str, pos: dict,
                   snap: dict, spot: float | None, dry: bool) -> int:
    """Decide se questa posizione va chiusa, e per quale motivo."""
    rec = st["positions"].get(sym) or {}
    e = cfg["exits"]
    ora = now_cet()

    # 1. fine giornata per le posizioni intraday
    if rec.get("modo") == "intraday":
        h, m = (cfg["modes"]["intraday"]["close_by"]).split(":")
        if ora.hour > int(h) or (ora.hour == int(h) and ora.minute >= int(m)):
            return _chiudi(cli, cfg, st, sym, pos, snap, "fine giornata (intraday)", dry)

    # 2. livelli sul SOTTOSTANTE — e' l'evento che decide, come sulle azioni
    if spot:
        if rec.get("stop_underlying") and spot <= float(rec["stop_underlying"]):
            return _chiudi(cli, cfg, st, sym, pos, snap,
                           f"stop sul titolo ({spot:.2f})", dry)
        if rec.get("target_underlying") and spot >= float(rec["target_underlying"]):
            return _chiudi(cli, cfg, st, sym, pos, snap,
                           f"obiettivo sul titolo ({spot:.2f})", dry)

    # 3. rete di sicurezza sul premio: protegge quando il titolo si muove poco
    #    ma il valore temporale evapora comunque
    entrata = float(rec.get("entry_premium") or 0)
    corrente = float(pos.get("current_price") or 0)
    if entrata > 0 and corrente > 0:
        var = corrente / entrata - 1
        if var <= -float(e["premium_stop_pct"]):
            return _chiudi(cli, cfg, st, sym, pos, snap,
                           f"premio a {var*100:+.0f}%", dry)
        if var >= float(e["premium_target_pct"]):
            return _chiudi(cli, cfg, st, sym, pos, snap,
                           f"premio a {var*100:+.0f}%", dry)

        # 3-bis. TRAILING sul premio: il massimo raggiunto sale, mai scende.
        # Protegge i guadagni intermedi, che altrimenti potevano tornare a zero
        # senza che nulla intervenisse.
        picco = max(float(rec.get("premium_peak") or 0), corrente, entrata)
        rec["premium_peak"] = picco
        guadagno_max = picco / entrata - 1
        if guadagno_max >= float(e["premium_trail_activate_pct"]):
            soglia = entrata * (1 + guadagno_max * (1 - float(e["premium_trail_giveback_pct"])))
            if corrente <= soglia:
                return _chiudi(cli, cfg, st, sym, pos, snap,
                               f"trailing: da {guadagno_max*100:+.0f}% a {var*100:+.0f}%", dry)

    # 4. tempo massimo
    apertura = (rec.get("opened_at") or "")[:10]
    if apertura and rec.get("modo") == "swing":
        try:
            giorni = (ora.date() - dt.date.fromisoformat(apertura)).days
            if giorni >= int(cfg["modes"]["swing"]["max_hold_days"]):
                return _chiudi(cli, cfg, st, sym, pos, snap,
                               f"scadenza tempo ({giorni} giorni)", dry)
        except ValueError:
            pass
    return 0


# =====================================================================
#  Ingressi
# =====================================================================
def _entra(cli, cfg: dict, st: dict, sel: dict, dry: bool) -> int:
    sym = sel["symbol"]
    snap = cli.quotes([sym]).get(sym)
    lim = _limite_acquisto(cli, snap)
    if lim is None:
        log.warning("%s: nessuna quotazione, salto.", sym)
        return 0
    costo = lim * MOLTIPLICATORE
    log.info("%s (%s %s): INGRESSO a limite %.2f = %.0f$ [strike %.1f, scad %s, spread %.1f%%]",
             sym, sel["ticker"], sel["modo"], lim, costo, sel["strike"],
             sel["expiration"], sel["spread_pct"])
    if dry:
        return 1

    o = cli.buy_to_open(sym, 1, limit_price=lim)
    riempito = None
    for _ in range(FILL_POLL_TRIES):
        time.sleep(FILL_POLL_SECONDS)
        cur = cli.order(o["id"])
        if cur.get("status") == "filled":
            riempito = cur
            break
        if cur.get("status") in ("canceled", "rejected", "expired"):
            log.warning("%s: ordine %s.", sym, cur.get("status"))
            _event(st, "ingresso_fallito", symbol=sym, stato=cur.get("status"))
            return 1
    if not riempito:
        # Un limite non eseguito resta appeso e impegna liquidita': si cancella
        # e si riprova al giro dopo, con una quotazione aggiornata.
        log.info("%s: limite non eseguito, cancello e riprovo al prossimo giro.", sym)
        try:
            cli.cancel_order(o["id"])
        except BrokerError:
            pass
        _event(st, "ingresso_non_eseguito", symbol=sym, limite=lim)
        return 1

    prezzo = float(riempito["filled_avg_price"])
    st["positions"][sym] = {
        "ticker": sel["ticker"], "modo": sel["modo"], "qty": 1,
        "entry_premium": prezzo,
        "underlying_entry": sel["spot"],
        "stop_underlying": sel["stop_underlying"],
        "target_underlying": sel["target_underlying"],
        "premium_stop_pct": float(cfg["exits"]["premium_stop_pct"]),
        "strike": sel["strike"], "expiration": sel["expiration"],
        "opened_at": now_cet().isoformat(timespec="seconds"),
    }
    _event(st, "ingresso", symbol=sym, ticker=sel["ticker"], modo=sel["modo"],
           premio=prezzo, costo_usd=round(prezzo * MOLTIPLICATORE, 2))
    log.info("%s: eseguito a %.2f (%.0f$). Stop titolo %.2f / obiettivo %.2f.",
             sym, prezzo, prezzo * MOLTIPLICATORE,
             sel["stop_underlying"], sel["target_underlying"])

    try:
        from lib import decisions
        reg = decisions.DecisionLog(REPO / cfg["state"]["dir"] / "decisions_log.json")
        reg.record(sel["ticker"], (
            f"Call {sel['ticker']} strike {sel['strike']} scad {sel['expiration']}, "
            f"{sel['otm_pct']:+.1f}% dal denaro, premio {prezzo*MOLTIPLICATORE:.0f}$, "
            f"spread {sel['spread_pct']:.1f}%. Modalita' {sel['modo']}, scarto "
            f"{sel['gap_pct']:+.2f}%."
        ), symbol=sym, modo=sel["modo"], premio=prezzo)
    except Exception as e:  # noqa: BLE001 — il registro non ferma un ordine
        log.warning("Registro decisioni non aggiornato: %s", e)
    return 1


# =====================================================================
def run(dry_run: bool = False) -> dict:
    cfg = load_config()
    cli = OptionsClient(cfg)
    acct = cli.assert_right_account()
    st = _load_state(cfg)

    equity = float(acct["equity"])
    picco = max(float(st.get("peak_equity") or 0), equity)
    st["peak_equity"] = picco
    dd = (picco - equity) / picco if picco > 0 else 0.0
    log.info("Conto %s | equity $%.2f | liquidita' $%.2f | massimo $%.2f | drawdown %.1f%%",
             acct["account_number"], equity, float(acct["cash"]), picco, dd * 100)

    maxdd = float(cfg["guardrails"]["max_drawdown_from_peak_pct"])
    bloccato = dd >= maxdd
    if bloccato:
        log.error("FRENO DI EMERGENZA: drawdown %.1f%% >= %.1f%%. Nessun ingresso nuovo.",
                  dd * 100, maxdd * 100)
        _event(st, "freno_emergenza", drawdown_pct=round(dd, 4))

    aperte = {p["symbol"]: p for p in cli.option_positions()}
    log.info("Posizioni aperte: %d", len(aperte))
    if not dry_run:
        _riconcilia(cli, st, aperte)

    budget = int(cfg["guardrails"]["max_orders_per_tick"])
    inviati = 0

    # --- gestione delle posizioni aperte ---
    if aperte:
        quot = cli.quotes(list(aperte))
        tick = {p.get("symbol") for p in aperte.values()}
        sottostanti = {(st["positions"].get(s) or {}).get("ticker") for s in aperte}
        sottostanti = {x for x in sottostanti if x}
        spot = cli.snapshots(list(sottostanti), feed="delayed_sip") if sottostanti else {}
        del tick
        for sym, pos in list(aperte.items()):
            if inviati >= budget:
                break
            t = (st["positions"].get(sym) or {}).get("ticker")
            s = ((spot.get(t) or {}).get("latestTrade") or {}).get("p") if t else None
            inviati += _safe(st, sym, "gestione", _valuta_uscita,
                             cli, cfg, st, sym, pos, quot.get(sym), s, dry_run)

    # --- ingressi ---
    if not bloccato:
        try:
            sel = read_json(REPO / cfg["state"]["files"]["selection"])
        except Exception:  # noqa: BLE001
            log.info("Nessuna selezione disponibile: esegui prima routine_o1_select.")
            sel = {"selezione": []}
        if sel.get("session_date") and sel["session_date"] != dt.date.today().isoformat():
            log.info("Selezione di un altro giorno (%s): ignorata.", sel["session_date"])
            sel = {"selezione": []}

        tetto = equity * float(cfg["modes"]["swing"]["max_total_premium_pct"])
        impegnato = sum(abs(float(p.get("cost_basis") or 0)) for p in aperte.values())
        cash = float(acct["cash"])
        usati, _ = pdt.count_recent_day_trades(cli)

        for x in sel.get("selezione", []):
            if inviati >= budget:
                log.info("Raggiunto il tetto di ordini per giro.")
                break
            if x["symbol"] in aperte:
                continue
            if x["modo"] == "intraday" and usati >= int(cfg["guardrails"]["day_trades_usable"]):
                log.info("%s: crediti intraday esauriti (%d), salto.", x["symbol"], usati)
                continue
            costo = float(x["premio_usd"])
            if impegnato + costo > tetto:
                log.info("%s: %.0f$ sforerebbe il tetto (%.0f$ su %.0f$), salto.",
                         x["symbol"], costo, impegnato, tetto)
                continue
            if costo > cash:
                log.info("%s: liquidita' insufficiente ($%.2f).", x["symbol"], cash)
                continue
            n = _safe(st, x["symbol"], "ingresso", _entra, cli, cfg, st, x, dry_run)
            inviati += n
            if n and not dry_run:
                acct = cli.account()
                cash = float(acct["cash"])
                impegnato += costo

    if not dry_run:
        _save_state(cfg, st)
    log.info("Giro concluso: %d operazioni%s.", inviati, " (dry-run)" if dry_run else "")
    return {"ok": True, "orders": inviati}


def main() -> int:
    ap = argparse.ArgumentParser(description="Opzioni — esecuzione e gestione")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    res = run(dry_run=a.dry_run)
    if res.get("ok") and not a.dry_run and res.get("orders") and not a.no_push:
        from lib import gitsync
        gitsync.sync(f"opzioni: operativita' {dt.date.today().isoformat()}")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
