/** Cliente del servidor local opcional (pipeline/server.py). Nunca inventa resultados. */
import type { LoteCargado } from "./geo";
import { aGeoJSONPipeline } from "./geo";

export const BACKEND = localStorage.getItem("agroscore-backend") ?? "http://127.0.0.1:8787";

export interface Salud { ok: boolean; gee_ok: boolean; gee_detalle: string; verificando?: boolean; version?: string }
export interface Trabajo { id: string; lote_id: string; estado: "en_cola" | "procesando" | "listo" | "error"; paso: string; progreso: number; error?: string | null }

async function conTiempo(url: string, init: RequestInit = {}, ms = 1500): Promise<Response> {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), ms);
  try { return await fetch(url, { ...init, signal: c.signal }); } finally { clearTimeout(t); }
}

/** null = no hay servidor local corriendo. */
export async function detectarBackend(refrescar = false): Promise<Salud | null> {
  try {
    const r = await conTiempo(`${BACKEND}/api/salud${refrescar ? "?refrescar=1" : ""}`, {}, 2500);
    return r.ok ? ((await r.json()) as Salud) : null;
  } catch { return null; }
}

export async function enviarLote(l: LoteCargado): Promise<Trabajo> {
  const r = await conTiempo(`${BACKEND}/api/lotes`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feature: aGeoJSONPipeline([l]).features[0] }),
  }, 15000);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error([j.error ?? `El servidor respondió ${r.status}`, j.gee_detalle].filter(Boolean).join(" Detalle: "));
  return j as Trabajo;
}

export async function estadoTrabajo(id: string): Promise<Trabajo> {
  const r = await conTiempo(`${BACKEND}/api/trabajos/${encodeURIComponent(id)}`, {}, 5000);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error ?? `El servidor respondió ${r.status}`);
  return j as Trabajo;
}
