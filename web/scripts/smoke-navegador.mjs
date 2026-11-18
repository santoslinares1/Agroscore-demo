#!/usr/bin/env node
// Verificación en navegador real (Chrome/Chromium headless vía playwright-core) del build en dist/ servido por HTTP.
// Uso:  npm run build && npm run test:navegador
// Navegador: CHROME_PATH, o /usr/bin/google-chrome, /usr/bin/chromium, /usr/bin/chromium-browser (el primero que exista).
// Sin internet: las peticiones a otros hosts (teselas del mapa) se responden localmente con una imagen vacía.
//
// Casos (cada uno sobre una copia de dist/):
//   ok        → arranca sin errores de consola, renderiza todas las tarjetas del index y las vistas principales.
//   roto      → un lote.json con JSON inválido y otro que no cumple el schema: esos muestran tarjeta de error,
//               los demás se renderizan, sin errores de JavaScript.
//   sin-index → demo/index.json no existe: pantalla "No se pudieron cargar los datos" con botón Reintentar.
// Sale con código 1 si algo falla.
import { createServer } from "node:http";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { extname, join, normalize, resolve } from "node:path";
import { chromium } from "playwright-core";

const DIST = resolve(process.argv[2] ?? join(import.meta.dirname, "..", "dist"));
const TIPOS = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".png": "image/png", ".svg": "image/svg+xml", ".pdf": "application/pdf", ".geojson": "application/geo+json" };
const PNG_VACIO = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

function navegador() {
  const c = [process.env.CHROME_PATH, "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"].filter(Boolean);
  const p = c.find((x) => existsSync(x));
  if (!p) throw new Error(`No encontré Chrome/Chromium (probé ${c.join(", ")}). Definí CHROME_PATH.`);
  return p;
}

function servir(dir) {
  return new Promise((ok) => {
    const srv = createServer((req, res) => {
      const ruta = decodeURIComponent(new URL(req.url, "http://x").pathname);
      const f = normalize(join(dir, ruta.endsWith("/") ? ruta + "index.html" : ruta));
      if (!f.startsWith(dir) || !existsSync(f)) { res.writeHead(404).end("no existe"); return; }
      try { res.writeHead(200, { "content-type": TIPOS[extname(f)] ?? "application/octet-stream" }).end(readFileSync(f)); }
      catch { res.writeHead(404).end("no existe"); }
    });
    srv.listen(0, "127.0.0.1", () => ok(srv));
  });
}

function copiaDist(nombre, modificar) {
  const dir = mkdtempSync(join(tmpdir(), `agroscore-smoke-${nombre}-`));
  cpSync(DIST, dir, { recursive: true });
  modificar?.(dir);
  return dir;
}

const fallas = [];
const check = (caso, cond, msg) => { console.log(`  ${cond ? "OK  " : "FALLA"} ${msg}`); if (!cond) fallas.push(`[${caso}] ${msg}`); };

async function caso(browser, nombre, dir, fn) {
  console.log(`\n== ${nombre}`);
  const srv = await servir(dir);
  const base = `http://127.0.0.1:${srv.address().port}/`;
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await ctx.route("**/*", (r) => {
    if (r.request().url().startsWith(base)) return r.continue();
    return r.fulfill({ status: 200, contentType: "image/png", body: PNG_VACIO });
  });
  const page = await ctx.newPage();
  const errores = [];
  page.on("pageerror", (e) => errores.push({ texto: `pageerror: ${e.message}`, url: "" }));
  page.on("console", (m) => { if (m.type() === "error") errores.push({ texto: `console.error: ${m.text()}`, url: m.location().url ?? "" }); });
  try { await fn({ page, base, errores }); }
  catch (e) {
    const extra = errores.length ? ` — errores de consola/JS: ${errores.map((x) => x.texto).join(" | ")}` : "";
    check(nombre, false, `excepción: ${e.message.split("\n")[0]}${extra}`);
  }
  finally { await ctx.close(); srv.close(); rmSync(dir, { recursive: true, force: true }); }
}

const ir = async (page, url) => { await page.goto(url); await page.waitForLoadState("networkidle"); await page.waitForTimeout(300); };

