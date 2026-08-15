"""
signals.py — selezione e dimensionamento della divisione cripto.

Tre compiti distinti, tenuti separati apposta:

  1. UNIVERSO   quali coppie sono negoziabili a costo accettabile (misurato)
  2. CLASSIFICA quali sono le piu' forti in questo momento (momentum trasversale)
  3. PESI       quanto capitale su ciascuna (rischio costante, non fette uguali)

Perche' momentum TRASVERSALE e non "compra se il mercato sale": si comprano le
piu' forti in classifica sempre, anche in fase negativa. E' la scelta aggressiva
ed e' quella che regge nelle verifiche indipendenti sulle cripto (l'effetto e'
concentrato su orizzonti di 1-4 settimane). Il prezzo da pagare, dichiarato: in
una discesa generale il portafoglio scende con il mercato.

Perche' NESSUN take profit: il rendimento del momentum arriva da poche posizioni
che corrono molto. Un tetto fisso le taglia tutte e lascia intere le perdenti.
"""
from __future__ import annotations

import datetime as dt
import logging

log = logging.getLogger("crypto.signals")


# =====================================================================
#  1. Universo
# =====================================================================
def discover_universe(client, cfg: dict) -> tuple[list[str], list[dict]]:
    """Coppie negoziabili che superano i filtri MISURATI (spread e storico).

    Ritorna (ammesse, diagnostica). Nessun elenco scritto a mano: se Alpaca
    aggiunge una coppia entra da sola, se una diventa cara esce da sola.
    """
    u = cfg["universe"]
    quote = "/" + u.get("quote_currency", "USD")
    excluded = set(u.get("exclude") or [])

    pairs = sorted(s for s in client.crypto_assets()
                   if s.endswith(quote) and s not in excluded)
    if not pairs:
        return [], []

    quotes = client.crypto_quotes(pairs)
    max_spread = float(u["max_spread_bps"])

    rows, ok = [], []
    for p in pairs:
        q = quotes.get(p) or {}
        bid, ask = float(q.get("bp") or 0), float(q.get("ap") or 0)
        if bid <= 0 or ask <= 0:
            rows.append({"pair": p, "ok": False, "reason": "nessuna quotazione"})
            continue
        mid = (bid + ask) / 2
        spread_bps = (ask - bid) / mid * 10_000
        if spread_bps > max_spread:
            rows.append({"pair": p, "ok": False, "spread_bps": round(spread_bps, 1),
                         "reason": f"spread {spread_bps:.0f}bp > {max_spread:.0f}bp"})
            continue
        rows.append({"pair": p, "ok": True, "spread_bps": round(spread_bps, 1), "mid": mid})
        ok.append(p)

    log.info("Universo: %d coppie negoziabili su %d (filtro spread <= %.0fbp).",
             len(ok), len(pairs), max_spread)
    return ok, rows


# =====================================================================
#  2. Metriche e classifica
# =====================================================================
def _atr_pct(bars: list[dict], days: int) -> float:
    """Escursione media giornaliera in %, misura di volatilita' della moneta."""
    use = [b for b in bars[-days:] if b.get("c")]
    if not use:
        return 0.0
    return sum((b["h"] - b["l"]) / b["c"] for b in use) / len(use)


def _return_pct(bars: list[dict], days: int) -> float | None:
    if len(bars) <= days:
        return None
    past = bars[-(days + 1)]["c"]
    return (bars[-1]["c"] / past - 1) if past else None


def compute_metrics(client, cfg: dict, pairs: list[str]) -> dict[str, dict]:
    """Momentum multi-finestra e volatilita' per ogni coppia."""
    s = cfg["strategy"]
    windows = {int(k): float(v) for k, v in s["momentum_weights"].items()}
    need = cfg["universe"]["min_history_days"]
    lookback = max(max(windows), need) + 20

    start = (dt.date.today() - dt.timedelta(days=lookback)).isoformat()
    bars = client.crypto_bars(pairs, start=start, timeframe="1D")

    out: dict[str, dict] = {}
    for p in pairs:
        b = bars.get(p) or []
        if len(b) < need:
            log.debug("%s: storico insufficiente (%d barre).", p, len(b))
            continue

        rets, score, weight_used = {}, 0.0, 0.0
        for w, wt in windows.items():
            r = _return_pct(b, w)
            if r is None:
                continue
            rets[w] = r
            score += wt * r
            weight_used += wt
        if weight_used <= 0:
            continue
        score /= weight_used  # normalizza se una finestra manca

        atr = _atr_pct(b, int(s["atr_days"]))
        out[p] = {
            "pair": p,
            "last": b[-1]["c"],
            "bars": len(b),
            "returns": {str(k): round(v, 4) for k, v in rets.items()},
            "momentum_score": round(score, 5),
            "atr_pct": round(atr, 5),
        }
    return out


def rank(metrics: dict[str, dict]) -> list[dict]:
    """Classifica per momentum decrescente. Il posto in classifica e' cio' che
    decide ingressi e uscite, non il segno assoluto del rendimento."""
    rows = sorted(metrics.values(), key=lambda m: m["momentum_score"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


# =====================================================================
#  3. Stop e pesi
# =====================================================================
def stop_distance_pct(metrics: dict, cfg: dict) -> float:
    """Distanza dello stop, proporzionale alla volatilita' della moneta.

    Uno stop fisso in percentuale e' l'errore classico: 8% e' larghissimo su
    BTC (1,7%/giorno) e viene toccato dal rumore su PEPE (8,2%/giorno). Con
    2,5 ATR ogni moneta ha lo spazio che le serve per respirare.
    """
    s = cfg["strategy"]
    d = float(metrics["atr_pct"]) * float(s["atr_stop_mult"])
    return max(float(s["min_stop_pct"]), min(float(s["max_stop_pct"]), d))


def target_weights(selected: list[dict], cfg: dict) -> dict[str, float]:
    """Pesi a RISCHIO COSTANTE, non fette uguali.

    Ogni posizione perde la stessa quota di capitale se lo stop scatta:
        peso = rischio_per_posizione / distanza_stop
    Poi si normalizza al livello di investimento voluto. Cosi' una moneta molto
    volatile entra comunque in portafoglio, ma pesando meno.
    """
    s = cfg["strategy"]
    risk = float(s["risk_per_position_pct"])
    lo, hi = float(s["min_position_pct"]), float(s["max_position_pct"])
    deploy = float(s["target_deployment_pct"])

    raw = {}
    for m in selected:
        d = stop_distance_pct(m, cfg)
        raw[m["pair"]] = max(lo, min(hi, risk / d if d > 0 else lo))

    total = sum(raw.values())
    if total <= 0:
        return {}
    # Si scala al livello di investimento voluto; se i tetti lo rendono
    # impossibile si resta sotto, mai sopra.
    scale = min(1.0, deploy / total)
    return {k: v * scale for k, v in raw.items()}


def select(cfg: dict, ranked: list[dict]) -> list[dict]:
    """Le prime N della classifica."""
    n = int(cfg["strategy"]["positions_to_open"])
    return ranked[:n]
