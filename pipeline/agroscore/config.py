"""Configuración central: pesos del score, campañas, umbrales y fuentes.

Todo número "de negocio" que use el pipeline vive acá, para que haya UNA sola
fuente de verdad (la web y el PDF leen el mismo lote.json que sale de acá).
"""
from __future__ import annotations

SCORE_VERSION = "1.2.0"

# Pesos del score (suman 1.0). Ver score.py para la normalización de cada componente.
SCORE_PESOS: dict[str, float] = {
    "vigor_historico": 0.35,
    "estabilidad": 0.20,
    "riesgo_hidrico": 0.20,
    "suelo": 0.15,
    "rotacion_mani": 0.10,
}

# Datos mínimos para publicar un score (v1.2.0). Sin esto el score total es null con un motivo
# legible: nunca un número armado casi solo con suelo/agua.
# - Componentes obligatorios: las series satelitales (vigor y estabilidad). Cada uno exige al
#   menos SCORE_MIN_CAMPANIAS_NDVI campañas con ndvi_max.
# - Cobertura mínima: suma de pesos nominales de los componentes con dato (0–1). Si es menor
#   se publica null. Si es >= mínima pero < 1 se publica el score REPONDERADO y el JSON lo
#   dice (score.reponderado, score.cobertura, score.componentes_usados, peso_efectivo).
SCORE_COMPONENTES_OBLIGATORIOS = ("vigor_historico", "estabilidad")
SCORE_MIN_CAMPANIAS_NDVI = 3
SCORE_COBERTURA_MIN = 0.70

# Confianza del score (M4, verificación 18/11): "alta" exige además cobertura de campañas. Con 9 campañas:
# alta >= 6 con NDVI (2/3) y 100 % del peso con dato; baja si menos de la mitad tiene NDVI. Supuesto, sin calibrar.
CONFIANZA_ALTA_FRAC_CAMPANIAS = 2 / 3
CONFIANZA_BAJA_FRAC_CAMPANIAS = 1 / 2

# El vigor puede salir de EVI, NDVI o ambos (score.vigor_base): la etiqueta con el índice la arma
# score.etiqueta_componente() según cada lote. Esta es la base, sin índice.
SCORE_ETIQUETAS: dict[str, str] = {
    "vigor_historico": "Vigor histórico",
    "estabilidad": "Estabilidad entre campañas",
    "riesgo_hidrico": "Riesgo hídrico (anegamiento)",
    "suelo": "Suelo",
    "rotacion_mani": "Rotación de maní",
}

# Campañas de verano: octubre (año N) a marzo (año N+1).
CAMPANIA_MES_INICIO = 10
CAMPANIA_MES_FIN = 3
PRIMERA_CAMPANIA = 2017  # 2017/18 (Sentinel-2 L2A completo en Argentina)
ULTIMA_CAMPANIA = 2025   # 2025/26 (terminada en marzo 2026)


def campanias(desde: int = PRIMERA_CAMPANIA, hasta: int = ULTIMA_CAMPANIA) -> list[str]:
    """Lista de campañas 'AAAA/AA' de `desde` a `hasta` inclusive."""
    return [f"{y}/{str(y + 1)[-2:]}" for y in range(desde, hasta + 1)]


def campania_fechas(campania: str) -> tuple[str, str]:
    """'2024/25' -> ('2024-10-01', '2025-04-01') (fin exclusivo)."""
    y = int(campania.split("/")[0])
    return f"{y}-{CAMPANIA_MES_INICIO:02d}-01", f"{y + 1}-{CAMPANIA_MES_FIN + 1:02d}-01"


