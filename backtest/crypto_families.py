"""
crypto_families.py — confronto fra FAMIGLIE di strategie cripto diverse.

Il primo backtest ha provato solo varianti della nostra idea (momentum
trasversale con stop). Qui si mettono alla prova approcci strutturalmente
diversi, sullo stesso storico e con le stesse regole di prudenza:

  * nessuno sguardo al futuro: si decide con i dati fino a oggi, si esegue
    all'apertura di domani;
  * costi pagati su ogni lato (commissione 0,25% misurata sul conto reale
    piu' circa 0,15% di meta' spread);
  * ogni strategia viene poi rivalutata sulle due meta' del periodo: se
    funziona solo in una, non e' una strategia.

Il metro non e' lo zero ma BITCOIN. In un settore dove il riferimento ha
fatto +10% nel periodo, una strategia che rende +5% ha perso.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.crypto_backtest import load_bars, index_by_date  # noqa: E402

COST = 0.0040
LARGE = ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "LINK/USD",
         "LTC/USD", "BCH/USD", "AVAX/USD", "DOT/USD", "ADA/USD"]


def _ma(hist, n):
    if len(hist) < n:
        return None
    return sum(b["c"] for b in hist[-n:]) / n


def _ret(hist, n):
    if len(hist) <= n or not hist[-(n + 1)]["c"]:
        return None
    return hist[-1]["c"] / hist[-(n + 1)]["c"] - 1


def simulate(bars, dates, lookup, decide, universe=None, label=""):
    """Motore generico. `decide(hist, day)` -> {coppia: peso} per DOMANI."""
    uni = universe or list(bars)
    equity, cash = 1000.0, 1000.0
    holdings: dict[str, float] = {}          # coppia -> quantita'
    hist = {p: [] for p in uni}
    pending = None
    peak, max_dd, ops = equity, 0.0, 0

    for di, day in enumerate(dates):
        today = {}
        for p in uni:
            b = lookup.get(p, {}).get(day)
            if b:
                hist[p].append(b)
                today[p] = b

        # esecuzione all'apertura di oggi delle decisioni di ieri
        if pending is not None:
            valore = cash + sum(q * today[p]["o"] for p, q in holdings.items() if p in today)
            for p in list(holdings):
                if p not in pending and p in today:
                    cash += holdings.pop(p) * today[p]["o"] * (1 - COST)
                    ops += 1
            for p, w in pending.items():
                if p not in today or w <= 0:
                    continue
                voluto = valore * w
                attuale = holdings.get(p, 0) * today[p]["o"]
                diff = voluto - attuale
                if abs(diff) < valore * 0.02:       # niente micro-ribilanciamenti
                    continue
                px = today[p]["o"]
                if diff > 0 and cash > 0:
                    speso = min(diff, cash)
                    holdings[p] = holdings.get(p, 0) + speso / (px * (1 + COST))
                    cash -= speso
                    ops += 1
                elif diff < 0:
                    qta = min(-diff / px, holdings.get(p, 0))
                    holdings[p] = holdings.get(p, 0) - qta
                    cash += qta * px * (1 - COST)
                    ops += 1
                    if holdings.get(p, 0) <= 1e-12:
                        holdings.pop(p, None)
            pending = None

        equity = cash + sum(q * today[p]["c"] for p, q in holdings.items() if p in today)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak else 0)

        if di < len(dates) - 1:
            pending = decide(hist, day) or {}

    anni = len(dates) / 365.25
    return {
        "label": label,
        "rendimento_pct": round((equity / 1000 - 1) * 100, 1),
        "annuo_pct": round(((equity / 1000) ** (1 / anni) - 1) * 100, 1) if anni > 0 else 0,
        "max_dd_pct": round(max_dd * 100, 1),
        "operazioni": ops,
    }


# =====================================================================
#  Le famiglie
# =====================================================================
def f_hold_btc(hist, day):
    return {"BTC/USD": 1.0}


def f_hold_basket(hist, day):
    vivi = [p for p in LARGE if hist.get(p)]
    return {p: 1.0 / len(vivi) for p in vivi} if vivi else {}


def make_trend_btc(n):
    def f(hist, day):
        h = hist.get("BTC/USD") or []
        m = _ma(h, n)
        if m is None:
            return {}
        return {"BTC/USD": 1.0} if h[-1]["c"] > m else {}
    return f


def make_trend_basket(n, top=3):
    """Tiene solo le large cap sopra la propria media mobile."""
    def f(hist, day):
        ok = []
        for p in LARGE:
            h = hist.get(p) or []
            m = _ma(h, n)
            if m and h[-1]["c"] > m:
                ok.append(p)
        if not ok:
            return {}
        ok = ok[:top] if top else ok
        return {p: 1.0 / len(ok) for p in ok}
    return f


def make_momentum_large(n_pos, window):
    """Momentum trasversale ma SOLO large cap, senza stop."""
    def f(hist, day):
        pun = []
        for p in LARGE:
            r = _ret(hist.get(p) or [], window)
            if r is not None:
                pun.append((r, p))
        pun.sort(reverse=True)
        sel = [p for r, p in pun[:n_pos] if r > 0]
        return {p: 1.0 / len(sel) for p in sel} if sel else {}
    return f


def make_reversion(n_pos, window):
    """Comprare i piu' scesi: l'opposto del momentum."""
    def f(hist, day):
        pun = []
        for p in LARGE:
            r = _ret(hist.get(p) or [], window)
            if r is not None:
                pun.append((r, p))
        pun.sort()
        sel = [p for r, p in pun[:n_pos]]
        return {p: 1.0 / len(sel) for p in sel} if sel else {}
    return f


def make_btc_eth_trend(n):
    """Il piu' semplice difendibile: BTC ed ETH, tenuti solo sopra la media."""
    def f(hist, day):
        ok = []
        for p in ("BTC/USD", "ETH/USD"):
            h = hist.get(p) or []
            m = _ma(h, n)
            if m and h[-1]["c"] > m:
                ok.append(p)
        return {p: 1.0 / len(ok) for p in ok} if ok else {}
    return f


