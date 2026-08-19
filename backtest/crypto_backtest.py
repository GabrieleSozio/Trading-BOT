"""
crypto_backtest.py — prova della strategia cripto su storico reale.

Riproduce giorno per giorno cio' che il bot fa in produzione: classifica di
momentum, selezione delle prime N, pesi a rischio costante, stop tarato sulla
volatilita' e trailing stop. Serve a rispondere con dei numeri a domande su cui
finora si poteva solo avere un'opinione.

Regole rispettate per non barare:

  * NESSUNO SGUARDO AL FUTURO. La decisione del giorno d usa solo barre fino al
    giorno d incluso, e viene eseguita all'APERTURA del giorno d+1. Usare la
    chiusura dello stesso giorno significherebbe comprare sapendo gia' com'e'
    andata.
  * DENTRO LA GIORNATA SI ASSUME IL PEGGIO. Se in un giorno il prezzo tocca sia
    lo stop sia un nuovo massimo, si considera colpito prima lo stop. Le barre
    giornaliere non dicono l'ordine, e l'ipotesi prudente evita di regalarsi
    guadagni inesistenti.
  * I COSTI SI PAGANO. Commissione e meta' spread su ogni lato, misurati sugli
    ordini reali del conto paper.

Limite noto e non eliminabile: l'universo e' quello che il broker offre OGGI.
Le monete tolte dal listino in passato non compaiono, quindi i risultati sono
ottimistici per costruzione (sopravvivono solo i sopravvissuti). Va tenuto a
mente prima di prendere sul serio il rendimento assoluto: i CONFRONTI fra
varianti restano validi, perche' l'errore e' lo stesso per tutte.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto.broker import CryptoClient, load_config  # noqa: E402

STABLE = {"USDC/USD", "USDT/USD", "USDG/USD", "PAXG/USD"}

# Costi per LATO, misurati sul conto reale: 0,25% di commissione (trattenuta in
# moneta sugli acquisti) piu' circa 0,15% di meta' spread.
COST_PER_SIDE = 0.0040


# =====================================================================
#  Dati
# =====================================================================
def load_bars(days: int) -> dict[str, list[dict]]:
    cli = CryptoClient(load_config())
    pairs = sorted(s for s in cli.crypto_assets()
                   if s.endswith("/USD") and s not in STABLE)
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    bars = cli.crypto_bars(pairs, start=start, timeframe="1D")
    out = {}
    for p, rows in bars.items():
        rows = sorted(rows, key=lambda b: b["t"])
        if len(rows) >= 120:
            out[p] = rows
    return out


def index_by_date(bars: dict) -> tuple[list[str], dict]:
    dates = sorted({b["t"][:10] for rows in bars.values() for b in rows})
    lookup = {p: {b["t"][:10]: b for b in rows} for p, rows in bars.items()}
    return dates, lookup


# =====================================================================
#  Segnali (stessa logica di crypto/signals.py)
# =====================================================================
def metrics_at(hist: list[dict], weights: dict, atr_days: int) -> dict | None:
    """Momentum e volatilita' usando SOLO le barre fornite (fino a oggi)."""
    need = max(max(weights), 90)
    if len(hist) < need + 1:
        return None
    score, used = 0.0, 0.0
    rets = {}
    for w, wt in weights.items():
        past = hist[-(w + 1)]["c"]
        if not past:
            continue
        r = hist[-1]["c"] / past - 1
        rets[w] = r
        score += wt * r
        used += wt
    if used <= 0:
        return None
    atr = sum((b["h"] - b["l"]) / b["c"] for b in hist[-atr_days:] if b["c"]) / atr_days
    return {"score": score / used, "atr": atr, "close": hist[-1]["c"]}


def stop_distance(atr: float, mult: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, atr * mult))


def target_weights(sel: list[dict], p: dict) -> dict[str, float]:
    raw = {}
    for s in sel:
        d = s["stop_dist"]
        raw[s["pair"]] = max(p["min_pos"], min(p["max_pos"],
                             p["risk_per_pos"] / d if d > 0 else p["min_pos"]))
    tot = sum(raw.values())
    if tot <= 0:
        return {}
    scale = min(1.0, p["deployment"] / tot)
    return {k: v * scale for k, v in raw.items()}


