"""ÚNICA implementación del score AgroScore (versión en config.SCORE_VERSION).

Score = round(100 × Σ peso_i × componente_i), componentes normalizados 0–1:

- vigor_historico (v1.2.0): el NDVI se satura con canopeo cerrado (0.94–0.95), así que el vigor usa EVI:
  media de `evi_max` de las campañas con dato, lineal entre EVI_MAX_REF (0.30 -> 0, 0.75 -> 1). Con
  VIGOR_PESO_EVI < 1 se mezcla con el valor equivalente de NDVI (NDVI_MAX_REF 0.55 -> 0, 0.90 -> 1):
  vigor = w·vigor_EVI + (1 − w)·vigor_NDVI. Si hay menos de SCORE_MIN_CAMPANIAS_NDVI campañas con `evi_max`
  (p. ej. JSON viejo o datos de ejemplo) el vigor cae a NDVI y `score.vigor_base` = "ndvi". Las referencias
  de EVI son PROVISORIAS (sin calibrar contra rendimientos; ver config.py).
- estabilidad: 1 − normalización del coeficiente de variación de `ndvi_max`
  entre campañas en CV_REF (CV 0.02 -> 1, CV 0.20 -> 0).
- riesgo_hidrico: 1 − (0.6 × fracción máx. anegada normalizada en AGUA_FRAC_REF
  + 0.4 × frecuencia normalizada en AGUA_FREC_REF). 1 = sin riesgo.
- suelo: media de (a) arena dentro de SUELO_ARENA_OPTIMA (1) con caída lineal
  de 20 puntos fuera, (b) arcilla ≤ SUELO_ARCILLA_MAX (1) con caída lineal de
  20 puntos, (c) carbono orgánico / SUELO_CO_OPTIMO (tope 1).
- rotacion_mani (para un manisero que alquila: el lote ideal NO tuvo maní recientemente,
  riesgo de carbón, Thecaphora frezii). Se calcula SOLO sobre campañas con dato de maní
  (cultivo conocido y no indeterminado; None o "agricultura"/"mixto"/... = faltante, NUNCA
  "sin maní"):
  * gap = campañas consecutivas con dato y sin maní hasta la última campaña
    (`campanias_sin_mani_confirmadas`); una campaña sin dato corta la racha (se asume que
    podría haber sido maní).
  * valor = min(1, gap / ROTACION_ANIOS_RECOMENDADOS). Con 4 campañas sin maní (">3 años",
    INTA) el valor es 1.0: cumplir exactamente el intervalo NO se castiga.
  * si todavía no se cumplió el intervalo (gap < recomendadas) se multiplica por
    max(0, 1 − 0.15 × maníes previos al último dentro de la ventana): el inóculo se acumula
    con la frecuencia. Con el intervalo cumplido no hay penalización extra (antes se
    contaba dos veces el mismo maní).
  * cobertura: campañas con dato / ventana (5). Con menos de ROTACION_MIN_CAMPANIAS_CON_DATO
    (3) con dato el componente queda en null (se excluye y se renormalizan los pesos) y se
    advierte. Con 3–4 con dato se calcula igual (valor conservador por la regla de la racha)
    y se advierte "parcial". Nunca da 1.0 solo por falta de datos.
  Supuestos sin calibrar: 4 campañas (las teliosporas pueden persistir 4–6 años) y 0.15.

Etiqueta del vigor: depende de `score.vigor_base` ("Vigor histórico (EVI)", "(EVI + NDVI)" o "(NDVI)"); ver
etiqueta_componente(). `vigor_base` es obligatorio en el JSON: la versión 1.2.0 calcula el vigor con EVI si hay
campañas con EVI y con NDVI si no (p. ej. datos de ejemplo), y la web/PDF/narrador lo muestran según ese campo.

Confianza del score (sin cambios en el valor del score):
- "alta": todos los componentes con dato (100 % del peso), rotación completa y al menos
  CONFIANZA_ALTA_FRAC_CAMPANIAS (2/3; 6 de 9) de las campañas con NDVI.
- "baja": rotación insuficiente, faltan 2+ componentes o menos de CONFIANZA_BAJA_FRAC_CAMPANIAS (1/2) de las
  campañas tienen NDVI.
- "media": el resto (p. ej. rotación parcial, 1 componente sin dato o entre 1/2 y 2/3 de campañas con NDVI).
`score.campanias_con_ndvi` y `score.campanias_total` dejan explícita esa cobertura.

Valores no finitos: NaN/inf en NDVI, EVI, agua o suelo cuentan como faltantes (nunca propagan NaN al score). Si el
NDVI máximo medio es <= 0 la estabilidad (coeficiente de variación) no está definida y queda null; el vigor con
una media negativa vale 0 (cae debajo de la referencia).

Datos mínimos y reponderación (v1.2.0):

- `vigor_historico` y `estabilidad` (series satelitales) son OBLIGATORIOS y exigen al menos
  SCORE_MIN_CAMPANIAS_NDVI (3) campañas con `ndvi_max`. Sin ellos el score total es `null` y
  `score.motivo_sin_score` explica por qué (nunca un número armado solo con suelo/agua).
- Cobertura = suma de los pesos nominales de los componentes con dato. Si es menor que
  SCORE_COBERTURA_MIN (0.70) el score total también es `null` con motivo.
- Si faltan componentes pero la cobertura alcanza, los pesos de los restantes se reescalan
  proporcionalmente (peso / cobertura) y eso queda EXPLÍCITO en el JSON: `score.reponderado`,
  `score.cobertura`, `score.componentes_usados`, `score.componentes_sin_dato` y `peso_efectivo`
  en cada componente (el aporte de un componente es 100 × valor × peso_efectivo). Más una
  advertencia visible. Un componente sin dato queda `valor: null`, nunca se rellena.
"""
from __future__ import annotations

