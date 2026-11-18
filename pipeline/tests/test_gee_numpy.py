"""a_numpy: los píxeles fuera del polígono deben salir NaN (no 0). Regresión de un bug visto en GEE real:
`unmask(-9999)` con sameFootprint=True (default) dejaba 0 fuera del lote y el k-means de zonas los tomaba como NDVI 0."""
import numpy as np

from agroscore import gee


class _Img:
    def __init__(self):
        self.llamadas = []

    def select(self, _):
        return self

    def clip(self, _):
        return self

    def unmask(self, *args):
        self.llamadas.append(args)
        return self


class _Region:
    def bounds(self, _):
        return self

    def coordinates(self):
        return self

    def get(self, _):
        return self

    def getInfo(self):
        return [[-63.0, -33.0], [-62.99, -33.0], [-62.99, -32.99], [-63.0, -32.99]]


class _Data:
    def computePixels(self, req):
        self.req = req
        w, h = req["grid"]["dimensions"]["width"], req["grid"]["dimensions"]["height"]
        a = np.full((h, w), 0.8, dtype="float32")
        a[0, 0] = -9999
        return {"NDVI": a}


class _EE:
    data = _Data()


def test_a_numpy_unmask_sin_mismo_footprint_y_nan(monkeypatch):
    monkeypatch.setattr(gee, "_ee", _EE())
    img = _Img()
    out, bbox = gee.a_numpy(img, _Region(), ["NDVI"], 10)
    assert img.llamadas == [(-9999, False)]
    assert np.isnan(out[0, 0, 0]) and np.isfinite(out[1, 1, 0])
    assert bbox == [-63.0, -33.0, -62.99, -32.99]
