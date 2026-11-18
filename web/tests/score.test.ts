// @vitest-environment jsdom
// Score v1.2.0: «Sin dato suficiente» (score null) y score parcial: nada debe romper ni mostrar un número inventado.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { scoreTxt, SIN_SCORE } from "../src/fmt";
import { fraseRotacion, rotacionSinDato, ultimoManiTxt } from "../src/textos";
import { bloqueScore, lineaTiempo } from "../src/views/detalle";
import { vistaInicio } from "../src/views/inicio";
import { vistaComparar } from "../src/views/comparar";
import { vistaDetalle } from "../src/views/detalle";
import { vistaInforme } from "../src/views/informe";
import type { Datos } from "../src/data";
import type { Lote } from "../src/types";

const DEMO = resolve(__dirname, "../public/demo");
const leer = <T,>(p: string): T => JSON.parse(readFileSync(resolve(DEMO, p), "utf-8")) as T;
const base = (): Lote => leer<Lote>("ejemplo_roca_norte/lote.json");

function sinScore(l: Lote): Lote {
  const c = structuredClone(l);
  c.score = { ...c.score, valor: null, confianza: null, componentes_usados: [], reponderado: false,
    motivo_sin_score: "Faltan datos satelitales suficientes: se necesitan al menos 3 campañas con NDVI y hay 0.",
    componentes: c.score.componentes.map((k) => ({ ...k, peso_efectivo: null })) };
  return c;
}
function parcial(l: Lote): Lote {
  const c = structuredClone(l);
  c.score = { ...c.score, reponderado: true, cobertura: 0.85, componentes_sin_dato: ["suelo"] };
  c.score.componentes = c.score.componentes.map((k) => (k.clave === "suelo" ? { ...k, valor: null, peso_efectivo: null }
    : { ...k, peso_efectivo: k.peso / 0.85 }));
  return c;
}
function rotacionInsuficiente(l: Lote): Lote {
  const c = structuredClone(l);
  c.rotacion = { ...c.rotacion, ultimo_mani: null, campanias_desde_mani: null, veces_mani_ultimas_5: 0,
    campanias_con_dato_ultimas_5: 1, campanias_ventana: 5, confianza_rotacion: "insuficiente" };
  c.score.componentes = c.score.componentes.map((k) => (k.clave === "rotacion_mani" ? { ...k, valor: null } : k));
  return c;
}
function datos(lotes: Lote[]): Datos {
  const index = { generado: "x", score_version: "1.2.0", ejemplo: true,
    lotes: lotes.map((l) => ({ id: l.id, nombre: l.nombre, localidad: l.localidad, area_ha: l.area_ha, score: l.score.valor,
      centroide: l.centroide, ejemplo: l.ejemplo })) };
  return { index, errores: new Map<string, string>(), lotes: new Map(lotes.map((l) => [l.id, l])), resumenes: new Map(lotes.map((l) => [l.id, "Resumen de prueba."])) };
}

describe("helpers de texto", () => {
  it("scoreTxt: número o «Sin dato suficiente»", () => {
    expect(scoreTxt(83)).toBe("83");
    expect(scoreTxt(0)).toBe("0");
    expect(scoreTxt(null)).toBe(SIN_SCORE);
    expect(scoreTxt(undefined)).toBe("Sin dato suficiente");
  });
  it("rotación sin dato suficiente ≠ «sin registro» y no cuenta como mejor valor", () => {
    const l = rotacionInsuficiente(base());
    expect(rotacionSinDato(l)).toBe(true);
    expect(ultimoManiTxt(l)).toBe("Sin dato suficiente");
    expect(fraseRotacion(l)).toContain("no alcanza para evaluar la rotación");
    const ok = base();
    expect(rotacionSinDato(ok)).toBe(false);
  });
  it("sin maní con dato completo sí es «sin registro»", () => {
    const l = structuredClone(base());
    l.rotacion = { ...l.rotacion, ultimo_mani: null, campanias_desde_mani: null, confianza_rotacion: "completa" };
    expect(ultimoManiTxt(l)).toBe("sin registro");
  });
});

