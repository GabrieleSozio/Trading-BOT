"""
quick_flip.py — simulazione meccanica del "quick flip scalper".

Il primo test (liquidity_reversal.py) misurava solo quanto spesso il prezzo
attraversa il range di apertura. Ha un difetto: un box piu' largo ha il
bersaglio piu' lontano, quindi una parte della differenza trovata e' pura
geometria, non previsione. Qui si simula l'operazione COMPLETA e si misura in
R — utile/perdita diviso il rischio allo stop — che e' la stessa unita' con cui
misuriamo le divisioni vere. Cosi' la larghezza del box smette di falsare il
confronto: entra sia nel bersaglio sia nel rischio.

REGOLE, tradotte dal video il piu' fedelmente possibile:
  1. Box = massimo/minimo dei primi 15 minuti (9:30-9:45 ET), esteso in avanti.
  2. Filtro "candela di manipolazione": ampiezza del box >= X% dell'ATR a 14
     giorni (il video dice 25%).
  3. Il prezzo deve USCIRE dal box nella stessa direzione della candela di
     apertura — e' il movimento che il video chiama manipolazione.
  4. Ingresso quando il prezzo RIENTRA nel box: e' la versione codificabile del
     "martello / engulfing fuori dal box". Il pattern esatto e' discrezionale,
     il rientro no.
  5. Stop oltre l'estremo raggiunto fuori dal box (la "coda").
  6. Bersaglio: il lato opposto del box.
  7. Ingresso entro 90 minuti dall'apertura; uscita entro la chiusura.

Una sola operazione al giorno: e' uno scalp, non un sistema che si accumula.

VARIANTI PROVATE (dichiarate per intero, per non ingannarsi da soli):
  A) la regola fedele, divisa tra giornate a candela ampia e normale;
  B) la soglia sull'ATR a 0.25 / 0.50 / 0.75 / 1.00, per vedere se filtra
     qualcosa quando finalmente filtra davvero.
Nessun'altra. Ogni variante in piu' e' un'occasione di trovare per caso.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.alpaca_rest import AlpacaClient  # noqa: E402

ET = ZoneInfo("America/New_York")
APERTURA = dt.time(9, 30)
FINE_BOX = dt.time(9, 45)
FINE_INGRESSI = dt.time(11, 0)   # 90 minuti dall'apertura
CHIUSURA = dt.time(15, 55)


def scarica(simbolo: str, giorni: int):
    cli = AlpacaClient(max_consecutive_errors=9)
    inizio = (dt.date.today() - dt.timedelta(days=giorni)).isoformat()

    minuti = cli.bars([simbolo], "1Min", inizio, feed="sip", limit=10000).get(simbolo, [])
    per_giorno: dict[str, list] = defaultdict(list)
    for b in minuti:
        t = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        if APERTURA <= t.time() <= CHIUSURA:
            b = dict(b)
            b["et"] = t
            per_giorno[t.date().isoformat()].append(b)
    per_giorno = {g: sorted(v, key=lambda x: x["et"])
                  for g, v in per_giorno.items() if len(v) > 200}

    giorni_b = cli.bars([simbolo], "1Day", inizio, feed="sip", limit=2000).get(simbolo, [])
    giorni_b.sort(key=lambda b: b["t"])
    atr = {}
    for i in range(14, len(giorni_b)):
        finestra = giorni_b[i - 14:i]        # solo giorni precedenti
        atr[giorni_b[i]["t"][:10]] = sum(x["h"] - x["l"] for x in finestra) / 14
    return per_giorno, atr


def simula(barre: list, atr: float) -> dict | None:
    """Una giornata. Ritorna l'operazione trovata, o None se non c'e' il setup."""
    box_b = [b for b in barre if b["et"].time() < FINE_BOX]
    resto = [b for b in barre if b["et"].time() >= FINE_BOX]
    if len(box_b) < 10 or len(resto) < 60 or not atr:
        return None

    alto = max(b["h"] for b in box_b)
    basso = min(b["l"] for b in box_b)
    if alto <= basso:
        return None
    quota_atr = (alto - basso) / atr

    su = box_b[-1]["c"] >= box_b[0]["o"]     # direzione della candela di apertura

    # --- fase 1: uscita dal box nella direzione della candela di apertura ----
    uscito = False
    estremo = None
    ingresso = None
    i_ingresso = None
    for i, b in enumerate(resto):
        if b["et"].time() > FINE_INGRESSI:
            break
        if su:
            if b["h"] > alto:
                uscito = True
                estremo = b["h"] if estremo is None else max(estremo, b["h"])
            elif uscito and b["c"] < alto:       # rientro nel box: si vende
                ingresso, i_ingresso = b["c"], i
                break
        else:
            if b["l"] < basso:
                uscito = True
                estremo = b["l"] if estremo is None else min(estremo, b["l"])
            elif uscito and b["c"] > basso:      # rientro nel box: si compra
                ingresso, i_ingresso = b["c"], i
                break
    if ingresso is None or estremo is None:
        return None

    # --- fase 2: l'operazione ------------------------------------------------
    # short se la candela di apertura era rialzista, long se ribassista.
    stop = estremo
    bersaglio = basso if su else alto
    rischio = abs(stop - ingresso)
    if rischio <= 0:
        return None
    # Se il bersaglio e' dalla parte sbagliata dello stop il setup non ha senso.
    premio = abs(bersaglio - ingresso)
    if premio <= 0:
        return None

    esito, uscita = "tempo", resto[-1]["c"]
    for b in resto[i_ingresso + 1:]:
        if su:                                   # posizione corta
            if b["h"] >= stop:
                esito, uscita = "stop", stop
                break
            if b["l"] <= bersaglio:
                esito, uscita = "bersaglio", bersaglio
                break
        else:                                    # posizione lunga
            if b["l"] <= stop:
                esito, uscita = "stop", stop
                break
            if b["h"] >= bersaglio:
                esito, uscita = "bersaglio", bersaglio
                break

    pnl = (ingresso - uscita) if su else (uscita - ingresso)
    return {
        "quota_atr": quota_atr,
        "R": pnl / rischio,
        "rr": premio / rischio,
        "esito": esito,
        "rischio_pct": rischio / ingresso * 100,
    }


