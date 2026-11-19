export const CULTIVOS: Record<string, string> = {
  mani: "Maní", soja: "Soja", maiz: "Maíz", girasol: "Girasol", sorgo: "Sorgo", trigo: "Trigo",
  pastura: "Pastura", mixto: "Mixto", otros: "Otros", otros_cultivos: "Otros cultivos",
  otros_posible_mani: "Otros (maní no separable)", agricultura: "Agricultura (sin detalle)",
  cultivo_temporario: "Cultivo temporario (sin detalle)", mosaico_agropecuario: "Mosaico agropecuario",
  maiz_2da: "Maíz de 2da", soja_2da: "Soja de 2da", no_agricola: "No agrícola", forestacion: "Forestación", pastizal: "Pastizal",
  monte: "Monte", agua: "Agua", urbano: "Urbano", cultivo_perenne: "Cultivo perenne",
};
export const cultivoNombre = (c: string | null) => (c ? CULTIVOS[c] ?? c : "Sin dato");

export function num(v: number | null | undefined, dec = 2, suf = ""): string {
  if (v === null || v === undefined) return "s/d";
  return v.toLocaleString("es-AR", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + suf;
}

export const SIN_SCORE = "Sin dato suficiente";
/** Texto del score: número, o «Sin dato suficiente» si el pipeline no tuvo datos mínimos (valor null). */
export const scoreTxt = (v: number | null | undefined): string => (v === null || v === undefined ? SIN_SCORE : String(v));

export function colorScore(s: number | null): string {
  if (s === null) return "#9e9e9e";
  if (s >= 75) return "#1a9641";
  if (s >= 60) return "#a6d96a";
  if (s >= 45) return "#fdae61";
  return "#d7191c";
}

/** Texto sobre el color del score: en los tonos claros el blanco no se lee al sol. */
export function textoScore(s: number | null): string {
  if (s !== null && s >= 45 && s < 75) return "#111713";
  return "#fffdf8";
}

/**
 * Lectura en criollo de las mismas franjas que ya pinta el mapa (75 / 60 / 45).
 * No es un dato nuevo: describe el número que ya calculó el pipeline.
 */
export function fraseScore(v: number | null): string {
  if (v === null) return "No alcanza con los datos para resumir el lote en un número.";
  if (v >= 75) return "Número alto: el lote se ve favorable para alquilar y sembrar maní.";
  if (v >= 60) return "Número medio-alto: mirá el detalle antes de decidir.";
  if (v >= 45) return "Número intermedio: hay puntos flojos para revisar.";
  return "Número bajo: revisá los riesgos antes de alquilar.";
}

export function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}

/** Markdown mínimo: párrafos, **negrita**, _itálica_. */
export function md(texto: string): string {
  return texto.trim().split(/\n\s*\n/).map((p) => {
    let h = esc(p.replace(/^#+\s*/, "")).replace(/\n/g, " ");
    h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|\s)_(.+?)_(?=\s|$|[.,;])/g, "$1<em>$2</em>");
    return `<p>${h}</p>`;
  }).join("");
}
