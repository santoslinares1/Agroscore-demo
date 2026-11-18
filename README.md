# AgroScore · Demo maní (prototipo para Golden Peanut)

Prototipo mostrable e **independiente** de la landing (no toca `agro-score-web`).
Historia central: *"Antes de alquilar un campo, quiero saber en un minuto cómo rindió los últimos
años, si tuvo maní recientemente y qué riesgos tiene."*

Principio: **cálculo pesado en batch (Python + Earth Engine), la demo solo lee archivos estáticos**
y funciona sin internet.

> ⚠️ Los 3 lotes incluidos son **LOTES DE EJEMPLO – datos de ejemplo**: polígonos dibujados a mano sobre
> la imagen satelital pública de Esri cerca de Alejandro Roca / Río Cuarto (siguiendo bordes de potreros
> visibles, NO son lotes de clientes) y números sintéticos. La web y el PDF lo avisan en rojo. El aviso
> desaparece solo cuando los JSON vienen del pipeline real (`"ejemplo": false`).

## Estructura
```
agroscore-demo/
  pipeline/                 # paquete Python 3.11 `agroscore`
    agroscore/              # config, aoi, gee, s2, landsat, crops, soil_climate, zones, water,
                            # score, render, report_pdf, narrator, pipeline, proveedores, ejemplo
      schema/               # lote.schema.json + index.schema.json (contrato de datos)
    data/lotes.geojson      # lotes de entrada (hoy: 3 de EJEMPLO)
    data/ejemplo_carga.kml  # KML de EJEMPLO para probar «Cargar lote» (3 polígonos, uno en MultiGeometry)
    data/cultivos/          # GeoTIFF IDECOR por campaña (no incluidos)
    tests/                  # pytest (mocks solo acá)
    run_pipeline.py         # acepta GeoJSON, KML o KMZ
    server.py               # servidor LOCAL opcional para «Analizar ahora» (127.0.0.1:8787)
    requirements.txt / requirements-dev.txt
  web/                      # Vite + TypeScript + Leaflet + Chart.js (todo empaquetado, sin CDN)
    public/demo/            # index.json + <id>/{lote.json, png, pdf, resumen.md} (copiado del pipeline)
    src/                    # main.ts, mapa.ts, grafico.ts, views/{inicio,detalle,comparar,informe,como,cargar}.ts
      carga/                # geo.ts (leer KML/KMZ/GeoJSON, validar, área), almacen.ts (localStorage), backend.ts
    tests/                  # vitest (npm test)
  scripts/
    copiar_salidas.py/.sh   # pipeline/out -> web/public/demo (valida contra el schema)
    demo_ejemplo.sh         # regenera ejemplo + copia + build
```

## Setup
Requisitos: Python 3.11+, Node 18+ (probado con Node 24).
```bash
# Pipeline
cd pipeline
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q

# Web
cd ../web
npm install
npm test          # vitest: lectura KML/KMZ/GeoJSON, validación y área
```

