"""
alpaca_rest.py — strato di plumbing broker (REST Alpaca) per le routine agentiche.

Filosofia: questo modulo contiene SOLO l'I/O verso Alpaca e utilità di robustezza
(scrittura atomica, fuso orario, conteggio errori R5). La STRATEGIA e le decisioni
vivono nei prompt agentici delle routine (cartella ROUTINES/), non qui.

Le chiavi NON sono nel codice: si leggono da secrets/alpaca_keys.env (git-ignored)
o, in mancanza, dalle variabili d'ambiente. Mai loggare le chiavi.

Endpoint usati (Fase 1 = Paper):
  trading: https://paper-api.alpaca.markets
  data:    https://data.alpaca.markets   (feed=iex, gratuito)
"""
from __future__ import annotations

import json
import os
import time
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

# --- Percorsi del progetto (questo file è in <repo>/lib/) ---
REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE = REPO_ROOT / "secrets" / "alpaca_keys.env"
CONFIG_FILE = REPO_ROOT / "config" / "trading_config.yaml"

CET = ZoneInfo("Europe/Rome")
US_EASTERN = ZoneInfo("America/New_York")


# =====================================================================
#  Config & credenziali
# =====================================================================
def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_keys() -> dict:
    """Carica le chiavi da secrets/alpaca_keys.env, con fallback su os.environ."""
    env: dict[str, str] = {}
    if SECRETS_FILE.exists():
        for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    api = env.get("ALPACA_API_KEY") or os.environ.get("ALPACA_API_KEY")
    sec = env.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    if not api or not sec:
        raise RuntimeError(
            "Credenziali Alpaca assenti: attese in secrets/alpaca_keys.env "
            "(ALPACA_API_KEY / ALPACA_SECRET_KEY) o nelle variabili d'ambiente."
        )
    base = env.get("ALPACA_BASE_URL") or os.environ.get(
        "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
    )
    data = env.get("ALPACA_DATA_URL") or os.environ.get(
        "ALPACA_DATA_URL", "https://data.alpaca.markets"
    )
    return {"api": api, "sec": sec, "base": base.rstrip("/"), "data": data.rstrip("/")}


# =====================================================================
#  R5 — eccezione di soglia errori broker
# =====================================================================
class BrokerError(RuntimeError):
    pass


class GuardrailR5(RuntimeError):
    """Sollevata quando si superano max_consecutive_api_errors (R5)."""