import math
import statistics

from . import config


def _lin(x: float, lo: float, hi: float) -> float:
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def _finito(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _ndvi_max(campanias: list[dict]) -> list[float]:
    return [c["ndvi_max"] for c in campanias if _finito(c.get("ndvi_max"))]


def _evi_max(campanias: list[dict]) -> list[float]:
    return [c["evi_max"] for c in campanias if _finito(c.get("evi_max"))]


ETIQUETAS_VIGOR = {"evi": "Vigor histórico (EVI)", "combinado": "Vigor histórico (EVI + NDVI)",
                   "ndvi": "Vigor histórico (NDVI)"}


def etiqueta_componente(clave: str, vigor_base_: str | None = None) -> str:
    """Etiqueta legible; la del vigor dice con qué índice se calculó (score.vigor_base)."""
    if clave == "vigor_historico" and vigor_base_ in ETIQUETAS_VIGOR:
        return ETIQUETAS_VIGOR[vigor_base_]
    return config.SCORE_ETIQUETAS[clave]


def vigor_base(campanias: list[dict]) -> str | None:
    """Índice con que se calcula el vigor: 'evi', 'combinado' (EVI + NDVI), 'ndvi' (sin EVI suficiente) o None."""
    if len(_ndvi_max(campanias)) < config.SCORE_MIN_CAMPANIAS_NDVI:
        return None
    w = config.VIGOR_PESO_EVI
    if w > 0 and len(_evi_max(campanias)) >= config.SCORE_MIN_CAMPANIAS_NDVI:
        return "evi" if w >= 1 else "combinado"
    return "ndvi"


def vigor_historico(campanias: list[dict]) -> float | None:
    base = vigor_base(campanias)
    if base is None:
        return None
    v_ndvi = _lin(statistics.fmean(_ndvi_max(campanias)), *config.NDVI_MAX_REF)
    if base == "ndvi":
        return v_ndvi
    v_evi = _lin(statistics.fmean(_evi_max(campanias)), *config.EVI_MAX_REF)
    w = config.VIGOR_PESO_EVI
    return v_evi if base == "evi" else w * v_evi + (1 - w) * v_ndvi


def estabilidad(campanias: list[dict]) -> float | None:
    v = _ndvi_max(campanias)
    if len(v) < config.SCORE_MIN_CAMPANIAS_NDVI:
        return None
    media = statistics.fmean(v)
    if media <= 0:          # sin vegetación (agua/suelo desnudo): el CV no está definido
        return None
    cv = statistics.pstdev(v) / media
    return 1 - _lin(cv, *config.CV_REF)


def riesgo_hidrico(agua: dict, area_ha: float) -> float | None:
    if not (_finito(agua.get("max_ha_anegadas")) and _finito(agua.get("frecuencia_pct")) and _finito(area_ha)) or area_ha <= 0:
        return None
    frac = agua["max_ha_anegadas"] / area_ha
    return 1 - (0.6 * _lin(frac, *config.AGUA_FRAC_REF) + 0.4 * _lin(agua["frecuencia_pct"], *config.AGUA_FREC_REF))


def suelo(s: dict) -> float | None:
    if not all(_finito(s.get(k)) for k in ("arena_pct", "arcilla_pct", "carbono_org")):
        return None
    lo, hi = config.SUELO_ARENA_OPTIMA
    a = s["arena_pct"]
    arena = 1.0 if lo <= a <= hi else max(0.0, 1 - (lo - a if a < lo else a - hi) / 20)
    arc = s["arcilla_pct"]
    arcilla = 1.0 if arc <= config.SUELO_ARCILLA_MAX else max(0.0, 1 - (arc - config.SUELO_ARCILLA_MAX) / 20)
    co = min(1.0, s["carbono_org"] / config.SUELO_CO_OPTIMO)
    return (arena + arcilla + co) / 3


def _datos_rotacion(rot: dict) -> tuple[int, int, int]:
    """(con_dato, ventana, gap_conservador). Tolera dicts viejos sin los campos nuevos."""
    ventana = rot.get("campanias_ventana", config.ROTACION_VENTANA)
    sin_dato = rot.get("campanias_sin_dato_ultimas_5", 0)
    con_dato = rot.get("campanias_con_dato_ultimas_5", ventana - sin_dato)
    if "campanias_sin_mani_confirmadas" in rot:
        gap = rot["campanias_sin_mani_confirmadas"]
    elif rot.get("ultimo_mani") is not None:
        gap = rot["campanias_desde_mani"]
    else:
        gap = con_dato
    return con_dato, ventana, gap


def rotacion_mani(rot: dict) -> float | None:
    con_dato, ventana, gap = _datos_rotacion(rot)
    if con_dato < config.ROTACION_MIN_CAMPANIAS_CON_DATO:
        return None
    if config.ROTACION_EXIGE_DATO_COMPLETO and con_dato < ventana:
        return None
    rec = config.ROTACION_ANIOS_RECOMENDADOS
    base = min(1.0, gap / rec)
    if gap >= rec:
        return base
    previos = max(0, rot.get("veces_mani_ultimas_5", 0) - 1)
    return base * max(0.0, 1 - config.ROTACION_PENALIZ_REPETICION * previos)


def _confianza(comps: dict, rot: dict, n_ndvi: int, n_total: int) -> str:
    faltan = sum(1 for v in comps.values() if v is None)
    conf = rot.get("confianza_rotacion")
    frac = n_ndvi / n_total if n_total else 0.0
    if conf == "insuficiente" or faltan >= 2 or frac < config.CONFIANZA_BAJA_FRAC_CAMPANIAS:
        return "baja"
    if conf == "parcial" or faltan == 1 or frac < config.CONFIANZA_ALTA_FRAC_CAMPANIAS - 1e-9:
        return "media"
    return "alta"


def _motivo_sin_score(comps: dict, campanias: list[dict], cobertura: float) -> str | None:
    """Texto legible de por qué no hay score total, o None si hay datos suficientes."""
    faltan_oblig = [k for k in config.SCORE_COMPONENTES_OBLIGATORIOS if comps[k] is None]
    if faltan_oblig:
        n = len(_ndvi_max(campanias))
        if n >= config.SCORE_MIN_CAMPANIAS_NDVI:
            return (f"El NDVI máximo medio de las {n} campañas con NDVI es <= 0 (sin vegetación): no se puede "
                    "calcular la estabilidad entre campañas.")
        nombres = " y ".join(config.SCORE_ETIQUETAS[k] for k in faltan_oblig)
        return (f"Faltan datos satelitales suficientes para {nombres}: se necesitan al menos "
                f"{config.SCORE_MIN_CAMPANIAS_NDVI} campañas con NDVI y hay {n}.")
    if cobertura < config.SCORE_COBERTURA_MIN:
        sin = ", ".join(config.SCORE_ETIQUETAS[k] for k, v in comps.items() if v is None)
        return (f"Solo hay dato para el {round(100 * cobertura)} % del peso del score (mínimo "
                f"{round(100 * config.SCORE_COBERTURA_MIN)} %). Sin dato: {sin}.")
    return None


def calcular(lote: dict) -> tuple[dict, list[str]]:
    """Recibe el lote (campanias, agua, suelo, rotacion, area_ha). Devuelve (score, advertencias).

    `score.valor` es None (con `motivo_sin_score`) si faltan los datos mínimos; ver docstring del módulo.
    """
    comps = {
        "vigor_historico": vigor_historico(lote["campanias"]),
        "estabilidad": estabilidad(lote["campanias"]),
        "riesgo_hidrico": riesgo_hidrico(lote["agua"], lote["area_ha"]),
        "suelo": suelo(lote["suelo"]),
        "rotacion_mani": rotacion_mani(lote["rotacion"]),
    }
    usados = [k for k, v in comps.items() if v is not None]
    sin_dato = [k for k, v in comps.items() if v is None]
    cobertura = round(sum(config.SCORE_PESOS[k] for k in usados), 4)
    motivo = _motivo_sin_score(comps, lote["campanias"], cobertura)
    reponderado = motivo is None and bool(sin_dato)

    adv: list[str] = []
    rot = lote["rotacion"]
    con_dato, ventana, _ = _datos_rotacion(rot)
    if con_dato < config.ROTACION_MIN_CAMPANIAS_CON_DATO:
        adv.append(f"Rotación de maní: solo {con_dato} de {ventana} campañas con dato de maní "
                   f"(mínimo {config.ROTACION_MIN_CAMPANIAS_CON_DATO}); no se calculó el componente.")
    elif config.ROTACION_EXIGE_DATO_COMPLETO and con_dato < ventana:
        adv.append(f"Rotación de maní: {con_dato} de {ventana} campañas con dato de maní; modo estricto "
                   "(ROTACION_EXIGE_DATO_COMPLETO): no se calculó el componente.")
    elif con_dato < ventana:
        adv.append(f"Rotación de maní: calculada con datos parciales ({con_dato} de {ventana} campañas con dato "
                   "de maní). Las campañas sin dato se tratan como posible maní: valor conservador.")
    vb = vigor_base(lote["campanias"])
    n_ndvi, n_total = len(_ndvi_max(lote["campanias"])), len(lote["campanias"])
    if vb in ("evi", "combinado"):
        adv.append(f"Vigor calculado con EVI (referencias {config.EVI_MAX_REF[0]:g}–{config.EVI_MAX_REF[1]:g}) "
                   "PROVISORIAS: sin calibrar contra rendimientos reales.")
    elif vb == "ndvi" and any("evi_max" in c for c in lote["campanias"]):
        adv.append("Vigor calculado con NDVI: menos de "
                   f"{config.SCORE_MIN_CAMPANIAS_NDVI} campañas con EVI (el NDVI se satura con canopeo cerrado).")
    if motivo:
        adv.append(f"Score no disponible: {motivo}")
    else:
        adv += [f"Score: componente '{k}' sin datos." for k in sin_dato]
        if reponderado:
            etq = ", ".join(config.SCORE_ETIQUETAS[k] for k in sin_dato)
            adv.append(f"Score parcial: calculado sobre el {round(100 * cobertura)} % del peso (sin dato: {etq}); "
                       "los pesos de los demás componentes se reescalaron proporcionalmente.")

    valor = None
    if motivo is None:
        total = sum(config.SCORE_PESOS[k] * comps[k] for k in usados)
        valor = round(100 * total / cobertura)
    return {
        "valor": valor,
        "version": config.SCORE_VERSION,
        "vigor_base": vb,
        "confianza": None if valor is None else _confianza(comps, rot, n_ndvi, n_total),
        "campanias_con_ndvi": n_ndvi,
        "campanias_total": n_total,
        "cobertura": cobertura,
        "componentes_usados": usados if valor is not None else [],
        "componentes_sin_dato": sin_dato,
        "reponderado": reponderado,
        "motivo_sin_score": motivo,
        "componentes": [
            {"clave": k, "etiqueta": etiqueta_componente(k, vb),
             "valor": None if v is None else round(v, 2), "peso": config.SCORE_PESOS[k],
             "peso_efectivo": round(config.SCORE_PESOS[k] / cobertura, 4) if valor is not None and v is not None else None}
            for k, v in comps.items()
        ],
    }, adv
