"""
orb_backtest.py — prova della strategia "prima candela" (opening range breakout).

Riproduce meccanicamente la regola vista nel video:
  1. si segna massimo e minimo della prima candela da 5 minuti (9:30-9:35 New York)
  2. si aspetta la chiusura di una candela oltre il livello (la "candela d'impulso")
  3. si aspetta il RITORNO sul livello rotto — e' il filtro su cui l'autore insiste
  4. si entra alla conferma, con stop sotto la candela d'impulso
  5. obiettivo a 2 volte il rischio, e comunque tutto chiuso entro le 11:00

Limite dichiarato: la regola originale ha una parte DISCREZIONALE ("aspetto che i
venditori si facciano vedere", "vedo debolezza sul ritorno"). Non e' codificabile.
Qui la conferma e' meccanica: la candela del ritorno deve richiudere nella
direzione della rottura. Se la versione meccanica non funziona, resta possibile
che il valore stesse proprio nel giudizio umano che non possiamo riprodurre.

Regole di prudenza, come sempre:
  * dentro la giornata si assume il PEGGIO: se una candela tocca sia lo stop sia
    l'obiettivo, si considera colpito prima lo stop;
  * costi pagati su entrambi i lati;
  * risultati misurati in FATTORI DI RISCHIO, non in percentuale;
  * confronto separato fra operazioni al rialzo e al ribasso, perche' la nostra
    fascia micro non puo' vendere allo scoperto.
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
COST = 0.0005          # spread per lato su titoli liquidi
APERTURA = dt.time(9, 30)
FINE_RANGE = dt.time(9, 35)
CHIUSURA = dt.time(11, 0)
TARGET_R = 2.0


def scarica(simbolo: str, giorni: int) -> dict[str, list]:
    """Barre da un minuto raggruppate per giornata di borsa (solo 9:30-11:00)."""
    cli = AlpacaClient(max_consecutive_errors=9)
    inizio = (dt.date.today() - dt.timedelta(days=giorni)).isoformat()
    grezze = cli.bars([simbolo], "1Min", inizio, feed="sip", limit=10000).get(simbolo, [])
    per_giorno: dict[str, list] = defaultdict(list)
    for b in grezze:
        t = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        if APERTURA <= t.time() <= CHIUSURA:
            b = dict(b)
            b["et"] = t
            per_giorno[t.date().isoformat()].append(b)
    return {g: sorted(v, key=lambda x: x["et"]) for g, v in per_giorno.items() if len(v) > 60}


def giornata(barre: list, consenti_short: bool, stop_mode: str = "impulso") -> dict | None:
    """Applica la regola a una singola giornata. Ritorna l'operazione o None."""
    apertura = [b for b in barre if b["et"].time() < FINE_RANGE]
    dopo = [b for b in barre if b["et"].time() >= FINE_RANGE]
    if len(apertura) < 3 or len(dopo) < 10:
        return None
    alto = max(b["h"] for b in apertura)
    basso = min(b["l"] for b in apertura)

    rotto = None          # "su" | "giu"
    impulso = None        # candela che ha rotto
    for i, b in enumerate(dopo):
        # --- fase 1: rottura confermata da una chiusura oltre il livello ---
        if rotto is None:
            if b["c"] > alto:
                rotto, impulso = "su", b
            elif b["c"] < basso and consenti_short:
                rotto, impulso = "giu", b
            continue

        # --- fase 2: il prezzo torna sul livello rotto ---
        livello = alto if rotto == "su" else basso
        tocca = b["l"] <= livello if rotto == "su" else b["h"] >= livello
        if not tocca:
            continue
        # conferma meccanica: la candela del ritorno richiude nella direzione
        conferma = b["c"] > livello if rotto == "su" else b["c"] < livello
        if not conferma:
            continue

        entrata = b["c"] * (1 + COST if rotto == "su" else 1 - COST)
        if stop_mode == "livello":
            # come nell'esempio reale del video: stop al ritorno sotto il livello
            # della prima candela, non sotto la candela d'impulso
            stop = basso if rotto == "su" else alto
            if rotto == "su" and stop >= entrata: stop = min(impulso["l"], alto)
            if rotto == "giu" and stop <= entrata: stop = max(impulso["h"], basso)
        elif stop_mode == "range":
            stop = alto if rotto == "su" else basso     # il livello rotto stesso
        else:
            stop = impulso["l"] if rotto == "su" else impulso["h"]
        rischio = abs(entrata - stop)
        if rischio <= 0:
            return None
        obiettivo = (entrata + TARGET_R * rischio if rotto == "su"
                     else entrata - TARGET_R * rischio)

        # --- fase 3: si segue l'operazione fino alle 11:00 ---
        for x in dopo[i + 1:]:
            colpito_stop = x["l"] <= stop if rotto == "su" else x["h"] >= stop
            colpito_tp = x["h"] >= obiettivo if rotto == "su" else x["l"] <= obiettivo
            if colpito_stop:            # prudenza: lo stop viene prima
                return {"dir": rotto, "r": -1.0, "esito": "stop", "ora": x["et"].strftime("%H:%M")}
            if colpito_tp:
                return {"dir": rotto, "r": TARGET_R - 2 * COST * entrata / rischio,
                        "esito": "target", "ora": x["et"].strftime("%H:%M")}
        ultimo = dopo[-1]["c"] * (1 - COST if rotto == "su" else 1 + COST)
        r = ((ultimo - entrata) / rischio) if rotto == "su" else ((entrata - ultimo) / rischio)
        return {"dir": rotto, "r": r, "esito": "scadenza 11:00", "ora": "11:00"}
    return None


