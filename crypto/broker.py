"""
broker.py — accesso al broker per la DIVISIONE CRIPTO.

Estende AlpacaClient (condiviso col bot azioni) puntandolo al SECONDO conto
paper. Non modifica nulla del client originale: aggiunge solo i metodi cripto,
che vivono su endpoint diversi (/v1beta3/crypto/us/... invece di /v2/stocks/...).

Vincoli del broker sulle cripto, verificati sul campo e non negoziabili:
  * niente bracket / OCO / OTO: le protezioni si gestiscono a mano
  * niente ordini stop di mercato: solo market, limit, stop_limit
  * UNA SOLA sell order per posizione (la prima prenota tutte le unita')
  * ordine minimo 10 USD, tutto frazionabile, niente leva, niente short
  * mercato aperto 24/7
"""
from __future__ import annotations

import logging
import urllib.parse
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path

import yaml

from lib.alpaca_rest import AlpacaClient, BrokerError

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = REPO_ROOT / "config" / "crypto_config.yaml"

log = logging.getLogger("crypto.broker")


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def to_pair(symbol: str) -> str:
    """'BTCUSD' -> 'BTC/USD'. Le posizioni tornano senza barra, gli ordini la vogliono."""
    if "/" in symbol:
        return symbol
    for q in ("USDT", "USDC", "USD"):
        if symbol.endswith(q) and len(symbol) > len(q):
            return f"{symbol[:-len(q)]}/{q}"
    return symbol


def to_flat(symbol: str) -> str:
    """'BTC/USD' -> 'BTCUSD'."""
    return symbol.replace("/", "")


