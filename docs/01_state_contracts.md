# 01 — Contratti di Stato (Schema dei file JSON)

Le routine comunicano **solo** tramite i file in [`state/`](../state/). Questi
schemi sono il "contratto" tra un membro del team e il successivo: chi scrive li
rispetta, chi legge può fidarsi della struttura. Se un campo manca, la routine
lettrice deve fermarsi con un ERROR (vedi principio "fail loud").

Tutti i file usano: timestamp in **ISO 8601 con timezone**, prezzi come `float`,
capitale in **USD**.

---

## Layout della cartella `state/`

```
state/
├── market_research.json        # output di 01 Premarket Analyst
├── target_orders.json          # output di 02 Portfolio Manager
├── approved_orders.json        # output di 03 Risk Manager
├── daily_executions_log.json   # output di 04 Execution Desk
└── archive/                    # 05 Reconciliation sposta qui i file di fine settimana
```

I file `*.json` di `state/` sono **stato runtime** e sono git-ignored: non vanno
versionati. Solo gli schemi (questo doc) e le routine sono versionati.

---

## `market_research.json` — da 01 Premarket Analyst

```json
{
  "generated_at": "2026-06-15T14:30:00+02:00",
  "session_date": "2026-06-15",
  "universe_size": 30,
  "candidates": [
    {
      "ticker": "NVDA",
      "sector": "Technology",
      "last_price": 131.42,
      "prev_close": 128.90,
      "gap_pct": 1.95,
      "premarket_volume": 4200000,
      "trend": "Bullish"
    }
  ]
}
```
- `candidates`: i **5** titoli con maggiore direzionalità (|gap_pct| più alto), ordinati per forza.
- `trend`: `"Bullish"` se `gap_pct > 0`, `"Bearish"` se `< 0`.

---

## `target_orders.json` — da 02 Portfolio Manager

```json
{
  "generated_at": "2026-06-15T15:00:00+02:00",
  "buying_power": 100000.00,
  "orders": [
    {
      "ticker": "NVDA",
      "sector": "Technology",
      "action": "buy",
      "target_entry_price": 130.77,
      "allocated_capital": 5000.00
    }
  ]
}
```
- Seleziona **3 dei 5** candidati (i 3 con `premarket_volume` maggiore).
- `action`: `"buy"` (Bullish) o `"sell_short"` (Bearish).
- `target_entry_price`: per i Bullish = `last_price * 0.995` (ritracciamento -0.5%).
- **Nessun ordine inviato qui:** è solo pianificazione.

---

## `approved_orders.json` — da 03 Risk Manager

```json
{
  "generated_at": "2026-06-15T15:10:00+02:00",
  "portfolio_value": 100000.00,
  "guardrails_applied": ["R2_max_size", "R3_stop_loss", "R4_sector_cap", "take_profit"],
  "orders": [
    {
      "ticker": "NVDA",
      "sector": "Technology",
      "action": "buy",
      "target_entry_price": 130.77,
      "allocated_capital": 5000.00,
      "stop_loss_price": 128.81,
      "take_profit_price": 134.69
    }
  ]
}
```
- `allocated_capital` ridotto al **5%** di `portfolio_value` se eccedeva (R2).
- `stop_loss_price` = `target_entry_price * 0.985` per i Long (R3, -1.5%).
- `take_profit_price` = `target_entry_price * 1.03` (+3%).
- Ordini scartati per R4 (cap di settore 15%) vengono rimossi e annotati nel log.

---

## `daily_executions_log.json` — da 04 Execution Desk

```json
{
  "session_date": "2026-06-15",
  "opening_balance": 100000.00,
  "closing_balance": 100850.00,
  "kill_switch_triggered": false,
  "events": [
    {
      "ts": "2026-06-15T15:42:00+02:00",
      "type": "ORDER_SUBMITTED",
      "ticker": "NVDA",
      "alpaca_order_id": "abc-123",
      "qty": 38,
      "entry": 130.77,
      "stop_loss": 128.81,
      "take_profit": 134.69
    },
    { "ts": "2026-06-15T21:45:00+02:00", "type": "LIQUIDATE_ALL", "reason": "EOD flat" }
  ]
}
```
- `type` ammessi: `ORDER_SUBMITTED`, `ORDER_FILLED`, `STOP_HIT`, `TP_HIT`,
  `KILL_SWITCH`, `LIQUIDATE_ALL`, `API_ERROR`, `SUSPENDED`.

---

## Note di robustezza

- **Atomicità:** scrivi su file temporaneo e poi rinomina, per non lasciare JSON a metà.
- **Validazione all'ingresso:** prima di usare un file, verifica `session_date`
  uguale a oggi. Un file di ieri = STOP (la staffetta è rotta).
