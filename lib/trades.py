"""
trades.py — operazioni chiuse misurate in FATTORI DI RISCHIO.

Perche' serve. Dire "+6%" non significa niente finche' non si sa quanto si era
messo a rischio per ottenerlo. Un +6% con lo stop al 3% vale il doppio di un +6%
con lo stop al 6%: nel primo caso si sono guadagnate 2 volte la somma rischiata,
nel secondo 1. Il fattore di rischio (P&L diviso la perdita che si sarebbe subita
allo stop) rende confrontabili operazioni con protezioni diverse, ed e' l'unico
numero che risponde davvero alla domanda "questa strategia ha un vantaggio?".

Conta soprattutto quando gli stop NON sono tutti uguali: la divisione cripto
taratura lo stop sulla volatilita' di ogni moneta (4% su BTC, 20% su PEPE),
quindi confrontare le sue percentuali fra loro e' privo di senso.

Regola pratica: una strategia e' sostenibile se la media dei fattori di rischio
e' positiva, anche con poche operazioni vincenti. Chiudere in media a +0,5R
significa che su 10 operazioni se ne possono perdere 6 e restare in guadagno.

Le operazioni si ricostruiscono dagli ordini del BROKER, non dai nostri file:
l'ordine padre da' prezzo di carico e quantita', la sua gamba di stop da' il
rischio, le vendite danno l'uscita.
"""
from __future__ import annotations

import logging
from collections import defaultdict

log = logging.getLogger("trades")

# Sotto questa distanza lo stop e' cosi' vicino al prezzo di carico che il
# rischio tende a zero e il fattore diventa un numero enorme e privo di senso
# (P&L diviso quasi-zero). E' successo davvero: una posizione uscita a +0,07%
# risultava +1,40R perche' lo stop era stato calcolato sul prezzo pianificato
# invece che su quello di esecuzione. Meglio dichiarare il dato inattendibile
# che pubblicare un numero lusinghiero e falso.
MIN_STOP_DISTANCE_PCT = 0.005


def closed_trades(client, after: str) -> list[dict]:
    """Operazioni azionarie chiuse dopo `after` (data ISO), con fattore di rischio.

    Ritorna un dict per operazione con: symbol, entry, exit, qty, stop, pl_usd,
    pl_pct, risk_usd, r_multiple, closed_by.
    """
    orders = client._request(
        "GET", client._t("/v2/orders"),
        params={"status": "all", "limit": 500, "nested": "true", "after": after},
    )

    # Vendite disponibili per abbinamento, in ordine di tempo e per titolo.
    sells: dict[str, list] = defaultdict(list)
    for o in orders:
        if o.get("side") == "sell" and o.get("status") == "filled" and o.get("filled_at"):
            sells[o["symbol"]].append(o)
    for lst in sells.values():
        lst.sort(key=lambda x: x["filled_at"])

    out = []
    for o in sorted(orders, key=lambda x: x.get("created_at") or ""):
        if o.get("side") != "buy" or o.get("status") != "filled":
            continue
        if "/" in o.get("symbol", ""):
            continue  # coppia cripto: appartiene all'altra divisione, non a questo conto
        legs = {l["type"]: l for l in (o.get("legs") or [])}
        entry = float(o.get("filled_avg_price") or 0)
        qty = float(o.get("filled_qty") or 0)
        if entry <= 0 or qty <= 0:
            continue

        # Uscita: la gamba che si e' riempita, oppure la prima vendita successiva
        # (le chiusure per scadenza avvengono a mercato, fuori dal bracket).
        chiusa_da, exit_px, closed_at = None, None, None
        for tipo, leg in legs.items():
            if leg.get("status") == "filled" and leg.get("filled_avg_price"):
                chiusa_da = "target" if tipo == "limit" else "stop"
                exit_px = float(leg["filled_avg_price"])
                closed_at = leg.get("filled_at")
                break
        if exit_px is None:
            cand = [s for s in sells.get(o["symbol"], [])
                    if (s.get("filled_at") or "") > (o.get("filled_at") or "")
                    and not s.get("_usata")]
            if cand:
                s = cand[0]
                s["_usata"] = True
                chiusa_da = "chiusura manuale"
                exit_px = float(s.get("filled_avg_price") or 0)
                closed_at = s.get("filled_at")
        if not exit_px:
            continue  # ancora aperta

        # Rischio: quanto si sarebbe perso se fosse scattato lo stop iniziale.
        stop = float((legs.get("stop") or {}).get("stop_price") or 0)
        risk = 0.0
        stop_sospetto = False
        if stop and stop < entry:
            if (entry - stop) / entry < MIN_STOP_DISTANCE_PCT:
                stop_sospetto = True   # stop troppo vicino: fattore non calcolabile
            else:
                risk = (entry - stop) * qty
        pl = (exit_px - entry) * qty
        out.append({
            "symbol": o["symbol"],
            "opened_at": o.get("filled_at"),
            "closed_at": closed_at,
            "entry": round(entry, 4),
            "exit": round(exit_px, 4),
            "stop": round(stop, 4) if stop else None,
            "qty": qty,
            "pl_usd": round(pl, 2),
            "pl_pct": round((exit_px / entry - 1) * 100, 2),
            "risk_usd": round(risk, 2) if risk else None,
            "r_multiple": round(pl / risk, 2) if risk > 0 else None,
            "stop_sospetto": stop_sospetto,
            "closed_by": chiusa_da,
        })
    return out


def summarize(trades: list[dict]) -> dict:
    """Statistiche, con e senza normalizzazione per il rischio."""
    if not trades:
        return {"n": 0}
    pls = [t["pl_usd"] for t in trades]
    wins = [t for t in trades if t["pl_usd"] > 0]
    rs = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
    s = {
        "n": len(trades),
        "vincenti": len(wins),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1),
        "pl_totale_usd": round(sum(pls), 2),
        "pl_medio_pct": round(sum(t["pl_pct"] for t in trades) / len(trades), 2),
    }
    if rs:
        vincR = [r for r in rs if r > 0]
        persR = [r for r in rs if r <= 0]
        s.update({
            "n_con_rischio_noto": len(rs),
            "R_medio": round(sum(rs) / len(rs), 2),
            "R_totale": round(sum(rs), 2),
            "R_migliore": round(max(rs), 2),
            "R_peggiore": round(min(rs), 2),
            "R_vincita_media": round(sum(vincR) / len(vincR), 2) if vincR else 0.0,
            "R_perdita_media": round(sum(persR) / len(persR), 2) if persR else 0.0,
        })
        # Quante operazioni perdenti "medie" si possono permettere per ogni
        # vincente media: e' la lettura pratica del vantaggio.
        if persR and s["R_perdita_media"] < 0:
            s["operazioni_perse_sostenibili_per_vincita"] = round(
                s["R_vincita_media"] / abs(s["R_perdita_media"]), 1)
    return s


def format_lines(trades: list[dict]) -> list[str]:
    """Righe leggibili per log e rendiconti."""
    out = []
    for t in trades:
        r = f"{t['r_multiple']:+.2f}R" if t.get("r_multiple") is not None else "  n/d"
        out.append("%-6s %-10s %8.2f -> %8.2f  %+7.2f%%  %8s  $%+9.2f  %s" % (
            t["symbol"], (t.get("closed_at") or "")[:10], t["entry"], t["exit"],
            t["pl_pct"], r, t["pl_usd"], t.get("closed_by") or "?"))
    return out
