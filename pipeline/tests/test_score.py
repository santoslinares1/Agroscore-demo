import pytest

from agroscore import config, score


def lote_base(**kw):
    l = {
        "area_ha": 100.0,
        "campanias": [{"ndvi_max": v} for v in (0.80, 0.82, 0.78, 0.81)],
        "agua": {"max_ha_anegadas": 2.0, "frecuencia_pct": 2.0},
        "suelo": {"arena_pct": 55, "arcilla_pct": 15, "carbono_org": 1.2},
        "rotacion": {"ultimo_mani": None, "campanias_desde_mani": None, "veces_mani_ultimas_5": 0,
                     "campanias_sin_dato_ultimas_5": 0},
    }
    l.update(kw)
    return l


def test_pesos_suman_1():
    assert sum(config.SCORE_PESOS.values()) == pytest.approx(1.0)


def test_score_rango_y_formula():
    s, adv = score.calcular(lote_base())
    assert 0 <= s["valor"] <= 100 and not adv
    esperado = round(100 * sum(c["peso"] * c["valor"] for c in s["componentes"]))
    assert abs(s["valor"] - esperado) <= 1  # componentes redondeados a 2 decimales
    assert s["version"] == config.SCORE_VERSION


def test_mani_reciente_baja_el_score():
    sin = score.calcular(lote_base())[0]["valor"]
    con = score.calcular(lote_base(rotacion={"ultimo_mani": "2025/26", "campanias_desde_mani": 0,
                                             "veces_mani_ultimas_5": 3, "campanias_sin_dato_ultimas_5": 0}))[0]
    assert con["valor"] < sin
    assert next(c for c in con["componentes"] if c["clave"] == "rotacion_mani")["valor"] == 0


def test_componente_nulo_renormaliza_y_advierte():
    s, adv = score.calcular(lote_base(suelo={"arena_pct": None, "arcilla_pct": None, "carbono_org": None}))
    assert s["valor"] is not None
    assert any("suelo" in a for a in adv)
    assert next(c for c in s["componentes"] if c["clave"] == "suelo")["valor"] is None


def test_anegamiento_baja_riesgo_hidrico():
    ok = score.riesgo_hidrico({"max_ha_anegadas": 0, "frecuencia_pct": 0}, 100)
    malo = score.riesgo_hidrico({"max_ha_anegadas": 20, "frecuencia_pct": 30}, 100)
    assert ok == 1 and malo == 0


# --- Rotación de maní: datos faltantes, cobertura y doble penalización (score v1.1.0) -----------


def _rot(**kw):
    r = {"ultimo_mani": None, "campanias_desde_mani": None, "veces_mani_ultimas_5": 0,
         "campanias_sin_dato_ultimas_5": 0, "campanias_con_dato_ultimas_5": 5, "campanias_ventana": 5,
         "campanias_sin_mani_confirmadas": 5, "cobertura_rotacion": 1.0, "confianza_rotacion": "completa"}
    r.update(kw)
    return r


def test_rotacion_intervalo_exacto_no_se_castiga():
    # último maní hace exactamente 4 campañas sin maní entre medio (>3 años, INTA): 1.0
    r = _rot(ultimo_mani="2021/22", campanias_desde_mani=4, veces_mani_ultimas_5=1,
             campanias_sin_mani_confirmadas=4)
    assert score.rotacion_mani(r) == 1.0


def test_rotacion_sin_intervalo_penaliza_repeticion_una_vez():
    sin_rep = score.rotacion_mani(_rot(ultimo_mani="2023/24", campanias_desde_mani=2, veces_mani_ultimas_5=1,
                                       campanias_sin_mani_confirmadas=2))
    con_rep = score.rotacion_mani(_rot(ultimo_mani="2023/24", campanias_desde_mani=2, veces_mani_ultimas_5=2,
                                       campanias_sin_mani_confirmadas=2))
    assert sin_rep == pytest.approx(0.5)
    assert con_rep == pytest.approx(0.5 * 0.85)  # un maní previo al último


def test_rotacion_mani_reciente_da_cero():
    assert score.rotacion_mani(_rot(ultimo_mani="2025/26", campanias_desde_mani=0, veces_mani_ultimas_5=3,
                                    campanias_sin_mani_confirmadas=0)) == 0


def test_rotacion_insuficiente_es_none_y_no_1():
    r = _rot(campanias_sin_dato_ultimas_5=3, campanias_con_dato_ultimas_5=2, cobertura_rotacion=0.4,
             campanias_sin_mani_confirmadas=0, confianza_rotacion="insuficiente")
    assert score.rotacion_mani(r) is None
    s, adv = score.calcular(lote_base(rotacion=r))
    comp = next(c for c in s["componentes"] if c["clave"] == "rotacion_mani")
    assert comp["valor"] is None and s["confianza"] == "baja"
    assert any("Rotación de maní" in a and "2 de 5" in a for a in adv)
    assert s["valor"] is not None  # pesos renormalizados


def test_rotacion_parcial_conservadora_y_advierte():
    # 4 de 5 con dato, la última campaña sin dato: la racha confirmada es 0 -> valor 0, no 1.0
    r = _rot(campanias_sin_dato_ultimas_5=1, campanias_con_dato_ultimas_5=4, cobertura_rotacion=0.8,
             campanias_sin_mani_confirmadas=0, confianza_rotacion="parcial")
    assert score.rotacion_mani(r) == 0
    s, adv = score.calcular(lote_base(rotacion=r))
    assert s["confianza"] == "media"
    assert any("datos parciales" in a for a in adv)


def test_rotacion_parcial_con_racha_larga_si_alcanza():
    # el hueco está al principio de la ventana; las 4 campañas más recientes sin maní confirmadas -> 1.0
    r = _rot(campanias_sin_dato_ultimas_5=1, campanias_con_dato_ultimas_5=4, cobertura_rotacion=0.8,
             campanias_sin_mani_confirmadas=4, confianza_rotacion="parcial")
    assert score.rotacion_mani(r) == 1.0


def test_confianza_alta_con_todo():
    s, _ = score.calcular(lote_base(rotacion=_rot()))
    assert s["confianza"] == "alta"
