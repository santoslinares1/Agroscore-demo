"""Proveedores de datos crudos para el pipeline.

`ProveedorGEE` es el real (Earth Engine + mapas de cultivo). El proveedor de
ejemplo vive en `ejemplo.py` y genera datos SINTÉTICOS marcados como tales.
Ambos exponen la misma interfaz, así el resto del pipeline (score, render, PDF,
JSON) es idéntico en los dos casos.
"""
from __future__ import annotations

from pathlib import Path

from . import crops, s2, soil_climate, water
from .gee import inicializar


class ProveedorGEE:
    ejemplo = False
    nombre = "gee"

    def __init__(self, project: str | None = None, cultivos_dir: str | Path = "data/cultivos",
                 idecor_asset_patron: str | None = None, usar_mapbiomas: bool = True):
        inicializar(project)
        self.fuentes: list = [crops.FuenteIDECORLocal(cultivos_dir)]
        if idecor_asset_patron:
            self.fuentes.append(crops.FuenteIDECOREE(idecor_asset_patron))
        if usar_mapbiomas:
            self.fuentes.append(crops.FuenteMapBiomas())

    def stats_campanias(self, lote, campanias):
        return {c: s2.stats_campania(lote, c) for c in campanias}

    def cultivos(self, lote, campanias):
        return crops.cultivos_por_campania(lote, campanias, self.fuentes)

    def ndvi_multianual(self, lote, campanias):
        return s2.ndvi_max_multianual(lote, campanias)

    def ultima(self, lote, campania):
        return s2.ultima_campania(lote, campania)

    def ndmi(self, lote, campania):
        return s2.ndmi_campania(lote, campania)

    def suelo(self, lote):
        return soil_climate.suelo(lote)

    def clima(self, lote):
        return soil_climate.clima(lote)

    def agua(self, lote):
        return water.agua(lote)
