"""Score v1.2.0: datos mínimos, reponderación explícita y propagación del score null.

Reproduce los dos bugs de la revisión de arquitectura (17/11/2026):
  1. score 100/100 con solo suelo (sin una sola imagen satelital);
  2. rotación de maní 1.0 cuando faltaban campañas / el mapa de cultivos no distingue maní.
Los proveedores falsos viven solo acá (MOCK, solo tests).
"""
import json
import socket
import threading

import jsonschema
import pytest
from pypdf import PdfReader

import server
from agroscore import aoi, config, crops, narrator, pipeline, publicar, score
from agroscore.ejemplo import ProveedorEjemplo
from tests.test_score import lote_base
from tests.test_server import feature


def _comp(s, clave):
    return next(c for c in s["componentes"] if c["clave"] == clave)


def _camp(cultivos):
    return [{"campania": f"{2017 + i}/{str(2018 + i)[-2:]}", "cultivo": c} for i, c in enumerate(cultivos)]


# --- Bug 1: 100/100 con solo suelo -------------------------------------------------------------

def test_bug_100_con_solo_suelo_ahora_es_null_con_motivo():
    lote = lote_base(
        campanias=[{"ndvi_max": None}] * 5,                      # ni una imagen satelital válida
        agua={"max_ha_anegadas": None, "frecuencia_pct": None},
        suelo={"arena_pct": 55, "arcilla_pct": 15, "carbono_org": 1.5},   # suelo ideal -> 1.0
        rotacion={"ultimo_mani": None, "campanias_sin_dato_ultimas_5": 5, "campanias_con_dato_ultimas_5": 0,
                  "campanias_ventana": 5},
    )
    s, adv = score.calcular(lote)
    assert s["valor"] is None                                    # antes: 100
    assert "campañas con NDVI" in s["motivo_sin_score"] and "hay 0" in s["motivo_sin_score"]
    assert s["confianza"] is None and s["componentes_usados"] == [] and s["reponderado"] is False
    assert _comp(s, "suelo")["valor"] == 1.0                     # el componente con dato se informa igual
    assert all(c["peso_efectivo"] is None for c in s["componentes"])
    assert any(a.startswith("Score no disponible") for a in adv)


def test_suelo_y_rotacion_perfectos_sin_ndvi_tampoco_dan_score():
    lote = lote_base(campanias=[{"ndvi_max": None}] * 4,
                     rotacion={"ultimo_mani": None, "campanias_desde_mani": None, "veces_mani_ultimas_5": 0,
                               "campanias_sin_dato_ultimas_5": 0, "campanias_con_dato_ultimas_5": 5,
                               "campanias_ventana": 5, "campanias_sin_mani_confirmadas": 5})
    s, _ = score.calcular(lote)
    assert s["valor"] is None
    assert s["cobertura"] == pytest.approx(0.45)  # agua .20 + suelo .15 + rotación .10


@pytest.mark.parametrize("n_ndvi", [0, 1, 2])
def test_menos_de_3_campanias_con_ndvi_no_hay_score(n_ndvi):
    campanias = [{"ndvi_max": 0.8}] * n_ndvi + [{"ndvi_max": None}] * (4 - n_ndvi)
    s, _ = score.calcular(lote_base(campanias=campanias))
    assert s["valor"] is None and f"hay {n_ndvi}" in s["motivo_sin_score"]
    assert _comp(s, "vigor_historico")["valor"] is None and _comp(s, "estabilidad")["valor"] is None


def test_con_3_campanias_ndvi_hay_score():
    s, _ = score.calcular(lote_base(campanias=[{"ndvi_max": v} for v in (0.8, 0.82, 0.78)] + [{"ndvi_max": None}]))
    assert s["valor"] is not None and s["motivo_sin_score"] is None


def test_cobertura_minima_70_sin_score_aunque_haya_series():
    # vigor .35 + estabilidad .20 + rotación .10 = .65 < .70 (faltan agua y suelo)
    lote = lote_base(agua={"max_ha_anegadas": None, "frecuencia_pct": None},
                     suelo={"arena_pct": None, "arcilla_pct": None, "carbono_org": None})
    s, _ = score.calcular(lote)
    assert s["cobertura"] == pytest.approx(0.65)
    assert s["valor"] is None and "65 %" in s["motivo_sin_score"] and "70 %" in s["motivo_sin_score"]