# =====================================================================
#  Motore
# =====================================================================
def backtest(bars: dict, dates: list[str], lookup: dict, p: dict) -> dict:
    equity = 1000.0
    cash = equity
    positions: dict[str, dict] = {}
    trades: list[dict] = []
    curve: list[tuple[str, float]] = []
    peak, max_dd = equity, 0.0

    hist: dict[str, list[dict]] = {k: [] for k in bars}
    pending: dict[str, float] | None = None   # decisioni da eseguire domani

    for di, day in enumerate(dates):
        # --- 1. aggiorna lo storico con la barra di oggi ---
        today_bar = {}
        for pair in bars:
            b = lookup[pair].get(day)
            if b:
                hist[pair].append(b)
                today_bar[pair] = b

        # --- 2. esegue all'APERTURA le decisioni prese ieri ---
        if pending is not None:
            for pair, usd in pending.items():
                b = today_bar.get(pair)
                if not b or pair in positions or usd <= 0:
                    continue
                px = b["o"] * (1 + COST_PER_SIDE)
                qty = usd / px
                m = metrics_at(hist[pair][:-1], p["weights"], p["atr_days"])
                if not m:
                    continue
                d = stop_distance(m["atr"], p["atr_mult"], p["min_stop"], p["max_stop"])
                positions[pair] = {"entry": px, "qty": qty, "high": px,
                                   "dist": d, "stop": px * (1 - d),
                                   "opened": day, "risk": usd * d}
                cash -= usd
            pending = None

        # --- 3. gestisce le posizioni aperte ---
        for pair in list(positions):
            b = today_bar.get(pair)
            pos = positions[pair]
            if not b:
                continue
            # Ipotesi prudente: prima il minimo, poi il massimo.
            if b["l"] <= pos["stop"]:
                exit_px = min(pos["stop"], b["o"]) * (1 - COST_PER_SIDE)
                pl = (exit_px - pos["entry"]) * pos["qty"]
                cash += exit_px * pos["qty"]
                trades.append({"pair": pair, "in": pos["opened"], "out": day,
                               "entry": pos["entry"], "exit": exit_px,
                               "pl": pl, "r": pl / pos["risk"] if pos["risk"] else None,
                               "why": "stop"})
                del positions[pair]
                continue
            if b["h"] > pos["high"]:
                pos["high"] = b["h"]
                if p["trailing"]:
                    pos["stop"] = max(pos["stop"], pos["high"] * (1 - pos["dist"]))
            if p["take_profit"] and b["h"] >= pos["entry"] * (1 + p["take_profit"]):
                exit_px = max(pos["entry"] * (1 + p["take_profit"]), b["o"]) * (1 - COST_PER_SIDE)
                pl = (exit_px - pos["entry"]) * pos["qty"]
                cash += exit_px * pos["qty"]
                trades.append({"pair": pair, "in": pos["opened"], "out": day,
                               "entry": pos["entry"], "exit": exit_px,
                               "pl": pl, "r": pl / pos["risk"] if pos["risk"] else None,
                               "why": "target"})
                del positions[pair]

        # --- 4. classifica di oggi (per decidere cosa fare domani) ---
        ranked = []
        for pair in bars:
            m = metrics_at(hist[pair], p["weights"], p["atr_days"])
            if m:
                m["pair"] = pair
                m["stop_dist"] = stop_distance(m["atr"], p["atr_mult"],
                                               p["min_stop"], p["max_stop"])
                ranked.append(m)
        ranked.sort(key=lambda x: x["score"], reverse=True)
        rank_of = {m["pair"]: i + 1 for i, m in enumerate(ranked)}

        # uscita per debolezza relativa (eseguita all'apertura di domani)
        esci = [pair for pair in positions
                if rank_of.get(pair, 9999) > p["rank_exit"]]
        for pair in esci:
            b = today_bar.get(pair)
            pos = positions[pair]
            if not b:
                continue
            exit_px = b["c"] * (1 - COST_PER_SIDE)
            pl = (exit_px - pos["entry"]) * pos["qty"]
            cash += exit_px * pos["qty"]
            trades.append({"pair": pair, "in": pos["opened"], "out": day,
                           "entry": pos["entry"], "exit": exit_px,
                           "pl": pl, "r": pl / pos["risk"] if pos["risk"] else None,
                           "why": "fuori classifica"})
            del positions[pair]

        # --- 5. valore del portafoglio ---
        mv = sum(pos["qty"] * (today_bar[pair]["c"] if pair in today_bar else pos["entry"])
                 for pair, pos in positions.items())
        equity = cash + mv
        curve.append((day, equity))
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak else 0)

        # --- 6. decide gli ingressi di domani ---
        if di < len(dates) - 1:
            liberi = p["positions"] - len(positions)
            if liberi > 0:
                cand = [m for m in ranked[:p["positions"]] if m["pair"] not in positions]
                if cand:
                    w = target_weights(ranked[:p["positions"]], p)
                    pending = {}
                    for m in cand[:liberi]:
                        usd = w.get(m["pair"], 0) * equity
                        if usd >= p["min_order"] and usd <= cash:
                            pending[m["pair"]] = usd

    rs = [t["r"] for t in trades if t["r"] is not None]
    wins = [t for t in trades if t["pl"] > 0]
    anni = len(dates) / 365.25
    return {
        "equity_finale": round(equity, 2),
        "rendimento_pct": round((equity / 1000 - 1) * 100, 1),
        "annuo_pct": round(((equity / 1000) ** (1 / anni) - 1) * 100, 1) if anni > 0 else 0,
        "max_drawdown_pct": round(max_dd * 100, 1),
        "n_operazioni": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "R_medio": round(sum(rs) / len(rs), 3) if rs else None,
        "R_totale": round(sum(rs), 1) if rs else None,
        "R_vincita_media": round(sum(r for r in rs if r > 0) / max(len([r for r in rs if r > 0]), 1), 2) if rs else None,
        "R_perdita_media": round(sum(r for r in rs if r <= 0) / max(len([r for r in rs if r <= 0]), 1), 2) if rs else None,
        "giorni": len(dates),
        "trades": trades,
        "curve": curve,
    }