class CryptoClient(AlpacaClient):
    """Client del conto cripto. Stessa robustezza R5 del bot azioni."""

    def __init__(self, cfg: dict | None = None, timeout: int = 30):
        cfg = cfg or load_config()
        self.cfg = cfg
        secrets = REPO_ROOT / cfg["meta"]["secrets_file"]
        super().__init__(
            max_consecutive_errors=cfg["guardrails"]["max_consecutive_api_errors"],
            timeout=timeout,
            secrets_file=secrets,
        )
        self._asset_cache: dict[str, dict] | None = None

    # -----------------------------------------------------------------
    #  Verifica di identita' del conto
    # -----------------------------------------------------------------
    def assert_right_account(self) -> dict:
        """Rifiuta di operare se non e' il conto cripto atteso.

        E' la barriera che rende impossibile, anche per errore di
        configurazione, toccare il conto azionario.
        """
        acct = self.account()
        expected = (self.cfg["meta"].get("account_hint") or "").strip()
        if expected and acct.get("account_number") != expected:
            raise RuntimeError(
                f"CONTO SBAGLIATO: collegato a {acct.get('account_number')}, "
                f"atteso {expected}. Operazioni annullate."
            )
        if self.cfg["meta"].get("paper_trading") and not self.is_paper:
            raise RuntimeError("Config dice paper ma l'endpoint non e' paper. Stop.")
        return acct

    # -----------------------------------------------------------------
    #  Anagrafica strumenti
    # -----------------------------------------------------------------
    def crypto_assets(self) -> dict[str, dict]:
        """Coppie negoziabili, con incrementi minimi di quantita' e prezzo."""
        if self._asset_cache is None:
            rows = self._request(
                "GET", self._t("/v2/assets"),
                params={"asset_class": "crypto", "status": "active"},
            )
            self._asset_cache = {
                a["symbol"]: a for a in rows if a.get("tradable")
            }
        return self._asset_cache

    # -----------------------------------------------------------------
    #  Dati di mercato (v1beta3, non v2/stocks)
    # -----------------------------------------------------------------
    def _cd(self, path: str) -> str:
        return f"{self._data}/v1beta3/crypto/us{path}"

    def crypto_quotes(self, symbols: list[str]) -> dict:
        out: dict = {}
        for i in range(0, len(symbols), 50):
            chunk = symbols[i:i + 50]
            res = self._request(
                "GET", self._cd("/latest/quotes"),
                params={"symbols": ",".join(chunk)},
            )
            out.update(res.get("quotes", {}))
        return out

    def crypto_snapshots(self, symbols: list[str]) -> dict:
        out: dict = {}
        for i in range(0, len(symbols), 50):
            chunk = symbols[i:i + 50]
            res = self._request(
                "GET", self._cd("/snapshots"),
                params={"symbols": ",".join(chunk)},
            )
            out.update(res.get("snapshots", {}))
        return out

    def crypto_bars(self, symbols: list[str], start: str,
                    timeframe: str = "1D", limit: int = 10000) -> dict:
        """Barre storiche. `start` e' OBBLIGATORIO: senza, l'API restituisce
        una sola barra (inciampo gia' pagato sul bot azioni)."""
        out: dict[str, list] = {}
        for i in range(0, len(symbols), 20):
            chunk = symbols[i:i + 20]
            page = None
            while True:
                params = {
                    "symbols": ",".join(chunk),
                    "timeframe": timeframe,
                    "start": start,
                    "limit": limit,
                }
                if page:
                    params["page_token"] = page
                res = self._request("GET", self._cd("/bars"), params=params)
                for k, v in (res.get("bars") or {}).items():
                    out.setdefault(k, []).extend(v)
                page = res.get("next_page_token")
                if not page:
                    break
        return out

    # -----------------------------------------------------------------
    #  Arrotondamenti imposti dal broker
    # -----------------------------------------------------------------
    # Aritmetica ESATTA, non in virgola mobile. Su una moneta da quattro
    # milionesimi di dollaro si possiedono decine di milioni di unita': dividere
    # 25.811.523,058252426 per un miliardesimo da' 2,6 x 10^16, che supera la
    # precisione dei numeri decimali del computer. L'arrotondamento finiva verso
    # l'ALTO e il broker rifiutava l'ordine perche' chiedevamo di vendere piu' di
    # quanto avevamo. Una posizione e' rimasta scoperta per ore per questo.
    def round_qty(self, pair: str, qty: float) -> Decimal:
        a = self.crypto_assets().get(pair, {})
        inc = Decimal(str(a.get("min_trade_increment") or "0.000000001"))
        d = Decimal(str(qty))
        return (d / inc).to_integral_value(rounding=ROUND_DOWN) * inc

    def round_price(self, pair: str, price: float) -> Decimal:
        a = self.crypto_assets().get(pair, {})
        inc = Decimal(str(a.get("price_increment") or "0.01"))
        d = Decimal(str(price))
        return (d / inc).to_integral_value(rounding=ROUND_HALF_UP) * inc

    @staticmethod
    def fmt(value: Decimal) -> str:
        """Numero per il broker, MAI in notazione scientifica.

        str(2.828e-06) produce '2.828e-06', che l'API non accetta. Con format
        'f' si ottiene '0.000002828'.
        """
        return format(value.normalize(), "f")

    def min_order_size(self, pair: str) -> float:
        a = self.crypto_assets().get(pair, {})
        return float(a.get("min_order_size") or 0)

    # -----------------------------------------------------------------
    #  Ordini
    # -----------------------------------------------------------------
    def buy_notional(self, pair: str, usd: float,
                     client_order_id: str | None = None) -> dict:
        """Acquisto a mercato per controvalore (le cripto sono frazionabili)."""
        body = {
            "symbol": pair,
            "notional": str(round(usd, 2)),
            "side": "buy",
            "type": "market",
            "time_in_force": "gtc",
        }
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", self._t("/v2/orders"), json=body)

    def sell_stop_limit(self, pair: str, qty: float, stop: float, limit: float,
                        client_order_id: str | None = None) -> dict:
        """Stop-limit di protezione. E' l'UNICO ordine di vendita ammesso sulla
        posizione: finche' e' aperto, le unita' sono prenotate."""
        body = {
            "symbol": pair,
            "qty": self.fmt(self.round_qty(pair, qty)),
            "side": "sell",
            "type": "stop_limit",
            "time_in_force": "gtc",
            "stop_price": self.fmt(self.round_price(pair, stop)),
            "limit_price": self.fmt(self.round_price(pair, limit)),
        }
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", self._t("/v2/orders"), json=body)

    def replace_order(self, order_id: str, stop: float | None = None,
                      limit: float | None = None, pair: str | None = None) -> dict:
        """Sostituisce un ordine aperto (PATCH), senza cancellarlo prima.

        E' la differenza tra alzare il trailing stop in sicurezza e lasciare la
        posizione scoperta per qualche secondo. Sul bot azioni quella finestra
        e' costata 124 USD: qui non la apriamo.
        """
        body: dict = {}
        if stop is not None:
            body["stop_price"] = self.fmt(self.round_price(pair or "", stop))
        if limit is not None:
            body["limit_price"] = self.fmt(self.round_price(pair or "", limit))
        return self._request("PATCH", self._t(f"/v2/orders/{order_id}"), json=body)

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", self._t(f"/v2/orders/{order_id}"))

    def sell_market(self, pair: str, qty: float) -> dict:
        """Uscita a mercato (uscita per debolezza relativa, non per stop)."""
        body = {
            "symbol": pair,
            "qty": self.fmt(self.round_qty(pair, qty)),
            "side": "sell",
            "type": "market",
            "time_in_force": "gtc",
        }
        return self._request("POST", self._t("/v2/orders"), json=body)

    # -----------------------------------------------------------------
    #  Posizioni
    # -----------------------------------------------------------------
    def crypto_positions(self) -> list[dict]:
        return [p for p in self.list_positions()
                if p.get("asset_class") == "crypto"]

    def close_crypto_position(self, symbol: str) -> dict:
        enc = urllib.parse.quote(to_flat(symbol), safe="")
        return self._request("DELETE", self._t(f"/v2/positions/{enc}"))

    def open_sell_orders(self) -> dict[str, dict]:
        """Ordini di vendita aperti, indicizzati per coppia."""
        out = {}
        for o in self.list_orders(status="open"):
            if o.get("side") == "sell":
                out[to_pair(o["symbol"])] = o
        return out


__all__ = ["CryptoClient", "load_config", "to_pair", "to_flat", "BrokerError"]
