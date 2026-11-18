import type { Datos } from "../data";
import { AVISO_EJEMPLO } from "../data";
import { esc, num } from "../fmt";
import { etiquetaComp, explicacion, INDICE_VIGOR, vigorBase, type VigorBase } from "../textos";
import type { Lote } from "../types";

export function vistaComo(app: HTMLElement, d: Datos) {
  const validos = d.index.lotes.map((x) => d.lotes.get(x.id)).filter((x): x is Lote => x !== undefined);
  const l0 = validos[0];
  const comps = l0?.score.componentes ?? [];
  const rec = l0?.rotacion.anios_recomendados;
  // Lo que se explica sale de los lotes que muestra la demo (no de supuestos): índice del vigor y versión de cada uno.
  const porIndice = new Map<VigorBase | null, number>();
  validos.forEach((l) => porIndice.set(vigorBase(l.score), (porIndice.get(vigorBase(l.score)) ?? 0) + 1));
  const indices = [...porIndice.keys()];
  const vigorUnico = indices.length === 1 && l0 !== undefined;
  const filaVigor = (c: (typeof comps)[number]) => {
    if (vigorUnico) return { t: etiquetaComp(c, l0.score), que: explicacion(c.clave, l0.score)?.que ?? "" };
    const det = indices.map((k) => `${porIndice.get(k)} con ${k ? INDICE_VIGOR[k] : "índice sin informar"}`).join(", ");
    return { t: "Vigor histórico", que: `${explicacion(c.clave)?.que ?? ""} El índice depende de los datos de cada lote: en esta demo, ${det} (se indica en cada lote).` };
  };
  const versiones = [...new Set(validos.map((l) => l.score.version))];
  const txtVersion = versiones.length > 1 ? `versiones ${versiones.join(", ")}` : `versión ${versiones[0] ?? d.index.score_version}`;
  app.innerHTML = `
    <nav class="migas"><a href="#/">← Todos los lotes</a></nav>
    <h1>Cómo funciona AgroScore</h1>
    <section class="grid-det">
      <article class="card ancho">
        <h2>De la imagen satelital al informe</h2>
        <ol class="pasos">
          <li><strong>Lote:</strong> se carga el polígono del campo (KML o GeoJSON, por ejemplo exportado de Google Earth).</li>
          <li><strong>Imágenes:</strong> se procesan todas las imágenes Sentinel-2 de cada campaña (octubre a marzo), sacando nubes y sombras.</li>
          <li><strong>Índices:</strong> NDVI y EVI (vigor del cultivo; el EVI no se satura con el cultivo cerrado) y NDMI (humedad de la vegetación) por campaña.
            El vigor del score usa EVI cuando hay suficientes campañas con EVI y NDVI cuando no; cada lote indica cuál.</li>
          <li><strong>Cultivo por campaña:</strong> se cruza el lote con mapas de cultivos (IDECOR para Córdoba; MapBiomas como respaldo) para saber cuándo hubo maní.</li>
          <li><strong>Agua y suelo:</strong> radar Sentinel-1 y registro histórico de agua (JRC) para anegamiento; SoilGrids para textura y carbono; ERA5 para lluvia.</li>
          <li><strong>Score e informe:</strong> todo se resume en un score 0–100, un PDF y esta web. El PDF y la web leen el mismo archivo, así que siempre muestran los mismos números.</li>
        </ol>
        <p>El procesamiento se hace antes de la reunión; esta demo solo muestra los resultados y funciona sin internet
          (sin internet no se ve la imagen satelital de fondo, pero sí el lote y sus capas).</p>
      </article>
      <article class="card ancho">
        <h2>Los componentes del score (${esc(txtVersion)})</h2>
        <table class="comp-tabla como"><thead><tr><th>Componente</th><th>Peso</th><th>Qué mide</th></tr></thead>
          <tbody>${comps.map((c) => {
            const ex = explicacion(c.clave);
            const f = c.clave === "vigor_historico" ? filaVigor(c) : { t: etiquetaComp(c, l0!.score), que: ex?.que ?? "" };
            return `<tr><th>${esc(f.t)}</th><td>${num(c.peso * 100, 0, "%")}</td><td>${esc(f.que)} <em>${ex?.alto ?? ""}</em></td></tr>`;
          }).join("")}</tbody></table>
        <p>Cada componente vale entre 0 y 1. Score = 100 × suma de (peso × componente).
          ${rec !== undefined ? `En rotación, el criterio de esta versión pide al menos <strong>${rec}</strong> campañas sin maní para puntaje completo.` : ""}
          Los pesos son una primera versión para validar con ustedes: se pueden ajustar según lo que más le importa a una empresa manisera.</p>
        <p>Si falta un componente, sus puntos se reparten entre los demás y el score se marca como <em>parcial</em>; sin al menos
          3 campañas con NDVI, o con menos del 70 % del peso con dato, no se da score. <strong>Confianza alta</strong> = todos los componentes con dato, rotación de maní
          con dato completo y al menos 2 de cada 3 campañas con NDVI válido; <strong>baja</strong> = faltan 2 o más componentes,
          la rotación no se pudo evaluar o menos de la mitad de las campañas tiene NDVI; <strong>media</strong> en el resto.</p>
      </article>
      <article class="card">
        <h2>Qué no hace (todavía)</h2>
        <ul><li>No reemplaza la recorrida a campo ni un análisis de suelo.</li>
          <li>No predice rinde en quintales: compara el comportamiento histórico del lote.</li>
          <li>El mapa de cultivos depende de lo que publican IDECOR / MapBiomas para cada campaña.</li></ul>
      </article>
      <article class="card">
        <h2>Sobre los datos de esta demo</h2>
        ${d.index.ejemplo ? `<p class="aviso-lote">${AVISO_EJEMPLO}.</p>
          <p>Los lotes que se ven son de ejemplo: los polígonos se dibujaron sobre una imagen satelital pública solo para mostrar
          cómo se ve el informe, y todos los números fueron generados por código. Con los polígonos reales, el mismo
          sistema produce el informe con datos satelitales reales y este aviso desaparece.</p>`
          : `<p>Los datos de estos lotes fueron procesados con imágenes satelitales y fuentes públicas (ver cada informe).</p>`}
      </article>
    </section>`;
}
