import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Lote } from "./types";
import { url } from "./data";
import { colorScore, esc, num } from "./fmt";

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
  satelite: "Satélite (Esri World Imagery)",
  topo: "Topográfico (Esri World Topo)",
  relieve: "Relieve físico (OpenTopoMap)",
  ninguno: "Sin mapa de fondo",
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
  d.textContent = "Sin conexión: no se puede cargar el mapa satelital de fondo. Se muestran el lote y sus capas propias.";
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
    zoomControl: !mini, dragging: !mini, scrollWheelZoom: opts.modo === "detalle" ? "center" : !mini,
    doubleClickZoom: !mini, boxZoom: !mini, keyboard: !mini, touchZoom: !mini, attributionControl: true,
    zoomSnap: opts.modo === "detalle" ? 0.25 : 1, zoomDelta: 0.5,
    zoomAnimation: !mini, fadeAnimation: !mini,
  });
  map.attributionControl.setPrefix(mini ? false : '<a href="https://leafletjs.com">Leaflet</a>');
  const ind = document.createElement("div");
  ind.className = "cargando-tiles";
  ind.textContent = "Cargando imagen satelital…";
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
      pol.bindTooltip(`<strong>${esc(l.nombre)}</strong><br>${l.score.valor === null ? "Sin dato suficiente" : `Score ${l.score.valor}/100`} · ${num(l.area_ha, 1)} ha` +
        (l.ejemplo ? `<br><span class="tt-ejemplo">EJEMPLO</span>` : ""), { sticky: true });
    }
    if (opts.onClick) pol.on("click", () => opts.onClick!(l.id));
    if (opts.modo === "inicio") {
      const m = L.marker([l.centroide[1], l.centroide[0]], {
        icon: L.divIcon({ className: "pin-lote", html: `<span style="background:${colorScore(l.score.valor)}" title="${l.score.valor === null ? "Sin dato suficiente" : ""}">${l.score.valor ?? "s/d"}</span><b>${esc(l.nombre.replace(/^Lote /, ""))}</b>`,
          iconSize: [0, 0] }),
        keyboard: true, title: l.nombre,
      }).addTo(grupo);
      if (opts.onClick) m.on("click", () => opts.onClick!(l.id));
    }
  }

  if (!mini) {
    L.control.layers(
      Object.fromEntries((Object.keys(bases) as BaseId[]).map((k) => [NOMBRES_BASE[k], bases[k]])),
      { "Rótulos y rutas": capaRotulos },
      { collapsed: opts.modo !== "detalle" || window.innerWidth < 700, position: "topright" },
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
    else map.fitBounds(b, { padding: mini ? [8, 8] : [28, 28], maxZoom: 17 });
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
    { id: "ninguna", nombre: "Solo imagen satelital", leyenda: "" },
    { id: "ndvi", nombre: "NDVI (vigor)", archivo: im.overlay_ndvi,
      leyenda: gradiente("ndvi", esc_.ndvi, `NDVI máximo${camp}`, "menos vigor", "más vigor") },
    { id: "ndmi", nombre: "NDMI (humedad)", archivo: im.overlay_ndmi,
      leyenda: gradiente("ndmi", esc_.ndmi, `NDMI medio${camp}`, "más seco", "más húmedo") },
    { id: "zonas", nombre: "Zonas Alta / Media / Baja", archivo: im.overlay_zonas,
      leyenda: `<div class="ley-t">Zonas de productividad</div>
        <div class="ley-z"><i style="background:#1a9641"></i>Alta ${num(l.zonas.alta_pct, 0, "%")}
        <i style="background:#fdcc8a"></i>Media ${num(l.zonas.media_pct, 0, "%")}
        <i style="background:#d7301f"></i>Baja ${num(l.zonas.baja_pct, 0, "%")}</div>` },
    { id: "rgb", nombre: "Color natural (Sentinel-2)", archivo: im.overlay_rgb,
      leyenda: `<div class="ley-t">Color natural ${im.fecha_rgb ?? ""}</div>` },
  ];
  const defs = todas.filter((d) => d.id === "ninguna" || d.archivo);

  const capas = new Map<CapaId, L.ImageOverlay>();
  for (const d of defs) {
    if (d.archivo) capas.set(d.id, L.imageOverlay(url(l.id, d.archivo), bounds, { className: "overlay-pix", opacity: 0.75 }));
  }
  let actual: CapaId = "ninguna";
  let opacidad = 0.75;

  const Ctrl = L.Control.extend({
    onAdd() {
      const div = L.DomUtil.create("div", "panel-capas leaflet-bar");
      const abierto = window.innerWidth >= 700;
      div.innerHTML = `<details ${abierto ? "open" : ""}>
        <summary class="pc-t">Capas del lote${l.ejemplo ? ' <span class="chip-ejemplo">EJEMPLO</span>' : ""}</summary>
        ${defs.map((d) => `<label><input type="radio" name="capa-${l.id}" value="${d.id}" ${d.id === actual ? "checked" : ""}> ${d.nombre}</label>`).join("")}
        <label class="pc-op">Opacidad <input type="range" min="0" max="100" value="${opacidad * 100}" aria-label="Opacidad de la capa"> <output>${Math.round(opacidad * 100)}%</output></label>
        <div class="pc-ley"></div></details>`;
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      return div;
    },
  });
  const ctrl = new Ctrl({ position: window.innerWidth < 700 ? "bottomright" : "topleft" });
  ctrl.addTo(map);
  const panel = ctrl.getContainer()!;
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

function gradiente(tipo: "ndvi" | "ndmi", escala: [number, number] | undefined, titulo: string, izq: string, der: string) {
  const [a, b] = escala ?? [NaN, NaN];
  return `<div class="ley-t">${titulo}</div>
    <div class="ley-grad ${tipo}"></div>
    <div class="ley-n"><span>${num(a, 1)}</span><span>${num(b, 1)}</span></div>
    <div class="ley-n"><small>${izq}</small><small>${der}</small></div>`;
}

/** Mapa satelital vacío (para cargar/dibujar lotes): mismos mapas base, rótulos, escala y fallback offline. */
export function mapaBase(el: HTMLElement, centro: [number, number] = [-33.35, -63.75], zoom = 11) {
  const map = L.map(el, { zoomSnap: 1 }).setView(centro, zoom);
  const ind = document.createElement("div");
  ind.className = "cargando-tiles";
  ind.textContent = "Cargando imagen satelital…";
  el.appendChild(ind);
  const bases = capasBase();
  Object.values(bases).forEach((b) => vigilarBase(b, el, map));
  const capaRotulos = rotulos();
  if (navigator.onLine) { bases.satelite.addTo(map); capaRotulos.addTo(map); }
  else { ind.remove(); bases.ninguno.addTo(map); setTimeout(() => avisoOffline(el, map), 0); }
  L.control.layers(
    Object.fromEntries((Object.keys(bases) as BaseId[]).map((k) => [NOMBRES_BASE[k], bases[k]])),
    { "Rótulos y rutas": capaRotulos }, { collapsed: true, position: "topright" },
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
