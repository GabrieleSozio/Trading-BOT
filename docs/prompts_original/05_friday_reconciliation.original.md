Sei un Financial Data Analyst. 
Scrivi l'ultima routine di Back Office del bot: `05_friday_reconciliation.py`.

CONTESTO ARCHITETTURALE:
Questa routine viene eseguita tramite CRON ogni Venerdì alle 23:00 CET a mercati chiusi. Serve per il calcolo delle performance settimanali e per ripulire lo stato su GitHub in vista del lunedì successivo.

INPUT E OUTPUT:
- Legge i dati reali dal broker (Alpaca API).
- Pulisce la repo GitHub.

SPECIFICHE LOGICHE (Cosa deve fare il codice):
1. Autenticati alle API di Alpaca.
2. Recupera l'Account History o gli "Activities" (i trade eseguiti) relativi agli ultimi 5 giorni lavorativi.
3. Calcola il PnL (Profitti/Perdite) realizzato netto della settimana e il numero totale di trade eseguiti.
4. (Opzionale) Implementa un blocco che formatti queste informazioni e le invii tramite webhook a Discord o Telegram, oppure semplicemente stampa nel log un riepilogo formattato in markdown.
5. Usa `PyGithub` per connetterti alla repository del progetto. Elimina o sposta in una cartella "archive" i file operativi della settimana (`market_research.json`, `target_orders.json`, `approved_orders.json`) per lasciare l'ambiente pulito per la settimana successiva.

REGOLE DI CODICE:
- Focus assoluto sull'uso corretto dell'endpoint `/v2/account/activities` di Alpaca.
- Prevedi la gestione delle timezone (UTC vs CET) per essere sicuro di scaricare esattamente i dati dal lunedì al venerdì.
- Genera il codice completo e commentato.