import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Lote } from "./types";
import { url } from "./data";
import { colorScore, esc, num, textoScore } from "./fmt";

// ---------------------------------------------------------------------------
// Mapas base (requieren internet). Si fallan, la demo sigue con el lote y sus
// capas propias (PNG locales) sobre fondo liso.
// ---------------------------------------------------------------------------
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const ATR_IMG = 'Imagen © <a href="https://www.esri.com/">Esri</a> — Esri, Maxar, Earthstar Geographics y la comunidad GIS';
const ATR_TOPO = "Mapa © Esri — Esri, HERE, Garmin, FAO, NOAA, USGS y la comunidad GIS";
const ATR_OTM = 'Datos © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, SRTM · estilo © <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)';

type BaseId = "satelite" | "topo" | "relieve" | "ninguno";

function capasBase(): Record<BaseId, L.Layer> {
  return {
    satelite: L.tileLayer(`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, {
      maxNativeZoom: 17, maxZoom: 19, attribution: ATR_IMG }),
    topo: L.tileLayer(`${ESRI}/World_Topo_Map/MapServer/tile/{z}/{y}/{x}`, {
      maxNativeZoom: 17, maxZoom: 19, attribution: ATR_TOPO }),
    relieve: L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
      subdomains: "abc", maxNativeZoom: 17, maxZoom: 19, attribution: ATR_OTM }),
    ninguno: L.layerGroup(),
  };
}

const NOMBRES_BASE: Record<BaseId, string> = {
  satelite: "Satélite",
  topo: "Caminos",
  relieve: "Relieve",
  ninguno: "Sin fondo",
};

function rotulos(): L.Layer {
  return L.layerGroup([
    L.tileLayer(`${ESRI}/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}`, { maxNativeZoom: 17, maxZoom: 19, opacity: 0.8 }),
    L.tileLayer(`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`, {
      maxNativeZoom: 17, maxZoom: 19, attribution: "Rótulos © Esri" }),
  ]);
}

const latlngs = (l: Lote) => l.geometry.coordinates[0].map(([lon, lat]) => [lat, lon] as [number, number]);
export const boundsLote = (l: Lote) => L.latLngBounds(latlngs(l));

/** Contorno de alto contraste: halo oscuro + línea amarilla. */
function dibujarLote(l: Lote, grupo: L.FeatureGroup, relleno: string | null, fillOpacity: number) {
  const pts = latlngs(l);
  L.polygon(pts, { color: "#000", weight: 8, opacity: 0.55, fill: false, interactive: false }).addTo(grupo);
  return L.polygon(pts, {
    color: "#ffe14d", weight: 3.5, opacity: 1, fillColor: relleno ?? "#ffe14d",
    fillOpacity: relleno ? fillOpacity : 0, dashArray: undefined,
  }).addTo(grupo);
}

function avisoOffline(el: HTMLElement, map: L.Map) {
  if (el.querySelector(".aviso-offline")) return;
  el.classList.add("sin-tiles");
  const d = document.createElement("div");
  d.className = "aviso-offline";
  d.textContent = "Sin conexión: no se ve la foto satelital. Igual podés ver el borde del lote y sus capas.";
  el.appendChild(d);
  map.fire("sin-tiles");
}

/** Vigila un mapa base: indicador de carga y fallback offline si fallan los tiles. */
function vigilarBase(capa: L.Layer, el: HTMLElement, map: L.Map) {
  if (!(capa instanceof L.TileLayer)) return;
  let ok = 0, err = 0;
  const cargando = el.querySelector<HTMLElement>(".cargando-tiles");
  capa.on("tileload", () => { ok++; cargando?.remove(); el.classList.remove("sin-tiles"); el.querySelector(".aviso-offline")?.remove(); });
  capa.on("tileerror", () => { err++; if (err >= 3 && ok === 0) { cargando?.remove(); avisoOffline(el, map); } });
}

interface OpcionesMapa {
  modo: "inicio" | "detalle" | "mini";
  onClick?: (id: string) => void;
}

export function crearMapa(el: HTMLElement, lotes: Lote[], opts: OpcionesMapa) {
  const mini = opts.modo === "mini";
  const map = L.map(el, {
    zoomControl: false, dragging: !mini, scrollWheelZoom: opts.modo === "detalle" ? "center" : !mini,
    doubleClickZoom: !mini, boxZoom: !mini, keyboard: !mini, touchZoom: !mini, attributionControl: true,
    zoomSnap: opts.modo === "detalle" ? 0.25 : 1, zoomDelta: 0.5,
    zoomAnimation: !mini, fadeAnimation: !mini,
  });
  map.attributionControl.setPrefix(mini ? false : '<a href="https://leafletjs.com">Leaflet</a>');
  const ind = document.createElement("div");
  ind.className = "cargando-tiles";
  ind.textContent = "Cargando la foto satelital…";
  el.appendChild(ind);

  const bases = capasBase();
  const guardada = (localStorage.getItem("mapa-base") as BaseId | null) ?? "satelite";
  const inicial: BaseId = mini ? "satelite" : (guardada in bases ? guardada : "satelite");
  Object.values(bases).forEach((b) => vigilarBase(b, el, map));
  const capaRotulos = rotulos();
  if (navigator.onLine) {
    bases[inicial].addTo(map);
    if (!mini && inicial === "satelite") capaRotulos.addTo(map);
  } else {
    ind.remove();
    bases.ninguno.addTo(map);
    setTimeout(() => avisoOffline(el, map), 0);
  }

  const grupo = L.featureGroup().addTo(map);
  for (const l of lotes) {
    const relleno = opts.modo === "inicio" ? colorScore(l.score.valor) : null;
    const pol = dibujarLote(l, grupo, relleno, 0.35);
    if (!mini) {
      pol.bindTooltip(`<strong>${esc(l.nombre)}</strong><br>${l.score.valor === null ? "Sin dato suficiente" : `Puntaje ${l.score.valor} de 100`} · ${num(l.area_ha, 1)} ha` +
        (l.ejemplo ? `<br><span class="tt-ejemplo">Datos de ejemplo</span>` : ""), { sticky: true });
    }
    if (opts.onClick) pol.on("click", () => opts.onClick!(l.id));
    if (opts.modo === "inicio") {
      const m = L.marker([l.centroide[1], l.centroide[0]], {
        icon: L.divIcon({ className: "pin-lote", html: `<span style="background:${colorScore(l.score.valor)};color:${textoScore(l.score.valor)}" title="${l.score.valor === null ? "Sin dato suficiente" : ""}">${l.score.valor ?? "s/d"}</span><b>${esc(l.nombre.replace(/^Lote Ejemplo\s+/i, "").replace(/^Lote\s+/i, ""))}</b>`,
          iconSize: [0, 0] }),
        keyboard: true, title: l.nombre,
      }).addTo(grupo);
      if (opts.onClick) m.on("click", () => opts.onClick!(l.id));
    }
  }

  if (!mini) {
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.control.layers(
      Object.fromEntries((Object.keys(bases) as BaseId[]).map((k) => [NOMBRES_BASE[k], bases[k]])),
      { "Nombres y rutas": capaRotulos },
      { collapsed: true, position: "topright" },
    ).addTo(map);
    L.control.scale({ imperial: false, position: "bottomleft", maxWidth: 160 }).addTo(map);
    map.on("baselayerchange", (e: L.LayersControlEvent) => {
      const id = (Object.keys(bases) as BaseId[]).find((k) => bases[k] === e.layer);
      if (id) localStorage.setItem("mapa-base", id);
    });
  }

  const encuadrar = () => {
    const b = grupo.getBounds();
    if (!b.isValid()) { map.setView([-33.4, -63.7], 6); return; }   // sin lotes válidos: vista general de Córdoba
    if (opts.modo === "inicio") map.fitBounds(b, { padding: [40, 40] });
    else map.fitBounds(b, { padding: mini ? [12, 12] : [40, 40], maxZoom: 17 });
  };
  encuadrar();
  setTimeout(() => { map.invalidateSize(); encuadrar(); }, 60);
  return {
    map,
    volarA: (id: string) => {
      const l = lotes.find((x) => x.id === id);
      if (l) map.flyToBounds(boundsLote(l), { maxZoom: 15, duration: 0.8, padding: [60, 60] });
    },
    verTodos: () => { const b = grupo.getBounds(); if (b.isValid()) map.flyToBounds(b, { padding: [40, 40], duration: 0.8 }); },
  };
}

// ---------------------------------------------------------------------------
// Capas propias del lote (NDVI, NDMI, zonas, color natural) con opacidad.
// ---------------------------------------------------------------------------
type CapaId = "ninguna" | "ndvi" | "ndmi" | "zonas" | "rgb";

export function agregarCapasLote(map: L.Map, l: Lote, el: HTMLElement, inicial: string | null = null) {
  const im = l.imagenes;
  const b = im.bbox;
  if (!b) return;
  const bounds = L.latLngBounds([[b[1], b[0]], [b[3], b[2]]]);
  const esc_ = im.escalas ?? {};
  const camp = im.campania_overlays ? ` · campaña ${im.campania_overlays}` : "";
  type Def = { id: CapaId; nombre: string; archivo?: string | null; leyenda: string };
  const todas: Def[] = [
    { id: "ninguna", nombre: "Solo la foto satelital", leyenda: "" },
    { id: "ndvi", nombre: "Vigor del cultivo (NDVI)", archivo: im.overlay_ndvi,
      leyenda: gradiente("ndvi", esc_.ndvi, `Vigor del cultivo (NDVI)${camp}`, "menos vigor", "más vigor") },
    { id: "ndmi", nombre: "Humedad en las plantas (NDMI)", archivo: im.overlay_ndmi,
      leyenda: gradiente("ndmi", esc_.ndmi, `Humedad en las plantas (NDMI)${camp}`, "más seco", "más húmedo") },
    { id: "zonas", nombre: "Zonas de manejo", archivo: im.overlay_zonas,
      leyenda: `<div class="ley-t">Zonas de manejo</div>
        <div class="ley-z"><span><i style="background:#1a9641"></i>Alta ${num(l.zonas.alta_pct, 0, "%")}</span>
        <span><i style="background:#fdcc8a"></i>Media ${num(l.zonas.media_pct, 0, "%")}</span>
        <span><i style="background:#d7301f"></i>Baja ${num(l.zonas.baja_pct, 0, "%")}</span></div>
        <p class="ley-nota">La zona baja conviene recorrerla primero.</p>` },
    { id: "rgb", nombre: "Color natural", archivo: im.overlay_rgb,
      leyenda: `<div class="ley-t">Color natural ${im.fecha_rgb ?? ""}</div><p class="ley-nota">Así se veía el lote ese día.</p>` },
  ];
  const defs = todas.filter((d) => d.id === "ninguna" || d.archivo);

  const capas = new Map<CapaId, L.ImageOverlay>();
  for (const d of defs) {
    if (d.archivo) capas.set(d.id, L.imageOverlay(url(l.id, d.archivo), bounds, { className: "overlay-pix", opacity: 0.75 }));
  }
  let actual: CapaId = "ninguna";
  let opacidad = 0.75;

  const panel = document.createElement("div");
  panel.className = "panel-capas";
  panel.innerHTML = `<details open>
    <summary class="pc-t">Qué ver arriba del satélite${l.ejemplo ? ' <span class="chip-ejemplo">Datos de ejemplo</span>' : ""}</summary>
    ${defs.map((d) => `<label><input type="radio" name="capa-${l.id}" value="${d.id}" ${d.id === actual ? "checked" : ""}> ${d.nombre}</label>`).join("")}
    <label class="pc-op">Intensidad <input type="range" min="0" max="100" value="${opacidad * 100}" aria-label="Intensidad de la capa"> <output>${Math.round(opacidad * 100)}%</output></label>
    <div class="pc-ley"></div></details>`;
  L.DomEvent.disableClickPropagation(panel);
  L.DomEvent.disableScrollPropagation(panel);
  const colocar = () => {
    const riel = document.getElementById("riel-capas");
    if (!document.body.contains(el) && !(riel && document.body.contains(riel))) {
      window.removeEventListener("resize", colocar);
      window.removeEventListener("hashchange", colocar);
      return;
    }
    if (riel && document.body.contains(riel)) {
      panel.classList.add("en-riel");
      panel.classList.remove("fuera");
      riel.appendChild(panel);
      return;
    }
    panel.classList.remove("en-riel");
    const angosto = window.innerWidth < 760;
    panel.classList.toggle("fuera", angosto);
    if (angosto) el.insertAdjacentElement("afterend", panel);
    else el.appendChild(panel);
  };
  colocar();
  window.addEventListener("resize", colocar);
  window.addEventListener("hashchange", colocar);
  const ley = panel.querySelector<HTMLElement>(".pc-ley")!;
  const rango = panel.querySelector<HTMLInputElement>("input[type=range]")!;
  const out = panel.querySelector("output")!;

  const mostrar = (id: CapaId) => {
    capas.forEach((c) => map.removeLayer(c));
    actual = id;
    const c = capas.get(id);
    if (c) { c.setOpacity(opacidad).addTo(map); }
    ley.innerHTML = defs.find((d) => d.id === id)?.leyenda ?? "";
    rango.disabled = !c;
    panel.querySelector<HTMLInputElement>(`input[value=${id}]`)!.checked = true;
  };
  panel.querySelectorAll<HTMLInputElement>("input[type=radio]").forEach((r) =>
    r.addEventListener("change", () => mostrar(r.value as CapaId)));
  rango.addEventListener("input", () => {
    opacidad = Number(rango.value) / 100;
    out.textContent = `${rango.value}%`;
    capas.get(actual)?.setOpacity(opacidad);
  });
  mostrar(inicial && capas.has(inicial as CapaId) ? (inicial as CapaId) : "ninguna");
  // Sin internet: mostrar NDVI para que el lote no quede vacío
  map.on("sin-tiles", () => { if (actual === "ninguna" && capas.has("ndvi")) mostrar("ndvi"); });
  if (el.classList.contains("sin-tiles") && capas.has("ndvi")) mostrar("ndvi");
}

type ClaseZona = "baja" | "alta";

function clasePixel(r: number, g: number, b: number, a: number): ClaseZona | "media" | null {
  if (a < 80) return null;
  if (r > 150 && r > g * 1.3 && r > b) return "baja";
  if (g > 90 && g > r * 1.15 && g > b) return "alta";
  return "media";
}

/**
 * Leyendas sobre la foto. El texto y el porcentaje salen de zonas.*_pct.
 * El punto es el centroide de los píxeles de ese color en overlay_zonas (misma georreferencia que la capa).
 * Si el PNG no se puede leer, no se dibuja nada: no se inventa una posición.
 */
export function anotarZonas(map: L.Map, l: Lote) {
  const archivo = l.imagenes.overlay_zonas;
  const bbox = l.imagenes.bbox;
  if (!archivo || !bbox) return;
  if (l.zonas.baja_pct === null && l.zonas.alta_pct === null) return;
  const img = new Image();
  img.onload = () => {
    if (!map.getContainer().isConnected) return;
    const maxLado = 160;
    const escala = Math.min(1, maxLado / Math.max(img.naturalWidth, img.naturalHeight));
    const w = Math.max(1, Math.round(img.naturalWidth * escala));
    const h = Math.max(1, Math.round(img.naturalHeight * escala));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    ctx.drawImage(img, 0, 0, w, h);
    let data: Uint8ClampedArray;
    try { data = ctx.getImageData(0, 0, w, h).data; } catch { return; }
    const acc: Record<ClaseZona, [number, number, number]> = { baja: [0, 0, 0], alta: [0, 0, 0] };
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const i = (y * w + x) * 4;
        const k = clasePixel(data[i], data[i + 1], data[i + 2], data[i + 3]);
        if (k !== "baja" && k !== "alta") continue;
        acc[k][0] += x;
        acc[k][1] += y;
        acc[k][2] += 1;
      }
    }
    const [west, south, east, north] = bbox;
    if (!map.getPane("anotaciones")) {
      const pane = map.createPane("anotaciones");
      pane.style.zIndex = "650";
      pane.style.pointerEvents = "none";
    }
    type Anot = {
      centro: L.LatLng; fx: number; fy: number; haciaIzquierda: boolean;
      marca: L.Marker; linea: L.Polyline; halo: L.Polyline; punto: L.CircleMarker; w: number; h: number;
    };
    const anotaciones: Anot[] = [];
    const crear = (k: ClaseZona, texto: string, pct: number | null) => {
      if (pct === null) return;
      const [sx, sy, n] = acc[k];
      if (n < 12) return;
      const fx = (sx / n) / w;
      const fy = (sy / n) / h;
      const centro = L.latLng(north - fy * (north - south), west + fx * (east - west));
      // La etiqueta sale hacia afuera del lote, no hacia la zona de enfrente.
      const haciaIzquierda = fx < 0.5;
      const iconSize: [number, number] = [158, 70];
      const iconAnchor: [number, number] = haciaIzquierda ? [iconSize[0], iconSize[1] / 2] : [0, iconSize[1] / 2];
      const html = `<span class="anotacion ${haciaIzquierda ? "hacia-izq" : "hacia-der"}"><span class="anotacion-mano">${esc(texto)}</span><span class="anotacion-num">${num(pct, 0, " %")}</span>${l.ejemplo ? `<span class="anotacion-ej">Datos de ejemplo</span>` : ""}</span>`;
      const opts = { pane: "anotaciones", interactive: false as const };
      anotaciones.push({
        centro, fx, fy, haciaIzquierda, w: iconSize[0], h: iconSize[1],
        marca: L.marker(centro, { ...opts, keyboard: false, icon: L.divIcon({ className: "anotacion-pin", html, iconSize, iconAnchor }) }),
        halo: L.polyline([centro, centro], { ...opts, color: "#fbf6ea", weight: 5.5, opacity: 0.95 }),
        linea: L.polyline([centro, centro], { ...opts, color: "#111713", weight: 2, opacity: 1 }),
        punto: L.circleMarker(centro, { ...opts, radius: 5.5, color: "#111713", weight: 2, fillColor: "#d6ef4a", fillOpacity: 1 }),
      });
    };
    crear("alta", "zona alta", l.zonas.alta_pct);
    crear("baja", "zona más floja", l.zonas.baja_pct);
    const choca = (a: { l: number; t: number; r: number; b: number }, b: { l: number; t: number; r: number; b: number }) =>
      a.l < b.r - 4 && a.r > b.l + 4 && a.t < b.b - 4 && a.b > b.t + 4;
    const layout = () => {
      if (!map.getContainer().isConnected) return;
      const size = map.getSize();
      const angosto = size.x < 720;
      const ocupadas: { l: number; t: number; r: number; b: number }[] = [];
      for (const a of anotaciones) {
        const puesta = map.hasLayer(a.marca);
        if (angosto) {
          if (puesta) { map.removeLayer(a.marca); map.removeLayer(a.linea); map.removeLayer(a.halo); map.removeLayer(a.punto); }
          continue;
        }
        if (!puesta) { a.halo.addTo(map); a.linea.addTo(map); a.punto.addTo(map); a.marca.addTo(map); }
        const p = map.latLngToContainerPoint(a.centro);
        const margen = 8;
        let x = p.x + (a.haciaIzquierda ? -78 : 78);
        let y = p.y + (a.fy < 0.5 ? -36 : 36);
        const clamp = () => {
          if (a.haciaIzquierda) x = Math.max(a.w + margen, Math.min(x, size.x - margen));
          else x = Math.max(margen, Math.min(x, size.x - a.w - margen));
          y = Math.max(a.h / 2 + margen, Math.min(y, size.y - a.h / 2 - margen));
        };
        clamp();
        for (let i = 0; i < 5; i++) {
          const left = a.haciaIzquierda ? x - a.w : x;
          const caja = { l: left, t: y - a.h / 2, r: left + a.w, b: y + a.h / 2 };
          if (!ocupadas.some((o) => choca(caja, o))) { ocupadas.push(caja); break; }
          y += a.h + 10;
          clamp();
        }
        const dest = map.containerPointToLatLng(L.point(x, y));
        a.halo.setLatLngs([a.centro, dest]);
        a.linea.setLatLngs([a.centro, dest]);
        a.marca.setLatLng(dest);
      }
    };
    layout();
    map.on("zoom move resize", layout);
    const cortar = () => map.off("zoom move resize", layout);
    map.on("unload", cortar);
    window.addEventListener("hashchange", cortar, { once: true });
    window.setTimeout(layout, 120);
  };
  img.src = url(l.id, archivo);
}

function gradiente(tipo: "ndvi" | "ndmi", escala: [number, number] | undefined, titulo: string, izq: string, der: string) {
  const [a, b] = escala ?? [NaN, NaN];
  return `<div class="ley-t">${titulo}</div>
    <div class="ley-grad ${tipo}"></div>
    <div class="ley-n"><span>${num(a, 1)}</span><span>${num(b, 1)}</span></div>
    <div class="ley-n"><small>${izq}</small><small>${der}</small></div>`;
}

/** Mapa satelital vacío (para cargar/dibujar lotes): mismos mapas base, rótulos, escala y fallback offline. */
export function mapaBase(el: HTMLElement, centro: [number, number] = [-33.35, -63.75], zoom = 11) {
  const map = L.map(el, { zoomSnap: 1, zoomControl: false }).setView(centro, zoom);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  const ind = document.createElement("div");
  ind.className = "cargando-tiles";
  ind.textContent = "Cargando la foto satelital…";
  el.appendChild(ind);
  const bases = capasBase();
  Object.values(bases).forEach((b) => vigilarBase(b, el, map));
  const capaRotulos = rotulos();
  if (navigator.onLine) { bases.satelite.addTo(map); capaRotulos.addTo(map); }
  else { ind.remove(); bases.ninguno.addTo(map); setTimeout(() => avisoOffline(el, map), 0); }
  L.control.layers(
    Object.fromEntries((Object.keys(bases) as BaseId[]).map((k) => [NOMBRES_BASE[k], bases[k]])),
    { "Nombres y rutas": capaRotulos }, { collapsed: true, position: "topright" },
  ).addTo(map);
  L.control.scale({ imperial: false, position: "bottomleft", maxWidth: 160 }).addTo(map);
  setTimeout(() => map.invalidateSize(), 60);
  return map;
}

/** Estilos de contorno reutilizables (halo oscuro + línea). */
export function contornoLote(pts: [number, number][], color = "#ffe14d", grupo?: L.LayerGroup, opts: L.PolylineOptions = {}) {
  const halo = L.polygon(pts, { color: "#000", weight: 8, opacity: 0.5, fill: false, interactive: false });
  const linea = L.polygon(pts, { color, weight: 3.5, fillOpacity: 0.08, fillColor: color, ...opts });
  if (grupo) { halo.addTo(grupo); linea.addTo(grupo); }
  return { halo, linea };
}
