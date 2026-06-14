Sei un Senior Quantitative Developer. 
Il tuo compito è scrivere la seconda routine del mio trading bot: `02_portfolio_manager.py`.

CONTESTO ARCHITETTURALE:
Lo script gira alle 15:00 CET. Usa GitHub come state management. 

INPUT E OUTPUT:
- Input: Deve fare git pull e leggere il file `market_research.json` creato dalla routine precedente.
- Output: Deve fare git push creando un nuovo file `target_orders.json`.

SPECIFICHE LOGICHE (Cosa deve fare il codice):
1. Autenticati ad Alpaca Markets (Paper Trading API) usando `alpaca-trade-api` per ottenere il `buying_power` (capitale liquido attuale del conto).
2. Leggi da `market_research.json` i 5 ticker "Momentum" selezionati dall'Analista.
3. Genera una strategia di allocazione. Dividi il capitale disponibile simulando di voler investire su 3 di questi 5 titoli (scegli quelli con volume maggiore).
4. Calcola il "Prezzo di Target Entry": per i titoli Bullish, imposta il target entry allo 0.5% in meno rispetto al prezzo attuale (per comprare sul ritracciamento).
5. Struttura i dati e salvali.

STRUTTURA DEL JSON DI OUTPUT (`target_orders.json`):
Deve essere una lista di dizionari con chiavi: "ticker", "action" (buy/sell_short), "target_entry_price", "allocated_capital".

REGOLE DI CODICE:
- Nessun ordine reale viene inviato ad Alpaca in questo script. È solo logica e calcolo.
- Usa `PyGithub` per il download/upload dello stato.
- Usa `logging` per tracciare il flusso. Usa `os.getenv` per le API keys.
- Scrivi il codice Python completo.