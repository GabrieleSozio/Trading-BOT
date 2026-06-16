#!/usr/bin/env bash
# Setup una-tantum su Linux Mint/Ubuntu. Da eseguire dentro la cartella del repo:
#   bash deploy/setup_linux.sh
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installo git e python..."
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

echo "==> Creo l'ambiente Python isolato (.venv)..."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

chmod +x deploy/run.sh deploy/pipeline.sh

echo ""
echo "==> Fatto! Mancano 2 cose:"
echo "   1) Crea il file secrets/alpaca_keys.env con le chiavi (vedi deploy/README.md)."
echo "   2) Installa il crontab (vedi deploy/README.md)."
echo ""
echo "Prova subito (a mercato chiuso e' normale che 01 dica 'mercato chiuso'):"
echo "   deploy/run.sh lib.healthcheck"
