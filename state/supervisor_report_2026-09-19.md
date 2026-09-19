# 🤖 Supervisore AI — 2026-09-19

## Performance settimana

- **per_fattore_di_rischio:** {'n': 0, 'dettaglio': []}
- **realized_pnl_closed_trades:** 0
- **n_closed_trades_week:** 0
- **win_rate_pct:** 0.0
- **best_trade:** 0.0
- **worst_trade:** 0.0
- **closed_detail:** []
- **open_positions:** ['INTC qty=1 uPL=-0.15']
- **unrealized_pnl_open:** -0.15
- **n_fills_week:** 7
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99926.39
- **capitale_operativo_strategia:** 535.38
- **rendimento_settimana_pct:** 0.0
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': -2.66, 'riferimento_pct': 4.42, 'alpha_pct': -7.08, 'giudizio': "il riferimento ha fatto meglio: fermi avremmo guadagnato di piu'"}
- **storico_dall_avvio:** {'da': '2026-07-29', 'n': 28, 'vincenti': 11, 'win_rate_pct': 39.3, 'pl_totale_usd': -14.44, 'pl_medio_pct': 0.14, 'n_con_rischio_noto': 27, 'R_medio': 0.04, 'R_totale': 1.07, 'R_migliore': 2.89, 'R_peggiore': -1.58, 'R_vincita_media': 1.83, 'R_perdita_media': -1.01, 'operazioni_perse_sostenibili_per_vincita': 1.8, 'alpha': {'n_confrontabili': 28, 'alpha_medio_per_operazione_pct': 0.03, 'quota_che_batte_il_mercato_pct': 35.7, 'migliore_pct': 8.73, 'peggiore_pct': -4.52, 'nota': "Questi campi misurano la QUALITA' delle singole scelte, NON il risultato del portafoglio: sommarli o interpretarli come sovraperformance e' sbagliato, perche' ogni posizione impegna solo una parte del capitale e dura pochi giorni mentre l'indice compone sempre. Per giudicare se la strategia sta battendo il mercato esiste UN SOLO numero valido: 'alpha_pct' dentro 'confronto_con_indice'. Operazioni mediamente buone possono benissimo convivere con un alpha di portafoglio nullo o negativo."}, 'ultime_10': ['SNAP -3.59% (-1.11R)', 'PFE -3.76% (-1.25R)', 'HOOD -3.05% (-1.00R)', 'KO -1.12% (-0.37R)', 'SMCI -3.04% (-0.97R)', 'NKE -3.89% (-1.30R)', 'HOOD -5.12% (-1.58R)', 'UBER -3.83% (-1.28R)', 'F +2.09% (+0.58R)', 'PFE +0.51% (+0.17R)']}
- **nota_storico:** 'storico_dall_avvio' contiene TUTTE le operazioni dall'inizio della strategia ed e' la base su cui giudicare. I campi settimanali servono solo a vedere cosa e' successo di recente: non trarne conclusioni statistiche, una settimana contiene troppe poche operazioni.
- **registro_decisioni:** {'in_sospeso': 1, 'risolte': 2, 'totali': 18, 'chiuse': 17}

## Analisi

Lo storico completo (28 operazioni) mostra un quadro problematico: win rate 39.3%, P&L totale -14.44 USD, R_totale positivo (1.07) ma alpha di portafoglio negativo (-7.08% contro SPY). Le ultime 10 operazioni sono dominate da perdite che hanno colpito lo stop (-3% ricorrente), segnale che molte entry vengono aperte poco prima di inversioni sfavorevoli. Il rendimento della strategia (-2.66%) contro un mercato in salita (+4.42%) indica che la selezione dei titoli sta sottoperformando nettamente. Non posso toccare stop, target, dimensione o modalita' swing. Con i parametri disponibili posso agire sulla qualita' della selezione (top_candidates), sulla tempestivita' dell'entry (retracement) e sulla durata delle posizioni. Il problema principale e' la scarsa qualita' delle scelte (35.7% batte il mercato), quindi ha senso allargare leggermente il bacino di candidati per dare piu' scelta al ranking, e ridurre di poco l'esposizione simultanea aprendo una posizione in meno per limitare il rischio finche' l'edge non migliora. Non intervengo con cambiamenti drastici: il campione e' comunque limitato e l'R positivo suggerisce che l'impianto non e' del tutto rotto.

## Modifiche applicate

- `tier.positions_to_open`: 2 → 1 — Con win rate 39% e alpha di portafoglio negativo, ridurre da 2 a 1 posizione simultanea diminuisce l'esposizione al rischio e concentra il capitale sulla singola miglior opportunita', prudente finche' l'edge non e' dimostrato sullo storico.
- `universe.top_candidates`: 4 → 6 — Solo il 35.7% delle scelte batte il mercato: allargare leggermente il bacino di candidati (da 4 a 6) offre al ranking piu' alternative per selezionare setup migliori, senza stravolgere la logica.