async function main() {
  if (!existsSync(join(DIST, "index.html")) || !existsSync(join(DIST, "demo", "index.json")))
    throw new Error(`${DIST} no tiene index.html y demo/index.json: corré "npm run build" primero.`);
  const index = JSON.parse(readFileSync(join(DIST, "demo", "index.json"), "utf-8"));
  const ids = index.lotes.map((l) => l.id);
  if (ids.length < 3) throw new Error("el smoke test necesita al menos 3 lotes en demo/index.json");
  const browser = await chromium.launch({ executablePath: navegador(), args: ["--no-sandbox"] });
  try {
    await caso(browser, "ok", copiaDist("ok"), async ({ page, base, errores }) => {
      await ir(page, base + "#/");
      await page.waitForSelector("a.tarjeta[data-id]", { timeout: 10000 });
      const n = await page.locator("a.tarjeta[data-id]").count();
      check("ok", n === ids.length, `inicio renderiza ${n}/${ids.length} tarjetas de lote`);
      check("ok", (await page.locator(".tarjeta-error").count()) === 0, "sin tarjetas de error");
      for (const ruta of [`#/lote/${ids[0]}`, "#/comparar", "#/como-funciona", `#/informe/${ids[0]}`]) {
        await ir(page, base + ruta);
        const txt = await page.innerText("body");
        check("ok", txt.trim().length > 200 && !txt.includes("No se pudieron cargar"), `${ruta} renderiza contenido`);
      }
      check("ok", errores.length === 0, `sin errores de consola/JS${errores.length ? ": " + errores.map((e) => e.texto).join(" | ") : ""}`);
    });

    const [malJson, malSchema] = ids;
    await caso(browser, "roto", copiaDist("roto", (d) => {
      writeFileSync(join(d, "demo", malJson, "lote.json"), "{ esto no es JSON");
      const l = JSON.parse(readFileSync(join(d, "demo", malSchema, "lote.json"), "utf-8"));
      delete l.score;
      writeFileSync(join(d, "demo", malSchema, "lote.json"), JSON.stringify(l));
    }), async ({ page, base, errores }) => {
      await ir(page, base + "#/");
      await page.waitForSelector(".tarjeta", { timeout: 10000 });
      const errIds = await page.locator(".tarjeta-error").evaluateAll((els) => els.map((e) => e.getAttribute("data-error")));
      check("roto", errIds.includes(malJson) && errIds.includes(malSchema) && errIds.length === 2, `tarjetas de error para los 2 lotes rotos (${errIds.join(", ")})`);
      const okN = await page.locator("a.tarjeta[data-id]").count();
      check("roto", okN === ids.length - 2, `los demás lotes se renderizan (${okN}/${ids.length - 2})`);
      await ir(page, base + `#/lote/${malJson}`);
      check("roto", (await page.locator(".aviso-lote.error").count()) > 0, "el detalle del lote roto muestra el aviso de error");
      await ir(page, base + `#/lote/${ids[2]}`);
      check("roto", !(await page.innerText("body")).includes("No se pudieron cargar"), "un lote sano sigue abriendo");
      check("roto", errores.length === 0, `sin errores de consola/JS${errores.length ? ": " + errores.map((e) => e.texto).join(" | ") : ""}`);
    });

    await caso(browser, "sin-index", copiaDist("sin-index", (d) => rmSync(join(d, "demo", "index.json"))), async ({ page, base, errores }) => {
      await ir(page, base + "#/");
      await page.waitForSelector(".error[role=alert]", { timeout: 10000 });
      const txt = await page.innerText("body");
      check("sin-index", txt.includes("No se pudieron cargar los datos"), "muestra 'No se pudieron cargar los datos'");
      check("sin-index", (await page.getByRole("button", { name: "Reintentar" }).count()) === 1, "muestra el botón Reintentar");
      // el único error de consola aceptable es el 404 del propio index.json que el navegador registra solo
      const otros = errores.filter((e) => !(e.texto.includes("404") && e.url.endsWith("/demo/index.json")));
      check("sin-index", otros.length === 0, `sin otros errores de consola/JS${otros.length ? ": " + otros.map((e) => e.texto).join(" | ") : ""}`);
    });
  } finally {
    await browser.close();
  }
  console.log(fallas.length ? `\nFALLÓ (${fallas.length}):\n- ${fallas.join("\n- ")}` : "\nTodo OK");
  process.exit(fallas.length ? 1 : 0);
}

main().catch((e) => { console.error(e.message); process.exit(1); });
