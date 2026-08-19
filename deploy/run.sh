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
# Si passano TUTTI gli argomenti, non solo il nome del modulo: con "$1"
# soltanto, un --dry-run veniva scartato in silenzio e la routine girava
# per davvero mentre si credeva di simulare.
mod="$1"; shift
exec .venv/bin/python -m "$mod" "$@"
