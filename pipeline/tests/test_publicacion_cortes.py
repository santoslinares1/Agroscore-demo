"""Publicación ante cortes abruptos (kill -9, apagón): el index.json NUNCA lista un lote sin carpeta y
`publicar.recuperar()` deja todo consistente, sin perder la versión anterior ni dejar temporales.

El corte se simula en un proceso hijo (fork) que muere con os._exit (sin rollback ni finally) justo antes de la
k-ésima operación que modifica el disco (os.rename / os.replace), para TODOS los k posibles.
"""
import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path

import pytest

import run_pipeline
from agroscore import publicar
from tests.conftest import DATA

IDS = ["ejemplo_roca_norte", "ejemplo_roca_sur", "ejemplo_rio_cuarto_este"]
pytestmark = pytest.mark.skipif(not hasattr(os, "fork"), reason="requiere fork (Linux/macOS)")


@pytest.fixture(scope="module")
def salida(tmp_path_factory):
    out = tmp_path_factory.mktemp("salida_cortes") / "out"
    assert run_pipeline.main([str(DATA / "lotes.geojson"), "--ejemplo", "--out", str(out)]) == 0
    return out


def huella(carpeta: Path) -> dict:
    return {str(p.relative_to(carpeta)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(carpeta.rglob("*")) if p.is_file()}


def invariante(dest: Path) -> None:
    """Lo que el usuario ve en CUALQUIER instante: cada lote del index tiene su carpeta con lote.json."""
    ip = dest / "index.json"
    if not ip.exists():
        return
    idx = json.loads(ip.read_text())            # nunca a medio escribir (os.replace)
    publicar.validar(idx, "index.schema.json")
    faltan = [l["id"] for l in idx["lotes"] if not (dest / l["id"] / "lote.json").is_file()]
    assert not faltan, f"el index lista lotes sin carpeta: {faltan}"


def limpio(dest: Path) -> None:
    ids_idx = sorted(l["id"] for l in json.loads((dest / "index.json").read_text())["lotes"])
    assert ids_idx == publicar.ids_publicados(dest)
    assert not [p.name for p in dest.iterdir() if p.name.startswith(".")]
    meta = publicar.dir_meta(dest)
    assert not [p.name for p in meta.iterdir()
                if p.name.startswith("staging-") or p.name.endswith(".tmp") or p.name == publicar.DIARIO]


def morir_en(k: int, fn) -> int:
    """Corre fn() en un hijo que muere (os._exit, sin limpiar nada) antes de su k-ésima operación de disco."""
    pid = os.fork()
    if pid == 0:  # hijo
        cuenta = {"n": 0}
        reales = {"rename": os.rename, "replace": os.replace}

        def envolver(nombre):
            def f(*a, **kw):
                cuenta["n"] += 1
                if cuenta["n"] == k:
                    os._exit(137)
                return reales[nombre](*a, **kw)
            return f
        os.rename, os.replace = envolver("rename"), envolver("replace")
        try:
            fn()
            os._exit(0)
        except BaseException:
            os._exit(3)
    _, st = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(st)


def preparar(salida, tmp_path):
    out = tmp_path / "out"
    shutil.copytree(salida, out)
    dest = tmp_path / "demo"
    publicar.publicar_lotes([out / IDS[0], out / IDS[1]], dest)
    d = json.loads((out / IDS[0] / "lote.json").read_text())
    d["nombre"] = "NOMBRE NUEVO"
    (out / IDS[0] / "lote.json").write_text(json.dumps(d, ensure_ascii=False))
    return out, dest


def test_corte_en_cada_paso_de_un_reemplazo_mas_lote_nuevo(salida, tmp_path):
    k, completos, cortados = 1, 0, 0
    while True:
        base = tmp_path / f"k{k}"
        out, dest = preparar(salida, base)
        antes = huella(dest)
        lote_viejo = (dest / IDS[0] / "lote.json").read_bytes()
        code = morir_en(k, lambda: publicar.publicar_lotes([out / IDS[0], out / IDS[2]], dest, reemplazar=True))
        invariante(dest)                                     # aun SIN recuperar
        publicar.recuperar(dest)
        invariante(dest)
        limpio(dest)
        nombre = json.loads((dest / IDS[0] / "lote.json").read_text())["nombre"]
        if code == 0 or nombre == "NOMBRE NUEVO":            # quedó la publicación completa
            assert sorted(publicar.ids_publicados(dest)) == sorted(IDS)
            resp = list((publicar.dir_versiones(dest) / IDS[0]).iterdir())
            assert len(resp) == 1 and (resp[0] / "lote.json").read_bytes() == lote_viejo   # la anterior no se pierde
            completos += 1
        else:                                                # quedó exactamente como antes
            assert huella(dest) == antes, f"k={k}"
            cortados += 1
        if code == 0:
            break
        assert code == 137
        k += 1
    assert cortados >= 4 and completos >= 1              # se probaron todos los puntos de corte


def test_corte_en_cada_paso_de_reemplazar_todo(salida, tmp_path):
    k = 1
    while True:
        base = tmp_path / f"k{k}"
        out, dest = preparar(salida, base)
        antes = huella(dest)
        code = morir_en(k, lambda: publicar.reemplazar_todo(out, dest))
        invariante(dest)
        publicar.recuperar(dest)
        assert (dest / "index.json").exists()                # el destino nunca queda perdido
        invariante(dest)
        limpio(dest)
        ids = publicar.ids_publicados(dest)
        if ids == sorted(IDS) and json.loads((dest / IDS[0] / "lote.json").read_text())["nombre"] == "NOMBRE NUEVO":
            completo = next((publicar.dir_versiones(dest) / "_completo").iterdir())
            assert huella(completo) == antes
        else:
            assert huella(dest) == antes, f"k={k}"
        if code == 0:
            break
        k += 1
    assert k >= 3


def test_recupera_restos_de_la_version_anterior_del_publicador(salida, tmp_path):
    """Restos del publicador v1.3 tras un kill (todo dentro del destino): staging, .index.*.tmp, .versiones y un
    lote listado sin carpeta (se había movido a .versiones). recuperar() los saca de lo que se sirve y repara."""
    out, dest = preparar(salida, tmp_path)
    viejo = huella(dest / IDS[0])
    (dest / ".versiones" / IDS[0]).mkdir(parents=True)
    shutil.move(str(dest / IDS[0]), dest / ".versiones" / IDS[0] / "20261118-104419")
    (dest / ".staging-20261118-104419-1" / IDS[0]).mkdir(parents=True)
    (dest / ".index.20261118-104419.1.tmp").write_text("{}")
    (dest / ".publicar.lock").write_text("")
    acciones = publicar.recuperar(dest)
    assert huella(dest / IDS[0]) == viejo                    # volvió la última versión respaldada
    invariante(dest)
    limpio(dest)
    assert any("restauró" in a for a in acciones)


def test_index_con_lote_sin_carpeta_ni_respaldo_se_repara_quitando_la_entrada(salida, tmp_path):
    out, dest = preparar(salida, tmp_path)
    shutil.rmtree(dest / IDS[1])
    publicar.recuperar(dest)
    invariante(dest)
    assert [l["id"] for l in json.loads((dest / "index.json").read_text())["lotes"]] == [IDS[0]]
    assert list((publicar.dir_versiones(dest) / "_index").glob("*-reparado.json"))   # el index previo se conserva


def test_destino_sano_no_se_toca(salida, tmp_path):
    out, dest = preparar(salida, tmp_path)
    antes = huella(dest)
    assert publicar.recuperar(dest) == []
    assert huella(dest) == antes


def test_reemplazar_todo_respeta_el_lock(salida, tmp_path):
    out, dest = preparar(salida, tmp_path)
    hecho = threading.Event()
    with publicar._lock(dest):
        t = threading.Thread(target=lambda: (publicar.reemplazar_todo(out, dest), hecho.set()))
        t.start()
        time.sleep(0.6)
        assert not hecho.is_set(), "reemplazar_todo no esperó el lock"
    t.join(10)
    assert hecho.is_set()
    limpio(dest)


def test_metadatos_fuera_de_lo_que_se_sirve(tmp_path, monkeypatch):
    web_demo = tmp_path / "proy" / "web" / "public" / "demo"
    assert publicar.dir_meta(web_demo) == tmp_path / "proy" / ".publicacion" / "demo"
    assert publicar.dir_meta(tmp_path / "x" / "demo") == tmp_path / "x" / ".publicacion-demo"
    monkeypatch.setenv(publicar.ENV_META, str(tmp_path / "meta"))
    assert publicar.dir_meta(web_demo) == tmp_path / "meta" / "demo"


def test_servidor_no_publica_en_dist():
    import server
    ds = server.destinos_web(None)
    assert ds == [server.RAIZ / "web" / "public" / "demo"]
    assert all("dist" not in d.parts for d in ds)
    # y sus metadatos (versiones, lock) quedan fuera de web/
    assert "web" not in publicar.dir_meta(ds[0]).relative_to(server.RAIZ).parts
