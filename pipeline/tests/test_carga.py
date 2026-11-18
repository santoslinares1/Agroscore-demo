"""Carga de lotes desde KML / KMZ / Feature (lo que manda la web) y validación de geometría."""
import math
import zipfile

import pytest

from tests.conftest import DATA
from agroscore import aoi

RAIZ_DATA = DATA / "ejemplo_carga.kml"


def cuadrado_txt(lon=-63.7, lat=-33.35, lado_m=800):
    dy = lado_m / 111_320
    dx = lado_m / (111_320 * math.cos(math.radians(lat)))
    pts = [(lon, lat), (lon + dx, lat), (lon + dx, lat + dy), (lon, lat + dy), (lon, lat)]
    return " ".join(f"{x},{y},0" for x, y in pts)


def kml(cuerpo, ns='xmlns="http://www.opengis.net/kml/2.2"'):
    return f'<?xml version="1.0"?><kml {ns}><Document>{cuerpo}</Document></kml>'


def pm(nombre, coords):
    return (f"<Placemark><name>{nombre}</name><Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}"
            "</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>")


def test_kml_de_ejemplo_del_repo_con_multigeometry():
    lotes = aoi.cargar(RAIZ_DATA)
    assert [l.nombre for l in lotes] == ["EJEMPLO Lote A", "EJEMPLO Campo B (1)", "EJEMPLO Campo B (2)"]
    assert len({l.id for l in lotes}) == 3
    assert all(20 < l.area_ha < 70 for l in lotes)
    assert all("EJEMPLO" in l.fuente.upper() for l in lotes)


@pytest.mark.parametrize("ns", ['xmlns="http://www.opengis.net/kml/2.2"', 'xmlns="http://earth.google.com/kml/2.1"', ""])
def test_kml_sin_depender_del_namespace(ns):
    lotes = aoi.leer_kml(kml(pm("Lote Ñandú 3", cuadrado_txt()), ns))
    assert len(lotes) == 1
    assert lotes[0].id == "lote_lote_nandu_3"
    assert lotes[0].area_ha == pytest.approx(64, rel=0.02)
    assert lotes[0].anillo[0] == lotes[0].anillo[-1]


def test_kml_cierra_anillo_abierto_y_nombres_repetidos():
    abierto = " ".join(cuadrado_txt().split()[:-1])
    lotes = aoi.leer_kml(kml(pm("A", abierto) + pm("A", cuadrado_txt(lon=-63.6))))
    assert lotes[0].anillo[0] == lotes[0].anillo[-1]
    assert lotes[0].id != lotes[1].id


def test_kml_sin_poligonos_o_invalido():
    with pytest.raises(aoi.AOIError, match="no tiene polígonos"):
        aoi.leer_kml(kml("<Placemark><Point><coordinates>-63.7,-33.3</coordinates></Point></Placemark>"))
    with pytest.raises(aoi.AOIError, match="XML"):
        aoi.leer_kml("<kml><Document>")


def test_kmz(tmp_path):
    p = tmp_path / "campo.kmz"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("doc.kml", kml(pm("Del KMZ", cuadrado_txt())))
        z.writestr("files/foto.jpg", b"\xff\xd8")
    lotes = aoi.cargar(p)
    assert lotes[0].nombre == "Del KMZ" and "KMZ" in lotes[0].fuente


def test_kmz_roto_o_sin_kml(tmp_path):
    roto = tmp_path / "roto.kmz"
    roto.write_bytes(b"no es zip")
    with pytest.raises(aoi.AOIError, match="KMZ"):
        aoi.cargar(roto)
    vacio = tmp_path / "vacio.kmz"
    with zipfile.ZipFile(vacio, "w") as z:
        z.writestr("leeme.txt", "hola")
    with pytest.raises(aoi.AOIError, match="no contiene"):
        aoi.cargar(vacio)


def test_autointerseccion_mono_rechazado():
    mono = [[-63.70, -33.35], [-63.69, -33.36], [-63.69, -33.35], [-63.70, -33.36], [-63.70, -33.35]]
    assert aoi.autointerseccion(mono) is not None
    with pytest.raises(aoi.AOIError, match="se cruza"):
        aoi._validar_anillo(mono, "x")


def test_poligono_concavo_valido_no_es_autointerseccion():
    L = [[-63.70, -33.35], [-63.68, -33.35], [-63.68, -33.355], [-63.69, -33.355], [-63.69, -33.36],
         [-63.70, -33.36], [-63.70, -33.35]]
    assert aoi.autointerseccion(L) is None
    assert aoi._validar_anillo(L, "L")


def test_vertices_repetidos_y_area_fuera_de_rango():
    with pytest.raises(aoi.AOIError, match="distintos"):
        aoi._validar_anillo([[-63.7, -33.3], [-63.7, -33.3], [-63.6, -33.3], [-63.7, -33.3]], "x")
    chico = [[-63.7, -33.3], [-63.7001, -33.3], [-63.7001, -33.3001], [-63.7, -33.3]]
    with pytest.raises(aoi.AOIError, match="fuera de rango"):
        aoi._validar_anillo(chico, "x")


def test_feature_como_lo_exporta_la_web():
    coords = [[float(a) for a in t.split(",")[:2]] for t in cuadrado_txt().split()]
    feat = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {"id": "cargado_lote_4_ab12", "nombre": "Lote 4", "localidad": "Sin especificar",
                           "fuente": "Cargado en la demo web (dibujo) el 2026-11-16", "propietario": None,
                           "notas_cultivo": "maní 23/24"}}
    l = aoi.lote_desde_feature(feat)
    assert l.id == "cargado_lote_4_ab12" and l.extra["notas_cultivo"] == "maní 23/24"
    feat["geometry"]["type"] = "MultiPolygon"
    with pytest.raises(aoi.AOIError, match="solo se admite Polygon"):
        aoi.lote_desde_feature(feat)
