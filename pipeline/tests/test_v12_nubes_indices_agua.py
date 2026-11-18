"""v1.2.0: Cloud Score+ + SCL, índices EVI/NDRE, vigor con EVI y confirmación óptica/JRC del agua.

Todo sin red: la lógica pura se prueba con numpy; la parte de Earth Engine con un `ee` falso (MagicMock) que
solo registra qué colección/banda/umbral se pidió. La equivalencia de las fórmulas con GEE real se verificó a
mano contra la API en vivo (ver README, «Verificación en vivo»).
"""
import json
from unittest.mock import MagicMock

import numpy as np
import pytest

from agroscore import aoi, config, narrator, pipeline, s2, score, water
from agroscore.ejemplo import ProveedorEjemplo
from tests.conftest import DATA


# --- Cloud Score+ y SCL ------------------------------------------------------------------------

def test_config_scl_validas_y_excluidas():
    assert config.S2_SCL_VALIDAS == [4, 5, 6]
    assert set(config.S2_SCL_EXCLUIDAS) == {3, 7, 8, 9, 10, 11}
    assert not set(config.S2_SCL_VALIDAS) & set(config.S2_SCL_EXCLUIDAS)
    assert config.S2_CS_UMBRAL == 0.6 and config.S2_CS_BANDA == "cs_cdf"
    assert config.S2_CLOUD_SCORE_PLUS == "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
    assert not hasattr(config, "S2_CLOUD_PROB")  # el join con s2cloudless ya no existe


