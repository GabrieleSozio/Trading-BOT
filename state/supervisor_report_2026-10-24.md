# 🤖 Supervisore AI — 2026-10-24

## Performance settimana

- **per_fattore_di_rischio:** {'n': 1, 'vincenti': 0, 'win_rate_pct': 0.0, 'pl_totale_usd': -14.33, 'pl_medio_pct': -4.85, 'n_con_rischio_noto': 1, 'R_medio': -1.0, 'R_totale': -1.0, 'R_migliore': -1.0, 'R_peggiore': -1.0, 'R_vincita_media': 0.0, 'R_perdita_media': -1.0, 'operazioni_perse_sostenibili_per_vincita': 0.0, 'dettaglio': ['SMCI -4.85% (-1.00R)']}
- **realized_pnl_closed_trades:** -14.33
- **n_closed_trades_week:** 1
- **win_rate_pct:** 0.0
- **best_trade:** -14.33
- **worst_trade:** -14.33
- **closed_detail:** ['SMCI -14.33']
- **open_positions:** ['NVDA qty=1 uPL=-4.83']
- **unrealized_pnl_open:** -4.83
- **n_fills_week:** 10
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99913.12
- **capitale_operativo_strategia:** 538.02
- **rendimento_settimana_pct:** -2.66
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': -2.18, 'riferimento_pct': 4.18, 'alpha_pct': -6.36, 'giudizio': "il riferimento ha fatto meglio: fermi avremmo guadagnato di piu'"}
- **storico_dall_avvio:** {'da': '2026-07-29', 'n': 48, 'vincenti': 18, 'win_rate_pct': 37.5, 'pl_totale_usd': -22.75, 'pl_medio_pct': 0.11, 'n_con_rischio_noto': 47, 'R_medio': 0.04, 'R_totale': 1.94, 'R_migliore': 2.94, 'R_peggiore': -1.58, 'R_vincita_media': 1.79, 'R_perdita_media': -0.95, 'operazioni_perse_sostenibili_per_vincita': 1.9, 'alpha': {'n_confrontabili': 48, 'alpha_medio_per_operazione_pct': 0.02, 'quota_che_batte_il_mercato_pct': 37.5, 'migliore_pct': 8.73, 'peggiore_pct': -4.85, 'nota': "Questi campi misurano la QUALITA' delle singole scelte, NON il risultato del portafoglio: sommarli o interpretarli come sovraperformance e' sbagliato, perche' ogni posizione impegna solo una parte del capitale e dura pochi giorni mentre l'indice compone sempre. Per giudicare se la strategia sta battendo il mercato esiste UN SOLO numero valido: 'alpha_pct' dentro 'confronto_con_indice'. Operazioni mediamente buone possono benissimo convivere con un alpha di portafoglio nullo o negativo."}, 'ultime_10': ['NKE +6.19% (+2.19R)', 'NFLX +2.68% (+0.89R)', 'SOFI -1.70% (-0.66R)', 'AAL -3.02% (-1.00R)', 'F +0.50% (+0.17R)', 'NKE +6.11% (+2.03R)', 'PLTR -3.03% (-1.01R)', 'RIVN -3.05% (-1.03R)', 'NKE -0.16% (-0.05R)', 'SMCI -4.85% (-1.00R)']}
- **nota_storico:** 'storico_dall_avvio' contiene TUTTE le operazioni dall'inizio della strategia ed e' la base su cui giudicare. I campi settimanali servono solo a vedere cosa e' successo di recente: non trarne conclusioni statistiche, una settimana contiene troppe poche operazioni.
- **registro_decisioni:** {'in_sospeso': 1, 'risolte': 3, 'totali': 38, 'chiuse': 37}

## Analisi

Lo storico completo (48 operazioni dall'avvio) mostra un quadro mediocre ma non disastroso: win rate 37.5%, R_medio +0.04, R_totale +1.94, con R_vincita_media 1.79 contro R_perdita_media -0.95 (rapporto favorevole che compensa parzialmente il basso win rate). Il P&L totale e' pero' leggermente negativo (-22.75 USD) e l'alpha medio per operazione e' praticamente nullo (+0.02%), con solo il 37.5% delle scelte che batte il mercato. L'alpha di portafoglio settimanale e' -6.36%, ma una singola settimana con 1 solo trade chiuso non e' statisticamente significativa. Il segnale piu' solido e' strutturale: il bot genera scelte di qualita' appena sopra lo zero e un win rate basso. Con 48 operazioni il campione comincia a essere valutabile, ma non emerge una leva parametrica chiara che risolva il problema: ne' il retracement d'ingresso, ne' il numero di candidati, ne' il max_hold mostrano evidenze dirette di essere mal tarati. Il basso win rate (37.5%) con buon rapporto R suggerisce una strategia trend-following che vive di poche vincite grandi; ridurre il max_hold o le posizioni rischierebbe di tagliare proprio le vincite migliori (NKE +6% su piu' giorni). Non ci sono dati che giustifichino modifiche prudenti con beneficio atteso chiaro. Preferisco non modificare per il gusto di modificare: il profilo rischio/rendimento per operazione e' positivo e il deficit e' marginale. Attendo piu' dati prima di intervenire.

## Modifiche applicate

- nessuna