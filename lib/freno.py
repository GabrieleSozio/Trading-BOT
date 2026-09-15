"""
freno.py — freno di emergenza con RIPARTENZA dopo una pausa.

Il freno blocca i nuovi ingressi quando il capitale operativo scende oltre una
certa quota dal suo massimo. Fino al 2026-09-15 non aveva una via d'uscita, ed
era un errore di progettazione: il conto puo' risalire solo facendo operazioni,
e il freno le vieta. Scattato una volta, restava tirato per sempre. E' successo
sul conto opzioni, fermo dall'11 settembre senza alcun modo di ripartire.

La regola nuova:

  1. il freno scatta come prima, e le posizioni aperte continuano a essere
     gestite fino all'uscita;
  2. quando il conto e' PIATTO (nessuna posizione) comincia una pausa;
  3. finita la pausa, il freno si riarma: il massimo di riferimento diventa il
     capitale rimasto, e da li' si riparte a contare.

Ripartire significa accettare il capitale piu' piccolo come nuova base. Non si
recupera nulla di cio' che e' stato perso: si smette solo di restare bloccati.
La pausa serve a non ricomprare nel pieno della stessa ondata che ha fatto
scattare il freno.

Gli eventi si registrano solo quando lo stato CAMBIA. Prima il freno annotava
un evento a ogni giro, e in tre giorni aveva spinto fuori dal registro tutto il
resto: gli ultimi 30 eventi del conto opzioni erano tutti "freno_emergenza".
"""
from __future__ import annotations

import datetime as dt


def valuta(guardrails: dict, st: dict, operativo: float, posizioni_aperte: int,
           ora: dt.datetime) -> dict:
    """Aggiorna lo stato del freno e dice se i nuovi ingressi sono bloccati.

    Ritorna un dizionario con:
      bloccato     True se non si deve aprire nulla di nuovo
      picco        massimo di riferimento corrente
      drawdown     distanza dal massimo, fra 0 e 1
      transizione  None, oppure "scattato" / "rientrato" / "riarmato"
      dettaglio    frase leggibile per i log
    """
    soglia = float(guardrails["max_drawdown_from_peak_pct"])
    pausa = float(guardrails.get("rearm_after_days") or 0)

    picco = max(float(st.get("peak_equity") or 0), operativo)
    st["peak_equity"] = round(picco, 2)
    dd = (picco - operativo) / picco if picco > 0 else 0.0
    era_attivo = bool(st.get("freno_attivo"))

    # --- sotto la soglia: tutto normale -----------------------------------
    if dd < soglia:
        st["freno_attivo"] = False
        st["freno_piatto_dal"] = None
        return {"bloccato": False, "picco": picco, "drawdown": dd,
                "transizione": "rientrato" if era_attivo else None,
                "dettaglio": ""}

    # --- oltre la soglia ------------------------------------------------
    st["freno_attivo"] = True
    transizione = None if era_attivo else "scattato"

    if posizioni_aperte > 0:
        # La pausa conta solo a conto piatto: finche' ci sono posizioni il
        # rischio e' ancora in corso e non ha senso misurare il riposo.
        st["freno_piatto_dal"] = None
        return {"bloccato": True, "picco": picco, "drawdown": dd,
                "transizione": transizione,
                "dettaglio": "posizioni ancora aperte: la pausa parte a conto piatto"}

    if pausa <= 0:
        return {"bloccato": True, "picco": picco, "drawdown": dd,
                "transizione": transizione,
                "dettaglio": "ripartenza automatica disattivata"}

    if not st.get("freno_piatto_dal"):
        st["freno_piatto_dal"] = ora.isoformat(timespec="seconds")

    dal = dt.datetime.fromisoformat(st["freno_piatto_dal"])
    trascorsi = (ora - dal).total_seconds() / 86400
    if trascorsi < pausa:
        return {"bloccato": True, "picco": picco, "drawdown": dd,
                "transizione": transizione,
                "dettaglio": "pausa: %.1f giorni su %.0f" % (trascorsi, pausa)}

    # --- pausa finita: si riparte dal capitale rimasto -------------------
    st.setdefault("riarmi", []).append({
        "at": ora.isoformat(timespec="seconds"),
        "picco_precedente": round(picco, 2),
        "nuova_base": round(operativo, 2),
        "drawdown_pct": round(dd * 100, 2),
    })
    st["riarmi"] = st["riarmi"][-50:]
    st["peak_equity"] = round(operativo, 2)
    st["freno_attivo"] = False
    st["freno_piatto_dal"] = None
    return {"bloccato": False, "picco": operativo, "drawdown": 0.0,
            "transizione": "riarmato",
            "dettaglio": "dopo %.1f giorni a conto piatto si riparte da $%.2f "
                         "(massimo precedente $%.2f, -%.1f%%)"
                         % (trascorsi, operativo, picco, dd * 100)}