# --- Sentinel-2 ---
S2_COLECCION = "COPERNICUS/S2_SR_HARMONIZED"
# Máscara de nubes (v1.2.0): Cloud Score+ (Google) enlazado con `linkCollection` por system:index.
# Reemplaza el join anterior con COPERNICUS/S2_CLOUD_PROBABILITY (s2cloudless, prob < 40).
# Verificado en GEE (2026-11-18): bandas `cs` y `cs_cdf`; las escenas de S2_SR_HARMONIZED de los lotes
# de ejemplo matchean 100 % (p. ej. 13/13 en 2017/18, 32/32 en 2025/26 con CLOUDY_PIXEL_PERCENTAGE < 60).
S2_CLOUD_SCORE_PLUS = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
S2_CS_BANDA = "cs_cdf"
# Umbral de cs_cdf (0 = nublado/sombra, 1 = despejado): se conserva el píxel si cs_cdf >= umbral.
# 0,60 es el valor recomendado en la documentación de Cloud Score+ para un balance nubes/cobertura
# (0,50 es más permisivo, 0,65–0,70 más estricto). Configurable; no está calibrado para estos lotes.
S2_CS_UMBRAL = 0.6
S2_MAX_NUBES_ESCENA = 60          # % CLOUDY_PIXEL_PERCENTAGE para descartar escenas (filtro de escena, previo al píxel)
# Clases SCL válidas: 4 vegetación, 5 suelo desnudo, 6 agua. Se EXCLUYEN (S2_SCL_EXCLUIDAS): 3 sombra de nube,
# 7 no clasificado/baja probabilidad, 8 y 9 nube prob. media/alta, 10 cirrus fino, 11 nieve/hielo
# (antes 7 y 11 figuraban como válidas). 0 sin dato, 1 saturado y 2 oscuro tampoco son válidas.
S2_SCL_VALIDAS = [4, 5, 6]
S2_SCL_EXCLUIDAS = [3, 7, 8, 9, 10, 11]
# Reflectancia: S2_SR_HARMONIZED ya resta el offset +1000 de las escenas con baseline >= 04.00
# (posteriores al 25/01/2022), así que todas las bandas están en la misma escala; solo hay que dividir
# por 10000 para tener reflectancia 0–1 (necesario para EVI, que tiene constantes aditivas).
S2_ESCALA_REFLECTANCIA = 10000.0
S2_ESCALA_M = 10
S2_MIN_ESCENAS = 20               # menos escenas válidas por campaña -> advertencia (S2 con 2 satélites da ~25–40)
S2_L2A_COMPLETO_DESDE = "2018-12-01"  # antes, COPERNICUS/S2_SR(_HARMONIZED) tiene solo parte de las escenas (verificado: 14 de 30 en 2017/18)
NUBES_ADVERTENCIA_PCT = 40        # si la campaña tuvo > 40% de observaciones perdidas, advertir
MAX_HUECO_SEMANAS = 3             # no interpolar más de 3 semanas seguidas

# --- Cultivos ---
CULTIVO_UMBRAL_DOMINANTE = 0.60   # < 60% de cobertura dominante -> "mixto"
CULTIVO_CLAVE_MANI = "mani"
ROTACION_VENTANA = 5              # "veces con maní en las últimas 5 campañas"
# Campañas SIN maní recomendadas entre dos maníes (riesgo de carbón, Thecaphora frezii).
# SUPUESTO agronómico: la recomendación clásica (INTA / Herbario de Fitopatología UBA) es
# "más de 3 años sin maní" => 4 campañas. Las teliosporas pueden sobrevivir 4 años o más
# (hasta ~6 según algunos estudios), así que 4 es un mínimo, no una garantía de riesgo cero.
ROTACION_ANIOS_RECOMENDADOS = 4
# Mínimo de campañas CON dato de maní dentro de la ventana para calcular el componente de
# rotación (3 de 5). Con menos, el componente queda sin valor y se renormalizan los pesos.
ROTACION_MIN_CAMPANIAS_CON_DATO = 3
# Modo estricto (opcional): si True, el componente de rotación queda en null cuando CUALQUIER
# campaña de la ventana no tiene dato de maní (en vez de calcularlo "parcial" y conservador
# con >= ROTACION_MIN_CAMPANIAS_CON_DATO). Por defecto False: el cálculo parcial ya nunca da
# 1.0 por falta de datos (una campaña sin dato corta la racha de campañas sin maní).
ROTACION_EXIGE_DATO_COMPLETO = False
# Penalización (por maní previo al último, dentro de la ventana) cuando todavía no se
# cumplió el intervalo recomendado: el inóculo se acumula con la frecuencia de maní.
ROTACION_PENALIZ_REPETICION = 0.15
# Valores de `cultivo` que NO permiten afirmar ni descartar maní en esa campaña: cuentan
# como SIN DATO para la rotación (igual que cultivo = None). "mixto" entra acá por
# conservadurismo: un lote partido (<60 % dominante) puede tener maní como minoría.
CULTIVOS_MANI_INDETERMINADO = frozenset({
    "otros_posible_mani",    # IDECOR 22/23: "Otros cultivos" no separa maní
    "agricultura", "cultivo_temporario", "mosaico_agropecuario",  # MapBiomas (sin clase de maní)
    "mixto",
})

