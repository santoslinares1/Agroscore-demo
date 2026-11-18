from agroscore.crops import cultivo_dominante, cultivos_por_campania, derivar_rotacion


def test_dominante_y_mixto():
    assert cultivo_dominante({"mani": 70, "soja": 30}) == ("mani", 0.7)
    assert cultivo_dominante({"mani": 50, "soja": 30, "maiz": 20}) == ("mixto", 0.5)
    assert cultivo_dominante({}) == (None, 0.0)


def _c(lista):
    return [{"campania": f"{2017 + i}/{str(2018 + i)[-2:]}", "cultivo": c} for i, c in enumerate(lista)]


def test_rotacion_mani_reciente():
    r = derivar_rotacion(_c(["soja", "mani", "maiz", "mani", "soja", "mani"]))
    assert r["ultimo_mani"] == "2022/23"
    assert r["campanias_desde_mani"] == 0
    assert r["veces_mani_ultimas_5"] == 3


def test_rotacion_sin_mani_y_sin_datos():
    r = derivar_rotacion(_c([None, "soja", None, "maiz"]))
    assert r["ultimo_mani"] is None and r["campanias_desde_mani"] is None
    assert r["campanias_sin_dato_ultimas_5"] == 2


class FuenteFalsa:  # MOCK (solo tests)
    def __init__(self, nombre, datos):
        self.nombre, self.datos = nombre, datos

    def histograma(self, lote, campania):
        return self.datos.get(campania)


def test_fuentes_en_orden_y_null_con_advertencia():
    idecor = FuenteFalsa("IDECOR", {"2024/25": {"mani": 90, "soja": 10}})
    mb = FuenteFalsa("MapBiomas", {"2023/24": {"soja": 100}})
    res, adv = cultivos_por_campania(None, ["2022/23", "2023/24", "2024/25"], [idecor, mb])
    assert res["2024/25"] == {"cultivo": "mani", "cultivo_fuente": "IDECOR", "cultivo_cobertura": 0.9}
    assert res["2023/24"]["cultivo_fuente"] == "MapBiomas"
    assert res["2022/23"]["cultivo"] is None
    assert any("2022/23" in a for a in adv)


# --- Campañas sin dato / indeterminadas no son "sin maní" ---------------------------------

from agroscore import config, score  # noqa: E402
from agroscore.crops import estado_mani  # noqa: E402


def test_estado_mani():
    assert estado_mani("mani") == "mani"
    assert estado_mani("soja") == "no_mani"
    assert estado_mani("pastura") == "no_mani"
    for ind in (None, "mixto", "agricultura", "cultivo_temporario", "otros_posible_mani", "mosaico_agropecuario"):
        assert estado_mani(ind) == "sin_dato"


def test_rotacion_none_no_cuenta_como_sin_mani():
    # maní hace 4 campañas pero las 2 últimas sin dato: la racha confirmada es 0, no 4
    r = derivar_rotacion(_c(["soja", "mani", "maiz", "soja", None, None]))
    assert r["campanias_desde_mani"] == 4
    assert r["campanias_sin_mani_confirmadas"] == 0
    assert r["campanias_con_dato_ultimas_5"] == 3 and r["campanias_ventana"] == 5
    assert r["cobertura_rotacion"] == 0.6 and r["confianza_rotacion"] == "parcial"


def test_rotacion_cobertura_insuficiente():
    r = derivar_rotacion(_c(["soja", "maiz", None, "agricultura", None, "mixto"]))
    assert r["campanias_con_dato_ultimas_5"] == 1  # solo "maiz"
    assert r["confianza_rotacion"] == "insuficiente"
    assert r["ultimo_mani"] is None


def test_rotacion_completa():
    r = derivar_rotacion(_c(["soja", "maiz", "soja", "maiz", "soja"]))
    assert r["confianza_rotacion"] == "completa" and r["campanias_sin_mani_confirmadas"] == 5
    assert r["cobertura_rotacion"] == 1.0


def test_racha_se_corta_en_dato_faltante():
    r = derivar_rotacion(_c(["mani", "soja", None, "maiz", "soja"]))
    assert r["campanias_sin_mani_confirmadas"] == 2
    assert r["campanias_desde_mani"] == 4


class FuenteGenerica:  # MOCK: fuente que no distingue maní
    nombre = "MapBiomas"
    distingue_mani = False

    def __init__(self, datos):
        self.datos = datos

    def histograma(self, lote, campania):
        return self.datos.get(campania)


