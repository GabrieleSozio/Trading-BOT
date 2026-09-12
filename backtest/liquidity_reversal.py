"""
liquidity_reversal.py — prova dell'affermazione centrale del "quick flip scalper".

La tesi del video: quando la prima candela da 15 minuti e' AMPIA (almeno il 25%
dell'escursione media giornaliera degli ultimi 14 giorni), quel movimento e'
"manipolazione" e il prezzo tende a TORNARE dentro il range di apertura.

Qui non si prova la strategia completa: si prova solo il nucleo, che e' l'unica
parte falsificabile. I pattern a candela (martello, engulfing) servono a
scegliere il momento d'ingresso e sono la parte discrezionale — se il nucleo
non regge, il momento d'ingresso non conta.

IL CONFRONTO E' LA COSA IMPORTANTE. Non basta sapere quante volte il prezzo
rientra dopo una candela ampia: bisogna sapere se rientra PIU' SPESSO che dopo
una candela normale. Se la percentuale e' la stessa, la "manipolazione" non
aggiunge nulla e stiamo solo misurando quanto i prezzi oscillano.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.alpaca_rest import AlpacaClient  # noqa: E402

ET = ZoneInfo("America/New_York")
APERTURA = dt.time(9, 30)
FINE_RANGE = dt.time(9, 45)      # prima candela da 15 minuti
FINE_FINESTRA = dt.time(11, 0)   # 90 minuti dall'apertura


def scarica(simbolo: str, giorni: int):
    """Barre da un minuto della finestra 9:30-11:00, piu' l'ATR giornaliero."""
    cli = AlpacaClient(max_consecutive_errors=9)
    inizio = (dt.date.today() - dt.timedelta(days=giorni)).isoformat()

    minuti = cli.bars([simbolo], "1Min", inizio, feed="sip", limit=10000).get(simbolo, [])
    per_giorno: dict[str, list] = defaultdict(list)
    for b in minuti:
        t = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        if APERTURA <= t.time() <= FINE_FINESTRA:
            b = dict(b)
            b["et"] = t
            per_giorno[t.date().isoformat()].append(b)
    per_giorno = {g: sorted(v, key=lambda x: x["et"])
                  for g, v in per_giorno.items() if len(v) > 60}

    giorni_b = cli.bars([simbolo], "1Day", inizio, feed="sip", limit=2000).get(simbolo, [])
    giorni_b.sort(key=lambda b: b["t"])
    atr = {}
    for i in range(14, len(giorni_b)):
        finestra = giorni_b[i - 14:i]          # SOLO giorni precedenti: niente futuro
        atr[giorni_b[i]["t"][:10]] = sum(x["h"] - x["l"] for x in finestra) / 14
    return per_giorno, atr


def analizza(barre: list, atr: float, soglia: float) -> dict | None:
    """Un giorno: la candela di apertura e cosa fa il prezzo nei 75 minuti dopo."""
    apertura = [b for b in barre if b["et"].time() < FINE_RANGE]
    dopo = [b for b in barre if b["et"].time() >= FINE_RANGE]
    if len(apertura) < 10 or len(dopo) < 30 or not atr:
        return None

    alto = max(b["h"] for b in apertura)
    basso = min(b["l"] for b in apertura)
    ampiezza = alto - basso
    if ampiezza <= 0:
        return None
    quota_atr = ampiezza / atr

    # direzione della candela di apertura
    su = apertura[-1]["c"] >= apertura[0]["o"]
    # il bersaglio della tesi: il lato OPPOSTO del range
    bersaglio = basso if su else alto

    rientrato = False
    esteso = False
    for b in dopo:
        if (su and b["h"] > alto) or (not su and b["l"] < basso):
            esteso = True                      # il movimento e' proseguito
        if (su and b["l"] <= bersaglio) or (not su and b["h"] >= bersaglio):
            rientrato = True
            break
    return {
        "quota_atr": quota_atr,
        "ampia": quota_atr >= soglia,
        "su": su,
        "rientrato": rientrato,
        "esteso_prima": esteso and not rientrato,
        "ampiezza_pct": ampiezza / apertura[-1]["c"] * 100,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simboli", default="SPY,QQQ,NVDA,AAPL,TSLA")
    ap.add_argument("--giorni", type=int, default=700)
    ap.add_argument("--soglia", type=float, default=0.25)
    a = ap.parse_args()

    print("TESI DEL VIDEO: dopo una prima candela da 15 minuti ampia (>=%.0f%% "
          "dell'ATR)," % (a.soglia * 100))
    print("il prezzo torna al lato OPPOSTO del range di apertura entro 90 minuti.\n")
    print("Il confronto che conta e' con le giornate a candela NORMALE.\n")

    print("%-6s %7s | %9s %9s | %9s %9s | %s" % (
        "TIT.", "GIORNI", "AMPIE", "rientra%", "NORMALI", "rientra%", "differenza"))
    print("-" * 82)
    tot_a = tot_ar = tot_n = tot_nr = 0
    for s in a.simboli.split(","):
        s = s.strip()
        try:
            giorni, atr = scarica(s, a.giorni)
        except Exception as e:  # noqa: BLE001
            print("%-6s errore: %s" % (s, str(e)[:50]))
            continue
        ampie, ampie_r, norm, norm_r = 0, 0, 0, 0
        for g in sorted(giorni):
            r = analizza(giorni[g], atr.get(g), a.soglia)
            if not r:
                continue
            if r["ampia"]:
                ampie += 1
                ampie_r += r["rientrato"]
            else:
                norm += 1
                norm_r += r["rientrato"]
        if not ampie or not norm:
            print("%-6s dati insufficienti (ampie=%d normali=%d)" % (s, ampie, norm))
            continue
        pa, pn = ampie_r / ampie * 100, norm_r / norm * 100
        tot_a += ampie; tot_ar += ampie_r; tot_n += norm; tot_nr += norm_r
        print("%-6s %7d | %9d %8.1f%% | %9d %8.1f%% | %+8.1f punti" % (
            s, ampie + norm, ampie, pa, norm, pn, pa - pn))

    if tot_a and tot_n:
        pa, pn = tot_ar / tot_a * 100, tot_nr / tot_n * 100
        print("-" * 82)
        print("%-6s %7d | %9d %8.1f%% | %9d %8.1f%% | %+8.1f punti" % (
            "TUTTI", tot_a + tot_n, tot_a, pa, tot_n, pn, pa - pn))
        print()
        if abs(pa - pn) < 5:
            print(">> Le due percentuali sono simili: la 'candela di manipolazione'")
            print("   NON prevede il rientro meglio di una candela qualsiasi.")
        elif pa > pn:
            print(">> Le candele ampie rientrano piu' spesso: la tesi ha un supporto.")
        else:
            print(">> Le candele ampie rientrano MENO spesso: la tesi e' rovesciata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
