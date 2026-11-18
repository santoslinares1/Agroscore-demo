"""Resumen en castellano del lote.

- `resumen_claude`: usa la API de Claude (Anthropic Messages API) si hay
  ANTHROPIC_API_KEY en el entorno. Se corre en batch y se cachea en resumen.md;
  la demo NUNCA llama a la API.
- `resumen_plantilla`: texto determinístico armado solo con números del JSON
  (fallback sin red / sin clave).
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path

from . import config
from .score import etiqueta_componente

PROMPT = (
    "Sos agrónomo. Escribí 120–180 palabras en castellano rioplatense para una empresa manisera que "
    "evalúa alquilar este lote. Usá SOLO los números del JSON; no estimes valores mirando la imagen. "
    "Mencioná rotación de maní, estabilidad, riesgo hídrico y zonas. El índice del vigor del score está en "
    "score.vigor_base (\"evi\" o \"combinado\": EVI con referencias provisorias sin calibrar; \"ndvi\": NDVI); nombrá "
    "ese índice y no otro. El agua anegada es la confirmada con imagen óptica (agua.max_ha_s1_sin_confirmar "
    "es lo que marcó solo el radar): aclaralo si es relevante. Si un dato es null, decí que no "
    "hay dato. Si score.valor es null no inventes ni estimes un puntaje: decí que no hay dato suficiente "
    "para un score y explicá el motivo (score.motivo_sin_score). Si score.reponderado es true, aclará que es "
    "un score parcial (score.cobertura) y qué componentes faltan. No uses títulos; devolvé uno o dos párrafos "
    "en Markdown simple."
)
API_URL = "https://api.anthropic.com/v1/messages"


def _lote_sin_geometria(lote: dict) -> dict:
    return {k: v for k, v in lote.items() if k not in ("geometry", "imagenes", "pdf", "resumen_md")}


def resumen_claude(lote: dict, carpeta: Path, modelo: str | None = None, timeout: int = 60) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno")
    modelo = modelo or os.environ.get("ANTHROPIC_MODEL", config.NARRADOR_MODELO_DEFAULT)
    contenido: list[dict] = []
    for png in (lote["imagenes"]["ndvi_ultima"], lote["zonas"]["png"]):
        data = base64.standard_b64encode((Path(carpeta) / png).read_bytes()).decode()
        contenido.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}})
    contenido.append({"type": "text", "text": PROMPT + "\n\nJSON del lote:\n" +
                      json.dumps(_lote_sin_geometria(lote), ensure_ascii=False, indent=1)})
    body = json.dumps({"model": modelo, "max_tokens": 600,
                       "messages": [{"role": "user", "content": contenido}]}).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    texto = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text").strip()
    return texto + f"\n\n_Resumen generado con Claude ({modelo}) a partir del JSON; revisado: pendiente._\n"


def _n(v, dec=2):
    return "sin dato" if v is None else (f"{v:.{dec}f}".replace(".", ",") if isinstance(v, float) else str(v))


def resumen_plantilla(lote: dict) -> str:
    s = lote["score"]
    comp = {c["clave"]: c["valor"] for c in s["componentes"]}
    r, z, a = lote["rotacion"], lote["zonas"], lote["agua"]
    ndvis = [c["ndvi_max"] for c in lote["campanias"] if c["ndvi_max"] is not None]
    evis = [c["evi_max"] for c in lote["campanias"] if c.get("evi_max") is not None]
    if r.get("confianza_rotacion") == "insuficiente":
        rot = (f"Solo hay dato de maní en {r.get('campanias_con_dato_ultimas_5', 0)} de las últimas "
               f"{r.get('campanias_ventana', 5)} campañas: no alcanza para evaluar la rotación (riesgo de carbón sin determinar).")
    elif comp.get("rotacion_mani") is None:
        rot = (f"Hay dato de maní en {r.get('campanias_con_dato_ultimas_5', '?')} de las últimas "
               f"{r.get('campanias_ventana', 5)} campañas: no se evaluó la rotación (riesgo de carbón sin determinar).")
    elif r["ultimo_mani"] is None:
        rot = "No hay maní registrado en las campañas con dato, algo favorable frente al carbón."
        if r.get("confianza_rotacion") == "parcial":
            rot += (f" Ojo: hay dato de maní en {r['campanias_con_dato_ultimas_5']} de las últimas "
                    f"{r['campanias_ventana']} campañas.")
    elif r["campanias_desde_mani"] == 0:
        rot = (f"La última campaña ({r['ultimo_mani']}) fue maní y lleva {r['veces_mani_ultimas_5']} maníes en "
               "las últimas 5: alquilarlo para maní ya implica riesgo alto de carbón.")
    else:
        rot = (f"El último maní fue en {r['ultimo_mani']} (hace {r['campanias_desde_mani']} campañas) y tuvo "
               f"{r['veces_mani_ultimas_5']} maníes en las últimas 5 campañas.")
    partes = []
    if lote.get("ejemplo"):
        partes.append(f"**{config.AVISO_EJEMPLO}.** Texto armado por plantilla sobre números sintéticos.")
    if s["valor"] is None:
        score_txt = (f"**no tiene score: sin dato suficiente.** {s.get('motivo_sin_score') or ''}".strip())
    else:
        score_txt = f"obtiene un score de **{_n(s['valor'])}/100**"
        if s.get("reponderado"):
            sin = ", ".join(etiqueta_componente(c["clave"], s.get("vigor_base")) for c in s["componentes"] if c["valor"] is None)
            score_txt += (f" (score parcial: calculado sobre el {round(100 * s.get('cobertura', 1))} % del peso; "
                          f"sin dato: {sin})")
    partes.append(
        f"**{lote['nombre']}** ({_n(lote['area_ha'], 1)} ha, {lote['localidad']}) {score_txt}. "
        f"El NDVI máximo por campaña va de {_n(min(ndvis) if ndvis else None)} a "
        f"{_n(max(ndvis) if ndvis else None)}"
        + (f" y el EVI máximo de {_n(min(evis))} a {_n(max(evis))} (el vigor del score usa EVI con referencias provisorias, "
           "sin calibrar)" if evis and s.get("vigor_base") in ("evi", "combinado")
           else " (el vigor del score usa NDVI)" if s.get("vigor_base") == "ndvi" else "")
        + f", con estabilidad {_n(comp.get('estabilidad'))} sobre 1. {rot}"
    )
    if a.get("max_ha_s1_sin_confirmar") is not None and a["max_ha_s1_sin_confirmar"] != a["max_ha_anegadas"]:
        extra_agua = (f" El radar Sentinel-1 solo había marcado hasta {_n(a['max_ha_s1_sin_confirmar'], 1)} ha; "
                      "se cuentan únicamente las confirmadas con imagen óptica o registro JRC.")
    else:
        extra_agua = ""
    partes.append(
        f"En riesgo hídrico, el máximo anegado detectado fue {_n(a['max_ha_anegadas'], 1)} ha "
        f"({a['fecha_max'] or 'sin fecha'}) y la frecuencia histórica de agua es {_n(a['frecuencia_pct'], 1)} %.{extra_agua} "
        f"Dentro del lote, {_n(z['alta_pct'])}% es zona alta, {_n(z['media_pct'])}% media y "
        f"{_n(z['baja_pct'])}% baja: conviene recorrer la zona baja antes de cerrar el alquiler."
    )
    return "\n\n".join(partes) + "\n"
