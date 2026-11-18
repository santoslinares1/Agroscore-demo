import json
import math

import pytest

from tests.conftest import DATA
from agroscore import aoi


def cuadrado(lat=-33.35, lon=-63.7, lado_m=1000):
    dy = lado_m / 111_320
    dx = lado_m / (111_320 * math.cos(math.radians(lat)))
    return [[lon, lat], [lon + dx, lat], [lon + dx, lat + dy], [lon, lat + dy], [lon, lat]]


def test_area_cuadrado_100ha():
    assert aoi.area_m2(cuadrado()) / 10_000 == pytest.approx(100, rel=0.01)


def test_cargar_geojson_lotes_del_repo():
    lotes = aoi.cargar(DATA / "lotes.geojson")
    assert len(lotes) == 3
    for l in lotes:
        assert 30 <= l.area_ha <= 200
        assert -34 < l.centroide[1] < -33 and -64.5 < l.centroide[0] < -63.5
        assert "EJEMPLO" in l.fuente.upper()


def _fc(props, ring):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}}]}


def test_faltan_propiedades(tmp_path):
    p = tmp_path / "x.geojson"
    p.write_text(json.dumps(_fc({"id": "a"}, cuadrado())))
    with pytest.raises(aoi.AOIError):
        aoi.cargar_geojson(p)


def test_cierra_anillo_y_rechaza_coordenadas_invertidas(tmp_path):
    props = {"id": "a", "nombre": "A", "localidad": "X", "fuente": "test"}
    ring = cuadrado()[:-1]
    p = tmp_path / "ok.geojson"
    p.write_text(json.dumps(_fc(props, ring)))
    l = aoi.cargar_geojson(p)[0]
    assert l.anillo[0] == l.anillo[-1]
    malo = [[y, x * 3] for x, y in cuadrado()]
    p2 = tmp_path / "mal.geojson"
    p2.write_text(json.dumps(_fc(props, malo)))
    with pytest.raises(aoi.AOIError):
        aoi.cargar_geojson(p2)
