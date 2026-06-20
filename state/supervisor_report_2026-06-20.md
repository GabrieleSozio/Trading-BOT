# 🤖 Supervisore AI — 2026-06-20

## Performance settimana

- **equity:** 99862.6
- **realized_pnl_closed_trades:** -137.34
- **n_closed_trades_week:** 4
- **win_rate_pct:** 25.0
- **best_trade:** 4164.48
- **worst_trade:** -4288.64
- **open_positions:** []
- **unrealized_pnl_open:** 0
- **n_fills_week:** 11
- **note:** PnL realizzato = solo round-trip chiusi; le posizioni aperte sono a parte. Affidabile al meglio nel run di fine settimana (flat).

## Analisi

Il campione settimanale è estremamente ridotto (solo 4 trade chiusi, 11 fill), quindi statisticamente poco significativo. Il PnL realizzato è leggermente negativo (-137.34, circa -0.14% dell'equity) e il win rate del 25% è basso, ma con appena 4 round-trip non è possibile distinguere tra sfortuna campionaria e un edge realmente carente. La forte dispersione tra best trade (+4164) e worst trade (-4288) indica una volatilità di esito molto elevata per singola posizione: i risultati sono dominati da pochi trade ad alto impatto. In questo contesto la mossa più prudente è ridurre la concentrazione/esposizione per trade riducendo le posizioni aperte contemporaneamente, contenendo l'impatto del singolo trade perdente. Non modifico universe.top_candidates né l'entry_retracement perché non ci sono evidenze che il problema sia nella selezione candidati o nel timing di ingresso, e con dati così scarsi qualsiasi tuning fine sarebbe overfitting sul rumore.

## Modifiche applicate

- `allocation.positions_to_open`: 3 → 2 — L'enorme dispersione tra best (+4164) e worst (-4288) trade mostra che i risultati sono dominati da singole posizioni ad alto impatto. Ridurre da 3 a 2 posizioni aperte contemporaneamente diminuisce in modo prudente la concentrazione e l'impatto del singolo trade perdente, senza azzerare la diversificazione, in attesa di accumulare un campione statisticamente più affidabile.