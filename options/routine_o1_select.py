"""
routine_o1_select.py — OPZIONI / Sceglie titoli e contratti.

Ha un universo PROPRIO di 30 titoli, scelti misurando la liquidita' delle loro
opzioni e non delle azioni: sull'universo azionario un contratto vicino al denaro
costava spesso piu' del capitale intero, oppure aveva spread del 132%.

Il confronto con la divisione azioni resta possibile sui titoli in comune, ma
non e' piu' un A/B puro: e' una scelta deliberata, presa dopo aver misurato che
il vincolo dei 100 contratti per opzione rendeva l'altro disegno inapplicabile.

Due modalita':
  INTRADAY  solo il candidato numero uno, e solo se il suo scarto di apertura
            supera la soglia. Scadenza ravvicinata, chiusura in giornata.
            Consuma un credito PDT.
  SWING     gli altri candidati. Scadenza a 2-5 settimane, tenuti piu' giorni.
            Non consuma crediti.

Molti candidati verranno scartati perche' NON ACQUISTABILI: un contratto vale
100 azioni, quindi su un titolo da 500 dollari il premio vicino al denaro supera
il nostro capitale. Non e' un errore, e' il vincolo dello strumento — e va
registrato, perche' altrimenti sembrerebbe che il bot non trovi occasioni.

Non invia ordini: scrive solo state/options/selection.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

from lib.alpaca_rest import atomic_write_json, read_json, now_cet
from lib import pdt
from options.broker import OptionsClient, load_config, MOLTIPLICATORE

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
log = logging.getLogger("options.o1")

REPO = Path(__file__).resolve().parent.parent


def _segnale(cli, cfg: dict) -> list[dict]:
    """Calcola il segnale sull'universo PROPRIO di questa divisione.

    Stessa logica dell'Analista azionario — scarto rispetto alla chiusura
    precedente e volume — ma su titoli scelti perche' le loro OPZIONI sono
    negoziabili con il nostro capitale. Usa il feed consolidato (SIP): in
    pre-apertura IEX e' praticamente vuoto, e l'abbiamo gia' pagata cara.
    """
    tk = cfg["universe"]["tickers"]
    oggi = dt.date.today().isoformat()
    inizio = (dt.date.today() - dt.timedelta(days=12)).isoformat()
    barre = cli.bars(tk, "1Day", inizio, feed="sip", limit=1000)
    prev = {}
    for s, rows in barre.items():
        fatte = [b for b in rows if b["t"][:10] < oggi]
        if fatte:
            prev[s] = fatte[-1]["c"]
    snap = cli.snapshots(tk, feed="delayed_sip")

    righe = []
    for s in tk:
        last = (snap.get(s) or {}).get("latestTrade", {}).get("p")
        pc = prev.get(s)
        if not last or not pc:
            continue
        gap = (last - pc) / pc * 100
        if abs(gap) > 50 or abs(gap) < 0.02:      # dato sporco, oppure fermo
            continue
        if gap < 0:                                # solo call: niente ribassisti
            continue
        vol = ((snap.get(s) or {}).get("dailyBar") or {}).get("v", 0)
        righe.append({"ticker": s, "gap_pct": round(gap, 2),
                      "last_price": round(last, 2), "volume": int(vol or 0)})
    righe.sort(key=lambda r: (r["gap_pct"], r["volume"]), reverse=True)
    return righe[: int(cfg["universe"]["top_candidates"])]


def scegli_contratto(cli, cfg: dict, ticker: str, spot: float,
                     modo: str, budget: float) -> dict | None:
    """Il contratto piu' vicino al denaro che rispetta TUTTI i vincoli.

    Si preferisce la vicinanza al denaro, non il prezzo basso: un contratto
    economico perche' lontano dal denaro pagherebbe solo con un movimento molto
    piu' grande di quello che il segnale prevede.
    """
    c = cfg["contract"]
    m = cfg["modes"][modo]
    try:
        catena = cli.chain(ticker, spot, c["type"],
                           m["expiry_min_days"], m["expiry_max_days"],
                           finestra_strike=0.06)
    except Exception as e:  # noqa: BLE001
        log.warning("%s: catena non leggibile (%s).", ticker, e)
        return None
    if not catena:
        return None
    quot = cli.quotes([x["symbol"] for x in catena[:80]])

    migliori = []
    for x in catena:
        strike = float(x["strike_price"])
        otm = (strike / spot - 1) * 100
        if otm < -1 or otm > float(c["max_otm_pct"]):
            continue
        s = quot.get(x["symbol"])
        ask, spread = cli.ask(s), cli.spread_pct(s)
        if ask is None or spread is None:
            continue
        premio = ask * MOLTIPLICATORE
        if premio > budget or premio > float(c["max_premium_usd"]):
            continue
        if premio < float(c["min_premium_usd"]) or spread > float(c["max_spread_pct"]):
            continue
        migliori.append((abs(otm), {
            "symbol": x["symbol"], "strike": strike, "expiration": x["expiration_date"],
            "otm_pct": round(otm, 2), "ask": ask, "premio_usd": round(premio, 2),
            "spread_pct": round(spread, 2),
        }))
    if not migliori:
        return None
    migliori.sort(key=lambda z: z[0])
    return migliori[0][1]


def run(dry_run: bool = False) -> dict:
    cfg = load_config()
    cli = OptionsClient(cfg)
    acct = cli.assert_right_account()
    equity = float(acct["equity"])
    log.info("Conto %s | equity $%.2f", acct["account_number"], equity)

    if equity < float(cfg["capital"]["min_usd"]):
        log.error("Capitale sotto la soglia minima: nessun contratto acquistabile.")
        return {"ok": False, "reason": "capitale insufficiente"}

    cand = _segnale(cli, cfg)
    if not cand:
        log.info("Nessun titolo in rialzo nell'universo: giornata in stand-by.")
        payload = {"generato_il": now_cet().isoformat(timespec="seconds"),
                   "session_date": dt.date.today().isoformat(),
                   "selezione": [], "scartati": [], "nota": "nessun candidato in rialzo"}
        if not dry_run:
            atomic_write_json(REPO / cfg["state"]["files"]["selection"], payload)
        return {"ok": True, "payload": payload}

    log.info("Candidati dall'universo opzioni (%d titoli): %s", len(cfg["universe"]["tickers"]),
             ", ".join("%s %+.2f%%" % (c["ticker"], c["gap_pct"]) for c in cand))

    # Crediti intraday disponibili (ne teniamo uno di riserva per le emergenze)
    g = cfg["guardrails"]
    usati, _ = pdt.count_recent_day_trades(cli)
    liberi = max(0, int(g["day_trades_usable"]) - usati)
    log.info("Crediti intraday: %d usati, %d utilizzabili (1 di riserva su %d totali).",
             usati, liberi, g["day_trades_total"])

    spot = cli.snapshots([c["ticker"] for c in cand], feed="delayed_sip")
    scelti, scartati = [], []

    for i, c in enumerate(cand):
        t = c["ticker"]
        s = (spot.get(t) or {}).get("latestTrade", {}).get("p")
        if not s:
            scartati.append({"ticker": t, "motivo": "prezzo non disponibile"})
            continue
        gap = float(c.get("gap_pct") or 0)

        mi = cfg["modes"]["intraday"]
        intraday = (mi.get("enabled") and i < int(mi["only_top_rank"])
                    and gap >= float(mi["min_gap_pct"]) and liberi > 0)
        modo = "intraday" if intraday else "swing"
        if modo == "swing" and not cfg["modes"]["swing"].get("enabled"):
            continue

        budget = equity * float(cfg["modes"][modo]["max_premium_pct"])
        con = scegli_contratto(cli, cfg, t, s, modo, budget)
        if not con:
            costo_min = round(s * MOLTIPLICATORE * 0.02, 0)
            scartati.append({"ticker": t, "spot": round(s, 2), "modo": modo,
                             "motivo": "nessun contratto entro budget/spread "
                                       f"(un contratto muove ~{s*MOLTIPLICATORE:,.0f}$)"})
            log.info("  %-5s spot %8.2f  scartato: nessun contratto nei limiti "
                     "(budget %.0f$)", t, s, budget)
            continue

        con.update({"ticker": t, "modo": modo, "gap_pct": gap, "spot": round(s, 2),
                    "rank": i + 1, "volume": c.get("volume"),
                    "stop_underlying": round(s * (1 - float(cfg["exits"]["underlying_stop_pct"])), 2),
                    "target_underlying": round(s * (1 + float(cfg["exits"]["underlying_target_pct"])), 2)})
        scelti.append(con)
        if modo == "intraday":
            liberi -= 1
        log.info("  %-5s %-9s %s strike %.1f (%.1f%% otm) scad %s | premio %.0f$ "
                 "spread %.1f%%", t, modo, cfg["contract"]["type"], con["strike"],
                 con["otm_pct"], con["expiration"], con["premio_usd"], con["spread_pct"])

    # Si tengono i migliori finche' la SOMMA dei premi resta nel tetto.
    sw = cfg["modes"]["swing"]
    tetto = equity * float(sw["max_total_premium_pct"])
    maxpos = int(sw["max_positions"])
    scelti.sort(key=lambda x: (x["modo"] != "intraday", x["rank"]))
    tenuti, speso = [], 0.0
    for x in scelti:
        if len(tenuti) >= maxpos or speso + x["premio_usd"] > tetto:
            continue
        tenuti.append(x); speso += x["premio_usd"]
    if len(tenuti) < len(scelti):
        log.info("Tenuti %d contratti su %d: %.0f$ impegnati sul tetto di %.0f$.",
                 len(tenuti), len(scelti), speso, tetto)
    scelti = tenuti

    payload = {
        "generato_il": now_cet().isoformat(timespec="seconds"),
        "session_date": dt.date.today().isoformat(),
        "conto": acct["account_number"],
        "equity_usd": round(equity, 2),
        "universo": len(cfg["universe"]["tickers"]),
        "crediti_intraday_liberi": liberi,
        "selezione": scelti,
        "scartati": scartati,
    }
    log.info("Selezionati %d contratti | scartati %d (per lo piu' non acquistabili).",
             len(scelti), len(scartati))

    if dry_run:
        log.info("dry-run: nessun file scritto.")
        return {"ok": True, "payload": payload, "written": False}
    atomic_write_json(REPO / cfg["state"]["files"]["selection"], payload)
    log.info("Scritto %s", cfg["state"]["files"]["selection"])
    return {"ok": True, "payload": payload, "written": True}


def main() -> int:
    ap = argparse.ArgumentParser(description="Opzioni — selezione dei contratti")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    res = run(dry_run=a.dry_run)
    if res.get("written") and not a.no_push:
        from lib import gitsync
        gitsync.sync(f"opzioni: selezione {dt.date.today().isoformat()}")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