## Comandos
```bash
# 1a) Datos de EJEMPLO (sin Earth Engine)
cd pipeline && python run_pipeline.py data/lotes.geojson --ejemplo && cd ..

# 1b) Datos REALES con tu cuenta de Earth Engine (ver pipeline/README.md)
earthengine authenticate
cd pipeline && python run_pipeline.py data/lotes.geojson --gee-project TU_PROYECTO [--narrar] && cd ..

# 2) Copiar salidas al front (NO destructivo: valida el schema en staging y recién ahí hace swap).
#    Si un id ya está publicado, falla (código 2) y no toca nada; opciones: --reemplazar-ids | --reemplazar-todo
#    (en ambos la versión anterior queda en .publicacion/demo/versiones/, fuera de lo que se sirve).
#    Detalle: sección «Publicación no destructiva».
./scripts/copiar_salidas.sh

# 3) Build y servir local (offline)
cd web && npm run build && npm run preview     # http://localhost:4173
#   verificación en navegador real del build: npm run test:navegador  (Chrome/Chromium headless; ver «Validación en la web»)
#   alternativa: npx http-server web/dist   o   python3 -m http.server -d web/dist 8080
#   Todo en uno (ejemplo): ./scripts/demo_ejemplo.sh
```
Nota: abrir `dist/index.html` con doble clic no funciona (el navegador bloquea leer JSON desde file://);
siempre servirlo con un servidor local. Para la reunión: llevar la notebook con el build y los PDF impresos.

## La demo
- **Mapa** (`#/`): imagen satelital real (Esri World Imagery) con los lotes coloreados por score y una
  etiqueta con el score. Al pasar el mouse por una tarjeta, el mapa vuela al lote.
- **Detalle** (`#/lote/<id>`):
  - mapa satelital encuadrado al lote, con contorno amarillo y halo oscuro, escala y selector de mapa base
    (Satélite / Topográfico Esri / Relieve OpenTopoMap / sin fondo + rótulos y rutas);
  - capas propias del lote sobre la imagen: NDVI, NDMI (humedad), zonas Alta/Media/Baja y color natural,
    con opacidad regulable y leyenda (`#/lote/<id>?capa=ndvi|ndmi|zonas|rgb` abre con esa capa);
  - score con desglose explicado en castellano llano, "Lectura rápida" (semáforo por componente),
    línea de tiempo de cultivos por campaña con el maní resaltado y "hace N campañas",
    gráfico NDVI, zonas, agua/suelo/clima, resumen, advertencias, PDF.
- **Comparar** (`#/comparar?ids=a,b,c`): 2–3 lotes en columnas con mini mapa satelital, mismo set de métricas y
  el mejor valor de cada fila resaltado.
- **Informe imprimible** (`#/informe/<id>`): vista tipo A4 con botón "Imprimir / guardar como PDF"
  (además del PDF generado por el pipeline).
- **Cómo funciona** (`#/como-funciona`): pasos, fuentes, componentes y pesos del score, límites, y qué
  significa que los datos sean de ejemplo.
- **Sin internet:** los mapas base necesitan conexión. Si no hay, el mapa muestra un aviso, fondo liso,
  el contorno del lote y prende sola la capa NDVI (PNG local). Todo lo demás funciona offline.
- **Cargar lote** (`#/cargar`): ver la sección siguiente.
- Mobile/tablet: diseño de una columna; el panel de capas se pliega.

## Cargar un lote
En `#/cargar` (menú «Cargar lote»):
1. **Subir** un KML o KMZ (Google Earth) o un GeoJSON. Se lee en el navegador (`@tmcw/togeojson` + `jszip`);
   si trae varios polígonos (varios Placemark, MultiGeometry o MultiPolygon) aparece una lista para elegir
   uno, varios o todos. Para probar: `pipeline/data/ejemplo_carga.kml` (EJEMPLO, no son lotes reales).
2. **O dibujarlo** sobre el satélite («Dibujar polígono», clic en cada esquina, cerrar en el primer punto) y
   ajustar con «Editar vértices» (Leaflet-Geoman). Un polígono subido también se puede editar.
3. **Validación en vivo:** se cierra solo si quedó abierto; rechaza bordes que se cruzan, menos de 3 vértices,
   coordenadas que no son lat/lon y áreas fuera de 1–20.000 ha; avisa si es < 5 ha, > 5.000 ha, tiene huecos
   o cae fuera de Argentina. Muestra el área en ha (turf) y encuadra el mapa al contorno.
4. **Datos:** nombre (obligatorio), propietario/establecimiento y notas de cultivo (opcionales).
5. **Guardar:** queda en `localStorage` de ese navegador y se lista como
   **«Lote cargado – pendiente de análisis»** (gris, rayado, sin score) en `#/cargar` y en el inicio.
   No se inventa ningún número: el score aparece recién cuando el pipeline lo procesa con datos reales.
6. **Analizar:**
   - **Sin servidor:** «Descargar GeoJSON para el pipeline» (o «GeoJSON» por lote) baja un archivo
     compatible con `pipeline/data/lotes.geojson`; la página muestra los comandos para copiar:
     ```bash
     cd pipeline
     python run_pipeline.py data/lotes_cargados.geojson --gee-project TU_PROYECTO --out out_cargados
     cd .. && python scripts/copiar_salidas.py --origen pipeline/out_cargados   # suma sin pisar (id repetido = error)
     ```
   - **Con el servidor local (opcional):**
     ```bash
     earthengine authenticate                                # una vez
     python pipeline/server.py --gee-project TU_PROYECTO     # http://127.0.0.1:8787
     ```
     La web lo detecta sola (`GET /api/salud`) y habilita «Analizar ahora»: `POST /api/lotes` valida el polígono
     y encola el análisis con Earth Engine; la web consulta `GET /api/trabajos/<id>` y muestra el avance.
     Al terminar, el servidor publica `lote.json` + capas en `web/public/demo` (o en `--destino`; **nunca** en
     `web/dist`, que es un artefacto de build), actualiza `index.json` sin borrar los demás lotes y la web muestra
     «Ver informe». Con `npm run dev` el lote aparece enseguida; para `npm run preview` o un build estático hay que
     volver a correr `npm run build`. Si el id ya está publicado responde **409** (no se encola el análisis) salvo que
     el cuerpo lleve `"reemplazar": true`; en ese caso la versión anterior se respalda en
     `.publicacion/demo/versiones/<id>/<fecha>/`. Al arrancar, el servidor repara cualquier publicación cortada.
     Si Earth Engine no está autenticado, el servidor responde 503 con el motivo y la web lo muestra tal cual
     y ofrece exportar. Si el análisis falla, el error se muestra en el lote; nunca se completa con datos falsos.
     El servidor escucha solo en 127.0.0.1, acepta CORS solo de localhost y no usa ni guarda claves.
   - Cuando hay lotes de ejemplo y lotes reales juntos, el aviso superior pasa a
     «Hay lotes de ejemplo (marcados EJEMPLO) junto a lotes analizados con datos reales».

## Publicación no destructiva (`pipeline/agroscore/publicar.py`, `scripts/copiar_salidas.py`, `server.py`)
- **No pisa:** si el id ya existe (carpeta o entrada en `index.json`) se rechaza (`IdExistenteError` / código 2 / HTTP 409).
- **Reemplazo explícito:** `--reemplazar-ids` (solo esos ids) o `--reemplazar-todo`; el servidor acepta `"reemplazar": true`.
  Aun así **nada se borra**: la versión anterior va a `<meta>/versiones/<id>/<AAAAmmdd-HHMMSS>/`, el `index.json`
  anterior a `versiones/_index/` y, con `--reemplazar-todo`, todo lo previo a `versiones/_completo/<fecha>/`.
- **Metadatos fuera de lo que se sirve** (`<meta>`): para `web/public/demo` es `<raíz>/.publicacion/demo/` (en `.gitignore`);
  para otro destino `<padre>/.publicacion-<nombre>/`, o `$AGROSCORE_PUBLICACION_DIR/<nombre>/` si esa variable está definida.
  Ahí van versiones, `publicar.lock`, staging y el diario de la operación: ni `npm run dev` ni `dist/` los sirven.
  Decisión (verificación 18/11, M2): antes `.versiones/` y `.publicar.lock` vivían dentro del destino y el servidor además
  publicaba en `web/dist/demo`, así que podían quedar servidos.
- **Validado, todo o nada y a prueba de cortes:** se arma en `<meta>/staging-*` (mismo filesystem), se valida cada `lote.json`
  copiado y el `index.json` final contra el schema; recién ahí se escribe un diario y se aplica en este orden: (1) `index.json`
  intermedio sin los ids que se reemplazan, (2) lote viejo → `versiones/`, lote nuevo → destino, (3) `index.json` final
  (escrituras con archivo temporal + `fsync` + rename atómico). Así **el `index.json` nunca lista un lote cuya carpeta no
  existe**, aunque el proceso muera en cualquier punto (kill -9, apagón). La próxima publicación, el servidor al arrancar o
  `python scripts/copiar_salidas.py --recuperar` leen el diario y completan o deshacen la operación, borran staging/temporales
  huérfanos, migran restos del formato viejo (`.versiones/`, `.staging-*`, `.index.*.tmp` dentro del destino) y reparan un
  `index.json` que liste lotes inexistentes (restaurando la última versión respaldada o, si no hay, quitando la entrada con el
  índice anterior respaldado). Tests: `pipeline/tests/test_publicacion_cortes.py` simula el corte antes de cada rename.
  Si no valida, el destino queda intacto y el script sale con código ≠ 0 (2 = id existente, 3 = no valida).
- `scripts/demo_ejemplo.sh` genera en una carpeta temporal y usa `--reemplazar-ids`: regenera los ejemplos sin tocar lotes reales.
- Defensa extra: el build saca de `dist/` cualquier archivo/carpeta oculto o temporal (`.*`, `*.tmp`, `*.lock`). No hay
  limpieza automática de `versiones/`: borrarla a mano cuando no haga falta.

## Validación en la web
La web valida `index.json` y cada `lote.json` contra **los mismos schemas del pipeline** (`pipeline/agroscore/schema/*.schema.json`):
`web/vite-plugin-validadores.ts` los compila con Ajv a código JS en el build (módulo `virtual:validadores`), sin duplicar los
schemas y sin llevar el compilador de Ajv al navegador. El código "standalone" de Ajv trae `require(...)` para sus funciones de
runtime (`ucs2length`, formatos de `ajv-formats`), que en el navegador no existe: el plugin lo empaqueta con esbuild como ESM puro
y el build falla si queda algún `require(` (test: `web/tests/validadores.test.ts`). Los lotes se cargan con `Promise.allSettled`: uno roto o que no carga se
muestra como «Este lote no se pudo cargar: <motivo>» y el resto sigue; si falla el índice, pantalla de error con el motivo y «Reintentar».

Verificación en navegador real: `cd web && npm run build && npm run test:navegador` (`web/scripts/smoke-navegador.mjs`, usa
`playwright-core` con el Chrome/Chromium del sistema: `CHROME_PATH` o `/usr/bin/google-chrome`). Sirve `dist/` por HTTP sin
internet y comprueba: sin errores de consola, todas las tarjetas del index y las vistas principales; un `lote.json` con JSON
inválido y otro fuera de schema muestran tarjeta de error y el resto carga; sin `index.json`, pantalla de error con «Reintentar».

## Score v1.2.0 (una sola implementación: `pipeline/agroscore/score.py`)
Score = 100 × Σ peso × componente (0–1). Pesos: vigor histórico 0,35 · estabilidad 0,20 · riesgo hídrico 0,20 ·
suelo 0,15 · rotación de maní 0,10. La normalización de cada componente está documentada en el docstring.

**Índice del vigor (`score.vigor_base`, obligatorio en el schema)**: en 1.2.0 el vigor usa EVI si hay ≥ 3 campañas con EVI
(`evi`, o `combinado` si `VIGOR_PESO_EVI` < 1) y NDVI si no (`ndvi`; p. ej. los datos de ejemplo, que no traen EVI). La versión
sola no alcanza para saber cuál se usó, así que web, PDF y narrador rotulan «Vigor histórico (EVI | EVI + NDVI | NDVI)» y
explican el método según ese campo de cada lote; «Cómo funciona» describe lo que usan los lotes que se muestran. NaN/inf en
los índices, agua o suelo cuentan como faltantes; con NDVI medio ≤ 0 la estabilidad queda `null` (no hay score).
La web y el PDF leen el mismo `lote.json` (hay un test que extrae el score del PDF y lo compara).

**Rotación de maní (v1.1.0)** — criterio agronómico: carbón del maní (*Thecaphora frezii*); INTA recomienda más de
3 años sin maní, o sea ≥ 4 campañas (`ROTACION_ANIOS_RECOMENDADOS`; las teliosporas pueden persistir 4–6 años,
supuesto conservador). Reglas:
- Cada campaña es `mani`, `no_mani` o `sin_dato`. **Sin dato** = `None` o clase genérica donde el maní no se puede
  separar (`CULTIVOS_MANI_INDETERMINADO`: `otros_posible_mani`, `agricultura`, `cultivo_temporario`,
  `mosaico_agropecuario`, `mixto`). Una campaña sin dato **nunca** cuenta como «sin maní».
- Valor = `min(1, campañas_sin_maní_confirmadas / 4)`, donde la racha confirmada se corta en la primera campaña
  con maní *o sin dato* (cuenta desde la más reciente). Con racha ≥ 4 vale 1,0 **sin más penalización**.
  Si la racha es menor, se descuenta 15 % por cada maní *anterior* al último (`ROTACION_PENALIZ_REPETICION`);
  ya no hay doble castigo a un lote que respetó el intervalo.
- Cobertura = campañas con dato / campañas de la ventana (5). Con < 3 con dato (`ROTACION_MIN_CAMPANIAS_CON_DATO`)
  el componente es `null`, se redistribuye su peso entre los demás y se agrega advertencia (nunca 1,0 optimista).
  Con 3–4 con dato (o ventana incompleta) se calcula, de forma conservadora, y se advierte.
- `score.confianza`: `alta` = todos los componentes con dato (100 % del peso), rotación completa **y** al menos 2/3 de las
  campañas con NDVI válido (6 de 9; `CONFIANZA_ALTA_FRAC_CAMPANIAS`); `baja` = rotación insuficiente, ≥ 2 componentes
  faltantes o menos de la mitad de las campañas con NDVI (`CONFIANZA_BAJA_FRAC_CAMPANIAS`); `media` = el resto.
  `score.campanias_con_ndvi` / `score.campanias_total` dejan la cobertura explícita. No cambia el valor del score.
  `rotacion.confianza_rotacion` = completa / parcial / insuficiente.

**Datos mínimos y reponderación (v1.2.0)** — el score nunca se completa con datos que no hay:
- **Score total `null` ("Sin dato suficiente")** si falta cualquiera de los dos componentes obligatorios (`vigor_historico`
  y `estabilidad`: cada uno exige ≥ 3 campañas con `ndvi_max`, `SCORE_MIN_CAMPANIAS_NDVI`) o si los componentes con dato
  suman menos del 70 % del peso (`SCORE_COBERTURA_MIN`). Antes, un lote con solo suelo daba 100/100.
  El motivo legible queda en `score.motivo_sin_score`; `confianza` y `componentes_usados` quedan vacíos.
- Un componente sin dato queda `null` en `componentes[]`. Si igual hay score (≥ 70 % del peso), la reponderación es
  **explícita**: `reponderado: true`, `cobertura`, `componentes_usados`, `componentes_sin_dato` y `peso_efectivo` por
  componente (= peso / cobertura), más una advertencia «Score parcial». Web y PDF lo muestran como *score parcial*.
- Rotación: `ROTACION_EXIGE_DATO_COMPLETO = False` (default) mantiene la regla graduada de v1.1.0 (≥ 3 de 5 campañas con
  dato). En `True`, basta una campaña sin dato en la ventana para que `rotacion_mani` sea `null` (modo estricto).
- Los consumidores (narrador, PDF, `publicar`, web) muestran «Sin dato suficiente» en vez de un número cuando `valor` es `null`.

Lotes de ejemplo actuales (regenerados el 18/11 con el proveedor de ejemplo: mismos scores; vigor con NDVI, 9/9 campañas con NDVI):
| Lote (EJEMPLO) | ha | Score | Historia sintética |
|---|---|---|---|
| ejemplo_roca_norte | 55,5 | 83 | último maní 2020/21 |
| ejemplo_rio_cuarto_este | 52,9 | 81 | último maní 2018/19, una campaña "mixto" (cuenta como sin dato: rotación 0,75, confianza media; con v1.0.0 daba 83) |
| ejemplo_roca_sur | 41,3 | 55 | maní en 2025/26 (3 de las últimas 5) y bajo anegable (sintético) |

## Checklist de aceptación (sección 7)
- [x] `index.json` y cada `lote.json` validan contra el schema (en el pipeline, en `copiar_salidas` y en tests).
- [x] Score web == score PDF en todos los lotes (test `test_score_pdf_igual_json`).
- [x] Cada campaña tiene cultivo o `null` con advertencia; maní resaltado (web y PDF).
- [x] Ninguna cifra en la UI que no venga del JSON (la UI solo formatea; "aporte" = valor × peso × 100).
- [x] El build (`dist/`) servido por HTTP arranca y renderiza los lotes en Chrome headless sin internet y sin errores de
      consola (`npm run test:navegador`, 18/11). JS principal ~453 kB (~132 kB gzip); «Cargar lote» es un chunk aparte de
      ~420 kB que se baja solo al abrirla. El tiempo de carga (< 2 s) **no** se midió en esta verificación.
- [x] Imágenes con leyenda, fecha y contorno (PNG del pipeline y capas del mapa con leyenda y escala).
- [x] Sin claves ni tokens en el repo (test `test_sin_claves_en_el_proyecto`; `ANTHROPIC_API_KEY` solo por entorno).
- [x] README con cómo regenerar (`python run_pipeline.py data/lotes.geojson`).
- [ ] **Pendiente con datos reales:** correr con Earth Engine sobre polígonos reales y comparar "Campo 1"
      (Río Cuarto, 144 ha) contra el PDF existente (88/100); documentar diferencias.

## Supuestos y pendientes
1. **Cultivo por campaña (crítico para maní).** Tres fuentes en orden: GeoTIFF de IDECOR locales
   (`data/cultivos/idecor_AAAA-AA.tif`, requiere `rasterio`), IDECOR como asset de EE (`--idecor-asset`) y
   MapBiomas Argentina de respaldo. Los códigos de IDECOR se verificaron contra los servicios OGC oficiales y
   están **por campaña** en `IDECOR_CLASES_POR_CAMPANIA` (los códigos cambian entre ediciones): maní separable solo
   en 2017/18 (clase 18) y 2023/24 en adelante (clase 4); 2022/23 no separa maní; 2018/19–2020/21 sin mapa
   utilizable (sin código verificado → `None`, no se inventa). Pendiente: licencia IDECOR (CC BY-SA 4.0;
   revisar la implicancia de ShareAlike para derivados comerciales). **MapBiomas Argentina no tiene clase maní**:
   su fallback devuelve clases genéricas (`agricultura`, `cultivo_temporario`, `pastura`…) y un «maní» de una fuente que no
   lo distingue se degrada a `agricultura`; ambas cuentan como **sin dato para maní**, jamás como «sin maní».
   El asset por defecto es la Colección 3 (`MAPBIOMAS_ASSET`), **verificado en GEE real** (2026-11-17): existe,
   bandas `classification_1985…2025`; el raster trae las clases 3, 4, 6, 63, 66, 77, 11, 12, 73, 34, 9, 15, 19, 21, 24,
   36, 25, 33, 27 (la agricultura sale como 19 «Cultivos temporarios»; el 18 no aparece). Los errores de GEE al consultar se loguean (logger `agroscore`,
   WARNING) y esa campaña queda sin dato; no se silencian. Mapas INTA: no implementados.
2. **Polígonos reales:** faltan. Los 3 lotes son de ejemplo; cargarlos en `#/cargar`, reemplazar
   `data/lotes.geojson` o pasar un KML/KMZ.
2b. **Lotes cargados:** viven en el `localStorage` del navegador (no se sincronizan entre equipos; borrar
   datos del sitio los borra). «Analizar ahora» con Earth Engine real **no se probó acá** (sin cuenta): se probó
   el flujo completo con un ejecutor simulado y el caso real «EE no autenticado» (503 + mensaje).
3. **Código de Earth Engine:** primera corrida real (2026-11-17) sobre los 3 lotes de ejemplo, 2017/18–2025/26, ~2 min
   (S2 SR harmonized + s2cloudless, JRC GSW, Sentinel-1, SoilGrids, ERA5-Land, MapBiomas Col. 3). Bugs corregidos:
   fuera del polígono salía NDVI 0 (zonas, `gee.a_numpy`), escenas S1 de borde de swath (VV −50 a −90 dB) contadas como
   «100 % anegado» (`water.py`). **Sin resolver:** el umbral fijo VV < −18 dB marca suelo desnudo liso en sequía como
   agua (el riesgo hídrico es solo un indicio); Sentinel-2 SR está incompleto antes de dic-2018 (2017/18 ≈ 13 de ~30
   escenas, `pct_nubes` subestimado; hay advertencia). IDECOR no está como asset EE ni local: la corrida cae a MapBiomas
   (sin dato de maní) y la rotación queda `null`.
4. **Score v1.2.0:** pesos y rangos de normalización son una propuesta razonable, no calibrada con rindes.
   El componente de rotación de maní está pensado para un manisero que alquila (maní reciente = peor).
5. **Narrador Claude:** implementado vía HTTP (Messages API); modelo por `ANTHROPIC_MODEL`
   (default `claude-sonnet-4-5`, verificar nombre vigente). Los resúmenes incluidos son de plantilla.
6. **Mapas base:** Esri World Imagery / World Topo y OpenTopoMap se usan con su atribución, para una demo.
   Para un producto comercial con tráfico conviene revisar los términos de uso de Esri (cuenta ArcGIS /
   clave de API) o pasar a otro proveedor de imágenes. Las capas propias (NDVI, NDMI, zonas) son PNG locales.
7. **Fuera de alcance:** login, pagos, granizo, Kc/ETc, backend en la nube (el servidor de análisis es solo local).
8. Este proyecto es independiente: si más adelante se quiere una ruta `/demo` en la landing, se puede
   portar el front, pero **no se tocó** `agro-score-web`.
