"""
broker.py — accesso al broker per la DIVISIONE OPZIONI.

Estende AlpacaClient (condiviso con azioni e cripto) puntandolo al TERZO conto
paper. Aggiunge solo i metodi per le opzioni: ricerca dei contratti, quotazioni,
invio ordini. Non tocca nulla del client originale.

Cose da sapere sulle opzioni, che le rendono diverse da azioni e cripto:
  * il contratto rappresenta 100 azioni: un premio di 1,13 costa 113 dollari
  * lo spread e' enorme rispetto alle azioni (4-7% contro lo 0,05%): la scelta
    del contratto conta quanto la scelta del titolo
  * il valore decade con il tempo anche se il sottostante non si muove
  * la perdita massima e' il premio pagato, ed e' l'unica cosa che ci piace
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import yaml

from lib.alpaca_rest import AlpacaClient, BrokerError

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = REPO_ROOT / "config" / "options_config.yaml"

log = logging.getLogger("options.broker")

MOLTIPLICATORE = 100      # un contratto = 100 azioni


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class OptionsClient(AlpacaClient):
    """Client del conto opzioni. Stessa robustezza R5 delle altre divisioni."""

    def __init__(self, cfg: dict | None = None, timeout: int = 30):
        cfg = cfg or load_config()
        self.cfg = cfg
        super().__init__(
            max_consecutive_errors=cfg["guardrails"]["max_consecutive_api_errors"],
            timeout=timeout,
            secrets_file=REPO_ROOT / cfg["meta"]["secrets_file"],
        )

    # -----------------------------------------------------------------
    def assert_right_account(self) -> dict:
        """Rifiuta di operare se non e' il conto opzioni atteso.

        E' la stessa barriera delle altre divisioni: rende impossibile toccare
        il capitale sbagliato anche per un errore di configurazione.
        """
        acct = self.account()
        atteso = (self.cfg["meta"].get("account_hint") or "").strip()
        if atteso and acct.get("account_number") != atteso:
            raise RuntimeError(
                f"CONTO SBAGLIATO: collegato a {acct.get('account_number')}, "
                f"atteso {atteso}. Operazioni annullate."
            )
        if self.cfg["meta"].get("paper_trading") and not self.is_paper:
            raise RuntimeError("Config dice paper ma l'endpoint non e' paper. Stop.")
        if int(acct.get("options_trading_level") or 0) < 1:
            raise RuntimeError("Il conto non e' abilitato alle opzioni.")
        return acct

    # -----------------------------------------------------------------
    #  Ricerca dei contratti
    # -----------------------------------------------------------------
    def chain(self, underlying: str, spot: float, tipo: str,
              giorni_min: int, giorni_max: int, finestra_strike: float = 0.06) -> list[dict]:
        """Contratti disponibili vicino al prezzo, nella finestra di scadenza voluta."""
        oggi = dt.date.today()
        rows = self._request("GET", self._t("/v2/options/contracts"), params={
            "underlying_symbols": underlying,
            "type": tipo,
            "status": "active",
            "strike_price_gte": str(round(spot * (1 - finestra_strike), 2)),
            "strike_price_lte": str(round(spot * (1 + finestra_strike), 2)),
            "expiration_date_gte": (oggi + dt.timedelta(days=giorni_min)).isoformat(),
            "expiration_date_lte": (oggi + dt.timedelta(days=giorni_max)).isoformat(),
            "limit": 200,
        }).get("option_contracts", [])
        return sorted(rows, key=lambda x: (x["expiration_date"], float(x["strike_price"])))

    def quotes(self, symbols: list[str]) -> dict:
        """Quotazioni dei contratti. Senza queste non si puo' misurare lo spread,
        che su questo strumento e' il costo dominante."""
        out: dict = {}
        for i in range(0, len(symbols), 100):
            chunk = symbols[i:i + 100]
            res = self._request("GET", self._d("/v1beta1/options/snapshots"),
                                params={"symbols": ",".join(chunk)})
            out.update(res.get("snapshots", {}))
        return out

    @staticmethod
    def spread_pct(snap: dict) -> float | None:
        q = (snap or {}).get("latestQuote") or {}
        bid, ask = float(q.get("bp") or 0), float(q.get("ap") or 0)
        if bid <= 0 or ask <= 0:
            return None
        mid = (bid + ask) / 2
        return (ask - bid) / mid * 100 if mid else None

    @staticmethod
    def ask(snap: dict) -> float | None:
        q = (snap or {}).get("latestQuote") or {}
        a = float(q.get("ap") or 0)
        return a if a > 0 else None

    # -----------------------------------------------------------------
    #  Ordini
    # -----------------------------------------------------------------
    def buy_to_open(self, symbol: str, qty: int = 1,
                    limit_price: float | None = None,
                    client_order_id: str | None = None) -> dict:
        """Acquisto di contratti. Si usa un limite quando possibile: con spread
        del 4-7% un ordine a mercato regala la meta' dello spread al venditore."""
        body = {
            "symbol": symbol,
            "qty": str(int(qty)),
            "side": "buy",
            "type": "limit" if limit_price else "market",
            "time_in_force": "day",
        }
        if limit_price:
            body["limit_price"] = f"{limit_price:.2f}"
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", self._t("/v2/orders"), json=body)

    def sell_to_close(self, symbol: str, qty: int = 1,
                      limit_price: float | None = None) -> dict:
        body = {
            "symbol": symbol,
            "qty": str(int(qty)),
            "side": "sell",
            "type": "limit" if limit_price else "market",
            "time_in_force": "day",
        }
        if limit_price:
            body["limit_price"] = f"{limit_price:.2f}"
        return self._request("POST", self._t("/v2/orders"), json=body)

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", self._t(f"/v2/orders/{order_id}"))

    # -----------------------------------------------------------------
    #  Posizioni
    # -----------------------------------------------------------------
    def option_positions(self) -> list[dict]:
        return [p for p in self.list_positions()
                if p.get("asset_class") == "us_option"]

    def order(self, order_id: str) -> dict:
        return self._request("GET", self._t(f"/v2/orders/{order_id}"))


__all__ = ["OptionsClient", "load_config", "BrokerError", "MOLTIPLICATORE"]
