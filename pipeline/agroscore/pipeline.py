"""Orquestación: lote -> artefactos (lote.json, PNGs, resumen.md, informe.pdf)."""
from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema

from . import config, crops, narrator, render, report_pdf, score, zones

log = logging.getLogger("agroscore")
SCHEMA_DIR = Path(__file__).parent / "schema"
TZ_AR = timezone(timedelta(hours=-3))


def cargar_schema(nombre: str) -> dict:
    return json.loads((SCHEMA_DIR / nombre).read_text(encoding="utf-8"))


def validar(obj: dict, schema: str) -> None:
    jsonschema.validate(obj, cargar_schema(schema), format_checker=jsonschema.FormatChecker())


def procesar_lote(lote, proveedor, out_dir: Path, campanias: list[str] | None = None,
                  narrar: bool = False, ahora: datetime | None = None, progreso=None) -> dict:
    """Procesa un lote. `progreso(fraccion, texto)` (opcional) recibe el avance para el servidor local."""
    avisar = progreso or (lambda f, t: None)
    campanias = campanias or config.campanias()
    carpeta = Path(out_dir) / lote.id
    carpeta.mkdir(parents=True, exist_ok=True)
    adv: list[str] = []
    ejemplo = bool(proveedor.ejemplo)
    if ejemplo:
        adv.append(f"{config.AVISO_EJEMPLO}: polígono y números sintéticos generados por código.")
    elif "EJEMPLO" in (lote.fuente or "").upper():
        adv.append("Polígono de ejemplo (no es un lote real): datos satelitales reales de un área ficticia.")

    avisar(0.05, f"Sentinel-2: NDVI/NDMI de {len(campanias)} campañas")
    stats = proveedor.stats_campanias(lote, campanias)
    avisar(0.35, "Cultivos por campaña (rotación)")
    cult, adv_c = proveedor.cultivos(lote, campanias)
    adv += adv_c
    ndvis = [stats[c]["ndvi_max"] for c in campanias if stats[c]["ndvi_max"] is not None]
    media = statistics.fmean(ndvis) if ndvis else None
    camp_list = []
    for c in campanias:
        st = stats[c]
        if st["ndvi_max"] is None:
            adv.append(f"Campaña {c}: sin imágenes Sentinel-2 válidas.")
        if st.get("pct_nubes") is not None and st["pct_nubes"] > config.NUBES_ADVERTENCIA_PCT:
            adv.append(f"Campaña {c}: {st['pct_nubes']}% de observaciones con nubes.")
        if not ejemplo and st["ndvi_max"] is not None and st.get("n_escenas") is not None and st["n_escenas"] < config.S2_MIN_ESCENAS:
            extra = (" Sentinel-2 SR (L2A) está incompleto antes de dic-2018 (solo escenas sueltas): pct_nubes "
                     "queda subestimado por sesgo a escenas limpias." if config.campania_fechas(c)[0] < config.S2_L2A_COMPLETO_DESDE else "")
            adv.append(f"Campaña {c}: solo {st['n_escenas']} escenas Sentinel-2 válidas (mínimo esperado {config.S2_MIN_ESCENAS}).{extra}")
        if (st.get("hueco_max_semanas") or 0) > config.MAX_HUECO_SEMANAS:
            adv.append(f"Campaña {c}: {st['hueco_max_semanas']} semanas seguidas sin imagen válida (no se interpoló).")
        camp_list.append({
            "campania": c,
            "cultivo": cult[c]["cultivo"],
            "cultivo_fuente": cult[c]["cultivo_fuente"],
            "cultivo_cobertura": cult[c]["cultivo_cobertura"],
            "ndvi_max": st["ndvi_max"],
            "ndvi_medio": st["ndvi_medio"],
            "ndvi_anomalia": None if st["ndvi_max"] is None or media is None else round(st["ndvi_max"] - media, 3),
            "ndmi_medio": st["ndmi_medio"],
            "evi_max": st.get("evi_max"),
            "evi_medio": st.get("evi_medio"),
            "ndre_max": st.get("ndre_max"),
            "ndre_medio": st.get("ndre_medio"),
            "obs_validas_px": st.get("obs_validas_px"),
            "pct_nubes": st["pct_nubes"],
            "n_escenas": st.get("n_escenas"),
            "hueco_max_semanas": st.get("hueco_max_semanas"),
        })
    rot = crops.derivar_rotacion(camp_list)
    rot["anios_recomendados"] = config.ROTACION_ANIOS_RECOMENDADOS

    # Zonas y renders
    avisar(0.5, "Zonas de manejo (NDVI multianual)")
    multi, bbox_m = proveedor.ndvi_multianual(lote, campanias)
    z = zones.zonificar(multi)
    ultima = campanias[-1]
    avisar(0.62, "Imagen más reciente y capas del mapa")
    ndvi_u, rgb_u, bbox_u, fecha_rgb = proveedor.ultima(lote, ultima)
    periodo = f"{campanias[0]}–{ultima}"
    pcts = {k: z[k] for k in ("alta_pct", "media_pct", "baja_pct")}
    anio_img = ultima.split("/")[0]
    f_ndvi, f_rgb = f"ndvi_{anio_img}.png", f"rgb_{anio_img}.png"
    render.render_ndvi(ndvi_u, bbox_u, lote.anillo, f"máximo campaña {ultima}", lote.nombre, carpeta / f_ndvi, ejemplo)
    render.render_rgb(rgb_u, bbox_u, lote.anillo, fecha_rgb, lote.nombre, carpeta / f_rgb, ejemplo)
    if z["alta_pct"] is not None:
        render.render_zonas(z["mapa"], bbox_m, lote.anillo, pcts, periodo, lote.nombre, carpeta / "zonas.png", ejemplo)
    else:
        adv.append("Zonas: no hay suficientes píxeles válidos para zonificar.")
    render.overlay_rgb(rgb_u, carpeta / "overlay_rgb.png")
    render.overlay_indice(ndvi_u, config.NDVI_ESCALA, carpeta / "overlay_ndvi.png")
    ndmi_u, _ = proveedor.ndmi(lote, ultima)
    render.overlay_indice(ndmi_u, config.NDMI_ESCALA, carpeta / "overlay_ndmi.png", cmap="BrBG")
    if z["alta_pct"] is not None:
        render.overlay_zonas(z["mapa"], carpeta / "overlay_zonas.png")

    avisar(0.8, "Suelo (SoilGrids), clima (ERA5) y agua (JRC, Sentinel-1)")
    suelo, clima, agua = proveedor.suelo(lote), proveedor.clima(lote), proveedor.agua(lote)
    if agua.get("max_ha_anegadas") is not None and lote.area_ha and agua["max_ha_anegadas"] >= 0.5 * lote.area_ha:
        adv.append(f"Agua: {agua['max_ha_anegadas']} de {lote.area_ha} ha anegadas (confirmadas) el {agua['fecha_max']}; "
                   "revisar a mano antes de confiar: los umbrales no están calibrados contra anegamientos reales.")
    if agua.get("max_ha_s1_sin_confirmar") is not None and agua.get("max_ha_anegadas") is not None \
            and agua["max_ha_s1_sin_confirmar"] > agua["max_ha_anegadas"]:
        adv.append(f"Agua: Sentinel-1 marcó hasta {agua['max_ha_s1_sin_confirmar']} ha "
                   f"({agua['fecha_max_s1_sin_confirmar']}) pero solo {agua['max_ha_anegadas']} ha se confirmaron con "
                   f"óptico (MNDWI) o JRC; el resto se descartó como probable suelo desnudo liso. "
                   "Bajo nubes persistentes no hay confirmación óptica: puede subestimar un anegamiento real.")
    if agua.get("n_escenas_s1_marcadas"):
        adv.append(f"Agua: de {agua['n_escenas_s1_marcadas']} escenas Sentinel-1 con >= {round(100 * config.AGUA_ESCENA_MARCADA_FRAC)} % "
                   f"del lote como agua, {agua.get('n_escenas_s1_marcadas_sin_optico', 0)} no se pudieron contrastar con óptico "
                   f"(óptico válido en < {round(100 * config.AGUA_OPTICO_COBERTURA_MIN)} % del lote) y {agua.get('n_escenas_s1_confirmadas', 0)} "
                   "escenas tuvieron anegamiento confirmado. Sin anegamiento confirmado = sin evidencia, no evidencia de ausencia.")
    ahora = ahora or datetime.now(TZ_AR)
    doc = {
        "id": lote.id, "nombre": lote.nombre, "localidad": lote.localidad,
        "fuente_poligono": lote.fuente, "area_ha": lote.area_ha, "centroide": lote.centroide,
        "geometry": lote.geometry,
        "score": None,
        "campanias": camp_list, "rotacion": rot,
        "zonas": {**pcts, "png": "zonas.png", "centros_ndvi": z["centros"]},
        "agua": agua, "suelo": suelo, "clima": clima,
        "imagenes": {"ndvi_ultima": f_ndvi, "rgb_ultima": f_rgb, "overlay_rgb": "overlay_rgb.png",
                     "overlay_ndvi": "overlay_ndvi.png", "overlay_ndmi": "overlay_ndmi.png",
                     "overlay_zonas": "overlay_zonas.png" if z["alta_pct"] is not None else None,
                     "campania_overlays": ultima,
                     "escalas": {"ndvi": list(config.NDVI_ESCALA), "ndmi": list(config.NDMI_ESCALA)},
                     "ndvi_campanias": "ndvi_campanias.png", "fecha_rgb": fecha_rgb,
                     "bbox": [round(b, 6) for b in bbox_u]},
        "resumen_md": "resumen.md", "resumen_fuente": "plantilla", "pdf": "informe.pdf",
        "generado": ahora.isoformat(timespec="seconds"),
        "advertencias": adv, "ejemplo": ejemplo, "fuente_datos": proveedor.nombre,
    }
    doc["score"], adv_s = score.calcular(doc)
    adv += adv_s

    resumen = None
    if narrar:
        try:
            resumen = narrator.resumen_claude(doc, carpeta)
            doc["resumen_fuente"] = "claude"
        except Exception as exc:  # sin red / sin clave: fallback
            log.warning("Narrador Claude no disponible (%s); uso plantilla", exc)
            adv.append("Resumen: generado por plantilla (Claude no disponible).")
    if resumen is None:
        resumen = narrator.resumen_plantilla(doc)
    (carpeta / "resumen.md").write_text(resumen, encoding="utf-8")

    avisar(0.93, "Informe PDF")
    validar(doc, "lote.schema.json")
    report_pdf.generar(doc, carpeta, resumen)
    (carpeta / "lote.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("%s: score %s", lote.id, doc["score"]["valor"] if doc["score"]["valor"] is not None else "sin dato suficiente")
    avisar(1.0, "Listo")
    return doc


def escribir_index(docs: list[dict], out_dir: Path) -> dict:
    idx = {
        "generado": datetime.now(TZ_AR).isoformat(timespec="seconds"),
        "score_version": config.SCORE_VERSION,
        "ejemplo": any(d["ejemplo"] for d in docs),
        "lotes": [{"id": d["id"], "nombre": d["nombre"], "localidad": d["localidad"], "area_ha": d["area_ha"],
                   "score": d["score"]["valor"], "centroide": d["centroide"], "geometry": d["geometry"],
                   "ejemplo": d["ejemplo"]} for d in docs],
    }
    validar(idx, "index.schema.json")
    Path(out_dir, "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    return idx