class AlpacaClient:
    """Client REST minimale con conteggio errori consecutivi (R5)."""

    def __init__(self, max_consecutive_errors: int = 3, timeout: int = 30):
        k = _load_keys()
        self._base = k["base"]
        self._data = k["data"]
        self._is_paper = "paper" in k["base"]
        self._h = {
            "APCA-API-KEY-ID": k["api"],
            "APCA-API-SECRET-KEY": k["sec"],
            "accept": "application/json",
        }
        self.max_consecutive_errors = max_consecutive_errors
        self._consecutive_errors = 0
        self._timeout = timeout

    @property
    def is_paper(self) -> bool:
        return self._is_paper

    # --- core HTTP con guardrail R5 ---
    def _request(self, method: str, url: str, **kw):
        try:
            r = requests.request(method, url, headers=self._h, timeout=self._timeout, **kw)
        except requests.RequestException as e:
            self._bump_error()
            raise BrokerError(f"{method} {url} fallita: {e}") from e
        # 5xx e 429 contano come errori broker (R5); 4xx logici no.
        if r.status_code >= 500 or r.status_code == 429:
            self._bump_error()
            raise BrokerError(f"{method} {url} -> HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code >= 400:
            # errore logico (es. ordine rifiutato): non incrementa R5, ma fallisce
            raise BrokerError(f"{method} {url} -> HTTP {r.status_code}: {r.text[:300]}")
        self._consecutive_errors = 0  # successo azzera il contatore
        if r.text:
            return r.json()
        return {}

    def _bump_error(self):
        self._consecutive_errors += 1
        if self._consecutive_errors >= self.max_consecutive_errors:
            raise GuardrailR5(
                f"R5: {self._consecutive_errors} errori broker consecutivi "
                f"(soglia {self.max_consecutive_errors}). Stop."
            )

    def _t(self, path: str) -> str:
        return f"{self._base}{path}"

    def _d(self, path: str) -> str:
        return f"{self._data}{path}"

    # --- ACCOUNT ---
    def account(self) -> dict:
        return self._request("GET", self._t("/v2/account"))

    def clock(self) -> dict:
        return self._request("GET", self._t("/v2/clock"))

    def calendar(self, start: str, end: str) -> list:
        return self._request(
            "GET", self._t("/v2/calendar"), params={"start": start, "end": end}
        )

    def is_trading_day(self, day: dt.date | None = None) -> bool:
        day = day or dt.datetime.now(US_EASTERN).date()
        s = day.isoformat()
        cal = self.calendar(s, s)
        return any(c.get("date") == s for c in cal)

    # --- MARKET DATA (feed IEX) ---
    def snapshots(self, symbols: list[str], feed: str = "iex") -> dict:
        out: dict = {}
        # batch da 100 simboli
        for i in range(0, len(symbols), 100):
            chunk = symbols[i : i + 100]
            res = self._request(
                "GET",
                self._d("/v2/stocks/snapshots"),
                params={"symbols": ",".join(chunk), "feed": feed},
            )
            out.update(res)
        return out

    def latest_trade(self, symbol: str, feed: str = "iex") -> float | None:
        res = self._request(
            "GET",
            self._d("/v2/stocks/trades/latest"),
            params={"symbols": symbol, "feed": feed},
        )
        return res.get("trades", {}).get(symbol, {}).get("p")

    # --- ORDERS ---
    def list_orders(self, status: str = "open", symbols: list[str] | None = None) -> list:
        params = {"status": status, "limit": 500}
        if symbols:
            params["symbols"] = ",".join(symbols)
        return self._request("GET", self._t("/v2/orders"), params=params)

    def submit_bracket_order(
        self,
        symbol: str,
        qty: int,
        side: str,  # "buy" | "sell"
        take_profit_price: float,
        stop_loss_price: float,
        limit_price: float | None = None,
        tif: str = "day",
        client_order_id: str | None = None,
    ) -> dict:
        body = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "limit" if limit_price else "market",
            "time_in_force": tif,
            "order_class": "bracket",
            "take_profit": {"limit_price": round(take_profit_price, 2)},
            "stop_loss": {"stop_price": round(stop_loss_price, 2)},
        }
        if limit_price:
            body["limit_price"] = round(limit_price, 2)
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", self._t("/v2/orders"), json=body)

    def cancel_all_orders(self) -> list:
        return self._request("DELETE", self._t("/v2/orders"))

    # --- POSITIONS ---
    def list_positions(self) -> list:
        return self._request("GET", self._t("/v2/positions"))

    def close_all_positions(self, cancel_orders: bool = True) -> list:
        return self._request(
            "DELETE",
            self._t("/v2/positions"),
            params={"cancel_orders": str(cancel_orders).lower()},
        )

    # --- ACTIVITIES (per la riconciliazione) ---
    def activities(self, activity_type: str = "FILL", after: str | None = None, until: str | None = None) -> list:
        params = {"activity_types": activity_type}
        if after:
            params["after"] = after
        if until:
            params["until"] = until
        return self._request("GET", self._t("/v2/account/activities"), params=params)


# =====================================================================
#  Utilità
# =====================================================================
def now_cet() -> dt.datetime:
    return dt.datetime.now(CET)


def today_session_date() -> str:
    """Data di sessione = data odierna a New York (mercato USA)."""
    return dt.datetime.now(US_EASTERN).date().isoformat()


def atomic_write_json(path: str | Path, payload: dict) -> None:
    """Scrive su file temporaneo e poi rinomina (no JSON a metà)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    # Self-test di sola lettura (sicuro: nessun ordine inviato)
    cfg = load_config()
    cli = AlpacaClient(
        max_consecutive_errors=cfg["guardrails"]["max_consecutive_api_errors"]
    )
    print("is_paper:", cli.is_paper)
    acct = cli.account()
    print("account:", acct["account_number"], "equity", acct["equity"], "bp", acct["buying_power"])
    clk = cli.clock()
    print("clock: is_open", clk["is_open"], "next_open", clk["next_open"])
    print("today trading day?", cli.is_trading_day())
    snap = cli.snapshots(["AAPL", "NVDA"])
    for s in ("AAPL", "NVDA"):
        d = snap.get(s, {})
        print(s, "last", d.get("latestTrade", {}).get("p"),
              "prevClose", d.get("prevDailyBar", {}).get("c"))
