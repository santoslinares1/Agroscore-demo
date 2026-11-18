// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import JSZip from "jszip";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  aGeoJSONPipeline, areaHa, leerArchivo, nuevoId, poligonosDeGeoJSON, poligonosDeKML, slug, validarPoligono, type LoteCargado,
} from "../src/carga/geo";

// cuadrado de ~800 m de lado cerca de Alejandro Roca (≈ 64 ha)
const lat = -33.35, lon = -63.7;
const dy = 800 / 111320, dx = 800 / (111320 * Math.cos((lat * Math.PI) / 180));
const CUAD = [[lon, lat], [lon + dx, lat], [lon + dx, lat + dy], [lon, lat + dy], [lon, lat]];
const coordsKML = (r: number[][]) => r.map((p) => `${p[0]},${p[1]},0`).join(" ");
const kml = (cuerpo: string) => `<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>${cuerpo}</Document></kml>`;
const pm = (n: string, r: number[][]) => `<Placemark><name>${n}</name><Polygon><outerBoundaryIs><LinearRing><coordinates>${coordsKML(r)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>`;
const buf = (s: string) => new TextEncoder().encode(s).buffer as ArrayBuffer;

describe("lectura de archivos", () => {
  it("KML con un polígono", () => {
    const p = poligonosDeKML(kml(pm("Lote 1", CUAD)));
    expect(p).toHaveLength(1);
    expect(p[0].nombre).toBe("Lote 1");
    expect(p[0].anillo).toHaveLength(5);
  });

  it("KML de ejemplo del repo: Placemark + MultiGeometry → 3 polígonos", async () => {
    const t = readFileSync(resolve(__dirname, "../../pipeline/data/ejemplo_carga.kml"), "utf-8");
    const p = await leerArchivo("ejemplo_carga.kml", buf(t));
    expect(p.map((x) => x.nombre)).toEqual(["EJEMPLO Lote A", "EJEMPLO Campo B (1)", "EJEMPLO Campo B (2)"]);
    p.forEach((x) => expect(validarPoligono(x).ok).toBe(true));
  });

  it("KMZ (zip con doc.kml)", async () => {
    const z = new JSZip();
    z.file("doc.kml", kml(pm("Del KMZ", CUAD) + pm("Otro", CUAD.map(([a, b]) => [a + 0.02, b]))));
    const p = await leerArchivo("campo.KMZ", await z.generateAsync({ type: "arraybuffer" }));
    expect(p.map((x) => x.nombre)).toEqual(["Del KMZ", "Otro"]);
    expect(p[0].origen).toBe("KMZ");
  });

  it("KMZ sin kml y KML roto dan error claro", async () => {
    const z = new JSZip(); z.file("leeme.txt", "hola");
    await expect(leerArchivo("x.kmz", await z.generateAsync({ type: "arraybuffer" }))).rejects.toThrow(/no contiene/);
    await expect(leerArchivo("x.kml", buf("<kml><Document>"))).rejects.toThrow(/XML/);
    await expect(leerArchivo("x.shp", buf("..."))).rejects.toThrow(/Formato no soportado/);
  });

  it("GeoJSON: FeatureCollection, MultiPolygon separado y nombres", async () => {
    const gj = { type: "FeatureCollection", features: [
      { type: "Feature", properties: { name: "A" }, geometry: { type: "Polygon", coordinates: [CUAD] } },
      { type: "Feature", properties: { nombre: "B" }, geometry: { type: "MultiPolygon", coordinates: [[CUAD], [CUAD]] } },
      { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [lon, lat] } },
    ] };
    const p = await leerArchivo("l.geojson", buf(JSON.stringify(gj)));
    expect(p.map((x) => x.nombre)).toEqual(["A", "B (1)", "B (2)"]);
    expect(poligonosDeGeoJSON({ type: "Polygon", coordinates: [CUAD, CUAD] })[0].huecos).toBe(1);
    await expect(leerArchivo("p.geojson", buf(JSON.stringify(gj.features[2])))).rejects.toThrow(/ningún polígono/);
  });

  it("archivo exportado por la web se vuelve a leer igual (ida y vuelta)", async () => {
    const l: LoteCargado = { id: "cargado_x_0001", nombre: "X", propietario: "", notas: "maní 23/24", anillo: CUAD, area_ha: 64,
      origen: "dibujo", creado: "2026-11-16T12:00:00.000Z", estado: "pendiente" };
    const fc = aGeoJSONPipeline([l]);
    expect(fc.features[0].properties).toMatchObject({ id: "cargado_x_0001", nombre: "X", localidad: "Sin especificar", notas_cultivo: "maní 23/24" });
    expect(fc.features[0].properties!.fuente).toMatch(/2026-11-16/);
    const p = await leerArchivo("lotes_cargados.geojson", buf(JSON.stringify(fc)));
    expect(p[0].anillo).toEqual(CUAD);
  });
});

