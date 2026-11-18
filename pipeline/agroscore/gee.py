"""Inicialización de Google Earth Engine y utilidades comunes.

Requiere `pip install earthengine-api` y haber corrido una vez
`earthengine authenticate` con la cuenta propia. El proyecto de Cloud se pasa por
`--gee-project` o la variable de entorno `EE_PROJECT`.
"""
from __future__ import annotations

import os
from typing import Any

_ee: Any = None
GEE_PLAZO_MS = 5 * 60 * 1000  # plazo por consulta a Earth Engine (ee.data.setDeadline)


def ee():
    """Devuelve el módulo `ee` ya inicializado (import perezoso)."""
    global _ee
    if _ee is None:
        try:
            import ee as _mod  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Falta earthengine-api: pip install earthengine-api") from exc
        _ee = _mod
    return _ee


def inicializar(project: str | None = None) -> None:
    mod = ee()
    project = project or os.environ.get("EE_PROJECT")
    try:
        mod.Initialize(project=project) if project else mod.Initialize()
        # sin plazo, una consulta colgada (visto en la corrida v1.2.0: >10 min sin respuesta) bloquea el pipeline
        if hasattr(mod.data, "setDeadline"):
            mod.data.setDeadline(GEE_PLAZO_MS)
    except Exception as exc:  # pragma: no cover - depende de credenciales
        raise RuntimeError(
            "No se pudo inicializar Earth Engine. Corré `earthengine authenticate` "
            "y pasá tu proyecto con --gee-project o EE_PROJECT."
        ) from exc


def geometria(lote) -> Any:
    return ee().Geometry.Polygon(lote.geometry["coordinates"], geodesic=False)


def a_numpy(imagen, region, bandas: list[str], escala: int = 10):
    """Descarga una imagen chica (un lote) como array numpy [alto, ancho, bandas].

    Usa `ee.data.computePixels`, que devuelve un structured array; para un lote de
    ~200 ha a 10 m son ~150×150 px, muy por debajo de los límites.
    """
    import numpy as np

    mod = ee()
    bounds = region.bounds(1)
    coords = bounds.coordinates().get(0).getInfo()
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    # paso en grados equivalente a `escala` metros (aprox. a la latitud del lote)
    import math

    lat0 = (min(ys) + max(ys)) / 2
    dy = escala / 111_320.0
    dx = escala / (111_320.0 * math.cos(math.radians(lat0)))
    ancho = max(1, int(round((max(xs) - min(xs)) / dx)))
    alto = max(1, int(round((max(ys) - min(ys)) / dy)))
    req = {
        # unmask(..., sameFootprint=False): con el default (True) los píxeles fuera del polígono (o sin dato)
        # salen como 0 y no como -9999; el k-means de zonas los tomaba como NDVI = 0 (bug verificado en GEE real).
        "expression": imagen.select(bandas).clip(region).unmask(-9999, False),
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {
            "dimensions": {"width": ancho, "height": alto},
            "affineTransform": {
                "scaleX": dx, "shearX": 0, "translateX": min(xs),
                "shearY": 0, "scaleY": -dy, "translateY": max(ys),
            },
            "crsCode": "EPSG:4326",
        },
    }
    arr = mod.data.computePixels(req)
    out = np.stack([arr[b].astype("float32") for b in bandas], axis=-1)
    out[out == -9999] = np.nan
    return out, [min(xs), min(ys), max(xs), max(ys)]
