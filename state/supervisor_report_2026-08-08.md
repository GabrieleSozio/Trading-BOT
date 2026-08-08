# 🤖 Supervisore AI — 2026-08-08

## Performance settimana

- **equity:** 99964.78
- **realized_pnl_closed_trades:** 14.32
- **n_closed_trades_week:** 4
- **win_rate_pct:** 50.0
- **best_trade:** 108.0
- **worst_trade:** -99.4
- **open_positions:** ['NKE qty=2 uPL=0.1']
- **unrealized_pnl_open:** 0.1
- **n_fills_week:** 8
- **note:** PnL realizzato = solo round-trip chiusi; le posizioni aperte sono a parte. Affidabile al meglio nel run di fine settimana (flat).

## Analisi

Il campione è molto ridotto: solo 4 trade chiusi nell'ultima settimana con win rate 50%. Il PnL realizzato è positivo (+14.32) ma dominato dalla dispersione fra best (+108) e worst (-99.4), segno che i pochi risultati sono guidati da singoli eventi e non da un pattern statisticamente affidabile. Con 2 posizioni x 45% siamo al 90% del capitale, dentro il vincolo del 100%. Non ci sono segnali chiari che giustifichino un aumento di rischio (piu' posizioni o hold piu' lungo) ne' una riduzione difensiva. La strategia swing e' imposta dal capitale e non modificabile. Con dati cosi' scarsi la scelta prudente e' non intervenire sui parametri di rischio. Un unico micro-aggiustamento difensivo potrebbe essere ampliare leggermente il bacino di candidati per migliorare la selezione senza aumentare il rischio, ma anche questo non e' supportato da evidenza sufficiente. In assenza di segnali statisticamente robusti, mantengo la configurazione attuale.

## Modifiche applicate

- nessuna