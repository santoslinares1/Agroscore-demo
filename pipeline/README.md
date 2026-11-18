# Pipeline AgroScore (Python 3.11+)

Genera, para cada lote de `data/lotes.geojson`, la carpeta `out/<id>/` con
`lote.json` (contrato en `agroscore/schema/lote.schema.json`), PNGs (NDVI, RGB,
zonas, gráfico por campaña), capas para el mapa web (`overlay_rgb/ndvi/ndmi/zonas.png`,
transparentes fuera del lote y alineadas con `imagenes.bbox`), `resumen.md` e
`informe.pdf`, más `out/index.json`.

## Instalación
```bash
cd pipeline
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt      # incluye earthengine-api, pytest y pypdf
# opcional, para leer GeoTIFF de IDECOR:  pip install rasterio
```

## Correr con datos REALES (tu cuenta de Google Earth Engine)
1. Tener un proyecto de Google Cloud con la API de Earth Engine habilitada y registrado para EE.
2. Autenticarse una vez: `earthengine authenticate`
3. Poner los polígonos reales en `data/lotes.geojson` (FeatureCollection, Polygon EPSG:4326,
   `properties: {id, nombre, localidad, fuente}`; `id` en minúsculas sin espacios).
   También acepta KML y KMZ de Google Earth (`python run_pipeline.py data/campos.kmz ...`): cada Polygon
   (también dentro de MultiGeometry) es un lote; el id sale del nombre (`lote_<nombre>`), la localidad queda
   «Sin especificar» y los huecos se ignoran. Se valida: cerrado, sin autointersección, 1–20.000 ha.
   Para probar: `data/ejemplo_carga.kml` (EJEMPLO).
4. (Recomendado) Bajar los mapas de cultivo de IDECOR a `data/cultivos/` (ver `data/cultivos/LEEME.md`).
5. Correr:
```bash
python run_pipeline.py data/lotes.geojson --gee-project TU_PROYECTO
# opciones: --desde 2019 --hasta 2025 --solo id1 id2 --idecor-asset 'projects/TU_PROYECTO/assets/idecor_{campania}'
#           --sin-mapbiomas --narrar (resumen con Claude, requiere ANTHROPIC_API_KEY)
```
La salida real lleva `"ejemplo": false`, así que el aviso de ejemplo desaparece solo en la web y el PDF.
Si los polígonos siguen siendo los de ejemplo, se agrega la advertencia "Polígono de ejemplo".

## Score v1.2.0: nubes, índices y agua
**Máscara de nubes.** Cloud Score+ (`GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`, banda `cs_cdf`, enlazada con
`linkCollection`) reemplaza al join con `COPERNICUS/S2_CLOUD_PROBABILITY`. Se conserva el píxel si
`cs_cdf >= S2_CS_UMBRAL` (0,6, en `config.py`) y la clase SCL es 4, 5 o 6 (se excluyen 3, 7, 8, 9, 10 y 11; antes 7 y 11
eran válidas). `S2_SR_HARMONIZED` ya resta el offset +1000 de las escenas posteriores al 25/01/2022: el código solo divide
por 10000. Se mantiene el filtro de escena `CLOUDY_PIXEL_PERCENTAGE < 60`.

**Índices** (por campaña igual que el NDVI, en `lote.json > campanias[]`): `evi_max/evi_medio` y `ndre_max/ndre_medio`,
más `obs_validas_px` (observaciones válidas medias por píxel). EVI = 2,5·(B8−B4)/(B8+6·B4−7,5·B2+1) con reflectancias 0–1
(se descarta lo que cae fuera de [−1, 1]). NDRE = (B8A−B5)/(B8A+B5): B8A y no B8 (par red-edge/NIR estándar, banda angosta);
B5 y B8A son de 20 m y GEE las remuestrea a 10 m (la información real es de 20 m). El NDVI sigue en la salida.

**Vigor.** `vigor_historico` usa EVI (`EVI_MAX_REF = (0.30, 0.75)`, `VIGOR_PESO_EVI = 1.0`; con peso < 1 se mezcla con NDVI).
⚠ Las referencias de EVI son **provisorias y no están calibradas** (no hay rendimientos de campo): se fijaron a priori como orden
de magnitud y hay que recalibrarlas. Sin EVI suficiente (< 3 campañas) el vigor cae a NDVI y `score.vigor_base` lo indica
(`evi` / `combinado` / `ndvi`). La estabilidad sigue calculándose sobre NDVI.

**Agua.** Un píxel cuenta como anegado solo si Sentinel-1 lo marca (VV filtrado < −18 dB) **y** lo confirma el óptico
(MNDWI > 0 en una escena S2 limpia dentro de ± `AGUA_VENTANA_OPTICA_DIAS` = 10 días) **o** figura como agua en
`JRC/GSW1_4/GlobalSurfaceWater` (`occurrence` ≥ `AGUA_JRC_OCURRENCIA_MIN_PCT` = 5 %). Sin óptico válido en la ventana (nubes) no
se confirma por el óptico (conservador: puede subestimar un anegamiento real bajo nubes persistentes). `agua` guarda también lo
que marcó solo el radar (`max_ha_s1_sin_confirmar`) para auditar el descarte. `JRC/GSW1_4/MonthlyHistory` termina en 2021-12 y
no se usa. Los umbrales siguen sin calibrar contra anegamientos reales. La consulta se hace por año (una sola consulta con todas
las escenas supera la memoria de GEE) y tarda ~1 min por lote.

