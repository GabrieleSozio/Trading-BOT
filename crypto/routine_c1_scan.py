"""
routine_c1_scan.py — CRIPTO / Scansione e classifica.

Gira una volta al giorno. Non invia ordini: legge il mercato, costruisce la
classifica di momentum e scrive `state/crypto/ranking.json`, che la routine di
trading usera' come lista della spesa.

Tenere la decisione (qui) separata dall'esecuzione (C2) significa che si puo'
far girare questa quante volte si vuole senza rischiare nulla.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from lib.alpaca_rest import atomic_write_json, now_cet
from crypto import signals
from crypto.broker import CryptoClient, load_config

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s"
)
log = logging.getLogger("crypto.c1")


def run(dry_run: bool = False) -> dict:
    cfg = load_config()
    cli = CryptoClient(cfg)
    acct = cli.assert_right_account()

    equity = float(acct["equity"])
    log.info("Conto cripto %s | equity $%.2f | cash $%.2f",
             acct["account_number"], equity, float(acct["cash"]))

    if equity < float(cfg["capital"]["min_usd"]):
        log.warning("Capitale eroso sotto la soglia minima ($%.2f).", equity)

    # 1. universo misurato
    pairs, diag = signals.discover_universe(cli, cfg)
    if not pairs:
        log.error("Nessuna coppia negoziabile: scansione interrotta.")
        return {"ok": False, "reason": "universo vuoto"}

    # 2. metriche e classifica
    metrics = signals.compute_metrics(cli, cfg, pairs)
    if not metrics:
        log.error("Nessuna coppia con storico sufficiente.")
        return {"ok": False, "reason": "storico insufficiente"}
    ranked = signals.rank(metrics)
    chosen = signals.select(cfg, ranked)
    weights = signals.target_weights(chosen, cfg)

    log.info("--- CLASSIFICA (prime 10 su %d) ---", len(ranked))
    for r in ranked[:10]:
        mark = "*" if r["pair"] in weights else " "
        rr = r["returns"]
        log.info(" %s %2d. %-12s score %+7.2f%%  (7g %+6.1f%% | 30g %+6.1f%% | 90g %+6.1f%%)"
                 "  vol %.1f%%/g  stop %.1f%%",
                 mark, r["rank"], r["pair"], r["momentum_score"] * 100,
                 rr.get("7", 0) * 100, rr.get("30", 0) * 100, rr.get("90", 0) * 100,
                 r["atr_pct"] * 100, signals.stop_distance_pct(r, cfg) * 100)

    log.info("--- SELEZIONE ---")
    for m in chosen:
        w = weights.get(m["pair"], 0)
        log.info("  %-12s peso %5.1f%%  ($%.2f)  stop a -%.1f%%",
                 m["pair"], w * 100, w * equity,
                 signals.stop_distance_pct(m, cfg) * 100)
    invested = sum(weights.values())
    log.info("  investito complessivo: %.1f%% | liquidita' %.1f%%",
             invested * 100, (1 - invested) * 100)

    payload = {
        "generated_at": now_cet().isoformat(timespec="seconds"),
        "session_date": dt.date.today().isoformat(),
        "account": acct["account_number"],
        "equity_usd": round(equity, 2),
        "universe_size": len(pairs),
        "universe_diagnostics": diag,
        "ranking": ranked,
        "selection": [
            {
                "pair": m["pair"],
                "rank": m["rank"],
                "momentum_score": m["momentum_score"],
                "atr_pct": m["atr_pct"],
                "stop_distance_pct": round(signals.stop_distance_pct(m, cfg), 5),
                "target_weight": round(weights.get(m["pair"], 0), 5),
                "target_usd": round(weights.get(m["pair"], 0) * equity, 2),
            }
            for m in chosen
        ],
    }

    if dry_run:
        log.info("dry-run: nessun file scritto.")
        return {"ok": True, "payload": payload, "written": False}

    atomic_write_json(cfg["state"]["files"]["ranking"], payload)
    log.info("Scritto %s", cfg["state"]["files"]["ranking"])
    return {"ok": True, "payload": payload, "written": True}


def main() -> int:
    ap = argparse.ArgumentParser(description="Cripto — scansione e classifica")
    ap.add_argument("--dry-run", action="store_true", help="non scrive lo stato")
    ap.add_argument("--no-push", action="store_true", help="non fa git push")
    a = ap.parse_args()

    res = run(dry_run=a.dry_run)
    if res.get("ok") and res.get("written") and not a.no_push:
        from lib import gitsync
        gitsync.sync(f"cripto: classifica {dt.date.today().isoformat()}")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
