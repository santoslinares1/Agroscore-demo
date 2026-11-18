import type { Index, Lote } from "./types";
import { validarIndex, validarLote } from "./validacion";

const BASE = "demo/";
export const url = (id: string, f: string) => `${BASE}${id}/${f}`;

/** El índice no se pudo leer o no es válido: sin índice no hay app, pero se muestra un mensaje claro. */
export class ErrorIndice extends Error {
  constructor(msg: string) { super(msg); this.name = "ErrorIndice"; }
}

class ErrorCarga extends Error {}

async function getJSON(p: string): Promise<unknown> {
  let r: Response;
  try { r = await fetch(BASE + p, { cache: "no-cache" }); }
  catch { throw new ErrorCarga("error de red al leer el archivo"); }
  if (!r.ok) throw new ErrorCarga(r.status === 404 ? "el archivo no existe (404)" : `el servidor respondió ${r.status}`);
  try { return await r.json(); }
  catch { throw new ErrorCarga("el archivo no es un JSON válido"); }
}

export interface Datos {
  index: Index;
  /** Solo los lotes que cargaron Y validan contra el schema. */
  lotes: Map<string, Lote>;
  resumenes: Map<string, string>;
  /** id → motivo corto, de los lotes del índice que NO se pudieron cargar o no validan. */
  errores: Map<string, string>;
}

export const textoErrorLote = (motivo: string) => `Este lote no se pudo cargar: ${motivo}`;

async function cargarLote(id: string): Promise<{ lote: Lote; resumen: string }> {
  const raw = await getJSON(`${id}/lote.json`);
  const motivo = validarLote(raw);
  if (motivo) throw new ErrorCarga(`no cumple el formato esperado (${motivo})`);
  const lote = raw as Lote;
  if (lote.id !== id) throw new ErrorCarga(`el id del archivo («${lote.id}») no coincide con el del índice`);
  let resumen = "";
  try {
    const r = await fetch(url(id, lote.resumen_md), { cache: "no-cache" });
    resumen = r.ok ? await r.text() : "";
  } catch { /* el resumen es opcional: se muestra vacío */ }
  return { lote, resumen };
}

export async function cargarDatos(): Promise<Datos> {
  let raw: unknown;
  try { raw = await getJSON("index.json"); }
  catch (e) { throw new ErrorIndice(`No se pudo leer el índice de lotes (index.json): ${(e as Error).message}.`); }
  const motivo = validarIndex(raw);
  if (motivo) throw new ErrorIndice(`El índice de lotes (index.json) no tiene el formato esperado: ${motivo}.`);
  const index = raw as Index;

  const lotes = new Map<string, Lote>();
  const resumenes = new Map<string, string>();
  const errores = new Map<string, string>();
  // allSettled: un lote roto o que no carga no tumba a los demás
  const res = await Promise.allSettled(index.lotes.map((l) => cargarLote(l.id)));
  res.forEach((r, i) => {
    const id = index.lotes[i].id;
    if (r.status === "fulfilled") { lotes.set(id, r.value.lote); resumenes.set(id, r.value.resumen); }
    else errores.set(id, r.reason instanceof ErrorCarga ? r.reason.message : `error inesperado (${String(r.reason)})`);
  });
  return { index, lotes, resumenes, errores };
}

export const AVISO_EJEMPLO = "LOTE DE EJEMPLO – datos de ejemplo";
