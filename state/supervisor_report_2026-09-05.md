# 🤖 Supervisore AI — 2026-09-05

## Performance settimana

- **per_fattore_di_rischio:** {'n': 3, 'vincenti': 0, 'win_rate_pct': 0.0, 'pl_totale_usd': -13.94, 'pl_medio_pct': -3.23, 'n_con_rischio_noto': 3, 'R_medio': -1.03, 'R_totale': -3.08, 'R_migliore': -0.97, 'R_peggiore': -1.11, 'R_vincita_media': 0.0, 'R_perdita_media': -1.03, 'operazioni_perse_sostenibili_per_vincita': 0.0, 'dettaglio': ['SNAP -3.59% (-1.11R)', 'HOOD -3.05% (-1.00R)', 'SMCI -3.04% (-0.97R)']}
- **realized_pnl_closed_trades:** -13.94
- **n_closed_trades_week:** 3
- **win_rate_pct:** 0.0
- **best_trade:** -3.21
- **worst_trade:** -6.17
- **closed_detail:** ['SNAP -6.17', 'HOOD -3.21', 'SMCI -4.56']
- **open_positions:** ['KO qty=1 uPL=-0.56', 'PFE qty=5 uPL=-2.15']
- **unrealized_pnl_open:** -2.71
- **n_fills_week:** 22
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99943.87
- **capitale_operativo_strategia:** 552.77
- **rendimento_settimana_pct:** -2.52
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': 0.5, 'riferimento_pct': 5.58, 'alpha_pct': -5.08, 'giudizio': "il riferimento ha fatto meglio: fermi avremmo guadagnato di piu'"}
- **storico_dall_avvio:** {'da': '2026-07-29', 'n': 21, 'vincenti': 9, 'win_rate_pct': 42.9, 'pl_totale_usd': 5.51, 'pl_medio_pct': 0.91, 'n_con_rischio_noto': 20, 'R_medio': 0.3, 'R_totale': 6.1, 'R_migliore': 2.89, 'R_peggiore': -1.39, 'R_vincita_media': 2.19, 'R_perdita_media': -0.95, 'operazioni_perse_sostenibili_per_vincita': 2.3, 'alpha': {'n_confrontabili': 21, 'alpha_medio_per_operazione_pct': 0.77, 'quota_che_batte_il_mercato_pct': 42.9, 'migliore_pct': 8.73, 'peggiore_pct': -4.42, 'nota': "Questi campi misurano la QUALITA' delle singole scelte, NON il risultato del portafoglio: sommarli o interpretarli come sovraperformance e' sbagliato, perche' ogni posizione impegna solo una parte del capitale e dura pochi giorni mentre l'indice compone sempre. Per giudicare se la strategia sta battendo il mercato esiste UN SOLO numero valido: 'alpha_pct' dentro 'confronto_con_indice'. Operazioni mediamente buone possono benissimo convivere con un alpha di portafoglio nullo o negativo."}, 'ultime_10': ['SOFI -3.05% (-1.00R)', 'COIN +6.88% (+2.27R)', 'NVDA -2.93% (-1.00R)', 'HOOD +5.99% (+1.99R)', 'WBD -0.83% (-0.28R)', 'AAL -4.29% (-1.39R)', 'INTC -3.03% (-1.00R)', 'SNAP -3.59% (-1.11R)', 'HOOD -3.05% (-1.00R)', 'SMCI -3.04% (-0.97R)']}
- **nota_storico:** 'storico_dall_avvio' contiene TUTTE le operazioni dall'inizio della strategia ed e' la base su cui giudicare. I campi settimanali servono solo a vedere cosa e' successo di recente: non trarne conclusioni statistiche, una settimana contiene troppe poche operazioni.
- **registro_decisioni:** {'in_sospeso': 2, 'risolte': 6, 'totali': 12, 'chiuse': 10}

## Analisi

Lo storico completo (21 operazioni dall'avvio) mostra un profilo statisticamente debole ma non catastrofico: win rate 42.9%, R_medio +0.30, P&L totale +5.51 USD. Il rapporto vincita/perdita e' sano (R_vincita_media +2.19 contro R_perdita_media -0.95, ovvero servono 2.3 perdite per bruciare una vincita), il che indica che il sistema di target/stop e' ragionevole. Il problema chiave e' l'alpha di portafoglio: -5.08% sull'ultima settimana, con SPY a +5.58% contro la strategia a +0.5%. La strategia rende poco mentre il mercato compone: capitale largamente sottoinvestito e troppo tempo fuori dal mercato. La settimana recente e' stata pessima (0/3 win) ma tre operazioni non permettono conclusioni statistiche, quindi non reagisco all'emotivita' della settimana. Sui 21 trade complessivi il quadro e' 'mediocre ma vivo'. Non ci sono elementi che giustifichino un cambio strutturale aggressivo. L'unica leva prudente coerente con l'alpha negativo persistente e' migliorare la selettivita' delle entrate: ridurre leggermente il retracement richiesto in ingresso rischia di peggiorare la qualita', mentre ridurre i candidati considerati puo' concentrare su idee migliori. Tuttavia con dati ancora limitati (21 trade) e un R_medio positivo, la scelta piu' saggia e' NON modificare per non degradare un edge fragile ma esistente. I parametri attuali (3 posizioni x 30% = 90% capitale, hold 5gg) sono gia' equilibrati e conformi al vincolo del 100%.

## Modifiche applicate

- nessuna