describe("bloqueScore", () => {
  it("score null: muestra «Sin dato suficiente» + motivo, sin «/100» ni «s/d»", () => {
    const h = bloqueScore(sinScore(base()));
    expect(h).toContain("Sin dato suficiente");
    expect(h).toContain("No se calculó un score total");
    expect(h).toContain("hay 0");
    expect(h).not.toContain("/100");
  });
  it("score parcial: avisa cobertura y usa peso efectivo", () => {
    const h = bloqueScore(parcial(base()));
    expect(h).toContain("Score parcial");
    expect(h).toContain("85");
    expect(h).toContain("Suelo");
  });
  it("score completo: sin avisos", () => {
    const h = bloqueScore(base());
    expect(h).not.toContain("aviso-score");
    expect(h).toContain("/100");
  });
  it("escapa el motivo (viene del JSON)", () => {
    const l = sinScore(base());
    l.score.motivo_sin_score = "<img src=x onerror=alert(1)>";
    const h = bloqueScore(l);
    expect(h).not.toContain("<img src=x");
    expect(h).toContain("&lt;img");
  });
  it("lineaTiempo no rompe con score null", () => {
    expect(lineaTiempo(sinScore(base()))).toContain("timeline");
  });
});

describe("vistas con score null / parcial (jsdom: nada crashea)", () => {
  const l0 = base();
  const lotes = [sinScore(l0), parcial(structuredClone({ ...leer<Lote>("ejemplo_roca_sur/lote.json") })), rotacionInsuficiente(leer<Lote>("ejemplo_rio_cuarto_este/lote.json"))];
  const d = datos(lotes);

  it("inicio", () => {
    const el = document.createElement("div"); document.body.appendChild(el);
    vistaInicio(el, d);
    expect(el.textContent).toContain("Sin dato suficiente");
    expect(el.querySelectorAll(".tarjeta").length).toBe(3);
  });
  it("detalle (score null, parcial y rotación insuficiente)", () => {
    for (const l of lotes) {
      const el = document.createElement("div"); document.body.appendChild(el);
      expect(() => vistaDetalle(el, d, l.id, null)).not.toThrow();
      expect(el.querySelector(".score-card")).not.toBeNull();
    }
    const el = document.createElement("div");
    vistaDetalle(el, d, lotes[0].id, null);
    expect(el.textContent).toContain("score sin dato suficiente");
    expect(el.textContent).not.toMatch(/score \d+\/100/);
  });
  it("comparar", () => {
    const el = document.createElement("div"); document.body.appendChild(el);
    expect(() => vistaComparar(el, d, lotes.map((l) => l.id).join(","))).not.toThrow();
    expect(el.textContent).toContain("Sin dato suficiente");
    expect(el.textContent).toContain("parcial");
  });
  it("informe imprimible", () => {
    const el = document.createElement("div"); document.body.appendChild(el);
    expect(() => vistaInforme(el, d, lotes[0].id)).not.toThrow();
    expect(el.textContent).toContain("Sin dato suficiente");
  });
});

describe("datos publicados en public/demo (score v1.2.0)", () => {
  it("cada lote tiene score numérico o null con motivo; los campos nuevos están presentes", () => {
    const idx = leer<{ lotes: { id: string; score: number | null }[] }>("index.json");
    expect(idx.lotes.length).toBeGreaterThan(0);
    for (const it of idx.lotes) {
      const l = leer<Lote>(`${it.id}/lote.json`);
      expect(l.score.version).toBe("1.2.0");
      expect(l.score.valor).toBe(it.score);
      expect(typeof l.score.reponderado).toBe("boolean");
      expect(typeof l.score.cobertura).toBe("number");
      if (l.score.valor === null) expect(l.score.motivo_sin_score).toBeTruthy();
      else expect(l.score.motivo_sin_score ?? null).toBeNull();
    }
  });
});
