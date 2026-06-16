#!/usr/bin/env bash
# Staffetta mattutina in ORDINE garantito: 01 -> 02 -> 03.
# (La 04 gira a parte, ogni minuto, dal crontab.)
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$DIR/run.sh" lib.routine_01_premarket
"$DIR/run.sh" lib.routine_02_portfolio
"$DIR/run.sh" lib.routine_03_risk
