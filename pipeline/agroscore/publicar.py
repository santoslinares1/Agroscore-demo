"""Publica la salida de uno o más lotes en la carpeta de datos de la web (web/public/demo). NO DESTRUCTIVO.

Reglas (v1.4):
- **No pisa**: si el id ya existe (carpeta o entrada en index.json) se rechaza con `IdExistenteError`,
  salvo `reemplazar=True`. Aun con reemplazo, la versión anterior NO se borra: se mueve a
  `<meta>/versiones/<id>/<AAAAmmdd-HHMMSS>/` (y el index.json anterior a `<meta>/versiones/_index/`).
- **Fuera de lo que se sirve**: versiones, lock, staging, temporales y diario viven en un directorio de
  metadatos (`dir_meta`) que NO está dentro del destino. Para `web/public/demo` es `<raíz>/.publicacion/demo/`,
  así que nunca terminan en `dist/` ni los sirve el server de desarrollo. El destino solo tiene index.json y
  las carpetas de los lotes.
- **Validado antes de tocar nada**: todo se arma en staging (mismo filesystem), se valida lo COPIADO (lote.json y el
  index.json nuevo) y recién entonces se hace el swap.
- **Invariante ante cortes (kill, apagón)**: el index.json NUNCA lista un lote cuya carpeta no existe. Orden:
  1) diario (`diario.json`) con lo que se va a hacer; 2) si hay reemplazos, index intermedio SIN los ids que se
  reemplazan; 3) mover la versión vigente a versiones y la nueva a su lugar; 4) index final (os.replace);
  5) borrar el diario. Si el proceso muere en el medio, `recuperar()` (que corre solo, bajo lock, al empezar cada
  publicación, al arrancar el server y con `copiar_salidas.py --recuperar`) deshace lo incompleto usando el diario,
  limpia staging/temporales huérfanos y repara el index (restaura la última versión respaldada o saca la entrada).
- Varios lotes a la vez = todo o nada. Un lock de archivo (`<meta>/publicar.lock`) serializa a todos los
  procesos que publican en el mismo destino (incluido `reemplazar_todo`).
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from . import config
from .pipeline import TZ_AR, validar

log = logging.getLogger("agroscore.publicar")

ARCHIVOS = ("lote.json", "resumen.md", "informe.pdf", "zonas.png", "overlay_rgb.png", "overlay_ndvi.png",
            "overlay_ndmi.png", "overlay_zonas.png", "ndvi_campanias.png")
VERSIONES = "versiones"
DIARIO = "diario.json"
LOCK = "publicar.lock"
ENV_META = "AGROSCORE_PUBLICACION_DIR"


class PublicacionError(Exception):
    """La publicación no se hizo (validación, archivos faltantes…). El destino quedó intacto."""


class IdExistenteError(PublicacionError):
    """El id ya está publicado y no se pidió reemplazar."""

    def __init__(self, ids: list[str]):
        self.ids = ids
        super().__init__(f"Ya existe un lote publicado con id {', '.join(ids)}; no se pisa. "
                         "Pedí el reemplazo explícito (la versión anterior se respalda en .publicacion/<destino>/versiones/).")


# --- dónde viven los metadatos (fuera de lo que se sirve) ---------------------------------------------------

def dir_meta(destino: Path) -> Path:
    """Directorio de metadatos de publicación de `destino` (versiones, lock, staging, diario).

    - `AGROSCORE_PUBLICACION_DIR` (si está): `<ese dir>/<nombre del destino>`.
    - destino dentro de una carpeta `public/` (p. ej. web/public/demo): `<padre de web>/.publicacion/<nombre>`
      (fuera de web/: ni el build ni el server de desarrollo lo sirven).
    - cualquier otro destino: `<padre>/.publicacion-<nombre>` (hermano, mismo filesystem).
    """
    destino = Path(destino).absolute()
    env = os.environ.get(ENV_META)
    if env:
        return Path(env).absolute() / destino.name
    if destino.parent.name == "public":
        return destino.parent.parent.parent / ".publicacion" / destino.name
    return destino.parent / f".publicacion-{destino.name}"


def dir_versiones(destino: Path) -> Path:
    return dir_meta(destino) / VERSIONES


def _ts(ahora: datetime | None = None) -> str:
    return (ahora or datetime.now(TZ_AR)).strftime("%Y%m%d-%H%M%S")


def entrada_index(doc: dict) -> dict:
    return {"id": doc["id"], "nombre": doc["nombre"], "localidad": doc["localidad"], "area_ha": doc["area_ha"],
            "score": doc["score"]["valor"], "centroide": doc["centroide"], "geometry": doc["geometry"],
            "ejemplo": doc["ejemplo"]}


def _nombre_ok(n: str) -> bool:
    return bool(n) and "/" not in n and "\\" not in n and n not in (".", "..") and not n.startswith(".")


def archivos_de(doc: dict) -> list[str]:
    """Archivos que forman un lote publicado: los fijos + los que lote.json referencia."""
    pngs = [v for v in doc["imagenes"].values() if isinstance(v, str) and v.lower().endswith(".png")]
    refs = list(ARCHIVOS) + pngs + [doc["pdf"], doc["resumen_md"], doc["zonas"]["png"]]
    vistos: list[str] = []
    for f in refs:
        if not isinstance(f, str) or not _nombre_ok(f):
            raise PublicacionError(f"lote.json referencia un nombre de archivo no válido: {f!r}")
        if f not in vistos:
            vistos.append(f)
    return vistos


def leer_lote(src: Path) -> dict:
    p = Path(src) / "lote.json"
    if not p.exists():
        raise PublicacionError(f"No existe {p}")
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        validar(doc, "lote.schema.json")
    except Exception as exc:  # JSON roto o schema inválido
        raise PublicacionError(f"{p} no valida contra el schema: {str(exc).splitlines()[0][:300]}") from exc
    return doc


def _validar_json(p: Path, schema: str) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        validar(d, schema)
        return d
    except Exception as exc:
        raise PublicacionError(f"{p.name} no valida contra {schema}: {str(exc).splitlines()[0][:300]}") from exc


def existentes(destino: Path, ids: list[str]) -> list[str]:
    """Ids ya publicados en `destino` (carpeta con lote.json o entrada en index.json)."""
    destino = Path(destino)
    en_index: set[str] = set()
    ip = destino / "index.json"
    if ip.exists():
        with contextlib.suppress(Exception):
            en_index = {l["id"] for l in json.loads(ip.read_text(encoding="utf-8")).get("lotes", [])}
    return [i for i in ids if i in en_index or (destino / i).exists()]


def existe(id_: str, destinos: list[Path]) -> bool:
    return any(existentes(d, [id_]) for d in destinos)


def ids_publicados(destino: Path) -> list[str]:
    destino = Path(destino)
    return sorted(p.name for p in destino.iterdir() if p.is_dir() and not p.name.startswith(".")) if destino.exists() else []


@contextlib.contextmanager
def _lock(destino: Path):
    """Lock exclusivo por destino. Vive en el dir de metadatos (no dentro del destino: sobrevive a reemplazar_todo)."""
    meta = dir_meta(destino)
    meta.mkdir(parents=True, exist_ok=True)
    with open(meta / LOCK, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield meta
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _mover(a: Path, b: Path) -> None:
    b.parent.mkdir(parents=True, exist_ok=True)
    os.rename(a, b)


def _unico(p: Path) -> Path:
    q, n = p, 1
    while q.exists():
        q, n = p.with_name(f"{p.name}-{n}"), n + 1
    return q


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _escribir_atomico(p: Path, texto: str, tmp_dir: Path) -> None:
    """Escribe `p` sin dejarlo nunca a medias: archivo temporal (en el dir de metadatos) + fsync + os.replace."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{p.name}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(texto)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _index_nuevo(destino: Path, docs: list[dict]) -> dict:
    ip = destino / "index.json"
    if ip.exists():
        try:
            idx = json.loads(ip.read_text(encoding="utf-8"))
            idx["lotes"]
        except Exception as exc:
            raise PublicacionError(f"El index.json actual de {destino} está dañado ({exc}); no se toca nada.") from exc
    else:
        idx = {"score_version": config.SCORE_VERSION, "lotes": []}
    nuevos = {d["id"]: entrada_index(d) for d in docs}
    lotes = [nuevos.pop(l["id"]) if l["id"] in nuevos else l for l in idx["lotes"]]
    lotes += list(nuevos.values())
    idx.update(lotes=lotes, generado=datetime.now(TZ_AR).isoformat(timespec="seconds"),
               score_version=config.SCORE_VERSION, ejemplo=any(l["ejemplo"] for l in lotes))
    validar(idx, "index.schema.json")
    return idx


