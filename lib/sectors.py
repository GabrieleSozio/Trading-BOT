"""
sectors.py — mappa settoriale statica dell'universo (per la guardrail R4).

Alpaca non espone il settore GICS via API, quindi usiamo una mappa nota.
Granularita' volutamente "a settore" (non sotto-industria): la R4 limita il
capitale per singolo settore al 15%. Ticker non mappato -> "Unknown".
"""

SECTOR_MAP = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "AMZN": "Consumer Discretionary",
    "GOOGL": "Communication Services",
    "META": "Communication Services",
    "TSLA": "Consumer Discretionary",
    "AMD": "Technology",
    "AVGO": "Technology",
    "NFLX": "Communication Services",
    "INTC": "Technology",
    "QCOM": "Technology",
    "ADBE": "Technology",
    "CRM": "Technology",
    "ORCL": "Technology",
    "CSCO": "Technology",
    "PYPL": "Financials",
    "MU": "Technology",
    "PLTR": "Technology",
    "SHOP": "Technology",
    "UBER": "Industrials",
    "COIN": "Financials",
    "SMCI": "Technology",
    "ARM": "Technology",
    "SNOW": "Technology",
    # --- fascia media / economica (accessibile a capitale ridotto) ---
    "HOOD": "Financials",
    "GM": "Consumer Discretionary",
    "KO": "Consumer Staples",
    "WFC": "Financials",
    "BAC": "Financials",
    "AFRM": "Financials",
    "NKE": "Consumer Discretionary",
    "CSX": "Industrials",
    "HPQ": "Technology",
    "PINS": "Communication Services",
    "DKNG": "Consumer Discretionary",
    "WBD": "Communication Services",
    "PFE": "Health Care",
    "T": "Communication Services",
    "SOFI": "Financials",
    "RIVN": "Consumer Discretionary",
    "F": "Consumer Discretionary",
    "AAL": "Industrials",
    "SNAP": "Communication Services",
}


def sector_of(ticker: str) -> str:
    return SECTOR_MAP.get(ticker.upper(), "Unknown")
