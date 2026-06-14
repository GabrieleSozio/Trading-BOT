Sei un Senior Python Developer esperto in finanza quantitativa. 
Il tuo compito è scrivere la prima routine di un trading bot multi-agente: `01_premarket_analyst.py`.

CONTESTO ARCHITETTURALE:
Il bot usa una repository GitHub privata per gestire lo stato (State Management). Le routine comunicano leggendo e scrivendo file `.json` su questa repo. Non usiamo database.

OBIETTIVO DELLO SCRIPT:
Scrivere uno script Python, da far girare tramite CRON alle 14:30 CET, che analizzi il mercato pre-apertura USA per trovare titoli "Momentum".

INPUT E OUTPUT:
- Output: Deve generare e pushare su GitHub un file chiamato `market_research.json`.

SPECIFICHE LOGICHE (Cosa deve fare il codice):
1. Usa la libreria `yfinance` o le API pubbliche/gratuite di Alpaca per scaricare i dati dei ticker del Nasdaq100 (o una tua lista di 20-30 ticker tech popolari).
2. Calcola la variazione percentuale del prezzo rispetto alla chiusura del giorno precedente (Gap Up/Down) e i volumi pre-market.
3. Seleziona i 5 titoli con la maggiore direzionalità (i migliori "Momentum" del giorno).
4. Crea un dizionario JSON con questi ticker, il loro prezzo attuale, il volume e il trend (Bullish/Bearish).
5. Usa la libreria `PyGithub` per scaricare la repo, salvare il file `market_research.json` aggiornato, fare commit e push.

REGOLE DI CODICE:
- Usa il modulo `logging` per stampare a schermo i passaggi (INFO, ERROR).
- Includi blocchi `try/except` robusti per le chiamate API (se `yfinance` fallisce per un ticker, passa al successivo).
- Usa variabili d'ambiente (`os.getenv`) per i token di GitHub e Alpaca.
- Scrivi codice pulito, modulare, con type hinting e docstrings. Genera il codice completo e pronto all'uso.