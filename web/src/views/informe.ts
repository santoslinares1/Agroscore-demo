import type { Datos } from "../data";
import { AVISO_EJEMPLO, url } from "../data";
import { crearMapa } from "../mapa";
import { graficoNDVI } from "../grafico";
import { cultivoNombre, esc, md, num } from "../fmt";
import { bloqueScore, leyendaCultivos, lineaTiempo, lotNoDisponible } from "./detalle";
import { fraseRotacion } from "../textos";

/** Vista de informe imprimible (Imprimir → Guardar como PDF) con los mismos datos del lote.json. */
export function vistaInforme(app: HTMLElement, d: Datos, id: string) {
  const l = d.lotes.get(id);
  if (!l) { app.innerHTML = lotNoDisponible(d, id); return; }
  const a = l.agua, z = l.zonas;
  app.innerHTML = `
    <div class="no-print barra-informe">
      <a href="#/lote/${l.id}">← Volver al lote</a>
      <span><button class="btn" type="button" id="imprimir">Imprimir / guardar como PDF</button>
      <a class="btn sec" href="${url(l.id, l.pdf)}" download="${l.id}_informe.pdf">PDF generado por el pipeline</a></span>
    </div>
    <article class="informe">
      ${l.ejemplo ? `<div class="aviso-informe">${AVISO_EJEMPLO.toUpperCase()} · polígono y números sintéticos, no es un lote de cliente</div>` : ""}
      <header class="inf-cab">
        <div><div class="marca"><span class="logo"></span>AgroScore</div>
          <h1>${esc(l.nombre)}</h1><p>${esc(l.localidad)} · ${num(l.area_ha, 1)} ha · centro ${l.centroide[1].toFixed(5)}, ${l.centroide[0].toFixed(5)}</p></div>
        <div class="inf-fecha">Informe de lote<br><small>${esc(l.generado.slice(0, 10))} · score v${esc(l.score.version)}</small></div>
      </header>
      <section class="inf-2 inf-top">
        <div><h2>Score</h2>${bloqueScore(l, false)}</div>
        <div><h2>Ubicación</h2><div id="mapa-inf" class="mapa inf"></div></div>
      </section>
      <section><h2>Resumen</h2>${md(d.resumenes.get(l.id) ?? "")}</section>
      <section class="salto"><h2>Campañas y rotación de maní</h2>${lineaTiempo(l)}${leyendaCultivos}
        <p class="frase">${esc(fraseRotacion(l))}</p>
        <div class="chart inf"><canvas id="ndvi-inf"></canvas></div>
        <table class="inf-tabla"><thead><tr><th>Campaña</th><th>Cultivo</th><th>Fuente</th><th>NDVI máx.</th><th>NDVI medio</th><th>Anomalía</th><th>NDMI</th><th>% nubes</th></tr></thead>
        <tbody>${l.campanias.map((c) => `<tr class="${c.cultivo === "mani" ? "fila-mani" : ""}"><td>${c.campania}</td><td>${esc(cultivoNombre(c.cultivo))}</td>
          <td>${esc(c.cultivo_fuente ?? "s/d")}</td><td>${num(c.ndvi_max)}</td><td>${num(c.ndvi_medio)}</td><td>${num(c.ndvi_anomalia)}</td>
          <td>${num(c.ndmi_medio)}</td><td>${num(c.pct_nubes, 0)}</td></tr>`).join("")}</tbody></table>
      </section>
      <section class="inf-2 salto">
        <div><h2>NDVI de la última campaña</h2><img src="${url(l.id, l.imagenes.ndvi_ultima)}" alt="NDVI"></div>
        <div><h2>Zonas (Alta ${num(z.alta_pct, 0)}% · Media ${num(z.media_pct, 0)}% · Baja ${num(z.baja_pct, 0)}%)</h2><img src="${url(l.id, z.png)}" alt="Zonas"></div>
      </section>
      <section><h2>Agua, suelo y clima</h2>
        <table class="inf-tabla"><tbody>
          <tr><th>Máx. superficie anegada</th><td>${num(a.max_ha_anegadas, 1, " ha")} ${a.fecha_max ? `(${a.fecha_max})` : ""}</td></tr>
          <tr><th>Frecuencia histórica de agua</th><td>${num(a.frecuencia_pct, 1, " %")}</td></tr>
          <tr><th>Arcilla / arena (0–5 cm)</th><td>${num(l.suelo.arcilla_pct, 1, " %")} / ${num(l.suelo.arena_pct, 1, " %")}</td></tr>
          <tr><th>Carbono orgánico</th><td>${num(l.suelo.carbono_org, 1, " %")}</td></tr>
          <tr><th>Lluvia media anual</th><td>${num(l.clima.pp_anual_mm, 0, " mm")} (${esc(l.clima.fuente)})</td></tr>
        </tbody></table>
        ${l.advertencias.length ? `<h3>Advertencias</h3><ul>${l.advertencias.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
      </section>
      <footer class="inf-pie">AgroScore · Sentinel-2 y Sentinel-1 (Copernicus), JRC, SoilGrids, ERA5 · fuente de datos: ${esc(l.fuente_datos)}</footer>
    </article>`;
  const el = app.querySelector<HTMLElement>("#mapa-inf")!;
  crearMapa(el, [l], { modo: "mini" });
  graficoNDVI(app.querySelector<HTMLCanvasElement>("#ndvi-inf")!, l);
  app.querySelector("#imprimir")!.addEventListener("click", () => window.print());
}