# --- recuperación tras un corte ----------------------------------------------------------------------------

def _deshacer(destino: Path, meta: Path, d: dict) -> str:
    """Deja el destino como antes de la operación del diario `d` (o la da por terminada si ya se completó)."""
    stg = Path(d["staging"])
    if d["tipo"] == "todo":
        anterior = Path(d["anterior"])
        if not destino.exists() and anterior.exists():
            os.rename(anterior, destino)            # se cortó entre mover el viejo y poner el nuevo
            res = "reemplazo total incompleto: se restauró el destino anterior"
        elif destino.exists() and not stg.exists():
            res = "reemplazo total ya completo"
        else:
            res = "reemplazo total no había empezado"
        shutil.rmtree(stg, ignore_errors=True)       # staging propio y temporal (nunca datos publicados)
        return res
    ip = destino / "index.json"
    if ip.exists() and _sha(ip.read_text(encoding="utf-8")) == d["index_final_sha"]:
        shutil.rmtree(stg, ignore_errors=True)
        return "publicación ya completa (solo faltaba limpiar)"
    descarte = _unico(meta / VERSIONES / "_incompleto" / d["ts"])
    for e in reversed(d["entradas"]):
        final = destino / e["id"]
        resp = Path(e["respaldo"]) if e.get("respaldo") else None
        if resp is not None and resp.exists():
            if final.exists():
                _mover(final, descarte / e["id"])     # la versión nueva, a medio publicar
            os.rename(resp, final)                    # vuelve la vigente
        elif e.get("nuevo") and final.exists() and not (stg / e["id"]).exists():
            _mover(final, descarte / e["id"])
    previo = Path(d["index_previo"]) if d.get("index_previo") else None
    if previo is not None and previo.exists():
        texto = previo.read_text(encoding="utf-8")
        if not ip.exists() or ip.read_text(encoding="utf-8") != texto:
            _escribir_atomico(ip, texto, meta)
    elif not d.get("habia_index") and ip.exists():
        _mover(ip, descarte / "index.json")
    shutil.rmtree(stg, ignore_errors=True)
    return "publicación incompleta deshecha (lo nuevo quedó en versiones/_incompleto)"


