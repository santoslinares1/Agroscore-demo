import { defineConfig } from "vite";
import { readdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { validadores } from "./vite-plugin-validadores";

/** Lo que nunca debe quedar en dist/: ocultos (.versiones, .publicar.lock, .staging-*, .index.*.tmp, …) y temporales. */
export const esResto = (nombre: string) => nombre.startsWith(".") || /\.(tmp|lock)$/i.test(nombre) || nombre.endsWith("~");

function limpiarRestos(dir: string): string[] {
  const borrados: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (esResto(e.name)) { rmSync(p, { recursive: true, force: true }); borrados.push(p); }
    else if (e.isDirectory()) borrados.push(...limpiarRestos(p));
  }
  return borrados;
}

// base relativa: el build funciona servido desde cualquier carpeta o subruta, sin internet.
export default defineConfig({
  base: "./",
  build: { outDir: "dist", assetsInlineLimit: 0, chunkSizeWarningLimit: 800 },
  plugins: [
    // valida index.json / lote.json con los schemas del pipeline (compilados a JS ESM en el build, sin duplicarlos)
    validadores(),
    {
      // defensa en profundidad: publicar.py ya guarda versiones/lock/staging FUERA de public/ (en .publicacion/),
      // pero si quedara algún resto oculto o temporal en public/ (p. ej. de una versión vieja), no llega a dist/.
      name: "sin-restos-en-dist",
      apply: "build",
      closeBundle() {
        const borrados = limpiarRestos(resolve(__dirname, "dist"));
        if (borrados.length) console.warn(`[sin-restos-en-dist] quitados de dist/: ${borrados.join(", ")}`);
      },
    },
  ],
});
