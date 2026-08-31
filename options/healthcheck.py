"""
healthcheck.py — verifica di integrita' della DIVISIONE OPZIONI.

Sola lettura: non invia ordini, non scrive stato. Risponde con numeri, non a
intuito, alla domanda "la divisione opzioni e' collegata, separata e sana?".
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ok_count = fail_count = 0


def check(label: str, fn) -> None:
    global ok_count, fail_count
    try:
        d = fn()
        print(f"  [OK]     {label}" + (f" — {d}" if d else ""))
        ok_count += 1
    except Exception as e:  # noqa: BLE001
        print(f"  [FALLITO] {label} — {type(e).__name__}: {str(e)[:160]}")
        fail_count += 1


def main() -> int:
    from options.broker import OptionsClient, load_config, MOLTIPLICATORE
    from options import routine_o1_select as o1
    from lib import pdt

    print("=" * 66)
    print("DIVISIONE OPZIONI — verifica di integrita'")
    print("=" * 66)
    cfg = load_config()
    S = {}

    def c_config():
        assert cfg["meta"]["division"] == "options"
        return (f"{len(cfg['universe']['tickers'])} titoli, contratti entro "
                f"{cfg['contract']['max_otm_pct']:.0f}% dal denaro")

    def c_secrets():
        p = REPO_ROOT / cfg["meta"]["secrets_file"]
        assert p.exists(), f"{p.name} assente"
        nomi = {l.split("=", 1)[0].strip() for l in p.read_text(encoding="utf-8").splitlines()
                if "=" in l and not l.strip().startswith("#")}
        for n in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
            assert n in nomi, f"manca {n}"
        return f"{p.name} presente e completo"

    def c_account():
        cli = OptionsClient(cfg)
        S["cli"] = cli
        a = cli.assert_right_account()
        S["acct"] = a
        return f"{a['account_number']} | equity ${float(a['equity']):,.2f}"

    def c_livello():
        a = S["acct"]
        assert S["cli"].is_paper, "endpoint NON paper"
        assert int(a.get("options_trading_level") or 0) >= 1, "opzioni non abilitate"
        return f"paper, livello opzioni {a['options_trading_level']}"

    def c_separazione():
        """Il controllo piu' importante: conto diverso da azioni E da cripto."""
        from lib.alpaca_rest import AlpacaClient
        mio = S["acct"]["account_number"]
        altri = {}
        for nome, f in (("azioni", "secrets/alpaca_keys.env"),
                        ("cripto", "secrets/alpaca_crypto_keys.env")):
            n = AlpacaClient(max_consecutive_errors=3,
                             secrets_file=REPO_ROOT / f).account()["account_number"]
            assert n != mio, f"STESSO CONTO DI {nome.upper()}!"
            altri[nome] = n
        return "distinto da " + ", ".join(f"{k} {v}" for k, v in altri.items())

    def c_catena():
        cli, cand = S["cli"], cfg["universe"]["tickers"][:3]
        snap = cli.snapshots(cand, feed="delayed_sip")
        n = 0
        for t in cand:
            s = (snap.get(t) or {}).get("latestTrade", {}).get("p")
            if s:
                n += len(cli.chain(t, s, cfg["contract"]["type"], 14, 35))
        assert n > 0, "nessun contratto raggiungibile"
        return f"{n} contratti leggibili su {len(cand)} titoli di prova"

    def c_segnale():
        righe = o1._segnale(S["cli"], cfg)
        return (f"{len(righe)} candidati in rialzo oggi"
                if righe else "nessun titolo in rialzo (normale in giornate deboli)")

    def c_acquistabilita():
        """Almeno qualche titolo deve avere contratti nei limiti, altrimenti la
        divisione non potrebbe mai operare e non sarebbe evidente il perche'."""
        cli = S["cli"]
        eq = float(S["acct"]["equity"])
        budget = eq * float(cfg["modes"]["swing"]["max_premium_pct"])
        snap = cli.snapshots(cfg["universe"]["tickers"][:8], feed="delayed_sip")
        trovati = 0
        for t in cfg["universe"]["tickers"][:8]:
            s = (snap.get(t) or {}).get("latestTrade", {}).get("p")
            if s and o1.scegli_contratto(cli, cfg, t, s, "swing", budget):
                trovati += 1
        assert trovati > 0, "nessun contratto acquistabile su 8 titoli di prova"
        return f"{trovati} titoli su 8 hanno contratti entro {budget:.0f}$"

    def c_pdt():
        usati, _ = pdt.count_recent_day_trades(S["cli"])
        usabili = int(cfg["guardrails"]["day_trades_usable"])
        tot = int(cfg["guardrails"]["day_trades_total"])
        assert usabili < tot, "nessun credito di riserva: rischio blocco a 90 giorni"
        return f"{usati} usati, {usabili} utilizzabili, 1 di riserva su {tot}"

    def c_state():
        d = REPO_ROOT / cfg["state"]["dir"]
        d.mkdir(parents=True, exist_ok=True)
        t = d / ".healthcheck.tmp"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        return f"{cfg['state']['dir']} scrivibile"

    def c_orfani():
        """Ordini appesi che immobilizzano liquidita' senza eseguirsi."""
        cli = S["cli"]
        ap = cli.list_orders(status="open")
        pos = cli.option_positions()
        assert len(ap) <= len(pos) + 2, f"{len(ap)} ordini aperti: sospetto accumulo"
        val = sum(abs(float(p.get("market_value") or 0)) for p in pos)
        return f"{len(pos)} posizioni (${val:,.2f}), {len(ap)} ordini aperti"

    check("configurazione leggibile", c_config)
    check("file chiavi opzioni", c_secrets)
    check("conto raggiungibile e corretto", c_account)
    check("conto paper con opzioni abilitate", c_livello)
    check("SEPARAZIONE dagli altri due conti", c_separazione)
    check("catene di contratti raggiungibili", c_catena)
    check("segnale calcolabile sull'universo", c_segnale)
    check("contratti effettivamente acquistabili", c_acquistabilita)
    check("crediti intraday con riserva", c_pdt)
    check("cartella di stato scrivibile", c_state)
    check("nessun ordine orfano", c_orfani)

    print("=" * 66)
    tot = ok_count + fail_count
    print(f"Risultato: {ok_count}/{tot} controlli superati.")
    if fail_count:
        print(">> Ci sono problemi: NON avviare la divisione opzioni.")
        return 1
    print(">> Divisione opzioni collegata, separata e operativa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
