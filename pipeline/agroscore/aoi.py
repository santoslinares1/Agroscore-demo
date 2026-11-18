"""Carga y validación de lotes (AOI): GeoJSON, KML o KMZ; área en ha y centroide."""
from __future__ import annotations

import json
import math
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

R_TIERRA_M = 6_378_137.0
PROPIEDADES_REQUERIDAS = ("id", "nombre", "localidad", "fuente")


class AOIError(ValueError):
    pass


@dataclass
class Lote:
    id: str
    nombre: str
    localidad: str
    fuente: str
    anillo: list[list[float]]  # [[lon, lat], ...] cerrado
    extra: dict = field(default_factory=dict)

    @property
    def geometry(self) -> dict:
        return {"type": "Polygon", "coordinates": [self.anillo]}

    @property
    def area_ha(self) -> float:
        return round(area_m2(self.anillo) / 10_000, 1)

    @property
    def centroide(self) -> list[float]:
        return centroide(self.anillo)

    @property
    def bbox(self) -> list[float]:
        lons = [p[0] for p in self.anillo]
        lats = [p[1] for p in self.anillo]
        return [min(lons), min(lats), max(lons), max(lats)]


def area_m2(anillo: list[list[float]]) -> float:
    """Área geodésica aproximada (esfera) de un anillo lon/lat, en m²."""
    if len(anillo) < 4:
        return 0.0
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(anillo[:-1], anillo[1:]):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total * R_TIERRA_M ** 2 / 2.0)


def centroide(anillo: list[list[float]]) -> list[float]:
    """Centroide planar del polígono (suficiente para lotes de < 10 km)."""
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(anillo[:-1], anillo[1:]):
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    if a == 0:
        xs, ys = zip(*anillo)
        return [round(sum(xs) / len(xs), 5), round(sum(ys) / len(ys), 5)]
    a *= 0.5
    return [round(cx / (6 * a), 5), round(cy / (6 * a), 5)]


def _cruzan(p1, p2, p3, p4) -> bool:
    """¿Se cruzan los segmentos p1-p2 y p3-p4 (incluye toques y solapes colineales)?"""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-18 else (1 if v > 0 else -1)

    def sobre(a, b, c):
        return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])
    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    return ((o1 == 0 and sobre(p1, p2, p3)) or (o2 == 0 and sobre(p1, p2, p4))
            or (o3 == 0 and sobre(p3, p4, p1)) or (o4 == 0 and sobre(p3, p4, p2)))


def autointerseccion(anillo: list[list[float]]) -> tuple[int, int] | None:
    """Devuelve el primer par de lados (no contiguos) que se cruzan, o None. O(n²): sobra para lotes."""
    lados = list(zip(anillo[:-1], anillo[1:]))
    n = len(lados)
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue  # lados contiguos comparten vértice
            if _cruzan(*lados[i], *lados[j]):
                return i, j
    return None


def _validar_anillo(anillo: list, lote_id: str) -> list[list[float]]:
    pts = [[float(p[0]), float(p[1])] for p in anillo]
    if len(pts) < 3:
        raise AOIError(f"{lote_id}: el polígono necesita al menos 3 vértices")
    if pts[0] != pts[-1]:
        pts.append(list(pts[0]))
    for lon, lat in pts:
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise AOIError(f"{lote_id}: coordenada fuera de rango ({lon}, {lat}); ¿está en EPSG:4326?")
    if len({(p[0], p[1]) for p in pts[:-1]}) < 3:
        raise AOIError(f"{lote_id}: el polígono necesita al menos 3 vértices distintos")
    cruce = autointerseccion(pts)
    if cruce:
        raise AOIError(f"{lote_id}: el contorno se cruza a sí mismo (lados {cruce[0] + 1} y {cruce[1] + 1}); "
                       "corregí el dibujo para que no forme un «moño»")
    ha = area_m2(pts) / 10_000
    if ha < 1 or ha > 20_000:
        raise AOIError(f"{lote_id}: área {ha:.1f} ha fuera de rango razonable (1–20.000 ha)")
    return pts


def cargar_geojson(path: str | Path) -> list[Lote]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AOIError(f"GeoJSON inválido: {exc}") from exc
    return cargar_geojson_obj(data)


