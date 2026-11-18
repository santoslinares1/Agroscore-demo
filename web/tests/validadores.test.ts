// C1: el módulo `virtual:validadores` tiene que ser ESM puro para el navegador (sin require ni imports externos).
// vitest corre en Node, donde `require` existe: por eso estos tests evalúan el código generado como un módulo ESM
// aislado (en Node ESM `require` NO está definido, igual que en el navegador).
import { describe, expect, it } from "vitest";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { generarCodigoValidadores, tieneRequire } from "../vite-plugin-validadores";

const DEMO = join(__dirname, "../public/demo");

describe("validadores generados (virtual:validadores)", () => {
  it("no contienen require( ni imports: corren en el navegador", async () => {
    const codigo = await generarCodigoValidadores();
    expect(tieneRequire(codigo)).toBe(false);
    expect(codigo).not.toMatch(/\brequire\s*\(/);
    expect(codigo).not.toMatch(/^\s*import\s/m);
    expect(codigo).toMatch(/export\s*\{[^}]*validarIndexSchema/);
  });

  it("evaluados como ESM sin require validan los datos publicados y rechazan uno roto", async () => {
    const dir = mkdtempSync(join(tmpdir(), "validadores-"));
    const f = join(dir, "validadores.mjs");
    writeFileSync(f, await generarCodigoValidadores());
    const m = await import(/* @vite-ignore */ pathToFileURL(f).href);
    const idx = JSON.parse(readFileSync(join(DEMO, "index.json"), "utf-8"));
    expect(m.validarIndexSchema(idx)).toBe(true);
    for (const l of idx.lotes) {
      const lote = JSON.parse(readFileSync(join(DEMO, l.id, "lote.json"), "utf-8"));
      expect(m.validarLoteSchema(lote), l.id).toBe(true);
      expect(m.validarLoteSchema({ ...lote, generado: "ayer" })).toBe(false);   // date-time (ajv-formats)
      expect(m.validarLoteSchema({ ...lote, nombre: "" })).toBe(false);          // minLength (ucs2length)
    }
  });

  it("el detector de require funciona", () => {
    expect(tieneRequire('var x = require("ajv/dist/runtime/ucs2length").default;')).toBe(true);
    expect(tieneRequire("const y = require_ucs2length(); obj.require (1)")).toBe(false);
  });
});
