"""
healthcheck.py — verifica di integrita' della DIVISIONE CRIPTO.

Sola lettura: non invia ordini, non scrive stato. Si puo' eseguire quando si
vuole. Serve a rispondere con dei numeri, non a intuito, alla domanda "il bot
cripto e' collegato e separato da quello azionario?".
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ok_count = 0
fail_count = 0


def check(label: str, fn) -> None:
    global ok_count, fail_count
    try:
        detail = fn()
        print(f"  [OK]     {label}" + (f" — {detail}" if detail else ""))
        ok_count += 1
    except Exception as e:  # noqa: BLE001
        print(f"  [FALLITO] {label} — {type(e).__name__}: {str(e)[:160]}")
        fail_count += 1


def main() -> int:
    from crypto.broker import CryptoClient, load_config
    from crypto import signals

    print("=" * 62)
    print("DIVISIONE CRIPTO — verifica di integrita'")
    print("=" * 62)

    cfg = load_config()
    state = {}

    def c_config():
        assert cfg["meta"]["division"] == "crypto"
        return f"{len(cfg['universe']['exclude'])} coppie escluse, " \
               f"{cfg['strategy']['positions_to_open']} posizioni"

    def c_secrets():
        p = REPO_ROOT / cfg["meta"]["secrets_file"]
        assert p.exists(), f"{p.name} assente"
        # Non si stampa MAI il contenuto: solo che le chiavi attese ci sono.
        names = {l.split("=", 1)[0].strip()
                 for l in p.read_text(encoding="utf-8").splitlines()
                 if "=" in l and not l.strip().startswith("#")}
        for need in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
            assert need in names, f"manca {need}"
        return f"{p.name} presente e completo"

    def c_account():
        cli = CryptoClient(cfg)
        state["cli"] = cli
        a = cli.assert_right_account()
        state["acct"] = a
        return f"{a['account_number']} | equity ${float(a['equity']):,.2f}"

    def c_paper():
        assert state["cli"].is_paper, "endpoint NON e' paper"
        assert state["acct"].get("crypto_status") == "ACTIVE", "cripto non abilitate"
        return "conto paper, cripto abilitate"

    def c_separation():
        """Il controllo piu' importante: e' un conto DIVERSO da quello azionario."""
        from lib.alpaca_rest import AlpacaClient
        stock = AlpacaClient(max_consecutive_errors=3).account()
        mine = state["acct"]["account_number"]
        assert stock["account_number"] != mine, "STESSO CONTO DELLE AZIONI!"
        return f"azioni {stock['account_number']} != cripto {mine}"

    def c_assets():
        n = len(state["cli"].crypto_assets())
        assert n > 10, f"solo {n} strumenti"
        return f"{n} coppie negoziabili dal broker"

    def c_universe():
        pairs, _ = signals.discover_universe(state["cli"], cfg)
        state["pairs"] = pairs
        assert len(pairs) >= 5, f"solo {len(pairs)} coppie superano i filtri"
        return f"{len(pairs)} coppie superano spread e liquidita'"

    def c_data():
        start = (dt.date.today() - dt.timedelta(days=120)).isoformat()
        bars = state["cli"].crypto_bars(state["pairs"][:5], start=start)
        short = [k for k, v in bars.items() if len(v) < 90]
        assert not short, f"storico corto per {short}"
        return f"barre giornaliere OK ({min(len(v) for v in bars.values())}+ per coppia)"

    def c_ranking():
        m = signals.compute_metrics(state["cli"], cfg, state["pairs"])
        r = signals.rank(m)
        sel = signals.select(cfg, r)
        w = signals.target_weights(sel, cfg)
        tot = sum(w.values())
        assert 0 < tot <= 1.0, f"esposizione fuori scala: {tot:.2f}"
        top = ", ".join(f"{s['pair'].split('/')[0]}" for s in sel)
        return f"classifica di {len(r)} coppie, selezione [{top}], investito {tot*100:.0f}%"

    def c_risk():
        """Il rischio complessivo deve restare entro limiti dichiarati."""
        m = signals.compute_metrics(state["cli"], cfg, state["pairs"])
        sel = signals.select(cfg, signals.rank(m))
        w = signals.target_weights(sel, cfg)
        rischio = sum(w[s["pair"]] * signals.stop_distance_pct(s, cfg) for s in sel)
        assert rischio < 0.25, f"rischio totale {rischio*100:.1f}% troppo alto"
        return f"perdita massima se scattano tutti gli stop: {rischio*100:.1f}% del capitale"

    def c_state():
        d = REPO_ROOT / cfg["state"]["dir"]
        d.mkdir(parents=True, exist_ok=True)
        t = d / ".healthcheck.tmp"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        return f"{cfg['state']['dir']} scrivibile"

    def c_no_orphans():
        """Posizioni senza protezione: la condizione da non avere mai."""
        cli = state["cli"]
        from crypto.broker import to_pair
        pos = {to_pair(p["symbol"]) for p in cli.crypto_positions()}
        sells = set(cli.open_sell_orders())
        naked = pos - sells
        assert not naked, f"POSIZIONI SCOPERTE: {naked}"
        return f"{len(pos)} posizioni, {len(sells)} protette"

    check("configurazione leggibile", c_config)
    check("file chiavi cripto", c_secrets)
    check("conto raggiungibile e corretto", c_account)
    check("conto paper con cripto attive", c_paper)
    check("SEPARAZIONE dal conto azionario", c_separation)
    check("anagrafica strumenti", c_assets)
    check("universo dopo i filtri", c_universe)
    check("dati storici sufficienti", c_data)
    check("classifica e dimensionamento", c_ranking)
    check("rischio complessivo entro i limiti", c_risk)
    check("cartella di stato scrivibile", c_state)
    check("nessuna posizione senza stop", c_no_orphans)

    print("=" * 62)
    total = ok_count + fail_count
    print(f"Risultato: {ok_count}/{total} controlli superati.")
    if fail_count:
        print(">> Ci sono problemi: NON avviare la divisione cripto.")
        return 1
    print(">> Divisione cripto collegata, separata e operativa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
