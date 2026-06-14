"""
healthcheck.py — verifica che tutti gli anelli del bot siano collegati.

Esegue controlli NON distruttivi (nessun ordine, nessun commit) e stampa un report
PASS/FAIL. Usalo quando vuoi sapere "è tutto collegato?".

Uso:  python -m lib.healthcheck
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from . import alpaca_rest as R

OK = "PASS"
KO = "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, fn):
    try:
        detail = fn()
        results.append((OK, name, detail or ""))
    except Exception as e:  # noqa: BLE001
        results.append((KO, name, f"{type(e).__name__}: {e}"))


def main():
    cfg_holder = {}

    def _config():
        cfg = R.load_config()
        cfg_holder["cfg"] = cfg
        assert cfg["meta"]["paper_trading"] is True, "paper_trading non è True!"
        return f"paper_trading={cfg['meta']['paper_trading']} universo={len(cfg['universe']['tickers'])} ticker"
    check("config + paper mode", _config)

    cli_holder = {}

    def _client():
        cli = R.AlpacaClient(max_consecutive_errors=3)
        cli_holder["cli"] = cli
        assert cli.is_paper, "endpoint NON è paper!"
        return "credenziali caricate, endpoint paper"
    check("secrets + client Alpaca", _client)

    def _account():
        acct = cli_holder["cli"].account()
        assert acct["status"] == "ACTIVE", f"account status {acct['status']}"
        assert not acct["trading_blocked"], "trading bloccato!"
        return f"{acct['account_number']} equity={acct['equity']} bp={acct['buying_power']}"
    check("Alpaca: account (trading)", _account)

    def _clock():
        clk = cli_holder["cli"].clock()
        td = cli_holder["cli"].is_trading_day()
        return f"is_open={clk['is_open']} giorno_di_borsa_oggi={td} next_open={clk['next_open']}"
    check("Alpaca: clock + calendario", _clock)

    def _data():
        snap = cli_holder["cli"].snapshots(["AAPL", "NVDA"])
        a = (snap.get("AAPL") or {}).get("latestTrade", {}).get("p")
        n = (snap.get("NVDA") or {}).get("latestTrade", {}).get("p")
        assert a and n, "snapshot vuoto"
        return f"AAPL={a} NVDA={n} (feed IEX)"
    check("Alpaca: market data", _data)

    def _state():
        d = Path(cfg_holder["cfg"]["state"]["dir"])
        tmp = d / "_healthcheck.tmp.json"
        R.atomic_write_json(tmp, {"ok": True})
        data = R.read_json(tmp)
        tmp.unlink()
        assert data["ok"] is True
        return f"scrittura atomica OK in {d}/"
    check("cartella state scrivibile", _state)

    def _git():
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run(["git", "-C", str(root), "ls-remote", "--heads", "origin"],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr.strip()
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True).stdout.strip()
        return f"remote raggiungibile: {url}"
    check("GitHub: accesso remoto", _git)

    def _modules():
        import importlib
        mods = ["routine_01_premarket", "routine_02_portfolio", "routine_03_risk",
                "routine_04_execution", "routine_05_reconciliation", "gitsync", "sectors"]
        for m in mods:
            importlib.import_module(f"lib.{m}")
        return f"{len(mods)} moduli importati senza errori"
    check("moduli routine importabili", _modules)

    # --- Report ---
    print("\n================ HEALTH CHECK Trading-BOT ================")
    width = max(len(n) for _, n, _ in results)
    n_ok = 0
    for status, name, detail in results:
        mark = "[OK]  " if status == OK else "[FAIL]"
        if status == OK:
            n_ok += 1
        print(f"{mark} {name.ljust(width)}  {detail}")
    print("=========================================================")
    print(f"Risultato: {n_ok}/{len(results)} controlli superati.")
    if n_ok != len(results):
        print(">> Qualcosa NON è collegato: vedi i [FAIL] qui sopra.")
        sys.exit(1)
    print(">> Tutte le integrazioni sono collegate e funzionanti.")


if __name__ == "__main__":
    main()
