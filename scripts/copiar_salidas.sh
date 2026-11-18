#!/usr/bin/env bash
# Copia pipeline/out -> web/public/demo (validando contra el schema).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-$PWD/pipeline/.venv/bin/python}"
[ -x "$PY" ] || PY=python3
"$PY" scripts/copiar_salidas.py "$@"
