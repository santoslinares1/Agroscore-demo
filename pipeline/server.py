#!/usr/bin/env python3
"""Servidor LOCAL opcional para «Analizar ahora» desde la web (#/cargar).

    python pipeline/server.py --gee-project MI_PROYECTO      # escucha en http://127.0.0.1:8787

- GET  /api/salud            -> {ok, gee_ok, gee_detalle, version}
- POST /api/lotes  {feature} -> valida el polígono y encola el análisis con Earth Engine (202 + trabajo)
- GET  /api/trabajos/<id>    -> {id, lote_id, estado: en_cola|procesando|listo|error, paso, progreso, error}

Al terminar, publica lote.json + capas en web/public/demo (o en --destino) y actualiza index.json. NUNCA escribe en
web/dist: el build es un artefacto (con `npm run dev` el lote aparece al recargar; para `npm run preview` o un dist/
servido como estático hay que volver a correr `npm run build`). La publicación NO pisa: si el id ya existe responde 409
(salvo {"reemplazar": true} en el cuerpo; en ese caso la versión anterior se respalda en
.publicacion/<destino>/versiones/<id>/<fecha>/, FUERA de lo que se sirve). Escritura atómica con diario: al arrancar se
repara cualquier publicación cortada (ver agroscore/publicar.py).
Solo escucha en 127.0.0.1 y acepta CORS de localhost. No usa ni guarda claves: Earth Engine usa las
credenciales de `earthengine authenticate` de tu máquina. Si Earth Engine no está listo, responde 503
con el motivo (la web ofrece exportar el GeoJSON). Nunca inventa resultados.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from agroscore import aoi, config  # noqa: E402

log = logging.getLogger("agroscore.server")
RAIZ = AQUI.parent
MAX_CUERPO = 2_000_000
ORIGEN_OK = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")

Progreso = Callable[[float, str], None]
Ejecutor = Callable[..., dict]  # (lote, progreso) o (lote, progreso, reemplazar=True)


def verificar_gee(project: str | None) -> tuple[bool, str]:
    """Inicializa Earth Engine y hace una consulta mínima. Devuelve (ok, detalle)."""
    try:
        from agroscore import gee
        gee.inicializar(project)
        gee.ee().Number(1).getInfo()
        return True, f"Earth Engine inicializado{f' (proyecto {project})' if project else ''}"
    except Exception as exc:  # credenciales, red, proyecto
        causa = exc.__cause__ or exc
        return False, f"{exc} [{type(causa).__name__}: {str(causa)[:200]}]" if causa is not exc else str(exc)


def ejecutor_gee(args) -> Ejecutor:
    """Ejecutor real: ProveedorGEE + procesar_lote + publicar en la web."""
    def correr(lote: aoi.Lote, progreso: Progreso, reemplazar: bool = False) -> dict:
        from agroscore import pipeline, publicar
        from agroscore.proveedores import ProveedorGEE
        prov = ProveedorGEE(args.gee_project, args.cultivos_dir, args.idecor_asset, not args.sin_mapbiomas)
        out = Path(args.out)
        doc = pipeline.procesar_lote(lote, prov, out, config.campanias(args.desde, args.hasta), progreso=progreso)
        progreso(0.97, "Publicando en la web")
        publicar.publicar(out / lote.id, destinos_web(args.destino), reemplazar=reemplazar)
        return doc
    return correr


def destinos_web(destino: str | None) -> list[Path]:
    """Carpeta de datos que sirve la web. Solo una y nunca web/dist (artefacto de build: se regenera con npm run build)."""
    return [Path(destino)] if destino else [RAIZ / "web" / "public" / "demo"]


class App:
    """Estado del servidor (separado del transporte HTTP para poder testearlo)."""

    def __init__(self, chequeo_gee: Callable[[], tuple[bool, str]], ejecutor: Ejecutor,
                 ya_publicado: Callable[[str], bool] | None = None):
        self._chequeo = chequeo_gee
        self.ya_publicado = ya_publicado  # id -> ¿ya existe en la web? (None = no se chequea)
        self._gee: tuple[bool, str] | None = None
        self._chk_lock = threading.Lock()
        self._chk_listo = threading.Event()
        self.ejecutor = ejecutor
        self.trabajos: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analisis")  # GEE de a uno

    def _verificar(self):
        with self._chk_lock:
            self._chk_listo.clear()
            try:
                self._gee = self._chequeo()
            except Exception as exc:  # pragma: no cover
                self._gee = (False, f"{type(exc).__name__}: {exc}")
            finally:
                self._chk_listo.set()

    def gee(self, refrescar: bool = False) -> tuple[bool, str]:
        """Estado de Earth Engine (bloqueante; se cachea: inicializar EE puede tardar varios segundos)."""
        if self._gee is None or refrescar:
            self._verificar()
        return self._gee  # type: ignore[return-value]

    def salud(self, refrescar=False) -> dict:
        """No bloquea más de ~1 s: si la verificación de EE sigue en curso, responde «verificando»."""
        if (self._gee is None or refrescar) and not self._chk_lock.locked():
            self._chk_listo.clear()
            threading.Thread(target=self._verificar, daemon=True).start()
        self._chk_listo.wait(1.0)
        if self._chk_lock.locked() or self._gee is None:
            return {"ok": True, "gee_ok": False, "verificando": True, "gee_detalle": "Verificando Earth Engine…",
                    "version": config.SCORE_VERSION}
        ok, det = self._gee
        return {"ok": True, "gee_ok": ok, "verificando": False, "gee_detalle": det, "version": config.SCORE_VERSION}

    def crear(self, cuerpo: dict) -> tuple[int, dict]:
        feat = cuerpo.get("feature") if isinstance(cuerpo, dict) else None
        if not isinstance(feat, dict):
            return 400, {"error": "Falta 'feature' (un Feature GeoJSON con Polygon)."}
        try:
            lote = aoi.lote_desde_feature(feat)
        except aoi.AOIError as exc:
            return 400, {"error": f"Polígono no válido: {exc}"}
        if not re.fullmatch(r"[a-z0-9_\-]{1,80}", lote.id):
            return 400, {"error": "id inválido (solo minúsculas, números, _ y -)."}
        reemplazar = cuerpo.get("reemplazar") is True
        if self.ya_publicado and not reemplazar and self.ya_publicado(lote.id):
            return 409, {"error": f"Ya existe un lote publicado con id {lote.id}; no se pisa. Para reemplazarlo enviá "
                                  "\"reemplazar\": true (la versión anterior se respalda en .publicacion/, fuera de la web).",
                         "lote_id": lote.id, "puede_reemplazar": True}
        ok, det = self.gee()
        if not ok:
            return 503, {"error": "Earth Engine no está disponible en este servidor: no se puede analizar ahora. "
                                  "Exportá el GeoJSON y corré el pipeline, o autenticá Earth Engine "
                                  "(earthengine authenticate) y reiniciá el servidor.", "gee_detalle": det}
        tid = uuid.uuid4().hex[:12]
        t = {"id": tid, "lote_id": lote.id, "estado": "en_cola", "paso": "En cola", "progreso": 0.0, "error": None,
             "area_ha": lote.area_ha, "reemplazar": reemplazar}
        with self.lock:
            self.trabajos[tid] = t
            respuesta = dict(t)
        self.pool.submit(self._correr, tid, lote, reemplazar)
        return 202, respuesta

    def _set(self, tid: str, **kw):
        with self.lock:
            self.trabajos[tid].update(kw)

    def _correr(self, tid: str, lote: aoi.Lote, reemplazar: bool = False):
        self._set(tid, estado="procesando", paso="Iniciando Earth Engine", progreso=0.02)
        try:
            prog = lambda f, txt: self._set(tid, progreso=round(float(f), 3), paso=txt)  # noqa: E731
            doc = self.ejecutor(lote, prog, True) if reemplazar else self.ejecutor(lote, prog)
            self._set(tid, estado="listo", paso="Listo", progreso=1.0, score=(doc.get("score") or {}).get("valor"))
        except Exception as exc:
            log.error("Trabajo %s (%s) falló:\n%s", tid, lote.id, traceback.format_exc())
            self._set(tid, estado="error", paso="Error", error=f"{type(exc).__name__}: {exc}")

    def trabajo(self, tid: str) -> dict | None:
        with self.lock:
            t = self.trabajos.get(tid)
            return dict(t) if t else None


def handler_para(app: App):
    class H(BaseHTTPRequestHandler):
        server_version = "AgroScoreLocal/1"

        def log_message(self, fmt, *a):
            log.info("%s %s", self.address_string(), fmt % a)

        def _cors(self):
            o = self.headers.get("Origin")
            if o and ORIGEN_OK.match(o):
                self.send_header("Access-Control-Allow-Origin", o)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Private-Network", "true")

        def _json(self, code: int, obj: dict):
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            ruta, _, qs = self.path.partition("?")
            if ruta == "/api/salud":
                return self._json(200, app.salud("refrescar=1" in qs))
            m = re.fullmatch(r"/api/trabajos/([0-9a-f]{1,32})", ruta)
            if m:
                t = app.trabajo(m.group(1))
                return self._json(200, t) if t else self._json(404, {"error": "trabajo inexistente"})
            if ruta == "/api/trabajos":
                with app.lock:
                    return self._json(200, {"trabajos": list(app.trabajos.values())})
            self._json(404, {"error": "ruta inexistente"})

        def do_POST(self):
            if self.path.split("?")[0] != "/api/lotes":
                return self._json(404, {"error": "ruta inexistente"})
            o = self.headers.get("Origin")
            if o and not ORIGEN_OK.match(o):
                return self._json(403, {"error": "origen no permitido (solo localhost)"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._json(400, {"error": "Content-Length inválido"})
            if n <= 0 or n > MAX_CUERPO:
                return self._json(413 if n > MAX_CUERPO else 400, {"error": "cuerpo vacío o demasiado grande"})
            try:
                cuerpo = json.loads(self.rfile.read(n))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._json(400, {"error": "JSON inválido"})
            code, obj = app.crear(cuerpo)
            self._json(code, obj)
    return H


def crear_servidor(app: App, host="127.0.0.1", port=8787) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler_para(app))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--gee-project", default=None, help="proyecto de Cloud para Earth Engine (o EE_PROJECT)")
    ap.add_argument("--out", default=str(AQUI / "out_servidor"))
    ap.add_argument("--destino", default=None, help="carpeta de datos que sirve la web (default web/public/demo; nunca web/dist)")
    ap.add_argument("--cultivos-dir", default=str(AQUI / "data" / "cultivos"))
    ap.add_argument("--idecor-asset", default=None)
    ap.add_argument("--sin-mapbiomas", action="store_true")
    ap.add_argument("--desde", type=int, default=config.PRIMERA_CAMPANIA)
    ap.add_argument("--hasta", type=int, default=config.ULTIMA_CAMPANIA)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("Escuchando en %s: el servidor no tiene autenticación, usalo solo en tu máquina.", a.host)
    from agroscore import publicar
    for d in destinos_web(a.destino):   # repara publicaciones cortadas (kill/apagón) antes de aceptar trabajos
        publicar.recuperar(d)            # cada acción ya queda en el log (publicar._recuperar)
    app = App(lambda: verificar_gee(a.gee_project), ejecutor_gee(a),
              ya_publicado=lambda i: publicar.existe(i, destinos_web(a.destino)))
    srv = crear_servidor(app, a.host, a.port)

    def informar():
        ok, det = app.gee()
        log.info("Earth Engine: %s — %s", "OK" if ok else "NO DISPONIBLE", det)
    threading.Thread(target=informar, daemon=True).start()
    log.info("Servidor local en http://%s:%d  (Ctrl+C para cortar)", a.host, a.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
