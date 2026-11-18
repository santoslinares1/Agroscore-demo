import "./style.css";
import { AVISO_EJEMPLO, cargarDatos, ErrorIndice, type Datos } from "./data";
import { vistaInicio } from "./views/inicio";
import { vistaDetalle } from "./views/detalle";
import { vistaComparar } from "./views/comparar";
import { vistaInforme } from "./views/informe";
import { vistaComo } from "./views/como";
import { leerLotes } from "./carga/almacen";
const fmtHa = (v: number) => v.toLocaleString("es-AR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
import { esc } from "./fmt";

const root = document.querySelector<HTMLDivElement>("#app")!;

function marco(d: Datos): HTMLElement {
  const todos = [...d.lotes.values()];
  const hayEjemplo = d.index.ejemplo || todos.some((l) => l.ejemplo);
  const hayReales = todos.some((l) => !l.ejemplo);
  const banner = !hayEjemplo ? "" : hayReales
    ? `<div class="aviso-ejemplo mixto" role="alert">HAY LOTES DE EJEMPLO (marcados EJEMPLO) <span>· junto a lotes analizados con datos reales. Los de ejemplo son sintéticos, no son campos de clientes.</span></div>`
    : `<div class="aviso-ejemplo" role="alert">${AVISO_EJEMPLO.toUpperCase()} <span>· Lotes y números sintéticos para mostrar el producto; no son campos de clientes.</span></div>`;
  root.innerHTML = `
    ${banner}
    <header class="top">
      <a class="marca" href="#/"><span class="logo"></span>AgroScore <small>Demo maní</small></a>
      <nav><a href="#/" data-r="/">Mapa</a><a href="#/comparar" data-r="/comparar">Comparar</a><a href="#/cargar" data-r="/cargar">Cargar lote</a><a href="#/como-funciona" data-r="/como-funciona">Cómo funciona</a></nav>
    </header>
    <main id="vista"></main>
    <footer class="footer">AgroScore · Sentinel-2 / Sentinel-1 (Copernicus), SoilGrids, ERA5 · score v${d.index.score_version}
      · <a href="https://agroscorelatam.com" target="_blank" rel="noopener">agroscorelatam.com</a></footer>`;
  return root.querySelector<HTMLElement>("#vista")!;
}

function enrutar(vista: HTMLElement, d: Datos) {
  const h = location.hash.replace(/^#/, "") || "/";
  const [ruta, qs] = h.split("?");
  const params = new URLSearchParams(qs ?? "");
  window.scrollTo(0, 0);
  document.body.classList.toggle("modo-informe", ruta.startsWith("/informe/"));
  root.querySelectorAll<HTMLAnchorElement>(".top nav a").forEach((a) =>
    a.classList.toggle("activo", a.dataset.r === ruta || (a.dataset.r === "/" && ruta.startsWith("/lote/"))));
  const nombre = (id: string) => d.lotes.get(id)?.nombre ?? d.index.lotes.find((l) => l.id === id)?.nombre ?? "";
  if (ruta.startsWith("/lote/")) { const id = decodeURIComponent(ruta.slice(6)); vistaDetalle(vista, d, id, params.get("capa")); document.title = `${nombre(id)} · AgroScore`; }
  else if (ruta.startsWith("/informe/")) { const id = decodeURIComponent(ruta.slice(9)); vistaInforme(vista, d, id); document.title = `Informe ${nombre(id)} · AgroScore`; }
  else if (ruta === "/comparar") { vistaComparar(vista, d, params.get("ids")); document.title = "Comparar lotes · AgroScore"; }
  else if (ruta === "/cargar") { vista.innerHTML = `<div class="cargando">Cargando…</div>`; import("./views/cargar").then((m) => m.vistaCargar(vista, d, recargar)); document.title = "Cargar lote · AgroScore"; }
  else if (ruta === "/como-funciona") { vistaComo(vista, d); document.title = "Cómo funciona · AgroScore"; }
  else { vistaInicio(vista, d); seccionPendientes(vista, d); document.title = "AgroScore · Demo maní"; }
}

/** En el inicio: lotes cargados por el usuario que todavía no tienen análisis (sin score inventado). */
function seccionPendientes(vista: HTMLElement, d: Datos) {
  const pend = leerLotes().filter((l) => !d.lotes.has(l.id));
  const s = document.createElement("section");
  s.className = "card pendientes-inicio";
  s.innerHTML = pend.length
    ? `<h2>Lotes cargados – pendientes de análisis <small>(${pend.length})</small></h2>
       <p>Guardados en este navegador. No tienen score hasta procesarlos con imágenes satelitales reales.</p>
       <ul>${pend.map((l) => `<li><strong>${esc(l.nombre)}</strong> · ${fmtHa(l.area_ha)} ha <span class="chip-estado ${l.estado === "error" ? "error" : l.estado === "analizando" ? "analizando" : "pendiente"}">${l.estado === "analizando" ? "Analizando…" : l.estado === "error" ? "Lote cargado – análisis con error" : "Lote cargado – pendiente de análisis"}</span></li>`).join("")}</ul>
       <a class="btn sec chico" href="#/cargar">Gestionar lotes cargados</a>`
    : `<h2>¿Tenés el contorno de un lote?</h2><p>Subí un KML/KMZ de Google Earth o dibujalo sobre el satélite.</p><a class="btn chico" href="#/cargar">Cargar un lote</a>`;
  vista.appendChild(s);
}

let datos: Datos;
let vistaActual: HTMLElement;
async function recargar() {
  try { datos = await cargarDatos(); } catch { return; }   // si el índice falla al recargar, se conserva lo que ya se mostraba
  const h = location.hash;
  vistaActual = marco(datos);
  if (location.hash === h) enrutar(vistaActual, datos);
}

cargarDatos()
  .then((d) => {
    datos = d;
    vistaActual = marco(d);
    window.addEventListener("hashchange", () => enrutar(vistaActual, datos));
    enrutar(vistaActual, d);
  })
  .catch((e) => {
    const detalle = e instanceof ErrorIndice ? e.message : `Error inesperado: ${String(e)}`;
    root.innerHTML = `<div class="error" role="alert"><h1>No se pudieron cargar los datos</h1><p>${esc(detalle)}</p>
      <p>Corré el pipeline y <code>scripts/copiar_salidas.sh</code>, y serví el build con <code>npm run preview</code>
      (abrir index.html con doble clic no permite leer los JSON).</p>
      <p><button class="btn" type="button" onclick="location.reload()">Reintentar</button></p></div>`;
  });
