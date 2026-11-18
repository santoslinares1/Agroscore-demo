"""Zonas intralote: k-means k=3 sobre NDVI máximo multianual (notebook 07).

Clusters ordenados por NDVI medio -> Alta / Media / Baja.
"""
from __future__ import annotations

import numpy as np

ETIQUETAS = ("baja", "media", "alta")  # índice 0,1,2 tras ordenar por media


def kmeans_1d(valores: np.ndarray, k: int = 3, iters: int = 50, semilla: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """k-means determinístico en 1D (init por cuantiles). Devuelve (etiquetas, centros)."""
    v = np.asarray(valores, dtype=float)
    centros = np.quantile(v, np.linspace(0.15, 0.85, k))
    etiquetas = np.zeros(len(v), dtype=int)
    for _ in range(iters):
        nuevas = np.argmin(np.abs(v[:, None] - centros[None, :]), axis=1)
        nuevos_c = np.array([v[nuevas == j].mean() if np.any(nuevas == j) else centros[j] for j in range(k)])
        if np.array_equal(nuevas, etiquetas) and np.allclose(nuevos_c, centros):
            break
        etiquetas, centros = nuevas, nuevos_c
    orden = np.argsort(centros)
    remap = np.empty(k, dtype=int)
    remap[orden] = np.arange(k)
    return remap[etiquetas], centros[orden]


def zonificar(ndvi: np.ndarray) -> dict:
    """ndvi: array 2D con NaN fuera del lote.

    Devuelve {'mapa': array 2D (0 baja, 1 media, 2 alta, -1 fuera), 'alta_pct', ...}.
    Los porcentajes suman 100 (se ajusta el redondeo en la clase mayor).
    """
    mask = np.isfinite(ndvi)
    if mask.sum() < 3:
        return {"mapa": np.full(ndvi.shape, -1), "alta_pct": None, "media_pct": None, "baja_pct": None,
                "centros": None}
    etq, centros = kmeans_1d(ndvi[mask], 3)
    mapa = np.full(ndvi.shape, -1, dtype=int)
    mapa[mask] = etq
    n = mask.sum()
    pct = [100 * np.sum(etq == j) / n for j in range(3)]
    red = [int(round(p)) for p in pct]
    red[int(np.argmax(pct))] += 100 - sum(red)
    return {"mapa": mapa, "baja_pct": red[0], "media_pct": red[1], "alta_pct": red[2],
            "centros": [round(float(c), 3) for c in centros]}
