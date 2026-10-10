# 🤖 Supervisore AI — 2026-10-10

## Performance settimana

- **per_fattore_di_rischio:** {'n': 0, 'dettaglio': []}
- **realized_pnl_closed_trades:** 0
- **n_closed_trades_week:** 0
- **win_rate_pct:** 0.0
- **best_trade:** 0.0
- **worst_trade:** 0.0
- **closed_detail:** []
- **open_positions:** ['NFLX qty=2 uPL=-1.3', 'NKE qty=6 uPL=8.689998', 'SOFI qty=13 uPL=3.64']
- **unrealized_pnl_open:** 11.03
- **n_fills_week:** 10
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99933.35
- **capitale_operativo_strategia:** 667.17
- **rendimento_settimana_pct:** 0.0
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': 21.3, 'riferimento_pct': 6.73, 'alpha_pct': 14.57, 'giudizio': 'la strategia ha battuto il riferimento'}
- **storico_dall_avvio:** {'da': '2026-07-29', 'n': 38, 'vincenti': 14, 'win_rate_pct': 36.8, 'pl_totale_usd': -18.55, 'pl_medio_pct': 0.15, 'n_con_rischio_noto': 37, 'R_medio': 0.04, 'R_totale': 1.41, 'R_migliore': 2.94, 'R_peggiore': -1.58, 'R_vincita_media': 1.93, 'R_perdita_media': -0.99, 'operazioni_perse_sostenibili_per_vincita': 1.9, 'alpha': {'n_confrontabili': 38, 'alpha_medio_per_operazione_pct': -0.03, 'quota_che_batte_il_mercato_pct': 34.2, 'migliore_pct': 8.73, 'peggiore_pct': -4.52, 'nota': "Questi campi misurano la QUALITA' delle singole scelte, NON il risultato del portafoglio: sommarli o interpretarli come sovraperformance e' sbagliato, perche' ogni posizione impegna solo una parte del capitale e dura pochi giorni mentre l'indice compone sempre. Per giudicare se la strategia sta battendo il mercato esiste UN SOLO numero valido: 'alpha_pct' dentro 'confronto_con_indice'. Operazioni mediamente buone possono benissimo convivere con un alpha di portafoglio nullo o negativo."}, 'ultime_10': ['INTC +8.61% (+2.94R)', 'INTC -3.94% (-1.38R)', 'T -2.43% (-0.86R)', 'NFLX -2.77% (-1.00R)', 'F -3.25% (-1.05R)', 'SMCI +5.94% (+1.87R)', 'SOFI -0.70% (-0.24R)', 'HOOD +6.18% (+2.07R)', 'INTC -2.97% (-1.01R)', 'ORCL -2.97% (-1.00R)']}
- **nota_storico:** 'storico_dall_avvio' contiene TUTTE le operazioni dall'inizio della strategia ed e' la base su cui giudicare. I campi settimanali servono solo a vedere cosa e' successo di recente: non trarne conclusioni statistiche, una settimana contiene troppe poche operazioni.
- **registro_decisioni:** {'in_sospeso': 3, 'risolte': 2, 'totali': 30, 'chiuse': 27}

## Analisi

Lo storico completo (38 operazioni) mostra un quadro ambivalente. Il win rate e' basso (36.8%) ma compensato da un rapporto vincita/perdita media favorevole (R_vincita_media 1.93 vs R_perdita_media -0.99), con R_totale positivo (+1.41). Tuttavia il P&L totale realizzato dall'avvio e' leggermente NEGATIVO (-18.55 USD) e l'alpha medio per operazione e' praticamente nullo/negativo (-0.03%), con solo il 34.2% delle operazioni che batte il mercato. L'unico dato di portafoglio valido, 'confronto_con_indice', mostra alpha_pct +14.57 (strategia 21.3% vs SPY 6.73%): questo e' positivo, ma e' influenzato dalle posizioni aperte attualmente in profitto (uPL +11.03) e va letto con prudenza dato il P&L realizzato negativo. Nel complesso il sistema e' sostanzialmente in pareggio sulla qualita' delle scelte: non ci sono segnali chiari e robusti che giustifichino un cambiamento. Il win rate basso e l'R_totale debolmente positivo suggeriscono un edge marginale, ma non c'e' evidenza statistica sufficiente per spostare parametri strutturali (numero posizioni, hold days, universo) in una direzione precisa. Modificare ora significherebbe inseguire il rumore. Mantengo i parametri invariati.

## Modifiche applicate

- nessuna