# 02 — Note di implementazione (cron job + motore deterministico)

> Questo documento descrive **come** le 5 routine di `ROUTINES/` sono state rese
> operative. I prompt in `ROUTINES/` restano la specifica funzionale (il "cosa");
> qui c'è il "come". In caso di conflitto numerico vince sempre
> [`config/trading_config.yaml`](../config/trading_config.yaml).

## Scelte architetturali

1. **Broker via REST, non MCP.** In questo ambiente non è installato `uv`/`uvx`
   (richiesto dall'esempio `alpaca_mcp.example.json`) e nessun server MCP Alpaca è
   configurato. Le note dello stesso esempio sanzionano esplicitamente l'uso diretto
   degli endpoint REST. Si usa quindi REST su `paper-api.alpaca.markets` +
   `data.alpaca.markets` (feed **IEX**, gratuito). Tutto l'I/O broker è centralizzato
   in [`lib/alpaca_rest.py`](../lib/alpaca_rest.py).

2. **Logica deterministica in `lib/`, supervisione agentica nel cron.** La strategia
   qui è interamente meccanica (gap, ordinamenti, `floor(capitale/prezzo)`, guardrail).
   Per un sistema che muove ordini è più sicuro eseguirla come codice deterministico
   che farla ri-derivare a un LLM ad ogni run. Ogni cron job è un agente Claude che
   **lancia e supervisiona** il modulo corrispondente, ne legge l'output e segnala
   gli errori (fail-loud). I moduli:
   - `lib/routine_01_premarket.py` → `state/market_research.json`
   - `lib/routine_02_portfolio.py` → `state/target_orders.json`
   - `lib/routine_03_risk.py` → `state/approved_orders.json`
   - `lib/routine_04_execution.py` → `state/daily_executions_log.json`
   - `lib/routine_05_reconciliation.py` → report + archivio
   - `lib/alpaca_rest.py` (plumbing), `lib/sectors.py` (mappa settoriale R4)

3. **`session_date` in ogni file di stato.** Gli esempi in `01_state_contracts.md`
   lo omettono in alcuni file, ma la validazione anti-"staffetta rotta" lo richiede:
   tutti gli output lo includono.

## Cron job (ora locale = CET, verificata)

| Routine | cron | Note |
|---------|------|------|
| 01 Premarket | `30 14 * * 1-5` | esce senza scrivere se non è giorno di borsa |
| 02 Portfolio | `0 15 * * 1-5` | valida `market_research.json` di oggi |
| 03 Risk | `10 15 * * 1-5` | valida `target_orders.json`; richiede `portfolio_value` reale |
| 04 Execution | `30 15 * * 1-5` | **disabilitato** finché non validato live (vedi sotto) |
| 05 Reconciliation | `0 23 * * 5` | venerdì, sola lettura broker + archivio |

> Lo scheduler dei task Claude applica un **jitter di alcuni minuti** ad ogni dispatch.
> Gli intervalli della staffetta (≥10 min) lo assorbono.

### Routine 04 = 1 lancio/giorno + loop Python
Per un tick al minuto, ~420 sessioni Claude/giorno sarebbero costose e imprecise (il
jitter rompe la cadenza al minuto). Quindi il cron delle 15:30 lancia **un solo
processo** `python -m lib.routine_04_execution --loop`, staccato dalla sessione, che
fa un tick ogni 60s fino alle 21:46 CET e poi esce. Vantaggio: l'app Claude serve
aperta solo intorno alle 15:30 per il lancio; dopo, il loop è indipendente.

## Rollover graduale (richiesto: niente produzione sotto il 95% di confidenza)

- ✅ Connessione paper verificata (account/clock/market data, sola lettura).
- ✅ Catena 01→02→03 eseguita a vuoto: guardrail R2/R3/R4 attive e corrette.
- ✅ Routine 04 validata in `--dry-run` (execute/eod/close, R1, idempotenza) — **nessun
  ordine ancora inviato davvero**.
- ✅ Routine 05 validata in `--dry-run`.
- ⏳ **Manca**: un test live di **un singolo Bracket Order** a mercato aperto, da
  fare in modo supervisionato, prima di **abilitare** il cron 04.

## Auto-push su GitHub dopo ogni routine

Ogni routine, a fine esecuzione, chiama `lib/gitsync.py::sync()` che fa
`git add -A` + commit + `git push origin HEAD` (best-effort: non fa MAI cadere la
routine; logga `push OK` o l'errore). Conseguenze di design:

- I file `state/*.json` **non sono più git-ignored**: sono tracciati e finiscono nel
  repo (backup/audit). Restano ignorati solo `state/*.out` / `state/*.err` (log del
  processo loop) e, ovviamente, `secrets/`.
- `sync()` ha un **guard di sicurezza**: se in staging comparisse un path che contiene
  `secret`/`.env`/`recovery`/`.key`/`alpaca_keys`, aborta il push e fa `git reset`.
- La Routine 04 NON pusha ad ogni tick: solo quando succede qualcosa (ordine inviato,
  kill switch, liquidazione EOD, chiusura sessione).
- I push vanno direttamente su `main`: è il comportamento voluto (il bot aggiorna il
  repo da solo). Tieni il repository **privato**.
- Le routine condividono comunque `state/` in locale: il push è backup, non trasporto.

## Esecuzione cloud (GitHub Actions)

Le routine possono girare **nel cloud** (GitHub Actions) invece che sul PC locale, così
non serve tenere acceso il computer con l'app aperta. I workflow sono in
`.github/workflows/`:

- `routine-01..03` e `05`: un run schedulato al giorno; eseguono il modulo Python.
- `routine-04`: NON usa il loop. Ogni run è **un singolo tick idempotente** (lo stato si
  ricostruisce dal broker), schedulato **ogni 10 minuti** nella finestra di mercato.
  Si paga così solo ~1 min di runner per tick (sta nei minuti gratuiti del piano private).

Punti chiave:
- **Credenziali**: nel cloud non c'è `secrets/alpaca_keys.env`; le chiavi arrivano dalle
  **GitHub Actions Secrets** `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (il codice fa fallback
  da file a variabili d'ambiente).
- **Stato condiviso via repo**: ogni workflow fa `checkout` (prende l'ultimo stato dal repo),
  esegue, e ricommitta lo stato. `lib/gitsync.py` fa `pull --rebase` + retry se due run
  pushano insieme.
- **Orari in UTC**: i cron di Actions sono in UTC e NON seguono l'ora legale. I valori
  attuali sono per l'ora legale (CEST = UTC+2). **Nota DST**: da fine ottobre (ora solare,
  CET = UTC+1) gli orari vanno spostati di +1 ora nei file workflow, oppure si accetta che
  le routine girino 1h prima in CET (innocuo: il codice della 04 si auto-regola sull'orario
  CET reale e le altre lavorano comunque intraday).
- **Mai locale + cloud insieme**: se girano entrambi si rischia il **doppio ordine**. Quando
  il cloud è attivo, i task locali schedulati vanno **disabilitati**.

## Caveat operativi

- **App aperta**: i cron Claude girano solo con l'app desktop aperta; se chiusa, il
  task parte al successivo avvio. Critico per un bot intraday.
- **Feed IEX**: volume pre-market e quote sono parziali rispetto al consolidato (SIP).
  Accettabile in fase paper; la selezione momentum ne risente in precisione.
- **Margine**: il conto paper espone `buying_power` 4×. La Routine 02 ripartisce il
  buying_power, ma la R2 della Routine 03 ricapping a 5% di `portfolio_value`: è il
  cap a 5% a dominare la size effettiva.
- **Dipendenze Python**: `requests`, `pyyaml` (installate nel `python` di sistema).

## Comandi utili (validazione manuale)

```powershell
python lib\alpaca_rest.py                              # self-test connessione (read-only)
python -m lib.routine_01_premarket --dry-run --force  # forza fuori orario, non scrive
python -m lib.routine_02_portfolio --dry-run
python -m lib.routine_03_risk --dry-run
python -m lib.routine_04_execution --dry-run --force-phase execute
python -m lib.routine_05_reconciliation --dry-run
```
