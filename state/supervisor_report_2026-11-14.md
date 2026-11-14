# 🤖 Supervisore AI — 2026-11-14

## Performance settimana

- **per_fattore_di_rischio:** {'n': 3, 'vincenti': 0, 'win_rate_pct': 0.0, 'pl_totale_usd': -20.21, 'pl_medio_pct': -2.81, 'n_con_rischio_noto': 3, 'R_medio': -1.01, 'R_totale': -3.02, 'R_migliore': -1.0, 'R_peggiore': -1.02, 'R_vincita_media': 0.0, 'R_perdita_media': -1.01, 'operazioni_perse_sostenibili_per_vincita': 0.0, 'dettaglio': ['AAL -3.12% (-1.00R)', 'NVDA -2.59% (-1.02R)', 'SOFI -2.71% (-1.00R)']}
- **realized_pnl_closed_trades:** -20.21
- **n_closed_trades_week:** 3
- **win_rate_pct:** 0.0
- **best_trade:** -4.32
- **worst_trade:** -8.41
- **closed_detail:** ['AAL -7.48', 'NVDA -4.32', 'SOFI -8.41']
- **open_positions:** ['NFLX qty=3 uPL=-3.36', 'PFE qty=10 uPL=-1.4']
- **unrealized_pnl_open:** -4.76
- **n_fills_week:** 22
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99936.82
- **capitale_operativo_strategia:** 697.88
- **rendimento_settimana_pct:** -2.9
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': 26.89, 'riferimento_pct': 3.41, 'alpha_pct': 23.47, 'giudizio': 'la strategia ha battuto il riferimento'}
- **storico_dall_avvio:** {'da': '2026-07-29', 'n': 66, 'vincenti': 27, 'win_rate_pct': 40.9, 'pl_totale_usd': 534.21, 'pl_medio_pct': 0.42, 'n_con_rischio_noto': 64, 'R_medio': 0.08, 'R_totale': 5.04, 'R_migliore': 2.94, 'R_peggiore': -2.12, 'R_vincita_media': 1.76, 'R_perdita_media': -1.0, 'operazioni_perse_sostenibili_per_vincita': 1.8, 'alpha': {'n_confrontabili': 66, 'alpha_medio_per_operazione_pct': 0.31, 'quota_che_batte_il_mercato_pct': 40.9, 'migliore_pct': 10.77, 'peggiore_pct': -6.75, 'nota': "Questi campi misurano la QUALITA' delle singole scelte, NON il risultato del portafoglio: sommarli o interpretarli come sovraperformance e' sbagliato, perche' ogni posizione impegna solo una parte del capitale e dura pochi giorni mentre l'indice compone sempre. Per giudicare se la strategia sta battendo il mercato esiste UN SOLO numero valido: 'alpha_pct' dentro 'confronto_con_indice'. Operazioni mediamente buone possono benissimo convivere con un alpha di portafoglio nullo o negativo."}, 'ultime_10': ['NFLX +6.07% (+2.03R)', 'AAL -3.03% (-1.00R)', 'NFLX -2.95% (-1.01R)', 'BAC -2.79% (-0.93R)', 'UBER +0.84% (+0.28R)', 'INTC +4.86% (+1.16R)', 'NVDA -3.15% (-1.04R)', 'AAL -3.12% (-1.00R)', 'NVDA -2.59% (-1.02R)', 'SOFI -2.71% (-1.00R)']}
- **nota_storico:** 'storico_dall_avvio' contiene TUTTE le operazioni dall'inizio della strategia ed e' la base su cui giudicare. I campi settimanali servono solo a vedere cosa e' successo di recente: non trarne conclusioni statistiche, una settimana contiene troppe poche operazioni.
- **registro_decisioni:** {'in_sospeso': 2, 'risolte': 5, 'totali': 57, 'chiuse': 55}

## Analisi

Lo storico completo (66 operazioni) mostra una strategia sana: win rate 40.9% con R_vincita_media 1.76 contro R_perdita_media -1.0, dando un R_totale positivo di +5.04 e un P&L di +534 USD. Soprattutto, l'unico numero valido per giudicare la sovraperformance - alpha_pct in confronto_con_indice - e' +23.47%, nettamente positivo: la strategia batte l'indice. La settimana recente e' negativa (3 trade persi, -2.9%), ma tre operazioni non costituiscono base statistica e rientrano nella normale varianza di una strategia con win rate ~41%. Le ultime 10 operazioni mostrano comunque vincite significative (NFLX +6.07%, INTC +4.86%). Il profilo di rischio e' coerente (perdite contenute a ~1R). Non ci sono segnali di degrado strutturale: modificare i parametri ora significherebbe reagire a rumore di breve periodo, violando il principio di prudenza. Mantengo invariati i parametri.

## Modifiche applicate

- nessuna