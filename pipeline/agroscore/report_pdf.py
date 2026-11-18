"""Informe PDF de 4 páginas alimentado SOLO por lote.json (misma fuente que la web)."""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from . import config  # noqa: E402
from .score import etiqueta_componente  # noqa: E402

VERDE = colors.HexColor("#1f6f43")
ROJO = colors.HexColor("#b00020")
MANI = colors.HexColor("#f4d27a")

CULTIVO_NOMBRE = {
    "mani": "Maní", "soja": "Soja", "maiz": "Maíz", "girasol": "Girasol", "sorgo": "Sorgo",
    "trigo": "Trigo", "pastura": "Pastura", "mixto": "Mixto", "otros": "Otros",
    "otros_cultivos": "Otros cultivos", None: "Sin dato",
    "otros_posible_mani": "Otros (maní no separable)", "agricultura": "Agricultura (sin detalle)",
    "cultivo_temporario": "Cultivo temporario (sin detalle)", "mosaico_agropecuario": "Mosaico agropecuario",
    "maiz_2da": "Maíz de 2da", "soja_2da": "Soja de 2da", "no_agricola": "No agrícola", "forestacion": "Forestación",
    "pastizal": "Pastizal", "monte": "Monte", "agua": "Agua", "urbano": "Urbano", "cultivo_perenne": "Cultivo perenne",
}


def _esc(t: str) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt(v, dec: int = 2, suf: str = "") -> str:
    if v is None:
        return "s/d"
    if isinstance(v, float):
        return f"{v:.{dec}f}".replace(".", ",") + suf
    return f"{v}{suf}"


def grafico_ndvi(lote: dict, path: Path) -> Path:
    camp = lote["campanias"]
    x = [c["campania"] for c in camp]
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=120)
    colores = ["#c9a227" if c["cultivo"] == "mani" else "#2e7d32" for c in camp]
    ax.bar(x, [c["ndvi_max"] or 0 for c in camp], color=colores, alpha=0.85, label="NDVI máx.")
    ax.plot(x, [c["ndvi_medio"] for c in camp], color="#1b3a57", marker="o", label="NDVI medio")
    if any(c.get("evi_max") is not None for c in camp):
        ax.plot(x, [c.get("evi_max") for c in camp], color="#c2185b", marker="s", linestyle="--", label="EVI máx.")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Índice")
    ax.tick_params(axis="x", labelrotation=45, labelsize=8)
    ax.legend(loc="lower left", fontsize=8)
    ax.set_title("NDVI y EVI por campaña (barras doradas = maní)", fontsize=10)
    if lote.get("ejemplo"):
        ax.text(0.5, 0.5, config.AVISO_EJEMPLO, transform=ax.transAxes, ha="center", va="center",
                color="#b00020", alpha=0.3, fontsize=18, rotation=15, weight="bold")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def _md_a_parrafos(md: str) -> list[str]:
    out = []
    for bloque in re.split(r"\n\s*\n", md.strip()):
        t = bloque.strip().lstrip("#").strip()
        t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        out.append(t.replace("\n", " "))
    return out


