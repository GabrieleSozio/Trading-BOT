# 🤖 Supervisore AI — 2026-08-22

## Performance settimana

- **per_fattore_di_rischio:** {'n': 3, 'vincenti': 1, 'win_rate_pct': 33.3, 'pl_totale_usd': -3.96, 'pl_medio_pct': 0.26, 'n_con_rischio_noto': 3, 'R_medio': 0.09, 'R_totale': 0.27, 'R_migliore': 2.27, 'R_peggiore': -1.0, 'R_vincita_media': 2.27, 'R_perdita_media': -1.0, 'operazioni_perse_sostenibili_per_vincita': 2.3, 'dettaglio': ['SOFI -3.06% (-1.00R)', 'SOFI -3.05% (-1.00R)', 'COIN +6.88% (+2.27R)']}
- **realized_pnl_closed_trades:** -3.96
- **n_closed_trades_week:** 3
- **win_rate_pct:** 33.3
- **best_trade:** 11.72
- **worst_trade:** -7.84
- **closed_detail:** ['SOFI -7.84', 'SOFI -7.84', 'COIN +11.72']
- **open_positions:** ['HOOD qty=2 uPL=5.24', 'NVDA qty=1 uPL=-0.7']
- **unrealized_pnl_open:** 4.54
- **n_fills_week:** 13
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99974.27
- **capitale_operativo_strategia:** 583.0
- **rendimento_settimana_pct:** -0.68
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': 6.0, 'riferimento_pct': 4.97, 'alpha_pct': 1.03, 'giudizio': 'la strategia ha battuto il riferimento'}
- **registro_decisioni:** {'in_sospeso': 2, 'risolte': 2, 'totali': 4, 'chiuse': 2}

## Analisi

Il campione e' molto piccolo (3 round-trip chiusi), quindi ogni conclusione statistica e' fragile. Nonostante il win rate basso (33%), il sistema ha R_totale positivo (+0.27R) grazie a un rapporto vincita/perdita favorevole (2.27R vs -1.0R), e ha battuto SPY (+1.03% di alpha). Le posizioni aperte sono in positivo (uPL +4.54). Le due perdite sono entrambe su SOFI: possibile problema di concentrazione/selezione ma con soli 3 trade non e' un pattern affidabile. Il P&L settimanale e' leggermente negativo (-0.68% sul capitale operativo) ma nella norma della variabilita'. Non ci sono segnali chiari e robusti che giustifichino modifiche: intervenire su un campione cosi' ridotto rischierebbe di ottimizzare sul rumore. Vincolo posizioni x dimensione: 2 x 45% = 90% <= 100%, rispettato; ridurre positions_to_open non e' necessario. Mantengo i parametri attuali e attendo piu' dati.

## Modifiche applicate

- nessuna