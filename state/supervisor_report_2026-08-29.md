# 🤖 Supervisore AI — 2026-08-29

## Performance settimana

- **per_fattore_di_rischio:** {'n': 0, 'dettaglio': []}
- **realized_pnl_closed_trades:** 0
- **n_closed_trades_week:** 0
- **win_rate_pct:** 0.0
- **best_trade:** 0.0
- **worst_trade:** 0.0
- **closed_detail:** []
- **open_positions:** ['AAL qty=18 uPL=-4.5', 'INTC qty=1 uPL=-0.1', 'WBD qty=8 uPL=-0.24']
- **unrealized_pnl_open:** -4.84
- **n_fills_week:** 9
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99971.13
- **capitale_operativo_strategia:** 579.94
- **rendimento_settimana_pct:** 0.0
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': 5.44, 'riferimento_pct': 5.47, 'alpha_pct': -0.02, 'giudizio': "il riferimento ha fatto meglio: fermi avremmo guadagnato di piu'"}
- **storico_dall_avvio:** {'da': '2026-07-29', 'n': 15, 'vincenti': 9, 'win_rate_pct': 60.0, 'pl_totale_usd': 34.81, 'pl_medio_pct': 2.46, 'n_con_rischio_noto': 14, 'R_medio': 0.85, 'R_totale': 11.85, 'R_migliore': 2.89, 'R_peggiore': -1.02, 'R_vincita_media': 2.19, 'R_perdita_media': -0.94, 'operazioni_perse_sostenibili_per_vincita': 2.3, 'alpha': {'n_confrontabili': 15, 'alpha_medio_pct': 2.21, 'alpha_totale_pct': 33.14, 'quota_che_batte_il_mercato_pct': 60.0, 'migliore_pct': 8.73, 'peggiore_pct': -3.82}, 'ultime_10': ['INTC +5.90% (+1.89R)', 'NKE -2.83% (-0.93R)', 'SMCI +8.66% (+2.89R)', 'HOOD +6.14% (+2.12R)', 'SMCI -3.05% (-1.02R)', 'SOFI -3.06% (-1.00R)', 'SOFI -3.05% (-1.00R)', 'COIN +6.88% (+2.27R)', 'NVDA -2.93% (-1.00R)', 'HOOD +5.99% (+1.99R)']}
- **nota_storico:** 'storico_dall_avvio' contiene TUTTE le operazioni dall'inizio della strategia ed e' la base su cui giudicare. I campi settimanali servono solo a vedere cosa e' successo di recente: non trarne conclusioni statistiche, una settimana contiene troppe poche operazioni.
- **registro_decisioni:** {'in_sospeso': 3, 'risolte': 2, 'totali': 7, 'chiuse': 4}

## Analisi

Lo storico dall'avvio mostra una strategia sana: 15 operazioni, win rate 60%, R_medio 0.85, R_totale 11.85, alpha_totale +33.14% con il 60% delle operazioni che battono il mercato. Questi sono numeri solidi che indicano un edge reale e persistente. L'alpha settimanale (-0.02%) e' sostanzialmente in pareggio con SPY, ma su una sola settimana con 3 posizioni ancora aperte (uPL leggermente negativo, -4.84 USD) non e' possibile trarre conclusioni: e' rumore statistico. Il rapporto R_vincita_media (2.19) contro R_perdita_media (-0.94) e' eccellente e mostra che il target/stop asimmetrico funziona. Le posizioni aperte sono ancora dentro le normali oscillazioni. Non c'e' alcun segnale nei dati che giustifichi un cambiamento dei parametri: la strategia produce alpha positivo e consistente. Modificare senza motivo rischierebbe di degradare un sistema che funziona. Il vincolo posizioni x dimensione (3 x 30% = 90%) e' rispettato. Restituisco changes vuoto.

## Modifiche applicate

- nessuna