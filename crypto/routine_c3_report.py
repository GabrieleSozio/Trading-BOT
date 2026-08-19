"""
routine_c3_report.py — CRIPTO / Rendiconto settimanale.

Gira la domenica sera. Non invia ordini: misura come sta andando la divisione e
chiede a Claude un'analisi scritta.

Perche' l'AI qui NON modifica la configurazione da sola (a differenza del
supervisore azionario): la divisione cripto e' appena nata e non ha uno storico
di operazioni chiuse. Ritoccare i parametri su tre o quattro trade significa
inseguire il rumore. Le proposte vengono scritte nel rendiconto e restano da
approvare finche' non c'e' abbastanza materiale per giudicare.

Il conto delle operazioni segue le POSIZIONI, non i singoli fill: un acquisto e
la successiva vendita sono UNA operazione con un risultato, non due. Contarli
separatamente falsa qualunque statistica (errore gia' commesso e corretto sul
bot azioni).
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

from lib import ai_client
from lib.alpaca_rest import atomic_write_json, read_json, now_cet
from crypto.broker import CryptoClient, load_config, to_pair

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s"
)
log = logging.getLogger("crypto.c3")


# =====================================================================
#  Operazioni chiuse
# =====================================================================
def closed_round_trips(fills: list[dict]) -> list[dict]:
    """Ricostruisce le operazioni complete seguendo la posizione per coppia.

    Si tiene il costo medio di carico; il risultato si realizza solo quando la
    posizione torna a zero (o si riduce), non a ogni fill.
    """
    by_pair: dict[str, list[dict]] = {}
    for f in sorted(fills, key=lambda x: x.get("transaction_time", "")):
        by_pair.setdefault(to_pair(f["symbol"]), []).append(f)

    trips = []
    for pair, rows in by_pair.items():
        qty = 0.0
        cost = 0.0          # costo totale della posizione aperta
        opened_at = None
        for f in rows:
            side = f.get("side", "")
            q = abs(float(f.get("qty") or 0))
            p = float(f.get("price") or 0)
            if q <= 0:
                continue
            if side.startswith("buy"):
                if qty == 0:
                    opened_at = f.get("transaction_time")
                qty += q
                cost += q * p
            else:
                if qty <= 0:
                    continue  # vendita senza carico noto: si ignora
                avg = cost / qty
                closed = min(q, qty)
                pl = (p - avg) * closed
                trips.append({
                    "pair": pair,
                    "qty": round(closed, 9),
                    "entry": round(avg, 8),
                    "exit": round(p, 8),
                    "pl_usd": round(pl, 2),
                    "pl_pct": round((p / avg - 1) * 100, 2) if avg else 0.0,
                    "opened_at": opened_at,
                    "closed_at": f.get("transaction_time"),
                })
                qty -= closed
                cost -= avg * closed
                # La commissione (~0,25%) e' trattenuta IN MONETA: si vendono
                # meno unita' di quante se ne comprano. Senza questo, il residuo
                # resterebbe per sempre "aperto" e il costo non comparirebbe mai,
                # facendo sembrare le operazioni migliori di quanto siano state.
                if 0 < qty <= closed * 0.05:
                    trips[-1]["commissione_usd"] = round(cost, 4)
                    trips[-1]["pl_usd"] = round(trips[-1]["pl_usd"] - cost, 2)
                    trips[-1]["pl_pct"] = round(
                        trips[-1]["pl_usd"] / (avg * closed) * 100, 2) if avg and closed else 0.0
                    qty, cost = 0.0, 0.0
                if qty <= 1e-12:
                    qty, cost, opened_at = 0.0, 0.0, None
    return sorted(trips, key=lambda t: t["closed_at"] or "")


def stats(trips: list[dict]) -> dict:
    if not trips:
        return {"n": 0}
    wins = [t for t in trips if t["pl_usd"] > 0]
    losses = [t for t in trips if t["pl_usd"] <= 0]
    tot = sum(t["pl_usd"] for t in trips)
    return {
        "n": len(trips),
        "vincenti": len(wins),
        "perdenti": len(losses),
        "win_rate_pct": round(len(wins) / len(trips) * 100, 1),
        "pl_totale_usd": round(tot, 2),
        "vincita_media_usd": round(sum(t["pl_usd"] for t in wins) / len(wins), 2) if wins else 0.0,
        "perdita_media_usd": round(sum(t["pl_usd"] for t in losses) / len(losses), 2) if losses else 0.0,
        "migliore": max(trips, key=lambda t: t["pl_usd"]) if trips else None,
        "peggiore": min(trips, key=lambda t: t["pl_usd"]) if trips else None,
    }


# =====================================================================
#  Analisi AI
# =====================================================================
SCHEMA = {
    "type": "object",
    # additionalProperties DEVE essere esplicito: l'API rifiuta lo schema senza,
    # e il rendiconto degraderebbe a soli numeri senza che nessuno se ne accorga.
    "additionalProperties": False,
    "properties": {
        "giudizio": {"type": "string"},
        "cosa_ha_funzionato": {"type": "array", "items": {"type": "string"}},
        "cosa_non_ha_funzionato": {"type": "array", "items": {"type": "string"}},
        "proposte": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "parametro": {"type": "string"},
                    "da": {"type": "string"},
                    "a": {"type": "string"},
                    "motivo": {"type": "string"},
                },
                "required": ["parametro", "da", "a", "motivo"],
            },
        },
        "dati_sufficienti": {"type": "boolean"},
    },
    "required": ["giudizio", "cosa_ha_funzionato", "cosa_non_ha_funzionato",
                 "proposte", "dati_sufficienti"],
}

SYSTEM = """Sei l'analista della divisione cripto di una societa' di trading simulata.
Operi su conto paper: nessun denaro reale.

