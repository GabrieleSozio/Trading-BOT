# 🏦 Trading-BOT — Hedge Fund Multi-Agente (Agentic)

Trading bot azionario USA **autonomo**, costruito come un team multi-agente che
simula un piccolo hedge fund. Non è un programma monolitico: è una **pipeline di 5
routine agentiche** (i "membri del team") schedulate nell'app desktop di Claude
Code. Le routine si passano il lavoro tramite **file JSON locali** e operano sul
broker **Alpaca** attraverso un **server MCP**.

> ⚠️ **Fase 1 = Paper Trading.** Nessun capitale reale finché `paper_trading: true`
> in `config/trading_config.yaml`. Questo non è consiglio finanziario.

---

## 🗂️ Struttura del progetto

```
Trading-BOT/
├── README.md                       # questo file
├── .gitignore
│
├── ROUTINES/                       # ⭐ i 5 membri del team (prompt delle routine schedulate)
│   ├── 01_premarket_analyst.md     #    14:30 CET — trova i Momentum del giorno
│   ├── 02_portfolio_manager.md     #    15:00 CET — pianifica l'allocazione
│   ├── 03_risk_manager.md          #    15:10 CET — applica le Guardrails
│   ├── 04_execution_desk.md        #    15:30–21:46 CET — invia ordini reali (Bracket)
│   └── 05_friday_reconciliation.md #    Ven 23:00 CET — report + pulizia stato
│
├── docs/
│   ├── 00_strategy_and_guardrails.md   # 📜 fonte unica: strategia + 5 regole inviolabili
│   ├── 01_state_contracts.md           # schemi JSON scambiati tra le routine
│   └── prompts_original/               # archivio dei prompt originali (versione Python)
│
├── config/
│   ├── trading_config.yaml         # ⚙️ tutti i parametri (universo, soglie, orari)
│   └── alpaca_mcp.example.json     # esempio di configurazione del server MCP Alpaca
│
├── state/                          # 📦 stato runtime (JSON locali, git-ignored)
│   └── archive/                    #    storico settimanale archiviato da Routine 05
│
└── secrets/                        # 🔐 segreti locali (git-ignored)
    └── alpaca_recovery_code.txt
```

---

## 🔄 Come funziona la "staffetta"

Ogni routine legge gli output delle precedenti, fa la sua parte, scrive il proprio
output. Lo stato condiviso vive in `state/`:

```
01 Analyst   ──▶ market_research.json
02 Portfolio ──▶ target_orders.json
03 Risk      ──▶ approved_orders.json      (qui si applicano le Guardrails)
04 Execution ──▶ daily_executions_log.json (qui si inviano ordini veri)
05 Reconcile ──▶ report settimanale + archivia i file in state/archive/
```

Dettaglio degli schemi: [`docs/01_state_contracts.md`](docs/01_state_contracts.md).

---

## 🛡️ Le 5 Guardrails inviolabili

Definite in [`docs/00_strategy_and_guardrails.md`](docs/00_strategy_and_guardrails.md),
parametrizzate in `config/trading_config.yaml`:

| # | Regola | Valore |
|---|--------|--------|
| R1 | Kill Switch giornaliero | -2% → chiudi tutto e iberna |
| R2 | Max position size | 5% del capitale per trade |
| R3 | Stop loss fisico obbligatorio (Bracket) | -1.5% |
| R4 | Max esposizione di settore | 15% |
| R5 | Soglia errori API broker | 3 consecutivi → stop |

(Take profit Bracket: +3%.)

---

## 🚀 Setup

1. **Chiavi Alpaca (paper):** crea un account su Alpaca e genera le API key paper.
   Le chiavi **non** vanno in un file: si impostano come **variabili secret della
   singola routine** quando la registri nell'app desktop (ogni routine che opera sul
   broker porta con sé le proprie credenziali).
2. **Server MCP Alpaca (opzionale ma consigliato):** usa
   `config/alpaca_mcp.example.json` come riferimento; le credenziali vengono iniettate
   dalle variabili della routine. Deve esporre: account
   (buying_power/portfolio_value/equity), market data, Bracket Order, lista/cancella
   ordini, lista/chiudi posizioni, account activities.
3. **Rivedi i parametri** in `config/trading_config.yaml` (universo titoli, soglie, orari).
4. **Registra le routine:** in Claude Code crea una routine schedulata per ciascun
   file in `ROUTINES/`, agli orari CET indicati nell'intestazione, impostando le
   variabili secret (chiavi Alpaca, eventuale webhook) di ciascuna.

---

## ✅ Convenzioni operative

- **Linguaggio:** le routine sono prompt agentici, non script. Modifichi il
  comportamento editando il `.md` della routine o la config — non c'è codice da compilare.
- **Fonte unica di verità:** i numeri stanno in `config/trading_config.yaml`; la
  strategia in `docs/00_strategy_and_guardrails.md`. Le routine vi fanno riferimento,
  non duplicano valori.
- **Fail loud:** input mancante o API muta ⇒ la routine logga ERROR ed esce, mai
  inventa dati o ordini.
- **Solo intraday:** flat obbligatorio a fine giornata, nessun overnight.

---

## 🔐 Sicurezza

`secrets/` e `.env` sono git-ignored. Il file `secrets/alpaca_recovery_code.txt`
(spostato qui dalla root) è il **codice di recovery del 2FA Alpaca**: tienilo
offline e **non committarlo mai**. Se questa cartella è già finita in un repo
remoto in passato, **rigenera il recovery code** da Alpaca.
