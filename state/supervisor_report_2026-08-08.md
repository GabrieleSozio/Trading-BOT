# 🤖 Supervisore AI — 2026-08-08

## Performance settimana

- **realized_pnl_closed_trades:** 14.32
- **n_closed_trades_week:** 2
- **win_rate_pct:** 100.0
- **best_trade:** 8.6
- **worst_trade:** 5.72
- **closed_detail:** ['SNAP +8.60', 'INTC +5.72']
- **open_positions:** ['NKE qty=2 uPL=0.1']
- **unrealized_pnl_open:** 0.1
- **n_fills_week:** 8
- **note:** P&L per round-trip effettivamente chiusi (acquisti e vendite abbinati, anche su piu' giorni). Le posizioni ancora aperte sono conteggiate a parte.
- **saldo_conto_paper:** 99964.78
- **capitale_operativo_strategia:** 243.29
- **rendimento_settimana_pct:** 5.89
- **nota_capitale:** Il conto paper ha un saldo grande, ma la strategia dimensiona le posizioni SOLO su 'capitale_operativo_strategia' (simulazione di un conto reale piccolo). Valuta le performance in rapporto a quest'ultimo, non al saldo del conto.

## Analisi

Campione estremamente ridotto: solo 2 trade chiusi nella settimana (SNAP +8.60, INTC +5.72), win rate 100% e rendimento +5.89% sul capitale operativo. I dati sono positivi ma statisticamente insufficienti per giustificare modifiche strutturali. Il vincolo posizioni x dimensione e' gia' al limite (2 x 45% = 90%, sotto il 100%): non c'e' margine per aumentare le posizioni senza sforare o ridurre la size (che non e' modificabile). Le operazioni chiuse hanno colpito il target in tempi che il max_hold_days=5 gestisce bene, e non ci sono segnali di uscite forzate per timeout. Il retracement di ingresso 0.5% sembra funzionare (8 fill, esecuzioni avvenute). Non emergono problemi da correggere: modificare ora significherebbe intervenire sul rumore piuttosto che sul segnale. Mantengo la configurazione attuale.

## Modifiche applicate

- nessuna