def prova(simbolo: str, giorni: int, consenti_short: bool, stop_mode: str = "impulso") -> dict:
    dati = scarica(simbolo, giorni)
    ops = []
    for g in sorted(dati):
        t = giornata(dati[g], consenti_short, stop_mode)
        if t:
            t["giorno"] = g
            ops.append(t)
    if not ops:
        return {"simbolo": simbolo, "giorni": len(dati), "n": 0}
    rs = [t["r"] for t in ops]
    vinc = [r for r in rs if r > 0]
    return {
        "simbolo": simbolo,
        "giorni": len(dati),
        "n": len(ops),
        "quota_giorni_con_operazione": round(len(ops) / len(dati) * 100, 1),
        "win_rate": round(len(vinc) / len(rs) * 100, 1),
        "R_medio": round(sum(rs) / len(rs), 3),
        "R_totale": round(sum(rs), 1),
        "esiti": {k: sum(1 for t in ops if t["esito"] == k)
                  for k in ("target", "stop", "scadenza 11:00")},
        "ops": ops,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simboli", default="SPY")
    ap.add_argument("--giorni", type=int, default=750)
    ap.add_argument("--short", action="store_true", help="ammetti anche le vendite allo scoperto")
    a = ap.parse_args()

    print("Regola: prima candela 5 min -> rottura -> RITORNO -> stop sotto l'impulso -> 2R")
    print("Ipotesi prudente: a parita' di candela, lo stop scatta prima dell'obiettivo.")
    print("Operazioni al ribasso: %s\n" % ("ammesse" if a.short else "ESCLUSE (come la fascia micro)"))

    tutte = []
    print("%-6s %7s %6s %9s %8s %9s %9s" % (
        "TIT.", "GIORNI", "OPER.", "GG CON OP.", "VINC.%", "R MEDIO", "R TOTALE"))
    print("-" * 66)
    for s in a.simboli.split(","):
        r = prova(s.strip(), a.giorni, a.short)
        if not r["n"]:
            print("%-6s %7d %6d   nessuna operazione" % (s, r["giorni"], 0)); continue
        tutte += r["ops"]
        print("%-6s %7d %6d %8.1f%% %7.1f%% %+8.3f %+9.1f" % (
            r["simbolo"], r["giorni"], r["n"], r["quota_giorni_con_operazione"],
            r["win_rate"], r["R_medio"], r["R_totale"]))
        print("        esiti: %s" % r["esiti"])

    if len(a.simboli.split(",")) > 1 and tutte:
        rs = [t["r"] for t in tutte]
        v = [x for x in rs if x > 0]
        print("-" * 66)
        print("%-6s %7s %6d %9s %7.1f%% %+8.3f %+9.1f" % (
            "TUTTI", "", len(rs), "", len(v)/len(rs)*100, sum(rs)/len(rs), sum(rs)))

    if tutte:
        meta = len(tutte) // 2
        for nome, g in (("prima meta'", tutte[:meta]), ("seconda meta'", tutte[meta:])):
            rs = [t["r"] for t in g]
            if rs:
                v = [x for x in rs if x > 0]
                print("  %-14s %3d oper. | %.0f%% vincenti | R medio %+.3f" % (
                    nome, len(rs), len(v)/len(rs)*100, sum(rs)/len(rs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
