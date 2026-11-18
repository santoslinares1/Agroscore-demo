"""Riesgo de anegamiento (módulo "riesgo"): JRC Global Surface Water + Sentinel-1 + confirmación óptica.

- frecuencia_pct: ocurrencia media de agua (JRC GSW, 1984–2021) dentro del lote.
- max_ha_anegadas / fecha_max: máxima superficie ANEGADA en AGUA_ANIOS. Un píxel cuenta solo si
  (1) Sentinel-1 lo marca como agua (VV filtrado < -18 dB) Y
  (2) lo confirma el óptico o JRC (v1.2.0, ver `confirmar_anegado`):
      a. MNDWI > AGUA_MNDWI_UMBRAL en alguna escena Sentinel-2 limpia (Cloud Score+ + SCL) dentro de
         ± AGUA_VENTANA_OPTICA_DIAS días de la escena S1; o
      b. JRC GSW `occurrence` >= AGUA_JRC_OCURRENCIA_MIN_PCT.
  Sin observación óptica válida en la ventana (nubes) el píxel NO se confirma por el óptico (conservador:
  puede subestimar un anegamiento bajo nubes persistentes). El valor sin confirmar queda aparte en
  `max_ha_s1_sin_confirmar` para poder auditar cuánto descartó el criterio.
- Se usa `JRC/GSW1_4/GlobalSurfaceWater` (estático, 1984–2021). `JRC/GSW1_4/MonthlyHistory` termina en
  2021-12 y no cubre 2022–2025, así que no sirve para escenas recientes.

Correcciones verificadas con GEE real: (1) en ~8 % de las escenas S1_GRD el lote cae en el borde del swath
y el VV es ruido/nodata (-50 a -90 dB); eso se contaba como «100 % anegado». Se enmascara VV <= S1_VV_MIN_VALIDO_DB
y se descartan las escenas que cubren menos de S1_COBERTURA_MIN del lote. (2) En sequías el suelo desnudo liso
también da VV < -18 dB y se marcaba como agua (39–52 ha falsas por lote en la corrida v1.1.0); la confirmación
óptica/JRC apunta a eso. Los umbrales siguen SIN calibrar contra anegamientos reales: tomar el valor como indicio.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import config, s2
from .gee import ee, geometria


def ventana_optica(fecha_iso: str, dias: int | None = None) -> tuple[str, str]:
    """Ventana óptica [inicio, fin) para una escena S1 del día `fecha_iso`: ± `dias`, con fin EXCLUSIVO
    (por eso suma un día extra), p. ej. ('2022-10-14', 10) -> ('2022-10-04', '2022-10-25')."""
    n = config.AGUA_VENTANA_OPTICA_DIAS if dias is None else dias
    d = date.fromisoformat(fecha_iso)
    return (d - timedelta(days=n)).isoformat(), (d + timedelta(days=n + 1)).isoformat()


def _y(a, b):
    return a.And(b) if hasattr(a, "And") else (a & b)


def _o(a, b):
    return a.Or(b) if hasattr(a, "Or") else (a | b)


def confirmar_anegado(s1_agua, optico_agua, jrc_agua):
    """Regla de confirmación (funciona con ndarray bool y con ee.Image 0/1):

        anegado = s1_agua  Y  (optico_agua  O  jrc_agua)

    `optico_agua` debe ser False (0) donde NO hay observación óptica válida: sin óptico no se confirma,
    solo JRC puede confirmar. El mismo código corre en Earth Engine y en los tests.
    """
    return _y(s1_agua, _o(optico_agua, jrc_agua))


def jrc_es_agua(occurrence, minimo_pct: float | None = None):
    """True donde la ocurrencia JRC (%) es >= mínimo (ndarray o ee.Image). Ocurrencia sin dato = no agua."""
    m = config.AGUA_JRC_OCURRENCIA_MIN_PCT if minimo_pct is None else minimo_pct
    return occurrence.gte(m) if hasattr(occurrence, "gte") else occurrence >= m


def _filas_periodo(mod, geom, jrc_agua, area_ha: float, inicio: str, fin: str) -> list[dict]:
    """Escenas S1 de [inicio, fin) con su ha de agua S1, ha confirmadas y ha del lote con óptico válido."""
    n_dias = config.AGUA_VENTANA_OPTICA_DIAS
    s1 = (
        mod.ImageCollection(config.S1_COLECCION)
        .filterBounds(geom)
        .filterDate(inicio, fin)
        .filter(mod.Filter.eq("instrumentMode", "IW"))
        .filter(mod.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .select("VV")
    )
    # Óptico limpio: 1 donde MNDWI > umbral, 0 donde hay observación válida sin agua, MASCARADO donde no hay dato
    # válido (nube/sombra/SCL excluida). Margen de ± n_dias alrededor del período para las escenas de los bordes.
    i0 = mod.Date(inicio).advance(-n_dias, "day")
    f0 = mod.Date(fin).advance(n_dias + 1, "day")
    opt = s2.coleccion_mndwi(geom, i0, f0) \
        .map(lambda i: i.gt(config.AGUA_MNDWI_UMBRAL).rename("w").copyProperties(i, ["system:time_start"]))
    # ventana vacía: max() de una colección vacía no tiene bandas; se le suma una imagen totalmente enmascarada.
    vacia = mod.ImageCollection([mod.Image(0).rename("w").selfMask()])
    px = mod.Image.pixelArea().divide(10_000)

    def _ha(m):
        return m.multiply(px).reduceRegion(mod.Reducer.sum(), geom, 10, maxPixels=1e9, tileScale=4).get("VV")

    def _escena(img):
        valido = img.gt(config.S1_VV_MIN_VALIDO_DB)          # fuera de swath / nodata -> inválido
        s1_agua = img.updateMask(valido).focal_median(30, "circle", "meters").lt(config.S1_UMBRAL_AGUA_DB).unmask(0)
        t = img.date()
        ventana = opt.filterDate(t.advance(-n_dias, "day"), t.advance(n_dias + 1, "day"))
        max_w = ventana.merge(vacia).max().select("w")
        optico_agua = max_w.unmask(0)                        # sin observación válida -> 0 (no confirma)
        conf = confirmar_anegado(s1_agua, optico_agua, jrc_agua)
        return mod.Feature(None, {
            "ha_s1": _ha(s1_agua.rename("VV").updateMask(valido)),
            "ha": _ha(conf.rename("VV").updateMask(valido)),
            "ha_valida": _ha(valido),
            "ha_optico": _ha(max_w.mask().rename("VV").updateMask(valido)),  # ha del lote con óptico válido en la ventana
            "fecha": t.format("YYYY-MM-dd")})

    fc = mod.FeatureCollection(s1.map(_escena)).filter(mod.Filter.notNull(["ha", "ha_s1", "ha_valida", "ha_optico"])) \
        .filter(mod.Filter.gte("ha_valida", area_ha * config.S1_COBERTURA_MIN))
    return [f["properties"] for f in fc.getInfo()["features"]]


def agua(lote) -> dict:
    mod = ee()
    geom = geometria(lote)
    occ = mod.Image(config.JRC_GSW).select("occurrence").unmask(0)
    frec = occ.reduceRegion(mod.Reducer.mean(), geom, 30).get("occurrence").getInfo()
    jrc_agua = jrc_es_agua(occ)
    area_ha = geom.area(1).getInfo() / 10_000
    a0, a1 = config.AGUA_ANIOS
    filas: list[dict] = []
    # por año: una sola consulta con ~600 escenas S1 anidando ventanas ópticas supera el límite de memoria de GEE
    for anio in range(a0, a1 + 1):
        filas += _filas_periodo(mod, geom, jrc_agua, area_ha, f"{anio}-01-01", f"{anio + 1}-01-01")
    return resumir_escenas(filas, frec, area_ha)


def resumir_escenas(filas: list[dict], frecuencia_pct, area_ha: float | None = None) -> dict:
    """Resume las escenas S1 (cada una: ha, ha_s1, ha_optico, fecha) en el dict `agua` del lote.

    Lógica pura (sin red): máximo confirmado, máximo S1 sin confirmar y cuántas escenas tuvieron óptico.
    """
    def _tope(clave):
        return max(filas, key=lambda p: p[clave]) if filas else None

    conf, crudo = _tope("ha"), _tope("ha_s1")
    auditoria: dict = {}
    if area_ha:
        marcadas = [p for p in filas if p["ha_s1"] >= config.AGUA_ESCENA_MARCADA_FRAC * area_ha]
        auditoria = {
            "n_escenas_s1_marcadas": len(marcadas),
            "n_escenas_s1_marcadas_sin_optico": sum(
                1 for p in marcadas if (p.get("ha_optico") or 0) < config.AGUA_OPTICO_COBERTURA_MIN * area_ha),
            "n_escenas_s1_confirmadas": sum(1 for p in filas if p["ha"] > 0),
        }
    return {
        "max_ha_anegadas": round(conf["ha"], 1) if conf else None,
        "fecha_max": conf["fecha"] if conf and conf["ha"] > 0 else None,
        "frecuencia_pct": None if frecuencia_pct is None else round(frecuencia_pct, 1),
        "max_ha_s1_sin_confirmar": round(crudo["ha_s1"], 1) if crudo else None,
        "fecha_max_s1_sin_confirmar": crudo["fecha"] if crudo else None,
        "n_escenas_s1": len(filas),
        "n_escenas_s1_con_optico": sum(1 for p in filas if (p.get("ha_optico") or 0) > 0),
        **auditoria,
        "criterio": (f"Sentinel-1 VV < {config.S1_UMBRAL_AGUA_DB:g} dB confirmado por MNDWI > "
                     f"{config.AGUA_MNDWI_UMBRAL:g} en S2 limpio (Cloud Score+ y SCL) a ± "
                     f"{config.AGUA_VENTANA_OPTICA_DIAS} días, o JRC occurrence >= "
                     f"{config.AGUA_JRC_OCURRENCIA_MIN_PCT:g} %; sin óptico válido no se confirma"),
    }
