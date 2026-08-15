"""
insider.py — attività degli insider dai moduli SEC Form 4.

Quando un dirigente o un amministratore compra o vende azioni della PROPRIA
societa' deve dichiararlo alla SEC entro 2 giorni lavorativi (Form 4). E' un dato
pubblico, gratuito e verificabile: nessuna chiave API, nessuna registrazione.

Cosa conta davvero. Un Form 4 registra molte cose che NON sono scelte di
investimento: assegnazioni di azioni come compenso (codice A), esercizio di stock
option (M), azioni trattenute per le tasse (F). L'unico segnale con un contenuto
informativo e' il codice **P**: acquisto sul mercato aperto, cioe' l'insider ha
speso denaro proprio. Le vendite (S) sono piu' ambigue (spesso pianificate o per
liquidita' personale) ma vengono comunque riportate.

Il risultato NON decide nulla da solo: viene passato all'AI come uno degli
elementi di valutazione, insieme a momentum e volume.

Regole SEC rispettate: User-Agent identificativo obbligatorio, max 10 richieste/s.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

log = logging.getLogger("insider")

SEC_UA = "Trading-BOT research (contatto: gabrielesozio03@gmail.com)"
# Niente Accept-Encoding: urllib non decomprime da solo e il gzip arriverebbe illeggibile.
_HEADERS = {"User-Agent": SEC_UA}
_PAUSE = 0.15          # ~7 richieste/s, sotto il limite SEC di 10
CACHE_HOURS = 12       # i Form 4 cambiano lentamente: inutile riscaricare a ogni tick

_cik_map: dict[str, str] | None = None


def _get(url: str, as_json: bool = True):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    time.sleep(_PAUSE)
    return json.loads(raw) if as_json else raw.decode("utf-8", "ignore")


def _cik_for(ticker: str) -> str | None:
    global _cik_map
    if _cik_map is None:
        try:
            data = _get("https://www.sec.gov/files/company_tickers.json")
            _cik_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in data.values()}
        except Exception as e:  # noqa: BLE001
            log.warning("Elenco CIK non scaricabile (%s): salto l'analisi insider.", e)
            _cik_map = {}
    return _cik_map.get(ticker.upper())


def _parse_form4(xml_text: str) -> list[dict]:
    """Estrae le transazioni rilevanti da un Form 4."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    def txt(el, path):
        n = el.find(path) if el is not None else None
        return n.text.strip() if n is not None and n.text else None

    owner = root.find(".//reportingOwner")
    name = txt(owner, "reportingOwnerId/rptOwnerName") or "?"
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    role = txt(rel, "officerTitle") or (
        "Director" if txt(rel, "isDirector") == "1" else
        "Officer" if txt(rel, "isOfficer") == "1" else "Insider")

    out = []
    for t in root.findall(".//nonDerivativeTransaction"):
        code = txt(t, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue  # ignoriamo compensi, opzioni, ritenute fiscali
        try:
            shares = float(txt(t, "transactionAmounts/transactionShares/value") or 0)
            price = float(txt(t, "transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        out.append({
            "code": code, "name": name, "role": role,
            "shares": shares, "price": price, "value": round(shares * price, 2),
            "date": txt(t, "transactionDate/value"),
        })
    return out


def _fetch_ticker(ticker: str, days: int, max_filings: int) -> dict:
    cik = _cik_for(ticker)
    if not cik:
        return {"ticker": ticker, "available": False}
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    try:
        sub = _get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    except Exception as e:  # noqa: BLE001
        log.warning("%s: submissions non leggibili (%s).", ticker, e)
        return {"ticker": ticker, "available": False}

    rec = sub.get("filings", {}).get("recent", {})
    txs, checked = [], 0
    for i, form in enumerate(rec.get("form", [])):
        if form != "4" or rec["filingDate"][i] < cutoff:
            continue
        if checked >= max_filings:
            break
        checked += 1
        acc = rec["accessionNumber"][i].replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/form4.xml"
        try:
            txs += _parse_form4(_get(url, as_json=False))
        except Exception:  # noqa: BLE001 — un filing illeggibile non deve fermare tutto
            continue

    buys = [t for t in txs if t["code"] == "P"]
    sells = [t for t in txs if t["code"] == "S"]
    return {
        "ticker": ticker,
        "available": True,
        "window_days": days,
        "n_buys": len(buys),
        "n_sells": len(sells),
        "buy_value_usd": round(sum(t["value"] for t in buys), 2),
        "sell_value_usd": round(sum(t["value"] for t in sells), 2),
        "buyers": sorted({f"{t['name']} ({t['role']})" for t in buys})[:3],
        "sellers": sorted({f"{t['name']} ({t['role']})" for t in sells})[:3],
    }


def activity(tickers: list[str], cache_dir: str = "state",
             days: int = 90, max_filings: int = 12) -> dict:
    """Attività insider per i ticker richiesti, con cache su file.

    Non solleva mai: se la SEC non risponde, restituisce semplicemente dati
    mancanti e il bot prosegue con gli altri criteri.
    """
    path = Path(cache_dir) / "insider_cache.json"
    cache = {}
    if path.exists():
        try:
            cache = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cache = {}

    now = dt.datetime.now(dt.timezone.utc)
    out, fetched = {}, 0
    for t in tickers:
        entry = cache.get(t)
        if entry:
            try:
                age = (now - dt.datetime.fromisoformat(entry["fetched_at"])).total_seconds() / 3600
                if age < CACHE_HOURS:
                    out[t] = entry["data"]
                    continue
            except Exception:  # noqa: BLE001
                pass
        data = _fetch_ticker(t, days, max_filings)
        out[t] = data
        cache[t] = {"fetched_at": now.isoformat(timespec="seconds"), "data": data}
        fetched += 1

    if fetched:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cache, indent=1), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log.warning("Cache insider non salvabile: %s", e)
        log.info("Insider: scaricati %d ticker (gli altri da cache).", fetched)
    return out


def summarize(data: dict) -> str:
    """Riga leggibile per ticker, da passare all'AI."""
    rows = []
    for t, d in data.items():
        if not d.get("available"):
            rows.append(f"{t}: dati non disponibili")
            continue
        if not d["n_buys"] and not d["n_sells"]:
            rows.append(f"{t}: nessuna operazione insider negli ultimi {d['window_days']}gg")
            continue
        parts = []
        if d["n_buys"]:
            parts.append(f"ACQUISTI {d['n_buys']} per ${d['buy_value_usd']:,.0f}"
                         + (f" ({', '.join(d['buyers'])})" if d["buyers"] else ""))
        if d["n_sells"]:
            parts.append(f"vendite {d['n_sells']} per ${d['sell_value_usd']:,.0f}")
        rows.append(f"{t}: " + " | ".join(parts))
    return "\n".join(rows)
