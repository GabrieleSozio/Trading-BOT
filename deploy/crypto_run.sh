#!/usr/bin/env bash
# Lanciatore della DIVISIONE CRIPTO. Uso:
#   deploy/crypto_run.sh crypto.routine_c1_scan
#
# Differenza importante rispetto a run.sh: qui le chiavi Alpaca NON si
# esportano nell'ambiente. La divisione cripto legge le proprie da
# secrets/alpaca_crypto_keys.env, indicato nella sua configurazione.
# Esportare quelle azionarie creerebbe un ripiego silenzioso: se un giorno il
# file cripto sparisse o fosse incompleto, il codice ricadrebbe sulle chiavi
# del conto azionario e opererebbe sul conto sbagliato. Meglio che fallisca.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

unset ALPACA_API_KEY ALPACA_SECRET_KEY ALPACA_BASE_URL ALPACA_DATA_URL ALPACA_PAPER

# Serve solo la chiave dell'AI (sta nel file azionario per ragioni storiche).
if [ -f secrets/alpaca_keys.env ]; then
  _k="$(grep -E '^ANTHROPIC_API_KEY=' secrets/alpaca_keys.env | head -1 | cut -d= -f2-)"
  if [ -n "${_k:-}" ]; then export ANTHROPIC_API_KEY="$_k"; fi
  unset _k
fi

exec .venv/bin/python -m "$1"
