# Eseguire il bot su un portatile Linux Mint (sempre acceso)

Alternativa al cloud GitHub: il portatile diventa il "cervello" sempre acceso, con
**cron preciso al minuto**. Codice identico; cambia solo chi lo lancia.

## Passi (una volta sola)

### 1. Scarica il progetto
```bash
cd ~
git clone https://github.com/GabrieleSozio/Trading-BOT.git
cd Trading-BOT
```

### 2. Installa tutto
```bash
bash deploy/setup_linux.sh
```
Installa git/python, crea l'ambiente isolato e le dipendenze.

### 3. Inserisci le chiavi
Crea il file `secrets/alpaca_keys.env` (NON finisce su GitHub):
```bash
nano secrets/alpaca_keys.env
```
Incolla (con le TUE chiavi):
```
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
ALPACA_PAPER=true
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_URL=https://data.alpaca.markets
ANTHROPIC_API_KEY=sk-ant-...
```
Verifica che funzioni:
```bash
deploy/run.sh lib.healthcheck
```

### 4. Attiva i timer (cron)
Apri `deploy/crontab.example`, sostituisci `/PERCORSO` con la cartella reale
(es. `/home/TUONOME/Trading-BOT`), poi installa:
```bash
crontab deploy/crontab.example   # dopo aver messo il percorso giusto
crontab -l                        # verifica
```

## Impostazioni del portatile (IMPORTANTE)

- **Non farlo sospendere:** Impostazioni → Risparmio energia →
  "Quando il coperchio e' chiuso: **Non fare nulla**" e "Sospensione: **Mai**"
  (almeno con l'alimentatore collegato). Tienilo **collegato alla corrente**.
- **Fuso orario:** il crontab usa `CRON_TZ=Europe/Rome`, quindi gli orari sono
  gia' quelli italiani (ora legale inclusa). Niente da calcolare.
- **Deve restare acceso** durante l'orario di mercato (~15:30-22:00 CET, lun-ven).

## Note

- **Auto-push su GitHub (opzionale):** di default ogni routine prova a fare push.
  Sul portatile serve un'autenticazione git (token GitHub) perche' funzioni; se non
  la imposti, il push semplicemente fallisce in silenzio e il bot lavora lo stesso
  in locale (lo stato vive nei file `state/`). Per avere anche il backup su GitHub,
  configura un Personal Access Token.
- **Log:** tutto finisce in `state/cron.log` (`tail -f state/cron.log` per guardarlo live).
- **Quando passi al portatile, DISATTIVA i timer di GitHub** per non far girare il bot
  due volte (chiedi a Claude: "disattiva gli orari su GitHub" e li tolgo dai workflow).
