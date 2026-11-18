import type { Datos } from "../data";
import { AVISO_EJEMPLO, textoErrorLote, url } from "../data";
import { agregarCapasLote, crearMapa } from "../mapa";
import { graficoNDVI } from "../grafico";
import { colorScore, cultivoNombre, esc, md, num, SIN_SCORE } from "../fmt";
import { comp, etiquetaComp, explicacion, fraseRotacion, INDICE_VIGOR, nivel, NIVEL_TXT, ultimoManiTxt, vigorBase } from "../textos";
import type { Lote } from "../types";

export function bloqueScore(l: Lote, explicar = true): string {
  const s = l.score;
  return `
    <div class="score-wrap">
      <div class="score-grande ${s.valor === null ? "sin-score" : ""}" style="--c:${colorScore(s.valor)}">
        ${s.valor === null ? `<span class="valor">${SIN_SCORE}</span>` : `<span class="valor">${s.valor}</span><span class="de">/100</span>`}
      </div>
      <div class="componentes">
        ${s.componentes.map((c) => {
          const pe = c.peso_efectivo ?? c.peso;
          const aporte = c.valor === null || s.valor === null ? null : 100 * c.valor * pe;
          const ex = explicacion(c.clave, s);
          return `<div class="comp">
            <div class="comp-t"><span>${esc(etiquetaComp(c, s))} <small class="peso">peso ${num(c.peso * 100, 0, "%")}</small></span>
              <span class="aporte">${num(aporte, 1)} <small>de ${num(pe * 100, 0)} pts</small></span></div>
            <div class="barra" role="img" aria-label="${num(c.valor)} sobre 1"><i class="n-${nivel(c.valor)}" style="width:${(c.valor ?? 0) * 100}%"></i></div>
            ${explicar && ex ? `<p class="comp-ex">${ex.que} <em>${ex.alto}</em></p>` : ""}
          </div>`;
        }).join("")}
      </div>
    </div>
    ${s.valor === null ? `<p class="aviso-score sin">No se calculó un score total: ${esc(s.motivo_sin_score ?? "datos insuficientes")}</p>`
      : s.reponderado ? `<p class="aviso-score parcial"><strong>Score parcial:</strong> calculado sobre el ${num((s.cobertura ?? 1) * 100, 0)} % del peso
        (sin dato: ${esc(s.componentes.filter((c) => c.valor === null).map((c) => etiquetaComp(c, s)).join(", "))}); los pesos de los demás
        componentes se reescalaron proporcionalmente.</p>` : ""}
    <small class="nota">Score = suma de los puntos de cada componente (valor 0–1 × peso × 100) · versión ${esc(s.version)} ·
      <a href="#/como-funciona">cómo se calcula</a></small>`;
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
    ["riesgo_hidrico", "Agua", `Máximo anegado: ${num(l.agua.max_ha_anegadas, 1, " ha")} de ${num(l.area_ha, 1)} ha · frecuencia ${num(l.agua.frecuencia_pct, 1, " %")}.`],
    ["vigor_historico", etiquetaComp({ clave: "vigor_historico", valor: null, peso: 0 }, l.score), fraseVigor(l)],
    ["estabilidad", "Estabilidad", "Qué tan parejo rinde de un año a otro."],
    ["suelo", "Suelo", `Arena ${num(l.suelo.arena_pct, 1, " %")} · arcilla ${num(l.suelo.arcilla_pct, 1, " %")} · carbono orgánico ${num(l.suelo.carbono_org, 1, " %")}.`],
  ];
  return `<ul class="semaforo">${items.map(([k, t, txt]) => {
    const n = nivel(comp(l, k)?.valor ?? null);
    return `<li class="n-${n}"><span class="sem-dot"></span><div><strong>${t}</strong> <span class="sem-tag">${NIVEL_TXT[n]}</span><br><small>${esc(txt)}</small></div></li>`;
  }).join("")}</ul><small class="nota">Semáforo de la demo: verde si el componente vale ≥ 0,75; amarillo entre 0,5 y 0,75; rojo debajo de 0,5.</small>`;
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
       <div class="aviso-lote error" role="alert"><h1>${esc(d.index.lotes.find((x) => x.id === id)?.nombre ?? id)}</h1>
       <p>${esc(textoErrorLote(motivo))}</p><p><small>id <code>${esc(id)}</code> · el resto de los lotes sigue funcionando.</small></p></div>`
    : `<p>No existe el lote <code>${esc(id)}</code>. <a href="#/">Volver</a></p>`;
}

export function vistaDetalle(app: HTMLElement, d: Datos, id: string, capa: string | null = null) {
  const l = d.lotes.get(id);
  if (!l) { app.innerHTML = lotNoDisponible(d, id); return; }
  const r = l.rotacion, z = l.zonas, a = l.agua;
  const fuentes = [...new Set(l.campanias.map((c) => c.cultivo_fuente).filter(Boolean))].join(", ") || "s/d";
  const otros = d.index.lotes.filter((x) => x.id !== id && d.lotes.has(x.id));
  app.innerHTML = `
    <nav class="migas"><a href="#/">← Todos los lotes</a>
      ${otros.map((o) => `<a class="chip-nav" href="#/lote/${o.id}">${esc(o.nombre.replace(/^Lote /, ""))}</a>`).join("")}</nav>
    ${l.ejemplo ? `<div class="aviso-lote">${AVISO_EJEMPLO}: el polígono está dibujado sobre una imagen pública solo para la demo y todos los números son sintéticos. No es un lote de cliente.</div>` : ""}
    <header class="cab-lote">
      <div><h1>${esc(l.nombre)}</h1><p>${esc(l.localidad)} · ${num(l.area_ha, 1)} ha · score ${l.score.valor === null ? SIN_SCORE.toLowerCase() : `${l.score.valor}/100`}</p></div>
      <div class="acciones">
        <a class="btn" href="${url(l.id, l.pdf)}" download="${l.id}_informe.pdf">Descargar PDF</a>
        <a class="btn sec" href="#/informe/${l.id}">Informe para imprimir</a>
        <a class="btn sec" href="#/comparar?ids=${[id, ...otros.map((o) => o.id)].slice(0, 3).join(",")}">Comparar</a>
      </div>
    </header>
    <section class="grid-det">
      <article class="card ancho card-mapa">
        <div id="mapa-lote" class="mapa grande"></div>
        <small>Contorno amarillo = límite del lote. Elegí una capa (NDVI, humedad, zonas) y ajustá la opacidad para verla sobre la imagen satelital.
          Centro: ${l.centroide[1].toFixed(5)}, ${l.centroide[0].toFixed(5)}</small>
      </article>
      <article class="card score-card"><h2>Score AgroScore</h2>${bloqueScore(l)}</article>
      <article class="card"><h2>Lectura rápida</h2>${lecturaRapida(l)}</article>
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
        <small>Fuente del mapa de cultivos: ${esc(fuentes)}. Campaña = octubre a marzo.</small>
      </article>
      <article class="card ancho"><h2>Vigor del cultivo por campaña (NDVI)</h2><div class="chart"><canvas id="ndvi" aria-label="Gráfico de NDVI por campaña"></canvas></div>
        <small>Barras = NDVI máximo de la campaña (doradas = maní); línea = NDVI medio. Escala fija 0–1: más alto, más verde.</small></article>
      <article class="card"><h2>Zonas dentro del lote</h2>
        <img class="img-zonas" src="${url(l.id, z.png)}" alt="Mapa de zonas de ${esc(l.nombre)}" loading="lazy" />
        <div class="zbar">
          <i class="alta" style="width:${z.alta_pct ?? 0}%">Alta ${num(z.alta_pct, 0, "%")}</i>
          <i class="media" style="width:${z.media_pct ?? 0}%">Media ${num(z.media_pct, 0, "%")}</i>
          <i class="baja" style="width:${z.baja_pct ?? 0}%">Baja ${num(z.baja_pct, 0, "%")}</i>
        </div>
        <small>Zonas armadas con el NDVI máximo de todas las campañas: sirven para recorrer primero la zona baja.</small></article>
      <article class="card"><h2>Agua, suelo y clima</h2>
        <dl class="dl">
          <dt>Máx. superficie anegada</dt><dd>${num(a.max_ha_anegadas, 1, " ha")} ${a.fecha_max ? `<small>(${a.fecha_max})</small>` : ""}</dd>
          <dt>Frecuencia histórica de agua</dt><dd>${num(a.frecuencia_pct, 1, " %")}</dd>
          <dt>Arcilla / arena (0–5 cm)</dt><dd>${num(l.suelo.arcilla_pct, 1, " %")} / ${num(l.suelo.arena_pct, 1, " %")}</dd>
          <dt>Carbono orgánico</dt><dd>${num(l.suelo.carbono_org, 1, " %")}</dd>
          <dt>Lluvia media anual</dt><dd>${num(l.clima.pp_anual_mm, 0, " mm")}</dd>
          <dt>Fuentes</dt><dd><small>${esc(l.suelo.fuente)} · ${esc(l.clima.fuente)}</small></dd>
        </dl></article>
      <article class="card ancho resumen"><h2>Resumen para el equipo</h2>${md(d.resumenes.get(l.id) ?? "")}
        <small>Resumen ${l.resumen_fuente === "claude" ? "redactado con IA a partir de los números del informe" : "armado automáticamente con los números del informe"}.</small></article>
      ${l.advertencias.length ? `<details class="card ancho"><summary>Advertencias de datos (${l.advertencias.length})</summary>
        <ul>${l.advertencias.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></details>` : ""}
    </section>
    <p class="pie">Generado ${esc(l.generado.replace("T", " "))} · fuente de datos: ${esc(l.fuente_datos)}</p>`;
  const el = app.querySelector<HTMLElement>("#mapa-lote")!;
  const m = crearMapa(el, [l], { modo: "detalle" });
  agregarCapasLote(m.map, l, el, capa);
  graficoNDVI(app.querySelector<HTMLCanvasElement>("#ndvi")!, l);
}
