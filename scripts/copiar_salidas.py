#!/usr/bin/env python3
"""Copia las salidas del pipeline (pipeline/out) al front (web/public/demo). NO DESTRUCTIVO.

Uso: python scripts/copiar_salidas.py [--origen pipeline/out] [--destino web/public/demo] [modo]

Modos (por defecto: sumar sin pisar):
  (sin flag)          suma los lotes de origen a los que ya hay. Si algún id ya existe en destino: error y NO
                      se toca nada (código 2).  `--agregar` se acepta por compatibilidad (es el mismo modo).
  --reemplazar-ids    los ids que ya existen se reemplazan; la versión anterior de cada uno queda en
                      <meta>/versiones/<id>/<fecha>/ . Los demás lotes del destino no se tocan.
  --reemplazar-todo   el destino pasa a tener SOLO los lotes de origen; lo anterior queda completo en
                      <meta>/versiones/_completo/<fecha>/ .
  --recuperar         solo repara el destino tras un corte (kill/apagón) y sale. Igual se hace solo al publicar.

<meta> = directorio de metadatos FUERA de lo que se sirve: para web/public/demo es <raíz>/.publicacion/demo/
(versiones, lock, staging, diario). Ver agroscore/publicar.py.
Siempre: staging + validación (index.json y cada lote.json contra el schema) + swap con diario. Si algo no valida,
el destino queda intacto y el script sale con código != 0. El index.json nunca lista un lote cuya carpeta no exista.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "pipeline"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", default=str(RAIZ / "pipeline" / "out"))
    ap.add_argument("--destino", default=str(RAIZ / "web" / "public" / "demo"))
    ap.add_argument("--agregar", action="store_true", help="(compatibilidad) sumar sin pisar: es el modo por defecto")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--reemplazar-ids", action="store_true", help="reemplazar los ids existentes (respalda la versión previa)")
    g.add_argument("--reemplazar-todo", action="store_true", help="destino = solo los lotes de origen (respalda todo lo previo)")
    ap.add_argument("--recuperar", action="store_true", help="solo reparar el destino tras un corte y salir")
    a = ap.parse_args(argv)
    org, dst = Path(a.origen), Path(a.destino)
    if a.recuperar:
        from agroscore import publicar
        acciones = publicar.recuperar(dst)
        print("\n".join(f"  {x}" for x in acciones) or f"  {dst}: nada que reparar")
        return 0
    idx_path = org / "index.json"
    if not idx_path.exists():
        print(f"No existe {idx_path}. Corré primero el pipeline.", file=sys.stderr)
        return 1
    try:
        from agroscore import publicar
    except ImportError as exc:  # sin validar no se publica: el schema es el contrato
        print(f"No se pudo importar agroscore ({exc}); no se copia nada sin validar contra el schema.", file=sys.stderr)
        return 1
    try:
        if a.reemplazar_todo:
            docs = publicar.reemplazar_todo(org, dst)
        else:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            publicar.validar(idx, "index.schema.json")
            docs = publicar.publicar_lotes([org / l["id"] for l in idx["lotes"]], dst, reemplazar=a.reemplazar_ids)
    except publicar.IdExistenteError as exc:
        print(f"ERROR: {exc}\nNo se tocó nada. Usá --reemplazar-ids (respalda lo anterior) o cambiá el id.", file=sys.stderr)
        return 2
    except publicar.PublicacionError as exc:
        print(f"ERROR: no se publicó nada (el destino quedó intacto): {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001  JSON roto, schema de index inválido, IO…
        print(f"ERROR: no se publicó nada (el destino quedó intacto): {type(exc).__name__}: {str(exc).splitlines()[0][:300]}",
              file=sys.stderr)
        return 3
    for d in docs:
        sc = d["score"]["valor"]
        print(f"  {d['id']}: score {sc if sc is not None else 'sin dato suficiente'}{'  (EJEMPLO)' if d['ejemplo'] else ''}")
    total = len(json.loads((dst / "index.json").read_text(encoding="utf-8"))["lotes"])
    print(f"Publicado en {dst}: {len(docs)} lote(s) nuevos/actualizados, {total} en total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
