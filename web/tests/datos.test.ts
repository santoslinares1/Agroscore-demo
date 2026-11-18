// @vitest-environment jsdom
// Validación de index.json / lote.json con los schemas del pipeline (Ajv) + carga tolerante (allSettled).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { cargarDatos, ErrorIndice } from "../src/data";
import { validarIndex, validarLote } from "../src/validacion";
import { vistaInicio } from "../src/views/inicio";
import { vistaDetalle } from "../src/views/detalle";
import { vistaInforme } from "../src/views/informe";
import { vistaComparar } from "../src/views/comparar";
import { vistaComo } from "../src/views/como";

const DEMO = resolve(__dirname, "../public/demo");
const SCHEMAS = resolve(__dirname, "../../pipeline/agroscore/schema");
const leerTxt = (p: string) => readFileSync(resolve(DEMO, p), "utf-8");
const leer = (p: string) => JSON.parse(leerTxt(p));
const IDS: string[] = leer("index.json").lotes.map((l: { id: string }) => l.id);
const [A, B, C] = IDS;

type Resp = { status: number; body?: string } | "red";
/** fetch simulado: ruta (relativa a demo/) → respuesta. Lo no declarado lee de public/demo. */
function simular(over: Record<string, Resp> = {}) {
  vi.stubGlobal("fetch", async (u: string) => {
    const p = String(u).replace(/^demo\//, "");
    const o = over[p];
    if (o === "red") throw new TypeError("Failed to fetch");
    if (o) return new Response(o.body ?? "", { status: o.status });
    if (existsSync(resolve(DEMO, p))) return new Response(leerTxt(p), { status: 200 });
    return new Response("", { status: 404 });
  });
}
beforeEach(() => simular());
afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); document.body.innerHTML = ""; });

const roto = (id: string, cambio: (d: any) => void): Resp => { const d = leer(`${id}/lote.json`); cambio(d); return { status: 200, body: JSON.stringify(d) }; };
const montar = () => { const el = document.createElement("div"); document.body.appendChild(el); return el; };

describe("schemas del pipeline compartidos con la web", () => {
  it("la web no duplica los schemas: solo existen en pipeline/agroscore/schema", () => {
    expect(readdirSync(SCHEMAS).filter((f) => f.endsWith(".schema.json")).sort()).toEqual(["index.schema.json", "lote.schema.json"]);
    for (const dir of ["../src", "../public", "../public/demo"])
      expect(readdirSync(resolve(__dirname, dir)).filter((f) => f.endsWith(".schema.json"))).toEqual([]);
  });
  it("los ejemplos publicados en public/demo validan (index y cada lote)", () => {
    expect(validarIndex(leer("index.json"))).toBeNull();
    expect(IDS.length).toBeGreaterThanOrEqual(3);
    for (const id of IDS) expect(validarLote(leer(`${id}/lote.json`))).toBeNull();
  });
  it("aplica las reglas del schema v1.2.0 (score null exige motivo; con valor, motivo null)", () => {
    const l = leer(`${A}/lote.json`);
    const sinMotivo = structuredClone(l); sinMotivo.score.valor = null; sinMotivo.score.motivo_sin_score = null;
    expect(validarLote(sinMotivo)).not.toBeNull();
    const conMotivo = structuredClone(l); conMotivo.score.motivo_sin_score = "algo";
    expect(validarLote(conMotivo)).not.toBeNull();
  });
  it("el motivo es corto y legible", () => {
    const l = leer(`${A}/lote.json`); l.score.valor = "alto";
    const m = validarLote(l)!;
    expect(m).toContain("score");
    expect(m.length).toBeLessThanOrEqual(200);
    const x = leer(`${A}/lote.json`); delete x.zonas;
    expect(validarLote(x)).toContain("zonas");
    expect(validarIndex({})).toContain("generado");
    const f = leer(`${A}/lote.json`); f.generado = "ayer a la tarde";
    expect(validarLote(f)).toContain("generado");          // el formato date-time también se valida (ajv-formats)
    expect(validarIndex(null)).not.toBeNull();
  });
});

