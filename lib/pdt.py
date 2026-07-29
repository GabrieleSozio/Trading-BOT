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
PDT_MAX_DAY_TRADES = 3            # in 5 giorni lavorativi


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

    Prudenza: si lascia sempre **un credito di margine**, perche' una posizione
    aperta oggi potrebbe chiudersi oggi stesso (take profit) e diventare essa
    stessa un day trade.
    """
    if not applies(equity):
        return True, "equity >= 25k: limite PDT non applicabile"
    used, detail = count_recent_day_trades(client)
    if used >= PDT_MAX_DAY_TRADES - 1:
        return False, (f"PDT: {used}/{PDT_MAX_DAY_TRADES} day trade negli ultimi 5 giorni "
                       f"({', '.join(detail)}): non apro per non sforare")
    return True, f"PDT: {used}/{PDT_MAX_DAY_TRADES} usati, margine sufficiente"