def test_fuente_sin_mani_nunca_dice_mani_ni_sin_mani():
    f = FuenteGenerica({"2023/24": {"cultivo_temporario": 90, "pastura": 10}, "2024/25": {"mani": 100}})
    res, adv = cultivos_por_campania(None, ["2023/24", "2024/25"], [f])
    assert res["2023/24"]["cultivo"] == "cultivo_temporario"
    assert res["2024/25"]["cultivo"] == "agricultura"  # degradado: la fuente no puede afirmar maní
    assert sum("no permite descartar maní" in a for a in adv) == 2
    rot = derivar_rotacion([{"campania": c, **v} for c, v in res.items()])
    assert rot["campanias_con_dato_ultimas_5"] == 0 and rot["confianza_rotacion"] == "insuficiente"
    assert score.rotacion_mani(rot) is None  # sin dato, no 1.0


def test_fuente_sin_mani_clase_no_agricola_si_es_dato():
    f = FuenteGenerica({"2024/25": {"pastura": 95, "agua": 5}})
    res, _ = cultivos_por_campania(None, ["2024/25"], [f])
    assert estado_mani(res["2024/25"]["cultivo"]) == "no_mani"


def test_idecor_2223_otros_es_indeterminado():
    # En 22/23 IDECOR no separa maní: la clase 3 no puede mapearse a "otros" a secas
    assert config.IDECOR_CLASES_POR_CAMPANIA["2022/23"][3] in config.CULTIVOS_MANI_INDETERMINADO
    assert "mani" not in config.IDECOR_CLASES_POR_CAMPANIA["2022/23"].values()
    for c in ("2023/24", "2024/25", "2025/26"):
        assert config.IDECOR_CLASES_POR_CAMPANIA[c][4] == "mani" and config.IDECOR_CLASES_POR_CAMPANIA[c][3] == "soja"
    assert config.IDECOR_CLASES_POR_CAMPANIA["2017/18"][18] == "mani"


def test_mapbiomas_leyenda_verificada():
    c3, c1 = config.MAPBIOMAS_CLASES_COL3, config.MAPBIOMAS_CLASES_COL1
    assert c3[18] == "agricultura" and c3[19] == "cultivo_temporario" and c3[36] == "cultivo_perenne"
    assert c3[15] == "pastura" and c3[12] == "pastizal" and c3[24] == "urbano" and c3[33] == "agua" and c3[3] == "monte"
    assert c1[18] == "agricultura" and c1[15] == "pastura" and c1[12] == "pastizal" and c1[21] == "mosaico_agropecuario"
    assert c1[33] == "agua" and c1[3] == "monte"
    assert not ({39, 41} & set(c3)) and not ({39, 41, 19, 24} & set(c1))  # códigos inventados antes
    assert c3[4] == "monte" and c3[25] == "no_agricola" and 27 not in c3  # 27 = no observado: se ignora
    assert "mani" not in c3.values() and "mani" not in c1.values()
    assert config.MAPBIOMAS_ASSET.endswith("collection3/mapbiomas_argentina_collection3_coverage_v1")
    assert config.MAPBIOMAS_CLASES is config.MAPBIOMAS_CLASES_COL3


# --- FuenteMapBiomas con un `ee` simulado (solo tests) ----------------------------------------

import logging  # noqa: E402

import pytest  # noqa: E402


class _EEException(Exception):
    pass


class _Dato:
    def __init__(self, v):
        self.v = v

    def getInfo(self):
        if isinstance(self.v, Exception):
            raise self.v
        return self.v

    def get(self, _):
        return self

    def reduceRegion(self, *a, **k):
        return self

    def select(self, _):
        return self

    def bandNames(self):
        return _Dato(self.v["bandas"])


class _FakeEE:
    EEException = _EEException

    class Reducer:
        @staticmethod
        def frequencyHistogram():
            return None

    class Geometry:
        @staticmethod
        def Polygon(*a, **k):
            return None

    def __init__(self, bandas, hist):
        self._bandas, self._hist = bandas, hist

    def Image(self, asset):
        d = _Dato({"bandas": self._bandas})
        d.reduceRegion = lambda *a, **k: _Dato(self._hist)
        return d


class _Lote:
    geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}


@pytest.fixture
def fake_ee(monkeypatch):
    from agroscore import gee

    def _instalar(bandas, hist):
        monkeypatch.setattr(gee, "_ee", _FakeEE(bandas, hist))

    yield _instalar
    monkeypatch.setattr(gee, "_ee", None)


