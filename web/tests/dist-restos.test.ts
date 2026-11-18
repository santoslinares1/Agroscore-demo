// M1/M2: restos ocultos o temporales de publicación nunca deben quedar en dist/.
import { describe, expect, it } from "vitest";
import { esResto } from "../vite.config";

describe("exclusión de restos en dist/", () => {
  it.each([".versiones", ".publicar.lock", ".staging-20261118-1", ".index.abc.tmp", ".DS_Store", "lote.json.tmp", "x.lock", "a~"])(
    "%s se excluye", (n) => expect(esResto(n)).toBe(true));
  it.each(["index.json", "lote.json", "informe.pdf", "assets", "ejemplo_roca_norte", "lote.geojson"])(
    "%s se mantiene", (n) => expect(esResto(n)).toBe(false));
});
