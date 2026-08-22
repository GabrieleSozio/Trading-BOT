"""
routine_c2_trade.py — CRIPTO / Esecuzione e gestione posizioni.

L'UNICA routine della divisione cripto che invia ordini. Gira ogni 30 minuti,
24/7 (il mercato cripto non chiude).

Cosa fa a ogni giro, in quest'ordine:
  1. verifica di essere sul conto giusto e che il freno di emergenza non sia tirato
  2. PROTEGGE: ogni posizione senza stop attivo ne riceve uno subito
  3. ALZA il trailing stop delle posizioni in guadagno (mai lo abbassa)
  4. ESCE dalle posizioni uscite dalla classifica
  5. ENTRA nelle nuove selezionate, se c'e' capitale

L'ordine non e' casuale: si protegge PRIMA di aprire nuovo rischio.

Vincolo del broker che governa tutto: sulle cripto Alpaca ammette UNA SOLA
sell order per posizione. Non esistono i bracket. Quindi la protezione e' uno
stop-limit singolo, che si SOSTITUISCE (PATCH) invece di cancellarlo e
ricrearlo: cancellare lascerebbe la posizione scoperta per qualche secondo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

from lib.alpaca_rest import atomic_write_json, read_json, now_cet, BrokerError
from crypto.broker import CryptoClient, load_config, to_pair

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s"
)
log = logging.getLogger("crypto.c2")

FILL_POLL_SECONDS = 2
FILL_POLL_TRIES = 10


# =====================================================================
#  Stato locale
# =====================================================================
def _load_state(cfg: dict) -> dict:
    try:
        return read_json(cfg["state"]["files"]["positions"])
    except Exception:  # noqa: BLE001 — primo avvio o file assente
        return {"positions": {}, "peak_equity": 0.0, "events": []}


def _save_state(cfg: dict, st: dict) -> None:
    st["updated_at"] = now_cet().isoformat(timespec="seconds")
    st["events"] = st.get("events", [])[-200:]
    atomic_write_json(cfg["state"]["files"]["positions"], st)


def _record_closed(st: dict, pair: str, rec: dict, exit_px: float,
                   pl_usd: float, motivo: str) -> None:
    """Registra un'operazione conclusa con il RISCHIO che era stato assunto.

    Serve per misurare i risultati in fattori di rischio. Su questa divisione e'
    indispensabile: gli stop vanno dal 4% (BTC) al 30% (monete molto volatili),
    quindi confrontare fra loro le percentuali di guadagno non dice nulla. Un
    +5% con stop al 4% e un +5% con stop al 20% sono risultati diversissimi.

    Il rischio va calcolato QUI e non dopo: una volta chiusa la posizione, la
    distanza dello stop di ingresso non e' piu' ricostruibile dal broker.
    """
    entry = float(rec.get("entry_price") or 0)
    qty = float(rec.get("qty") or 0)
    dist = float(rec.get("stop_distance_pct") or 0)
    risk = entry * qty * dist
    st.setdefault("closed_trades", []).append({
        "pair": pair,
        "opened_at": rec.get("opened_at"),
        "closed_at": now_cet().isoformat(timespec="seconds"),
        "entry": entry,
        "exit": round(exit_px, 10) if exit_px else None,
        "qty": qty,
        "stop_distance_pct": dist,
        "pl_usd": round(pl_usd, 2),
        "pl_pct": round((exit_px / entry - 1) * 100, 2) if entry and exit_px else None,
        "risk_usd": round(risk, 2) if risk else None,
        "r_multiple": round(pl_usd / risk, 2) if risk > 0 else None,
        "motivo": motivo,
    })
    st["closed_trades"] = st["closed_trades"][-300:]


def _reconcile_closed(cli, st: dict, positions: dict) -> None:
    """Posizioni sparite dal broker senza che il bot le abbia chiuse.

    Significa che e' scattato lo stop depositato: e' l'esito piu' frequente e
    finora non veniva registrato da nessuna parte. Senza questo, le operazioni
    perdenti sparivano dal conteggio e lo stato conservava per sempre posizioni
    che non esistono piu'.
    """
    for pair in list(st.get("positions", {})):
        if pair in positions:
            continue
        rec = st["positions"].pop(pair)
        exit_px, pl = 0.0, 0.0
        try:
            vendite = [o for o in cli.list_orders(status="closed", symbols=[pair])
                       if o.get("side") == "sell" and o.get("status") == "filled"
                       and o.get("filled_avg_price")]
            vendite.sort(key=lambda o: o.get("filled_at") or "")
            if vendite:
                ultima = vendite[-1]
                exit_px = float(ultima["filled_avg_price"])
                qty = float(ultima.get("filled_qty") or rec.get("qty") or 0)
                pl = (exit_px - float(rec.get("entry_price") or exit_px)) * qty
        except BrokerError as e:
            log.warning("%s: uscita non ricostruibile (%s).", pair, str(e)[:120])
        log.info("%s: chiusa dal broker (stop) a %.8f, risultato $%+.2f", pair, exit_px, pl)
        _record_closed(st, pair, rec, exit_px, pl, "stop sul broker")
        _event(st, "chiusa_da_stop", pair=pair, prezzo=exit_px, pl_usd=round(pl, 2))


def _event(st: dict, kind: str, **fields) -> None:
    st.setdefault("events", []).append(
        {"at": now_cet().isoformat(timespec="seconds"), "event": kind, **fields}
    )


# =====================================================================
#  Quarantena delle coppie non eseguibili
# =====================================================================
# Alcune coppie sono in elenco e quotate, ma un ordine a mercato resta
# appeso senza riempirsi (visto dal vivo su HYPE/USD). Ritentare ogni
# mezz'ora e' inutile: si mettono in quarantena per un giorno.
QUARANTINE_AFTER_FAILURES = 2
QUARANTINE_HOURS = 24


def _register_fill_failure(cfg: dict, st: dict, pair: str) -> None:
    q = st.setdefault("fill_failures", {})
    rec = q.setdefault(pair, {"count": 0})
    rec["count"] += 1
    rec["last_at"] = now_cet().isoformat(timespec="seconds")
    if rec["count"] >= QUARANTINE_AFTER_FAILURES:
        until = now_cet() + dt.timedelta(hours=QUARANTINE_HOURS)
        rec["quarantine_until"] = until.isoformat(timespec="seconds")
        log.warning("%s: in quarantena fino a %s dopo %d mancate esecuzioni.",
                    pair, until.strftime("%d/%m %H:%M"), rec["count"])
        _event(st, "quarantena", pair=pair, fino=rec["quarantine_until"])


def _in_quarantine(st: dict, pair: str) -> bool:
    rec = (st.get("fill_failures") or {}).get(pair)
    if not rec or not rec.get("quarantine_until"):
        return False
    try:
        if now_cet() < dt.datetime.fromisoformat(rec["quarantine_until"]):
            return True
    except Exception:  # noqa: BLE001
        return False
    rec.pop("quarantine_until", None)   # scaduta: si riprova
    rec["count"] = 0
    return False


# =====================================================================
#  Protezione
# =====================================================================
def _stop_prices(cfg: dict, reference: float, distance_pct: float) -> tuple[float, float]:
    """Stop e limite. Il limite sta SOTTO lo stop: in una caduta veloce il
    prezzo scavalca lo stop e senza margine l'ordine non si riempirebbe."""
    stop = reference * (1 - distance_pct)
    limit = stop * (1 - float(cfg["strategy"]["stop_limit_offset_pct"]))
    return stop, limit


