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
from . import ai_client, capital as cap_mod, gitsync
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


def _closed_round_trips(fills: list) -> list:
    """P&L dei round-trip effettivamente CHIUSI, abbinando acquisti e vendite.

    Non si puo' raggruppare per (titolo, giorno): in swing una posizione dura piu'
    giorni, quindi l'acquisto e la vendita finirebbero in due "operazioni" distinte
    (una enorme perdita e un enorme guadagno, entrambi falsi). Qui si segue la
    posizione nel tempo con il suo prezzo medio e si realizza il P&L solo quando
    viene ridotta o chiusa. Gestisce sia long sia short.
    """
    by_symbol = defaultdict(list)
    for f in sorted(fills, key=lambda x: x.get("transaction_time", "")):
        if f.get("symbol"):
            by_symbol[f["symbol"]].append(f)

    out = []
    for sym, lst in by_symbol.items():
        qty_pos, avg, realized = 0.0, 0.0, 0.0
        for f in lst:
            try:
                q = float(f["qty"]) * (1 if f.get("side", "").startswith("buy") else -1)
                price = float(f["price"])
            except (KeyError, TypeError, ValueError):
                continue
            if qty_pos == 0 or (qty_pos > 0) == (q > 0):
                # apertura o incremento: aggiorna il prezzo medio di carico
                tot = abs(qty_pos) + abs(q)
                avg = (avg * abs(qty_pos) + price * abs(q)) / tot if tot else 0.0
                qty_pos += q
            else:
                # riduzione o chiusura: qui si realizza il risultato
                closing = min(abs(q), abs(qty_pos))
                realized += closing * (price - avg) * (1 if qty_pos > 0 else -1)
                qty_pos += q
                if abs(qty_pos) < 1e-9:          # posizione chiusa del tutto
                    out.append((sym, round(realized, 2)))
                    qty_pos, avg, realized = 0.0, 0.0, 0.0
                elif (qty_pos > 0) != (q < 0):   # ribaltata: riparte da capo
                    avg = price
    return out


def _perf_summary(client: AlpacaClient) -> dict:
    """Performance reale dell'ultima settimana lavorativa, dal broker."""
    now = now_cet().astimezone(US_EASTERN)
    monday = now.date() - dt.timedelta(days=now.weekday())
    start = dt.datetime.combine(monday, dt.time(0, 0), tzinfo=US_EASTERN)
    fills = client.activities("FILL", after=start.isoformat())
    acct = client.account()
    positions = client.list_positions()

    trips = _closed_round_trips(fills)
    pnls = [p for _s, p in trips]
    wins = [p for p in pnls if p > 0]
    unrealized = sum(float(p.get("unrealized_pl", 0)) for p in positions)
    return {
        "equity": float(acct["equity"]),
        "realized_pnl_closed_trades": round(sum(pnls), 2),
        "n_closed_trades_week": len(pnls),
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 1) if pnls else 0.0,
        "best_trade": round(max(pnls), 2) if pnls else 0.0,
        "worst_trade": round(min(pnls), 2) if pnls else 0.0,
        "closed_detail": [f"{s} {p:+.2f}" for s, p in trips],
        "open_positions": [f"{p['symbol']} qty={p['qty']} uPL={p.get('unrealized_pl')}" for p in positions],
        "unrealized_pnl_open": round(unrealized, 2),
        "n_fills_week": len(fills),
        "note": "P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.",
    }


def _current_value(cfg: dict, param: str, tier: dict):
    """Valore attuale. I parametri 'tier.<x>' si riferiscono alla FASCIA ATTIVA."""
    if param.startswith("tier."):
        return tier[param.split(".", 1)[1]]
    node = cfg
    for part in param.split("."):
        node = node[part]
    return node


def _validate(param: str, raw_value, tunable: dict, forbidden: list,
              tier: dict) -> tuple[bool, object, str]:
    """Ritorna (ok, valore_validato, motivo_rifiuto).

    Oltre a whitelist e range, applica un INVARIANTE di sicurezza: il capitale
    complessivamente allocabile (posizioni x size) non puo' superare il 100%.
    Cosi' l'AI puo' cambiare il numero di posizioni senza mai creare sovra-esposizione.
    """
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
    if param == "tier.positions_to_open":
        esposizione = val * float(tier["max_position_size_pct"])
        if esposizione > 1.0:
            return False, None, (f"sovra-esposizione: {val} posizioni x "
                                 f"{tier['max_position_size_pct']*100:.0f}% = "
                                 f"{esposizione*100:.0f}% del capitale (max 100%)")
    if param == "tier.max_hold_days" and cap_mod.is_intraday(tier):
        return False, None, "max_hold_days non ha effetto in modalita' intraday"
    return True, val, ""


