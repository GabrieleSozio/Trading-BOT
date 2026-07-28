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


def effective_capital(cfg: dict, real_equity: float) -> tuple[float, bool]:
    """Capitale su cui dimensionare le operazioni.

    Se `capital.simulated_usd` > 0 usa quell'importo (per provare in paper la
    strategia con capitale ridotto), ma MAI piu' dell'equity realmente
    disponibile. Ritorna (capitale, is_simulated).
    """
    sim = float((cfg.get("capital") or {}).get("simulated_usd") or 0)
    if sim > 0:
        cap = min(sim, real_equity)
        if cap < sim:
            log.warning(
                "Capitale simulato %.2f > equity reale %.2f: uso %.2f.",
                sim, real_equity, cap,
            )
        return round(cap, 2), True
    return round(real_equity, 2), False


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
