"""
Routine 05 — Friday Reconciliation / Back Office (logica deterministica).

A fine settimana calcola la performance REALE dal broker (account activities, non
i log locali) e archivia i file di stato. Sola lettura sul broker.

Finestra: lunedi' 00:00 -> venerdi' 23:59:59 US/Eastern della settimana conclusa.
Conversione timezone esplicita (errore qui = report falsato).

Uso:  python -m lib.routine_05_reconciliation [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import shutil
import urllib.request
import json
from collections import defaultdict
from pathlib import Path

from .alpaca_rest import (
    AlpacaClient,
    GuardrailR5,
    load_config,
    now_cet,
    US_EASTERN,
)
from . import gitsync

log = logging.getLogger("routine05")


def _week_window_et(ref: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """Lunedi' 00:00 -> venerdi' 23:59:59 US/Eastern della settimana di `ref`."""
    ref_et = ref.astimezone(US_EASTERN)
    monday = ref_et.date() - dt.timedelta(days=ref_et.weekday())  # weekday(): lun=0
    friday = monday + dt.timedelta(days=4)
    start = dt.datetime.combine(monday, dt.time(0, 0, 0), tzinfo=US_EASTERN)
    end = dt.datetime.combine(friday, dt.time(23, 59, 59), tzinfo=US_EASTERN)
    return start, end


def _send_webhook(url: str, content: str) -> bool:
    try:
        body = json.dumps({"content": content}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200 <= r.status < 300
    except Exception as e:
        log.warning("Invio webhook fallito: %s", e)
        return False


def run(dry_run: bool = False) -> str:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    archive_dir = cfg["state"]["archive_dir"]
    files = cfg["state"]["files"]
    notif = cfg.get("notifications", {})

    start, end = _week_window_et(now_cet())
    log.info("Finestra settimana (ET): %s -> %s", start.isoformat(), end.isoformat())

    client = AlpacaClient(max_consecutive_errors=cfg["guardrails"]["max_consecutive_api_errors"])
    try:
        fills = client.activities("FILL", after=start.isoformat(), until=end.isoformat())
        acct = client.account()
    except GuardrailR5:
        log.error("R5: troppi errori broker. Stop senza archiviare (o tutto o niente).")
        raise SystemExit(1)

    # --- Aggregazione per (symbol, giorno ET) = un "trade" intraday ---
    trades = defaultdict(lambda: {"cashflow": 0.0, "fills": 0})
    realized = 0.0
    for f in fills:
        try:
            qty = float(f["qty"]); price = float(f["price"]); side = f["side"]
        except (KeyError, ValueError):
            continue
        cash = qty * price * (1 if side.startswith("sell") else -1)
        realized += cash
        day = f.get("transaction_time", "")[:10]
        trades[(f.get("symbol"), day)]["cashflow"] += cash
        trades[(f.get("symbol"), day)]["fills"] += 1

    closed = [v["cashflow"] for v in trades.values()]
    n_trades = len(closed)
    wins = [c for c in closed if c > 0]
    win_rate = (len(wins) / n_trades * 100) if n_trades else 0.0
    best = max(closed) if closed else 0.0
    worst = min(closed) if closed else 0.0
    equity = float(acct["equity"])

    report = (
        f"# 📊 Report Settimanale Trading-BOT\n"
        f"**Settimana (ET):** {start.date()} → {end.date()}\n\n"
        f"- **PnL realizzato netto:** ${realized:,.2f}\n"
        f"- **Trade eseguiti:** {n_trades}  (fill totali: {len(fills)})\n"
        f"- **Win rate:** {win_rate:.1f}%  ({len(wins)}/{n_trades})\n"
        f"- **Best trade:** ${best:,.2f}\n"
        f"- **Worst trade:** ${worst:,.2f}\n"
        f"- **Equity fine settimana:** ${equity:,.2f}\n"
    )
    log.info("\n%s", report)

    # --- Notifica opzionale ---
    if notif.get("enabled"):
        url = os.environ.get("RECON_WEBHOOK_URL") or os.environ.get("DISCORD_WEBHOOK_URL")
        if url:
            ok = _send_webhook(url, report) if not dry_run else True
            log.info("Webhook %s", "inviato" if ok else "fallito (proseguo)")
        else:
            log.warning("notifications.enabled ma nessun webhook URL nei secret. Salto.")

    # --- Archiviazione stato (atomica per cartella) ---
    archive_sub = Path(archive_dir) / now_cet().date().isoformat()
    moved = []
    for key, path in files.items():
        p = Path(path)
        if p.exists():
            moved.append(p.name)
            if not dry_run:
                archive_sub.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(archive_sub / p.name))
    if dry_run:
        log.info("DRY-RUN: avrei archiviato %s in %s/", moved, archive_sub)
    else:
        log.info("Archiviati %s in %s/", moved, archive_sub)
        gitsync.sync(f"routine 05 reconciliation {start.date()}..{end.date()}")

    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
