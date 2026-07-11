# 🤖 Supervisore AI — 2026-07-11

## Performance settimana

- **equity:** 99556.29
- **realized_pnl_closed_trades:** 157.59
- **n_closed_trades_week:** 2
- **win_rate_pct:** 50.0
- **best_trade:** 177.95
- **worst_trade:** -20.36
- **open_positions:** ['INTC qty=-40 uPL=41.6', 'MSFT qty=13 uPL=218.92', 'NFLX qty=67 uPL=-56.28', 'NVDA qty=-24 uPL=-208.86', 'ORCL qty=34 uPL=-131.92', 'PLTR qty=37 uPL=-204.24']
- **unrealized_pnl_open:** -340.78
- **n_fills_week:** 23
- **note:** PnL realizzato = solo round-trip chiusi; le posizioni aperte sono a parte. Affidabile al meglio nel run di fine settimana (flat).

## Analisi

I dati disponibili sono molto limitati: solo 2 trade chiusi nell'ultima settimana (win rate 50%, PnL realizzato +157.59). Con un campione cosi' ridotto non e' statisticamente possibile trarre conclusioni affidabili sull'efficacia dei parametri. Il PnL realizzato e' positivo, mentre le posizioni aperte mostrano un unrealized negativo (-340.78) concentrato su alcuni nomi (NVDA -208.86, PLTR -204.24, ORCL -131.92), ma trattandosi di posizioni ancora aperte non e' un segnale conclusivo. Non emergono evidenze chiare che giustifichino modifiche ai parametri di allocazione, entry retracement o dimensione dell'universo. In particolare, non ci sono dati che suggeriscano che aumentare o ridurre il numero di posizioni aperte, cambiare il retracement di ingresso o ampliare/restringere i candidati porterebbe a un miglioramento. Adottando un approccio prudente, preferisco raccogliere piu' dati (piu' trade chiusi) prima di intervenire.

## Modifiche applicate

- nessuna