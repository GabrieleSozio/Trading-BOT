# 🤖 Supervisore AI — 2026-07-25

## Performance settimana

- **equity:** 98975.47
- **realized_pnl_closed_trades:** -101.17
- **n_closed_trades_week:** 2
- **win_rate_pct:** 0.0
- **best_trade:** -38.4
- **worst_trade:** -62.77
- **open_positions:** ['INTC qty=-40 uPL=742.4', 'MSFT qty=13 uPL=174.72', 'NFLX qty=67 uPL=-276.04', 'NVDA qty=-24 uPL=-109.98', 'ORCL qty=34 uPL=-1004.02', 'PLTR qty=37 uPL=-347.43']
- **unrealized_pnl_open:** -820.35
- **n_fills_week:** 10
- **note:** PnL realizzato = solo round-trip chiusi; le posizioni aperte sono a parte. Affidabile al meglio nel run di fine settimana (flat).

## Analisi

Il campione è estremamente ridotto: solo 2 trade chiusi nella settimana (win rate 0%, PnL realizzato -101.17) e 10 fill totali. Con n=2 round-trip non è statisticamente possibile trarre conclusioni affidabili sulla qualità del segnale o sull'edge del sistema. Le posizioni aperte mostrano un quadro misto (uPL totale -820.35) ma non ancora realizzato, quindi non informativo. Non emergono pattern chiari che giustifichino modifiche ai parametri: aumentare positions_to_open o top_candidates in una fase di perdita e con dati insufficienti aumenterebbe l'esposizione senza evidenza di edge, mentre modificare l'entry_retracement non ha supporto statistico. La scelta prudente è mantenere i parametri invariati e attendere un campione più ampio di trade chiusi (idealmente 20-30 round-trip) prima di ottimizzare.

## Modifiche applicate

- nessuna