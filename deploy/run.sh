#!/usr/bin/env bash
# Esegue una routine caricando le chiavi dall'env file. Uso:
#   deploy/run.sh lib.routine_01_premarket
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
# Carica le chiavi (ALPACA_* e ANTHROPIC_API_KEY) come variabili d'ambiente.
if [ -f secrets/alpaca_keys.env ]; then
  set -a; . secrets/alpaca_keys.env; set +a
fi
exec .venv/bin/python -m "$1"