La strategia e': momentum trasversale sulle 3 coppie piu' forti in classifica,
sempre investito, nessun take profit, uscita per trailing stop (2,5 x volatilita'
giornaliera) o per caduta fuori dalla top 5.

Il tuo compito e' valutare l'andamento con onesta' statistica. Sii diretto sui
problemi. Ma NON confondere il rumore con il segnale: con poche operazioni chiuse
non si puo' concludere quasi nulla, e dirlo e' la risposta giusta. Se i dati non
bastano, metti dati_sufficienti a false e non proporre modifiche.
Rispondi in italiano."""


def _resolve_decisions(cfg: dict, cli, dry_run: bool) -> dict:
    """Chiude le decisioni cripto in sospeso e ne ricava una lezione.

    L'esito arriva dalle operazioni che routine_c2 registra alla chiusura, dove
    il rischio d'ingresso e' ancora noto. L'alpha si misura contro Bitcoin, non
    contro lo zero.
    """
    from lib import decisions, benchmark as bmk
    reg = decisions.DecisionLog(Path(cfg["state"]["dir"]) / "decisions_log.json")
    sospese = reg.pending()
    if not sospese:
        return {"in_sospeso": 0, "risolte": 0}

    try:
        stato = read_json(cfg["state"]["files"]["positions"])
        chiuse = stato.get("closed_trades") or []
    except Exception:  # noqa: BLE001
        chiuse = []
    if not chiuse:
        return {"in_sospeso": len(sospese), "risolte": 0}

    start = min(e["date"] for e in sospese)
    btc = bmk.crypto_series(cli, start)
    chiuse = bmk.add_alpha(chiuse, btc, key_in="opened_at",
                           key_out="closed_at", key_pct="pl_pct")

    per_coppia: dict[str, list] = {}
    for t in chiuse:
        per_coppia.setdefault(t["pair"], []).append(t)

    model = (cfg.get("ai") or {}).get("model")
    risolte = 0
    for e in sospese:
        cand = [t for t in per_coppia.get(e["ticker"], [])
                if (t.get("opened_at") or "")[:10] >= e["date"]]
        if not cand:
            continue           # posizione ancora aperta
        t = sorted(cand, key=lambda x: x.get("opened_at") or "")[0]
        outcome = {k: t.get(k) for k in
                   ("pl_pct", "pl_usd", "r_multiple", "alpha_pct",
                    "benchmark_pct")}
        outcome["closed_by"] = t.get("motivo")
        lezione = None if dry_run else decisions.reflect(e["decision"], outcome, model)
        if lezione:
            log.info("Lezione su %s (%s%% | alpha %s): %s", e["ticker"],
                     outcome.get("pl_pct"), outcome.get("alpha_pct"), lezione[:150])
        if not dry_run and reg.resolve(e["ticker"], e["date"], outcome, lezione or ""):
            risolte += 1
    return {"in_sospeso": len(sospese), "risolte": risolte, **reg.stats()}


def ai_analysis(payload: dict, model: str | None) -> dict | None:
    if not ai_client.ai_enabled():
        log.warning("ANTHROPIC_API_KEY assente: rendiconto senza analisi AI.")
        return None
    import json
    user = (
        "Rendiconto della divisione cripto.\n\n"
        f"Capitale iniziale: ${payload['capitale']['iniziale_usd']}\n"
        f"Equity attuale:    ${payload['capitale']['equity_usd']}\n"
        f"Rendimento:        {payload['capitale']['rendimento_pct']}%\n"
        f"Giorni di attivita': {payload['capitale']['giorni']}\n\n"
        f"Operazioni chiuse: {json.dumps(payload['statistiche'], ensure_ascii=False)}\n\n"
        f"Dettaglio: {json.dumps(payload['operazioni'][-20:], ensure_ascii=False)}\n\n"
        f"Posizioni aperte: {json.dumps(payload['posizioni_aperte'], ensure_ascii=False)}\n\n"
        f"Classifica corrente: {json.dumps(payload.get('classifica_top5', []), ensure_ascii=False)}\n\n"
        "Valuta l'andamento e, SOLO se i dati bastano, proponi modifiche."
    )
    try:
        return ai_client.ask_json(SYSTEM, user, SCHEMA, model=model, max_tokens=2500)
    except ai_client.AIUnavailable as e:
        log.warning("Analisi AI non disponibile (%s): rendiconto solo numerico.", e)
        return None


# =====================================================================
def run(dry_run: bool = False) -> dict:
    cfg = load_config()
    cli = CryptoClient(cfg)
    acct = cli.assert_right_account()

    equity = float(acct["equity"])
    initial = float(cfg["capital"].get("initial_usd") or equity)
    start = cfg["capital"].get("strategy_start") or ""
    try:
        d0 = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        giorni = max(1, (dt.datetime.now(dt.timezone.utc) - d0).days)
    except Exception:  # noqa: BLE001
        giorni = 1

    fills = cli.activities("FILL", after=start[:10] if start else None)
    fills = [f for f in fills if "/" in to_pair(f.get("symbol", ""))]
    trips = closed_round_trips(fills)
    st = stats(trips)

    positions = []
    for p in cli.crypto_positions():
        positions.append({
            "pair": to_pair(p["symbol"]),
            "qty": float(p["qty"]),
            "carico": float(p["avg_entry_price"]),
            "prezzo": float(p["current_price"]),
            "valore_usd": round(float(p["market_value"]), 2),
            "pl_usd": round(float(p["unrealized_pl"]), 2),
            "pl_pct": round(float(p["unrealized_plpc"]) * 100, 2),
        })

    try:
        rk = read_json(cfg["state"]["files"]["ranking"])
        top5 = [{"pair": r["pair"], "rank": r["rank"],
                 "momentum_pct": round(r["momentum_score"] * 100, 2)}
                for r in rk.get("ranking", [])[:5]]
    except Exception:  # noqa: BLE001
        top5 = []

    # Riconciliazione. Alpaca non espone le commissioni: non ci sono attivita'
    # di tipo FEE e il record del fill non le riporta. Quella sull'acquisto e'
    # ricostruibile (viene trattenuta in moneta), quella sulla vendita no: si
    # vede solo come differenza tra il risultato delle operazioni e il saldo.
    # Il saldo e' la verita'; si dichiara lo scarto invece di nasconderlo.
    unrealized = sum(p["pl_usd"] for p in positions)
    realizzato_reale = (equity - initial) - unrealized
    realizzato_operazioni = float(st.get("pl_totale_usd") or 0)
    riconciliazione = {
        "realizzato_dalle_operazioni_usd": round(realizzato_operazioni, 2),
        "realizzato_dal_saldo_usd": round(realizzato_reale, 2),
        "commissioni_vendita_stimate_usd": round(realizzato_operazioni - realizzato_reale, 2),
        "nota": ("Alpaca non dichiara le commissioni via API. Quella sull'acquisto "
                 "e' dedotta dalle unita' trattenute; quella sulla vendita e' la "
                 "differenza residua. Il saldo del conto e' il dato attendibile."),
    }

    # Risultati in FATTORI DI RISCHIO. Su questa divisione e' la misura che
    # conta: gli stop vanno dal 4% al 30% a seconda della volatilita' della
    # moneta, quindi confrontare fra loro le percentuali di guadagno non dice
    # nulla. Il rischio viene registrato alla chiusura da routine_c2, perche'
    # dopo non e' piu' ricostruibile dal broker.
    per_rischio = {}
    try:
        stato = read_json(cfg["state"]["files"]["positions"])
        chiuse_r = [t for t in (stato.get("closed_trades") or [])
                    if t.get("r_multiple") is not None]
        if chiuse_r:
            rs = [t["r_multiple"] for t in chiuse_r]
            v = [r for r in rs if r > 0]
            p = [r for r in rs if r <= 0]
            per_rischio = {
                "n": len(rs),
                "R_medio": round(sum(rs) / len(rs), 2),
                "R_totale": round(sum(rs), 2),
                "R_migliore": round(max(rs), 2),
                "R_peggiore": round(min(rs), 2),
                "R_vincita_media": round(sum(v) / len(v), 2) if v else 0.0,
                "R_perdita_media": round(sum(p) / len(p), 2) if p else 0.0,
                "dettaglio": [f"{t['pair']} {t['pl_pct']:+.2f}% ({t['r_multiple']:+.2f}R, "
                              f"stop {t['stop_distance_pct']*100:.0f}%)" for t in chiuse_r],
            }
    except Exception as e:  # noqa: BLE001 — misura accessoria
        log.warning("Fattori di rischio non disponibili: %s", e)

    # --- Alpha rispetto a Bitcoin ---
    # Sulle cripto il metro non e' lo zero, e' BTC: una moneta che sale meno di
    # Bitcoin sta di fatto perdendo, perche' gli stessi soldi fermi su BTC
    # avrebbero reso di piu' con meno movimento e meno costi.
    confronto = {}
    try:
        from lib import benchmark as bmk
        confronto = bmk.period_alpha(cli, "crypto", (start or "")[:10],
                                     (equity / initial - 1) * 100 if initial else 0.0)
    except Exception as e:  # noqa: BLE001 — misura accessoria
        log.warning("Confronto con Bitcoin non disponibile: %s", e)

    # --- Decisioni passate: esito noto e lezione ---
    registro = {}
    try:
        registro = _resolve_decisions(cfg, cli, dry_run)
    except Exception as e:  # noqa: BLE001
        log.warning("Registro decisioni non elaborato: %s", e)

    payload = {
        "generato_il": now_cet().isoformat(timespec="seconds"),
        "divisione": "cripto",
        "conto": acct["account_number"],
        "riconciliazione": riconciliazione,
        "per_fattore_di_rischio": per_rischio,
        "confronto_con_bitcoin": confronto,
        "registro_decisioni": registro,
        "capitale": {
            "iniziale_usd": round(initial, 2),
            "equity_usd": round(equity, 2),
            "rendimento_pct": round((equity / initial - 1) * 100, 2) if initial else 0.0,
            "giorni": giorni,
        },
        "statistiche": st,
        "operazioni": trips,
        "posizioni_aperte": positions,
        "classifica_top5": top5,
    }

    log.info("=" * 62)
    log.info("DIVISIONE CRIPTO — rendiconto")
    log.info("  capitale  $%.2f -> $%.2f  (%+.2f%% in %d giorni)",
             initial, equity, payload["capitale"]["rendimento_pct"], giorni)
    if st["n"]:
        log.info("  operazioni chiuse: %d | vincenti %d (%.0f%%) | P&L lordo $%.2f",
                 st["n"], st["vincenti"], st["win_rate_pct"], st["pl_totale_usd"])
        log.info("  realizzato dal saldo $%.2f | commissioni di vendita stimate $%.2f",
                 riconciliazione["realizzato_dal_saldo_usd"],
                 riconciliazione["commissioni_vendita_stimate_usd"])
    else:
        log.info("  nessuna operazione ancora chiusa.")
    for p in positions:
        log.info("  aperta %-10s %+7.2f%%  ($%+.2f)", p["pair"], p["pl_pct"], p["pl_usd"])
    if per_rischio:
        log.info("  --- per fattore di rischio (%d operazioni) ---", per_rischio["n"])
        for d in per_rischio["dettaglio"][-8:]:
            log.info("    %s", d)
        log.info("  R medio %+.2f | vincita media %+.2fR | perdita media %+.2fR",
                 per_rischio["R_medio"], per_rischio["R_vincita_media"],
                 per_rischio["R_perdita_media"])
        if per_rischio["R_medio"] > 0:
            log.info("  R medio positivo: la strategia guadagna piu' di quanto rischia.")
        else:
            log.info("  R medio negativo: finora la strategia rischia piu' di quanto rende.")
    else:
        log.info("  fattori di rischio: nessuna operazione ancora chiusa dopo la modifica.")
    log.info("=" * 62)

    an = ai_analysis(payload, (cfg.get("ai") or {}).get("model"))
    if an:
        payload["analisi_ai"] = an
        log.info("ANALISI: %s", an["giudizio"])
        for x in an.get("cosa_non_ha_funzionato", []):
            log.info("  problema: %s", x)
        if an.get("dati_sufficienti"):
            for p in an.get("proposte", []):
                log.info("  proposta: %s  %s -> %s  (%s)",
                         p["parametro"], p["da"], p["a"], p["motivo"])
        else:
            log.info("  l'analisi giudica i dati ancora insufficienti: "
                     "nessuna modifica proposta.")

    if dry_run:
        log.info("dry-run: nessun file scritto.")
        return {"ok": True, "written": False}

    out = f"{cfg['state']['dir']}/report_{dt.date.today().isoformat()}.json"
    atomic_write_json(out, payload)
    atomic_write_json(f"{cfg['state']['dir']}/report_latest.json", payload)
    log.info("Scritto %s", out)
    return {"ok": True, "written": True}


def main() -> int:
    ap = argparse.ArgumentParser(description="Cripto — rendiconto settimanale")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    res = run(dry_run=a.dry_run)
    if res.get("written") and not a.no_push:
        from lib import gitsync
        gitsync.sync(f"cripto: rendiconto {dt.date.today().isoformat()}")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
