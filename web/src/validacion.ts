// Validación en el navegador de index.json y lote.json contra LOS MISMOS schemas del pipeline (sin duplicarlos):
// el plugin `vite-plugin-validadores.ts` lee pipeline/agroscore/schema/*.schema.json y los compila con Ajv a código JS
// en el build (módulo virtual). Si el pipeline cambia el contrato, la web lo sigue sin tocar nada acá.
import { validarIndexSchema, validarLoteSchema } from "virtual:validadores";

interface ErrorAjv { instancePath: string; keyword: string; message?: string; params: Record<string, unknown> }
type Validador = ((x: unknown) => boolean) & { errors?: ErrorAjv[] | null };

/** Primer error del schema como frase corta y legible (≤ 200 caracteres). */
export function motivoCorto(errs: ErrorAjv[] | null | undefined): string {
  const e = errs?.[0];
  if (!e) return "no cumple el formato esperado";
  const ruta = e.instancePath ? e.instancePath.replace(/^\//, "").replace(/\//g, " › ") : "(raíz)";
  const p = e.params;
  const extra = e.keyword === "additionalProperties" ? ` «${String(p.additionalProperty)}»`
    : e.keyword === "required" ? ` «${String(p.missingProperty)}»`
    : e.keyword === "enum" ? `: ${(p.allowedValues as unknown[]).map(String).join(" | ")}` : "";
  const s = `${ruta} ${e.message ?? "no es válido"}${extra}`;
  return s.length > 200 ? `${s.slice(0, 197)}…` : s;
}

const correr = (v: Validador, x: unknown): string | null => (v(x) ? null : motivoCorto(v.errors));

/** null si valida; si no, el motivo corto. */
export const validarIndex = (x: unknown): string | null => correr(validarIndexSchema as Validador, x);
export const validarLote = (x: unknown): string | null => correr(validarLoteSchema as Validador, x);
