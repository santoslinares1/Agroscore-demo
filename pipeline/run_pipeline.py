#!/usr/bin/env python3
"""Genera los artefactos de la demo para cada lote del GeoJSON.

Uso real (Earth Engine):
    python run_pipeline.py data/lotes.geojson --gee-project MI_PROYECTO
KML/KMZ de Google Earth (cada Polygon es un lote):
    python run_pipeline.py data/ejemplo_carga.kml --gee-project MI_PROYECTO
Datos de EJEMPLO (sintéticos, sin cuenta de GEE; quedan marcados como ejemplo):
    python run_pipeline.py data/lotes_ejemplo.geojson --ejemplo
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agroscore import aoi, config, pipeline  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lotes", help="GeoJSON, KML o KMZ con los lotes (p. ej. exportado de Google Earth)")
    ap.add_argument("--out", default="out", help="carpeta de salida (default: out)")
    ap.add_argument("--ejemplo", action="store_true", help="usar el proveedor de DATOS DE EJEMPLO (sintéticos)")
    ap.add_argument("--gee-project", default=None, help="proyecto de Google Cloud para Earth Engine (o EE_PROJECT)")
    ap.add_argument("--cultivos-dir", default="data/cultivos", help="GeoTIFFs de IDECOR idecor_AAAA-AA.tif")
    ap.add_argument("--idecor-asset", default=None, help="patrón de assets EE, ej. projects/p/assets/idecor_{campania}")
    ap.add_argument("--sin-mapbiomas", action="store_true", help="no usar MapBiomas como respaldo")
    ap.add_argument("--desde", type=int, default=config.PRIMERA_CAMPANIA)
    ap.add_argument("--hasta", type=int, default=config.ULTIMA_CAMPANIA)
    ap.add_argument("--narrar", action="store_true", help="resumen con Claude (requiere ANTHROPIC_API_KEY)")
    ap.add_argument("--solo", nargs="*", help="procesar solo estos ids")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    lotes = aoi.cargar(a.lotes)
    if a.solo:
        lotes = [l for l in lotes if l.id in a.solo]
    if a.ejemplo:
        from agroscore.ejemplo import ProveedorEjemplo
        prov = ProveedorEjemplo()
        logging.warning("MODO EJEMPLO: los resultados son sintéticos y quedan marcados como tales.")
    else:
        from agroscore.proveedores import ProveedorGEE
        prov = ProveedorGEE(a.gee_project, a.cultivos_dir, a.idecor_asset, not a.sin_mapbiomas)

    out = Path(a.out)
    camp = config.campanias(a.desde, a.hasta)
    docs = [pipeline.procesar_lote(l, prov, out, camp, narrar=a.narrar) for l in lotes]
    pipeline.escribir_index(docs, out)
    print(f"\n{'Lote':<28} {'ha':>7} {'Score':>6}  Advertencias")
    for d in docs:
        sc = d["score"]["valor"]
        print(f"{d['id']:<28} {d['area_ha']:>7} {'s/d' if sc is None else sc:>6}  {len(d['advertencias'])}")
    print(f"\nSalida en {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
