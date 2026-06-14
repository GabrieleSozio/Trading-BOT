Sei un High-Frequency Execution Engine Developer. 
Scrivi il cuore pulsante del trading bot: `04_execution_desk.py`.

CONTESTO ARCHITETTURALE E TIMING:
A differenza delle altre routine, questa girerà in Loop Continuo (o CRON ogni minuto) dalle 15:30 CET alle 21:46 CET. È l'unica routine che invia ordini veri al broker.

INPUT E OUTPUT:
- Input: Legge `approved_orders.json` all'avvio.
- Output: Registra l'operatività locale e alle 21:46 fa push di `daily_executions_log.json`.

SPECIFICHE LOGICHE DEL LOOP (Cosa deve fare il codice):
1. **Fase di Avvio (15:30):** Legge gli ordini approvati.
2. **Loop di Monitoraggio (ogni minuto):** Usa le API REST di Alpaca per leggere il prezzo attuale dei ticker autorizzati. 
3. **Execution:** Se il prezzo in tempo reale tocca il `target_entry_price`, invia l'ordine.
   - **TASSATIVO:** Devi usare le API di Alpaca per inviare un `Bracket Order` (Ordine madre di acquisto + Stop Loss child + Take Profit child contemporaneamente). Calcola la "quantity" in base a `allocated_capital / prezzo`.
4. **Kill Switch (Global Risk):** Ad ogni ciclo, calcola il PnL giornaliero. Se scende del -2% rispetto al balance iniziale, INVIA IMMEDIATAMENTE un comando `close_all_positions()` ad Alpaca e un comando `cancel_all_orders()`. Ferma il loop (`sys.exit()`).
5. **Liquidate All (21:45 CET):** Se sono le 21:45 CET, forza `close_all_positions()` ad Alpaca per non andare overnight.

REGOLE DI PREVENZIONE ERRORI:
- Implementa un contatore di errori API. Se falliscono 3 chiamate REST ad Alpaca consecutivamente, vai in sleep per 5 minuti.
- Gestisci accuratamente i ritardi e gli stati pendenti degli ordini.
- Fornisci il codice Python completo e commentato riga per riga.