def test_coleccion_enlaza_cloud_score_plus_y_enmascara_con_umbral(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(s2, "ee", lambda: fake)
    s2.coleccion("geom", "2024-10-01", "2025-04-01")
    pedidas = [c.args[0] for c in fake.ImageCollection.call_args_list if c.args and isinstance(c.args[0], str)]
    assert config.S2_CLOUD_SCORE_PLUS in pedidas
    assert config.S2_COLECCION in pedidas
    assert "COPERNICUS/S2_CLOUD_PROBABILITY" not in pedidas
    enlazada = fake.ImageCollection.return_value.filterBounds.return_value.filterDate.return_value.filter.return_value
    args = enlazada.linkCollection.call_args.args
    assert args[1] == ["cs_cdf"]


def test_enmascarar_usa_umbral_y_clases_validas():
    img = MagicMock()
    scl = img.select.return_value
    s2._enmascarar(img)
    scl.remap.assert_called_once_with([4, 5, 6], [1, 1, 1], 0)
    img.select.assert_any_call("cs_cdf")
    img.select.return_value.gte.assert_called_once_with(config.S2_CS_UMBRAL)


# --- Índices -----------------------------------------------------------------------------------

def test_evi_valor_conocido():
    # B8=0.5, B4=0.05, B2=0.03: 2.5*0.45 / (0.5 + 0.3 - 0.225 + 1) = 1.125 / 1.575
    assert s2.evi(0.5, 0.05, 0.03) == pytest.approx(1.125 / 1.575)


def test_evi_no_se_satura_como_ndvi():
    # dos canopeos densos (B8 0.45 vs 0.60, rojo bajo): el NDVI apenas se mueve (~0.92 -> ~0.94), el EVI separa más
    def ndvi(b8, b4): return (b8 - b4) / (b8 + b4)
    a, b = (0.45, 0.02, 0.02), (0.60, 0.02, 0.02)
    dn, de = ndvi(b[0], b[1]) - ndvi(a[0], a[1]), s2.evi(*b) - s2.evi(a[0], a[1], a[2])
    assert dn < 0.03 and de > 0.1


def test_ndre_valor_conocido_y_signo():
    assert s2.ndre(0.45, 0.25) == pytest.approx(0.2 / 0.7)
    assert s2.ndre(0.2, 0.3) < 0  # suelo/estrés: B5 > B8A


def test_expresiones_gee_iguales_a_las_funciones_numpy():
    """La cadena que corre en Earth Engine (Image.expression) da lo mismo que evi()/ndre() en numpy."""
    rng = np.random.default_rng(1)
    b2, b4, b5, b8, b8a = (rng.uniform(0.01, 0.6, 500) for _ in range(5))
    np.testing.assert_allclose(eval(s2.EVI_EXPR, {}, {"b8": b8, "b4": b4, "b2": b2}), s2.evi(b8, b4, b2))
    np.testing.assert_allclose(eval(s2.NDRE_EXPR, {}, {"b8a": b8a, "b5": b5}), s2.ndre(b8a, b5))


def test_indices_pide_escala_reflectancia_y_expresiones():
    img = MagicMock()
    s2._indices(img)
    img.select.return_value.divide.assert_called_once_with(10000.0)
    exprs = [c.args[0] for c in img.select.return_value.divide.return_value.expression.call_args_list]
    assert exprs == [s2.EVI_EXPR, s2.NDRE_EXPR]


# --- Vigor con EVI -----------------------------------------------------------------------------

def _camps(ndvi, evi=None):
    return [{"ndvi_max": n, **({"evi_max": e} if evi else {})} for n, e in zip(ndvi, evi or ndvi)]


def test_vigor_usa_evi_y_refs_configurables(monkeypatch):
    c = _camps([0.95] * 4, [0.60] * 4)
    assert score.vigor_base(c) == "evi"
    esperado = (0.60 - config.EVI_MAX_REF[0]) / (config.EVI_MAX_REF[1] - config.EVI_MAX_REF[0])
    assert score.vigor_historico(c) == pytest.approx(esperado)
    assert score.vigor_historico(c) < 1.0           # con NDVI 0.95 daba 1.0 (saturado)
    monkeypatch.setattr(config, "EVI_MAX_REF", (0.2, 0.6))
    assert score.vigor_historico(c) == pytest.approx(1.0)


def test_vigor_combinado_y_fallback_ndvi(monkeypatch):
    c = _camps([0.95] * 4, [0.525] * 4)
    monkeypatch.setattr(config, "VIGOR_PESO_EVI", 0.5)
    assert score.vigor_base(c) == "combinado"
    v_e = (0.525 - 0.30) / 0.45
    assert score.vigor_historico(c) == pytest.approx(0.5 * v_e + 0.5 * 1.0)
    # sin EVI (JSON viejo / ejemplo): cae a NDVI y lo dice
    viejo = _camps([0.80] * 4)
    assert score.vigor_base(viejo) == "ndvi"
    assert score.vigor_historico(viejo) == pytest.approx((0.80 - 0.55) / 0.35)
    # menos de 3 campañas con EVI: también NDVI
    poco = [{"ndvi_max": 0.8, "evi_max": 0.5}, {"ndvi_max": 0.8, "evi_max": 0.5}, {"ndvi_max": 0.8, "evi_max": None}]
    assert score.vigor_base(poco) == "ndvi"


def test_score_expone_vigor_base_y_advierte_provisorio():
    from tests.test_score import lote_base
    s, adv = score.calcular(lote_base(campanias=_camps([0.9] * 4, [0.6] * 4)))
    assert s["vigor_base"] == "evi"
    assert any("PROVISORIAS" in a for a in adv)
    s2_, adv2 = score.calcular(lote_base())
    assert s2_["vigor_base"] == "ndvi" and not adv2


def test_version_del_score():
    assert config.SCORE_VERSION == "1.2.0"


# --- Agua: confirmación óptica / JRC -----------------------------------------------------------

S1 = np.array([True, True, True, True, False])
OPT = np.array([True, False, False, False, True])      # MNDWI > 0 donde hay óptico limpio
JRC = np.array([False, False, True, False, False])


def test_confirmar_tabla_de_verdad():
    # px0: S1 + óptico -> sí | px1: S1 sin óptico ni JRC (suelo liso) -> no
    # px2: S1 + JRC sin óptico -> sí | px3: S1 sola -> no | px4: óptico sin S1 -> no
    assert water.confirmar_anegado(S1, OPT, JRC).tolist() == [True, False, True, False, False]


def test_sin_optico_valido_no_se_confirma():
    optico = np.zeros(5, dtype=bool)                   # nube en toda la ventana: no hay óptico válido
    sin_jrc = np.zeros(5, dtype=bool)
    assert not water.confirmar_anegado(S1, optico, sin_jrc).any()
    assert water.confirmar_anegado(S1, optico, JRC).tolist() == [False, False, True, False, False]


def test_jrc_umbral_ocurrencia(monkeypatch):
    occ = np.array([0.0, 4.9, 5.0, 80.0])
    assert water.jrc_es_agua(occ).tolist() == [False, False, True, True]
    assert water.jrc_es_agua(occ, 50).tolist() == [False, False, False, True]
    monkeypatch.setattr(config, "AGUA_JRC_OCURRENCIA_MIN_PCT", 90.0)
    assert not water.jrc_es_agua(occ).any()


def test_ventana_optica_configurable():
    assert water.ventana_optica("2022-10-14", 10) == ("2022-10-04", "2022-10-25")  # fin exclusivo
    assert water.ventana_optica("2022-01-02", 5) == ("2021-12-28", "2022-01-08")
    assert config.AGUA_VENTANA_OPTICA_DIAS == 10
    assert water.ventana_optica("2022-10-14") == ("2022-10-04", "2022-10-25")


def test_resumir_escenas():
    filas = [
        {"fecha": "2020-05-01", "ha": 0.0, "ha_s1": 40.0, "ha_optico": 50.0},
        {"fecha": "2021-03-02", "ha": 3.2, "ha_s1": 3.5, "ha_optico": 10.0},
        {"fecha": "2022-07-22", "ha": 0.0, "ha_s1": 52.0, "ha_optico": 0.0},
    ]
    r = water.resumir_escenas(filas, 0.04, area_ha=100.0)
    # marcadas = ha_s1 >= 5 % de 100 ha: escenas 1 y 3; sin óptico (< 50 ha con dato válido): solo la 3 (la 1 tiene justo 50)
    assert r["n_escenas_s1_marcadas"] == 2 and r["n_escenas_s1_marcadas_sin_optico"] == 1
    assert r["n_escenas_s1_confirmadas"] == 1
    assert r["max_ha_anegadas"] == 3.2 and r["fecha_max"] == "2021-03-02"
    assert r["max_ha_s1_sin_confirmar"] == 52.0 and r["fecha_max_s1_sin_confirmar"] == "2022-07-22"
    assert r["n_escenas_s1"] == 3 and r["n_escenas_s1_con_optico"] == 2
    assert r["frecuencia_pct"] == 0.0 and "sin óptico válido no se confirma" in r["criterio"]


def test_resumir_escenas_sin_anegamiento_y_sin_escenas():
    r = water.resumir_escenas([{"fecha": "2020-05-01", "ha": 0.0, "ha_s1": 12.0, "ha_optico": 5.0}], 0)
    assert r["max_ha_anegadas"] == 0.0 and r["fecha_max"] is None
    vacio = water.resumir_escenas([], None)
    assert vacio["max_ha_anegadas"] is None and vacio["n_escenas_s1"] == 0 and vacio["frecuencia_pct"] is None


# --- Salida (schema, narrador, PDF) con los campos nuevos ----------------------------------------

class _ProveedorV12(ProveedorEjemplo):
    """MOCK solo tests: ejemplo + EVI/NDRE y agua con confirmación (para probar contrato, resumen y PDF)."""

    def stats_campanias(self, lote, campanias):
        out = super().stats_campanias(lote, campanias)
        for st in out.values():
            st.update(evi_max=round(st["ndvi_max"] * 0.7, 3), evi_medio=0.3, ndre_max=0.4, ndre_medio=0.25,
                      obs_validas_px=12.5)
        return out

    def agua(self, lote):
        return {"max_ha_anegadas": 1.5, "fecha_max": "2021-03-02", "frecuencia_pct": 0.0,
                "max_ha_s1_sin_confirmar": 40.0, "fecha_max_s1_sin_confirmar": "2022-07-22",
                "n_escenas_s1": 300, "n_escenas_s1_con_optico": 250, "criterio": "test"}


def test_salida_v12_valida_schema_narrador_y_pdf(tmp_path):
    lote = aoi.cargar(DATA / "lotes.geojson")[0]
    doc = pipeline.procesar_lote(lote, _ProveedorV12(), tmp_path, config.campanias(2019, 2025))
    guardado = json.loads((tmp_path / lote.id / "lote.json").read_text())
    pipeline.validar(guardado, "lote.schema.json")
    assert guardado["score"]["vigor_base"] == "evi"
    assert all(c["evi_max"] is not None and c["ndre_max"] is not None for c in guardado["campanias"])
    assert any("solo 1.5 ha se confirmaron" in a for a in doc["advertencias"])
    resumen = (tmp_path / lote.id / "resumen.md").read_text()
    assert "EVI" in resumen and "40,0 ha" in resumen and "confirmadas" in resumen
    from pypdf import PdfReader
    texto = "\n".join(p.extract_text() for p in PdfReader(str(tmp_path / lote.id / "informe.pdf")).pages)
    assert "EVI" in texto and "NDRE" in texto and "PROVISORIAS" in texto and "Cloud Score+" in texto


def test_narrador_ejemplo_sin_evi_no_menciona_evi(tmp_path):
    lote = aoi.cargar(DATA / "lotes.geojson")[0]
    pipeline.procesar_lote(lote, ProveedorEjemplo(), tmp_path, config.campanias(2019, 2025))
    assert "EVI" not in (tmp_path / lote.id / "resumen.md").read_text()