def generar(lote: dict, carpeta: Path, resumen_md: str) -> Path:
    carpeta = Path(carpeta)
    pdf_path = carpeta / lote["pdf"]
    chart = grafico_ndvi(lote, carpeta / "ndvi_campanias.png")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=VERDE, fontSize=22, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=VERDE)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=10, leading=14)
    peq = ParagraphStyle("p", parent=body, fontSize=8, textColor=colors.grey)
    aviso = ParagraphStyle("av", parent=body, textColor=colors.white, backColor=ROJO, fontSize=12,
                           alignment=1, borderPadding=6, spaceAfter=10, leading=16)
    ejemplo = bool(lote.get("ejemplo"))

    def encabezado(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(2 * cm, 1.2 * cm, f"AgroScore · {lote['nombre']} · generado {lote['generado'][:10]}"
                          f" · score v{lote['score']['version']}")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
        if ejemplo:
            canvas.setFillColor(ROJO)
            canvas.rect(0, A4[1] - 1.1 * cm, A4[0], 1.1 * cm, fill=1, stroke=0)
            canvas.setFillColor(colors.white)
            canvas.setFont("Helvetica-Bold", 12)
            canvas.drawCentredString(A4[0] / 2, A4[1] - 0.75 * cm, config.AVISO_EJEMPLO.upper())
            canvas.setFillColor(colors.Color(0.69, 0, 0.13, alpha=0.08))
            canvas.setFont("Helvetica-Bold", 44)
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "LOTE DE EJEMPLO")
        canvas.restoreState()

    s = lote["score"]
    st: list = []
    # --- Página 1: portada y score ---
    st.append(Paragraph("Informe AgroScore de lote", h1))
    if ejemplo:
        st.append(Paragraph(f"{config.AVISO_EJEMPLO}. Polígono y números sintéticos generados por código; "
                            "no corresponden a un campo real.", aviso))
    st.append(Paragraph(f"<b>{lote['nombre']}</b> · {lote['localidad']} · {fmt(lote['area_ha'], 1)} ha", body))
    st.append(Paragraph(f"Centroide: {lote['centroide'][1]:.4f}, {lote['centroide'][0]:.4f}", peq))
    st.append(Spacer(1, 14))
    sin_score = s["valor"] is None
    if sin_score:
        st.append(Paragraph("<font size=24 color='#b00020'><b>Score AgroScore: sin dato suficiente</b></font>",
                            ParagraphStyle("sc", parent=body, leading=30)))
        st.append(Spacer(1, 4))
        st.append(Paragraph(f"No se calculó un score total. Motivo: {_esc(s.get('motivo_sin_score') or 'datos insuficientes')}",
                            ParagraphStyle("sm", parent=body, textColor=ROJO)))
    else:
        st.append(Paragraph(f"<font size=30 color='#1f6f43'><b>Score AgroScore: {fmt(s['valor'])}/100</b></font>",
                            ParagraphStyle("sc", parent=body, leading=36)))
        if s.get("reponderado"):
            sin = ", ".join(etiqueta_componente(c["clave"], s.get("vigor_base")) for c in s["componentes"] if c["valor"] is None)
            st.append(Spacer(1, 4))
            st.append(Paragraph(f"<b>Score parcial:</b> calculado sobre el {round(100 * s.get('cobertura', 1))} % del peso "
                                f"(sin dato: {_esc(sin)}); los pesos de los demás componentes se reescalaron "
                                "proporcionalmente (columna «Peso efectivo»).", ParagraphStyle("sp", parent=body, textColor=ROJO)))
    st.append(Spacer(1, 10))
    filas = [["Componente", "Valor (0–1)", "Peso", "Peso efectivo", "Aporte"]]
    for c in s["componentes"]:
        pe = c.get("peso_efectivo")
        aporte = None if c["valor"] is None or pe is None else round(100 * c["valor"] * pe, 1)
        filas.append([etiqueta_componente(c["clave"], s.get("vigor_base")), fmt(c["valor"]), fmt(c["peso"]), fmt(pe), fmt(aporte, 1)])
    t = Table(filas, colWidths=[6 * cm, 2.6 * cm, 2.2 * cm, 3 * cm, 2.2 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), VERDE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    st.append(t)
    st.append(Spacer(1, 8))
    st.append(Paragraph("Score = 100 × Σ (peso efectivo × componente); si no falta ningún componente, peso efectivo = peso. "
                        f"Sin score si faltan las series satelitales (vigor y estabilidad) o si hay dato para menos del "
                        f"{round(100 * config.SCORE_COBERTURA_MIN)} % del peso. Ver metodología en la página 4.", peq))
    st.append(Spacer(1, 14))
    st.append(Paragraph("Resumen", h2))
    for p in _md_a_parrafos(resumen_md):
        st.append(Paragraph(p, body))
    st.append(PageBreak())

    # --- Página 2: campañas y rotación ---
    st.append(Paragraph("Historia por campaña (oct–mar)", h2))
    st.append(Image(str(chart), width=17 * cm, height=6.8 * cm))
    filas = [["Campaña", "Cultivo", "Fuente", "NDVI máx", "NDVI medio", "EVI máx", "NDRE máx", "Anomalía", "NDMI", "% nubes"]]
    estilos = [("BACKGROUND", (0, 0), (-1, 0), VERDE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
               ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8)]
    for i, c in enumerate(lote["campanias"], start=1):
        filas.append([c["campania"], CULTIVO_NOMBRE.get(c["cultivo"], c["cultivo"]), c["cultivo_fuente"] or "s/d",
                      fmt(c["ndvi_max"]), fmt(c["ndvi_medio"]), fmt(c.get("evi_max")), fmt(c.get("ndre_max")),
                      fmt(c["ndvi_anomalia"]), fmt(c["ndmi_medio"]), fmt(c["pct_nubes"])])
        if c["cultivo"] == "mani":
            estilos.append(("BACKGROUND", (0, i), (-1, i), MANI))
    t = Table(filas)
    t.setStyle(TableStyle(estilos))
    st.append(t)
    r = lote["rotacion"]
    st.append(Spacer(1, 10))
    st.append(Paragraph("Rotación de maní", h2))
    st.append(Paragraph(
        f"Último maní: <b>{r['ultimo_mani'] or 'sin registro'}</b> · campañas desde el último maní: "
        f"<b>{fmt(r['campanias_desde_mani'])}</b> · veces con maní en las últimas 5 campañas: "
        f"<b>{r['veces_mani_ultimas_5']}</b> · campañas con dato de maní: "
        f"<b>{r.get('campanias_con_dato_ultimas_5', '—')}/{r.get('campanias_ventana', '—')}</b>. El criterio del score (v{lote['score']['version']}) pide al menos "
        f"{r.get('anios_recomendados', config.ROTACION_ANIOS_RECOMENDADOS)} campañas sin maní para puntaje completo, "
        "porque repetir maní aumenta el riesgo de carbón (<i>Thecaphora frezii</i>).", body))
    rot_comp = next((c for c in s["componentes"] if c["clave"] == "rotacion_mani"), None)
    if rot_comp is not None and rot_comp["valor"] is None:
        st.append(Paragraph("<b>Rotación no evaluada:</b> no hay dato de maní suficiente en las campañas recientes; "
                            "el riesgo de carbón queda sin determinar y el componente no entra al score.",
                            ParagraphStyle("rn", parent=body, textColor=ROJO)))
    st.append(PageBreak())

    # --- Página 3: imágenes ---
    st.append(Paragraph("Imágenes del lote", h2))
    im = lote["imagenes"]
    tabla_img = Table([[Image(str(carpeta / im["ndvi_ultima"]), width=8.3 * cm, height=8.3 * cm),
                        Image(str(carpeta / lote["zonas"]["png"]), width=8.3 * cm, height=8.3 * cm)]])
    st.append(tabla_img)
    st.append(Image(str(carpeta / im["rgb_ultima"]), width=8.3 * cm, height=8.3 * cm))
    z = lote["zonas"]
    st.append(Paragraph(f"Zonas: Alta {fmt(z['alta_pct'])}% · Media {fmt(z['media_pct'])}% · "
                        f"Baja {fmt(z['baja_pct'])}%", body))
    st.append(PageBreak())

    # --- Página 4: suelo, clima, agua, metodología ---
    a, su, cl = lote["agua"], lote["suelo"], lote["clima"]
    st.append(Paragraph("Riesgo hídrico, suelo y clima", h2))
    filas = [
        ["Máx. superficie anegada (confirmada)", f"{fmt(a['max_ha_anegadas'], 1)} ha ({a['fecha_max'] or 's/d'})"],
        ["Máx. marcado solo por Sentinel-1", f"{fmt(a.get('max_ha_s1_sin_confirmar'), 1)} ha ({a.get('fecha_max_s1_sin_confirmar') or 's/d'})"],
        ["Frecuencia histórica de agua", fmt(a["frecuencia_pct"], 1, " %")],
        ["Arcilla / Arena (0–5 cm)", f"{fmt(su['arcilla_pct'], 1, ' %')} / {fmt(su['arena_pct'], 1, ' %')}"],
        ["Carbono orgánico", fmt(su["carbono_org"], 1, " %")],
        ["Precipitación media anual", f"{fmt(cl['pp_anual_mm'], 0, ' mm')} ({cl['fuente']})"],
        ["Fuentes", Paragraph(f"Sentinel-2, Sentinel-1/JRC GSW, {su['fuente']}, {cl['fuente']}, cultivos: "
                    f"{', '.join(sorted({c['cultivo_fuente'] for c in lote['campanias'] if c['cultivo_fuente']})) or 's/d'}", body)],
    ]
    t = Table(filas, colWidths=[6 * cm, 11 * cm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    st.append(t)
    st.append(Spacer(1, 10))
    st.append(Paragraph("Metodología del score", h2))
    vb = s.get("vigor_base")
    ev0, ev1 = config.EVI_MAX_REF
    if vb == "evi":
        linea_vigor = (f"Vigor histórico: EVI máximo medio por campaña, lineal entre {fmt(ev0)} y {fmt(ev1)} "
                       "(referencias PROVISORIAS, sin calibrar con rendimientos; el NDVI se satura con canopeo cerrado).")
    elif vb == "combinado":
        linea_vigor = (f"Vigor histórico: {round(100 * config.VIGOR_PESO_EVI)} % EVI máximo (lineal {fmt(ev0)}–{fmt(ev1)}, "
                       "referencias PROVISORIAS) y el resto NDVI máximo (0,55–0,90).")
    else:
        linea_vigor = "Vigor histórico: NDVI máximo medio por campaña, lineal entre 0,55 y 0,90."
    for linea in [
        linea_vigor,
        "Estabilidad: 1 − coeficiente de variación del NDVI máximo entre campañas (0,02 → 1; 0,20 → 0).",
        (f"Riesgo hídrico: fracción máxima anegada y frecuencia de agua (JRC). Un píxel cuenta como anegado si "
         f"Sentinel-1 lo marca como agua Y lo confirma el óptico (MNDWI > {fmt(config.AGUA_MNDWI_UMBRAL, 0)} en Sentinel-2 limpio a ± "
         f"{config.AGUA_VENTANA_OPTICA_DIAS} días) o JRC (ocurrencia ≥ {fmt(config.AGUA_JRC_OCURRENCIA_MIN_PCT, 0)} %); "
         "sin óptico válido no se confirma. Umbrales sin calibrar."),
        f"Imágenes: Sentinel-2 con máscara Cloud Score+ (cs_cdf ≥ {fmt(config.S2_CS_UMBRAL)}) y SCL 4/5/6.",
        "Suelo: textura franco-arenosa óptima para maní y carbono orgánico.",
        "Rotación de maní: penaliza maní reciente y repetido (riesgo de carbón).",
    ]:
        st.append(Paragraph("• " + linea, body))
    if lote["advertencias"]:
        st.append(Spacer(1, 10))
        st.append(Paragraph("Advertencias", h2))
        for w in lote["advertencias"]:
            st.append(Paragraph("• " + w.replace("<", "&lt;"), body))

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm, title=f"AgroScore – {lote['nombre']}",
                            author="AgroScore", subject=f"score={'sin dato suficiente' if lote['score']['valor'] is None else lote['score']['valor']}")
    doc.build(st, onFirstPage=encabezado, onLaterPages=encabezado)
    return pdf_path
