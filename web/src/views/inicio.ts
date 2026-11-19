import type { Datos } from "../data";
import { textoErrorLote } from "../data";
import { crearMapa } from "../mapa";
import { ultimoManiTxt } from "../textos";
import { colorScore, esc, fraseScore, num, scoreTxt, textoScore } from "../fmt";
import type { Lote } from "../types";

function hero(top: Lote, todos: Lote[]): string {
  const iguales = todos.filter((l) => l.score.valor !== null && l.score.valor === top.score.valor).length;
  const kicker = top.score.valor === null
    ? "Datos de ejemplo"
    : iguales > 1
      ? "Datos de ejemplo · entre los números más altos"
      : "Datos de ejemplo · el número más alto de estos ejemplos";
  return `
    <section class="hero" data-id="${top.id}" aria-label="Lote para mirar primero">
      <div class="hero-score ${top.score.valor === null ? "sin-score" : ""}" style="--c:${colorScore(top.score.valor)}">
        ${top.score.valor === null
          ? `<span class="hero-num hero-sd">${scoreTxt(top.score.valor)}</span>`
          : `<span class="hero-num">${top.score.valor}</span><span class="hero-de">de 100</span>`}
      </div>
      <div class="hero-txt">
        <p class="kicker">${kicker}</p>
        <h2>${esc(top.nombre)}</h2>
        <p class="score-frase">${esc(fraseScore(top.score.valor))}</p>
        <p class="hero-meta">${esc(top.localidad)} · ${num(top.area_ha, 1)} ha · último maní ${esc(ultimoManiTxt(top))}</p>
        ${top.ejemplo ? `<span class="chip-ejemplo">Datos de ejemplo</span>` : ""}
        <div class="acciones"><a class="btn" href="#/lote/${top.id}">Ver este lote</a></div>
      </div>
    </section>`;
}

export function vistaInicio(app: HTMLElement, d: Datos) {
  const lotes = d.index.lotes.filter((l) => d.lotes.has(l.id)).map((l) => d.lotes.get(l.id)!)
    .sort((a, b) => (b.score.valor ?? -1) - (a.score.valor ?? -1));
  const rotos = d.index.lotes.filter((l) => d.errores.has(l.id));
  const ha = lotes.reduce((s, l) => s + l.area_ha, 0);
  const top = lotes[0];
  app.innerHTML = `
    <section class="intro">
      <h1>¿Conviene alquilar este campo para maní?</h1>
      <p class="lead">Mirá cada lote en un minuto. El número de 0 a 100 resume el vigor del cultivo, la humedad, las zonas y si hubo maní hace poco.</p>
      <div class="resumen-inicio"><span><strong>${lotes.length}</strong> lotes</span><span><strong>${num(ha, 1)}</strong> ha</span>
        <span><strong>${lotes[0]?.campanias.length ?? 0}</strong> campañas analizadas (${esc(lotes[0]?.campanias[0]?.campania ?? "")} a ${esc(lotes[0]?.campanias.at(-1)?.campania ?? "")})</span></div>
    </section>
    ${top ? hero(top, lotes) : ""}
    <section class="inicio">
      <div class="mapa-wrap">
        <div id="mapa" class="mapa" role="region" aria-label="Mapa de los lotes"></div>
        <button class="btn-ver-todos" type="button">Ver todos los lotes</button>
      </div>
      <div class="lista">
        <h2>Elegí un lote</h2>
        ${rotos.map((l) => `
          <div class="tarjeta tarjeta-error" role="alert" data-error="${esc(l.id)}">
            <span class="badge-score sin-score" aria-hidden="true">!</span>
            <span class="t-info"><strong>${esc(l.nombre)}</strong>
              <small>${esc(textoErrorLote(d.errores.get(l.id)!))}</small>
              <small>${esc(l.localidad)} · ${num(l.area_ha, 1)} ha</small>
              <small class="codigo">Código interno: <code>${esc(l.id)}</code></small></span>
          </div>`).join("")}
        ${lotes.map((l) => `
          <a class="tarjeta" href="#/lote/${l.id}" data-id="${l.id}">
            <span class="badge-score ${l.score.valor === null ? "sin-score" : ""}" style="background:${colorScore(l.score.valor)};color:${textoScore(l.score.valor)}"${l.score.motivo_sin_score ? ` title="${esc(l.score.motivo_sin_score)}"` : ""}>${scoreTxt(l.score.valor)}</span>
            <span class="t-info">
              <strong>${esc(l.nombre)}</strong>
              <span class="frase-score">${esc(fraseScore(l.score.valor))}</span>
              <small>${esc(l.localidad)} · ${num(l.area_ha, 1)} ha</small>
              <small>Último maní: <b>${esc(ultimoManiTxt(l))}</b> · maní en las últimas 5: <b>${l.rotacion.veces_mani_ultimas_5}</b></small>
              ${l.ejemplo ? `<span class="chip-ejemplo">Datos de ejemplo</span>` : ""}
            </span>
            <span class="flecha" aria-hidden="true">›</span>
          </a>`).join("")}
        ${lotes.length >= 2 ? `<a class="btn sec" href="#/comparar">Comparar lotes</a>` : ""}
        <div class="leyenda" aria-label="Escala del número"><span class="ley-tit">El número</span><span style="background:#1a9641"></span>75 o más <span style="background:#a6d96a"></span>60 a 74
          <span style="background:#fdae61"></span>45 a 59 <span style="background:#d7191c"></span>menos de 45</div>
        <p class="ayuda">Tocá una tarjeta para abrir el lote. En la computadora, pasá el mouse por encima para ubicarlo en el mapa.
          <a href="#/como-funciona">¿Cómo se calcula?</a></p>
      </div>
    </section>`;
  const m = crearMapa(app.querySelector<HTMLElement>("#mapa")!, lotes, { modo: "inicio", onClick: (id) => (location.hash = `#/lote/${id}`) });
  app.querySelectorAll<HTMLElement>(".tarjeta, .hero").forEach((t) => {
    const id = t.dataset.id;
    if (!id) return;
    t.addEventListener("mouseenter", () => m.volarA(id));
    t.addEventListener("focusin", () => m.volarA(id));
  });
  app.querySelector(".btn-ver-todos")!.addEventListener("click", () => m.verTodos());
}