describe("validación y área", () => {
  it("área en ha con turf ≈ 64 ha", () => {
    expect(areaHa(CUAD)).toBeCloseTo(64, 0);
    const v = validarPoligono({ anillo: CUAD });
    expect(v.ok).toBe(true);
    expect(v.area_ha).toBeCloseTo(64, 0);
    expect(v.errores).toEqual([]);
  });

  it("cierra anillos abiertos con aviso", () => {
    const v = validarPoligono({ anillo: CUAD.slice(0, 4) });
    expect(v.ok).toBe(true);
    expect(v.anillo[0]).toEqual(v.anillo.at(-1));
    expect(v.avisos.join()).toMatch(/no estaba cerrado/);
  });

  it("rechaza autointersección (moño)", () => {
    const mono = [CUAD[0], CUAD[2], CUAD[1], CUAD[3], CUAD[0]];
    const v = validarPoligono({ anillo: mono });
    expect(v.ok).toBe(false);
    expect(v.errores.join()).toMatch(/se cruza/);
  });

  it("rechaza menos de 3 vértices, muy chico y muy grande", () => {
    expect(validarPoligono({ anillo: [CUAD[0], CUAD[1], CUAD[0]] }).ok).toBe(false);
    const chico = CUAD.map(([a, b]) => [lon + (a - lon) / 20, lat + (b - lat) / 20]);
    expect(validarPoligono({ anillo: chico }).errores.join()).toMatch(/mínimo/);
    const enorme = CUAD.map(([a, b]) => [lon + (a - lon) * 30, lat + (b - lat) * 30]);
    expect(validarPoligono({ anillo: enorme }).errores.join()).toMatch(/máximo/);
    const grande = CUAD.map(([a, b]) => [lon + (a - lon) * 10, lat + (b - lat) * 10]);
    const vg = validarPoligono({ anillo: grande });
    expect(vg.ok).toBe(true);
    expect(vg.avisos.join()).toMatch(/muy grande/);
  });

  it("avisa (sin bloquear) si está fuera de Argentina o con lat/lon invertidas", () => {
    const inv = CUAD.map(([a, b]) => [b, a]);
    const v = validarPoligono({ anillo: inv });
    expect(v.ok).toBe(true);
    expect(v.avisos.join()).toMatch(/fuera de Argentina/);
    expect(validarPoligono({ anillo: CUAD }).avisos.join()).not.toMatch(/Argentina/);
  });

  it("coordenadas proyectadas (no grados) → error", () => {
    const utm = [[400000, 6300000], [400800, 6300000], [400800, 6300800], [400000, 6300000]];
    expect(validarPoligono({ anillo: utm }).errores.join()).toMatch(/fuera de rango/);
  });

  it("slug e id únicos", () => {
    expect(slug("Lote Ñandú – Nº 3")).toBe("lote_nandu_n_3");
    const ids = new Set<string>();
    for (let i = 0; i < 50; i++) { const id = nuevoId("Lote", ids); expect(ids.has(id)).toBe(false); ids.add(id); }
    expect([...ids][0]).toMatch(/^cargado_lote_[0-9a-f]{4}$/);
  });
});