def cargar_geojson_obj(data: dict) -> list[Lote]:
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise AOIError("Se espera un FeatureCollection")
    lotes: list[Lote] = []
    ids: set[str] = set()
    for i, feat in enumerate(data.get("features", [])):
        props = feat.get("properties") or {}
        faltan = [k for k in PROPIEDADES_REQUERIDAS if not props.get(k)]
        if faltan:
            raise AOIError(f"feature #{i}: faltan propiedades {faltan}")
        geom = feat.get("geometry") or {}
        if not isinstance(geom.get("coordinates"), list) or not geom["coordinates"]:
            raise AOIError(f"{props['id']}: geometría sin coordenadas")
        if geom.get("type") != "Polygon":
            raise AOIError(f"{props['id']}: solo se admite Polygon (no {geom.get('type')})")
        if props["id"] in ids:
            raise AOIError(f"id duplicado: {props['id']}")
        ids.add(props["id"])
        anillo = _validar_anillo(geom["coordinates"][0], props["id"])
        extra = {k: v for k, v in props.items() if k not in PROPIEDADES_REQUERIDAS}
        lotes.append(Lote(props["id"], props["nombre"], props["localidad"], props["fuente"], anillo, extra))
    if not lotes:
        raise AOIError("El archivo no tiene lotes")
    return lotes


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:40] or "lote"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _hijos(el, nombre: str):
    return [c for c in el.iter() if _local(c.tag) == nombre]


def _coords(texto: str) -> list[list[float]]:
    pts = []
    for tupla in texto.split():
        partes = tupla.split(",")
        if len(partes) >= 2:
            pts.append([float(partes[0]), float(partes[1])])
    return pts


def leer_kml(texto: bytes | str, localidad: str = "Sin especificar", fuente: str = "KML") -> list[Lote]:
    """Lee los Polygon de cada Placemark (también dentro de MultiGeometry) de un KML.

    No depende del namespace (KML 2.2, Google Earth 'gx', o sin namespace). Cada polígono
    se valida (cerrado, sin autointersección, 1–20.000 ha). Los huecos (innerBoundaryIs) se ignoran.
    """
    try:
        root = ET.fromstring(texto)
    except ET.ParseError as exc:
        raise AOIError(f"El KML no es un XML válido: {exc}") from exc
    lotes: list[Lote] = []
    ids: set[str] = set()
    n = 0
    for pm in _hijos(root, "Placemark"):
        nombre_el = next((c for c in pm if _local(c.tag) == "name"), None)
        base = (nombre_el.text or "").strip() if nombre_el is not None else ""
        polis = _hijos(pm, "Polygon")
        for k, poly in enumerate(polis):
            outer = next(iter(_hijos(poly, "outerBoundaryIs")), None)
            coords = next(iter(_hijos(outer, "coordinates")), None) if outer is not None else None
            if coords is None or not (coords.text or "").strip():
                continue
            n += 1
            nombre = base or f"Lote {n}"
            if len(polis) > 1:
                nombre = f"{nombre} ({k + 1})"
            lid = "lote_" + slug(nombre)
            while lid in ids:
                lid += "_b"
            ids.add(lid)
            lotes.append(Lote(lid, nombre, localidad, fuente, _validar_anillo(_coords(coords.text), lid)))
    if not lotes:
        raise AOIError("El KML no tiene polígonos (Placemark con Polygon). Las líneas o puntos no sirven como lote.")
    return lotes


def cargar_kml(path: str | Path, localidad: str = "Sin especificar", fuente: str | None = None) -> list[Lote]:
    p = Path(path)
    return leer_kml(p.read_bytes(), localidad, fuente or f"KML {p.name}")


def cargar_kmz(path: str | Path, localidad: str = "Sin especificar", fuente: str | None = None) -> list[Lote]:
    """KMZ = zip con un .kml adentro (Google Earth usa doc.kml)."""
    p = Path(path)
    try:
        with zipfile.ZipFile(p) as z:
            kmls = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not kmls:
                raise AOIError("El KMZ no contiene ningún .kml")
            nombre = "doc.kml" if "doc.kml" in kmls else kmls[0]
            return leer_kml(z.read(nombre), localidad, fuente or f"KMZ {p.name}")
    except zipfile.BadZipFile as exc:
        raise AOIError(f"{p.name} no es un KMZ válido (zip dañado)") from exc


def cargar(path: str | Path) -> list[Lote]:
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".kml":
        return cargar_kml(p)
    if suf == ".kmz":
        return cargar_kmz(p)
    return cargar_geojson(p)


def lote_desde_feature(feat: dict) -> Lote:
    """Un Feature GeoJSON (como lo exporta la web) -> Lote validado."""
    return cargar_geojson_obj({"type": "FeatureCollection", "features": [feat]})[0]
