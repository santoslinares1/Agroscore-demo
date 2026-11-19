import {
  BarController, BarElement, CategoryScale, Chart, Legend, LinearScale, LineController, LineElement, PointElement, Tooltip,
} from "chart.js";
import type { Lote } from "./types";
import { cultivoNombre } from "./fmt";

Chart.register(BarController, BarElement, CategoryScale, LinearScale, LineController, LineElement, PointElement, Tooltip, Legend);

Chart.defaults.font.family = '"IBM Plex Sans", "Segoe UI", sans-serif';
Chart.defaults.font.size = 14;
Chart.defaults.color = "#243028";

export const DORADO = "#c9a227";

export function graficoNDVI(canvas: HTMLCanvasElement, l: Lote) {
  const c = l.campanias;
  return new Chart(canvas, {
    data: {
      labels: c.map((x) => x.campania),
      datasets: [
        { type: "bar", label: "Vigor máximo (NDVI)", data: c.map((x) => x.ndvi_max),
          backgroundColor: c.map((x) => (x.cultivo === "mani" ? DORADO : "#1f6f43")), order: 2 },
        { type: "line", label: "Vigor medio (NDVI)", data: c.map((x) => x.ndvi_medio), borderColor: "#111713",
          backgroundColor: "#111713", pointBackgroundColor: "#111713", tension: 0.2, order: 1 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        y: { min: 0, max: 1, title: { display: true, text: "Vigor (NDVI)", font: { size: 14 } }, ticks: { font: { size: 14 } } },
        x: { ticks: { font: { size: 13 }, maxRotation: 0, autoSkip: true } },
      },
      plugins: {
        legend: { position: "bottom", labels: { font: { size: 14 }, boxWidth: 14, padding: 16 } },
        tooltip: { callbacks: { afterTitle: (it) => `Cultivo: ${cultivoNombre(c[it[0].dataIndex].cultivo)}` } },
      },
    },
  });
}