# --- Reponderación explícita ---------------------------------------------------------------------

def test_reponderacion_queda_explicita_en_el_json():
    s, adv = score.calcular(lote_base(suelo={"arena_pct": None, "arcilla_pct": None, "carbono_org": None}))
    assert s["valor"] is not None and s["reponderado"] is True
    assert s["cobertura"] == pytest.approx(0.85)
    assert "suelo" in s["componentes_sin_dato"] and "suelo" not in s["componentes_usados"]
    assert _comp(s, "suelo")["peso_efectivo"] is None
    assert _comp(s, "vigor_historico")["peso_efectivo"] == pytest.approx(0.35 / 0.85, abs=1e-4)
    assert sum(c["peso_efectivo"] for c in s["componentes"] if c["peso_efectivo"] is not None) == pytest.approx(1.0, abs=1e-3)
    assert any(a.startswith("Score parcial") and "85 %" in a for a in adv)
    # el aporte (100 × valor × peso_efectivo) reconstruye el score
    aportes = sum(100 * c["valor"] * c["peso_efectivo"] for c in s["componentes"] if c["peso_efectivo"] is not None)
    assert abs(aportes - s["valor"]) <= 1


def test_sin_faltantes_no_hay_reponderacion():
    s, adv = score.calcular(lote_base())
    assert s["reponderado"] is False and s["cobertura"] == pytest.approx(1.0)
    assert s["motivo_sin_score"] is None and not adv
    assert all(c["peso_efectivo"] == pytest.approx(c["peso"]) for c in s["componentes"])


# --- Bug 2: rotación 1.0 con campañas faltantes ------------------------------------------------------

def test_bug_rotacion_1_con_campanias_faltantes():
    """2 de las últimas 5 sin dato y ningún maní visto: antes daba 1.0 (rotación 'perfecta')."""
    rot = crops.derivar_rotacion(_camp(["soja", "soja", "maiz", "soja", None, None, "maiz"]))
    assert rot["ultimo_mani"] is None and rot["campanias_sin_dato_ultimas_5"] == 2
    v = score.rotacion_mani(rot)
    assert v is not None and v < 1.0           # una campaña sin dato corta la racha de «sin maní» confirmadas
    assert v == pytest.approx(1 / config.ROTACION_ANIOS_RECOMENDADOS)  # solo la última campaña confirmada


def test_bug_rotacion_1_con_mapbiomas_que_no_distingue_mani():
    """Todas 'cultivo_temporario' (MapBiomas): no se puede afirmar 'sin maní' -> null, no 1.0."""
    rot = crops.derivar_rotacion(_camp(["cultivo_temporario"] * 9))
    assert rot["campanias_con_dato_ultimas_5"] == 0
    assert score.rotacion_mani(rot) is None


def test_rotacion_null_si_falta_dato_en_todas_las_campanias_sin_dato():
    rot = crops.derivar_rotacion(_camp([None] * 9))
    assert score.rotacion_mani(rot) is None


def test_rotacion_modo_estricto_null_si_cualquier_campania_sin_dato(monkeypatch):
    rot = crops.derivar_rotacion(_camp(["soja", "maiz", "soja", None, "maiz", "soja", "maiz"]))
    assert score.rotacion_mani(rot) is not None   # modo por defecto: parcial conservador
    monkeypatch.setattr(config, "ROTACION_EXIGE_DATO_COMPLETO", True)
    assert score.rotacion_mani(rot) is None
    s, adv = score.calcular(lote_base(rotacion=rot))
    assert _comp(s, "rotacion_mani")["valor"] is None
    assert any("modo estricto" in a for a in adv)
    assert s["valor"] is not None and s["reponderado"] is True  # 0.90 de cobertura


# --- Propagación: schema, narrador, PDF, publicar --------------------------------------------------------

class ProveedorSinSatelite(ProveedorEjemplo):
    """MOCK (solo tests): igual que el real (ejemplo=False) pero sin ninguna campaña con NDVI."""
    ejemplo = False
    nombre = "gee"

    def stats_campanias(self, lote, campanias):
        return {c: {"ndvi_max": None, "ndvi_medio": None, "ndmi_medio": None, "pct_nubes": None,
                    "hueco_max_semanas": None, "n_escenas": 0} for c in campanias}


