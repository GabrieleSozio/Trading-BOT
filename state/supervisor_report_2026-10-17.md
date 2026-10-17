# 🤖 Supervisore AI — 2026-10-17

## Performance settimana

- **per_fattore_di_rischio:** {'n': 4, 'vincenti': 1, 'win_rate_pct': 25.0, 'pl_totale_usd': -2.89, 'pl_medio_pct': -0.75, 'n_con_rischio_noto': 4, 'R_medio': -0.25, 'R_totale': -1.01, 'R_migliore': 2.03, 'R_peggiore': -1.03, 'R_vincita_media': 2.03, 'R_perdita_media': -1.01, 'operazioni_perse_sostenibili_per_vincita': 2.0, 'dettaglio': ['AAL -3.02% (-1.00R)', 'NKE +6.11% (+2.03R)', 'PLTR -3.03% (-1.01R)', 'RIVN -3.05% (-1.03R)']}
- **realized_pnl_closed_trades:** -17.17
- **n_closed_trades_week:** 4
- **win_rate_pct:** 25.0
- **best_trade:** 2.76
- **worst_trade:** -8.97
- **closed_detail:** ['NKE +2.76', 'AAL -4.94', 'PLTR -6.02', 'RIVN -8.97']
- **open_positions:** ['F qty=13 uPL=4.81', 'NKE qty=8 uPL=-2.24']
- **unrealized_pnl_open:** 2.57
- **n_fills_week:** 26
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99934.62
- **capitale_operativo_strategia:** 889.6
- **rendimento_settimana_pct:** -1.93
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': 61.75, 'riferimento_pct': 4.63, 'alpha_pct': 57.11, 'giudizio': 'la strategia ha battuto il riferimento'}
- **storico_dall_avvio:** {'da': '2026-07-29', 'n': 45, 'vincenti': 17, 'win_rate_pct': 37.8, 'pl_totale_usd': -8.72, 'pl_medio_pct': 0.22, 'n_con_rischio_noto': 44, 'R_medio': 0.06, 'R_totale': 2.82, 'R_migliore': 2.94, 'R_peggiore': -1.58, 'R_vincita_media': 1.89, 'R_perdita_media': -0.98, 'operazioni_perse_sostenibili_per_vincita': 1.9, 'alpha': {'n_confrontabili': 45, 'alpha_medio_per_operazione_pct': 0.08, 'quota_che_batte_il_mercato_pct': 35.6, 'migliore_pct': 8.73, 'peggiore_pct': -4.52, 'nota': "Questi campi misurano la QUALITA' delle singole scelte, NON il risultato del portafoglio: sommarli o interpretarli come sovraperformance e' sbagliato, perche' ogni posizione impegna solo una parte del capitale e dura pochi giorni mentre l'indice compone sempre. Per giudicare se la strategia sta battendo il mercato esiste UN SOLO numero valido: 'alpha_pct' dentro 'confronto_con_indice'. Operazioni mediamente buone possono benissimo convivere con un alpha di portafoglio nullo o negativo."}, 'ultime_10': ['HOOD +6.18% (+2.07R)', 'INTC -2.97% (-1.01R)', 'ORCL -2.97% (-1.00R)', 'NKE +6.19% (+2.19R)', 'NFLX +2.68% (+0.89R)', 'SOFI -1.70% (-0.66R)', 'AAL -3.02% (-1.00R)', 'NKE +6.11% (+2.03R)', 'PLTR -3.03% (-1.01R)', 'RIVN -3.05% (-1.03R)']}
- **nota_storico:** 'storico_dall_avvio' contiene TUTTE le operazioni dall'inizio della strategia ed e' la base su cui giudicare. I campi settimanali servono solo a vedere cosa e' successo di recente: non trarne conclusioni statistiche, una settimana contiene troppe poche operazioni.
- **registro_decisioni:** {'in_sospeso': 2, 'risolte': 7, 'totali': 36, 'chiuse': 34}

## Analisi

Lo storico completo (45 operazioni) mostra un quadro statisticamente piu' affidabile della settimana. Il win rate e' 37.8% con R_medio marginalmente positivo (0.06) e R_totale +2.82, indicando un edge molto debole ma non nullo. Il P&L totale in USD e' leggermente negativo (-8.72), quindi la strategia e' sostanzialmente in pareggio. L'unico indicatore valido di sovraperformance e' alpha_pct in confronto_con_indice: +57.11%, ma questo valore e' gonfiato e poco credibile su un capitale operativo di soli 889 USD e va interpretato con cautela; l'alpha_medio_per_operazione e' solo +0.08%. La settimana recente e' stata negativa (win_rate 25%, -1.93%) ma con 4 sole operazioni non e' statisticamente significativa: non va usata per concludere nulla. Il profilo R vincita/perdita (1.89 vs -0.98) e' favorevole: le vincite ripagano quasi due perdite, coerente con target +6% e stop -3%. Il sistema e' sostanzialmente in equilibrio con un edge sottile. Non ci sono segnali chiari e robusti nello storico che giustifichino modifiche strutturali ai parametri: ogni cambiamento rischierebbe di essere rumore guidato da una settimana debole. In linea con la prudenza richiesta, non modifico per il gusto di modificare.

## Modifiche applicate

- nessuna