def test_mapbiomas_mapea_y_ignora_codigos_desconocidos(fake_ee):
    from agroscore.crops import FuenteMapBiomas

    fake_ee(["classification_2024"], {"19": 80.0, "15": 10.0, "39": 10.0})  # 39 no existe en la leyenda
    h = FuenteMapBiomas().histograma(_Lote(), "2024/25")
    assert h == {"cultivo_temporario": 80.0, "pastura": 10.0}


def test_mapbiomas_anio_sin_mapa_devuelve_none(fake_ee):
    from agroscore.crops import FuenteMapBiomas

    fake_ee(["classification_2022"], {"19": 1.0})
    assert FuenteMapBiomas().histograma(_Lote(), "2025/26") is None


def test_mapbiomas_error_ee_se_loguea(fake_ee, monkeypatch, caplog):
    from agroscore import gee
    from agroscore.crops import FuenteMapBiomas

    fake_ee(["classification_2024"], _EEException("Image asset 'x' not found"))
    with caplog.at_level(logging.WARNING, logger="agroscore"):
        assert FuenteMapBiomas().histograma(_Lote(), "2024/25") is None
    assert any("not found" in r.getMessage() for r in caplog.records)


def test_mapbiomas_error_inesperado_no_se_traga(fake_ee):
    from agroscore.crops import FuenteMapBiomas

    fake_ee(["classification_2024"], RuntimeError("bug"))
    with pytest.raises(RuntimeError):
        FuenteMapBiomas().histograma(_Lote(), "2024/25")


# --- FuenteIDECORLocal con rasters sintéticos (necesita rasterio) --------------------------------


def _tif(path, arr, nodata=None, crs="EPSG:22174"):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype=arr.dtype, crs=crs, transform=from_origin(4432000, 6311000, 10, 10),
                       nodata=nodata) as dst:
        dst.write(arr, 1)


def _lote_idecor():
    pytest.importorskip("pyproj")
    from pyproj import Transformer

    t = Transformer.from_crs(22174, 4326, always_xy=True)
    pts = [(4432100, 6310100), (4432900, 6310100), (4432900, 6310900), (4432100, 6310900), (4432100, 6310100)]

    class L:
        geometry = {"type": "Polygon", "coordinates": [[list(t.transform(x, y)) for x, y in pts]]}

    return L()


def test_idecor_local_float_nan_y_codigos_por_campania(tmp_path):
    import numpy as np

    from agroscore.crops import FuenteIDECORLocal

    a = np.full((100, 100), np.nan, dtype="float32")
    a[:, :60] = 4.0   # maní (23/24+)
    a[:, 60:90] = 3.0  # soja
    _tif(tmp_path / "idecor_2024-25.tif", a)
    h = FuenteIDECORLocal(tmp_path).histograma(_lote_idecor(), "2024/25")
    assert h and h["mani"] > h["soja"] > 0 and "otros" not in h
    assert cultivo_dominante(h)[0] in ("mani", "mixto")


def test_idecor_local_2223_clase3_no_es_mani(tmp_path):
    import numpy as np

    from agroscore.crops import FuenteIDECORLocal

    a = np.full((100, 100), 3, dtype="uint8")
    a[:, 90:] = 8  # nodata del raster 22/23
    a[:5, :5] = 33  # valor sin etiqueta: se ignora
    _tif(tmp_path / "idecor_2022-23.tif", a, nodata=8)
    h = FuenteIDECORLocal(tmp_path).histograma(_lote_idecor(), "2022/23")
    assert set(h) == {"otros_posible_mani"}
    res, adv = cultivos_por_campania(_lote_idecor(), ["2022/23"], [FuenteIDECORLocal(tmp_path)])
    assert estado_mani(res["2022/23"]["cultivo"]) == "sin_dato" and adv


def test_idecor_local_sin_mapeo_o_archivo_es_none(tmp_path):
    import numpy as np

    from agroscore.crops import FuenteIDECORLocal

    _tif(tmp_path / "idecor_2019-20.tif", np.ones((10, 10), dtype="uint8"))
    f = FuenteIDECORLocal(tmp_path)
    assert f.histograma(_lote_idecor(), "2019/20") is None  # sin códigos verificados: no se inventa
    assert f.histograma(_lote_idecor(), "2024/25") is None  # sin archivo
