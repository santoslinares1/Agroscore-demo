# Web demo (Vite + TypeScript)
```bash
npm install
npm run dev        # desarrollo
npm run build      # genera dist/ (base relativa, sin CDN)
npm run preview    # sirve dist/ en http://localhost:4173
npm test           # vitest (incluye: el módulo de validadores generado no tiene require())
npm run test:navegador   # después de build: Chrome/Chromium headless sobre dist/ servido por HTTP (CHROME_PATH opcional)
```
Lee `public/demo/index.json` y `public/demo/<id>/*` (copiados con `../scripts/copiar_salidas.sh`) y los valida con los
schemas de `../pipeline/agroscore/schema` (Ajv compilado en el build por `vite-plugin-validadores.ts`; por eso `web/` se
construye dentro del monorepo). Un lote inválido o que no carga se muestra como tarjeta de error; el resto de la app sigue.
Si algún `lote.json` tiene `"ejemplo": true`, se muestra el aviso "LOTE DE EJEMPLO – datos de ejemplo".
El código de validación generado se empaqueta con esbuild como ESM puro (sin `require`, que no existe en el navegador).
El build saca de `dist/` cualquier oculto o temporal (`.*`, `*.tmp`, `*.lock`); los metadatos de publicación viven en
`../.publicacion/`, fuera de `public/`. El rótulo y la explicación del vigor salen de `score.vigor_base` de cada lote.
