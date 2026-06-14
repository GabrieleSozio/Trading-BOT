# 00 — Strategia & Guardrails (Fonte Unica di Verità)

> Questo è il documento canonico del sistema. Ogni routine agentica DEVE leggerlo
> all'avvio. Le costanti numeriche vivono in [`config/trading_config.yaml`](../config/trading_config.yaml):
> in caso di dubbio, la config vince. Non duplicare valori a memoria.

---

## 1. Scopo & Architettura

Trading bot azionario USA **completamente autonomo**, strutturato come un team
multi-agente che simula un piccolo hedge fund. Il sistema **non** è un monolite:
è una pipeline di **5 routine agentiche indipendenti** (i "membri del team"),
ciascuna schedulata nell'app desktop di Claude Code.

- **Esecuzione:** ogni membro è una *routine* (agente schedulato), non uno script Python.
- **Comunicazione (State Management):** le routine si passano il lavoro tramite
  **file JSON locali** nella cartella [`state/`](../state/). Nessun database.
- **Broker & dati:** Alpaca Markets, esposto agli agenti tramite **MCP server**
  (vedi [`config/alpaca_mcp.example.json`](../config/alpaca_mcp.example.json)).
- **Fase 1:** Paper Trading (gratuito). Nessun capitale reale finché non si
  rimuove esplicitamente il flag paper in config.

### Flusso giornaliero (la "staffetta")

```
14:30 CET ─ 01 Premarket Analyst ──▶ state/market_research.json
15:00 CET ─ 02 Portfolio Manager ──▶ state/target_orders.json
15:10 CET ─ 03 Risk Manager      ──▶ state/approved_orders.json   (applica le Guardrails)
15:30–21:46 CET ─ 04 Execution Desk ─▶ invia ordini reali + state/daily_executions_log.json
Venerdì 23:00 CET ─ 05 Reconciliation ─▶ report settimanale + pulizia state/
```

Ogni routine: (1) legge i JSON prodotti dalle routine precedenti, (2) esegue la
propria logica usando i tool MCP di Alpaca, (3) scrive il proprio JSON di output.

---

## 2. Strategia di Trading: Momentum Intraday

Operatività **esclusivamente intraday** (day-trading): si apre e si chiude tutto
nella stessa giornata per azzerare il rischio overnight. Strategia base:
**"Momentum con Filtro di Ritracciamento"**.

- **Identificazione:** asset con forte direzionalità e alti volumi in pre-market/apertura.
- **Entry:** non si compra sul picco. Si attende un leggero ritracciamento
  fisiologico per un prezzo d'ingresso migliore.
- **Exit (Flat obbligatorio):** 15 minuti prima della chiusura tutte le posizioni
  vengono liquidate. **Nessun titolo overnight, mai.**

---

## 3. The Guardrails — Regole Inviolabili (CRITICO)

Queste regole sono il cuore della gestione del rischio. Sono codificate come
valori in `config/trading_config.yaml` e applicate da **03 Risk Manager** e
verificate/eseguite da **04 Execution Desk**. Una routine che non può rispettare
una guardrail si ferma e logga, **non** improvvisa.

| # | Regola | Valore | Owner |
|---|--------|--------|-------|
| **R1** | **Hard Daily Stop-Loss (Kill Switch)** — se il portafoglio scende del **-2%** vs apertura, chiudi tutte le posizioni a mercato, cancella gli ordini pendenti e iberna fino al giorno dopo. | `-2%` | 04 Execution |
| **R2** | **Maximum Position Size** — nessun trade impegna più del **5%** del capitale totale. | `5%` | 03 Risk |
| **R3** | **Mandatory Physical Stop Loss** — ogni acquisto va inviato come **Bracket Order** con stop loss tra **-1% e -1.5%** dal prezzo d'ingresso. | `-1.5%` | 03 Risk + 04 Execution |
| **R4** | **Maximum Sector Correlation** — il capitale in un singolo settore (es. Tech) non supera il **15%** del totale. | `15%` | 03 Risk |
| **R5** | **API Error & Latency Threshold** — dopo **3 errori consecutivi** dal broker (timeout/5xx), la routine si ferma, logga e si sospende. Niente loop disastrosi. | `3` | tutte |

**Take Profit:** ogni Bracket Order include un take profit a **+3%** dal prezzo d'ingresso.

---

## 4. Principi operativi per ogni agente

1. **Leggi prima, agisci dopo.** All'avvio leggi questo file e la config.
2. **Fail loud, never silent.** Se un input manca o un'API non risponde, logga
   un ERROR esplicito ed esci con stato di errore. Mai inventare dati.
3. **Idempotenza.** Se rilanciata, una routine non deve duplicare ordini già
   inviati: controlla sempre lo stato reale su Alpaca prima di agire.
4. **Solo Paper finché non detto altrimenti.** Verifica `paper_trading: true` in config.
5. **Timezone.** Tutti gli orari sono **CET**. Converti sempre in modo esplicito
   (CET ↔ US/Eastern ↔ UTC) quando interroghi il broker.
6. **Credenziali.** Le chiavi API Alpaca (e gli eventuali webhook) **non** stanno in
   file `.env` o nel repo: sono **variabili secret della singola routine**, impostate
   nell'app desktop. Ogni routine che opera sul broker porta con sé le proprie chiavi.
   Non scrivere mai le chiavi nei file di stato o nei log.
