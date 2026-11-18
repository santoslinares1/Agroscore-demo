import {
  BarController, BarElement, CategoryScale, Chart, Legend, LinearScale, LineController, LineElement, PointElement, Tooltip,
} from "chart.js";
import type { Lote } from "./types";
import { cultivoNombre } from "./fmt";

Chart.register(BarController, BarElement, CategoryScale, LinearScale, LineController, LineElement, PointElement, Tooltip, Legend);

export const DORADO = "#c9a227";

export function graficoNDVI(canvas: HTMLCanvasElement, l: Lote) {
  const c = l.campanias;
  return new Chart(canvas, {
    data: {
      labels: c.map((x) => x.campania),
      datasets: [
        { type: "bar", label: "NDVI máx.", data: c.map((x) => x.ndvi_max),
          backgroundColor: c.map((x) => (x.cultivo === "mani" ? DORADO : "#2e7d32")), order: 2 },
        { type: "line", label: "NDVI medio", data: c.map((x) => x.ndvi_medio), borderColor: "#1b3a57",
          backgroundColor: "#1b3a57", tension: 0.2, order: 1 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: { y: { min: 0, max: 1, title: { display: true, text: "NDVI" } } },
      plugins: {
        legend: { position: "bottom" },
        tooltip: { callbacks: { afterTitle: (it) => `Cultivo: ${cultivoNombre(c[it[0].dataIndex].cultivo)}` } },
      },
    },
  });
}