describe("cargarDatos", () => {
  it("todo válido: carga los lotes y no hay errores", async () => {
    const d = await cargarDatos();
    expect([...d.lotes.keys()].sort()).toEqual([...IDS].sort());
    expect(d.errores.size).toBe(0);
    expect(d.lotes.get(A)!.score.valor).toBe(leer(`${A}/lote.json`).score.valor);
    expect(d.resumenes.get(A)!.length).toBeGreaterThan(10);
  });
  it("los 3 ejemplos de public/demo se muestran con su score (el del lote.json)", async () => {
    const d = await cargarDatos(); const el = montar();
    vistaInicio(el, d);
    const tarjetas = new Map([...el.querySelectorAll<HTMLElement>(".tarjeta[data-id]")].map((t) => [t.dataset.id!, t.querySelector(".badge-score")!.textContent]));
    for (const id of IDS) {
      const v = leer(`${id}/lote.json`).score.valor;
      expect(tarjetas.get(id)).toBe(v === null ? "Sin dato suficiente" : String(v));
      const det = montar(); vistaDetalle(det, d, id, null);
      expect(det.querySelector(".score-grande .valor")!.textContent).toBe(v === null ? "Sin dato suficiente" : String(v));
    }
    expect(IDS.length).toBeGreaterThanOrEqual(3);
  });
  it("lote inválido: queda como error con motivo, los demás cargan", async () => {
    simular({ [`${B}/lote.json`]: roto(B, (d) => { d.score.valor = "alto"; }) });
    const d = await cargarDatos();
    expect([...d.lotes.keys()].sort()).toEqual([A, C].sort());
    expect(d.errores.get(B)).toMatch(/no cumple el formato esperado.*score/);
  });
  it("lote con campo requerido faltante", async () => {
    simular({ [`${B}/lote.json`]: roto(B, (d) => { delete d.campanias; }) });
    expect((await cargarDatos()).errores.get(B)).toContain("campanias");
  });
  it("lote que da 404", async () => {
    simular({ [`${C}/lote.json`]: { status: 404 } });
    const d = await cargarDatos();
    expect(d.errores.get(C)).toBe("el archivo no existe (404)");
    expect(d.lotes.size).toBe(IDS.length - 1);
  });
  it("lote con 500, JSON roto o error de red", async () => {
    simular({ [`${A}/lote.json`]: { status: 500 }, [`${B}/lote.json`]: { status: 200, body: "{no es json" }, [`${C}/lote.json`]: "red" });
    const d = await cargarDatos();
    expect(d.errores.get(A)).toContain("500");
    expect(d.errores.get(B)).toContain("JSON");
    expect(d.errores.get(C)).toContain("red");
    expect(d.lotes.size).toBe(0);              // todos rotos: igual devuelve datos (la app muestra el índice con errores)
    expect(d.index.lotes.length).toBe(IDS.length);
  });
  it("el id del archivo no coincide con el del índice", async () => {
    simular({ [`${B}/lote.json`]: { status: 200, body: leerTxt(`${A}/lote.json`) } });
    expect((await cargarDatos()).errores.get(B)).toContain("no coincide");
  });
  it("sin resumen (404 o red) el lote igual carga", async () => {
    simular({ [`${A}/resumen.md`]: "red", [`${B}/resumen.md`]: { status: 404 } });
    const d = await cargarDatos();
    expect(d.errores.size).toBe(0);
    expect(d.resumenes.get(A)).toBe("");
    expect(d.resumenes.get(B)).toBe("");
  });
  it("índice inexistente, 500, no-JSON o de red: ErrorIndice con mensaje claro", async () => {
    for (const [r, txt] of [[{ status: 404 }, "404"], [{ status: 500 }, "500"], [{ status: 200, body: "<html>" }, "JSON"], ["red", "red"]] as [Resp, string][]) {
      simular({ "index.json": r });
      const e = await cargarDatos().catch((x) => x);
      expect(e).toBeInstanceOf(ErrorIndice);
      expect(e.message).toContain("index.json");
      expect(e.message).toContain(txt);
    }
  });
  it("índice inválido (sin lotes, campo faltante, tipo erróneo)", async () => {
    const idx = leer("index.json");
    const casos: unknown[] = [{ ...idx, lotes: [] }, (({ generado, ...r }) => r)(idx), { ...idx, lotes: [{ ...idx.lotes[0], area_ha: "mucha" }] }, [], "x"];
    for (const c of casos) {
      simular({ "index.json": { status: 200, body: JSON.stringify(c) } });
      const e = await cargarDatos().catch((x) => x);
      expect(e).toBeInstanceOf(ErrorIndice);
      expect(e.message).toContain("formato esperado");
    }
  });
});

