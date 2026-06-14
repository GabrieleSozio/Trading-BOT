Sei un rigoroso Chief Risk Officer tradotto in codice. 
Scrivi la terza routine del mio sistema: `03_risk_manager.py`. Gira alle 15:10 CET.

OBIETTIVO DELLO SCRIPT:
Prendere gli ordini teorici, applicare le "Guardrails" (regole di sicurezza inviolabili) e sfornare gli ordini approvati.

INPUT E OUTPUT:
- Input: git pull, legge `target_orders.json`. Interroga Alpaca per il `portfolio_value` totale.
- Output: git push, salva `approved_orders.json`.

LE GUARDRAILS DA CODIFICARE RIGIDAMENTE:
1. **Regola Max Size (5%):** Controlla il campo "allocated_capital" di ogni ordine. Se quel valore supera il 5% del `portfolio_value` totale letto da Alpaca, sovrascrivi e riduci il capitale allocato esattamente al 5%.
2. **Stop Loss Matematico Obbligatorio:** Aggiungi a ogni singolo ordine nel JSON un nuovo campo `"stop_loss_price"`. Calcolalo: se l'ordine è Long, lo stop loss è `target_entry_price * 0.985` (-1.5%).
3. **Take Profit Obbligatorio:** Aggiungi un campo `"take_profit_price"` calcolato al +3% dal prezzo di ingresso.

STRUTTURA DEL JSON DI OUTPUT (`approved_orders.json`):
Lista di dizionari: "ticker", "action", "target_entry_price", "allocated_capital", "stop_loss_price", "take_profit_price".

REGOLE DI CODICE:
- Lo script non deve mai fallire silenziosamente. Se le API di Alpaca non rispondono per leggere il bilancio, blocca tutto ed esci con codice di errore (exit 1).
- Usa Type Hinting e docstrings. Genera il codice completo.