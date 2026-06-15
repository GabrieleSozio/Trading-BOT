"""
Routine 06 — Supervisore AI (Performance Review & Tuning).

Claude analizza la performance reale del bot e propone/applica MIGLIORAMENTI, ma
SOLO sui parametri in whitelist e dentro i range definiti in config (sezione
`supervisor`). Non può MAI toccare le guardrail, il flag paper, gli orari o lo stato.
Ogni modifica è validata dal codice (non ci si fida dell'AI), motivata e committata.

Se l'AI non è disponibile: logga ed esce senza modifiche (il bot non si ferma).

Uso:  python -m lib.routine_06_supervisor [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

from .alpaca_rest import (
    AlpacaClient,
    GuardrailR5,
    CONFIG_FILE,
    load_config,
    now_cet,
    US_EASTERN,
)
from . import ai_client, gitsync
from .ai_client import AIUnavailable

log = logging.getLogger("routine06")

_AI_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "analysis": {"type": "string"},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "param": {"type": "string"},
                    "new_value": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["param", "new_value", "reason"],
            },
        },
    },
    "required": ["analysis", "changes"],
}


def _perf_summary(client: AlpacaClient) -> dict:
    """Performance reale dell'ultima settimana lavorativa, dal broker."""
    now = now_cet().astimezone(US_EASTERN)
    monday = now.date() - dt.timedelta(days=now.weekday())
    start = dt.datetime.combine(monday, dt.time(0, 0), tzinfo=US_EASTERN)
    fills = client.activities("FILL", after=start.isoformat())
    acct = client.account()
    positions = client.list_positions()
    open_symbols = {p["symbol"] for p in positions}
    # PnL realizzato attendibile solo per i simboli NON più aperti (round-trip chiusi).
    trades = defaultdict(float)
    for f in fills:
        try:
            qty = float(f["qty"]); price = float(f["price"]); side = f["side"]
        except (KeyError, ValueError):
            continue
        cash = qty * price * (1 if side.startswith("sell") else -1)
        trades[(f.get("symbol"), f.get("transaction_time", "")[:10])] += cash
    closed = [c for (sym, _d), c in trades.items() if sym not in open_symbols]
    wins = [c for c in closed if c > 0]
    unrealized = sum(float(p.get("unrealized_pl", 0)) for p in positions)
    return {
        "equity": float(acct["equity"]),
        "realized_pnl_closed_trades": round(sum(closed), 2),
        "n_closed_trades_week": len(closed),
        "win_rate_pct": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
        "best_trade": round(max(closed), 2) if closed else 0.0,
        "worst_trade": round(min(closed), 2) if closed else 0.0,
        "open_positions": [f"{p['symbol']} qty={p['qty']} uPL={p.get('unrealized_pl')}" for p in positions],
        "unrealized_pnl_open": round(unrealized, 2),
        "n_fills_week": len(fills),
        "note": "PnL realizzato = solo round-trip chiusi; le posizioni aperte sono a parte. Affidabile al meglio nel run di fine settimana (flat).",
    }


def _current_value(cfg: dict, param: str):
    node = cfg
    for part in param.split("."):
        node = node[part]
    return node


def _validate(param: str, raw_value, tunable: dict, forbidden: list) -> tuple[bool, object, str]:
    """Ritorna (ok, valore_validato, motivo_rifiuto)."""
    top = param.split(".")[0]
    if top in forbidden:
        return False, None, f"parametro vietato (prefisso '{top}')"
    if param not in tunable:
        return False, None, "fuori dalla whitelist dei parametri modificabili"
    spec = tunable[param]
    try:
        val = int(raw_value) if spec.get("type") == "int" else float(raw_value)
    except (TypeError, ValueError):
        return False, None, "valore non numerico"
    lo, hi = spec["min"], spec["max"]
    if val < lo or val > hi:
        return False, None, f"fuori range [{lo}, {hi}]"
    return True, val, ""


def _apply_to_config(param: str, new_value) -> bool:
    """Sostituisce il valore del leaf-key nel file YAML preservando i commenti."""
    leaf = param.split(".")[-1]
    text = CONFIG_FILE.read_text(encoding="utf-8")
    pattern = re.compile(rf"^(\s*{re.escape(leaf)}:\s*)([^\s#]+)(.*)$", re.MULTILINE)
    new_text, n = pattern.subn(rf"\g<1>{new_value}\g<3>", text, count=1)
    if n != 1:
        log.error("Impossibile localizzare '%s' nel config (match=%d).", leaf, n)
        return False
    CONFIG_FILE.write_text(new_text, encoding="utf-8")
    return True


