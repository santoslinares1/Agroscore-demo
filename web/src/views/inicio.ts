import type { Datos } from "../data";
import { textoErrorLote } from "../data";
import { crearMapa } from "../mapa";
import { ultimoManiTxt } from "../textos";
import { colorScore, esc, num, scoreTxt } from "../fmt";

export function vistaInicio(app: HTMLElement, d: Datos) {
  const lotes = d.index.lotes.filter((l) => d.lotes.has(l.id)).map((l) => d.lotes.get(l.id)!)
    .sort((a, b) => (b.score.valor ?? -1) - (a.score.valor ?? -1));
  const rotos = d.index.lotes.filter((l) => d.errores.has(l.id));
  const ha = lotes.reduce((s, l) => s + l.area_ha, 0);
  app.innerHTML = `
    <section class="intro">
      <h1>¿Conviene alquilar este campo para maní?</h1>
      <p>Cada lote resumido en un minuto: score 0–100, qué se sembró en cada campaña (con el maní marcado),
      vigor del cultivo, zonas dentro del lote, riesgo de anegamiento e informe PDF.</p>
      <div class="resumen-inicio"><span><strong>${lotes.length}</strong> lotes</span><span><strong>${num(ha, 1)}</strong> ha</span>
        <span><strong>${lotes[0]?.campanias.length ?? 0}</strong> campañas analizadas (${esc(lotes[0]?.campanias[0]?.campania ?? "")} a ${esc(lotes[0]?.campanias.at(-1)?.campania ?? "")})</span></div>
    </section>
    <section class="inicio">
      <div class="mapa-wrap"><div id="mapa" class="mapa"></div>
        <button class="btn-ver-todos" type="button">Ver todos los lotes</button></div>
      <div class="lista">
        ${rotos.map((l) => `
          <div class="tarjeta tarjeta-error" role="alert" data-error="${esc(l.id)}">
            <span class="badge-score sin-score" aria-hidden="true">!</span>
            <span class="t-info"><strong>${esc(l.nombre)}</strong>
              <small>${esc(textoErrorLote(d.errores.get(l.id)!))}</small>
              <small>${esc(l.localidad)} · ${num(l.area_ha, 1)} ha · id <code>${esc(l.id)}</code></small></span>
          </div>`).join("")}
        ${lotes.map((l) => `
          <a class="tarjeta" href="#/lote/${l.id}" data-id="${l.id}">
            <span class="badge-score ${l.score.valor === null ? "sin-score" : ""}" style="background:${colorScore(l.score.valor)}"${l.score.motivo_sin_score ? ` title="${esc(l.score.motivo_sin_score)}"` : ""}>${scoreTxt(l.score.valor)}</span>
            <span class="t-info">
              <strong>${esc(l.nombre)}</strong>
              <small>${esc(l.localidad)} · ${num(l.area_ha, 1)} ha</small>
              <small>Último maní: <b>${esc(ultimoManiTxt(l))}</b> · maní en las últimas 5: <b>${l.rotacion.veces_mani_ultimas_5}</b></small>
              ${l.ejemplo ? `<span class="chip-ejemplo">EJEMPLO</span>` : ""}
            </span>
            <span class="flecha" aria-hidden="true">›</span>
          </a>`).join("")}
        <a class="btn" href="#/comparar">Comparar lotes lado a lado</a>
        <div class="leyenda"><span class="ley-tit">Score</span><span style="background:#1a9641"></span>≥75 <span style="background:#a6d96a"></span>60–74
          <span style="background:#fdae61"></span>45–59 <span style="background:#d7191c"></span>&lt;45</div>
        <p class="ayuda">Pasá el mouse por una tarjeta para ubicar el lote en el mapa; tocala para ver el detalle.
          <a href="#/como-funciona">¿Cómo se calcula?</a></p>
      </div>
    </section>`;
  const m = crearMapa(app.querySelector<HTMLElement>("#mapa")!, lotes, { modo: "inicio", onClick: (id) => (location.hash = `#/lote/${id}`) });
  app.querySelectorAll<HTMLElement>(".tarjeta").forEach((t) => {
    t.addEventListener("mouseenter", () => m.volarA(t.dataset.id!));
    t.addEventListener("focus", () => m.volarA(t.dataset.id!));
  });
  app.querySelector(".btn-ver-todos")!.addEventListener("click", () => m.verTodos());
}