@pytest.fixture(scope="module")
def doc_sin_score(tmp_path_factory):
    out = tmp_path_factory.mktemp("sin_score")
    lote = aoi.lote_desde_feature(feature("cargado_sinscore_0001"))
    doc = pipeline.procesar_lote(lote, ProveedorSinSatelite(), out)
    return out, lote, doc


def test_pipeline_con_score_null_valida_schema_y_no_revienta(doc_sin_score):
    out, lote, doc = doc_sin_score
    assert doc["score"]["valor"] is None and doc["score"]["motivo_sin_score"]
    guardado = json.loads((out / lote.id / "lote.json").read_text())
    pipeline.validar(guardado, "lote.schema.json")
    assert any(a.startswith("Score no disponible") for a in guardado["advertencias"])


def test_schema_exige_motivo_si_valor_null_y_prohibe_motivo_si_hay_valor(doc_sin_score):
    _, _, doc = doc_sin_score
    malo = json.loads(json.dumps(doc))
    malo["score"]["motivo_sin_score"] = None
    with pytest.raises(jsonschema.ValidationError):
        pipeline.validar(malo, "lote.schema.json")
    con_valor, _ = score.calcular(lote_base())
    mezcla = json.loads(json.dumps(doc))
    mezcla["score"] = {**con_valor, "motivo_sin_score": "algo"}
    with pytest.raises(jsonschema.ValidationError):
        pipeline.validar(mezcla, "lote.schema.json")


def test_narrador_plantilla_dice_sin_dato_suficiente(doc_sin_score):
    out, lote, doc = doc_sin_score
    txt = (out / lote.id / "resumen.md").read_text()
    assert "sin dato suficiente" in txt and "/100" not in txt
    assert doc["score"]["motivo_sin_score"].split(".")[0] in txt
    assert "score.valor es null" in narrator.PROMPT


def test_pdf_dice_sin_dato_suficiente_y_no_un_numero(doc_sin_score):
    out, lote, _ = doc_sin_score
    txt = "\n".join(p.extract_text() for p in PdfReader(str(out / lote.id / "informe.pdf")).pages)
    assert "sin dato suficiente" in txt.lower()
    assert "/100" not in txt.split("Resumen")[0]
    assert "Motivo:" in txt


def test_publicar_y_index_con_score_null(doc_sin_score, tmp_path):
    out, lote, _ = doc_sin_score
    dest = tmp_path / "demo"
    publicar.publicar(out / lote.id, [dest])
    idx = json.loads((dest / "index.json").read_text())
    assert idx["lotes"][0]["score"] is None
    pipeline.validar(idx, "index.schema.json")


def test_pdf_y_resumen_con_score_parcial(tmp_path):
    class SinSuelo(ProveedorEjemplo):
        ejemplo = False
        nombre = "gee"

        def suelo(self, lote):
            return {"arcilla_pct": None, "arena_pct": None, "carbono_org": None, "fuente": "SoilGrids"}

    lote = aoi.lote_desde_feature(feature("cargado_parcial_0001"))
    doc = pipeline.procesar_lote(lote, SinSuelo(), tmp_path)
    s = doc["score"]
    assert s["valor"] is not None and s["reponderado"] is True
    txt = "\n".join(p.extract_text() for p in PdfReader(str(tmp_path / lote.id / "informe.pdf")).pages)
    assert "Score parcial" in txt and "Peso efectivo" in txt
    assert "score parcial" in (tmp_path / lote.id / "resumen.md").read_text()


# --- server.py: Content-Length no numérico -> 400 (antes: excepción sin respuesta) -----------------

def test_content_length_no_numerico_devuelve_400():
    app = server.App(lambda: (True, "mock"), lambda l, p: {})
    srv = server.crear_servidor(app, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        s = socket.create_connection(("127.0.0.1", srv.server_address[1]), timeout=5)
        s.sendall(b"POST /api/lotes HTTP/1.1\r\nHost: localhost\r\nContent-Length: abc\r\n\r\n")
        resp = s.recv(2048).decode()
        s.close()
        assert resp.startswith(("HTTP/1.0 400", "HTTP/1.1 400"))
        assert "Content-Length inválido" in resp
        assert app.trabajos == {}
    finally:
        srv.shutdown()
        srv.server_close()
