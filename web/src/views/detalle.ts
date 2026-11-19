import type { Datos } from "../data";
import { AVISO_EJEMPLO, textoErrorLote, url } from "../data";
import { agregarCapasLote, crearMapa } from "../mapa";
import { graficoNDVI } from "../grafico";
import { cultivoNombre, esc, fraseScore, md, num, SIN_SCORE } from "../fmt";
import { comp, etiquetaComp, explicacion, fraseRotacion, INDICE_VIGOR, nivel, NIVEL_TXT, ultimoManiTxt, vigorBase } from "../textos";
import type { Lote } from "../types";

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** Fecha de una imagen (YYYY-MM-DD) en criollo, sin inventar el día si el texto no parsea. */
export function fechaStamp(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const mes = MESES[Number(m[2]) - 1];
  return mes ? `${Number(m[3])} ${mes} ${m[1]}` : iso;
}

/** Fecha y fuente de la foto, en una línea. */
export function metaImagen(l: Lote): string {
  const fecha = fechaStamp(l.imagenes.fecha_rgb);
  const camp = l.imagenes.campania_overlays;
  return ["Sentinel-2", fecha || "fecha s/d", camp ? `campaña ${camp}` : "", "Copernicus"].filter(Boolean).join(" · ");
}

/** Tabla corta al lado del mapa. Cada cifra sale del lote. */
export function notasMargen(l: Lote): string {
  const filas: [string, string][] = [["Superficie", `${num(l.area_ha, 1)} ha`]];
  if (l.zonas.alta_pct !== null) filas.push(["Zona alta", `${num(l.zonas.alta_pct, 0)} %`]);
  if (l.zonas.media_pct !== null) filas.push(["Zona media", `${num(l.zonas.media_pct, 0)} %`]);
  if (l.zonas.baja_pct !== null) filas.push(["Zona baja", `${num(l.zonas.baja_pct, 0)} %`]);
  filas.push(["Último maní", ultimoManiTxt(l)]);
  return `<div class="notas-margen">
    ${l.ejemplo ? `<span class="chip-ejemplo">Datos de ejemplo</span>` : ""}
    <table class="notas-tabla"><tbody>${filas.map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${esc(v)}</td></tr>`).join("")}</tbody></table>
    <p class="meta-imagen">${esc(metaImagen(l))}</p>
  </div>`;
}

function avisosScore(l: Lote): string {
  const s = l.score;
  if (s.valor === null) return `<p class="aviso-score sin">No se calculó un score total: ${esc(s.motivo_sin_score ?? "datos insuficientes")}</p>`;
  if (!s.reponderado) return "";
  return `<p class="aviso-score parcial"><strong>Score parcial:</strong> calculado sobre el ${num((s.cobertura ?? 1) * 100, 0)} % del peso
    (sin dato: ${esc(s.componentes.filter((c) => c.valor === null).map((c) => etiquetaComp(c, s)).join(", "))}); los pesos de los demás
    componentes se reescalaron proporcionalmente.</p>`;
}

/** El número grande, con unidad, como en una planilla. */
export function figuraNumero(l: Lote): string {
  const s = l.score;
  return `<div class="figura-num ${s.valor === null ? "sin-score" : ""}">
    <span class="rotulo">Número</span>
    ${s.valor === null
      ? `<p class="cifra cifra-sd score-grande"><span class="valor">${SIN_SCORE}</span></p>`
      : `<p class="cifra score-grande" role="img" aria-label="Número ${s.valor} de 100"><span class="valor">${s.valor}</span><span class="unidad">/100</span></p>`}
    ${l.ejemplo ? `<span class="chip-ejemplo">Datos de ejemplo</span>` : ""}
    <p class="score-frase">${esc(fraseScore(s.valor))}</p>
    ${avisosScore(l)}
  </div>`;
}

function tablaComponentes(l: Lote, explicar: boolean): string {
  const s = l.score;
  return `<table class="planilla-tabla">
    <thead><tr><th>Parte</th><th>Valor</th><th>Aporte</th></tr></thead>
    <tbody>${s.componentes.map((c) => {
      const pe = c.peso_efectivo ?? c.peso;
      const aporte = c.valor === null || s.valor === null ? null : 100 * c.valor * pe;
      const ex = explicacion(c.clave, s);
      return `<tr>
        <th scope="row">${esc(etiquetaComp(c, s))} <small class="peso">pesa ${num(c.peso * 100, 0, "%")}</small>
          ${explicar && ex ? `<p class="comp-ex">${ex.que} <em>${ex.alto}</em></p>` : ""}</th>
        <td class="num" data-h="Valor"><span class="regla-valor" role="img" aria-label="${num(c.valor)} sobre 1"><i class="n-${nivel(c.valor)}" style="width:${(c.valor ?? 0) * 100}%"></i></span>${num(c.valor)}</td>
        <td class="num" data-h="Aporte">${num(aporte, 1)} <small>de ${num(pe * 100, 0)}</small></td>
      </tr>`;
    }).join("")}</tbody>
  </table>`;
}

export function bloqueScore(l: Lote, explicar = true, conNumero = true): string {
  const s = l.score;
  return `<div class="planilla">
    ${conNumero ? figuraNumero(l) : ""}
    ${tablaComponentes(l, explicar)}
    <small class="nota">El número suma cada parte (su valor por el peso). Versión ${esc(s.version)} ·
      <a href="#/como-funciona">cómo se calcula</a></small>
  </div>`;
}

export function lineaTiempo(l: Lote, compacta = false): string {
  const n = l.campanias.length;
  return `<div class="timeline ${compacta ? "compacta" : ""}" role="list">${l.campanias.map((c, i) => {
    const hace = n - 1 - i;
    const tit = `${cultivoNombre(c.cultivo)}${c.cultivo_fuente ? " · fuente " + c.cultivo_fuente : ""}${c.cultivo_cobertura != null ? " · cubre " + num(c.cultivo_cobertura * 100, 0, "%") + " del lote" : ""}`;
    return `<div role="listitem" class="camp c-${c.cultivo ?? "nulo"}" title="${esc(tit)}">
      <span class="anio">${c.campania}</span>
      <span class="cult">${c.cultivo === "mani" ? "MANÍ" : esc(cultivoNombre(c.cultivo))}</span>
      ${compacta ? "" : `<span class="hace">${hace === 0 ? "última" : `hace ${hace}`}</span>`}
    </div>`;
  }).join("")}</div>`;
}

export const leyendaCultivos = `<div class="ley-cult">
  <span><i class="c-mani"></i>Maní</span><span><i class="c-soja"></i>Soja</span><span><i class="c-maiz"></i>Maíz</span>
  <span><i class="c-mixto"></i>Mixto (ningún cultivo ≥ 60%)</span><span><i class="c-nulo"></i>Sin dato</span></div>`;

function lecturaRapida(l: Lote): string {
  const items: [string, string, string][] = [
    ["rotacion_mani", "Rotación de maní", fraseRotacion(l)],
    ["riesgo_hidrico", "Agua en el lote", `Como máximo se vieron ${num(l.agua.max_ha_anegadas, 1, " ha")} con agua, de ${num(l.area_ha, 1)} ha. Aparece en el ${num(l.agua.frecuencia_pct, 1, " %")} de las veces.`],
    ["vigor_historico", etiquetaComp({ clave: "vigor_historico", valor: null, peso: 0 }, l.score), fraseVigor(l)],
    ["estabilidad", "Estabilidad entre campañas", "Si el lote viene parejo de un año a otro o tiene altibajos."],
    ["suelo", "Suelo para maní", `Arena ${num(l.suelo.arena_pct, 1, " %")} · arcilla ${num(l.suelo.arcilla_pct, 1, " %")} · carbono orgánico ${num(l.suelo.carbono_org, 1, " %")}.`],
  ];
  return `<ul class="semaforo">${items.map(([k, t, txt]) => {
    const n = nivel(comp(l, k)?.valor ?? null);
    return `<li class="n-${n}"><span class="sem-dot" aria-hidden="true"></span><div><strong>${t}</strong> <span class="sem-tag">${NIVEL_TXT[n]}</span><small>${esc(txt)}</small></div></li>`;
  }).join("")}</ul><small class="nota">Semáforo de la demo: verde si esa parte vale 0,75 o más; amarillo entre 0,50 y 0,75; rojo por debajo de 0,50.</small>`;
}

function rango(l: Lote, indice: "ndvi_max" | "evi_max" = "ndvi_max"): string {
  const v = l.campanias.map((c) => c[indice]).filter((x): x is number => typeof x === "number" && Number.isFinite(x));
  return v.length ? `${num(Math.min(...v))} y ${num(Math.max(...v))}` : "s/d";
}

/** Lectura rápida del vigor con el índice que realmente usó el score (score.vigor_base). */
function fraseVigor(l: Lote): string {
  const vb = vigorBase(l.score);
  if (vb === "evi") return `EVI máximo por campaña entre ${rango(l, "evi_max")} (el score usa EVI; referencias provisorias).`;
  if (vb === "combinado") return `EVI máximo entre ${rango(l, "evi_max")} y NDVI máximo entre ${rango(l)} (el score usa ${INDICE_VIGOR.combinado}).`;
  return `NDVI máximo por campaña entre ${rango(l)}.`;
}

/** Pantalla para un id que no está entre los lotes válidos: roto (con motivo) o inexistente. */
export function lotNoDisponible(d: Datos, id: string): string {
  const motivo = d.errores.get(id);
  return motivo
    ? `<nav class="migas"><a href="#/">← Todos los lotes</a></nav>
       <div class="aviso-lote error" role="alert"><h1>${esc(d.index.lotes.find((x) => x.id === id)?.nombre ?? "Este lote")}</h1>
       <p>${esc(textoErrorLote(motivo))}</p><p class="codigo"><small>El resto de los lotes sigue funcionando. Código interno: <code>${esc(id)}</code></small></p></div>`
    : `<p>No existe el lote que buscaste. <a href="#/">Volver al mapa</a></p><p class="codigo"><small>Código interno: <code>${esc(id)}</code></small></p>`;
}

export function vistaDetalle(app: HTMLElement, d: Datos, id: string, capa: string | null = null) {
  const l = d.lotes.get(id);
  if (!l) { app.innerHTML = lotNoDisponible(d, id); return; }
  const r = l.rotacion, z = l.zonas, a = l.agua;
  const fuentes = [...new Set(l.campanias.map((c) => c.cultivo_fuente).filter(Boolean))].join(", ") || "s/d";
  const otros = d.index.lotes.filter((x) => x.id !== id && d.lotes.has(x.id));
  app.innerHTML = `
    <nav class="migas"><a href="#/">← Volver al mapa</a>
      ${otros.map((o) => `<a class="chip-nav" href="#/lote/${o.id}">${esc(o.nombre.replace(/^Lote Ejemplo\s+/i, "").replace(/^Lote\s+/i, ""))}</a>`).join("")}</nav>
    ${l.ejemplo ? `<div class="aviso-lote">${AVISO_EJEMPLO}: el polígono está dibujado sobre una imagen pública solo para la demo y todos los números son sintéticos. No es un lote de cliente.</div>` : ""}
    <header class="ficha score-card">
      <div>
        <h1>${esc(l.nombre)}</h1>
        <p class="cab-meta">${esc(l.localidad)} · ${num(l.area_ha, 1)} ha${l.score.valor === null ? " · score sin dato suficiente" : ""}</p>
      </div>
      ${figuraNumero(l)}
    </header>
    <div class="acciones">
      <a class="btn" href="#/informe/${l.id}">Abrir informe para imprimir</a>
      <a class="btn sec" href="${url(l.id, l.pdf)}" download="${l.id}_informe.pdf">Descargar el PDF</a>
      <a class="btn sec" href="#/comparar?ids=${[id, ...otros.map((o) => o.id)].slice(0, 3).join(",")}">Comparar con otros</a>
    </div>
    <section class="escena">
      <div id="mapa-lote" class="mapa protagonista" role="region" aria-label="Foto satelital del lote"></div>
      <aside class="margen">
        <div id="riel-capas"></div>
        ${notasMargen(l)}
      </aside>
    </section>
    <p class="mapa-ayuda">El borde amarillo es el límite del lote. Elegí qué ver arriba de la foto y mové la intensidad. Las notas del margen y las leyendas sobre la foto salen de este mismo lote.</p>
    <p class="mapa-coord"><small>Centro del lote: ${l.centroide[1].toFixed(5)}, ${l.centroide[0].toFixed(5)}</small></p>
    <section class="grid-det">
      <article class="card ancho"><h2>Cómo se arma el número</h2>${bloqueScore(l, true, false)}</article>
      <article class="card ancho"><h2>Qué mirar primero</h2>${lecturaRapida(l)}</article>
      <article class="card ancho"><h2>Qué se sembró en cada campaña</h2>
        ${lineaTiempo(l)}
        ${leyendaCultivos}
        <div class="kpis">
          <div class="${r.campanias_desde_mani !== null && r.anios_recomendados !== undefined && r.campanias_desde_mani < r.anios_recomendados ? "kpi-alerta" : ""}">
            <span>Último maní</span><strong>${esc(ultimoManiTxt(l))}</strong></div>
          <div><span>Campañas desde el último maní</span><strong>${r.campanias_desde_mani ?? "—"}</strong></div>
          <div><span>Veces con maní en las últimas 5</span><strong>${r.veces_mani_ultimas_5}</strong></div>
        </div>
        <p class="frase">${esc(fraseRotacion(l))}</p>
        <small>Fuente del mapa de cultivos: ${esc(fuentes)}. Cada campaña va de octubre a marzo. El maní va en dorado.</small>
      </article>
      <article class="card ancho"><h2>Vigor del cultivo por campaña (NDVI)</h2><div class="chart"><canvas id="ndvi" aria-label="Gráfico de vigor del cultivo (NDVI) por campaña"></canvas></div>
        <small>Las barras son el vigor máximo de la campaña; en dorado, las de maní. La línea es el vigor medio. Más alto, más verde.</small></article>
      <article class="card"><h2>Zonas de manejo</h2>
        <img class="img-zonas" src="${url(l.id, z.png)}" alt="Mapa de zonas de manejo de ${esc(l.nombre)}" loading="lazy" />
        <div class="zbar" aria-hidden="true">
          <i class="alta" style="width:${z.alta_pct ?? 0}%">${(z.alta_pct ?? 0) >= 12 ? `Alta ${num(z.alta_pct, 0, "%")}` : ""}</i>
          <i class="media" style="width:${z.media_pct ?? 0}%">${(z.media_pct ?? 0) >= 12 ? `Media ${num(z.media_pct, 0, "%")}` : ""}</i>
          <i class="baja" style="width:${z.baja_pct ?? 0}%">${(z.baja_pct ?? 0) >= 12 ? `Baja ${num(z.baja_pct, 0, "%")}` : ""}</i>
        </div>
        <ul class="ley-z ley-z-lista">
          <li><i style="background:#1a9641"></i>Alta ${num(z.alta_pct, 0, "%")}</li>
          <li><i style="background:#fdcc8a"></i>Media ${num(z.media_pct, 0, "%")}</li>
          <li><i style="background:#d7301f"></i>Baja ${num(z.baja_pct, 0, "%")}</li>
        </ul>
        <small>Armadas con el vigor máximo de todas las campañas. Conviene recorrer primero la zona baja.</small></article>
      <article class="card"><h2>Agua, suelo y lluvia</h2>
        <dl class="dl">
          <dt>Máxima superficie con agua</dt><dd>${num(a.max_ha_anegadas, 1)} <small>ha</small> ${a.fecha_max ? `<small>(${a.fecha_max})</small>` : ""}</dd>
          <dt>Cada cuánto aparece agua</dt><dd>${num(a.frecuencia_pct, 1)} <small>%</small></dd>
          <dt>Arcilla / arena (0–5 cm)</dt><dd>${num(l.suelo.arcilla_pct, 1)} <small>%</small> / ${num(l.suelo.arena_pct, 1)} <small>%</small></dd>
          <dt>Carbono orgánico</dt><dd>${num(l.suelo.carbono_org, 1)} <small>%</small></dd>
          <dt>Lluvia media del año</dt><dd>${num(l.clima.pp_anual_mm, 0)} <small>mm</small></dd>
          <dt>Fuentes</dt><dd><small>${esc(l.suelo.fuente)} · ${esc(l.clima.fuente)}</small></dd>
        </dl></article>
      <article class="card ancho resumen"><h2>Resumen en criollo</h2>${md(d.resumenes.get(l.id) ?? "")}
        <small>Resumen ${l.resumen_fuente === "claude" ? "redactado con ayuda de IA a partir de los números del informe" : "armado automáticamente con los números del informe"}.</small></article>
      ${l.advertencias.length ? `<details class="card ancho"><summary>Avisos sobre los datos (${l.advertencias.length})</summary>
        <ul>${l.advertencias.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></details>` : ""}
    </section>
    <p class="pie">Generado ${esc(l.generado.replace("T", " "))} · fuente de datos: ${esc(l.fuente_datos)}</p>`;
  const el = app.querySelector<HTMLElement>("#mapa-lote")!;
  const m = crearMapa(el, [l], { modo: "detalle" });
  agregarCapasLote(m.map, l, el, capa);
  graficoNDVI(app.querySelector<HTMLCanvasElement>("#ndvi")!, l);
}
