# 🤖 Supervisore AI — 2026-06-27

## Performance settimana

- **equity:** 100070.18
- **realized_pnl_closed_trades:** -87.04
- **n_closed_trades_week:** 2
- **win_rate_pct:** 0.0
- **best_trade:** -36.8
- **worst_trade:** -50.24
- **open_positions:** ['MSFT qty=13 uPL=61.23', 'NVDA qty=-24 uPL=233.46']
- **unrealized_pnl_open:** 294.69
- **n_fills_week:** 12
- **note:** PnL realizzato = solo round-trip chiusi; le posizioni aperte sono a parte. Affidabile al meglio nel run di fine settimana (flat).

## Analisi

Il campione è statisticamente irrilevante: solo 2 trade round-trip chiusi nella settimana, con un PnL realizzato lievemente negativo (-87.04). Il win rate del 0% non è significativo su 2 sole operazioni. Le posizioni aperte mostrano uPL positivo complessivo (+294.69) e l'equity è sostanzialmente flat/positiva. Non emerge alcun pattern chiaro che giustifichi una modifica dei parametri: i due trade persi sono di entità contenuta e coerente (-36.8 e -50.24), senza segnali di problemi sistematici di selezione candidati, di numero di posizioni o di logica di ingresso. Con così pochi dati, qualsiasi cambiamento sarebbe overfitting sul rumore. La scelta prudente è non modificare nulla e attendere un campione più ampio di trade chiusi.

## Modifiche applicate

- nessuna