def run(dry_run: bool = False) -> str:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    sup = cfg.get("supervisor", {})
    if not sup.get("enabled"):
        log.info("Supervisore disabilitato in config. Esco.")
        return ""
    tunable = sup.get("tunable", {})
    forbidden = sup.get("forbidden_prefixes", [])
    model = cfg.get("ai", {}).get("supervisor_model")

    client = AlpacaClient(max_consecutive_errors=cfg["guardrails"]["max_consecutive_api_errors"])
    try:
        perf = _perf_summary(client)
    except GuardrailR5:
        log.error("R5: troppi errori broker. Stop.")
        sys.exit(1)

    current = {p: _current_value(cfg, p) for p in tunable}
    log.info("Performance: %s", perf)
    log.info("Parametri attuali (modificabili): %s", current)

    # --- L'AI analizza e propone (entro i limiti che le dichiariamo) ---
    bounds_desc = "\n".join(
        f"- {p}: attuale={current[p]} | consentito [{s['min']}, {s['max']}] ({s.get('type')})"
        for p, s in tunable.items()
    )
    system = (
        "Sei il Chief Investment Officer di un piccolo hedge fund algoritmico in fase "
        "PAPER. Analizzi la performance del bot e proponi miglioramenti PRUDENTI. "
        "Puoi modificare SOLO i parametri elencati, restando NEI RANGE indicati. "
        "NON puoi toccare le regole di rischio (guardrail), il flag paper, gli orari. "
        "Se i dati sono insufficienti o tutto va bene, restituisci changes vuoto. "
        "Rispondi solo nel formato JSON richiesto, in italiano."
    )
    user = (
        f"Performance ultima settimana (dati reali dal broker):\n{perf}\n\n"
        f"Parametri modificabili e range consentiti:\n{bounds_desc}\n\n"
        f"Proponi 0 o più modifiche (param, new_value, reason). Sii conservativo: "
        f"cambia solo se c'è una motivazione chiara dai dati."
    )
    try:
        data = ai_client.ask_json(system, user, _AI_SCHEMA, model=model, max_tokens=2500)
    except AIUnavailable as e:
        log.warning("AI non disponibile (%s): nessuna analisi/modifica. Esco.", e)
        return ""

    analysis = data.get("analysis", "")
    proposed = data.get("changes", []) or []
    applied, rejected = [], []
    for ch in proposed:
        param = ch.get("param", "")
        ok, val, why = _validate(param, ch.get("new_value"), tunable, forbidden)
        if not ok:
            rejected.append((param, ch.get("new_value"), why))
            log.warning("RIFIUTATA modifica %s=%s: %s", param, ch.get("new_value"), why)
            continue
        if val == current.get(param):
            log.info("Modifica %s invariata (%s): salto.", param, val)
            continue
        if dry_run:
            log.info("DRY-RUN: applicherei %s: %s -> %s (%s)", param, current[param], val, ch.get("reason"))
            applied.append((param, current[param], val, ch.get("reason")))
            continue
        if _apply_to_config(param, val):
            applied.append((param, current[param], val, ch.get("reason")))
            log.info("APPLICATA %s: %s -> %s (%s)", param, current[param], val, ch.get("reason"))

    # --- Report ---
    today = now_cet().date().isoformat()
    lines = [f"# 🤖 Supervisore AI — {today}", "", "## Performance settimana", ""]
    lines += [f"- **{k}:** {v}" for k, v in perf.items()]
    lines += ["", "## Analisi", "", analysis or "(nessuna)", "", "## Modifiche applicate", ""]
    lines += ([f"- `{p}`: {old} → {new} — {why}" for p, old, new, why in applied] or ["- nessuna"])
    if rejected:
        lines += ["", "## Proposte RIFIUTATE (fuori limiti)", ""]
        lines += [f"- `{p}` = {v}: {why}" for p, v, why in rejected]
    report = "\n".join(lines)
    log.info("\n%s", report)

    report_path = Path(cfg["state"]["dir"]) / f"supervisor_report_{today}.md"
    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        gitsync.sync(f"routine 06 supervisore {today} ({len(applied)} modifiche)")
    else:
        log.info("DRY-RUN: nessun file scritto, nessun commit.")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
