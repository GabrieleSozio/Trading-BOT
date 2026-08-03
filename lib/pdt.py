"""
pdt.py — contatore Pattern Day Trader.

Perche' serve. Un "day trade" e' comprare e vendere lo stesso titolo nella stessa
giornata di borsa. La normativa USA (FINRA) consente a un conto sotto i 25.000 USD
al massimo **3 day trade ogni 5 giorni lavorativi**: al superamento il conto viene
marcato come Pattern Day Trader e il day trading gli viene bloccato.

Il bot opera in swing proprio per evitarlo, MA un day trade puo' capitare comunque:
se una posizione aperta stamattina colpisce il take profit nel pomeriggio, quello e'
un round-trip intragiornaliero a tutti gli effetti. Questo modulo li conta e permette
alla Routine 04 di fermarsi PRIMA di sforare.

Alpaca espone `daytrade_count` sui conti live; sul paper e' assente, quindi lo
ricalcoliamo dai fill.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict

log = logging.getLogger("pdt")

PDT_EQUITY_THRESHOLD = 25_000.0   # sotto questa soglia si applica il limite
# La regola FINRA marca come Pattern Day Trader chi esegue QUATTRO o piu' day trade
# in 5 giorni lavorativi: tre sono quindi consentiti senza conseguenze.
PDT_FLAG_AT = 4
PDT_MAX_SAFE = PDT_FLAG_AT - 1    # 3 day trade tollerati nella finestra


def applies(equity: float) -> bool:
    """Il limite PDT vale solo sotto i 25.000 USD di equity."""
    return equity < PDT_EQUITY_THRESHOLD


def count_recent_day_trades(client, days_back: int = 7) -> tuple[int, list]:
    """Day trade nelle ultime ~5 sessioni: (numero, elenco 'TICKER@data').

    Un (simbolo, giorno) conta come day trade se nello stesso giorno ci sono
    fill sia in acquisto sia in vendita.
    """
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_back)).isoformat()
    try:
        fills = client.activities("FILL", after=since)
    except Exception as e:  # noqa: BLE001 — in caso di dubbio non blocchiamo il bot
        log.warning("Impossibile leggere le attivita' per il conteggio PDT: %s", e)
        return 0, []

    sides = defaultdict(set)
    for f in fills:
        sym, day, side = f.get("symbol"), (f.get("transaction_time") or "")[:10], f.get("side", "")
        if not sym or not day:
            continue
        sides[(sym, day)].add("buy" if side.startswith("buy") else "sell")

    trades = sorted(f"{sym}@{day}" for (sym, day), s in sides.items() if len(s) >= 2)
    return len(trades), trades


def can_open_new_position(client, equity: float) -> tuple[bool, str]:
    """Si puo' aprire una nuova posizione senza rischiare di sforare il PDT?

    Il caso peggiore per una nuova posizione e' che si chiuda in giornata (take
    profit colpito subito), diventando essa stessa un day trade. Quindi si blocca
    quando i day trade gia' usati sono 3: un altro sarebbe il QUARTO, cioe' quello
    che fa scattare la marcatura. Con 2 usati si puo' ancora aprire, perche' al
    massimo si arriva a 3, che e' consentito.
    """
    if not applies(equity):
        return True, "equity >= 25k: limite PDT non applicabile"
    used, detail = count_recent_day_trades(client)
    if used >= PDT_MAX_SAFE:
        return False, (f"PDT: {used}/{PDT_MAX_SAFE} day trade negli ultimi 5 giorni "
                       f"({', '.join(detail)}): un altro sarebbe il {PDT_FLAG_AT}o e "
                       f"farebbe scattare la marcatura. Non apro.")
    return True, f"PDT: {used}/{PDT_MAX_SAFE} usati, margine sufficiente"