def riepiloga(nome: str, ops: list) -> None:
    if not ops:
        print("%-22s nessuna operazione" % nome)
        return
    r = [o["R"] for o in ops]
    vinte = [x for x in r if x > 0]
    centrati = sum(1 for o in ops if o["esito"] == "bersaglio")
    print("%-22s %5d op | R medio %+6.2f | vinte %5.1f%% | bersaglio %5.1f%% "
          "| R/R medio %.2f | rischio %.2f%%" % (
              nome, len(ops), mean(r), len(vinte) / len(r) * 100,
              centrati / len(ops) * 100, mean(o["rr"] for o in ops),
              mean(o["rischio_pct"] for o in ops)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simboli", default="SPY,QQQ,NVDA,AAPL,TSLA")
    ap.add_argument("--giorni", type=int, default=700)
    a = ap.parse_args()

    print("QUICK FLIP SCALPER — simulazione meccanica")
    print("Fade dell'apertura: si esce dal box, si rientra, si punta al lato opposto.")
    print("R = utile/perdita diviso il rischio allo stop. Costi NON inclusi.\n")

    tutte: list = []
    for s in a.simboli.split(","):
        s = s.strip()
        try:
            giorni, atr = scarica(s, a.giorni)
        except Exception as e:  # noqa: BLE001
            print("%-6s errore: %s" % (s, str(e)[:60]))
            continue
        ops = []
        for g in sorted(giorni):
            o = simula(giorni[g], atr.get(g))
            if o:
                o["tit"] = s
                ops.append(o)
        riepiloga(s, ops)
        tutte.extend(ops)

    print("-" * 100)
    riepiloga("TUTTI", tutte)
    if not tutte:
        return 0

    print("\nVARIANTE A — la soglia del video (25% dell'ATR):")
    riepiloga("  candela ampia", [o for o in tutte if o["quota_atr"] >= 0.25])
    riepiloga("  candela normale", [o for o in tutte if o["quota_atr"] < 0.25])

    print("\nVARIANTE B — la soglia spostata, per vedere se filtra qualcosa:")
    for s in (0.25, 0.50, 0.75, 1.00):
        sel = [o for o in tutte if o["quota_atr"] >= s]
        riepiloga("  ATR >= %.2f" % s, sel)

    print("\nNota: senza costi. Sulle azioni lo scarto denaro-lettera vale circa")
    print("0.05%%, sulle opzioni dall'1%% all'8%% — su un rischio medio del %.2f%%"
          % mean(o["rischio_pct"] for o in tutte))
    print("il costo in opzioni si mangia da solo una fetta grande del risultato.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
