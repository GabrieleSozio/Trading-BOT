"""
stock_families.py — confronto fra FAMIGLIE di strategie azionarie.

Non varianti della nostra idea: approcci strutturalmente diversi, provati sullo
stesso storico, con gli stessi vincoli reali del nostro conto e le stesse regole
di prudenza gia' usate sulle cripto.

Vincoli riprodotti fedelmente:
  * capitale iniziale 550 USD e AZIONI INTERE (a 30% per posizione la soglia e'
    ~175 USD: molti titoli non sono proprio comprabili, e questo cambia il
    risultato piu' di quanto si pensi);
  * niente vendite allo scoperto (fascia micro);
  * ribilanciamento mensile per le strategie lente, cosa che evita del tutto la
    regola Pattern Day Trader;
  * costi su ogni lato (Alpaca non prende commissioni sulle azioni, resta lo
    spread sui titoli liquidi).

Regole anti-illusione:
  * NESSUNO SGUARDO AL FUTURO: si decide con i dati fino a oggi, si esegue
    all'apertura di domani;
  * ogni famiglia viene rivalutata sulle due meta' del periodo;
  * si confronta sempre con il comprare-e-tenere, perche' un rendimento positivo
    mentre il mercato saliva di piu' e' un fallimento.

Avvertenza che vale per tutto il file: piu' famiglie si provano, piu' e'
probabile che la migliore sia fortuna. I risultati qui vanno letti come
indicazioni di DIREZIONE, mai come promesse.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402
from lib.alpaca_rest import AlpacaClient  # noqa: E402

COST = 0.0005          # spread su titoli liquidi; niente commissioni
CAPITALE = 550.0
N_POS, PESO = 3, 0.30  # come la configurazione attuale


def load(days: int = 1300):
    cfg = yaml.safe_load(open("config/trading_config.yaml", encoding="utf-8"))
    tk = cfg["universe"]["tickers"] + ["SPY"]
    cli = AlpacaClient(max_consecutive_errors=9)
    import datetime as dt
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    bars = cli.bars(tk, "1Day", start, feed="sip", limit=10000)
    bars = {k: sorted(v, key=lambda b: b["t"]) for k, v in bars.items() if len(v) > 300}
    dates = sorted({b["t"][:10] for r in bars.values() for b in r})
    lookup = {s: {b["t"][:10]: b for b in r} for s, r in bars.items()}
    return bars, dates, lookup


def _ma(h, n):
    return sum(b["c"] for b in h[-n:]) / n if len(h) >= n else None


def _ret(h, n):
    return h[-1]["c"] / h[-(n + 1)]["c"] - 1 if len(h) > n and h[-(n + 1)]["c"] else None


def _vol(h, n):
    if len(h) < n + 1:
        return None
    r = [h[i]["c"] / h[i - 1]["c"] - 1 for i in range(len(h) - n, len(h)) if h[i - 1]["c"]]
    if not r:
        return None
    m = sum(r) / len(r)
    return (sum((x - m) ** 2 for x in r) / len(r)) ** 0.5


def simulate(bars, dates, lookup, decide, universo=None, mensile=True):
    """Motore a peso obiettivo con azioni intere."""
    uni = universo or [s for s in bars if s != "SPY"]
    cash = CAPITALE
    qty: dict[str, int] = {}
    hist = {s: [] for s in bars}
    pending = None
    peak = maxdd = 0.0
    equity = CAPITALE
    ops = 0
    mese_visto = None

    for di, day in enumerate(dates):
        oggi = {}
        for s in bars:
            b = lookup[s].get(day)
            if b:
                hist[s].append(b)
                oggi[s] = b

        # esecuzione all'apertura
        if pending is not None:
            val = cash + sum(q * oggi[s]["o"] for s, q in qty.items() if s in oggi)
            for s in list(qty):
                if s not in pending and s in oggi:
                    cash += qty.pop(s) * oggi[s]["o"] * (1 - COST); ops += 1
            for s, w in pending.items():
                if s not in oggi or w <= 0:
                    continue
                px = oggi[s]["o"]
                voluto = int(val * w / px)          # AZIONI INTERE
                delta = voluto - qty.get(s, 0)
                if delta > 0:
                    costo = delta * px * (1 + COST)
                    if costo > cash:
                        delta = int(cash / (px * (1 + COST)))
                        costo = delta * px * (1 + COST)
                    if delta > 0:
                        qty[s] = qty.get(s, 0) + delta; cash -= costo; ops += 1
                elif delta < 0:
                    n = min(-delta, qty.get(s, 0))
                    if n > 0:
                        qty[s] -= n; cash += n * px * (1 - COST); ops += 1
                        if qty[s] == 0:
                            qty.pop(s)
            pending = None

        equity = cash + sum(q * oggi[s]["c"] for s, q in qty.items() if s in oggi)
        peak = max(peak, equity)
        maxdd = max(maxdd, (peak - equity) / peak if peak else 0)

        if di < len(dates) - 1:
            mese = day[:7]
            if mensile and mese == mese_visto:
                continue                            # si ribilancia una volta al mese
            nuovo = decide(hist, day, equity, uni)
            if nuovo is not None:
                pending = nuovo
                mese_visto = mese

    anni = len(dates) / 252
    return {"rend": (equity / CAPITALE - 1) * 100,
            "annuo": ((equity / CAPITALE) ** (1 / anni) - 1) * 100 if anni > 0 else 0,
            "maxdd": maxdd * 100, "ops": ops, "finale": equity}


# =====================================================================
#  Famiglie
# =====================================================================
def f_spy(h, d, eq, uni):
    return {"SPY": 1.0}


def f_paniere(h, d, eq, uni):
    vivi = [s for s in uni if h.get(s)]
    return {s: 1.0 / len(vivi) for s in vivi} if vivi else {}


def mk_momentum(giorni, n=N_POS, peso=PESO):
    """Momentum trasversale: compra i piu' saliti negli ultimi N giorni."""
    def f(h, d, eq, uni):
        p = []
        for s in uni:
            r = _ret(h.get(s) or [], giorni)
            if r is not None and (h[s][-1]["c"] <= eq * peso):   # azioni intere
                p.append((r, s))
        p.sort(reverse=True)
        sel = [s for r, s in p[:n] if r > 0]
        return {s: peso for s in sel}
    return f


