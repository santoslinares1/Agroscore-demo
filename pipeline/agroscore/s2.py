"""Sentinel-2 en Google Earth Engine: máscara de nubes, índices (NDVI, NDMI, EVI, NDRE, MNDWI) y
estadísticas por campaña (oct–mar). Portado de los notebooks 02 (descarga) y 03 (preproceso).

Máscara de nubes (v1.2.0): Cloud Score+ (`cs_cdf` >= config.S2_CS_UMBRAL, enlazado con linkCollection) y SCL
válida (config.S2_SCL_VALIDAS = 4, 5, 6). Reflectancias: `S2_SR_HARMONIZED` ya normaliza el offset +1000 de
las escenas posteriores a 25/01/2022; solo se divide por 10000.

Índices (reflectancias 0–1):
- NDVI = (B8 − B4)/(B8 + B4); NDMI = (B8 − B11)/(B8 + B11).
- EVI  = 2,5·(B8 − B4)/(B8 + 6·B4 − 7,5·B2 + 1). Se descarta (enmascara) lo que cae fuera de [−1, 1]:
  no es físico y sale de denominadores casi nulos (bordes de nube/sombra residuales).
- NDRE = (B8A − B5)/(B8A + B5). Se eligió B8A (865 nm, banda angosta de 20 m) y no B8 (842 nm, ancha de 10 m):
  es el par red-edge/NIR estándar y evita la contaminación por vapor de agua/rojo de la B8 ancha. B5 y B8A son
  de 20 m: GEE las remuestrea (vecino más cercano) a la grilla de 10 m, así que el NDRE tiene información de
  20 m aunque se reduzca a 10 m.
- MNDWI = (B3 − B11)/(B3 + B11) (agua; lo usa water.py para confirmar Sentinel-1).

Se exportan ESTADÍSTICAS por campaña y rasters chicos del lote (para zonas y
render), nunca rasters crudos de escenas completas.
"""
from __future__ import annotations

from . import config
from .gee import a_numpy, ee, geometria


# Fórmulas como texto: la MISMA cadena corre en Earth Engine (`Image.expression`) y se contrasta en los tests
# contra las funciones numpy `evi()` / `ndre()` (ee.Image no sobrecarga los operadores aritméticos de Python).
EVI_EXPR = "2.5 * (b8 - b4) / (b8 + 6 * b4 - 7.5 * b2 + 1)"
NDRE_EXPR = "(b8a - b5) / (b8a + b5)"


def evi(b8, b4, b2):
    """EVI con reflectancias 0–1 (float o ndarray)."""
    return 2.5 * (b8 - b4) / (b8 + 6 * b4 - 7.5 * b2 + 1)


def ndre(b8a, b5):
    """NDRE = (B8A − B5)/(B8A + B5) con reflectancias 0–1 (float o ndarray)."""
    return (b8a - b5) / (b8a + b5)


def _mascara(img):
    """Máscara booleana: Cloud Score+ (cs_cdf >= umbral) Y SCL en config.S2_SCL_VALIDAS (4, 5, 6)."""
    scl = img.select("SCL")
    valida = scl.remap(config.S2_SCL_VALIDAS, [1] * len(config.S2_SCL_VALIDAS), 0)
    return valida.And(img.select(config.S2_CS_BANDA).gte(config.S2_CS_UMBRAL))


def _enmascarar(img):
    return img.updateMask(_mascara(img))


def _indices(img):
    r = img.select(["B2", "B3", "B4", "B5", "B8", "B8A", "B11"]).divide(config.S2_ESCALA_REFLECTANCIA)
    b2, b3, b4, b5, b8, b8a, b11 = (r.select(b) for b in ("B2", "B3", "B4", "B5", "B8", "B8A", "B11"))
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndmi = img.normalizedDifference(["B8", "B11"]).rename("NDMI")
    e = r.expression(EVI_EXPR, {"b8": b8, "b4": b4, "b2": b2})
    e = e.updateMask(e.gte(-1).And(e.lte(1))).rename("EVI")
    nd = r.expression(NDRE_EXPR, {"b8a": b8a, "b5": b5}).rename("NDRE")
    mn = b3.subtract(b11).divide(b3.add(b11)).rename("MNDWI")
    return img.addBands([ndvi, ndmi, e, nd, mn]).copyProperties(img, ["system:time_start"])