# Mapeo de clases de los mapas de cultivos de IDECOR (Mapas Córdoba) a claves internas.
# POR CAMPAÑA: el código de clase NO es el mismo entre ediciones (p. ej. el 3 es
# "Otros cultivos" en 22/23 pero "Soja" en 23/24). Solo figuran códigos VERIFICADOS
# contra GetLegendGraphic/GetStyles (SLD) del GeoServer de IDECOR y contra conteos de
# píxeles; ver /workspace/idecor/INFORME_IDECOR.md para URLs y evidencia.
#   Raster: WCS https://idecor-wcs.mapascordoba.gob.ar/geoserver/idecor/wcs
#   Leyenda: WMS https://idecor-ws.mapascordoba.gob.ar/geoserver/idecor/wms (GetLegendGraphic)
#   Licencia: CC BY-SA 4.0 (https://www.idecor.gob.ar/terminos-y-condiciones/) -> revisar
#   la condición CompartirIgual antes de usar en un producto comercial.
# Un código que no esté acá se IGNORA (no se asume "otros"). 0/NaN = fondo (no cultivo).
# Sin entrada para una campaña = no hay mapa utilizable (no se inventa nada):
#   2018/19, 2019/20: no hay capa publicada en los geoservicios (no encontradas).
#   2020/21, 2021/22: máscaras binarias soja / maíz / otros (3 rasters por campaña,
#   valor 1 = presencia; coverageId idecor__cobertura_{soja,maiz}_2020_2021,
#   idecor__otros_cultivos_2020_2021, idecor__{soja,maiz,otros}_2122). El maní va dentro
#   de "otros" y NO se puede separar -> no entra en este diccionario (soporte multi-archivo
#   pendiente en crops.py).
# "maiz_2da"/"soja_2da" = cultivo estival de segunda tras trigo (17/18).
IDECOR_CLASES_POR_CAMPANIA: dict[str, dict[int, str]] = {
    # Land Cover Nivel 3 2017/2018 (coverageId idecor__LandCover_Nivel3_28_dic_2018_30m_completo,
    # EPSG:4326, 30 m, uint8, nodata 0). Verificado: maní 324.681 ha (raster) vs 320.891 ha (suma
    # de cultivos_por_dpto_mapa.sup_mani).
    "2017/18": {
        1: "no_agricola", 2: "no_agricola", 3: "no_agricola", 4: "no_agricola", 5: "no_agricola",
        6: "no_agricola", 7: "no_agricola", 8: "no_agricola", 9: "no_agricola", 10: "no_agricola",
        11: "no_agricola", 12: "no_agricola", 13: "no_agricola", 14: "no_agricola",
        15: "trigo", 16: "maiz", 17: "soja", 18: "mani", 19: "sorgo",
        20: "maiz_2da", 21: "soja_2da", 22: "otros", 23: "pastura", 24: "pastura",
        25: "otros", 26: "otros", 27: "otros",
    },
    # 22/23 (idecor__coberturas_estivales_2223, EPSG:22174, 10 m, uint8, nodata 8). NO separa maní:
    # su clase 3 "Otros cultivos" puede incluirlo -> "otros_posible_mani" (cuenta como sin dato de maní).
    # Aparece un valor 33 sin etiqueta (~0,02 % de píxeles): se ignora.
    "2022/23": {1: "soja", 2: "maiz", 3: "otros_posible_mani"},
    # 23/24 (idecor__coberturas_estivales_2324, uint8, nodata 0), 24/25 (..._2425, float32, fondo NaN)
    # y 25/26 (..._2526, float32, fondo NaN; sin leyenda publicada: etiquetas confirmadas porque los
    # % de superficie coinciden con lo publicado por IDECOR, ver informe).
    "2023/24": {1: "maiz", 2: "maiz", 3: "soja", 4: "mani", 5: "otros"},
    "2024/25": {1: "maiz", 2: "maiz", 3: "soja", 4: "mani", 5: "otros"},
    "2025/26": {1: "maiz", 2: "maiz", 3: "soja", 4: "mani", 5: "otros"},
}
# Obsoleto: el mapeo plano anterior (1 soja, 2 maiz, 3 mani, ...) era un SUPUESTO y es
# incorrecto para todas las ediciones verificadas. Se deja vacío a propósito.
IDECOR_CLASES: dict[int, str] = {}