def _ultima_version(meta: Path, id_: str) -> Path | None:
    d = meta / VERSIONES / id_
    snaps = sorted((p for p in d.iterdir() if (p / "lote.json").is_file()), key=lambda p: p.name) if d.is_dir() else []
    return snaps[-1] if snaps else None


def _migrar_legado(destino: Path, meta: Path, ts: str, acciones: list[str]) -> None:
    """Restos de la publicación v1.3 (todo dentro del destino) -> dir de metadatos."""
    if destino.exists():
        for p in destino.iterdir():
            if p.name.startswith(".staging-") and p.is_dir():
                shutil.rmtree(p, ignore_errors=True)  # staging temporal huérfano (copias del origen)
                acciones.append(f"borrado staging huérfano {p.name}")
            elif p.name.startswith(".index.") and p.name.endswith(".tmp"):
                p.unlink(missing_ok=True)
                acciones.append(f"borrado temporal huérfano {p.name}")
            elif p.name == ".publicar.lock":
                p.unlink(missing_ok=True)
        viejas = destino / ".versiones"
        if viejas.is_dir():
            for grupo in viejas.iterdir():
                for snap in (grupo.iterdir() if grupo.is_dir() else []):
                    _mover(snap, _unico(meta / VERSIONES / grupo.name / snap.name))
                with contextlib.suppress(OSError):
                    grupo.rmdir()
            with contextlib.suppress(OSError):
                viejas.rmdir()
            acciones.append("versiones viejas movidas fuera del destino")
    padre = destino.parent
    if padre.exists():
        for p in sorted(padre.iterdir()):
            if not p.name.startswith(f".staging-{destino.name}-"):
                continue
            if "-anterior-" in p.name:   # destino completo previo de un reemplazar_todo cortado: NUNCA se borra
                if not destino.exists():
                    os.rename(p, destino)
                    acciones.append(f"restaurado el destino completo desde {p.name}")
                else:
                    _mover(p, _unico(meta / VERSIONES / "_completo" / f"legado-{ts}"))
                    acciones.append(f"{p.name} movido a versiones/_completo")
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                acciones.append(f"borrado staging huérfano {p.name}")