def coleccion_mndwi(geom, inicio: str, fin: str):
    """Colección liviana para la confirmación de agua: solo MNDWI de escenas limpias (misma máscara que `coleccion`).

    Un píxel enmascarado = sin observación válida (nube/sombra/SCL excluida)."""
    def _mndwi(i):
        r = i.select(["B3", "B11"]).divide(config.S2_ESCALA_REFLECTANCIA)
        return r.normalizedDifference(["B3", "B11"]).rename("MNDWI") \
            .updateMask(_mascara(i)).copyProperties(i, ["system:time_start"])
    return _enlazada(geom, inicio, fin).map(_mndwi)


def _enlazada(geom, inicio: str, fin: str):
    mod = ee()
    s2 = (
        mod.ImageCollection(config.S2_COLECCION)
        .filterBounds(geom)
        .filterDate(inicio, fin)
        .filter(mod.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.S2_MAX_NUBES_ESCENA))
    )
    cs = mod.ImageCollection(config.S2_CLOUD_SCORE_PLUS)
    # linkCollection agrega `cs_cdf` por system:index; una escena sin match quedaría sin la banda y se descarta
    # (en los lotes de ejemplo matchean todas).
    col = s2.linkCollection(cs, [config.S2_CS_BANDA]).map(
        lambda i: mod.Algorithms.If(i.bandNames().contains(config.S2_CS_BANDA), i, None), True)
    return mod.ImageCollection(col)


def coleccion(geom, inicio: str, fin: str, enmascarar: bool = True):
    col = _enlazada(geom, inicio, fin)
    if enmascarar:
        col = col.map(_enmascarar)
    return col.map(_indices)


def stats_campania(lote, campania: str) -> dict:
    """Estadísticas del lote para una campaña.

    - ndvi_max: media espacial del compuesto de máximo NDVI por píxel.
    - ndvi_medio: media espacial del compuesto de media NDVI por píxel.
    - ndmi_medio: ídem con NDMI.
    - evi_max / evi_medio, ndre_max / ndre_medio: ídem con EVI y NDRE (ver docstring del módulo).
    - obs_validas_px: media espacial del número de observaciones válidas (post-máscara) por píxel.
    - pct_nubes: % de observaciones píxel-fecha perdidas por nubes/sombras.
    - hueco_max_semanas: mayor cantidad de semanas seguidas sin observación válida.
    """
    mod = ee()
    geom = geometria(lote)
    inicio, fin = config.campania_fechas(campania)
    col = coleccion(geom, inicio, fin)
    n = col.size().getInfo()
    if n == 0:
        return {"ndvi_max": None, "ndvi_medio": None, "ndmi_medio": None,
                "evi_max": None, "evi_medio": None, "ndre_max": None, "ndre_medio": None,
                "pct_nubes": None, "hueco_max_semanas": None, "n_escenas": 0, "obs_validas_px": None}

    comp = mod.Image.cat([
        col.select("NDVI").max().rename("ndvi_max"),
        col.select("NDVI").mean().rename("ndvi_medio"),
        col.select("NDMI").mean().rename("ndmi_medio"),
        col.select("EVI").max().rename("evi_max"),
        col.select("EVI").mean().rename("evi_medio"),
        col.select("NDRE").max().rename("ndre_max"),
        col.select("NDRE").mean().rename("ndre_medio"),
        col.select("NDVI").count().rename("obs_validas_px"),
    ])
    red = comp.reduceRegion(mod.Reducer.mean(), geom, config.S2_ESCALA_M, maxPixels=1e9).getInfo()

    # % de nubes: observaciones válidas vs. totales dentro del polígono
    total = coleccion(geom, inicio, fin, enmascarar=False).select("NDVI").count()
    validas = col.select("NDVI").count()
    cnt = mod.Image.cat([total.rename("t"), validas.rename("v")]).reduceRegion(
        mod.Reducer.sum(), geom, config.S2_ESCALA_M * 2, maxPixels=1e9).getInfo()
    pct_nubes = None
    if cnt.get("t"):
        pct_nubes = round(100 * (1 - (cnt.get("v") or 0) / cnt["t"]))

    serie = serie_semanal(lote, campania, col=col)
    return {
        "ndvi_max": _r(red.get("ndvi_max")),
        "ndvi_medio": _r(red.get("ndvi_medio")),
        "ndmi_medio": _r(red.get("ndmi_medio")),
        "evi_max": _r(red.get("evi_max")),
        "evi_medio": _r(red.get("evi_medio")),
        "ndre_max": _r(red.get("ndre_max")),
        "ndre_medio": _r(red.get("ndre_medio")),
        "obs_validas_px": _r(red.get("obs_validas_px"), 1),
        "pct_nubes": pct_nubes,
        "hueco_max_semanas": hueco_max_semanas(serie),
        "n_escenas": n,
    }


