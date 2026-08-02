"""
capital.py — capitale operativo e fasce di rischio.

Il bot adatta strategia e limiti alla dimensione del conto. Questo modulo e' la
fonte unica di verita' per due domande:

  1. "Con quanti soldi sto operando?"   -> effective_capital()
  2. "Quali regole valgono a questa cifra?" -> resolve_tier()

Perche' la strategia cambia con il capitale: la regola USA *Pattern Day Trader*
vieta piu' di 3 operazioni intraday ogni 5 giorni lavorativi ai conti sotto i
25.000 USD. Sotto quella soglia il bot opera in SWING (posizioni tenute piu'
giorni, che non consumano crediti PDT); sopra, torna all'intraday con flat serale.
"""
from __future__ import annotations

import logging

log = logging.getLogger("capital")


class TierError(RuntimeError):
    """Configurazione delle fasce assente o malformata."""


def strategy_pnl(client, start_iso: str) -> float:
    """Profitto/perdita cumulato della strategia dal suo avvio.

    Si ricava dal broker, non da un contatore interno: cosi' non puo' andare fuori
    sincrono e si auto-corregge. Somma il flusso di cassa di tutti i fill dall'avvio
    (negativo per gli acquisti, positivo per le vendite) e ci aggiunge il valore di
    mercato di cio' che e' ancora aperto.
    """
    fills = client.activities("FILL", after=start_iso)
    net = 0.0
    for f in fills:
        try:
            qty, price, side = float(f["qty"]), float(f["price"]), f.get("side", "")
        except (KeyError, TypeError, ValueError):
            continue
        net += qty * price * (1 if side.startswith("sell") else -1)
    market_value = sum(float(p.get("market_value", 0)) for p in client.list_positions())
    return net + market_value


def effective_capital(cfg: dict, real_equity: float, client=None) -> tuple[float, bool]:
    """Capitale su cui dimensionare le operazioni.

    Con `capital.base_usd` > 0 il bot opera su quell'importo invece che sull'equity
    reale (serve a provare in paper la strategia che si usera' con capitale ridotto).
    Se `capital.compound` e' true, al capitale base si somma il P&L cumulato della
    strategia: i guadagni vengono reinvestiti e le perdite riducono l'esposizione,
    esattamente come accadrebbe su un conto reale.

    In ogni caso non si opera mai per piu' dell'equity realmente disponibile.
    Ritorna (capitale, is_simulated).
    """
    c = cfg.get("capital") or {}
    base = float(c.get("base_usd") or c.get("simulated_usd") or 0)
    if base <= 0:
        return round(real_equity, 2), False

    cap = base
    if c.get("compound") and client is not None:
        try:
            pnl = strategy_pnl(client, c.get("strategy_start") or "2000-01-01T00:00:00Z")
            cap = base + pnl
            log.info("Compounding: base %.2f %+.2f di risultati = %.2f USD operativi",
                     base, pnl, cap)
        except Exception as e:  # noqa: BLE001 — mai bloccare il bot per il calcolo
            log.warning("P&L cumulato non calcolabile (%s): uso il capitale base.", e)
            cap = base

    floor_usd = float(c.get("min_usd") or 0)
    if cap < floor_usd:
        log.warning("Capitale sceso a %.2f, sotto il minimo operativo %.2f.", cap, floor_usd)
    cap = min(cap, real_equity)
    return round(max(cap, 0.0), 2), True


def resolve_tier(cfg: dict, capital: float) -> dict:
    """Fascia attiva per il capitale dato (prima con up_to_equity >= capitale;
    l'ultima con up_to_equity null e' il catch-all)."""
    tiers = cfg.get("tiers") or []
    if not tiers:
        raise TierError("sezione 'tiers' assente in config: impossibile applicare le regole")
    for t in tiers:
        cap_limit = t.get("up_to_equity")
        if cap_limit is None or capital <= float(cap_limit):
            return dict(t)
    return dict(tiers[-1])


def max_affordable_price(capital: float, tier: dict) -> float:
    """Prezzo massimo per azione ancora acquistabile: se una singola azione costa
    piu' della quota allocata, il titolo non e' operabile (usiamo azioni INTERE
    per poter allegare lo stop-loss fisico, che le frazioni non supportano)."""
    return capital * float(tier["max_position_size_pct"])


def describe(tier: dict, capital: float, simulated: bool) -> str:
    origin = "SIMULATO" if simulated else "reale"
    return (
        f"capitale {capital:,.2f} USD ({origin}) -> fascia '{tier['name']}' "
        f"[{tier['mode']}] {tier['positions_to_open']} posizioni x "
        f"{tier['max_position_size_pct']*100:.0f}% | stop -{tier['stop_loss_pct']*100:.1f}% "
        f"/ target +{tier['take_profit_pct']*100:.1f}% | "
        f"short {'si' if tier.get('allow_short') else 'no'} | "
        f"max hold {tier.get('max_hold_days', 0)}gg"
    )


def is_intraday(tier: dict) -> bool:
    return str(tier.get("mode", "intraday")).lower() == "intraday"
