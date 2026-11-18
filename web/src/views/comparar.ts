import type { Datos } from "../data";
import { textoErrorLote, url } from "../data";
import { crearMapa } from "../mapa";
import { colorScore, esc, num, scoreTxt } from "../fmt";
import { lineaTiempo } from "./detalle";
import { etiquetaComp, INDICE_VIGOR, nivel, rotacionSinDato, ultimoManiTxt, vigorBase } from "../textos";
import type { Lote } from "../types";

const MAX = 3;

interface Fila { t: string; html: (l: Lote) => string; valor?: (l: Lote) => number | null; mejor?: "max" | "min" }

const ndviProm = (l: Lote) => {
  const v = l.campanias.map((c) => c.ndvi_max).filter((x): x is number => x !== null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
};

export function vistaComparar(app: HTMLElement, d: Datos, idsParam: string | null) {
  const todos = d.index.lotes.filter((l) => d.lotes.has(l.id)).map((l) => d.lotes.get(l.id)!);
  const rotos = d.index.lotes.filter((l) => d.errores.has(l.id));
  const avisoRotos = rotos.map((l) => `<div class="aviso-lote error" role="alert"><strong>${esc(l.nombre)}</strong>: ${esc(textoErrorLote(d.errores.get(l.id)!))}</div>`).join("");
  if (!todos.length) {
    app.innerHTML = `<nav class="migas"><a href="#/">← Todos los lotes</a></nav><h1>Comparar lotes</h1>${avisoRotos}
      <p>No hay lotes válidos para comparar.</p>`;
    return;
  }
  let ids = (idsParam ?? "").split(",").filter((i) => d.lotes.has(i)).slice(0, MAX);
  if (ids.length < 2) ids = [...new Set([...ids, ...todos.map((l) => l.id)])].slice(0, Math.min(MAX, todos.length));
  const sel = ids.map((i) => d.lotes.get(i)!);
  const comps = sel[0]?.score.componentes ?? [];
  const vigorUnico = new Set(sel.map((l) => vigorBase(l.score))).size === 1;
  const titulo = (c: (typeof comps)[number]) =>
    c.clave === "vigor_historico" && !vigorUnico ? "Vigor histórico" : etiquetaComp(c, sel[0].score);

  const filas: Fila[] = [
    { t: "Ubicación", html: (l) => `<div class="mapa mini" data-mini="${l.id}"></div>` },
    { t: "Score", html: (l) => `<span class="badge-score ${l.score.valor === null ? "sin-score" : ""}" style="background:${colorScore(l.score.valor)}">${scoreTxt(l.score.valor)}</span>`
        + (l.score.valor === null && l.score.motivo_sin_score ? `<br><small>${esc(l.score.motivo_sin_score)}</small>` : l.score.reponderado ? `<br><small>parcial (${num((l.score.cobertura ?? 1) * 100, 0)} % del peso)</small>` : ""),
      valor: (l) => l.score.valor, mejor: "max" },
    ...comps.map((c, i): Fila => ({
      // el vigor puede venir de índices distintos según el lote (score.vigor_base): si no coinciden, se aclara por celda
      t: `${titulo(c)} (peso ${num(c.peso * 100, 0, "%")})`,
      html: (l) => {
        const v = l.score.componentes[i]?.valor ?? null, vb = vigorBase(l.score);
        const indice = c.clave === "vigor_historico" && !vigorUnico && vb ? ` <small>(${INDICE_VIGOR[vb]})</small>` : "";
        return `<span class="mini-barra"><i class="n-${nivel(v)}" style="width:${(v ?? 0) * 100}%"></i></span> ${num(v)}${indice}`;
      },
      valor: (l) => l.score.componentes[i]?.valor ?? null, mejor: "max",
    })),
    { t: "Superficie", html: (l) => num(l.area_ha, 1, " ha") },
    { t: "Último maní", html: (l) => esc(ultimoManiTxt(l)) },
    { t: "Campañas desde el último maní", html: (l) => `${l.rotacion.campanias_desde_mani ?? "—"}`,
      valor: (l) => (rotacionSinDato(l) ? null : l.rotacion.campanias_desde_mani ?? 99), mejor: "max" },
    { t: "Veces con maní en las últimas 5", html: (l) => `${l.rotacion.veces_mani_ultimas_5}`,
      valor: (l) => l.rotacion.veces_mani_ultimas_5, mejor: "min" },
    { t: "Campañas", html: (l) => lineaTiempo(l, true) },
    { t: "NDVI máx. promedio", html: (l) => num(ndviProm(l)), valor: ndviProm, mejor: "max" },
    { t: "Zonas Alta / Media / Baja", html: (l) => `${num(l.zonas.alta_pct, 0)} / ${num(l.zonas.media_pct, 0)} / ${num(l.zonas.baja_pct, 0)} %` },
    { t: "Máx. anegado", html: (l) => num(l.agua.max_ha_anegadas, 1, " ha"), valor: (l) => l.agua.max_ha_anegadas, mejor: "min" },
    { t: "Frecuencia de agua", html: (l) => num(l.agua.frecuencia_pct, 1, " %"), valor: (l) => l.agua.frecuencia_pct, mejor: "min" },
    { t: "Arena / arcilla", html: (l) => `${num(l.suelo.arena_pct, 1)} / ${num(l.suelo.arcilla_pct, 1)} %` },
    { t: "Lluvia media anual", html: (l) => num(l.clima.pp_anual_mm, 0, " mm") },
    { t: "Zonas", html: (l) => `<img class="img-comp" src="${url(l.id, l.zonas.png)}" alt="Zonas de ${esc(l.nombre)}" loading="lazy">` },
    { t: "Informe", html: (l) => `<a class="btn chico" href="${url(l.id, l.pdf)}" download="${l.id}_informe.pdf">PDF</a> <a href="#/lote/${l.id}">Ver detalle</a>` },
  ];

  const mejorIdx = (f: Fila): Set<number> => {
    if (!f.valor || sel.length < 2) return new Set();
    const v = sel.map(f.valor);
    const ok = v.filter((x): x is number => x !== null);
    if (!ok.length || new Set(ok).size === 1) return new Set();
    const best = f.mejor === "min" ? Math.min(...ok) : Math.max(...ok);
    return new Set(v.map((x, i) => (x === best ? i : -1)).filter((i) => i >= 0));
  };

  app.innerHTML = `
    <nav class="migas"><a href="#/">← Todos los lotes</a></nav>
    <h1>Comparar lotes</h1>
    ${avisoRotos}
    <div class="selector">${todos.map((l) => `
      <label><input type="checkbox" value="${l.id}" ${ids.includes(l.id) ? "checked" : ""}> ${esc(l.nombre)}
      ${l.ejemplo ? `<span class="chip-ejemplo">EJEMPLO</span>` : ""}</label>`).join("")}
      <small>Elegí 2 o 3 lotes. <span class="mejor-demo">Resaltado</span> = mejor valor de la fila.</small></div>
    <div class="tabla-wrap"><table class="comp-tabla">
      <thead><tr><th></th>${sel.map((l) => `<th>${esc(l.nombre)}<br><small>${esc(l.localidad)} · ${num(l.area_ha, 1)} ha</small></th>`).join("")}</tr></thead>
      <tbody>${filas.map((f) => { const b = mejorIdx(f); return `<tr><th>${esc(f.t)}</th>${sel.map((l, i) =>
        `<td class="${b.has(i) ? "mejor" : ""}">${f.html(l)}</td>`).join("")}</tr>`; }).join("")}</tbody>
    </table></div>`;

  app.querySelectorAll<HTMLElement>("[data-mini]").forEach((el) => {
    const l = d.lotes.get(el.dataset.mini!)!;
    crearMapa(el, [l], { modo: "mini", onClick: () => (location.hash = `#/lote/${l.id}`) });
  });
  app.querySelectorAll<HTMLInputElement>(".selector input").forEach((cb) => cb.addEventListener("change", () => {
    const marcados = [...app.querySelectorAll<HTMLInputElement>(".selector input:checked")].map((x) => x.value);
    if (marcados.length > MAX) { cb.checked = false; return; }
    if (marcados.length >= 2) location.hash = `#/comparar?ids=${marcados.join(",")}`;
  }));
}
