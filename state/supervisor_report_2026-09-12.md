# 🤖 Supervisore AI — 2026-09-12

## Performance settimana

- **per_fattore_di_rischio:** {'n': 3, 'vincenti': 0, 'win_rate_pct': 0.0, 'pl_totale_usd': -17.59, 'pl_medio_pct': -4.28, 'n_con_rischio_noto': 3, 'R_medio': -1.39, 'R_totale': -4.16, 'R_migliore': -1.28, 'R_peggiore': -1.58, 'R_vincita_media': 0.0, 'R_perdita_media': -1.39, 'operazioni_perse_sostenibili_per_vincita': 0.0, 'dettaglio': ['NKE -3.89% (-1.30R)', 'HOOD -5.12% (-1.58R)', 'UBER -3.83% (-1.28R)']}
- **realized_pnl_closed_trades:** -15.92
- **n_closed_trades_week:** 4
- **win_rate_pct:** 25.0
- **best_trade:** 1.67
- **worst_trade:** -6.08
- **closed_detail:** ['PFE +1.67', 'NKE -5.98', 'HOOD -6.08', 'UBER -5.53']
- **open_positions:** ['F qty=12 uPL=6.72', 'PFE qty=5 uPL=1.3']
- **unrealized_pnl_open:** 8.02
- **n_fills_week:** 16
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99930.5
- **capitale_operativo_strategia:** 539.49
- **rendimento_settimana_pct:** -2.95
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.
- **confronto_con_indice:** {'riferimento': 'SPY', 'strategia_pct': -1.91, 'riferimento_pct': 4.77, 'alpha_pct': -6.69, 'giudizio': "il riferimento ha fatto meglio: fermi avremmo guadagnato di piu'"}
- **storico_dall_avvio:** {'da': '2026-07-29', 'n': 26, 'vincenti': 9, 'win_rate_pct': 34.6, 'pl_totale_usd': -18.5, 'pl_medio_pct': 0.05, 'n_con_rischio_noto': 25, 'R_medio': 0.01, 'R_totale': 0.32, 'R_migliore': 2.89, 'R_peggiore': -1.58, 'R_vincita_media': 2.19, 'R_perdita_media': -1.01, 'operazioni_perse_sostenibili_per_vincita': 2.2, 'alpha': {'n_confrontabili': 26, 'alpha_medio_per_operazione_pct': -0.02, 'quota_che_batte_il_mercato_pct': 34.6, 'migliore_pct': 8.73, 'peggiore_pct': -4.52, 'nota': "Questi campi misurano la QUALITA' delle singole scelte, NON il risultato del portafoglio: sommarli o interpretarli come sovraperformance e' sbagliato, perche' ogni posizione impegna solo una parte del capitale e dura pochi giorni mentre l'indice compone sempre. Per giudicare se la strategia sta battendo il mercato esiste UN SOLO numero valido: 'alpha_pct' dentro 'confronto_con_indice'. Operazioni mediamente buone possono benissimo convivere con un alpha di portafoglio nullo o negativo."}, 'ultime_10': ['AAL -4.29% (-1.39R)', 'INTC -3.03% (-1.00R)', 'SNAP -3.59% (-1.11R)', 'PFE -3.76% (-1.25R)', 'HOOD -3.05% (-1.00R)', 'KO -1.12% (-0.37R)', 'SMCI -3.04% (-0.97R)', 'NKE -3.89% (-1.30R)', 'HOOD -5.12% (-1.58R)', 'UBER -3.83% (-1.28R)']}
- **nota_storico:** 'storico_dall_avvio' contiene TUTTE le operazioni dall'inizio della strategia ed e' la base su cui giudicare. I campi settimanali servono solo a vedere cosa e' successo di recente: non trarne conclusioni statistiche, una settimana contiene troppe poche operazioni.
- **registro_decisioni:** {'in_sospeso': 2, 'risolte': 5, 'totali': 17, 'chiuse': 15}

## Analisi

Lo storico completo (26 operazioni) mostra un quadro debole ma non catastrofico: win_rate 34.6%, R_medio praticamente nullo (0.01), P&L totale -18.5 USD, alpha medio per operazione -0.02%. Il fatto rilevante e' che le ultime 10 operazioni sono quasi tutte perdenti (9 su 10 negative), segnalando un deterioramento recente, ma una settimana/dieci trade non bastano per conclusioni statistiche robuste. L'alpha di portafoglio settimanale e' -6.69% (SPY +4.77 contro strategia -1.91): il mercato ha fatto molto meglio. Il pattern delle perdite e' costante e vicino allo stop (-3% ricorrente), il che suggerisce entry deboli piu' che dimensionamento errato. Le vincite quando ci sono hanno R medio 2.19 (buon rapporto rischio/rendimento), quindi il problema e' la QUALITA' delle entrate, non i target. Intervento prudente: alzare la selettivita' restringendo le candidate per concentrarsi sui setup migliori e ridurre leggermente il numero di posizioni aperte contemporaneamente per limitare l'esposizione durante questa fase di scarsa efficacia. Non tocco max_hold_days ne' il retracement senza evidenza chiara. Le posizioni x dimensione: passando a 2 posizioni x 30% resto ben sotto il 100%.

## Modifiche applicate

- `tier.positions_to_open`: 3 → 2 — Con win_rate 34.6% e un recente cluster di perdite quasi tutte allo stop, ridurre da 3 a 2 posizioni concentra il capitale sui segnali migliori e abbassa l'esposizione durante una fase di alpha negativo, restando entro i vincoli (2x30%=60%).
- `universe.top_candidates`: 5 → 4 — Restringere il pool di candidati da 5 a 4 aumenta la selettivita' delle entrate: il problema evidenziato dallo storico e' la qualita' degli ingressi (molte chiusure vicine allo stop), non i target che mostrano buon R quando vanno a segno.