def _recuperar(destino: Path, meta: Path) -> list[str]:
    acciones: list[str] = []
    ts = _ts()
    diario = meta / DIARIO
    if diario.exists():
        try:
            d = json.loads(diario.read_text(encoding="utf-8"))
            acciones.append(_deshacer(destino, meta, d))
        except Exception as exc:  # noqa: BLE001  diario ilegible: se conserva para revisarlo a mano
            _mover(diario, _unico(meta / f"diario-ilegible-{ts}.json"))
            acciones.append(f"diario ilegible apartado ({exc})")
        diario.unlink(missing_ok=True)
    for p in meta.iterdir() if meta.exists() else []:   # bajo lock: todo staging/temporal es huérfano
        if p.name.startswith("staging-") and p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            acciones.append(f"borrado staging huérfano {p.name}")
        elif p.name.endswith(".tmp"):
            p.unlink(missing_ok=True)
            acciones.append(f"borrado temporal huérfano {p.name}")
    _migrar_legado(destino, meta, ts, acciones)
    # consistencia: ninguna entrada del index sin su carpeta
    ip = destino / "index.json"
    if ip.exists():
        try:
            idx = json.loads(ip.read_text(encoding="utf-8"))
            lotes = idx["lotes"]
        except Exception:  # noqa: BLE001  index dañado: no se toca (publicar falla con mensaje claro)
            return acciones
        quitar = []
        for l in lotes:
            final = destino / l["id"]
            if (final / "lote.json").is_file():
                continue
            snap = None if final.exists() else _ultima_version(meta, l["id"])
            if snap is not None:
                os.rename(snap, final)
                acciones.append(f"{l['id']}: faltaba la carpeta; se restauró la última versión respaldada ({snap.name})")
            else:
                quitar.append(l["id"])
        if quitar:
            bk = _unico(meta / VERSIONES / "_index" / f"{ts}-reparado.json")
            bk.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ip, bk)
            idx["lotes"] = [l for l in lotes if l["id"] not in quitar]
            idx["ejemplo"] = any(l.get("ejemplo") for l in idx["lotes"])
            _escribir_atomico(ip, _json(idx), meta)
            acciones.append(f"index reparado: se quitaron {quitar} (sin carpeta ni respaldo); index previo en {bk.name}")
    for a in acciones:
        log.warning("Recuperación de %s: %s", destino, a)
    return acciones


def recuperar(destino: Path) -> list[str]:
    """Repara `destino` tras un corte abrupto (toma el lock). Devuelve las acciones hechas (vacío = estaba sano)."""
    destino = Path(destino)
    if not destino.parent.exists():
        return []
    with _lock(destino) as meta:
        return _recuperar(destino, meta)


# --- publicar -----------------------------------------------------------------------------------------------

def _rollback(destino: Path, meta: Path, diario: dict) -> None:
    """Deshace en caliente; si el rollback mismo falla, el diario queda para la próxima recuperación."""
    try:
        _deshacer(destino, meta, diario)
        (meta / DIARIO).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        log.exception("Rollback incompleto en %s: se reintenta en la próxima recuperación (diario conservado)", destino)


def _escribir_diario(meta: Path, d: dict) -> None:
    _escribir_atomico(meta / DIARIO, _json(d), meta)