# MapBiomas Argentina (respaldo). NO distingue maní: la clase más fina es "Cultivos
# temporarios" (Col. 3) o "Agricultura" (Col. 1). Por eso cualquier cultivo que devuelva
# se guarda con una clave genérica (ver CULTIVOS_MANI_INDETERMINADO) y cuenta como SIN DATO
# de maní: este respaldo nunca puede decir "no hubo maní".
# Asset de la Colección 3 tomado de https://argentina.mapbiomas.org/descargas/mapas-de-la-coleccion/
# VERIFICADO EN GEE REAL (2026-11-17, proyecto con credenciales de usuario, solo lectura): el asset existe
# (Image, collection_id 3, versión v1, serie 1985–2025), bandas `classification_1985` … `classification_2025`
# (30 m, EPSG:4326). La campaña AAAA/AA se asocia al mapa del año AAAA (supuesto); si falta la banda, queda sin mapa.
# (El asset Col. 1 anterior llegaba solo hasta 2022:
# projects/mapbiomas-public/assets/argentina/collection1/mapbiomas_argentina_collection1_integration_v1)
MAPBIOMAS_ASSET = "projects/mapbiomas-public/assets/argentina/lulc/collection3/mapbiomas_argentina_collection3_coverage_v1"
MAPBIOMAS_BANDA = "classification_{anio}"   # verificado en GEE para Col. 3
# Leyenda Col. 3 (https://argentina.mapbiomas.org/wp-content/uploads/sites/8/2026/09/ARG-LegendCode-Col3.pdf).
# Los códigos no listados se IGNORAN (no se asumen "otros").
# Clases que trae el raster, según la descripción del asset en GEE (19): 3, 4, 6, 63, 66, 77, 11, 12, 73, 34, 9,
# 15, 19, 21, 24, 36, 25, 33, 27. OJO: el 18 "Agricultura" (clase madre del PDF) NO aparece en el raster: la
# agricultura sale como 19 "Temporary crops". Los nombres en inglés de GEE están entre paréntesis.
MAPBIOMAS_CLASES_COL3: dict[int, str] = {
    3: "monte",                  # 1.1 Bosques cerrados (Closed forests)
    4: "monte",                  # Bosques abiertos (Open forests)
    6: "monte",                  # Bosques inundables (Flooded forests)
    63: "pastizal",              # Mosaico de herbáceas y arbustivas (Shrub and herbaceous mosaics)
    66: "monte",                 # Arbustales cerrados (Closed shrublands)
    77: "monte",                 # Arbustales abiertos (Open shrublands)
    11: "pastizal",              # Herbáceas inundables (Flooded grassland)
    73: "pastizal",              # Turberas (Peatlands)
    9: "forestacion",            # Plantaciones forestales (Forest plantations)
    25: "no_agricola",           # Otras áreas sin vegetación (Other non-vegetated areas)
    12: "pastizal",              # 2.4 Herbáceas
    15: "pastura",               # 3.1 Pastura
    18: "agricultura",           # 3.1 Agricultura
    19: "cultivo_temporario",    # 3.1.1 Cultivos temporarios
    21: "mosaico_agropecuario",  # 3.5 Mosaico de agricultura y pastura
    24: "urbano",                # 4.1 Áreas urbanas
    33: "agua",                  # 5.1 Ríos, lagunas, lagos y océano
    36: "cultivo_perenne",       # Cultivos perennes
}
# Leyenda Col. 1 (https://argentina.mapbiomas.org/wp-content/uploads/sites/12/2024/05/Legend-Code_Argentina-Col-1-2.pdf,
# PDF-imagen leído a ojo). Col. 1 no tiene clase urbana, ni 19 ni 39/41 (los de antes eran inventados).
MAPBIOMAS_CLASES_COL1: dict[int, str] = {
    3: "monte",                  # 1.1 Leñosa cerrada
    12: "pastizal",              # 2.2 Pastizal
    15: "pastura",               # 3.1 Pastura
    18: "agricultura",           # 3.2 Agricultura
    21: "mosaico_agropecuario",  # 3.5 Mosaico agropecuario
    33: "agua",                  # 5.1 Río, lago u océano
}
MAPBIOMAS_CLASES: dict[int, str] = MAPBIOMAS_CLASES_COL3

# --- Suelo y clima (se eligió SoilGrids + ERA5-Land, igual que el notebook) ---
SOILGRIDS_ASSETS = {
    "arcilla": "projects/soilgrids-isric/clay_mean",
    "arena": "projects/soilgrids-isric/sand_mean",
    "carbono": "projects/soilgrids-isric/soc_mean",
}
ERA5_COLECCION = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
CLIMA_ANIOS = (2016, 2025)