def _apply_to_config(param: str, new_value, tier_name: str | None = None) -> bool:
    """Sostituisce il valore nel YAML preservando i commenti.

    Per i parametri 'tier.<x>' la modifica e' circoscritta al blocco della fascia
    indicata: senza questo, una sostituzione globale colpirebbe la prima fascia
    del file invece di quella attiva.
    """
    leaf = param.split(".")[-1]
    lines = CONFIG_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = 0, len(lines)

    if param.startswith("tier."):
        if not tier_name:
            log.error("Modifica di fascia senza nome fascia: rifiutata.")
            return False
        start = next((i for i, l in enumerate(lines)
                      if re.match(rf"^\s*-\s*name:\s*{re.escape(tier_name)}\s*$", l)), -1)
        if start < 0:
            log.error("Fascia '%s' non trovata nel config.", tier_name)
            return False
        end = next((i for i in range(start + 1, len(lines))
                    if re.match(r"^\s*-\s*name:\s*", lines[i])), len(lines))

    pattern = re.compile(rf"^(\s*{re.escape(leaf)}:\s*)([^\s#]+)(.*)$")
    for i in range(start, end):
        m = pattern.match(lines[i])
        if m:
            lines[i] = f"{m.group(1)}{new_value}{m.group(3)}\n"
            CONFIG_FILE.write_text("".join(lines), encoding="utf-8")
            return True
    log.error("Impossibile localizzare '%s' nel config (fascia=%s).", leaf, tier_name)
    return False


def run(dry_run: bool = False) -> str:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    sup = cfg.get("supervisor", {})
    if not sup.get("enabled"):
        log.info("Supervisore disabilitato in config. Esco.")
        return ""
    forbidden = sup.get("forbidden_prefixes", [])
    model = cfg.get("ai", {}).get("supervisor_model")

    client = AlpacaClient(max_consecutive_errors=cfg["guardrails"]["max_consecutive_api_errors"])
    try:
        perf = _perf_summary(client)
    except GuardrailR5:
        log.error("R5: troppi errori broker. Stop.")
        sys.exit(1)

    # Contesto: il bot cambia strategia con il capitale, l'AI deve saperlo.
    cap_usd, simulated = cap_mod.effective_capital(cfg, perf["equity"], client)
    tier = cap_mod.resolve_tier(cfg, cap_usd)

    # Il conto paper ha ~100k, ma la strategia opera su una frazione simulata.
    # Senza chiarirlo l'AI legge due cifre incoerenti e diffida dei propri dati.
    perf["saldo_conto_paper"] = perf.pop("equity")
    perf["capitale_operativo_strategia"] = cap_usd
    if cap_usd:
        perf["rendimento_settimana_pct"] = round(
            perf["realized_pnl_closed_trades"] / cap_usd * 100, 2)
    perf["nota_capitale"] = (
        "Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni "
        "SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). "
        "Valuta le performance in rapporto a quest'ultimo, non al saldo del conto."
    )

    # Parametri modificabili: globali + quelli DELLA FASCIA ATTIVA (prefissati
    # 'tier.'). I limiti di protezione (stop, size, drawdown, short, mode)
    # restano fuori dalla whitelist e quindi intoccabili.
    tunable = dict(sup.get("tunable", {}))
    for p, spec in (sup.get("tier_tunable") or {}).items():
        tunable[f"tier.{p}"] = spec
    current = {p: _current_value(cfg, p, tier) for p in tunable}
    log.info("%s", cap_mod.describe(tier, cap_usd, simulated))
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
        "I parametri che iniziano con 'tier.' agiscono sulla fascia di capitale ATTIVA. "
        "NON puoi toccare i limiti di protezione (stop loss, dimensione massima per "
        "posizione, kill switch, short, modalita' intraday/swing), il flag paper o gli "
        "orari: sono esclusi apposta e ogni proposta in tal senso verra' rifiutata. "
        "Un vincolo e' verificato dal codice: posizioni x dimensione non puo' superare "
        "il 100% del capitale. "
        "Se i dati sono insufficienti o tutto va bene, restituisci changes vuoto: "
        "non modificare per il gusto di modificare. "
        "Rispondi solo nel formato JSON richiesto, in italiano."
    )
    user = (
        f"Contesto operativo: {cap_mod.describe(tier, cap_usd, simulated)}.\n"
        f"(Il bot adatta da solo strategia e limiti al capitale: sotto i 25.000 USD opera "
        f"in swing su piu' giorni per non incorrere nella regola Pattern Day Trader, "
        f"sopra torna all'intraday. Questi limiti NON sono modificabili da te.)\n\n"
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
        ok, val, why = _validate(param, ch.get("new_value"), tunable, forbidden, tier)
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
        if _apply_to_config(param, val, tier["name"]):
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
