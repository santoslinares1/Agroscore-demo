import type { LoteCargado } from "./geo";

const CLAVE = "agroscore-lotes-cargados-v1";

export function leerLotes(): LoteCargado[] {
  try { const v = JSON.parse(localStorage.getItem(CLAVE) ?? "[]"); return Array.isArray(v) ? v : []; }
  catch { return []; }
}
export function guardarLotes(l: LoteCargado[]) { localStorage.setItem(CLAVE, JSON.stringify(l)); }
export function actualizarLote(id: string, cambios: Partial<LoteCargado>) {
  guardarLotes(leerLotes().map((l) => (l.id === id ? { ...l, ...cambios } : l)));
}