def publicar_lotes(carpetas: list[Path], destino: Path, reemplazar: bool = False,
                   ahora: datetime | None = None) -> list[dict]:
    """Publica varias carpetas `<out>/<id>` en `destino` (todo o nada). Devuelve los lote.json publicados."""
    destino = Path(destino)
    carpetas = [Path(c) for c in carpetas]
    docs = [leer_lote(c) for c in carpetas]
    ids = [d["id"] for d in docs]
    if len(set(ids)) != len(ids):
        raise PublicacionError(f"Ids repetidos en la misma publicación: {sorted({i for i in ids if ids.count(i) > 1})}")
    for c, d in zip(carpetas, docs, strict=True):
        if c.name != d["id"]:
            raise PublicacionError(f"La carpeta {c.name!r} no coincide con el id {d['id']!r} de su lote.json")
    ts = _ts(ahora)
    with _lock(destino) as meta:
        _recuperar(destino, meta)
        repetidos = existentes(destino, ids)
        if repetidos and not reemplazar:
            raise IdExistenteError(repetidos)
        stg = _unico(meta / f"staging-{ts}-{os.getpid()}")
        stg.mkdir(parents=True)
        try:
            # 1) armar en staging y validar lo COPIADO (no solo el origen)
            for c, d in zip(carpetas, docs, strict=True):
                (stg / d["id"]).mkdir()
                for f in archivos_de(d):
                    if not (c / f).is_file():
                        raise PublicacionError(f"{d['id']}: falta {f} (lo referencia lote.json o es parte del lote)")
                    shutil.copy2(c / f, stg / d["id"] / f)
                _validar_json(stg / d["id"] / "lote.json", "lote.schema.json")
            # 2) index final, validado y releído desde disco
            destino.mkdir(parents=True, exist_ok=True)
            idx_final = _json(_index_nuevo(destino, docs))
            (stg / "index.json").write_text(idx_final, encoding="utf-8")
            _validar_json(stg / "index.json", "index.schema.json")
        except BaseException:
            shutil.rmtree(stg, ignore_errors=True)   # staging propio y temporal (nunca datos publicados)
            raise
        # 3) diario + swap. Desde acá cualquier corte se deshace con el diario.
        ip = destino / "index.json"
        idx_previo = None
        if ip.exists():
            idx_previo = _unico(meta / VERSIONES / "_index" / f"{ts}.json")
            idx_previo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ip, idx_previo)
        entradas = []
        for d in docs:
            final = destino / d["id"]
            resp = _unico(meta / VERSIONES / d["id"] / ts) if final.exists() else None
            entradas.append({"id": d["id"], "respaldo": str(resp) if resp else None, "nuevo": resp is None})
        diario = {"tipo": "lotes", "ts": ts, "destino": str(destino), "staging": str(stg), "entradas": entradas,
                  "index_previo": str(idx_previo) if idx_previo else None, "habia_index": ip.exists(),
                  "index_final_sha": _sha(idx_final)}
        try:
            _escribir_diario(meta, diario)
            reemplazados = [e["id"] for e in entradas if e["respaldo"]]
            if reemplazados and ip.exists():   # index intermedio: los ids que se reemplazan dejan de listarse
                idx = json.loads(ip.read_text(encoding="utf-8"))
                idx["lotes"] = [l for l in idx["lotes"] if l["id"] not in reemplazados]
                idx["ejemplo"] = any(l.get("ejemplo") for l in idx["lotes"])
                _escribir_atomico(ip, _json(idx), meta)
            for e in entradas:
                final = destino / e["id"]
                if e["respaldo"]:
                    _mover(final, Path(e["respaldo"]))
                os.rename(stg / e["id"], final)
            _escribir_atomico(ip, idx_final, meta)
        except BaseException:
            _rollback(destino, meta, diario)
            raise
        (meta / DIARIO).unlink(missing_ok=True)
        shutil.rmtree(stg, ignore_errors=True)
    return docs