def _ensure_protection(cli, cfg: dict, st: dict, pair: str, pos: dict,
                       open_sells: dict, dry: bool) -> int:
    """Crea o alza lo stop di una posizione. Ritorna il numero di ordini inviati."""
    rec = st["positions"].setdefault(pair, {})
    # La quantita' si prende come STRINGA dal broker e non si fa passare da un
    # numero in virgola mobile: 25811523.058252426 diventerebbe ...428, cioe'
    # cinque miliardesimi in piu' di quanto possediamo, e l'ordine verrebbe
    # rifiutato per saldo insufficiente. Su monete da milionesimi di dollaro si
    # detengono decine di milioni di unita' e l'errore diventa reale.
    qty_str = pos.get("qty_available") or pos.get("qty") or "0"
    qty = float(qty_str)
    if qty <= 0:
        return 0

    entry = float(pos["avg_entry_price"])
    last = float(pos["current_price"])
    dist = float(rec.get("stop_distance_pct") or 0)
    if dist <= 0:
        # posizione mai vista prima (o stato perso): si ricava dalla volatilita'
        dist = float(cfg["strategy"]["min_stop_pct"])
        rec["stop_distance_pct"] = dist

    # Il massimo raggiunto governa il trailing: sale con il prezzo, mai scende.
    high = max(float(rec.get("high_water") or entry), last, entry)
    rec["high_water"] = high
    rec.setdefault("entry_price", entry)
    rec.setdefault("opened_at", now_cet().isoformat(timespec="seconds"))

    want_stop, want_limit = _stop_prices(cfg, high, dist)
    existing = open_sells.get(pair)

    # --- nessuna protezione attiva: si crea ---
    if not existing:
        if qty < cli.min_order_size(pair):
            log.warning("%s: quantita' %.9f sotto il minimo negoziabile, "
                        "impossibile proteggere.", pair, qty)
            return 0
        log.warning("%s: SCOPERTA -> creo stop-limit a %.6f (limite %.6f)",
                    pair, want_stop, want_limit)
        if dry:
            return 1
        o = cli.sell_stop_limit(pair, qty_str, want_stop, want_limit)
        rec["stop_order_id"] = o["id"]
        rec["stop_price"] = want_stop
        _event(st, "stop_creato", pair=pair, stop=round(want_stop, 8), qty=qty)
        return 1

    rec["stop_order_id"] = existing["id"]
    cur_stop = float(existing.get("stop_price") or 0)

    # --- protezione gia' presente: si alza solo se il guadagno lo merita ---
    min_move = float(cfg["strategy"]["trail_update_min_move_pct"])
    if cur_stop > 0 and want_stop <= cur_stop * (1 + min_move):
        rec["stop_price"] = cur_stop
        return 0

    log.info("%s: alzo il trailing stop %.6f -> %.6f (massimo %.6f, +%.1f%% da entrata)",
             pair, cur_stop, want_stop, high, (high / entry - 1) * 100)
    if dry:
        return 1
    try:
        # Attenzione: Alpaca non modifica l'ordine, ne crea uno NUOVO con un id
        # diverso e cancella il vecchio. Verificato sul campo. Va registrato l'id
        # nuovo, altrimenti lo stato punta a un ordine che non esiste piu'.
        new = cli.replace_order(existing["id"], stop=want_stop, limit=want_limit, pair=pair)
        rec["stop_order_id"] = new.get("id", existing["id"])
        rec["stop_price"] = want_stop
        _event(st, "trailing_alzato", pair=pair,
               da=round(cur_stop, 8), a=round(want_stop, 8))
        return 1
    except BrokerError as e:
        # Non si cancella l'ordine esistente: meglio uno stop piu' basso che
        # nessuno stop. Si ritenta al giro successivo.
        log.error("%s: sostituzione stop fallita (%s). Resta lo stop precedente.",
                  pair, str(e)[:200])
        _event(st, "trailing_fallito", pair=pair, errore=str(e)[:200])
        return 0


