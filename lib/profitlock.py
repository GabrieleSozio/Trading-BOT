"""
profitlock.py — blocco del profitto a livello di CONTO.

Le protezioni che avevamo erano tutte per posizione: stop, trailing, tempo.
Nessuna guardava il totale. Cosi' il conto opzioni e' arrivato a 829 dollari ed
e' tornato a 694 senza che nulla intervenisse — il picco era la somma di tre
posizioni, e nessuna singola aveva toccato la propria soglia.

Questo modulo aggiunge la regola mancante: quando l'equity supera la base di un
importo deciso, si LIQUIDA TUTTO e quel guadagno diventa la nuova base. Da li'
si riparte a contare.

Serve un obiettivo preciso: incassi frequenti e certi invece di guadagni grandi
e sospesi. Il costo e' dichiarato — se una posizione sarebbe andata molto oltre,
quel resto non lo si prende. E' il prezzo della certezza, non un difetto.

La liquidazione puo' richiedere piu' giri: sulle opzioni un limite puo' non
riempirsi, sulle cripto va prima tolto lo stop depositato. Per questo esiste una
FASE di incasso: finche' dura non si apre nulla di nuovo, e la base si aggiorna
solo quando il conto e' davvero piatto. Aggiornarla prima farebbe ripartire il
conteggio da un valore che comprende posizioni ancora aperte.
"""
from __future__ import annotations

import logging

log = logging.getLogger("profitlock")


def _cfg(cfg: dict) -> dict:
    return cfg.get("profit_lock") or {}


def attivo(cfg: dict) -> bool:
    return bool(_cfg(cfg).get("enabled"))


def base(cfg: dict, st: dict) -> float:
    """Base corrente da cui si misura il guadagno. Parte dal capitale iniziale
    e sale a ogni incasso."""
    b = st.get("profit_lock_base")
    if b is None:
        b = float(cfg.get("capital", {}).get("initial_usd") or 0)
        st["profit_lock_base"] = b
    return float(b)


def da_incassare(cfg: dict, st: dict, equity: float) -> tuple[bool, str]:
    """Va liquidato tutto? Ritorna (si/no, motivo leggibile).

    Se una liquidazione e' gia' in corso continua finche' non e' completa: un
    incasso a meta' lascerebbe posizioni aperte con la base gia' spostata.
    """
    if not attivo(cfg):
        return False, ""
    b = base(cfg, st)
    soglia = float(_cfg(cfg).get("threshold_usd") or 0)
    if st.get("incasso_in_corso"):
        return True, "incasso in corso: chiudo le posizioni rimaste"
    if soglia > 0 and equity >= b + soglia:
        st["incasso_in_corso"] = True
        return True, (f"soglia raggiunta: equity ${equity:.2f} contro base "
                      f"${b:.2f} + ${soglia:.0f}")
    return False, ""


def completa(cfg: dict, st: dict, equity: float, posizioni_aperte: int) -> str | None:
    """Chiude il ciclo quando il conto e' davvero piatto: sposta la base e
    registra quanto e' stato messo da parte. Ritorna il messaggio, o None."""
    if not st.get("incasso_in_corso") or posizioni_aperte > 0:
        return None
    vecchia = base(cfg, st)
    incassato = equity - vecchia
    st["profit_lock_base"] = round(equity, 2)
    st["incasso_in_corso"] = False
    st["incassato_totale"] = round(float(st.get("incassato_totale") or 0) + incassato, 2)
    st.setdefault("incassi", []).append(
        {"da": round(vecchia, 2), "a": round(equity, 2), "importo": round(incassato, 2)})
    st["incassi"] = st["incassi"][-50:]
    return (f"INCASSATO ${incassato:+.2f}: la base passa da ${vecchia:.2f} a "
            f"${equity:.2f} (totale messo da parte ${st['incassato_totale']:+.2f})")


def descrivi(cfg: dict, st: dict, equity: float) -> str:
    """Riga di stato per i log."""
    if not attivo(cfg):
        return "blocco del profitto: disattivato"
    b = base(cfg, st)
    soglia = float(_cfg(cfg).get("threshold_usd") or 0)
    manca = (b + soglia) - equity
    return ("blocco profitto: base $%.2f, incasso a $%.2f, mancano $%.2f "
            "(gia' messi da parte $%.2f)" % (
                b, b + soglia, manca, float(st.get("incassato_totale") or 0)))
