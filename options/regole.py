"""
regole.py — regole di calendario e di prudenza della DIVISIONE OPZIONI.

Raccoglie tre decisioni prese il 2026-09-15 dopo la perdita su INTC:

  NIENTE OPZIONI TENUTE A MERCATO CHIUSO PIU' DI UNA NOTTE
  Lo stop sul titolo e' un controllo del nostro programma: guarda ogni 15
  minuti e solo a borsa aperta. Nel weekend non c'e' nessuno. INTC ha chiuso
  venerdi' a 102,94 e aperto lunedi' a 95,82, gia' sotto lo stop: il contratto
  e' uscito a -68% invece del -50% previsto. Prima di un weekend o di una
  festivita' si chiude tutto, e in quella sessione non si aprono posizioni
  swing (andrebbero chiuse in giornata, consumando un credito PDT).

  ORARI DAL CALENDARIO DELLA BORSA, NON DALL'OROLOGIO ITALIANO
  La chiusura intraday era fissata alle 21:40 di Roma. Ma per una settimana
  tra fine ottobre e inizio novembre, e per tre settimane a marzo, l'Europa e
  gli Stati Uniti cambiano ora in date diverse e New York chiude alle 21:00
  italiane: alle 21:40 la borsa sarebbe gia' chiusa e la posizione "intraday"
  resterebbe aperta tutta la notte. Anche le mezze giornate (il venerdi' dopo
  il Ringraziamento chiude alle 13:00) sfuggivano. Il calendario del broker
  conosce tutti questi casi.

  PAUSA SULLO STESSO TITOLO DOPO UNA PERDITA
  SLV e' stato venduto in perdita e ricomprato 75 minuti dopo; quella seconda
  operazione ha perso altri 150$.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")


def stato_sessione(cli, ora: dt.datetime | None = None) -> dict:
    """Dove siamo nella sessione di oggi, secondo il calendario della borsa.

    Ritorna:
      aperta               True se la borsa e' aperta adesso
      minuti_alla_chiusura minuti che mancano alla campana (None se chiusa)
      chiusura_lunga       True se dopo oggi la borsa resta chiusa piu' di una
                           notte (weekend, festivita')
      chiude_alle          orario di chiusura di New York, per i log
    """
    ora = (ora or dt.datetime.now(dt.timezone.utc)).astimezone(NEW_YORK)
    oggi = ora.date()
    cal = cli.calendar(oggi.isoformat(), (oggi + dt.timedelta(days=10)).isoformat())
    giorni = sorted(cal, key=lambda c: c["date"])

    vuoto = {"aperta": False, "minuti_alla_chiusura": None,
             "chiusura_lunga": False, "chiude_alle": None}
    if not giorni or giorni[0]["date"] != oggi.isoformat():
        return vuoto                       # oggi la borsa non apre

    g = giorni[0]
    apre = dt.datetime.combine(oggi, dt.time.fromisoformat(g["open"]), NEW_YORK)
    chiude = dt.datetime.combine(oggi, dt.time.fromisoformat(g["close"]), NEW_YORK)

    lunga = True                           # senza sessioni note davanti: prudenza
    if len(giorni) > 1:
        prossimo = dt.date.fromisoformat(giorni[1]["date"])
        lunga = (prossimo - oggi).days > 1

    aperta = apre <= ora < chiude
    return {
        "aperta": aperta,
        "minuti_alla_chiusura": (chiude - ora).total_seconds() / 60 if aperta else None,
        "chiusura_lunga": lunga,
        "chiude_alle": g["close"],
    }


def in_chiusura(cfg: dict, sessione: dict) -> bool:
    """Siamo nella finestra finale in cui si chiude e non si apre nulla?"""
    m = sessione.get("minuti_alla_chiusura")
    return m is not None and m <= float(cfg["session"]["close_minutes_before_close"])


def uscita_a_mercato(cfg: dict, sessione: dict) -> bool:
    """Ultimo tentativo utile prima della campana: meglio pagare lo spread che
    tenere la posizione a mercato chiuso."""
    m = sessione.get("minuti_alla_chiusura")
    return m is not None and m <= float(cfg["session"]["market_order_minutes_before_close"])


def in_raffreddamento(cfg: dict, st: dict, ticker: str,
                      ora: dt.datetime | None = None) -> tuple[bool, str]:
    """Il titolo e' stato chiuso in perdita da poco? Se si', per ora non si ricompra."""
    giorni = float(cfg["guardrails"].get("reentry_cooldown_days") or 0)
    if giorni <= 0 or not ticker:
        return False, ""
    ora = ora or dt.datetime.now(dt.timezone.utc)
    for t in reversed(st.get("closed_trades") or []):
        if t.get("ticker") != ticker or float(t.get("pl_usd") or 0) >= 0:
            continue
        try:
            chiusa = dt.datetime.fromisoformat(t["closed_at"])
        except (KeyError, ValueError):
            continue
        trascorsi = (ora - chiusa).total_seconds() / 86400
        if trascorsi < giorni:
            return True, ("chiuso in perdita %.1f giorni fa ($%+.0f), pausa di %.0f giorni"
                          % (trascorsi, float(t["pl_usd"]), giorni))
        return False, ""                  # l'ultima perdita e' gia' lontana
    return False, ""
