import type { Componente, Lote, Score } from "./types";

export type VigorBase = "evi" | "combinado" | "ndvi";
/** Con qué índice se calculó el vigor (score.vigor_base). La versión del score sola no alcanza: la 1.2.0 usa EVI si
 *  hay campañas con EVI y NDVI si no (p. ej. datos de ejemplo). */
export const INDICE_VIGOR: Record<VigorBase, string> = { evi: "EVI", combinado: "EVI + NDVI", ndvi: "NDVI" };
const QUE_VIGOR: Record<VigorBase | "sd", string> = {
  evi: "Qué tan verde y vigoroso estuvo el cultivo en el pico de cada campaña (índice EVI máximo, satélite Sentinel-2; referencias provisorias, sin calibrar con rindes).",
  combinado: "Qué tan verde y vigoroso estuvo el cultivo en el pico de cada campaña (combinación de los índices EVI y NDVI máximos, satélite Sentinel-2; referencias del EVI provisorias).",
  ndvi: "Qué tan verde y vigoroso estuvo el cultivo en el pico de cada campaña (índice NDVI máximo, satélite Sentinel-2).",
  sd: "Qué tan verde y vigoroso estuvo el cultivo en el pico de cada campaña (índice de vegetación máximo, satélite Sentinel-2).",
};
export const vigorBase = (s: Score): VigorBase | null =>
  s.vigor_base === "evi" || s.vigor_base === "combinado" || s.vigor_base === "ndvi" ? s.vigor_base : null;

/** Etiqueta del componente. La del vigor sale de score.vigor_base (no de la etiqueta guardada, que en JSON
 *  anteriores podía decir NDVI aunque el vigor fuera EVI). */
export function etiquetaComp(c: Componente, s: Score): string {
  if (c.clave === "vigor_historico") {
    const vb = vigorBase(s);
    return vb ? `Vigor histórico (${INDICE_VIGOR[vb]})` : "Vigor histórico";
  }
  return c.etiqueta ?? c.clave;
}

/** Explicación del componente para un lote (la del vigor depende del índice usado). */
export function explicacion(clave: string, s?: Score): { que: string; alto: string } | undefined {
  const ex = EXPLICACION[clave];
  if (!ex || clave !== "vigor_historico") return ex;
  return { ...ex, que: QUE_VIGOR[(s && vigorBase(s)) ?? "sd"] };
}

/** Explicación en castellano llano de cada componente del score (no contiene cifras). Para el vigor usar explicacion(). */
export const EXPLICACION: Record<string, { que: string; alto: string }> = {
  vigor_historico: {
    que: QUE_VIGOR.sd,
    alto: "Más alto = el lote viene produciendo bien.",
  },
  estabilidad: {
    que: "Si el lote rinde parecido todos los años o tiene altibajos fuertes entre campañas.",
    alto: "Más alto = más parejo y previsible.",
  },
  riesgo_hidrico: {
    que: "Cuánta superficie se vio con agua y con qué frecuencia (radar Sentinel-1 confirmado con imagen óptica o registro histórico JRC).",
    alto: "Más alto = menos riesgo de anegamiento.",
  },
  suelo: {
    que: "Textura (arena / arcilla) y materia orgánica del suelo según SoilGrids. Para maní suma un suelo suelto, franco-arenoso.",
    alto: "Más alto = suelo más apto para maní.",
  },
  rotacion_mani: {
    que: "Cuántas campañas pasaron desde el último maní y cuántas veces se hizo maní en las últimas 5. Repetir maní aumenta el riesgo de enfermedades como el carbón.",
    alto: "Más alto = mejor rotación para alquilar y sembrar maní.",
  },
};

export type Nivel = "bien" | "atencion" | "riesgo" | "sd";
/** Semáforo de la demo a partir del valor 0–1 del componente (criterio visual, no agronómico). */
export function nivel(v: number | null): Nivel {
  if (v === null) return "sd";
  if (v >= 0.75) return "bien";
  if (v >= 0.5) return "atencion";
  return "riesgo";
}
export const NIVEL_TXT: Record<Nivel, string> = { bien: "Bien", atencion: "Atención", riesgo: "Riesgo", sd: "Sin dato" };

export const comp = (l: Lote, clave: string): Componente | undefined => l.score.componentes.find((c) => c.clave === clave);

/** true si la rotación de maní no se pudo evaluar (dato de maní insuficiente): no es lo mismo que «sin maní». */
export const rotacionSinDato = (l: Lote): boolean =>
  l.rotacion.confianza_rotacion === "insuficiente" || comp(l, "rotacion_mani")?.valor === null;
export const ultimoManiTxt = (l: Lote): string =>
  rotacionSinDato(l) && l.rotacion.ultimo_mani === null ? "Sin dato suficiente" : (l.rotacion.ultimo_mani ?? "sin registro");

export function fraseRotacion(l: Lote): string {
  const r = l.rotacion;
  const rec = r.anios_recomendados;
  const cd = r.campanias_con_dato_ultimas_5, vt = r.campanias_ventana ?? 5;
  if (rotacionSinDato(l) && r.confianza_rotacion !== "insuficiente")
    return `Hay dato de maní en ${cd ?? 0} de las últimas ${vt} campañas: no se evaluó la rotación (riesgo de carbón sin determinar).`;
  if (r.confianza_rotacion === "insuficiente")
    return `Solo hay dato de maní en ${cd ?? 0} de las últimas ${vt} campañas: no alcanza para evaluar la rotación (riesgo de carbón sin determinar).`;
  const aviso = r.confianza_rotacion === "parcial" && cd !== undefined ? ` (dato de maní en ${cd} de ${vt} campañas)` : "";
  if (r.ultimo_mani === null) return `No hay maní registrado en las campañas con dato${aviso}.`;
  const n = r.campanias_desde_mani ?? 0;
  const base = n === 0 ? `La última campaña (${r.ultimo_mani}) fue maní` : `El último maní fue en ${r.ultimo_mani}, hace ${n} campaña${n === 1 ? "" : "s"}`;
  if (rec === undefined) return base + aviso + ".";
  return n < rec
    ? `${base}: menos de las ${rec} campañas sin maní que pide el criterio del score${aviso}.`
    : `${base}: cumple las ${rec} campañas sin maní que pide el criterio del score${aviso}.`;
}
