import type { Datos } from "../data";
import { AVISO_EJEMPLO, url } from "../data";
import { crearMapa } from "../mapa";
import { graficoNDVI } from "../grafico";
import { cultivoNombre, esc, md, num } from "../fmt";
import { bloqueScore, leyendaCultivos, lineaTiempo, lotNoDisponible, notasMargen, selloImagen } from "./detalle";
import { fraseRotacion } from "../textos";

/** Vista de informe imprimible (Imprimir → Guardar como PDF) con los mismos datos del lote.json. */
export function vistaInforme(app: HTMLElement, d: Datos, id: string) {
  const l = d.lotes.get(id);
  if (!l) { app.innerHTML = lotNoDisponible(d, id); return; }
  const a = l.agua, z = l.zonas;
  const marca = l.ejemplo ? `<span class="chip-ejemplo">Datos de ejemplo</span>` : "";
  const celda = (h: string, v: string) => `<td data-h="${esc(h)}">${v}</td>`;
  app.innerHTML = `
    <div class="no-print barra-informe">
      <a href="#/lote/${l.id}">← Volver al lote</a>
      <span><button class="btn" type="button" id="imprimir">Imprimir o guardar como PDF</button>
      <a class="btn sec" href="${url(l.id, l.pdf)}" download="${l.id}_informe.pdf">Descargar el PDF ya armado</a></span>
    </div>
    <article class="informe">
      ${l.ejemplo ? `<div class="aviso-informe">${AVISO_EJEMPLO} · polígono y números sintéticos, no es un lote de cliente</div>` : ""}
      <header class="inf-cab">
        <div>
          <p class="kicker">AgroScore · cuaderno de campo</p>
          <h1>${esc(l.nombre)}</h1>
          <p>${esc(l.localidad)} · ${num(l.area_ha, 1)} ha</p>
          <p class="centro">centro ${l.centroide[1].toFixed(5)}, ${l.centroide[0].toFixed(5)}</p>
        </div>
        ${selloImagen(l)}
      </header>
      <section class="inf-apertura">
        <div><h2>El número ${marca}</h2>${bloqueScore(l, false)}</div>
        <div class="bloque-mapa">
          <h2>Dónde está ${marca}</h2>
          <div id="mapa-inf" class="mapa inf"></div>
          <p class="mapa-ayuda">Borde amarillo: límite del lote. Fondo: imagen Esri. La fecha del sello es la del color natural Sentinel-2.</p>
          ${notasMargen(l)}
        </div>
      </section>
      <section class="resumen prosa"><h2>Resumen ${marca}</h2>${md(d.resumenes.get(l.id) ?? "")}</section>
      <section class="campanias-inf"><h2>Campañas y rotación de maní ${marca}</h2>${lineaTiempo(l)}${leyendaCultivos}
        <p class="frase">${esc(fraseRotacion(l))}</p>
        <div class="chart inf"><canvas id="ndvi-inf" aria-label="Vigor del cultivo por campaña"></canvas></div>
        <p class="mapa-ayuda">Barras: vigor máximo (NDVI). En dorado, las campañas con maní. Línea: vigor medio.</p>
        <table class="inf-tabla"><thead><tr><th>Campaña</th><th>Cultivo</th><th>Fuente</th><th>Vigor máx. (NDVI)</th><th>Vigor medio (NDVI)</th><th>Anomalía</th><th>Humedad (NDMI)</th><th>Nubes</th></tr></thead>
        <tbody>${l.campanias.map((c) => `<tr class="${c.cultivo === "mani" ? "fila-mani" : ""}">${celda("Campaña", c.campania)}${celda("Cultivo", esc(cultivoNombre(c.cultivo)))}
          ${celda("Fuente", esc(c.cultivo_fuente ?? "s/d"))}${celda("Vigor máx. (NDVI)", num(c.ndvi_max))}${celda("Vigor medio (NDVI)", num(c.ndvi_medio))}${celda("Anomalía", num(c.ndvi_anomalia))}
          ${celda("Humedad (NDMI)", num(c.ndmi_medio))}${celda("Nubes", num(c.pct_nubes, 0))}</tr>`).join("")}</tbody></table>
      </section>
      <section class="salto figuras-inf">
        <div class="inf-2">
          <figure class="figura"><h2>Vigor de la última campaña (NDVI) ${marca}</h2><img src="${url(l.id, l.imagenes.ndvi_ultima)}" alt="Vigor del cultivo (NDVI) de ${esc(l.nombre)}">
            <figcaption class="ley-print"><div class="ley-grad ndvi"></div><div class="ley-n"><span>menos vigor</span><span>más vigor</span></div></figcaption></figure>
          <figure class="figura"><h2>Zonas de manejo ${marca}</h2><img src="${url(l.id, z.png)}" alt="Zonas de manejo de ${esc(l.nombre)}">
            <figcaption><ul class="ley-z ley-z-lista">
              <li><i style="background:#1a9641"></i>Alta ${num(z.alta_pct, 0, "%")}</li>
              <li><i style="background:#fdcc8a"></i>Media ${num(z.media_pct, 0, "%")}</li>
              <li><i style="background:#d7301f"></i>Baja ${num(z.baja_pct, 0, "%")}</li>
            </ul></figcaption></figure>
        </div>
        <h2>Agua, suelo y lluvia ${marca}</h2>
        <table class="inf-tabla"><tbody>
          <tr><th>Máxima superficie con agua</th><td>${num(a.max_ha_anegadas, 1, " ha")} ${a.fecha_max ? `(${a.fecha_max})` : ""}</td></tr>
          <tr><th>Cada cuánto aparece agua</th><td>${num(a.frecuencia_pct, 1, " %")}</td></tr>
          <tr><th>Arcilla / arena (0–5 cm)</th><td>${num(l.suelo.arcilla_pct, 1, " %")} / ${num(l.suelo.arena_pct, 1, " %")}</td></tr>
          <tr><th>Carbono orgánico</th><td>${num(l.suelo.carbono_org, 1, " %")}</td></tr>
          <tr><th>Lluvia media del año</th><td>${num(l.clima.pp_anual_mm, 0, " mm")} (${esc(l.clima.fuente)})</td></tr>
        </tbody></table>
        ${l.advertencias.length ? `<h3>Avisos sobre los datos</h3><ul>${l.advertencias.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
      </section>
      <footer class="inf-pie">${l.ejemplo ? "Datos de ejemplo. " : ""}Generado ${esc(l.generado.slice(0, 10))} · score v${esc(l.score.version)} · AgroScore · Sentinel-2 y Sentinel-1 (Copernicus), JRC, SoilGrids, ERA5 · fuente de datos: ${esc(l.fuente_datos)}</footer>
    </article>`;
  const el = app.querySelector<HTMLElement>("#mapa-inf")!;
  const mapa = crearMapa(el, [l], { modo: "mini" });
  graficoNDVI(app.querySelector<HTMLCanvasElement>("#ndvi-inf")!, l);
  const imprimir = () => {
    mapa.map.invalidateSize();
    window.setTimeout(() => window.print(), 180);
  };
  app.querySelector("#imprimir")!.addEventListener("click", imprimir);
}