def main() -> int:
    print("Scarico lo storico...")
    bars = load_bars(900)
    dates, lookup = index_by_date(bars)
    meta = len(dates) // 2
    print("  %d coppie, %d giorni (%s -> %s)\n" % (len(bars), len(dates), dates[0], dates[-1]))

    fam = [
        ("comprare e tenere BITCOIN", f_hold_btc, None),
        ("paniere 10 large cap, ribilanciato", f_hold_basket, LARGE),
        ("BTC sopra la media a 50 giorni", make_trend_btc(50), ["BTC/USD"]),
        ("BTC sopra la media a 100 giorni", make_trend_btc(100), ["BTC/USD"]),
        ("BTC sopra la media a 200 giorni", make_trend_btc(200), ["BTC/USD"]),
        ("BTC+ETH sopra la media a 100 gg", make_btc_eth_trend(100), LARGE),
        ("large cap sopra la media a 100 gg", make_trend_basket(100, top=None), LARGE),
        ("momentum 30gg su large cap (3)", make_momentum_large(3, 30), LARGE),
        ("momentum 90gg su large cap (3)", make_momentum_large(3, 90), LARGE),
        ("inversione: compra i piu' scesi (3)", make_reversion(3, 30), LARGE),
    ]

    print("%-38s %9s %8s %8s %7s" % ("FAMIGLIA", "RENDIM.", "ANNUO", "MAX DD", "OPER."))
    print("-" * 76)
    risultati = []
    for nome, fn, uni in fam:
        r = simulate(bars, dates, lookup, fn, uni, nome)
        risultati.append((nome, fn, uni, r))
        print("%-38s %+8.1f%% %+7.1f%% %7.1f%% %6d" % (
            nome, r["rendimento_pct"], r["annuo_pct"], r["max_dd_pct"], r["operazioni"]))

    print("\n" + "=" * 76)
    print("PROVA DI ROBUSTEZZA — funziona in ENTRAMBE le meta' del periodo?")
    print("(%s->%s  |  %s->%s)\n" % (dates[0], dates[meta], dates[meta], dates[-1]))
    print("%-38s %11s %11s  %s" % ("FAMIGLIA", "1a META'", "2a META'", "giudizio"))
    print("-" * 76)
    for nome, fn, uni, _ in risultati:
        a = simulate(bars, dates[:meta], lookup, fn, uni)["rendimento_pct"]
        b = simulate(bars, dates[meta:], lookup, fn, uni)["rendimento_pct"]
        g = "coerente" if (a > 0) == (b > 0) else "INCOERENTE"
        if a > 0 and b > 0:
            g = "positiva in entrambe"
        print("%-38s %+10.1f%% %+10.1f%%  %s" % (nome, a, b, g))
    return 0


if __name__ == "__main__":
    sys.exit(main())
