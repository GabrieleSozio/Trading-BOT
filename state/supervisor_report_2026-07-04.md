# 🤖 Supervisore AI — 2026-07-04

## Performance settimana

- **equity:** 100473.21
- **realized_pnl_closed_trades:** 0
- **n_closed_trades_week:** 0
- **win_rate_pct:** 0.0
- **best_trade:** 0.0
- **worst_trade:** 0.0
- **open_positions:** ['MSFT qty=13 uPL=288.99', 'NFLX qty=67 uPL=230.48', 'NVDA qty=-24 uPL=178.26']
- **unrealized_pnl_open:** 697.73
- **n_fills_week:** 2
- **note:** PnL realizzato = solo round-trip chiusi; le posizioni aperte sono a parte. Affidabile al meglio nel run di fine settimana (flat).

## Analisi

I dati disponibili sono insufficienti per trarre conclusioni statisticamente rilevanti. Nella settimana non ci sono stati round-trip chiusi (n_closed_trades_week=0, win_rate=0), quindi non esiste alcuna metrica di PnL realizzato o hit-rate su cui basare un tuning. Ci sono solo 2 fill totali e 3 posizioni ancora aperte con un uPL positivo complessivo (+697.73), che è incoraggiante ma non conclusivo: l'unrealized PnL puo' cambiare e non riflette la qualita' del sistema di uscita. Modificare parametri come positions_to_open, entry_retracement_pct o top_candidates senza un campione di trade chiusi significherebbe fare overfitting sul rumore. La strategia prudente e' mantenere invariata la configurazione e raccogliere ulteriori dati (piu' round-trip chiusi) prima di intervenire.

## Modifiche applicate

- nessuna