describe("vistas con lotes inválidos (mezcla de válidos e inválidos)", () => {
  async function mezcla() {
    simular({ [`${B}/lote.json`]: roto(B, (d) => { d.score.valor = "alto"; }), [`${C}/lote.json`]: { status: 404 } });
    return cargarDatos();
  }
  it("inicio: tarjetas de error con el motivo + tarjeta normal del lote bueno", async () => {
    const d = await mezcla(); const el = montar();
    expect(() => vistaInicio(el, d)).not.toThrow();
    expect(el.querySelectorAll(".tarjeta:not(.tarjeta-error)").length).toBe(1);
    const err = [...el.querySelectorAll(".tarjeta-error")];
    expect(err.length).toBe(2);
    expect(err.map((x) => x.textContent).join(" ")).toContain("Este lote no se pudo cargar: el archivo no existe (404)");
    expect(el.textContent).toContain("Este lote no se pudo cargar: no cumple el formato esperado");
    expect(el.textContent).toMatch(/1\s*lotes/);   // el resumen cuenta solo los válidos
  });
  it("inicio con TODOS los lotes rotos no crashea (mapa vacío)", async () => {
    simular(Object.fromEntries(IDS.map((i) => [`${i}/lote.json`, { status: 404 }])));
    const d = await cargarDatos(); const el = montar();
    expect(() => vistaInicio(el, d)).not.toThrow();
    expect(el.querySelectorAll(".tarjeta-error").length).toBe(IDS.length);
    expect(() => vistaComparar(montar(), d, null)).not.toThrow();
    expect(() => vistaComo(montar(), d)).not.toThrow();
  });
  it("detalle e informe de un lote roto: mensaje, sin crash; el del lote bueno sigue andando", async () => {
    const d = await mezcla();
    for (const vista of [(e: HTMLElement) => vistaDetalle(e, d, B, null), (e: HTMLElement) => vistaInforme(e, d, B)]) {
      const el = montar();
      expect(() => vista(el)).not.toThrow();
      expect(el.textContent).toContain("Este lote no se pudo cargar: no cumple el formato esperado");
      expect(el.querySelector('a[href="#/"]')).not.toBeNull();
    }
    const el = montar(); vistaDetalle(el, d, C, null);
    expect(el.textContent).toContain("el archivo no existe (404)");
    const ok = montar(); vistaDetalle(ok, d, A, null);
    expect(ok.querySelector(".score-card")).not.toBeNull();
    expect(ok.querySelectorAll(".chip-nav").length).toBe(0);     // no ofrece navegar a lotes rotos
    const inf = montar(); vistaInforme(inf, d, A);
    expect(inf.querySelector(".informe")).not.toBeNull();
  });
  it("id que no existe en el índice", async () => {
    const d = await cargarDatos(); const el = montar();
    vistaDetalle(el, d, "no_existe", null);
    expect(el.textContent).toContain("No existe el lote");
  });
  it("comparar: ignora los rotos, los avisa y compara los válidos", async () => {
    const d = await mezcla(); const el = montar();
    expect(() => vistaComparar(el, d, `${A},${B},${C}`)).not.toThrow();
    expect(el.querySelectorAll(".aviso-lote.error").length).toBe(2);
    expect(el.textContent).toContain("Este lote no se pudo cargar");
    expect(el.querySelectorAll("table.comp-tabla thead th").length).toBe(2);   // vacío + 1 lote válido
  });
  it("cómo funciona sigue andando con el primer lote roto", async () => {
    simular({ [`${IDS[0]}/lote.json`]: { status: 404 } });
    const d = await cargarDatos(); const el = montar();
    vistaComo(el, d);
    expect(el.querySelectorAll("table.como tbody tr").length).toBeGreaterThan(0);
  });
});

describe("main.ts (arranque de la app)", () => {
  async function arrancar() {
    document.body.innerHTML = `<div id="app"></div>`;
    location.hash = "";
    await import("../src/main");
    await vi.waitFor(() => expect(document.querySelector("#app")!.innerHTML.length).toBeGreaterThan(50), { timeout: 4000 });
    return document.querySelector<HTMLElement>("#app")!;
  }
  it("índice caído: mensaje claro con el motivo y botón Reintentar (no pantalla en blanco)", async () => {
    simular({ "index.json": { status: 404 } });
    const app = await arrancar();
    expect(app.textContent).toContain("No se pudieron cargar los datos");
    expect(app.textContent).toContain("index.json");
    expect(app.textContent).toContain("404");
    expect(app.querySelector("button")!.textContent).toBe("Reintentar");
  });
  it("índice inválido: mensaje claro", async () => {
    simular({ "index.json": { status: 200, body: "{}" } });
    const app = await arrancar();
    expect(app.textContent).toContain("no tiene el formato esperado");
  });
  it("un lote roto no impide que la app arranque con el resto", async () => {
    simular({ [`${B}/lote.json`]: { status: 404 } });
    const app = await arrancar();
    await vi.waitFor(() => expect(app.querySelectorAll(".tarjeta").length).toBe(IDS.length));
    expect(app.querySelectorAll(".tarjeta-error").length).toBe(1);
    expect(app.textContent).toContain("Este lote no se pudo cargar");
    expect(app.querySelector(".top")).not.toBeNull();       // header/navegación presentes
  });
});