def mk_trend(ma_giorni, n=N_POS, peso=PESO):
    """Segue la tendenza: tiene solo i titoli sopra la propria media mobile,
    ordinati per forza. E' l'approccio con le prove piu' solide."""
    def f(h, d, eq, uni):
        p = []
        for s in uni:
            hh = h.get(s) or []
            m = _ma(hh, ma_giorni)
            if m and hh[-1]["c"] > m and hh[-1]["c"] <= eq * peso:
                r = _ret(hh, 120)
                if r is not None:
                    p.append((r, s))
        p.sort(reverse=True)
        return {s: peso for r, s in p[:n]}
    return f


def mk_dual(ma_giorni, giorni, n=N_POS, peso=PESO):
    """Doppio filtro: forte in classifica E sopra la propria media."""
    def f(h, d, eq, uni):
        p = []
        for s in uni:
            hh = h.get(s) or []
            m = _ma(hh, ma_giorni)
            r = _ret(hh, giorni)
            if m and r and r > 0 and hh[-1]["c"] > m and hh[-1]["c"] <= eq * peso:
                p.append((r, s))
        p.sort(reverse=True)
        return {s: peso for r, s in p[:n]}
    return f


def mk_reversion(giorni, n=N_POS, peso=PESO):
    """Compra i piu' scesi: l'opposto del momentum."""
    def f(h, d, eq, uni):
        p = []
        for s in uni:
            r = _ret(h.get(s) or [], giorni)
            if r is not None and h[s][-1]["c"] <= eq * peso:
                p.append((r, s))
        p.sort()
        return {s: peso for r, s in p[:n]}
    return f


