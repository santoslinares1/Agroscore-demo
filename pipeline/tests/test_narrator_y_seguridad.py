import re
from pathlib import Path

import pytest

from agroscore import narrator

_PIPELINE = Path(__file__).resolve().parents[1]
# raíz del monorepo si existe (pipeline/ + web/); si no, solo pipeline/ (tests ejecutables aislados)
RAIZ = _PIPELINE.parent if (_PIPELINE.parent / "web").is_dir() else _PIPELINE


def test_claude_sin_clave_falla_explicito(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        narrator.resumen_claude({}, Path("."))


def test_plantilla_usa_numeros_del_json():
    lote = {"nombre": "L", "area_ha": 100.0, "localidad": "X", "ejemplo": False,
            "score": {"valor": 77, "componentes": [{"clave": "estabilidad", "valor": 0.8}]},
            "rotacion": {"ultimo_mani": None, "campanias_desde_mani": None, "veces_mani_ultimas_5": 0},
            "zonas": {"alta_pct": 40, "media_pct": 35, "baja_pct": 25},
            "agua": {"max_ha_anegadas": None, "fecha_max": None, "frecuencia_pct": 1.5},
            "campanias": [{"ndvi_max": 0.8}, {"ndvi_max": 0.7}]}
    t = narrator.resumen_plantilla(lote)
    assert "77/100" in t and "sin dato" in t and "LOTE DE EJEMPLO" not in t


def test_sin_claves_en_el_proyecto():
    patron = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{10,}|AIza[0-9A-Za-z_\-]{30,}|ghp_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY)")
    for p in RAIZ.rglob("*"):
        if p.is_file() and p.suffix in {".py", ".ts", ".json", ".md", ".txt", ".html", ".sh", ".env", ".js"} \
                and not any(x in p.parts for x in ("node_modules", ".venv", "dist", "out")):
            assert not patron.search(p.read_text(errors="ignore")), p