def serie_semanal(lote, campania: str, col=None) -> list[tuple[str, float | None]]:
    """Serie semanal de NDVI medio del lote (None si la semana no tuvo dato válido)."""
    mod = ee()
    geom = geometria(lote)
    inicio, fin = config.campania_fechas(campania)
    col = col or coleccion(geom, inicio, fin)
    semanas = mod.List.sequence(0, mod.Date(fin).difference(mod.Date(inicio), "week").floor().subtract(1))

    def _semana(k):
        d0 = mod.Date(inicio).advance(k, "week")
        sub = col.filterDate(d0, d0.advance(1, "week")).select("NDVI")
        val = mod.Algorithms.If(
            sub.size().gt(0),
            sub.mean().reduceRegion(mod.Reducer.mean(), geom, 20).get("NDVI"),
            None,
        )
        return mod.Feature(None, {"semana": d0.format("YYYY-MM-dd"), "ndvi": val})

    fc = mod.FeatureCollection(semanas.map(_semana)).getInfo()
    return [(f["properties"]["semana"], f["properties"].get("ndvi")) for f in fc["features"]]


def hueco_max_semanas(serie: list[tuple[str, float | None]]) -> int:
    peor = act = 0
    for _, v in serie:
        act = act + 1 if v is None else 0
        peor = max(peor, act)
    return peor


def ndvi_max_multianual(lote, campanias: list[str]):
    """Array [alto, ancho] con la media de los compuestos de NDVI máx. por campaña."""
    mod = ee()
    geom = geometria(lote)
    comps = []
    for c in campanias:
        i, f = config.campania_fechas(c)
        comps.append(coleccion(geom, i, f).select("NDVI").max())
    img = mod.ImageCollection(comps).mean().rename("NDVI")
    arr, bbox = a_numpy(img, geom, ["NDVI"], config.S2_ESCALA_M)
    return arr[..., 0], bbox


def ultima_campania(lote, campania: str):
    """(ndvi_max [h,w], rgb [h,w,3] reflectancia 0–1, bbox, fecha_rgb) de la campaña."""
    mod = ee()
    geom = geometria(lote)
    i, f = config.campania_fechas(campania)
    col = coleccion(geom, i, f)
    ndvi, bbox = a_numpy(col.select("NDVI").max(), geom, ["NDVI"], config.S2_ESCALA_M)
    # RGB: la escena más limpia de enero–febrero (pico del cultivo de verano)
    y = int(campania.split("/")[0]) + 1
    pico = col.filterDate(f"{y}-01-01", f"{y}-03-01").sort("CLOUDY_PIXEL_PERCENTAGE")
    escena = mod.Image(pico.first())
    fecha = mod.Date(escena.get("system:time_start")).format("YYYY-MM-dd").getInfo()
    rgb, _ = a_numpy(escena.select(["B4", "B3", "B2"]).divide(10000), geom, ["B4", "B3", "B2"], config.S2_ESCALA_M)
    return ndvi[..., 0], rgb, bbox, fecha


def ndmi_campania(lote, campania: str):
    """Array [alto, ancho] de NDMI medio de la campaña (humedad de la vegetación) y bbox."""
    geom = geometria(lote)
    i, f = config.campania_fechas(campania)
    arr, bbox = a_numpy(coleccion(geom, i, f).select("NDMI").mean(), geom, ["NDMI"], config.S2_ESCALA_M)
    return arr[..., 0], bbox


def _r(v, n: int = 3):
    return None if v is None else round(float(v), n)