def mk_lowvol(n=N_POS, peso=PESO):
    """I titoli piu' tranquilli: anomalia documentata da decenni."""
    def f(h, d, eq, uni):
        p = []
        for s in uni:
            v = _vol(h.get(s) or [], 120)
            if v and h[s][-1]["c"] <= eq * peso:
                p.append((v, s))
        p.sort()
        return {s: peso for v, s in p[:n]}
    return f


def mk_spy_trend(ma_giorni):
    """SPY, ma solo quando e' sopra la sua media. Il resto liquidi."""
    def f(h, d, eq, uni):
        hh = h.get("SPY") or []
        m = _ma(hh, ma_giorni)
        if m is None:
            return {}
        return {"SPY": 1.0} if hh[-1]["c"] > m else {}
    return f


def main() -> int:
    print("Scarico lo storico consolidato...")
    bars, dates, lookup = load()
    uni = [s for s in bars if s != "SPY"]
    meta = len(dates) // 2
    print("  %d titoli + SPY, %d giorni (%s -> %s)\n" % (
        len(uni), len(dates), dates[0], dates[-1]))

    fam = [
        ("comprare e tenere SPY",                f_spy,               ["SPY"], True),
        ("paniere equipesato dell'universo",     f_paniere,           uni,     True),
        ("SPY sopra la media a 200 giorni",      mk_spy_trend(200),   ["SPY"], False),
        ("momentum 6 mesi (3 titoli)",           mk_momentum(126),    uni,     True),
        ("momentum 12 mesi (3 titoli)",          mk_momentum(252),    uni,     True),
        ("momentum 1 mese (3 titoli)",           mk_momentum(21),     uni,     True),
        ("tendenza: sopra media 200gg",          mk_trend(200),       uni,     True),
        ("tendenza: sopra media 100gg",          mk_trend(100),       uni,     True),
        ("doppio filtro (media 200 + mom 6m)",   mk_dual(200, 126),   uni,     True),
        ("inversione: i piu' scesi in 1 mese",   mk_reversion(21),    uni,     True),
        ("bassa volatilita' (3 titoli)",         mk_lowvol(),         uni,     True),
    ]

    print("%-38s %9s %8s %8s %7s %9s" % ("FAMIGLIA", "RENDIM.", "ANNUO", "MAX DD", "OPER.", "FINALE"))
    print("-" * 86)
    salvate = []
    for nome, fn, u, mens in fam:
        r = simulate(bars, dates, lookup, fn, u, mens)
        salvate.append((nome, fn, u, mens))
        print("%-38s %+8.1f%% %+7.1f%% %7.1f%% %6d %9.0f$" % (
            nome, r["rend"], r["annuo"], r["maxdd"], r["ops"], r["finale"]))

    print("\n" + "=" * 86)
    print("PROVA DI ROBUSTEZZA — regge in ENTRAMBE le meta'?")
    print("(%s->%s | %s->%s)\n" % (dates[0], dates[meta], dates[meta], dates[-1]))
    print("%-38s %11s %11s  %s" % ("FAMIGLIA", "1a META'", "2a META'", "giudizio"))
    print("-" * 86)
    for nome, fn, u, mens in salvate:
        a = simulate(bars, dates[:meta], lookup, fn, u, mens)["rend"]
        b = simulate(bars, dates[meta:], lookup, fn, u, mens)["rend"]
        g = "positiva in entrambe" if a > 0 and b > 0 else (
            "negativa in entrambe" if a <= 0 and b <= 0 else "INCOERENTE")
        print("%-38s %+10.1f%% %+10.1f%%  %s" % (nome, a, b, g))
    return 0


if __name__ == "__main__":
    sys.exit(main())
