/** Lectura y validación de lotes cargados por el usuario (KML / KMZ / GeoJSON). Sin efectos de red. */
import { kml as kmlAGeoJSON } from "@tmcw/togeojson";
import JSZip from "jszip";
import turfArea from "@turf/area";
import kinks from "@turf/kinks";
import type { Feature, FeatureCollection, Polygon, Position } from "geojson";

export interface PoligonoLeido { nombre: string; anillo: Position[]; huecos: number; origen: string }
export interface Validacion { ok: boolean; area_ha: number; errores: string[]; avisos: string[]; anillo: Position[] }

export const AREA_MIN_HA = 1;
export const AREA_MAX_HA = 20000;
// Caja aproximada de Argentina continental (solo para avisar, no bloquea)
export const ARG_BBOX = { lonMin: -73.6, lonMax: -53.6, latMin: -55.1, latMax: -21.7 };

/** Extrae polígonos de un GeoJSON (Feature, FeatureCollection o geometría). MultiPolygon se separa. */
export function poligonosDeGeoJSON(gj: unknown, origen = "GeoJSON"): PoligonoLeido[] {
  const out: PoligonoLeido[] = [];
  const visitar = (g: any, nombre: string) => {
    if (!g) return;
    if (g.type === "FeatureCollection") g.features?.forEach((f: any, i: number) => visitar(f, nombreDe(f, i)));
    else if (g.type === "Feature") visitar(g.geometry, nombre || nombreDe(g, 0));
    else if (g.type === "GeometryCollection") {
      const polis = (g.geometries ?? []).filter((x: any) => x?.type === "Polygon" || x?.type === "MultiPolygon");
      polis.forEach((x: any, i: number) => visitar(x, polis.length > 1 ? `${nombre} (${i + 1})` : nombre));
    }
    else if (g.type === "Polygon" && Array.isArray(g.coordinates?.[0]))
      out.push({ nombre, anillo: limpiar(g.coordinates[0]), huecos: g.coordinates.length - 1, origen });
    else if (g.type === "MultiPolygon")
      g.coordinates.forEach((p: Position[][], i: number) =>
        out.push({ nombre: g.coordinates.length > 1 ? `${nombre} (${i + 1})` : nombre, anillo: limpiar(p[0]), huecos: p.length - 1, origen }));
  };
  visitar(gj, "");
  return out.map((p, i) => ({ ...p, nombre: p.nombre || `Polígono ${i + 1}` }));
}

function nombreDe(f: any, i: number): string {
  const p = f?.properties ?? {};
  return String(p.nombre ?? p.name ?? p.Name ?? p.NOMBRE ?? "").trim() || `Polígono ${i + 1}`;
}

const limpiar = (r: Position[]): Position[] => r.map((c) => [Number(c[0]), Number(c[1])]);

export function poligonosDeKML(texto: string, parser: DOMParser = new DOMParser()): PoligonoLeido[] {
  const doc = parser.parseFromString(texto, "text/xml");
  if (doc.getElementsByTagName("parsererror").length) throw new Error("El KML no es un XML válido.");
  return poligonosDeGeoJSON(kmlAGeoJSON(doc as unknown as Document), "KML");
}

export async function poligonosDeKMZ(buf: ArrayBuffer, parser?: DOMParser): Promise<PoligonoLeido[]> {
  const zip = await JSZip.loadAsync(buf);
  const kmls = Object.values(zip.files).filter((f) => !f.dir && f.name.toLowerCase().endsWith(".kml"));
  if (!kmls.length) throw new Error("El KMZ no contiene ningún archivo .kml.");
  const principal = kmls.find((f) => f.name.toLowerCase().endsWith("doc.kml")) ?? kmls[0];
  return poligonosDeKML(await principal.async("string"), parser).map((p) => ({ ...p, origen: "KMZ" }));
}

/** Detecta el tipo por extensión y devuelve los polígonos encontrados. */
export async function leerArchivo(nombre: string, datos: ArrayBuffer, parser?: DOMParser): Promise<PoligonoLeido[]> {
  const ext = nombre.toLowerCase().split(".").pop();
  let res: PoligonoLeido[];
  if (ext === "kmz") res = await poligonosDeKMZ(datos, parser);
  else {
    const texto = new TextDecoder("utf-8").decode(datos);
    if (ext === "kml") res = poligonosDeKML(texto, parser);
    else if (ext === "geojson" || ext === "json") {
      let gj: unknown;
      try { gj = JSON.parse(texto); } catch { throw new Error("El archivo no es un JSON válido."); }
      res = poligonosDeGeoJSON(gj);
    } else throw new Error("Formato no soportado: usá .kml, .kmz o .geojson.");
  }
  if (!res.length) throw new Error("No se encontró ningún polígono en el archivo (¿son solo puntos o líneas?).");
  return res;
}

