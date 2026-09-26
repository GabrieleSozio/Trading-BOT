# 🤖 Supervisore AI — 2026-09-26

## Performance settimana

- **per_fattore_di_rischio:** {'n': 0, 'dettaglio': []}
- **realized_pnl_closed_trades:** -8.08
- **n_closed_trades_week:** 1
- **win_rate_pct:** 0.0
- **best_trade:** -8.08
- **worst_trade:** -8.08
- **closed_detail:** ['INTC -8.08']
- **open_positions:** ['INTC qty=1 uPL=-3.19']
- **unrealized_pnl_open:** -3.19
- **n_fills_week:** 2
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99932.71
- **capitale_operativo_strategia:** 541.7
- **rendimento_settimana_pct:** -1.49
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': -1.51, 'riferimento_pct': 5.74, 'alpha_pct': -7.25, 'giudizio': "il riferimento ha fatto meglio: fermi avremmo guadagnato di piu'"}
- **storico_dall_avvio:** {'da': '2026-07-29', 'n': 29, 'vincenti': 12, 'win_rate_pct': 41.4, 'pl_totale_usd': -5.08, 'pl_medio_pct': 0.43, 'n_con_rischio_noto': 28, 'R_medio': 0.14, 'R_totale': 4.01, 'R_migliore': 2.94, 'R_peggiore': -1.58, 'R_vincita_media': 1.93, 'R_perdita_media': -1.01, 'operazioni_perse_sostenibili_per_vincita': 1.9, 'alpha': {'n_confrontabili': 29, 'alpha_medio_per_operazione_pct': 0.27, 'quota_che_batte_il_mercato_pct': 37.9, 'migliore_pct': 8.73, 'peggiore_pct': -4.52, 'nota': "Questi campi misurano la QUALITA' delle singole scelte, NON il risultato del portafoglio: sommarli o interpretarli come sovraperformance e' sbagliato, perche' ogni posizione impegna solo una parte del capitale e dura pochi giorni mentre l'indice compone sempre. Per giudicare se la strategia sta battendo il mercato esiste UN SOLO numero valido: 'alpha_pct' dentro 'confronto_con_indice'. Operazioni mediamente buone possono benissimo convivere con un alpha di portafoglio nullo o negativo."}, 'ultime_10': ['PFE -3.76% (-1.25R)', 'HOOD -3.05% (-1.00R)', 'KO -1.12% (-0.37R)', 'SMCI -3.04% (-0.97R)', 'NKE -3.89% (-1.30R)', 'HOOD -5.12% (-1.58R)', 'UBER -3.83% (-1.28R)', 'F +2.09% (+0.58R)', 'PFE +0.51% (+0.17R)', 'INTC +8.61% (+2.94R)']}
- **nota_storico:** 'storico_dall_avvio' contiene TUTTE le operazioni dall'inizio della strategia ed e' la base su cui giudicare. I campi settimanali servono solo a vedere cosa e' successo di recente: non trarne conclusioni statistiche, una settimana contiene troppe poche operazioni.
- **registro_decisioni:** {'in_sospeso': 1, 'risolte': 1, 'totali': 19, 'chiuse': 18}

## Analisi

Lo storico completo (29 operazioni) mostra una strategia sostanzialmente in pareggio ma con alpha di portafoglio negativo: alpha_pct -7.25% contro SPY che ha fatto +5.74%. Il P&L totale dall'avvio e' -5.08 USD, win rate 41.4%, R_medio +0.14, R_totale +4.01. Le singole scelte sono mediamente accettabili (R_vincita_media 1.93 vs R_perdita_media -1.01, rapporto favorevole) ma la quota che batte il mercato e' solo 37.9% e l'alpha di portafoglio e' negativo. Il problema strutturale principale e': una sola posizione al 30% del capitale lascia il 70% inutilizzato mentre l'indice compone sempre. Questo e' il motore dell'alpha negativo: siamo troppo poco esposti. Con dimensione 30% per posizione, posso aprire fino a 3 posizioni restando sotto il 100% (90%), aumentando l'esposizione media e la capacita' di catturare il rendimento di mercato senza toccare stop loss o dimensione. E' una mossa prudente e coerente col vincolo posizioni x dimensione <= 100%. Le ultime 10 operazioni mostrano diverse chiusure a -3% (stop) ma anche vincite importanti (INTC +8.61%): il sistema di selezione funziona, manca esposizione. Non tocco max_hold_days (5gg swing e' ragionevole) ne' i parametri di entrata/universo senza evidenza specifica.

## Modifiche applicate

- `tier.positions_to_open`: 1 → 3 — Con una sola posizione al 30% resta inutilizzato il 70% del capitale mentre l'indice compone sempre: e' la causa principale dell'alpha di portafoglio negativo (-7.25%). Portando a 3 posizioni (3x30%=90%, entro il vincolo del 100%) si aumenta l'esposizione e la diversificazione mantenendo intatti stop e dimensione. Le scelte singole hanno R_vincita_media 1.93 vs R_perdita_media -1.01, quindi vale la pena aumentare il numero di scommesse con edge positivo.