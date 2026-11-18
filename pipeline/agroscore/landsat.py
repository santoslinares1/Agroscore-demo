"""(Opcional) Historia Landsat 5/7/8/9 desde 2000 para NDVI por campaña.

No se usa en el score; queda disponible para extender la serie
(notebook 05). Usa Collection 2 Level 2 con máscara QA_PIXEL.
"""
from __future__ import annotations

from . import config
from .gee import ee, geometria

_COLS = {
    "LANDSAT/LT05/C02/T1_L2": ("SR_B4", "SR_B3"),
    "LANDSAT/LE07/C02/T1_L2": ("SR_B4", "SR_B3"),
    "LANDSAT/LC08/C02/T1_L2": ("SR_B5", "SR_B4"),
    "LANDSAT/LC09/C02/T1_L2": ("SR_B5", "SR_B4"),
}


def _prep(nir: str, red: str):
    def f(img):
        qa = img.select("QA_PIXEL")
        limpio = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        sr = img.select([nir, red]).multiply(0.0000275).add(-0.2)
        return sr.normalizedDifference([nir, red]).rename("NDVI").updateMask(limpio) \
            .copyProperties(img, ["system:time_start"])
    return f


def ndvi_max_campania(lote, campania: str) -> float | None:
    mod = ee()
    geom = geometria(lote)
    i, f = config.campania_fechas(campania)
    cols = [mod.ImageCollection(c).filterBounds(geom).filterDate(i, f).map(_prep(*b)) for c, b in _COLS.items()]
    col = cols[0]
    for c in cols[1:]:
        col = col.merge(c)
    if col.size().getInfo() == 0:
        return None
    v = col.max().reduceRegion(mod.Reducer.mean(), geom, 30).get("NDVI").getInfo()
    return None if v is None else round(v, 3)
