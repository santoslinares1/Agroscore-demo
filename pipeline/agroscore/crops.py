"""Cultivo por campaña y rotación de maní (módulo nuevo, crítico para maní).

Fuentes, en orden de preferencia (se registra cuál se usó en `cultivo_fuente`):
1. IDECOR (Córdoba): Coberturas Agrícolas Estivales por campaña (GeoTIFF, WCS de Mapas
   Córdoba). Se dejan en `data/cultivos/idecor_<AAAA-AA>.tif` (recorte por lote) o se
   suben a Earth Engine (ver `FuenteIDECOREE`). Códigos de clase POR CAMPAÑA en
   `config.IDECOR_CLASES_POR_CAMPANIA` (verificados; ver README). Solo 2017/18 y 2023/24 en
   adelante separan maní; 2022/23 lo deja dentro de "otros".
2. MapBiomas Argentina (respaldo, en Earth Engine). NO distingue maní: devuelve claves
   genéricas ("agricultura", "cultivo_temporario"...) que cuentan como SIN DATO de maní.

Regla de rotación: una campaña es dato de maní solo si el cultivo es conocido y distinto de
los indeterminados (`config.CULTIVOS_MANI_INDETERMINADO`). `None` o indeterminado = faltante,
nunca "sin maní".

Método: moda de la clase dentro del polígono con % de cobertura. Si la clase
dominante cubre < 60% del lote -> "mixto".
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from . import config

log = logging.getLogger("agroscore")


def cultivo_dominante(histograma: dict[str, float], umbral: float = config.CULTIVO_UMBRAL_DOMINANTE):
    """Devuelve (cultivo, cobertura 0–1). Histograma: clase -> píxeles (o área).

    Ignora clases sin dato. Si la dominante < umbral, devuelve ("mixto", cobertura).
    """
    hist = {k: float(v) for k, v in histograma.items() if k and v and v > 0}
    total = sum(hist.values())
    if total <= 0:
        return None, 0.0
    clase, n = max(hist.items(), key=lambda kv: kv[1])
    cob = n / total
    if cob < umbral:
        return "mixto", round(cob, 2)
    return clase, round(cob, 2)


def estado_mani(cultivo: str | None) -> str:
    """'mani' | 'no_mani' (cultivo conocido y distinto de maní) | 'sin_dato' (None o indeterminado)."""
    if cultivo == config.CULTIVO_CLAVE_MANI:
        return "mani"
    if cultivo is None or cultivo in config.CULTIVOS_MANI_INDETERMINADO:
        return "sin_dato"
    return "no_mani"


def derivar_rotacion(campanias: list[dict], ventana: int = config.ROTACION_VENTANA) -> dict:
    """A partir de la lista de campañas (se ordena vieja -> nueva) con `cultivo`.

    Campañas sin dato de maní = `cultivo` None o indeterminado (ver `estado_mani`).
    - ultimo_mani: campaña más reciente con maní (o None).
    - campanias_desde_mani: campañas posteriores al último maní conocido (0 si fue la última);
      None si nunca hubo. OJO: si entre medio hay campañas sin dato es una cota superior.
    - campanias_sin_mani_confirmadas: racha de campañas CON dato y sin maní terminando en la
      última campaña (se corta en el primer maní o campaña sin dato). Es la cota inferior
      conservadora que usa el score.
    - veces_mani_ultimas_5: campañas con maní en la ventana.
    - campanias_sin_dato_ultimas_5 / campanias_con_dato_ultimas_5 / campanias_ventana /
      cobertura_rotacion (con dato / ventana, 0–1).
    - confianza_rotacion: 'completa' (ventana entera con dato), 'parcial' (>= mínimo con dato)
      o 'insuficiente' (< `ROTACION_MIN_CAMPANIAS_CON_DATO`).
    """
    ordenadas = sorted(campanias, key=lambda c: c["campania"])
    estados = [estado_mani(c.get("cultivo")) for c in ordenadas]
    ultimo_idx = None
    for i, e in enumerate(estados):
        if e == "mani":
            ultimo_idx = i
    ult = estados[-ventana:]
    n_vent = len(ult)
    con_dato = sum(1 for e in ult if e != "sin_dato")
    racha = 0
    for e in reversed(estados):
        if e != "no_mani":
            break
        racha += 1
    if con_dato < config.ROTACION_MIN_CAMPANIAS_CON_DATO:
        confianza = "insuficiente"
    elif con_dato == n_vent and n_vent == ventana:
        confianza = "completa"
    else:
        confianza = "parcial"
    return {
        "ultimo_mani": ordenadas[ultimo_idx]["campania"] if ultimo_idx is not None else None,
        "campanias_desde_mani": (len(ordenadas) - 1 - ultimo_idx) if ultimo_idx is not None else None,
        "campanias_sin_mani_confirmadas": racha,
        "veces_mani_ultimas_5": sum(1 for e in ult if e == "mani"),
        "campanias_sin_dato_ultimas_5": n_vent - con_dato,
        "campanias_con_dato_ultimas_5": con_dato,
        "campanias_ventana": n_vent,
        "cobertura_rotacion": round(con_dato / n_vent, 2) if n_vent else 0.0,
        "confianza_rotacion": confianza,
    }


class FuenteCultivo(Protocol):
    nombre: str

    def histograma(self, lote, campania: str) -> dict[str, float] | None: ...


class FuenteIDECORLocal:
    """GeoTIFFs de IDECOR (p. ej. recortes por lote bajados del WCS de Mapas Córdoba).

    Los códigos de clase cambian entre ediciones: se usa `config.IDECOR_CLASES_POR_CAMPANIA`
    (o un dict plano `clases` para pruebas). Sin mapeo verificado para la campaña -> None
    (sin dato). Los códigos que no estén en el mapeo (fondo 0, NaN, valores sin etiqueta) se
    ignoran: nunca se asumen "otros".
    """

    nombre = "IDECOR"

    def __init__(self, carpeta: str | Path, clases: dict | None = None):
        self.carpeta = Path(carpeta)
        self.clases = clases

    def _archivo(self, campania: str) -> Path:
        return self.carpeta / f"idecor_{campania.replace('/', '-')}.tif"

    def _mapeo(self, campania: str) -> dict[int, str] | None:
        if self.clases is not None:
            # plano {codigo: clase} o por campaña {campania: {codigo: clase}}
            if self.clases and all(isinstance(k, str) for k in self.clases):
                return self.clases.get(campania)
            return self.clases
        return config.IDECOR_CLASES_POR_CAMPANIA.get(campania)

    def histograma(self, lote, campania: str):
        f = self._archivo(campania)
        mapeo = self._mapeo(campania)
        if not f.exists() or not mapeo:
            return None
        try:
            import numpy as np
            import rasterio
            from rasterio.mask import mask
            from rasterio.warp import transform_geom
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Para leer GeoTIFF de IDECOR instalá rasterio: pip install rasterio") from exc
        with rasterio.open(f) as src:
            geom = transform_geom("EPSG:4326", src.crs, lote.geometry)
            try:
                data, _ = mask(src, [geom], crop=True, filled=False)
            except ValueError:  # el lote no solapa el raster
                return None
            vals = np.ma.asarray(data[0]).compressed()
        vals = vals[np.isfinite(vals)]
        cods, cuenta = np.unique(vals, return_counts=True)
        hist: dict[str, float] = {}
        for c, n in zip(cods, cuenta):
            clase = mapeo.get(int(c))
            if clase is not None:
                hist[clase] = hist.get(clase, 0.0) + float(n)
        return hist or None


class FuenteIDECOREE:
    """Mapas IDECOR subidos como assets de Earth Engine.

    `patron` con {campania}, p. ej. 'projects/mi-proyecto/assets/idecor_{campania}'
    donde campania = '2024_25'.
    """

    nombre = "IDECOR"

    def __init__(self, patron: str, banda: str = "b1", clases: dict | None = None):
        self.patron = patron
        self.banda = banda
        self.clases = clases

    def histograma(self, lote, campania: str):
        from .gee import ee, geometria

        mod = ee()
        mapeo = FuenteIDECORLocal(".", self.clases)._mapeo(campania)
        if not mapeo:
            return None
        asset = self.patron.format(campania=campania.replace("/", "_"))
        try:
            img = mod.Image(asset).select(self.banda)
            h = img.reduceRegion(mod.Reducer.frequencyHistogram(), geometria(lote), 10, maxPixels=1e9) \
                .get(self.banda).getInfo()
        except mod.EEException as exc:  # asset inexistente, cuota, etc.: queda sin dato, pero se avisa
            log.warning("IDECOR (asset %s, campaña %s): %s", asset, campania, exc)
            return None
        if not h:
            return None
        hist: dict[str, float] = {}
        for k, v in h.items():
            clase = mapeo.get(int(float(k)))
            if clase is not None:
                hist[clase] = hist.get(clase, 0.0) + float(v)
        return hist or None


class FuenteMapBiomas:
    """MapBiomas Argentina en Earth Engine (respaldo). NO distingue maní.

    Devuelve clases genéricas (p. ej. "cultivo_temporario"); `cultivos_por_campania` las trata
    como sin dato de maní. Asset, banda y años: ver SIN VERIFICAR en `config.MAPBIOMAS_ASSET`.
    La campaña 2024/25 se asocia al mapa anual 2024 (SUPUESTO: la campaña cruza dos años
    calendario); si la banda de ese año no existe, la campaña queda sin mapa.
    """

    nombre = "MapBiomas"
    distingue_mani = False

    def __init__(self, asset: str = config.MAPBIOMAS_ASSET, clases: dict[int, str] | None = None,
                 banda: str = config.MAPBIOMAS_BANDA):
        self.asset = asset
        self.clases = clases or config.MAPBIOMAS_CLASES
        self.banda = banda

    def histograma(self, lote, campania: str):
        from .gee import ee, geometria

        mod = ee()
        anio = int(campania.split("/")[0])
        banda = self.banda.format(anio=anio)
        try:
            img = mod.Image(self.asset)
            if banda not in img.bandNames().getInfo():
                log.info("MapBiomas: el asset no tiene la banda %s (campaña %s): sin mapa", banda, campania)
                return None
            h = img.select(banda).reduceRegion(
                mod.Reducer.frequencyHistogram(), geometria(lote), 30, maxPixels=1e9).get(banda).getInfo()
        except mod.EEException as exc:  # asset inexistente, cuota, etc.: queda sin dato, pero se avisa
            log.warning("MapBiomas (asset %s, campaña %s): %s", self.asset, campania, exc)
            return None
        if not h:
            return None
        hist: dict[str, float] = {}
        for k, v in h.items():
            clase = self.clases.get(int(float(k)))  # códigos fuera de la leyenda se ignoran
            if clase is not None:
                hist[clase] = hist.get(clase, 0.0) + float(v)
        return hist or None


def cultivos_por_campania(lote, campanias: Iterable[str], fuentes: list[FuenteCultivo]):
    """Para cada campaña prueba las fuentes en orden. Devuelve (dict, advertencias).

    Una fuente que no distingue maní (`distingue_mani = False`) nunca puede dar "mani": si su
    clase dominante fuera maní se degrada a "agricultura". Los cultivos indeterminados
    (`config.CULTIVOS_MANI_INDETERMINADO`) generan una advertencia: cuentan como sin dato de
    maní en la rotación.
    """
    res: dict[str, dict] = {}
    adv: list[str] = []
    for c in campanias:
        hecho = False
        for f in fuentes:
            h = f.histograma(lote, c)
            if h:
                cultivo, cob = cultivo_dominante(h)
                if cultivo == config.CULTIVO_CLAVE_MANI and not getattr(f, "distingue_mani", True):
                    cultivo = "agricultura"
                res[c] = {"cultivo": cultivo, "cultivo_fuente": f.nombre, "cultivo_cobertura": cob}
                if cultivo in config.CULTIVOS_MANI_INDETERMINADO:
                    adv.append(f"Campaña {c}: cultivo '{cultivo}' ({f.nombre}) no permite descartar maní; "
                               "cuenta como sin dato de maní para la rotación.")
                hecho = True
                break
        if not hecho:
            res[c] = {"cultivo": None, "cultivo_fuente": None, "cultivo_cobertura": None}
            adv.append(f"Campaña {c}: sin mapa de cultivo disponible (cultivo = null).")
    return res, adv
