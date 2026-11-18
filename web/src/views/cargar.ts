import L from "leaflet";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import type { Position } from "geojson";
import type { Datos } from "../data";
import { contornoLote, mapaBase } from "../mapa";
import { esc } from "../fmt";
import {
  aGeoJSONPipeline, fmtHa, leerArchivo, nuevoId, validarPoligono, type LoteCargado, type PoligonoLeido,
} from "../carga/geo";
import { actualizarLote, guardarLotes, leerLotes } from "../carga/almacen";
import { detectarBackend, enviarLote, estadoTrabajo, type Salud, BACKEND } from "../carga/backend";

type Candidato = PoligonoLeido & { sel: boolean };
const aLatLng = (r: Position[]) => r.map(([lon, lat]) => [lat, lon] as [number, number]);
const deLatLng = (ll: L.LatLng[]) => ll.map((p) => [Number(p.lng.toFixed(7)), Number(p.lat.toFixed(7))]);

export function comandoPipeline(): string {
  return [
    "# 1) Guardá el GeoJSON descargado como pipeline/data/lotes_cargados.geojson",
    "cd pipeline",
    "earthengine authenticate          # una sola vez, con tu cuenta",
    "python run_pipeline.py data/lotes_cargados.geojson --gee-project TU_PROYECTO --out out_cargados",
    "cd .. && python scripts/copiar_salidas.py --origen pipeline/out_cargados --agregar",
    "# o, con el servidor local:  python pipeline/server.py --gee-project TU_PROYECTO   (botón «Analizar ahora»)",
  ].join("\n");
}