def reemplazar_todo(origen: Path, destino: Path, ahora: datetime | None = None) -> list[dict]:
    """El destino pasa a contener SOLO los lotes de `origen`. Lo anterior no se borra: queda completo en
    `<meta>/versiones/_completo/<ts>/`. Toma el mismo lock que publicar_lotes."""
    origen, destino = Path(origen), Path(destino)
    idx_o = _validar_json(origen / "index.json", "index.schema.json") if (origen / "index.json").exists() else None
    if idx_o is None:
        raise PublicacionError(f"No existe {origen / 'index.json'}")
    carpetas = [origen / l["id"] for l in idx_o["lotes"]]
    docs = [leer_lote(c) for c in carpetas]
    ts = _ts(ahora)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with _lock(destino) as meta:
        _recuperar(destino, meta)
        stg = _unico(meta / f"staging-todo-{ts}-{os.getpid()}")
        stg.mkdir(parents=True)
        try:
            for c, d in zip(carpetas, docs, strict=True):
                if c.name != d["id"]:
                    raise PublicacionError(f"La carpeta {c.name!r} no coincide con el id {d['id']!r} de su lote.json")
                (stg / d["id"]).mkdir()
                for f in archivos_de(d):
                    if not (c / f).is_file():
                        raise PublicacionError(f"{d['id']}: falta {f}")
                    shutil.copy2(c / f, stg / d["id"] / f)
                _validar_json(stg / d["id"] / "lote.json", "lote.schema.json")
            shutil.copy2(origen / "index.json", stg / "index.json")
            _validar_json(stg / "index.json", "index.schema.json")
            ids_idx = sorted(l["id"] for l in json.loads((stg / "index.json").read_text(encoding="utf-8"))["lotes"])
            if ids_idx != sorted(d["id"] for d in docs):
                raise PublicacionError("index.json de origen inconsistente con sus lotes")
        except BaseException:
            shutil.rmtree(stg, ignore_errors=True)
            raise
        anterior = _unico(meta / VERSIONES / "_completo" / ts)
        diario = {"tipo": "todo", "ts": ts, "destino": str(destino), "staging": str(stg), "anterior": str(anterior)}
        try:
            _escribir_diario(meta, diario)
            if destino.exists():
                _mover(destino, anterior)        # sin index no se lista nada: el invariante se cumple
            os.rename(stg, destino)
        except BaseException:
            _rollback(destino, meta, diario)
            raise
        (meta / DIARIO).unlink(missing_ok=True)
    return docs


# --- API previa (compatibilidad) -------------------------------------------------------------------------

def agregar_a_index(destino: Path, docs: list[dict]) -> dict:
    """Agrega/actualiza entradas en index.json (validado, escritura atómica). No toca carpetas de lotes.
    Rechaza entradas cuya carpeta no existe (el index nunca lista un lote inexistente)."""
    destino = Path(destino)
    faltan = [d["id"] for d in docs if not (destino / d["id"] / "lote.json").is_file()]
    if faltan:
        raise PublicacionError(f"No se agrega al index: no existe la carpeta de {faltan}")
    with _lock(destino) as meta:
        idx = _index_nuevo(destino, docs)
        texto = _json(idx)
        tmp = meta / f"index.{os.getpid()}.check.tmp"
        tmp.write_text(texto, encoding="utf-8")
        try:
            _validar_json(tmp, "index.schema.json")
        finally:
            tmp.unlink(missing_ok=True)
        _escribir_atomico(destino / "index.json", texto, meta)
    return idx


def publicar(carpeta_lote: Path, destinos: list[Path], reemplazar: bool = False) -> dict:
    """carpeta_lote = <out>/<id> (con lote.json). Publica en cada destino (creable).
    Con id existente: IdExistenteError salvo `reemplazar=True` (y en ese caso respalda lo anterior)."""
    carpeta_lote = Path(carpeta_lote)
    destinos = [Path(d) for d in destinos]
    doc = leer_lote(carpeta_lote)
    if not reemplazar:  # chequeo previo en TODOS los destinos: si uno ya lo tiene, no se escribe en ninguno
        for d in destinos:
            rep = existentes(d, [doc["id"]])
            if rep:
                raise IdExistenteError(rep)
    for d in destinos:
        publicar_lotes([carpeta_lote], d, reemplazar=reemplazar)
    return doc
