// @vitest-environment jsdom
// M3 (verificación 18/11): el rótulo y la explicación del vigor salen de score.vigor_base de cada lote, no de la
// versión ni de un texto fijo. "Cómo funciona" describe lo que muestran los lotes de la demo.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { etiquetaComp, explicacion } from "../src/textos";
import { bloqueScore } from "../src/views/detalle";
import { vistaComo } from "../src/views/como";
import { vistaComparar } from "../src/views/comparar";
import type { Datos } from "../src/data";
import type { Lote } from "../src/types";

const DEMO = resolve(__dirname, "../public/demo");
const base = (id = "ejemplo_roca_norte"): Lote => JSON.parse(readFileSync(resolve(DEMO, id, "lote.json"), "utf-8"));
const conBase = (l: Lote, vb: "evi" | "ndvi" | "combinado" | null | undefined, etiquetaVieja?: string): Lote => {
  const c = structuredClone(l);
  if (vb === undefined) delete c.score.vigor_base; else c.score.vigor_base = vb;
  if (etiquetaVieja) c.score.componentes = c.score.componentes.map((k) => (k.clave === "vigor_historico" ? { ...k, etiqueta: etiquetaVieja } : k));
  return c;
};
const vigor = (l: Lote) => l.score.componentes.find((c) => c.clave === "vigor_historico")!;
function datos(lotes: Lote[]): Datos {
  const index = { generado: "x", score_version: "1.2.0", ejemplo: true,
    lotes: lotes.map((l) => ({ id: l.id, nombre: l.nombre, localidad: l.localidad, area_ha: l.area_ha, score: l.score.valor,
      centroide: l.centroide, ejemplo: l.ejemplo })) };
  return { index, errores: new Map(), lotes: new Map(lotes.map((l) => [l.id, l])), resumenes: new Map() } as Datos;
}
const montar = () => { const el = document.createElement("div"); document.body.replaceChildren(el); return el; };

describe("etiqueta del vigor según score.vigor_base", () => {
  it("los ejemplos publicados declaran vigor_base y se rotulan con ese índice", () => {
    for (const id of ["ejemplo_roca_norte", "ejemplo_roca_sur", "ejemplo_rio_cuarto_este"]) {
      const l = base(id);
      expect(l.score.vigor_base, id).toBe("ndvi");
      expect(etiquetaComp(vigor(l), l.score)).toBe("Vigor del cultivo (NDVI)");
    }
  });

  it("EVI aunque la etiqueta guardada diga NDVI (JSON anterior inconsistente)", () => {
    const l = conBase(base(), "evi", "Vigor histórico (NDVI)");
    expect(etiquetaComp(vigor(l), l.score)).toBe("Vigor del cultivo (EVI)");
    expect(explicacion("vigor_historico", l.score)!.que).toContain("EVI");
    const html = bloqueScore(l);
    expect(html).toContain("Vigor del cultivo (EVI)");
    expect(html).not.toContain("Vigor del cultivo (NDVI)");
  });

  it("NDVI: la explicación no habla de EVI", () => {
    const l = base();
    expect(explicacion("vigor_historico", l.score)!.que).toContain("NDVI");
    expect(explicacion("vigor_historico", l.score)!.que).not.toContain("EVI");
    expect(bloqueScore(l)).toContain("Vigor del cultivo (NDVI)");
  });

  it("sin vigor_base (JSON viejo): rótulo genérico, sin afirmar un índice", () => {
    const l = conBase(base(), undefined);
    expect(etiquetaComp(vigor(l), l.score)).toBe("Vigor del cultivo");
    expect(etiquetaComp({ clave: "suelo", etiqueta: "Suelo", valor: 1, peso: 0.15 }, l.score)).toBe("Suelo");
  });
});

describe("Cómo funciona y Comparar coherentes con los lotes mostrados", () => {
  it("todos NDVI → la tabla dice NDVI y no EVI", () => {
    const el = montar();
    vistaComo(el, datos([base("ejemplo_roca_norte"), base("ejemplo_roca_sur")]));
    const fila = [...el.querySelectorAll("table.como tbody tr")].find((tr) => tr.textContent!.includes("Vigor"))!;
    expect(fila.querySelector("th")!.textContent).toBe("Vigor del cultivo (NDVI)");
    expect(fila.textContent).not.toContain("EVI");
    expect(el.textContent).toContain("versión 1.2.0");
    expect(el.textContent).toContain("Confianza alta");
  });

  it("mezcla EVI y NDVI → la tabla lo dice con cuántos lotes de cada uno", () => {
    const el = montar();
    const a = base("ejemplo_roca_norte"), b = conBase(base("ejemplo_roca_sur"), "evi");
    vistaComo(el, datos([a, b]));
    const fila = [...el.querySelectorAll("table.como tbody tr")].find((tr) => tr.textContent!.includes("Vigor"))!;
    expect(fila.querySelector("th")!.textContent).toBe("Vigor del cultivo");
    expect(fila.textContent).toContain("1 con NDVI");
    expect(fila.textContent).toContain("1 con EVI");

    const el2 = montar();
    vistaComparar(el2, datos([a, b]), `${a.id},${b.id}`);
    expect(el2.textContent).toContain("(EVI)");
    expect(el2.textContent).toContain("(NDVI)");
  });
});