# Suelo "ideal" para maní: franco-arenoso, bien drenado.
SUELO_ARENA_OPTIMA = (45.0, 70.0)
SUELO_ARCILLA_MAX = 25.0
SUELO_CO_OPTIMO = 1.5  # % carbono orgánico

# --- Agua ---
JRC_GSW = "JRC/GSW1_4/GlobalSurfaceWater"
# OJO: JRC/GSW1_4/MonthlyHistory termina en 2021-12 (verificado en GEE), no cubre 2022–2025 -> no se usa.
S1_COLECCION = "COPERNICUS/S1_GRD"
S1_UMBRAL_AGUA_DB = -18.0
S1_VV_MIN_VALIDO_DB = -30.0   # por debajo es ruido/nodata de borde de swath (se vieron -50 a -90 dB), no agua
S1_COBERTURA_MIN = 0.9        # fracción mínima del lote con VV válido para usar la escena
AGUA_ANIOS = (2017, 2025)
# Confirmación (v1.2.0): un píxel que Sentinel-1 marca como agua cuenta como ANEGADO solo si
#  (a) lo confirma el óptico: MNDWI = (B3 − B11)/(B3 + B11) > AGUA_MNDWI_UMBRAL en alguna escena S2 LIMPIA
#      (máscara Cloud Score+ + SCL) dentro de ± AGUA_VENTANA_OPTICA_DIAS de la fecha de la escena S1, o
#  (b) figura como agua en JRC GSW: `occurrence` >= AGUA_JRC_OCURRENCIA_MIN_PCT (agua permanente/estacional).
# Si no hay ninguna observación óptica válida para ese píxel en la ventana (nubes), NO se confirma por el
# óptico (criterio conservador: puede subestimar un anegamiento bajo nubes persistentes).
AGUA_VENTANA_OPTICA_DIAS = 10   # N: ± días entre la escena Sentinel-1 y el óptico (configurable; sin calibrar)
AGUA_MNDWI_UMBRAL = 0.0         # MNDWI > 0 = agua (umbral clásico de Xu 2006)
AGUA_JRC_OCURRENCIA_MIN_PCT = 5.0  # supuesto sin calibrar: >= 5 % de las observaciones 1984–2021 con agua
# Solo para AUDITAR el descarte (no cambia el score): una escena S1 es «marcada» si el radar da >= 5 % del lote como
# agua; entre las marcadas se cuentan las que NO se pudieron contrastar (óptico válido en < 50 % del lote).
AGUA_ESCENA_MARCADA_FRAC = 0.05
AGUA_OPTICO_COBERTURA_MIN = 0.5

# --- Normalización del score ---
NDVI_MAX_REF = (0.55, 0.90)    # ndvi_max medio del lote -> 0..1
# Vigor con EVI (v1.2.0): el NDVI se satura con canopeo cerrado (0,94–0,95 en 2023/24) y el vigor daba 1,0.
# REFERENCIAS PROVISORIAS, NO CALIBRADAS: no hay datos de campo (rendimiento) con que calibrarlas. Se fijaron
# a priori (sin mirar los resultados de los lotes) como orden de magnitud de un pico de EVI Sentinel-2 en
# cultivos estivales: ~0,30 = canopeo ralo/estresado, ~0,75 = canopeo muy denso. Hay que recalibrarlas con
# rendimientos reales antes de usar el score para decidir.
EVI_MAX_REF = (0.30, 0.75)     # evi_max medio del lote -> 0..1  (PROVISORIO)
# Peso del EVI en el componente de vigor (0 = solo NDVI como en v1.1, 1 = solo EVI). Si faltan campañas con EVI
# (menos de SCORE_MIN_CAMPANIAS_NDVI) el vigor cae a NDVI y el JSON lo dice (score.vigor_base).
VIGOR_PESO_EVI = 1.0
CV_REF = (0.02, 0.20)          # coef. de variación del ndvi_max entre campañas -> 1..0
AGUA_FRAC_REF = (0.0, 0.15)    # fracción máx. del lote anegada -> 1..0
AGUA_FREC_REF = (0.0, 25.0)    # frecuencia (%) de agua -> 1..0

# --- Render ---
RENDER_LADO_PX = 1000
NDVI_ESCALA = (0.0, 1.0)
NDMI_ESCALA = (-0.2, 0.6)

AVISO_EJEMPLO = "LOTE DE EJEMPLO – datos de ejemplo"

# --- Narrador ---
NARRADOR_MODELO_DEFAULT = "claude-sonnet-4-5"
