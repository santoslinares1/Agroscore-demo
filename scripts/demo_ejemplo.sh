#!/usr/bin/env bash
# Regenera los DATOS DE EJEMPLO (sintéticos), los publica en el front sin borrar nada y compila la web.
# No borra el demo: se genera en una carpeta temporal, se valida contra el schema y se hace swap; las versiones
# anteriores de los ejemplos quedan en .publicacion/demo/versiones/ (fuera de lo que se sirve). Los lotes reales/cargados
# no se tocan.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-$PWD/pipeline/.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/agroscore-ejemplo.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT   # solo la carpeta temporal de esta corrida
(cd pipeline && "$PY" run_pipeline.py data/lotes.geojson --ejemplo --out "$TMP/out")
"$PY" scripts/copiar_salidas.py --origen "$TMP/out" --reemplazar-ids   # != 0 si no valida: el demo queda intacto
(cd web && npm install && npm run build)
echo "Listo. Serví la demo con: cd web && npm run preview"
