"""Verificación 18/11: M4 (confianza "alta" exige cobertura de campañas), M3 (etiqueta del vigor explícita según
score.vigor_base) y valores no finitos (NaN/inf, NDVI medio <= 0) que no deben propagarse al score."""
import json
import math
from pathlib import Path

import jsonschema
import pytest

from agroscore import config, score
from tests.test_score import lote_base


def _comp(s, clave):
    return next(c for c in s["componentes"] if c["clave"] == clave)


def _serie(n_total, n_ndvi, v=0.8):
    return [{"ndvi_max": (v + 0.01 * (i % 3)) if i < n_ndvi else None} for i in range(n_total)]


# --- M4: confianza -----------------------------------------------------------------------------

@pytest.mark.parametrize("n_ndvi,esperada", [(9, "alta"), (6, "alta"), (5, "media"), (4, "baja"), (3, "baja")])
def test_confianza_segun_campanias_con_ndvi(n_ndvi, esperada):
    s, _ = score.calcular(lote_base(campanias=_serie(9, n_ndvi)))
    assert s["valor"] is not None
    assert s["campanias_con_ndvi"] == n_ndvi and s["campanias_total"] == 9
    assert s["confianza"] == esperada


def test_bug_m4_alta_con_3_de_9_campanias_ya_no():
    # antes: 3 de 9 campañas con NDVI y todo lo demás completo daba confianza "alta"
    s, _ = score.calcular(lote_base(campanias=_serie(9, 3)))
    assert s["confianza"] != "alta"


def test_alta_exige_100_por_ciento_del_peso():
    s, _ = score.calcular(lote_base(campanias=_serie(9, 9), suelo={"arena_pct": None, "arcilla_pct": 15, "carbono_org": 1}))
    assert s["reponderado"] and s["confianza"] == "media"


def test_alta_exige_rotacion_completa():
    rot = {"ultimo_mani": None, "campanias_desde_mani": None, "veces_mani_ultimas_5": 0, "campanias_sin_dato_ultimas_5": 1,
           "campanias_con_dato_ultimas_5": 4, "campanias_ventana": 5, "campanias_sin_mani_confirmadas": 4,
           "confianza_rotacion": "parcial"}
    s, _ = score.calcular(lote_base(campanias=_serie(9, 9), rotacion=rot))
    assert s["confianza"] == "media"


def test_confianza_no_cambia_el_valor():
    a, _ = score.calcular(lote_base(campanias=_serie(9, 9)))
    b, _ = score.calcular(lote_base(campanias=_serie(9, 9) + [{"ndvi_max": None}] * 9))
    assert a["valor"] == b["valor"] and a["confianza"] == "alta" and b["confianza"] == "media"


# --- M3: etiqueta del vigor explícita ----------------------------------------------------------

def test_etiqueta_del_vigor_segun_indice():
    con_evi = [{"ndvi_max": 0.9, "evi_max": 0.6}] * 4
    s_evi, _ = score.calcular(lote_base(campanias=con_evi))
    s_ndvi, _ = score.calcular(lote_base())
    assert s_evi["vigor_base"] == "evi" and _comp(s_evi, "vigor_historico")["etiqueta"] == "Vigor histórico (EVI)"
    assert s_ndvi["vigor_base"] == "ndvi" and _comp(s_ndvi, "vigor_historico")["etiqueta"] == "Vigor histórico (NDVI)"
    assert score.etiqueta_componente("vigor_historico", "combinado") == "Vigor histórico (EVI + NDVI)"
    assert score.etiqueta_componente("vigor_historico", None) == "Vigor histórico"
    assert score.etiqueta_componente("suelo", "evi") == config.SCORE_ETIQUETAS["suelo"]


def test_schema_exige_vigor_base_si_hay_score():
    sch = json.loads((Path(score.__file__).parent / "schema" / "lote.schema.json").read_text(encoding="utf-8"))
    sub = {"$defs": sch["$defs"], **sch["properties"]["score"]}
    s, _ = score.calcular(lote_base())
    jsonschema.validate(s, sub)
    sin = {k: v for k, v in s.items() if k != "vigor_base"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(sin, sub)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**s, "vigor_base": None}, sub)


# --- valores no finitos ------------------------------------------------------------------------

def test_nan_en_ndvi_cuenta_como_faltante():
    camp = [{"ndvi_max": v} for v in (0.8, float("nan"), 0.82, float("inf"), 0.79)]
    s, _ = score.calcular(lote_base(campanias=camp))
    assert s["valor"] is not None and s["campanias_con_ndvi"] == 3
    assert all(c["valor"] is None or math.isfinite(c["valor"]) for c in s["componentes"])


def test_nan_en_evi_no_rompe_el_vigor():
    camp = [{"ndvi_max": 0.9, "evi_max": float("nan")}] * 4
    s, _ = score.calcular(lote_base(campanias=camp))
    assert s["vigor_base"] == "ndvi" and math.isfinite(_comp(s, "vigor_historico")["valor"])


@pytest.mark.parametrize("v", [0.0, -0.1])
def test_ndvi_medio_cero_o_negativo_estabilidad_null(v):
    s, _ = score.calcular(lote_base(campanias=[{"ndvi_max": v}] * 4))
    assert _comp(s, "estabilidad")["valor"] is None
    assert s["valor"] is None and "<= 0" in s["motivo_sin_score"]
    assert _comp(s, "vigor_historico")["valor"] == 0.0


def test_nan_en_agua_y_suelo_son_null():
    s, _ = score.calcular(lote_base(campanias=_serie(4, 4), agua={"max_ha_anegadas": float("nan"), "frecuencia_pct": 2.0},
                                    suelo={"arena_pct": 55, "arcilla_pct": float("nan"), "carbono_org": 1.2}))
    assert _comp(s, "riesgo_hidrico")["valor"] is None and _comp(s, "suelo")["valor"] is None
    assert s["valor"] is None and "65 %" in s["motivo_sin_score"]          # cobertura 0.65 < 0.70
    solo_agua, _ = score.calcular(lote_base(campanias=_serie(4, 4), agua={"max_ha_anegadas": 1.0, "frecuencia_pct": float("inf")}))
    assert _comp(solo_agua, "riesgo_hidrico")["valor"] is None and solo_agua["reponderado"] and solo_agua["valor"] is not None
    assert all(c["valor"] is None or math.isfinite(c["valor"]) for c in s["componentes"])
