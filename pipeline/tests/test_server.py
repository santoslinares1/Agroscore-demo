"""Servidor local: endpoints HTTP reales en un puerto efímero, con Earth Engine SIMULADO (mock).

Nada de esto toca Earth Engine: el chequeo y el ejecutor se inyectan.
"""
import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import server
from agroscore import pipeline, publicar
from agroscore.ejemplo import ProveedorEjemplo
from tests.test_carga import cuadrado_txt

COORDS = [[float(a) for a in t.split(",")[:2]] for t in cuadrado_txt().split()]


def feature(id_="cargado_test_0001", coords=COORDS):
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {"id": id_, "nombre": "Lote test", "localidad": "Sin especificar", "fuente": "test"}}


@pytest.fixture
def levantar():
    servidores = []

    def _lev(chequeo, ejecutor):
        app = server.App(chequeo, ejecutor)
        srv = server.crear_servidor(app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servidores.append(srv)
        return app, f"http://127.0.0.1:{srv.server_address[1]}"
    yield _lev
    for s in servidores:
        s.shutdown()
        s.server_close()


def pedir(url, cuerpo=None, origen="http://localhost:5173"):
    data = None if cuerpo is None else json.dumps(cuerpo).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "Origin": origen})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), dict(e.headers)


def esperar(base, tid, hasta=5.0):
    t0 = time.time()
    while time.time() - t0 < hasta:
        _, t, _ = pedir(f"{base}/api/trabajos/{tid}")
        if t["estado"] in ("listo", "error"):
            return t
        time.sleep(0.05)
    raise AssertionError("el trabajo no terminó")


def test_salud_y_cors(levantar):
    _, base = levantar(lambda: (True, "mock"), lambda l, p: {})
    code, s, h = pedir(f"{base}/api/salud")
    assert code == 200 and s["ok"] and s["gee_ok"] and s["gee_detalle"] == "mock"
    assert h["Access-Control-Allow-Origin"] == "http://localhost:5173"
    _, _, h2 = pedir(f"{base}/api/salud", origen="https://malicioso.example")
    assert "Access-Control-Allow-Origin" not in h2


def test_gee_no_autenticado_devuelve_503_y_no_encola(levantar):
    llamado = []
    app, base = levantar(lambda: (False, "No se pudo inicializar Earth Engine. Corré `earthengine authenticate`"),
                         lambda l, p: llamado.append(l))
    code, s, _ = pedir(f"{base}/api/salud")
    assert code == 200 and s["gee_ok"] is False and "authenticate" in s["gee_detalle"]
    code, r, _ = pedir(f"{base}/api/lotes", {"feature": feature()})
    assert code == 503 and "Earth Engine" in r["error"] and "authenticate" in r["gee_detalle"]
    assert not app.trabajos and not llamado


def test_poligono_invalido_400(levantar):
    _, base = levantar(lambda: (True, "mock"), lambda l, p: {})
    mono = [[-63.70, -33.35], [-63.69, -33.36], [-63.69, -33.35], [-63.70, -33.36], [-63.70, -33.35]]
    code, r, _ = pedir(f"{base}/api/lotes", {"feature": feature(coords=mono)})
    assert code == 400 and "se cruza" in r["error"]
    code, r, _ = pedir(f"{base}/api/lotes", {"nada": 1})
    assert code == 400
    code, r, _ = pedir(f"{base}/api/lotes", {"feature": feature(id_="../../etc")})
    assert code == 400


def test_origen_externo_rechazado(levantar):
    _, base = levantar(lambda: (True, "mock"), lambda l, p: {})
    code, _, _ = pedir(f"{base}/api/lotes", {"feature": feature()}, origen="https://otro.example")
    assert code == 403


def test_trabajo_ok_con_progreso(levantar):
    pasos = []

    def ejecutor(lote, progreso):
        progreso(0.5, "Sentinel-2 (mock)")
        pasos.append(lote.id)
        return {"score": {"valor": 70}}
    _, base = levantar(lambda: (True, "mock"), ejecutor)
    code, t, _ = pedir(f"{base}/api/lotes", {"feature": feature()})
    assert code == 202 and t["estado"] == "en_cola" and t["lote_id"] == "cargado_test_0001"
    fin = esperar(base, t["id"])
    assert fin["estado"] == "listo" and fin["progreso"] == 1.0 and fin["error"] is None
    assert pasos == ["cargado_test_0001"]
    assert pedir(f"{base}/api/trabajos/ffffffff")[0] == 404


def test_error_del_ejecutor_se_informa_tal_cual(levantar):
    def falla(lote, progreso):
        raise RuntimeError("Earth Engine: User memory limit exceeded")
    _, base = levantar(lambda: (True, "mock"), falla)
    _, t, _ = pedir(f"{base}/api/lotes", {"feature": feature()})
    fin = esperar(base, t["id"])
    assert fin["estado"] == "error" and "User memory limit exceeded" in fin["error"]


def test_publicar_suma_al_index_sin_borrar_los_demas(tmp_path):
    """Con el proveedor de EJEMPLO (no GEE): publica un lote en una carpeta web que ya tiene otros."""
    dest = tmp_path / "demo"
    from agroscore import aoi
    # carpeta web "previa" autocontenida (no depende de web/public/demo): un lote ya publicado
    previo = aoi.lote_desde_feature(feature("cargado_pub_0001"))
    pipeline.procesar_lote(previo, ProveedorEjemplo(), tmp_path / "out_previo")
    publicar.publicar(tmp_path / "out_previo" / previo.id, [dest])
    antes = json.loads((dest / "index.json").read_text())["lotes"]
    assert [l["id"] for l in antes] == ["cargado_pub_0001"]
    lote = aoi.lote_desde_feature(feature("cargado_pub_0002"))
    pipeline.procesar_lote(lote, ProveedorEjemplo(), tmp_path / "out")
    publicar.publicar(tmp_path / "out" / lote.id, [dest])
    idx = json.loads((dest / "index.json").read_text())
    ids = [l["id"] for l in idx["lotes"]]
    assert ids == [l["id"] for l in antes] + ["cargado_pub_0002"]
    assert (dest / "cargado_pub_0002" / "lote.json").exists()
    assert (dest / "cargado_pub_0002" / "overlay_ndvi.png").exists()
    # republicar el mismo id NO pisa (v1.3); con reemplazo explícito reemplaza, sin duplicar (y respalda la anterior)
    with pytest.raises(publicar.IdExistenteError):
        publicar.publicar(tmp_path / "out" / lote.id, [dest])
    publicar.publicar(tmp_path / "out" / lote.id, [dest], reemplazar=True)
    assert len(list((publicar.dir_versiones(dest) / lote.id).iterdir())) == 1
    assert [l["id"] for l in json.loads((dest / "index.json").read_text())["lotes"]].count("cargado_pub_0002") == 1
