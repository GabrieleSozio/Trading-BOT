#!/usr/bin/env bash
# Lanciatore della DIVISIONE OPZIONI. Uso:
#   deploy/options_run.sh options.routine_o1_select
#
# Come per le cripto, le chiavi Alpaca NON si esportano nell'ambiente: questa
# divisione legge le proprie da secrets/alpaca_options_keys.env tramite la sua
# configurazione. Esportare quelle azionarie creerebbe un ripiego silenzioso
# verso il conto sbagliato se il file mancasse. Meglio che fallisca.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

unset ALPACA_API_KEY ALPACA_SECRET_KEY ALPACA_BASE_URL ALPACA_DATA_URL ALPACA_PAPER

if [ -f secrets/alpaca_keys.env ]; then
  _k="$(grep -E '^ANTHROPIC_API_KEY=' secrets/alpaca_keys.env | head -1 | cut -d= -f2-)"
  if [ -n "${_k:-}" ]; then export ANTHROPIC_API_KEY="$_k"; fi
  unset _k
fi

mod="$1"; shift
exec .venv/bin/python -m "$mod" "$@"