# =====================================================================
#  Uscite
# =====================================================================
def _exit_position(cli, cfg: dict, st: dict, pair: str, pos: dict,
                   open_sells: dict, motivo: str, dry: bool) -> int:
    """Uscita deliberata a mercato. Richiede di togliere prima lo stop, perche'
    le unita' sono prenotate dall'ordine di vendita aperto."""
    qty = float(pos["qty"])
    pl = float(pos.get("unrealized_pl") or 0)
    log.info("%s: USCITA (%s) — qty %.9f, P&L $%.2f", pair, motivo, qty, pl)
    if dry:
        return 1

    existing = open_sells.get(pair)
    if existing:
        try:
            cli.cancel_order(existing["id"])
            time.sleep(1)  # il broker deve liberare le unita' prenotate
        except BrokerError as e:
            log.error("%s: impossibile cancellare lo stop (%s): uscita annullata, "
                      "la posizione resta PROTETTA.", pair, str(e)[:200])
            return 0
    try:
        cli.close_crypto_position(pair)
    except BrokerError as e:
        log.error("%s: chiusura fallita (%s). Riprotezione al prossimo giro.",
                  pair, str(e)[:200])
        _event(st, "uscita_fallita", pair=pair, errore=str(e)[:200])
        return 1
    rec = st["positions"].pop(pair, None)
    if rec:
        _record_closed(st, pair, rec, float(pos.get("current_price") or 0), pl, motivo)
    _event(st, "uscita", pair=pair, motivo=motivo, pl_usd=round(pl, 2))
    return 1