export function areaHa(anillo: Position[]): number {
  return turfArea({ type: "Polygon", coordinates: [cerrar(anillo)] }) / 10_000;
}

export function cerrar(anillo: Position[]): Position[] {
  if (!anillo.length) return anillo;
  const [a, b] = [anillo[0], anillo[anillo.length - 1]];
  return a[0] === b[0] && a[1] === b[1] ? anillo : [...anillo, [a[0], a[1]]];
}

export function validarPoligono(p: Pick<PoligonoLeido, "anillo"> & { huecos?: number }): Validacion {
  const errores: string[] = [];
  const avisos: string[] = [];
  let anillo = p.anillo.filter((c) => Number.isFinite(c[0]) && Number.isFinite(c[1]));
  // quitar vértices repetidos consecutivos
  anillo = anillo.filter((c, i) => i === 0 || c[0] !== anillo[i - 1][0] || c[1] !== anillo[i - 1][1]);
  const estabaCerrado = anillo.length > 1 && anillo[0][0] === anillo.at(-1)![0] && anillo[0][1] === anillo.at(-1)![1];
  anillo = cerrar(anillo);
  if (!estabaCerrado && anillo.length > 3) avisos.push("El polígono no estaba cerrado: se cerró uniendo el último vértice con el primero.");
  if (anillo.length < 4) {
    errores.push("El polígono necesita al menos 3 vértices distintos.");
    return { ok: false, area_ha: 0, errores, avisos, anillo };
  }
  if (anillo.some(([lon, lat]) => Math.abs(lon) > 180 || Math.abs(lat) > 90))
    errores.push("Hay coordenadas fuera de rango: el archivo tiene que estar en latitud/longitud (WGS84, EPSG:4326).");
  const poli: Feature<Polygon> = { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [anillo] } };
  if (!errores.length && kinks(poli).features.length > 0)
    errores.push("El borde del polígono se cruza consigo mismo. Corregí los vértices (forma de moño / 8).");
  const ha = errores.length ? 0 : areaHa(anillo);
  if (!errores.length) {
    if (ha < AREA_MIN_HA) errores.push(`El lote mide ${fmtHa(ha)} ha: menos del mínimo (${AREA_MIN_HA} ha).`);
    else if (ha > AREA_MAX_HA) errores.push(`El lote mide ${fmtHa(ha)} ha: más del máximo (${AREA_MAX_HA.toLocaleString("es-AR")} ha). ¿Es un campo entero o una región?`);
    else if (ha < 5) avisos.push("Lote muy chico (< 5 ha): con píxeles de 10 m el análisis tiene poco detalle.");
    else if (ha > 5000) avisos.push("Lote muy grande (> 5.000 ha): conviene dividirlo en lotes de manejo.");
  }
  const fuera = anillo.some(([lon, lat]) => lon < ARG_BBOX.lonMin || lon > ARG_BBOX.lonMax || lat < ARG_BBOX.latMin || lat > ARG_BBOX.latMax);
  if (fuera && !errores.length) avisos.push("El lote parece estar fuera de Argentina (¿coordenadas invertidas?). Los mapas de cultivo de IDECOR cubren solo Córdoba.");
  if (p.huecos) avisos.push(`El polígono tiene ${p.huecos} hueco(s): se usa solo el borde exterior.`);
  return { ok: errores.length === 0, area_ha: Math.round(ha * 10) / 10, errores, avisos, anillo };
}

export const fmtHa = (v: number) => v.toLocaleString("es-AR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export function slug(s: string): string {
  return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "lote";
}

export interface LoteCargado {
  id: string; nombre: string; propietario: string; notas: string; anillo: Position[]; area_ha: number;
  origen: string; creado: string; estado: "pendiente" | "analizando" | "analizado" | "error";
  trabajo?: string; error?: string; avisos?: string[];
}

/** FeatureCollection compatible con pipeline/data/lotes.geojson (properties: id, nombre, localidad, fuente). */
export function aGeoJSONPipeline(lotes: LoteCargado[]): FeatureCollection<Polygon> {
  return {
    type: "FeatureCollection",
    features: lotes.map((l) => ({
      type: "Feature",
      properties: {
        id: l.id, nombre: l.nombre, localidad: l.propietario || "Sin especificar",
        fuente: `Cargado en la demo web (${l.origen}) el ${l.creado.slice(0, 10)}`,
        propietario: l.propietario || null, notas_cultivo: l.notas || null,
      },
      geometry: { type: "Polygon", coordinates: [l.anillo] },
    })),
  };
}

export function nuevoId(nombre: string, existentes: Set<string>): string {
  let id: string;
  do { id = `cargado_${slug(nombre)}_${Math.random().toString(16).slice(2, 6)}`; } while (existentes.has(id));
  return id;
}
