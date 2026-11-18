"""Proveedor de DATOS DE EJEMPLO (sintéticos, determinísticos por id de lote).

Sirve para tener una demo navegable sin cuenta de Earth Engine. Todo lo que sale
de acá lleva `"ejemplo": true` y el aviso "LOTE DE EJEMPLO – datos de ejemplo"
en la web y el PDF. NUNCA presentar estos números como reales.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
from matplotlib.path import Path as MplPath

FUENTE_CULTIVO = "EJEMPLO"

# Rotaciones sintéticas por lote (vieja -> nueva). None = campaña sin mapa.
_ROTACIONES = {
    "ejemplo_roca_norte": [None, "soja", "maiz", "mani", "soja", "maiz", "soja", "maiz", "soja"],
    "ejemplo_roca_sur": [None, "maiz", "soja", "maiz", "mani", "soja", "mani", "maiz", "mani"],
    "ejemplo_rio_cuarto_este": [None, "mani", "soja", "maiz", "soja", "mixto", "maiz", "soja", "maiz"],
}
_ROT_DEFAULT = [None, "soja", "maiz", "soja", "mani", "maiz", "soja", "maiz", "soja"]

_NDVI_CULTIVO = {"maiz": 0.86, "soja": 0.84, "mani": 0.78, "mixto": 0.80, None: 0.80}
# Campañas secas plausibles (2017/18 y 2022/23 fueron años de sequía en la región).
_CAMPANIA_SECA = {"2017/18": -0.10, "2022/23": -0.16, "2020/21": -0.04}


def _rng(*partes: str) -> np.random.Generator:
    h = hashlib.sha256("|".join(partes).encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "little"))


def _grilla(lote, escala_m: float = 10.0):
    minx, miny, maxx, maxy = lote.bbox
    lat0 = (miny + maxy) / 2
    dy = escala_m / 111_320.0
    dx = escala_m / (111_320.0 * math.cos(math.radians(lat0)))
    w = max(2, int(round((maxx - minx) / dx)))
    h = max(2, int(round((maxy - miny) / dy)))
    xs = minx + (np.arange(w) + 0.5) * (maxx - minx) / w
    ys = maxy - (np.arange(h) + 0.5) * (maxy - miny) / h
    X, Y = np.meshgrid(xs, ys)
    dentro = MplPath(lote.anillo).contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(h, w)
    u = (X - minx) / (maxx - minx)
    v = (Y - miny) / (maxy - miny)
    return dentro, u, v, [minx, miny, maxx, maxy]


def _suave(rng, shape, n=6):
    """Campo suave sumando gaussianas aleatorias."""
    h, w = shape
    yy, xx = np.mgrid[0:1:complex(h), 0:1:complex(w)]
    f = np.zeros(shape)
    for _ in range(n):
        cx, cy, s, a = rng.uniform(0, 1), rng.uniform(0, 1), rng.uniform(0.12, 0.35), rng.uniform(-1, 1)
        f += a * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * s ** 2))
    return (f - f.mean()) / (f.std() + 1e-9)


class ProveedorEjemplo:
    ejemplo = True
    nombre = "ejemplo"

    def _rot(self, lote, campanias):
        rot = _ROTACIONES.get(lote.id, _ROT_DEFAULT)
        rot = (rot * 3)[-len(campanias):] if len(rot) < len(campanias) else rot[-len(campanias):]
        return dict(zip(campanias, rot))

    def stats_campanias(self, lote, campanias):
        rot = self._rot(lote, campanias)
        calidad = _rng(lote.id, "calidad").uniform(-0.05, 0.03)
        out = {}
        for c in campanias:
            r = _rng(lote.id, c)
            base = _NDVI_CULTIVO[rot[c]] + calidad + _CAMPANIA_SECA.get(c, 0) + r.normal(0, 0.015)
            ndvi_max = float(np.clip(base, 0.3, 0.95))
            out[c] = {
                "ndvi_max": round(ndvi_max, 3),
                "ndvi_medio": round(ndvi_max - r.uniform(0.18, 0.26), 3),
                "ndmi_medio": round(0.08 + (ndvi_max - 0.6) * 0.6 + r.normal(0, 0.02), 3),
                "pct_nubes": int(r.integers(6, 48)),
                "hueco_max_semanas": int(r.integers(0, 5)),
                "n_escenas": int(r.integers(14, 30)),
            }
        return out

    def cultivos(self, lote, campanias):
        rot = self._rot(lote, campanias)
        res, adv = {}, []
        for c in campanias:
            cul = rot[c]
            if cul is None:
                res[c] = {"cultivo": None, "cultivo_fuente": None, "cultivo_cobertura": None}
                adv.append(f"Campaña {c}: sin mapa de cultivo disponible (cultivo = null).")
            else:
                cob = 0.52 if cul == "mixto" else round(float(_rng(lote.id, c, "cob").uniform(0.72, 0.97)), 2)
                res[c] = {"cultivo": cul, "cultivo_fuente": FUENTE_CULTIVO, "cultivo_cobertura": cob}
        return res, adv

    def ndvi_multianual(self, lote, campanias):
        dentro, u, v, bbox = _grilla(lote)
        r = _rng(lote.id, "zonas")
        campo = 0.80 + 0.045 * _suave(r, dentro.shape) - 0.03 * (u - 0.5) + r.normal(0, 0.008, dentro.shape)
        if lote.id.endswith("sur"):  # bajo anegable sintético en el sector este-centro
            campo -= 0.12 * np.exp(-((u - 0.62) ** 2 + (v - 0.38) ** 2) / 0.025)
        campo = np.clip(campo, 0, 1).astype("float32")
        campo[~dentro] = np.nan
        return campo, bbox

    def ultima(self, lote, campania):
        multi, bbox = self.ndvi_multianual(lote, [campania])
        r = _rng(lote.id, campania, "ultima")
        ndvi = np.clip(multi + r.normal(-0.02, 0.015, multi.shape), 0, 1).astype("float32")
        g = np.clip((np.nan_to_num(ndvi, nan=0.5) - 0.2) / 0.75, 0, 1)[..., None]
        veg, suelo = np.array([0.05, 0.08, 0.04]), np.array([0.22, 0.17, 0.12])
        rgb = (g * veg + (1 - g) * suelo).astype("float32")
        rgb += r.normal(0, 0.004, rgb.shape).astype("float32")
        rgb[~np.isfinite(ndvi)] = np.nan
        y = int(campania.split("/")[0]) + 1
        return ndvi, rgb, bbox, f"{y}-02-{int(r.integers(3, 27)):02d}"

    def ndmi(self, lote, campania):
        multi, bbox = self.ndvi_multianual(lote, [campania])
        r = _rng(lote.id, campania, "ndmi")
        ndmi = 0.12 + 0.9 * (multi - 0.78) + r.normal(0, 0.012, multi.shape)
        if lote.id.endswith("sur"):
            dentro, u, v, _ = _grilla(lote)
            ndmi += 0.22 * np.exp(-((u - 0.62) ** 2 + (v - 0.38) ** 2) / 0.025)
        return np.where(np.isfinite(multi), ndmi, np.nan).astype("float32"), bbox

    def suelo(self, lote):
        r = _rng(lote.id, "suelo")
        return {"arcilla_pct": round(float(r.uniform(11, 21)), 1), "arena_pct": round(float(r.uniform(48, 66)), 1),
                "carbono_org": round(float(r.uniform(0.8, 1.4)), 1), "fuente": "SoilGrids (ejemplo)"}

    def clima(self, lote):
        r = _rng(lote.id, "clima")
        return {"pp_anual_mm": int(r.integers(740, 860)), "fuente": "ERA5 (ejemplo)"}

    def agua(self, lote):
        r = _rng(lote.id, "agua")
        area = lote.area_ha
        frac = 0.11 if lote.id.endswith("sur") else float(r.uniform(0.005, 0.03))
        return {"max_ha_anegadas": round(area * frac, 1),
                "fecha_max": f"20{int(r.integers(19, 25))}-{int(r.integers(2, 5)):02d}-{int(r.integers(1, 28)):02d}",
                "frecuencia_pct": round(9.0 if lote.id.endswith("sur") else float(r.uniform(0.5, 3.5)), 1)}