# =====================================================================
#  Ingressi
# =====================================================================
def _enter(cli, cfg: dict, st: dict, sel: dict, usd: float, dry: bool) -> int:
    pair = sel["pair"]
    if usd < float(cfg["strategy"]["min_order_usd"]):
        log.info("%s: %.2f USD sotto il minimo d'ordine, salto.", pair, usd)
        return 0

    log.info("%s: INGRESSO $%.2f (rank %d, momentum %+.2f%%, stop -%.1f%%)",
             pair, usd, sel["rank"], sel["momentum_score"] * 100,
             sel["stop_distance_pct"] * 100)
    if dry:
        return 1

    o = cli.buy_notional(pair, usd)
    # Si attende il riempimento: senza prezzo reale di carico non si puo'
    # calcolare uno stop corretto (lezione RIVN sul bot azioni).
    filled = None
    for _ in range(FILL_POLL_TRIES):
        time.sleep(FILL_POLL_SECONDS)
        cur = cli._request("GET", cli._t(f"/v2/orders/{o['id']}"))
        if cur.get("status") == "filled":
            filled = cur
            break
        if cur.get("status") in ("canceled", "rejected", "expired"):
            log.error("%s: ordine %s.", pair, cur.get("status"))
            _event(st, "ingresso_fallito", pair=pair, stato=cur.get("status"))
            return 1

    if not filled:
        # Un ordine a mercato che non si riempie NON va lasciato pendente: tiene
        # bloccata la liquidita' e al giro dopo se ne aggiungerebbe un altro.
        # Si cancella e si mette la coppia in quarantena: se non e' eseguibile
        # oggi, e' inutile ritentarla ogni mezz'ora.
        log.warning("%s: non eseguito in %ds. Cancello l'ordine per non bloccare "
                    "la liquidita'.", pair, FILL_POLL_SECONDS * FILL_POLL_TRIES)
        try:
            cli.cancel_order(o["id"])
        except BrokerError as e:
            log.error("%s: cancellazione fallita (%s).", pair, str(e)[:150])
        _register_fill_failure(cfg, st, pair)
        _event(st, "ingresso_non_eseguito", pair=pair)
        return 1

    price = float(filled["filled_avg_price"])
    qty = float(filled["filled_qty"])
    dist = float(sel["stop_distance_pct"])
    st["positions"][pair] = {
        "entry_price": price,
        "qty": qty,
        "high_water": price,
        "stop_distance_pct": dist,
        "opened_at": now_cet().isoformat(timespec="seconds"),
        "entry_rank": sel["rank"],
    }
    _event(st, "ingresso", pair=pair, prezzo=price, qty=qty, usd=round(usd, 2))
    log.info("%s: eseguito a %.6f per %.9f unita'.", pair, price, qty)

    # Registra il PERCHE', per poterlo rileggere quando l'esito sara' noto.
    # Qui la decisione e' deterministica, quindi la motivazione e' il posto in
    # classifica e i numeri che ce l'hanno portata.
    try:
        from lib import decisions
        reg = decisions.DecisionLog(Path(cfg["state"]["dir"]) / "decisions_log.json")
        reg.record(pair, (
            f"Entrata al {sel['rank']}o posto della classifica di momentum "
            f"(punteggio {sel['momentum_score']*100:+.2f}%), stop a "
            f"-{dist*100:.1f}% tarato sulla volatilita' giornaliera. "
            f"Peso assegnato {sel.get('target_weight', 0)*100:.1f}% del capitale."
        ), rank=sel["rank"], momentum=sel["momentum_score"],
            stop_distance_pct=dist, usd=round(usd, 2))
    except Exception as e:  # noqa: BLE001 — il registro non deve mai fermare un ordine
        log.warning("%s: registro decisioni non aggiornato (%s).", pair, e)

    # Protezione IMMEDIATA, nello stesso giro. Aspettare il tick successivo
    # lascerebbe la posizione scoperta per mezz'ora: inaccettabile, ed e'
    # esattamente il tipo di finestra che sul bot azioni e' gia' costata cara.
    # NB: la quantita' protetta e' quella DISPONIBILE, non quella comprata:
    # Alpaca trattiene la commissione (~0,25%) in moneta.
    stop, limit = _stop_prices(cfg, price, dist)
    for attempt in range(3):
        time.sleep(1)
        try:
            pos = {to_pair(p["symbol"]): p for p in cli.crypto_positions()}.get(pair)
            if not pos:
                continue
            avail_str = pos.get("qty_available") or "0"
            avail = float(avail_str)
            if avail <= 0:
                continue
            if avail < cli.min_order_size(pair):
                log.warning("%s: %.9f unita' sotto il minimo negoziabile: "
                            "impossibile proteggere.", pair, avail)
                break
            o2 = cli.sell_stop_limit(pair, avail_str, stop, limit)
            st["positions"][pair]["stop_order_id"] = o2["id"]
            st["positions"][pair]["stop_price"] = stop
            log.info("%s: protetto subito con stop-limit a %.6f (-%.1f%%).",
                     pair, stop, dist * 100)
            _event(st, "stop_creato", pair=pair, stop=round(stop, 8), qty=avail)
            break
        except BrokerError as e:
            log.warning("%s: protezione al tentativo %d fallita (%s).",
                        pair, attempt + 1, str(e)[:150])
    else:
        log.error("%s: POSIZIONE APERTA SENZA STOP. Il prossimo giro la protegge.", pair)
        _event(st, "aperta_senza_stop", pair=pair)
    return 1