def base_params(**over) -> dict:
    p = {
        "weights": {7: 0.45, 30: 0.40, 90: 0.15},
        "atr_days": 14, "atr_mult": 2.5,
        "min_stop": 0.04, "max_stop": 0.30,
        "positions": 3, "deployment": 0.96,
        "risk_per_pos": 0.05, "min_pos": 0.12, "max_pos": 0.45,
        "rank_exit": 5, "min_order": 10.0,
        "trailing": True, "take_profit": None,
    }
    p.update(over)
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="Prova storica della strategia cripto")
    ap.add_argument("--days", type=int, default=900)
    ap.add_argument("--out", default="backtest/results_crypto.json")
    a = ap.parse_args()

    print("Scarico lo storico...")
    bars = load_bars(a.days)
    dates, lookup = index_by_date(bars)
    print("  %d coppie, %d giorni (%s -> %s)\n" % (len(bars), len(dates), dates[0], dates[-1]))

    varianti = [
        ("PRODUZIONE (trailing, 3 posizioni)", base_params()),
        ("con target fisso +16%, niente trailing", base_params(trailing=False, take_profit=0.16)),
        ("con target fisso +30%, niente trailing", base_params(trailing=False, take_profit=0.30)),
        ("trailing piu' stretto (2.0 x ATR)", base_params(atr_mult=2.0)),
        ("trailing piu' largo (3.5 x ATR)", base_params(atr_mult=3.5)),
        ("2 posizioni", base_params(positions=2)),
        ("5 posizioni", base_params(positions=5, rank_exit=8)),
        ("solo momentum a 30 giorni", base_params(weights={30: 1.0})),
        ("solo momentum a 7 giorni", base_params(weights={7: 1.0})),
        ("momentum lento (30/90)", base_params(weights={30: 0.5, 90: 0.5})),
        ("uscita piu' lenta (oltre il 10 posto)", base_params(rank_exit=10)),
        ("senza costi (per misurarne il peso)", base_params()),
    ]

    print("%-40s %9s %8s %8s %7s %8s %8s" % (
        "VARIANTE", "RENDIM.", "ANNUO", "MAX DD", "OPER.", "VINC.%", "R MEDIO"))
    print("-" * 96)
    risultati = {}
    global COST_PER_SIDE
    for nome, p in varianti:
        salva = COST_PER_SIDE
        if "senza costi" in nome:
            COST_PER_SIDE = 0.0
        r = backtest(bars, dates, lookup, p)
        COST_PER_SIDE = salva
        risultati[nome] = {k: v for k, v in r.items() if k not in ("trades", "curve")}
        print("%-40s %+8.1f%% %+7.1f%% %7.1f%% %7d %7.1f%% %+8.3f" % (
            nome, r["rendimento_pct"], r["annuo_pct"], r["max_drawdown_pct"],
            r["n_operazioni"], r["win_rate_pct"], r["R_medio"] or 0))
        if nome.startswith("PRODUZIONE"):
            risultati["_produzione_dettaglio"] = {
                "R_vincita_media": r["R_vincita_media"],
                "R_perdita_media": r["R_perdita_media"],
                "R_totale": r["R_totale"],
                "trades": r["trades"][-40:],
            }

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(risultati, indent=1), encoding="utf-8")
    print("\nDettaglio salvato in %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
