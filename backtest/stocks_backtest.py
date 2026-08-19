"""
stocks_backtest.py — prova della strategia azionaria su storico reale.

Riproduce il nucleo deterministico della divisione azioni: scarto di apertura
rispetto alla chiusura precedente, filtro di accessibilita' e di direzione,
ingresso su ritracciamento, protezione con stop e target, chiusura d'ufficio
dopo N giorni di borsa.

Cosa NON puo' riprodurre, dichiarato apertamente:

  * la SELEZIONE DI CLAUDE. In produzione l'AI sceglie 5 candidati fra quelli
    filtrati, con motivazione. Qui si usa il criterio deterministico di ripiego
    (i movimenti piu' ampi). Se l'AI aggiunge valore, questa prova lo ignora; se
    ne toglie, idem. Misura quindi il MOTORE, non l'intero sistema.
  * il VOLUME DI PRE-APERTURA, che in produzione ordina i candidati. Servirebbero
    le barre da un minuto di ogni giorno per due anni.
  * il segnale INSIDER, che dipende da quando i moduli sono stati depositati.

Assunzioni prudenti, per non regalarsi risultati:
  * dentro la giornata si assume che il minimo arrivi prima del massimo, quindi
    a parita' di giorno lo stop scatta prima del target;
  * lo scarto di apertura e' noto solo all'apertura, e l'ingresso avviene dopo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402
from lib.alpaca_rest import AlpacaClient  # noqa: E402

COST_PER_SIDE = 0.0005   # spread su titoli liquidi; niente commissioni su Alpaca


def load_bars(days: int) -> dict[str, list[dict]]:
    cfg = yaml.safe_load(open("config/trading_config.yaml", encoding="utf-8"))
    tk = cfg["universe"]["tickers"]
    cli = AlpacaClient(max_consecutive_errors=9)
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    bars = cli.bars(tk, "1Day", start, feed="sip", limit=10000)
    return {k: sorted(v, key=lambda b: b["t"]) for k, v in bars.items() if len(v) > 200}


def backtest(bars: dict, p: dict) -> dict:
    dates = sorted({b["t"][:10] for rows in bars.values() for b in rows})
    lookup = {s: {b["t"][:10]: b for b in rows} for s, rows in bars.items()}
    prev = {s: None for s in bars}

    capital = 550.0
    cash = capital
    positions: dict[str, dict] = {}
    trades: list[dict] = []
    peak, max_dd = capital, 0.0
    giorni_senza_candidati = 0

    for di, day in enumerate(dates):
        oggi = {s: lookup[s].get(day) for s in bars}
        oggi = {s: b for s, b in oggi.items() if b}

        # --- 1. gestione delle posizioni aperte ---
        for sym in list(positions):
            b = oggi.get(sym)
            pos = positions[sym]
            if not b:
                continue
            pos["giorni"] += 1
            uscita = None
            # prudenza: prima il minimo
            if b["l"] <= pos["stop"]:
                uscita = (min(pos["stop"], b["o"]), "stop")
            elif b["h"] >= pos["target"]:
                uscita = (max(pos["target"], b["o"]), "target")
            elif pos["giorni"] >= p["max_hold"]:
                uscita = (b["c"], "scadenza")
            if uscita:
                px = uscita[0] * (1 - COST_PER_SIDE)
                pl = (px - pos["entry"]) * pos["qty"]
                cash += px * pos["qty"]
                trades.append({"sym": sym, "in": pos["opened"], "out": day,
                               "entry": pos["entry"], "exit": px, "qty": pos["qty"],
                               "pl": round(pl, 2),
                               "pct": round((px / pos["entry"] - 1) * 100, 2),
                               "r": round(pl / pos["risk"], 3) if pos["risk"] else None,
                               "why": uscita[1]})
                del positions[sym]

        # --- 2. valore corrente e capitale operativo ---
        mv = sum(pos["qty"] * (oggi[s]["c"] if s in oggi else pos["entry"])
                 for s, pos in positions.items())
        capital = cash + mv
        peak = max(peak, capital)
        max_dd = max(max_dd, (peak - capital) / peak if peak else 0)

        # --- 3. nuovi ingressi ---
        liberi = p["positions"] - len(positions)
        if liberi > 0 and di > 0:
            max_price = capital * p["size_pct"]
            cand = []
            for s, b in oggi.items():
                pc = prev[s]
                if not pc or not pc["c"]:
                    continue
                gap = (b["o"] - pc["c"]) / pc["c"] * 100
                if abs(gap) > 50 or abs(gap) < 0.02:
                    continue
                if gap < 0:                       # niente short in fascia micro
                    continue
                if b["o"] > max_price:            # servono azioni intere
                    continue
                if s in positions:
                    continue
                cand.append((gap, s, b))
            if not cand:
                giorni_senza_candidati += 1
            cand.sort(reverse=True)
            for gap, s, b in cand[:liberi]:
                target_entry = b["o"] * (1 - p["retracement"])
                if b["l"] > target_entry:
                    continue                      # il ritracciamento non e' arrivato
                px = target_entry * (1 + COST_PER_SIDE)
                quota = capital * p["size_pct"]
                qty = int(min(quota, cash) // px)
                if qty < 1:
                    continue
                stop = px * (1 - p["stop"])
                positions[s] = {"entry": px, "qty": qty, "opened": day, "giorni": 0,
                                "stop": stop, "target": px * (1 + p["take_profit"]),
                                "risk": (px - stop) * qty}
                cash -= px * qty

        for s, b in oggi.items():
            prev[s] = b

    rs = [t["r"] for t in trades if t["r"] is not None]
    wins = [t for t in trades if t["pl"] > 0]
    anni = len(dates) / 252
    return {
        "capitale_finale": round(capital, 2),
        "rendimento_pct": round((capital / 550 - 1) * 100, 1),
        "annuo_pct": round(((capital / 550) ** (1 / anni) - 1) * 100, 1) if anni > 0 else 0,
        "max_drawdown_pct": round(max_dd * 100, 1),
        "n_operazioni": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "R_medio": round(sum(rs) / len(rs), 3) if rs else None,
        "R_vincita_media": round(sum(r for r in rs if r > 0) / max(len([r for r in rs if r > 0]), 1), 2) if rs else None,
        "R_perdita_media": round(sum(r for r in rs if r <= 0) / max(len([r for r in rs if r <= 0]), 1), 2) if rs else None,
        "giorni_borsa": len(dates),
        "giorni_senza_candidati": giorni_senza_candidati,
        "uscite": {k: sum(1 for t in trades if t["why"] == k)
                   for k in ("stop", "target", "scadenza")},
        "trades": trades,
    }


def base(**over) -> dict:
    p = {"positions": 2, "size_pct": 0.45, "stop": 0.03, "take_profit": 0.06,
         "max_hold": 5, "retracement": 0.005}
    p.update(over)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=760)
    ap.add_argument("--out", default="backtest/results_stocks.json")
    a = ap.parse_args()

    print("Scarico lo storico consolidato...")
    bars = load_bars(a.days)
    n = len(next(iter(bars.values())))
    print("  %d titoli, %d giorni di borsa\n" % (len(bars), n))

    varianti = [
        ("PRODUZIONE (stop -3% / target +6%, 5gg)", base()),
        ("target +10%", base(take_profit=0.10)),
        ("target +12%, stop -4%", base(stop=0.04, take_profit=0.12)),
        ("stop -2% / target +6%", base(stop=0.02)),
        ("stop -5% / target +6%", base(stop=0.05)),
        ("tenuta max 10 giorni", base(max_hold=10)),
        ("tenuta max 3 giorni", base(max_hold=3)),
        ("ingresso senza ritracciamento", base(retracement=0.0)),
        ("ritracciamento piu' profondo (1,5%)", base(retracement=0.015)),
        ("3 posizioni da 30%", base(positions=3, size_pct=0.30)),
    ]

    print("%-42s %9s %8s %8s %7s %7s %8s" % (
        "VARIANTE", "RENDIM.", "ANNUO", "MAX DD", "OPER.", "VINC.%", "R MEDIO"))
    print("-" * 96)
    out = {}
    for nome, p in varianti:
        r = backtest(bars, p)
        out[nome] = {k: v for k, v in r.items() if k != "trades"}
        print("%-42s %+8.1f%% %+7.1f%% %7.1f%% %7d %6.1f%% %+8.3f" % (
            nome, r["rendimento_pct"], r["annuo_pct"], r["max_drawdown_pct"],
            r["n_operazioni"], r["win_rate_pct"], r["R_medio"] or 0))
        if nome.startswith("PRODUZIONE"):
            out["_produzione"] = {k: v for k, v in r.items() if k != "trades"}
            out["_ultime_operazioni"] = r["trades"][-25:]

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nDettaglio in %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