**Verificación en vivo** (2026-11-18, solo lecturas): las expresiones EVI/NDRE/MNDWI de GEE coinciden con las funciones numpy
(`s2.evi`, `s2.ndre`) a precisión float32 sobre los píxeles de una escena real; control positivo del agua: en una caja sobre Mar
Chiquita (JRC apagado, solo óptico) se confirman 49,1 de 49,1 ha marcadas por S1 (promedio de 25 escenas de 2022).

## Servidor local (opcional) para «Analizar ahora» desde la web
```bash
earthengine authenticate
python server.py --gee-project TU_PROYECTO     # http://127.0.0.1:8787  (--port, --out, --destino)
```
| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/api/salud` | `{ok, gee_ok, verificando, gee_detalle}` (EE se verifica en segundo plano; `?refrescar=1` reintenta) |
| POST | `/api/lotes` `{feature}` | 202 + trabajo · 400 polígono inválido · 503 si Earth Engine no está listo (con `gee_detalle`) |
| GET | `/api/trabajos/<id>` | `{id, lote_id, estado: en_cola/procesando/listo/error, paso, progreso 0–1, error}` |

Corre los trabajos de a uno (`procesar_lote(..., progreso=cb)`), escribe en `out_servidor/` y publica con
`agroscore/publicar.py` en `web/public/demo` (nunca en `web/dist`; otro destino con `--destino`), agregando al `index.json`. No pisa ids existentes (409; `"reemplazar": true` para reemplazar y respaldar en `.publicacion/demo/versiones/`). Al arrancar repara publicaciones cortadas.
Sin autenticación: escucha en 127.0.0.1 y acepta CORS solo de `localhost`/`127.0.0.1`.

## Datos de EJEMPLO (sin cuenta de GEE)
```bash
python run_pipeline.py data/lotes.geojson --ejemplo
```
Usa `agroscore/ejemplo.py`: números SINTÉTICOS determinísticos, marcados `"ejemplo": true`,
con aviso "LOTE DE EJEMPLO – datos de ejemplo" en JSON, PNG, PDF y web. Nunca presentarlos como reales.

## Resumen con Claude (opcional)
```bash
export ANTHROPIC_API_KEY=...   # nunca commitear
export ANTHROPIC_MODEL=claude-sonnet-4-5   # opcional
python run_pipeline.py data/lotes.geojson --gee-project TU_PROYECTO --narrar
```
Se envía el JSON sin geometría + PNG de NDVI y zonas; el prompt obliga a usar solo los números del JSON.
Se cachea en `resumen.md` (la demo nunca llama a la API). Si falla, cae a la plantilla y lo advierte.
Revisar a mano los resúmenes antes de mostrarlos.

## Módulos
| Módulo | Qué hace |
|---|---|
| `config.py` | pesos del score, campañas oct–mar, umbrales, assets |
| `aoi.py` | carga GeoJSON/KML/KMZ, valida (cerrado, sin autointersección, 1–20.000 ha), área (ha) y centroide |
| `publicar.py` | publica lotes en la carpeta de la web sin borrar nada: no pisa ids (reemplazo explícito con respaldo en `.publicacion/<destino>/versiones/`, fuera de lo que se sirve), staging + validación + diario; resiste cortes (`recuperar()`): el `index.json` nunca lista un lote inexistente |
| `gee.py` | init de Earth Engine y descarga de rasters chicos (`computePixels`) |
| `s2.py` | Sentinel-2 SR harmonized, máscara Cloud Score+ (`cs_cdf` ≥ 0,6) + SCL 4/5/6, NDVI/NDMI/EVI/NDRE/MNDWI, stats por campaña, serie semanal |
| `landsat.py` | (opcional) NDVI Landsat 5–9 desde 2000, no entra al score v1 |
| `crops.py` | cultivo por campaña (IDECOR local/asset, MapBiomas respaldo), moda con umbral 60% -> "mixto", rotación con cobertura/confianza (sin dato ≠ sin maní) |
| `soil_climate.py` | SoilGrids (arcilla, arena, SOC 0–5 cm) + ERA5-Land (lluvia anual) |
| `zones.py` | k-means k=3 sobre NDVI máx. multianual -> Alta/Media/Baja |
| `water.py` | JRC Global Surface Water (frecuencia) + Sentinel-1 VV < −18 dB **confirmado por óptico (MNDWI) o JRC** (máx. ha anegadas) |
| `score.py` | ÚNICA implementación del score (normalización documentada en el docstring) |
| `render.py` | PNG 1000 px, escala fija NDVI 0–1, barra de colores, contorno, fecha |
| `report_pdf.py` | PDF de 4 páginas desde `lote.json` |
| `narrator.py` | resumen con Claude o plantilla |
| `pipeline.py` | orquestación + validación jsonschema + `index.json` |

## Tests
```bash
python -m pytest -q
```
Cubren AOI, cultivos/rotación, zonas, score, Cloud Score+/SCL, fórmulas EVI/NDRE, vigor con EVI y confirmación de agua (`test_v12_nubes_indices_agua.py`), contrato JSON (schema), score PDF == JSON,
marcado de ejemplo, nulls con advertencia y que no haya claves en el repo; KML/KMZ/autointersección
(`test_carga.py`) y el servidor local con Earth Engine simulado: 503 sin EE, 400 polígono inválido, CORS,
progreso, error del análisis informado tal cual y publicación sin borrar otros lotes (`test_server.py`).
Los mocks viven solo en `tests/`.