# =====================================================================
#  Giro completo
# =====================================================================
def run(dry_run: bool = False) -> dict:
    cfg = load_config()
    cli = CryptoClient(cfg)
    acct = cli.assert_right_account()
    st = _load_state(cfg)

    equity = float(acct["equity"])
    cash = float(acct["cash"])
    peak = max(float(st.get("peak_equity") or 0), equity)
    st["peak_equity"] = peak
    dd = (peak - equity) / peak if peak > 0 else 0.0

    log.info("Conto %s | equity $%.2f | cash $%.2f | massimo $%.2f | drawdown %.1f%%",
             acct["account_number"], equity, cash, peak, dd * 100)

    max_dd = float(cfg["guardrails"]["max_drawdown_from_peak_pct"])
    entries_blocked = dd >= max_dd
    if entries_blocked:
        log.error("FRENO DI EMERGENZA: drawdown %.1f%% >= %.1f%%. "
                  "Nessun nuovo ingresso; le posizioni restano protette.",
                  dd * 100, max_dd * 100)
        _event(st, "freno_emergenza", drawdown_pct=round(dd, 4))

    positions = {to_pair(p["symbol"]): p for p in cli.crypto_positions()}
    all_open = cli.list_orders(status="open")
    open_sells = {to_pair(o["symbol"]): o for o in all_open if o.get("side") == "sell"}
    # Un acquisto gia' in coda significa che l'ingresso e' in corso: senza questo
    # controllo si accumulerebbe un ordine per ogni giro finche' non si riempie.
    pending_buys = {to_pair(o["symbol"]): o for o in all_open if o.get("side") == "buy"}
    log.info("Posizioni aperte: %d | protezioni attive: %d | acquisti in coda: %d",
             len(positions), len(open_sells), len(pending_buys))

    # Prima di ogni altra cosa: registrare cio' che si e' chiuso da solo mentre
    # il bot non guardava. Altrimenti quelle operazioni non entrano mai nel
    # conteggio dei risultati.
    if not dry_run:
        _reconcile_closed(cli, st, positions)

    # classifica del giorno
    try:
        ranking = read_json(cfg["state"]["files"]["ranking"])
    except Exception:  # noqa: BLE001
        log.error("Classifica assente: esegui prima routine_c1_scan. "
                  "Questo giro protegge soltanto.")
        ranking = {"ranking": [], "selection": []}

    rank_by_pair = {r["pair"]: r["rank"] for r in ranking.get("ranking", [])}
    selection = {s["pair"]: s for s in ranking.get("selection", [])}
    budget = int(cfg["guardrails"]["max_orders_per_tick"])
    sent = 0

    # --- 1) protezione, prima di tutto ---
    for pair, pos in positions.items():
        if sent >= budget:
            break
        sent += _ensure_protection(cli, cfg, st, pair, pos, open_sells, dry_run)

    # --- 2) uscite per debolezza relativa ---
    threshold = int(cfg["strategy"]["rank_exit_threshold"])
    for pair, pos in list(positions.items()):
        if sent >= budget:
            break
        r = rank_by_pair.get(pair)
        if not ranking.get("ranking"):
            continue  # senza classifica non si giudica
        if r is None:
            sent += _exit_position(cli, cfg, st, pair, pos, open_sells,
                                   "uscita dall'universo", dry_run)
        elif r > threshold:
            sent += _exit_position(cli, cfg, st, pair, pos, open_sells,
                                   f"scesa al {r}o posto (soglia {threshold})", dry_run)

    # --- 3) ingressi ---
    if not entries_blocked:
        for pair, sel in selection.items():
            if sent >= budget:
                log.info("Raggiunto il tetto di ordini per giro.")
                break
            if pair in positions:
                continue
            if pair in pending_buys:
                log.info("%s: acquisto gia' in coda dal giro precedente, non ne "
                         "aggiungo un altro.", pair)
                continue
            if _in_quarantine(st, pair):
                log.info("%s: in quarantena (non eseguibile), salto.", pair)
                continue
            usd = min(float(sel["target_usd"]), cash * 0.98)
            if usd < float(cfg["strategy"]["min_order_usd"]):
                log.info("%s: liquidita' insufficiente ($%.2f).", pair, cash)
                continue
            n = _enter(cli, cfg, st, sel, usd, dry_run)
            sent += n
            if n and not dry_run:
                cash = float(cli.account()["cash"])

    if not dry_run:
        _save_state(cfg, st)
    log.info("Giro concluso: %d operazioni%s.", sent, " (dry-run)" if dry_run else "")
    return {"ok": True, "orders": sent, "drawdown_pct": dd}


def main() -> int:
    ap = argparse.ArgumentParser(description="Cripto — esecuzione e protezioni")
    ap.add_argument("--dry-run", action="store_true",
                    help="simula: nessun ordine inviato, nessuno stato scritto")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()

    res = run(dry_run=a.dry_run)
    if res.get("ok") and not a.dry_run and res.get("orders") and not a.no_push:
        from lib import gitsync
        gitsync.sync(f"cripto: operativita' {dt.date.today().isoformat()}")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
