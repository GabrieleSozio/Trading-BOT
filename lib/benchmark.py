"""
benchmark.py — quanto abbiamo fatto IN PIU' del non fare niente.

Il rendimento da solo inganna. Il bot azioni ha reso +43% in due anni e
sembrava un buon risultato: il mercato nello stesso periodo ne aveva fatti
+72%. Stavamo misurando un successo che era in realta' una perdita relativa,
e ce ne siamo accorti solo con la prova su storico.

L'alpha e' la differenza fra quanto abbiamo guadagnato e quanto avremmo
guadagnato comprando l'indice e stando fermi. E' l'unico numero che giustifica
l'esistenza di un bot: se l'alpha e' negativo, la stessa somma parcheggiata su
un indice avrebbe reso di piu' con meno rischio e meno lavoro.

Riferimenti: SPY per le azioni americane, Bitcoin per le cripto (e' il metro
del settore: una moneta che sale meno di BTC sta di fatto perdendo).
"""
from __future__ import annotations

import datetime as dt
import logging

log = logging.getLogger("benchmark")

SPY = "SPY"
CRYPTO_BENCH = "BTC/USD"

_cache: dict[tuple, list] = {}


def _stock_bars(client, symbol: str, start: str, end: str | None) -> list[dict]:
    key = ("stock", symbol, start, end)
    if key not in _cache:
        _cache[key] = client.bars([symbol], "1Day", start, end=end,
                                  feed="sip", limit=2000).get(symbol, [])
    return _cache[key]


def _crypto_bars(client, symbol: str, start: str) -> list[dict]:
    key = ("crypto", symbol, start)
    if key not in _cache:
        _cache[key] = client.crypto_bars([symbol], start=start,
                                         timeframe="1D").get(symbol, [])
    return _cache[key]


def _pct_between(bars: list[dict], d0: str, d1: str) -> float | None:
    """Variazione dell'indice fra due date (chiusura a chiusura)."""
    if not bars:
        return None
    prima = [b for b in bars if b["t"][:10] <= d0]
    dopo = [b for b in bars if b["t"][:10] <= d1]
    if not prima or not dopo:
        return None
    a, b = prima[-1]["c"], dopo[-1]["c"]
    return (b / a - 1) * 100 if a else None


def stock_series(client, start: str, end: str | None = None) -> list[dict]:
    return _stock_bars(client, SPY, start, end)


def crypto_series(client, start: str) -> list[dict]:
    return _crypto_bars(client, CRYPTO_BENCH, start)


def add_alpha(trades: list[dict], bars: list[dict],
              key_in: str = "opened_at", key_out: str = "closed_at",
              key_pct: str = "pl_pct") -> list[dict]:
    """Aggiunge a ogni operazione il rendimento dell'indice nello STESSO periodo
    e la differenza. Confrontare con l'indice sull'intero anno sarebbe sbagliato:
    una posizione tenuta tre giorni va confrontata con quei tre giorni."""
    for t in trades:
        d0 = (t.get(key_in) or "")[:10]
        d1 = (t.get(key_out) or "")[:10]
        b = _pct_between(bars, d0, d1) if d0 and d1 else None
        t["benchmark_pct"] = round(b, 2) if b is not None else None
        t["alpha_pct"] = round(t[key_pct] - b, 2) if b is not None and t.get(key_pct) is not None else None
    return trades


def summarize_alpha(trades: list[dict]) -> dict:
    """Sintesi dell'alpha: quante operazioni hanno davvero battuto il mercato."""
    con = [t for t in trades if t.get("alpha_pct") is not None]
    if not con:
        return {}
    a = [t["alpha_pct"] for t in con]
    meglio = [x for x in a if x > 0]
    return {
        "n_confrontabili": len(con),
        "alpha_medio_pct": round(sum(a) / len(a), 2),
        "alpha_totale_pct": round(sum(a), 2),
        "quota_che_batte_il_mercato_pct": round(len(meglio) / len(con) * 100, 1),
        "migliore_pct": round(max(a), 2),
        "peggiore_pct": round(min(a), 2),
    }


def period_alpha(client, kind: str, start: str, strategy_pct: float) -> dict:
    """Alpha di periodo: rendimento della strategia contro quello dell'indice.

    `kind` e' 'stock' (SPY) o 'crypto' (BTC). `strategy_pct` e' il rendimento
    della strategia nello stesso arco di tempo.
    """
    oggi = dt.date.today().isoformat()
    try:
        bars = (stock_series(client, start) if kind == "stock"
                else crypto_series(client, start))
        b = _pct_between(bars, start, oggi)
    except Exception as e:  # noqa: BLE001 — misura accessoria, mai bloccante
        log.warning("Indice di riferimento non disponibile: %s", e)
        return {}
    if b is None:
        return {}
    return {
        "riferimento": SPY if kind == "stock" else CRYPTO_BENCH,
        "strategia_pct": round(strategy_pct, 2),
        "riferimento_pct": round(b, 2),
        "alpha_pct": round(strategy_pct - b, 2),
        "giudizio": ("la strategia ha battuto il riferimento"
                     if strategy_pct > b else
                     "il riferimento ha fatto meglio: fermi avremmo guadagnato di piu'"),
    }
