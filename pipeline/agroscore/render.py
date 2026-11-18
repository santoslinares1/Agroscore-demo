"""Render de PNGs de mapas: 1000 px de lado, escala FIJA (NDVI 0–1), barra de
colores/leyenda, contorno del lote, fecha e índice escritos en la imagen."""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from PIL import Image  # noqa: E402

from . import config  # noqa: E402

ZONAS_COLORES = ["#d7301f", "#fdcc8a", "#1a9641"]  # baja, media, alta
ZONAS_NOMBRES = ["Baja", "Media", "Alta"]
DPI = 100


def _figura(bbox, ancho_ax: float = 0.80):
    lat0 = (bbox[1] + bbox[3]) / 2
    fig = plt.figure(figsize=(config.RENDER_LADO_PX / DPI, config.RENDER_LADO_PX / DPI), dpi=DPI)
    ax = fig.add_axes([0.08, 0.12, ancho_ax, 0.78])
    ax.set_aspect(1 / math.cos(math.radians(lat0)))
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])
    ax.tick_params(labelsize=8)
    ax.ticklabel_format(useOffset=False)
    return fig, ax


def _comun(fig, ax, anillo, titulo: str, subtitulo: str, ejemplo: bool):
    xs, ys = zip(*anillo)
    ax.plot(xs, ys, color="black", lw=2.2)
    ax.plot(xs, ys, color="white", lw=0.8, ls="--")
    fig.text(0.06, 0.955, titulo, fontsize=17, weight="bold")
    fig.text(0.06, 0.925, subtitulo, fontsize=11, color="#333")
    fig.text(0.06, 0.03, "AgroScore · Sentinel-2 (Copernicus) · EPSG:4326", fontsize=8, color="#666")
    if ejemplo:
        fig.text(0.5, 0.5, config.AVISO_EJEMPLO, fontsize=20, color="#b00020", alpha=0.35,
                 ha="center", va="center", rotation=30, weight="bold")
        fig.text(0.5, 0.07, config.AVISO_EJEMPLO.upper(), fontsize=12, color="white", ha="center",
                 bbox=dict(facecolor="#b00020", edgecolor="none", pad=4), weight="bold")


def _guardar(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def render_ndvi(ndvi: np.ndarray, bbox, anillo, fecha: str, lote_nombre: str, path: Path, ejemplo: bool,
                indice: str = "NDVI"):
    fig, ax = _figura(bbox)
    cmap = plt.get_cmap("RdYlGn").with_extremes(bad=(0, 0, 0, 0))
    im = ax.imshow(np.ma.masked_invalid(ndvi), extent=[bbox[0], bbox[2], bbox[1], bbox[3]],
                   cmap=cmap, vmin=config.NDVI_ESCALA[0], vmax=config.NDVI_ESCALA[1],
                   interpolation="nearest", origin="upper")
    fig.canvas.draw()
    pos = ax.get_position()
    cax = fig.add_axes([pos.x1 + 0.02, pos.y0, 0.025, pos.height])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label(f"{indice} (escala fija {config.NDVI_ESCALA[0]:.0f}–{config.NDVI_ESCALA[1]:.0f})")
    _comun(fig, ax, anillo, f"{lote_nombre} · {indice} máximo", f"{indice} · {fecha}", ejemplo)
    _guardar(fig, path)


def render_rgb(rgb: np.ndarray, bbox, anillo, fecha: str, lote_nombre: str, path: Path, ejemplo: bool):
    fig, ax = _figura(bbox)
    ax.imshow(estirar_rgb(rgb), extent=[bbox[0], bbox[2], bbox[1], bbox[3]], interpolation="nearest",
              origin="upper")
    _comun(fig, ax, anillo, f"{lote_nombre} · color natural", f"RGB (B4-B3-B2) · {fecha}", ejemplo)
    _guardar(fig, path)


def render_zonas(mapa: np.ndarray, bbox, anillo, pcts: dict, periodo: str, lote_nombre: str, path: Path,
                 ejemplo: bool):
    fig, ax = _figura(bbox, ancho_ax=0.68)
    cmap = ListedColormap(ZONAS_COLORES).with_extremes(bad=(0, 0, 0, 0))
    ax.imshow(np.ma.masked_less(mapa, 0), extent=[bbox[0], bbox[2], bbox[1], bbox[3]], cmap=cmap,
              vmin=-0.5, vmax=2.5, interpolation="nearest", origin="upper")
    handles = [Patch(color=ZONAS_COLORES[i], label=f"{ZONAS_NOMBRES[i]} ({pcts[k]}%)")
               for i, k in enumerate(["baja_pct", "media_pct", "alta_pct"])]
    ax.legend(handles=handles[::-1], loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=10,
              title="Zona", frameon=False)
    _comun(fig, ax, anillo, f"{lote_nombre} · zonas de productividad",
           f"k-means (k=3) sobre NDVI máximo multianual · {periodo}", ejemplo)
    _guardar(fig, path)


def estirar_rgb(rgb: np.ndarray) -> np.ndarray:
    out = np.nan_to_num(rgb.astype(float), nan=0.0)
    validos = out[np.isfinite(rgb).all(axis=-1)]
    if validos.size:
        lo, hi = np.percentile(validos, 2), np.percentile(validos, 98)
        out = np.clip((out - lo) / max(hi - lo, 1e-6), 0, 1)
    return out


def overlay_rgb(rgb: np.ndarray, path: Path):
    """PNG crudo (sin ejes) para superponer en Leaflet con el bbox; transparente fuera del lote."""
    est = estirar_rgb(rgb)
    alfa = np.isfinite(rgb).all(axis=-1).astype(float)
    img = np.dstack([est, alfa])
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((img * 255).astype("uint8"), "RGBA").save(path)


def overlay_indice(arr: np.ndarray, escala: tuple[float, float], path: Path, cmap: str = "RdYlGn"):
    """PNG RGBA crudo (sin ejes) del índice con escala FIJA, transparente fuera del lote (para Leaflet)."""
    cm = plt.get_cmap(cmap)
    norm = np.clip((np.nan_to_num(arr, nan=escala[0]) - escala[0]) / (escala[1] - escala[0]), 0, 1)
    rgba = cm(norm)
    rgba[..., 3] = np.isfinite(arr).astype(float)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((rgba * 255).astype("uint8"), "RGBA").save(path)


def overlay_zonas(mapa: np.ndarray, path: Path):
    """PNG RGBA de zonas (baja/media/alta) transparente fuera del lote."""
    colores = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] + [255] for c in ZONAS_COLORES], dtype="uint8")
    out = np.zeros(mapa.shape + (4,), dtype="uint8")
    for j in range(3):
        out[mapa == j] = colores[j]
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, "RGBA").save(path)
