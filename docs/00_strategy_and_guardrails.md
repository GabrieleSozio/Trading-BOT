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

## 2. Strategia di Trading: Momentum adattivo al capitale

Strategia base: **"Momentum con Filtro di Ritracciamento"** — si entra su titoli
con forte direzionalità e alti volumi, ma **non sul picco**: si attende un leggero
ritracciamento per un prezzo d'ingresso migliore.

**La modalità di uscita, però, dipende dalla dimensione del conto.** Il motivo è
regolamentare, non discrezionale: la regola USA **Pattern Day Trader (PDT)** vieta
più di **3 operazioni intraday ogni 5 giorni lavorativi** ai conti sotto i
**25.000 USD**. Un bot puramente intraday su un conto piccolo verrebbe bloccato
dopo pochi giorni.

Il bot legge quindi il proprio capitale e adotta la **fascia** corrispondente
(definite in `config/trading_config.yaml` → `tiers`):

| Fascia | Capitale | Modalità | Posizioni | Size | Stop / Target | Short | Uscita |
|---|---|---|---|---|---|---|---|
| **micro** | < $2.000 | **swing** | 2 | 45% | -3% / +6% | no | max 5 giorni di borsa |
| **small** | $2k–25k | **swing** | 3 | 30% | -3% / +6% | no | max 5 giorni di borsa |
| **standard** | ≥ $25.000 | **intraday** | 3 | 5% | -1,5% / +3% | sì | flat obbligatorio la sera |

- **Swing** (capitale piccolo): le posizioni restano aperte più giorni — non sono
  day-trade, quindi **non consumano crediti PDT**. Stop e take profit sono inviati
  come **bracket GTC**, così restano attivi sul broker anche di notte. Una posizione
  che supera `max_hold_days` viene chiusa comunque.
- **Intraday** (capitale ≥ 25k): comportamento classico, **flat obbligatorio** 15
  minuti prima della chiusura, nessun titolo overnight.

### Accessibilità dei titoli
Il bot opera con **azioni intere** (le frazioni non supportano lo stop-loss fisico).
La Routine 01 scarta quindi automaticamente i titoli il cui prezzo per azione supera
la quota allocabile (`capitale × max_position_size_pct`): con $220 e il 45%, sono
operabili solo titoli sotto i ~$99.

### Capitale operativo e simulazione
Il dimensionamento non usa il buying power ma il **capitale operativo**
(`config → capital.simulated_usd`). Se impostato > 0, il bot opera come se avesse
quella cifra (mai più dell'equity reale): serve a **provare in paper la strategia
che si userà davvero** con capitale ridotto. A 0 usa l'equity reale del conto.

---

## 3. The Guardrails — Regole Inviolabili (CRITICO)

Queste regole sono il cuore della gestione del rischio. Sono codificate come
valori in `config/trading_config.yaml` e applicate da **03 Risk Manager** e
verificate/eseguite da **04 Execution Desk**. Una routine che non può rispettare
una guardrail si ferma e logga, **non** improvvisa.

Le regole restano **cinque e inviolabili**; ciò che cambia con la fascia sono i
**valori numerici** (definiti in `tiers`), non l'esistenza della regola.

| # | Regola | Valore (micro / standard) | Owner |
|---|--------|--------|-------|
| **R1** | **Hard Daily Stop-Loss (Kill Switch)** — se il capitale scende oltre soglia vs apertura, chiudi tutto, cancella gli ordini e iberna fino al giorno dopo. | `-6%` / `-2%` | 04 Execution |
| **R2** | **Maximum Position Size** — nessun trade impegna più della quota della fascia. | `45%` / `5%` | 03 Risk |
| **R3** | **Mandatory Physical Stop Loss** — ogni ingresso è un **Bracket Order** con stop fisico sul broker (GTC in swing, day in intraday). | `-3%` / `-1,5%` | 03 Risk + 04 Execution |
| **R4** | **Maximum Sector Correlation** — capitale massimo su un singolo settore. | `100%`* / `15%` | 03 Risk |
| **R5** | **API Error & Latency Threshold** — dopo **3 errori consecutivi** dal broker, la routine si ferma, logga e si sospende. | `3` (globale) | tutte |

\* Con sole 2 posizioni la diversificazione settoriale non è materialmente
possibile: il cap viene neutralizzato per non bloccare ogni operazione. È una
scelta consapevole, non una dimenticanza — su capitale micro il rischio si
controlla con size e stop, non con la diversificazione.

**Take Profit:** ogni Bracket Order include un take profit (+6% micro / +3% standard).

**Vincolo aggiuntivo (swing):** `max_hold_days` — una posizione aperta da più di
N giorni di borsa viene chiusa a mercato, anche in utile/perdita, per non
trasformare uno swing in un investimento a tempo indeterminato.

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
