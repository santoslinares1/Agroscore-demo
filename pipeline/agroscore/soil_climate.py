"""Suelo (SoilGrids 2.0) y clima (ERA5-Land mensual) en Earth Engine.

Se eligió UNA combinación: SoilGrids + ERA5-Land (la del notebook 06 v2). La
versión del Worker con NASA POWER queda descartada para el score.
"""
from __future__ import annotations

from . import config
from .gee import ee, geometria


def suelo(lote) -> dict:
    """Arcilla y arena (%) y carbono orgánico (%) en 0–5 cm, media del lote.

    SoilGrids publica arcilla/arena en g/kg (÷10 -> %) y SOC en dg/kg
    (÷100 -> %). Bandas: '<prop>_0-5cm_mean'.
    """
    mod = ee()
    geom = geometria(lote)
    out = {}
    for clave, asset, banda, div in [
        ("arcilla_pct", config.SOILGRIDS_ASSETS["arcilla"], "clay_0-5cm_mean", 10),
        ("arena_pct", config.SOILGRIDS_ASSETS["arena"], "sand_0-5cm_mean", 10),
        ("carbono_org", config.SOILGRIDS_ASSETS["carbono"], "soc_0-5cm_mean", 100),
    ]:
        v = mod.Image(asset).select(banda).reduceRegion(mod.Reducer.mean(), geom, 250).get(banda).getInfo()
        out[clave] = None if v is None else round(v / div, 1)
    out["fuente"] = "SoilGrids"
    return out


def clima(lote) -> dict:
    """Precipitación media anual (mm) de ERA5-Land para CLIMA_ANIOS."""
    mod = ee()
    geom = geometria(lote)
    a0, a1 = config.CLIMA_ANIOS
    col = mod.ImageCollection(config.ERA5_COLECCION).filterDate(f"{a0}-01-01", f"{a1 + 1}-01-01") \
        .select("total_precipitation_sum")
    total_m = col.sum().reduceRegion(mod.Reducer.mean(), geom.centroid(1).buffer(5000), 11132) \
        .get("total_precipitation_sum").getInfo()
    pp = None if total_m is None else round(total_m * 1000 / (a1 - a0 + 1))
    return {"pp_anual_mm": pp, "fuente": "ERA5"}
