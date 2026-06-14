# File: 00_overview_strategy_guardrails.md

## 1. Project Purpose & Architecture
L'obiettivo è costruire un trading bot completamente autonomo per il mercato azionario USA, strutturato come un sistema multi-agente[cite: 1]. L'approccio scelto simula una vera e propria banca d'investimento o un Hedge Fund[cite: 1]. Il sistema non è un monolite, ma una pipeline di 5 script cloud indipendenti (routines) che comunicano in modo asincrono utilizzando una repository GitHub come gestore dello stato (State Management)[cite: 1].

**Flusso di base:**
1. Il CRON attiva la singola routine[cite: 1].
2. La routine fa un `git pull` per leggere i file `.json` generati dalle routine precedenti[cite: 1].
3. Esegue la sua logica specifica in Python[cite: 1].
4. Aggiorna lo stato (es. ordini, log) e fa un `git push` sulla repository[cite: 1].

Broker designato: Alpaca Markets (tramite API in Python). Fase 1: Paper Trading in modalità gratuita.

## 2. Trading Strategy: Momentum Intraday
Il sistema agirà esclusivamente in day-trading (aprendo e chiudendo le operazioni nella stessa giornata per azzerare i rischi notturni)[cite: 1]. La strategia di base sarà di tipo "Momentum con Filtro di Rintracciamento"[cite: 1].
*   **Identificazione:** Trovare asset con forte direzionalità e alti volumi in pre-market o apertura[cite: 1].
*   **Entry:** Non acquistare al picco, ma attendere un leggero ritracciamento fisiologico per ottenere un prezzo d'ingresso migliore[cite: 1].
*   **Exit (Flat):** 15 minuti prima della chiusura dei mercati, tutte le posizioni vengono tassativamente liquidate[cite: 1]. Nessun titolo deve figurare in portafoglio overnight[cite: 1].

## 3. The Guardrails (CRITICAL - Inviolable Rules)
Queste regole devono essere codificate rigidamente nel `03_risk_manager.py` e verificate nel `04_execution_desk.py`.
*   **[REGOLA 1] Hard Daily Stop-Loss (Kill Switch):** Se il portafoglio globale scende del -2% rispetto all'apertura, tutte le posizioni vengono chiuse al mercato e il sistema si iberna fino al giorno successivo[cite: 1].
*   **[REGOLA 2] Maximum Position Size:** Nessun trade può impegnare più del 5% del capitale totale disponibile del portafoglio[cite: 1].
*   **[REGOLA 3] Mandatory Physical Stop Loss:** Ogni ordine di acquisto DEVE essere inviato al broker tramite API con un ordine Bracket (o Stop Loss contestuale) impostato tra -1% e -1.5% dal prezzo d'acquisto[cite: 1].
*   **[REGOLA 4] Maximum Sector Correlation:** Il capitale investito in un singolo settore (es. Tech) non può superare il 15% del capitale totale[cite: 1].
*   **[REGOLA 5] API Error & Latency Threshold:** Se la routine riceve 3 errori consecutivi dal Broker (timeout/500 errors), si blocca istantaneamente, logga l'errore e si sospende per evitare loop disastrosi[cite: 1].