export function vistaCargar(app: HTMLElement, d: Datos, recargar: () => Promise<void>) {
  app.innerHTML = `
    <nav class="migas"><a href="#/">← Todos los lotes</a></nav>
    <header class="cab-lote"><div><h1>Cargar un lote</h1>
      <p>Subí el contorno del campo (KML o KMZ de Google Earth, o GeoJSON) o dibujalo sobre la imagen satelital.
      El lote queda guardado en este navegador como <strong>pendiente de análisis</strong>: el score se calcula después con imágenes satelitales reales.</p></div>
      <div id="estado-backend" class="estado-backend buscando">Buscando servidor local…</div></header>
    <section class="cargar">
      <div class="mapa-wrap"><div id="mapa-carga" class="mapa grande"></div></div>
      <aside class="panel-carga">
        <div class="card paso"><h2>1. Subir archivo</h2>
          <label class="drop" id="drop"><input type="file" id="archivo" accept=".kml,.kmz,.geojson,.json">
            <strong>Elegí o arrastrá un archivo</strong><small>KML, KMZ o GeoJSON · puede tener varios polígonos</small></label>
          <div id="encontrados"></div></div>
        <div class="card paso"><h2>2. … o dibujarlo en el mapa</h2>
          <div class="botones"><button class="btn" type="button" id="dibujar">Dibujar polígono</button>
            <button class="btn sec" type="button" id="editar" disabled>Editar vértices</button>
            <button class="btn sec" type="button" id="limpiar" disabled>Borrar</button></div>
          <small>Hacé clic en cada esquina del lote y cerralo tocando el primer punto. Usá «Topográfico» o «Relieve» en el selector de capas si querés otro fondo.</small></div>
        <form class="card paso" id="form"><h2>3. Datos del lote</h2>
          <label>Nombre del lote <span class="req">*</span><input name="nombre" required maxlength="80" placeholder="Ej.: Lote 4 – La Esperanza"></label>
          <label>Propietario / establecimiento <small>(opcional)</small><input name="propietario" maxlength="80" placeholder="Ej.: Est. La Esperanza, Alejandro Roca"></label>
          <label>Notas de cultivo <small>(opcional)</small><textarea name="notas" rows="2" maxlength="400" placeholder="Ej.: maní 2023/24 según el dueño; soja 2024/25"></textarea></label>
          <div id="validacion" class="validacion vacia">Todavía no hay un polígono. Subí un archivo o dibujalo.</div>
          <button class="btn" type="submit" id="guardar" disabled>Guardar lote</button>
        </form>
      </aside>
    </section>
    <section class="card pendientes" id="pendientes"></section>`;

  const el = app.querySelector<HTMLElement>("#mapa-carga")!;
  const map = mapaBase(el);
  const capaPendientes = L.featureGroup().addTo(map);
  const capaCandidatos = L.featureGroup().addTo(map);
  let candidatos: Candidato[] = [];
  let dibujado: { capa: L.Polygon; anillo: Position[] } | null = null;
  let backend: Salud | null = null;
  const $ = <T extends HTMLElement>(s: string) => app.querySelector<T>(s)!;

  map.pm.setLang("es");
  map.pm.setGlobalOptions({ allowSelfIntersection: false, templineStyle: { color: "#ffe14d" }, hintlineStyle: { color: "#ffe14d", dashArray: "5,5" },
    pathOptions: { color: "#ffe14d", weight: 3.5, fillOpacity: 0.1 } } as any);

  // ---------- selección actual ----------
  const seleccion = (): (PoligonoLeido)[] =>
    dibujado ? [{ nombre: "Polígono dibujado", anillo: dibujado.anillo, huecos: 0, origen: "dibujo" }] : candidatos.filter((c) => c.sel);

  function pintarCandidatos() {
    capaCandidatos.clearLayers();
    candidatos.forEach((c, i) => {
      const { linea } = contornoLote(aLatLng(c.anillo), c.sel ? "#ffe14d" : "#ffffff", capaCandidatos,
        c.sel ? {} : { dashArray: "6,6", weight: 2, fillOpacity: 0 });
      linea.bindTooltip(esc(c.nombre)).on("click", () => { candidatos[i].sel = !candidatos[i].sel; refrescar(); });
    });
  }

  function encuadrar() {
    const b = L.featureGroup([...capaCandidatos.getLayers(), ...(dibujado ? [dibujado.capa] : [])]).getBounds();
    if (b.isValid()) map.fitBounds(b, { padding: [30, 30], maxZoom: 17 });
  }

  function refrescar() {
    pintarCandidatos();
    const enc = $("#encontrados");
    enc.innerHTML = candidatos.length ? `
      <div class="enc-t">${candidatos.length} polígono(s) encontrado(s) ${candidatos.length > 1 ? `<button type="button" class="link" id="todos">Elegir todos</button> · <button type="button" class="link" id="ninguno">ninguno</button>` : ""}</div>
      <ul class="enc-lista">${candidatos.map((c, i) => {
        const v = validarPoligono(c);
        return `<li><label><input type="checkbox" data-i="${i}" ${c.sel ? "checked" : ""}> <span>${esc(c.nombre)}</span>
          <small>${v.ok ? `${fmtHa(v.area_ha)} ha` : `<span class="err">no válido</span>`}</small></label></li>`;
      }).join("")}</ul>` : "";
    enc.querySelectorAll<HTMLInputElement>("input[data-i]").forEach((cb) => cb.addEventListener("change", () => {
      candidatos[Number(cb.dataset.i)].sel = cb.checked; refrescar();
    }));
    enc.querySelector("#todos")?.addEventListener("click", () => { candidatos.forEach((c) => (c.sel = true)); refrescar(); });
    enc.querySelector("#ninguno")?.addEventListener("click", () => { candidatos.forEach((c) => (c.sel = false)); refrescar(); });

    const sel = seleccion();
    $<HTMLButtonElement>("#editar").disabled = !(dibujado || sel.length === 1);
    $<HTMLButtonElement>("#limpiar").disabled = !(dibujado || candidatos.length);
    const val = $("#validacion");
    if (!sel.length) {
      val.className = "validacion vacia";
      val.textContent = candidatos.length ? "Marcá al menos un polígono de la lista." : "Todavía no hay un polígono. Subí un archivo o dibujalo.";
      $<HTMLButtonElement>("#guardar").disabled = true;
      $<HTMLButtonElement>("#guardar").textContent = "Guardar lote";
      return;
    }
    const vs = sel.map((s) => ({ s, v: validarPoligono(s) }));
    const okCount = vs.filter((x) => x.v.ok).length;
    const total = (okCount ? vs.filter((x) => x.v.ok) : vs).reduce((a, x) => a + x.v.area_ha, 0);
    val.className = `validacion ${okCount === vs.length ? "ok" : okCount ? "parcial" : "error"}`;
    val.innerHTML = `
      <div class="val-area"><strong>${fmtHa(total)} ha</strong> ${vs.length > 1 ? `en ${okCount} de ${vs.length} polígonos válidos` : okCount ? "· geometría válida" : ""}</div>
      ${vs.map(({ s, v }) => (v.errores.length || v.avisos.length) ? `<div class="val-item">${vs.length > 1 ? `<b>${esc(s.nombre)}:</b> ` : ""}
        ${v.errores.map((e) => `<div class="err">✗ ${esc(e)}</div>`).join("")}${v.avisos.map((a) => `<div class="aviso">⚠ ${esc(a)}</div>`).join("")}</div>` : "").join("")}`;
    $<HTMLButtonElement>("#guardar").disabled = okCount === 0;
    $<HTMLButtonElement>("#guardar").textContent = okCount > 1 ? `Guardar ${okCount} lotes` : "Guardar lote";
    const nombre = $<HTMLInputElement>("input[name=nombre]");
    if (!nombre.value && sel.length === 1 && sel[0].origen !== "dibujo") nombre.value = sel[0].nombre;
  }

  // ---------- archivo ----------
  async function cargarArchivo(f: File) {
    quitarDibujo();
    try {
      const polis = await leerArchivo(f.name, await f.arrayBuffer());
      candidatos = polis.map((p, i) => ({ ...p, sel: polis.length === 1 || i === 0 }));
      $("#encontrados").classList.remove("error");
      refrescar();
      encuadrar();
    } catch (e) {
      candidatos = [];
      refrescar();
      $("#encontrados").innerHTML = `<div class="err">✗ ${esc(String((e as Error).message ?? e))}</div>`;
    }
  }
  const inp = $<HTMLInputElement>("#archivo");
  inp.addEventListener("change", () => inp.files?.[0] && cargarArchivo(inp.files[0]));
  const drop = $("#drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("encima"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("encima"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("encima"); const f = e.dataTransfer?.files[0]; if (f) cargarArchivo(f); });

  // ---------- dibujo / edición ----------
  function quitarDibujo() {
    if (dibujado) { map.removeLayer(dibujado.capa); dibujado = null; }
    map.pm.disableDraw();
  }
  $("#dibujar").addEventListener("click", () => {
    quitarDibujo();
    candidatos = [];
    refrescar();
    // mientras se dibuja, los contornos ya guardados no capturan los clics
    map.removeLayer(capaPendientes);
    map.pm.enableDraw("Polygon", { snappable: false } as any);
  });
  map.on("pm:drawend", () => { if (!map.hasLayer(capaPendientes)) capaPendientes.addTo(map); });
  map.on("pm:create", (e: any) => {
    const capa = e.layer as L.Polygon;
    const anillo = deLatLng((capa.getLatLngs()[0] as L.LatLng[]));
    dibujado = { capa, anillo: [...anillo, anillo[0]] };
    capa.on("pm:edit pm:markerdragend pm:vertexadded pm:vertexremoved", () => {
      const a = deLatLng((capa.getLatLngs()[0] as L.LatLng[]));
      dibujado = { capa, anillo: [...a, a[0]] };
      refrescar();
    });
    refrescar();
  });
  $("#editar").addEventListener("click", () => {
    if (!dibujado) {
      // convertir el polígono subido seleccionado en editable
      const s = candidatos.find((c) => c.sel);
      if (!s) return;
      candidatos = [];
      capaCandidatos.clearLayers();
      const capa = L.polygon(aLatLng(s.anillo.slice(0, -1)), { color: "#ffe14d", weight: 3.5, fillOpacity: 0.1 }).addTo(map);
      map.fire("pm:create", { layer: capa });
      $<HTMLInputElement>("input[name=nombre]").value ||= s.nombre;
    }
    const capa = dibujado!.capa;
    if (capa.pm.enabled()) { capa.pm.disable(); $("#editar").textContent = "Editar vértices"; }
    else { capa.pm.enable({ allowSelfIntersection: false } as any); $("#editar").textContent = "Terminar edición"; }
  });
  $("#limpiar").addEventListener("click", () => { quitarDibujo(); candidatos = []; inp.value = ""; refrescar(); $("#encontrados").innerHTML = ""; });

  // ---------- guardar ----------
  $("#form").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = new FormData(e.target as HTMLFormElement);
    const base = String(f.get("nombre") ?? "").trim();
    if (!base) { $<HTMLInputElement>("input[name=nombre]").focus(); return; }
    const sel = seleccion().map((s) => ({ s, v: validarPoligono(s) })).filter((x) => x.v.ok);
    const existentes = new Set([...leerLotes().map((l) => l.id), ...d.index.lotes.map((l) => l.id)]);
    const nuevos: LoteCargado[] = sel.map(({ s, v }) => {
      const nombre = sel.length > 1 ? `${base} – ${s.nombre}` : base;
      const id = nuevoId(nombre, existentes);
      existentes.add(id);
      return { id, nombre, propietario: String(f.get("propietario") ?? "").trim(), notas: String(f.get("notas") ?? "").trim(),
        anillo: v.anillo, area_ha: v.area_ha, origen: s.origen, creado: new Date().toISOString(), estado: "pendiente", avisos: v.avisos };
    });
    guardarLotes([...leerLotes(), ...nuevos]);
    quitarDibujo(); candidatos = []; inp.value = ""; $("#encontrados").innerHTML = "";
    (e.target as HTMLFormElement).reset();
    refrescar();
    pintarPendientes(nuevos.map((n) => n.id));
  });

  // ---------- lista de pendientes ----------
  function pintarPendientes(resaltar: string[] = []) {
    const lotes = leerLotes();
    capaPendientes.clearLayers();
    lotes.forEach((l) => contornoLote(aLatLng(l.anillo), l.estado === "analizado" ? "#4caf50" : "#cfd8dc", capaPendientes,
      { dashArray: "8,6", weight: 2.5, fillOpacity: 0.05 }).linea.bindTooltip(`${esc(l.nombre)} · ${fmtHa(l.area_ha)} ha · pendiente`));
    const puedeAnalizar = !!backend?.gee_ok;
    const sec = $("#pendientes");
    sec.innerHTML = `
      <div class="pend-cab"><h2>Lotes cargados <small>(${lotes.length})</small></h2>
        ${lotes.length ? `<div class="botones"><button class="btn sec chico" type="button" id="exportar">Descargar GeoJSON para el pipeline</button></div>` : ""}</div>
      ${lotes.length ? `<ul class="pend-lista">${lotes.map((l) => `
        <li class="pend ${resaltar.includes(l.id) ? "nuevo" : ""}" data-id="${l.id}">
          <div class="pend-info"><strong>${esc(l.nombre)}</strong>
            <small>${fmtHa(l.area_ha)} ha${l.propietario ? ` · ${esc(l.propietario)}` : ""} · ${esc(l.origen)} · ${new Date(l.creado).toLocaleDateString("es-AR")}</small>
            ${l.notas ? `<small class="notas">Notas: ${esc(l.notas)}</small>` : ""}
            ${chipEstado(l)}
            ${l.estado === "analizando" ? `<div class="progreso"><i style="width:0%"></i></div><small class="paso-txt">En cola…</small>` : ""}
            ${l.estado === "error" ? `<small class="err">Error del análisis: ${esc(l.error ?? "")}</small>` : ""}
          </div>
          <div class="pend-acc">
            ${l.estado === "analizado" ? `<a class="btn chico" href="#/lote/${l.id}">Ver informe</a>` : ""}
            <button class="btn sec chico" type="button" data-acc="ver">Ver en el mapa</button>
            ${l.estado !== "analizado" ? `<button class="btn chico" type="button" data-acc="analizar" ${puedeAnalizar && l.estado !== "analizando" ? "" : "disabled"}
              title="${puedeAnalizar ? "Correr el análisis con Earth Engine en el servidor local" : "Necesita el servidor local con Earth Engine autenticado"}">Analizar ahora</button>` : ""}
            <button class="btn sec chico" type="button" data-acc="geojson">GeoJSON</button>
            <button class="btn sec chico peligro" type="button" data-acc="borrar">Eliminar</button>
          </div></li>`).join("")}</ul>
        <details class="comando" ${backend?.gee_ok ? "" : "open"}><summary>Cómo analizarlos sin el servidor local (exportar y correr el pipeline)</summary>
          <pre id="cmd">${esc(comandoPipeline())}</pre><button class="btn sec chico" type="button" id="copiar">Copiar comandos</button></details>`
        : `<p class="vacio">Todavía no cargaste lotes. Los que guardes aparecen acá como <em>pendientes de análisis</em>: no tienen score hasta que se procesen con imágenes satelitales.</p>`}`;

    sec.querySelector("#exportar")?.addEventListener("click", () => descargar(lotes, "lotes_cargados.geojson"));
    sec.querySelector("#copiar")?.addEventListener("click", async (ev) => {
      try { await navigator.clipboard.writeText(comandoPipeline()); (ev.target as HTMLElement).textContent = "¡Copiado!"; }
      catch { (ev.target as HTMLElement).textContent = "Seleccioná el texto y copialo"; }
    });
    sec.querySelectorAll<HTMLButtonElement>("button[data-acc]").forEach((b) => b.addEventListener("click", () => {
      const id = b.closest<HTMLElement>("li")!.dataset.id!;
      const l = leerLotes().find((x) => x.id === id)!;
      const acc = b.dataset.acc;
      if (acc === "ver") map.fitBounds(L.latLngBounds(aLatLng(l.anillo)), { padding: [30, 30], maxZoom: 17 });
      if (acc === "geojson") descargar([l], `${l.id}.geojson`);
      if (acc === "borrar" && confirm(`¿Eliminar «${l.nombre}» de este navegador?`)) { guardarLotes(leerLotes().filter((x) => x.id !== id)); pintarPendientes(); }
      if (acc === "analizar") analizar(l);
    }));
    lotes.filter((l) => l.estado === "analizando" && l.trabajo).forEach((l) => seguir(l.id, l.trabajo!));
  }

  function chipEstado(l: LoteCargado): string {
    if (l.estado === "analizado") return `<span class="chip-estado analizado">Analizado con datos satelitales</span>`;
    if (l.estado === "analizando") return `<span class="chip-estado analizando">Analizando…</span>`;
    if (l.estado === "error") return `<span class="chip-estado error">Lote cargado – análisis con error</span>`;
    return `<span class="chip-estado pendiente">Lote cargado – pendiente de análisis</span>`;
  }

  async function analizar(l: LoteCargado) {
    try {
      const t = await enviarLote(l);
      actualizarLote(l.id, { estado: "analizando", trabajo: t.id, error: undefined });
      pintarPendientes();
    } catch (e) {
      actualizarLote(l.id, { estado: "error", error: String((e as Error).message ?? e) });
      pintarPendientes();
    }
  }

  const siguiendo = new Set<string>();
  function seguir(id: string, trabajo: string) {
    if (siguiendo.has(trabajo)) return;
    siguiendo.add(trabajo);
    const tick = async () => {
      if (!document.body.contains(sec())) { siguiendo.delete(trabajo); return; }
      try {
        const t = await estadoTrabajo(trabajo);
        const li = app.querySelector<HTMLElement>(`li[data-id="${id}"]`);
        if (li) {
          li.querySelector<HTMLElement>(".progreso i")?.style.setProperty("width", `${Math.round(t.progreso * 100)}%`);
          const p = li.querySelector(".paso-txt"); if (p) p.textContent = t.paso || t.estado;
        }
        if (t.estado === "listo") { siguiendo.delete(trabajo); actualizarLote(id, { estado: "analizado" }); await recargar(); pintarPendientes(); return; }
        if (t.estado === "error") { siguiendo.delete(trabajo); actualizarLote(id, { estado: "error", error: t.error ?? "error desconocido" }); pintarPendientes(); return; }
      } catch (e) {
        const li = app.querySelector(`li[data-id="${id}"] .paso-txt`);
        if (li) li.textContent = `No se pudo consultar el servidor (${(e as Error).message}). Reintentando…`;
      }
      setTimeout(tick, 2000);
    };
    tick();
  }
  const sec = () => app.querySelector("#pendientes");

  function descargar(lotes: LoteCargado[], nombre: string) {
    const blob = new Blob([JSON.stringify(aGeoJSONPipeline(lotes), null, 2)], { type: "application/geo+json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = nombre;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  // ---------- servidor local ----------
  const pintarBackend = (s: Salud | null) => {
    backend = s;
    const eb = app.querySelector<HTMLElement>("#estado-backend");
    if (!eb) return;
    if (!s) { eb.className = "estado-backend no"; eb.innerHTML = `Servidor local no detectado · podés <b>exportar</b> los lotes y correr el pipeline (abajo).`; }
    else if (s.verificando) { eb.className = "estado-backend buscando"; eb.innerHTML = `Servidor local conectado · verificando Earth Engine…`; setTimeout(() => detectarBackend().then(pintarBackend), 3000); }
    else if (!s.gee_ok) {
      eb.className = "estado-backend gee-no";
      eb.innerHTML = `<b>Servidor local conectado, pero Earth Engine no está listo.</b> ${esc(s.gee_detalle)}
        <br>Mientras tanto exportá los lotes (abajo). <button type="button" class="link" id="reintentar-gee">Volver a verificar</button>`;
      eb.querySelector("#reintentar-gee")?.addEventListener("click", () => { eb.innerHTML = "Verificando Earth Engine…"; detectarBackend(true).then(pintarBackend); });
    }
    else { eb.className = "estado-backend si"; eb.innerHTML = `Servidor local conectado (${esc(BACKEND)}) · Earth Engine listo: usá «Analizar ahora».`; }
    pintarPendientes();
  };
  detectarBackend().then(pintarBackend);
  pintarPendientes();
  const pend = leerLotes();
  if (pend.length) setTimeout(() => map.fitBounds(L.latLngBounds(pend.flatMap((l) => aLatLng(l.anillo))), { padding: [40, 40], maxZoom: 15 }), 80);
  refrescar();
}
