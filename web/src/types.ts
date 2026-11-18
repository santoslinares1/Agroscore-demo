// Tipos del contrato de datos (pipeline/agroscore/schema/*.schema.json)
export interface Componente { clave: string; etiqueta?: string; valor: number | null; peso: number; peso_efectivo?: number | null }
export interface Campania {
  campania: string; cultivo: string | null; cultivo_fuente: string | null; cultivo_cobertura?: number | null;
  ndvi_max: number | null; ndvi_medio: number | null; ndvi_anomalia: number | null;
  ndmi_medio: number | null; pct_nubes: number | null;
  /** v1.2.0: EVI (vigor del score) y NDRE; null/ausente en JSON viejos */
  evi_max?: number | null; evi_medio?: number | null; ndre_max?: number | null; ndre_medio?: number | null;
  obs_validas_px?: number | null; n_escenas?: number | null; hueco_max_semanas?: number | null;
}
export interface Lote {
  id: string; nombre: string; localidad: string; fuente_poligono?: string; area_ha: number;
  centroide: [number, number];
  geometry: { type: "Polygon"; coordinates: number[][][] };
  score: {
    valor: number | null; version: string; confianza?: "alta" | "media" | "baja" | null; componentes: Componente[];
    /** score v1.2.0: null en `valor` = sin dato suficiente (ver motivo_sin_score) */
    cobertura?: number; componentes_usados?: string[]; componentes_sin_dato?: string[];
    reponderado?: boolean; motivo_sin_score?: string | null;
    /** índice con que se calculó el vigor ("evi" | "combinado" | "ndvi"). Obligatorio en el schema (null solo sin
     *  score); opcional acá para tolerar JSON anteriores, que se rotulan "Vigor histórico" sin índice. */
    vigor_base?: "evi" | "combinado" | "ndvi" | null;
    /** campañas con NDVI válido / total: la confianza "alta" exige >= 2/3 (ver pipeline/agroscore/score.py) */
    campanias_con_ndvi?: number; campanias_total?: number;
  };
  campanias: Campania[];
  rotacion: { ultimo_mani: string | null; campanias_desde_mani: number | null; veces_mani_ultimas_5: number;
    campanias_sin_dato_ultimas_5?: number; campanias_con_dato_ultimas_5?: number; campanias_ventana?: number;
    campanias_sin_mani_confirmadas?: number; cobertura_rotacion?: number | null;
    confianza_rotacion?: "completa" | "parcial" | "insuficiente"; anios_recomendados?: number };
  zonas: { alta_pct: number | null; media_pct: number | null; baja_pct: number | null; png: string };
  agua: { max_ha_anegadas: number | null; fecha_max: string | null; frecuencia_pct: number | null;
    /** v1.2.0: lo que marcó solo Sentinel-1 antes de la confirmación óptica/JRC */
    max_ha_s1_sin_confirmar?: number | null; fecha_max_s1_sin_confirmar?: string | null;
    n_escenas_s1?: number | null; n_escenas_s1_con_optico?: number | null;
    n_escenas_s1_marcadas?: number | null; n_escenas_s1_marcadas_sin_optico?: number | null; n_escenas_s1_confirmadas?: number | null; criterio?: string | null };
  suelo: { arcilla_pct: number | null; arena_pct: number | null; carbono_org: number | null; fuente: string };
  clima: { pp_anual_mm: number | null; fuente: string };
  imagenes: { ndvi_ultima: string; rgb_ultima: string; overlay_rgb?: string; fecha_rgb?: string | null;
    overlay_ndvi?: string; overlay_ndmi?: string; overlay_zonas?: string | null; ndvi_campanias?: string;
    campania_overlays?: string; escalas?: { ndvi?: [number, number]; ndmi?: [number, number] };
    bbox?: [number, number, number, number] };
  resumen_md: string; resumen_fuente?: string; pdf: string; generado: string;
  advertencias: string[]; ejemplo: boolean; fuente_datos: string;
}
export interface IndexLote {
  id: string; nombre: string; localidad: string; area_ha: number; score: number | null;
  centroide: [number, number]; ejemplo: boolean;
}
export interface Index { generado: string; score_version: string; ejemplo: boolean; lotes: IndexLote[] }
export type Score = Lote["score"];
