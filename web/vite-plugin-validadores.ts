// Compila a JavaScript, en tiempo de build, los validadores Ajv de index.schema.json y lote.schema.json
// (los MISMOS del pipeline). El navegador solo recibe código de validación listo (sin el compilador de Ajv).
// Módulo virtual: `virtual:validadores`.
//
// Ojo (C1, verificación 18/11): el código "standalone" de Ajv referencia sus funciones de runtime con `require(...)`
// (p. ej. `require("ajv/dist/runtime/ucs2length")` por `minLength` y `require("ajv-formats/dist/formats")` por
// `format: date-time`) aunque se pida `esm: true`. En el navegador eso tira `ReferenceError: require is not defined` y la
// app no arranca. Por eso el código generado se empaqueta con esbuild (bundle ESM para navegador, sin imports externos):
// las funciones de runtime quedan inlineadas y el resultado es ESM puro. Si quedara un `require(`, el build falla.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import standaloneCode from "ajv/dist/standalone/index.js";
import { build } from "esbuild";
import type { Plugin } from "vite";

export const SCHEMAS_DIR = resolve(__dirname, "../pipeline/agroscore/schema");
export const ARCHIVOS_SCHEMA = ["index.schema.json", "lote.schema.json"].map((f) => resolve(SCHEMAS_DIR, f));
const ID = "virtual:validadores";

/** true si el código todavía depende de CommonJS (no corre como ESM en el navegador). */
export function tieneRequire(codigo: string): boolean {
  return /(^|[^\w$.])require\s*\(/.test(codigo) || /Dynamic require of/.test(codigo);
}

/** Código ESM puro (sin require ni imports) con `validarIndexSchema` y `validarLoteSchema`. */
export async function generarCodigoValidadores(): Promise<string> {
  const ajv = new Ajv2020({ strict: false, allErrors: false, code: { source: true, esm: true } });
  addFormats(ajv);
  const [sIndex, sLote] = ARCHIVOS_SCHEMA.map((f) => JSON.parse(readFileSync(f, "utf-8")));
  ajv.addSchema(sIndex, "index");
  ajv.addSchema(sLote, "lote");
  const fuente = standaloneCode(ajv, { validarIndexSchema: "index", validarLoteSchema: "lote" });
  const r = await build({
    stdin: { contents: fuente, resolveDir: __dirname, sourcefile: "validadores-ajv.js", loader: "js" },
    bundle: true, format: "esm", platform: "browser", target: "es2020", write: false, legalComments: "none",
    logLevel: "silent",
  });
  // El runtime de Ajv trae `ucs2length.code = 'require("ajv/dist/runtime/ucs2length").default'`: es un string que solo
  // usa el *compilador* para generar código; en runtime no se ejecuta. Se neutraliza para que el módulo no contenga
  // ningún `require(` (así la verificación de abajo puede ser estricta).
  const codigo = r.outputFiles[0].text.replace(
    /\.code\s*=\s*(?:'require\([^'\n]*'|"require\((?:[^"\\\n]|\\.)*"|`require\([^`]*`)/g, '.code = ""');
  if (tieneRequire(codigo)) throw new Error("vite-plugin-validadores: el código generado todavía tiene require(); no correría en el navegador");
  return codigo;
}

export function validadores(): Plugin {
  return {
    name: "validadores-ajv-standalone",
    resolveId(id) { return id === ID ? "\0" + ID : null; },
    async load(id) {
      if (id !== "\0" + ID) return null;
      ARCHIVOS_SCHEMA.forEach((f) => this.addWatchFile(f));   // si cambia el schema del pipeline, se regenera
      return generarCodigoValidadores();
    },
  };
}
