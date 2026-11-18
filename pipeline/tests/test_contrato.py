"""Tests de contrato: el lote.json valida contra el schema y el score del PDF es
idéntico al del JSON. Usa el proveedor de ejemplo y un proveedor MOCK (solo tests)."""
import json
import re

import numpy as np
import pytest
from pypdf import PdfReader

from tests.conftest import DATA
from agroscore import aoi, config, pipeline
from agroscore.ejemplo import ProveedorEjemplo

CAMP = config.campanias(2019, 2025)


@pytest.fixture(scope="module")
def lotes():
    return aoi.cargar(DATA / "lotes.geojson")


@pytest.fixture(scope="module")
def salida_ejemplo(tmp_path_factory, lotes):
    out = tmp_path_factory.mktemp("out")
    docs = [pipeline.procesar_lote(l, ProveedorEjemplo(), out, CAMP) for l in lotes]
    idx = pipeline.escribir_index(docs, out)
    return out, docs, idx


def texto_pdf(path):
    return "\n".join(p.extract_text() for p in PdfReader(str(path)).pages)


def test_schema_lote_e_index(salida_ejemplo):
    out, docs, idx = salida_ejemplo
    for d in docs:
        guardado = json.loads((out / d["id"] / "lote.json").read_text())
        pipeline.validar(guardado, "lote.schema.json")
    pipeline.validar(json.loads((out / "index.json").read_text()), "index.schema.json")
    assert [l["score"] for l in idx["lotes"]] == [d["score"]["valor"] for d in docs]


def test_score_pdf_igual_json(salida_ejemplo):
    out, docs, _ = salida_ejemplo
    for d in docs:
        txt = texto_pdf(out / d["id"] / "informe.pdf")
        m = re.search(r"Score AgroScore:\s*(\d+)/100", txt)
        assert m and int(m.group(1)) == d["score"]["valor"]
        assert len(PdfReader(str(out / d["id"] / "informe.pdf")).pages) == 4


def test_ejemplo_marcado_en_json_pdf_y_png(salida_ejemplo):
    out, docs, idx = salida_ejemplo
    assert idx["ejemplo"] is True
    for d in docs:
        assert d["ejemplo"] is True and d["fuente_datos"] == "ejemplo"
        assert any(config.AVISO_EJEMPLO in a for a in d["advertencias"])
        assert "LOTE DE EJEMPLO" in texto_pdf(out / d["id"] / "informe.pdf").upper()
        for f in ("ndvi_2025.png", "rgb_2025.png", "zonas.png", "overlay_rgb.png", "overlay_ndvi.png",
                  "overlay_ndmi.png", "overlay_zonas.png", "resumen.md"):
            assert (out / d["id"] / f).exists()


def test_cada_campania_tiene_cultivo_o_null_con_advertencia(salida_ejemplo):
    _, docs, _ = salida_ejemplo
    for d in docs:
        for c in d["campanias"]:
            if c["cultivo"] is None:
                assert any(c["campania"] in a for a in d["advertencias"])


class ProveedorMockGEE(ProveedorEjemplo):
    """MOCK (solo tests): simula el proveedor real (ejemplo=False) con huecos de datos."""
    ejemplo = False
    nombre = "gee"

    def stats_campanias(self, lote, campanias):
        st = super().stats_campanias(lote, campanias)
        st[campanias[0]] = {"ndvi_max": None, "ndvi_medio": None, "ndmi_medio": None, "pct_nubes": None,
                            "hueco_max_semanas": None}
        return st

    def suelo(self, lote):
        return {"arcilla_pct": None, "arena_pct": None, "carbono_org": None, "fuente": "SoilGrids"}


def test_pipeline_real_sin_aviso_y_nulls_con_advertencia(tmp_path, lotes):
    d = pipeline.procesar_lote(lotes[0], ProveedorMockGEE(), tmp_path, CAMP)
    assert d["ejemplo"] is False
    assert not any(config.AVISO_EJEMPLO in a for a in d["advertencias"])
    assert any("Polígono de ejemplo" in a for a in d["advertencias"])  # el polígono sigue siendo de ejemplo
    assert d["campanias"][0]["ndvi_max"] is None and d["campanias"][0]["ndvi_anomalia"] is None
    assert any("sin imágenes" in a for a in d["advertencias"])
    assert any("suelo" in a for a in d["advertencias"])
    assert "LOTE DE EJEMPLO – DATOS" not in texto_pdf(tmp_path / d["id"] / "informe.pdf").upper()


def test_anomalia_es_relativa_a_media_del_lote(salida_ejemplo):
    _, docs, _ = salida_ejemplo
    for d in docs:
        anom = [c["ndvi_anomalia"] for c in d["campanias"] if c["ndvi_anomalia"] is not None]
        assert abs(np.mean(anom)) < 0.002


def test_overlays_alineados_y_escalas_en_json(salida_ejemplo):
    from PIL import Image
    out, docs, _ = salida_ejemplo
    for d in docs:
        im = d["imagenes"]
        assert im["escalas"]["ndvi"] == [0.0, 1.0]
        assert d["rotacion"]["anios_recomendados"] == config.ROTACION_ANIOS_RECOMENDADOS
        tam = {Image.open(out / d["id"] / im[k]).size for k in ("overlay_rgb", "overlay_ndvi", "overlay_ndmi", "overlay_zonas")}
        assert len(tam) == 1  # misma grilla -> se superponen exacto con el mismo bbox
        assert Image.open(out / d["id"] / im["overlay_ndvi"]).getchannel("A").getextrema()[1] == 255
    # en lotes no rectangulares, lo de afuera del polígono queda transparente
    norte = next(d for d in docs if d["id"] == "ejemplo_roca_norte")
    a = Image.open(out / norte["id"] / norte["imagenes"]["overlay_ndvi"]).getchannel("A")
    assert a.getextrema() == (0, 255)
