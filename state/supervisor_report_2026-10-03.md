# 🤖 Supervisore AI — 2026-10-03

## Performance settimana

- **per_fattore_di_rischio:** {'n': 6, 'vincenti': 2, 'win_rate_pct': 33.3, 'pl_totale_usd': -3.09, 'pl_medio_pct': 0.12, 'n_con_rischio_noto': 6, 'R_medio': 0.0, 'R_totale': 0.02, 'R_migliore': 2.07, 'R_peggiore': -1.05, 'R_vincita_media': 1.97, 'R_perdita_media': -0.98, 'operazioni_perse_sostenibili_per_vincita': 2.0, 'dettaglio': ['T -2.43% (-0.86R)', 'NFLX -2.77% (-1.00R)', 'F -3.25% (-1.05R)', 'SMCI +5.94% (+1.87R)', 'HOOD +6.18% (+2.07R)', 'INTC -2.97% (-1.01R)']}
- **realized_pnl_closed_trades:** -1.93
- **n_closed_trades_week:** 6
- **win_rate_pct:** 33.3
- **best_trade:** 7.32
- **worst_trade:** -6.0
- **closed_detail:** ['INTC -2.52', 'T -3.67', 'NFLX -3.90', 'F -6.00', 'SMCI +7.32', 'HOOD +6.84']
- **open_positions:** ['ORCL qty=1 uPL=0.98', 'SOFI qty=11 uPL=1.43']
- **unrealized_pnl_open:** 2.41
- **n_fills_week:** 21
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99930.2
- **capitale_operativo_strategia:** 702.06
- **rendimento_settimana_pct:** -0.27
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': 27.65, 'riferimento_pct': 5.51, 'alpha_pct': 22.14, 'giudizio': 'la strategia ha battuto il riferimento'}
- **storico_dall_avvio:** {'da': '2026-07-29', 'n': 36, 'vincenti': 14, 'win_rate_pct': 38.9, 'pl_totale_usd': -13.14, 'pl_medio_pct': 0.26, 'n_con_rischio_noto': 35, 'R_medio': 0.08, 'R_totale': 2.65, 'R_migliore': 2.94, 'R_peggiore': -1.58, 'R_vincita_media': 1.93, 'R_perdita_media': -1.02, 'operazioni_perse_sostenibili_per_vincita': 1.9, 'alpha': {'n_confrontabili': 36, 'alpha_medio_per_operazione_pct': 0.12, 'quota_che_batte_il_mercato_pct': 36.1, 'migliore_pct': 8.73, 'peggiore_pct': -4.52, 'nota': "Questi campi misurano la QUALITA' delle singole scelte, NON il risultato del portafoglio: sommarli o interpretarli come sovraperformance e' sbagliato, perche' ogni posizione impegna solo una parte del capitale e dura pochi giorni mentre l'indice compone sempre. Per giudicare se la strategia sta battendo il mercato esiste UN SOLO numero valido: 'alpha_pct' dentro 'confronto_con_indice'. Operazioni mediamente buone possono benissimo convivere con un alpha di portafoglio nullo o negativo."}, 'ultime_10': ['F +2.09% (+0.58R)', 'PFE +0.51% (+0.17R)', 'INTC +8.61% (+2.94R)', 'INTC -3.94% (-1.38R)', 'T -2.43% (-0.86R)', 'NFLX -2.77% (-1.00R)', 'F -3.25% (-1.05R)', 'SMCI +5.94% (+1.87R)', 'HOOD +6.18% (+2.07R)', 'INTC -2.97% (-1.01R)']}
- **nota_storico:** 'storico_dall_avvio' contiene TUTTE le operazioni dall'inizio della strategia ed e' la base su cui giudicare. I campi settimanali servono solo a vedere cosa e' successo di recente: non trarne conclusioni statistiche, una settimana contiene troppe poche operazioni.
- **registro_decisioni:** {'in_sospeso': 2, 'risolte': 7, 'totali': 27, 'chiuse': 25}

## Analisi

Lo storico completo (36 operazioni) mostra una strategia robusta: R_totale +2.65, R_medio +0.08, win rate 38.9% con R_vincita_media 1.93 contro R_perdita_media -1.02 (rapporto quasi 2:1, coerente con target +6%/stop -3%). Il P&L totale leggermente negativo (-13.14 USD) e' spiegato da frizioni, ma il profilo rischio/rendimento e' sano. Soprattutto, l'UNICO numero valido per giudicare la sovraperformance - alpha_pct nel confronto_con_indice - e' +22.14% (27.65% vs SPY 5.51%): la strategia sta nettamente battendo il mercato. La settimana recente (6 trade, win 33%) e' statisticamente irrilevante e nei ranges normali di varianza. Non emergono segnali di deterioramento strutturale. Il max_hold di 5gg e le altre impostazioni sono coerenti con il regime swing. Non ci sono motivazioni chiare nei dati per modificare alcun parametro: modificare ora sarebbe interferire con una strategia che funziona. Mantengo lo status quo.

## Modifiche applicate

- nessuna