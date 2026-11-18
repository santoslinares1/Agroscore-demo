"""Publicación NO destructiva: no pisa ids existentes, respalda al reemplazar, escribe atómico y valida antes del swap."""
import hashlib
import importlib.util
import json
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path

import pytest

import run_pipeline
import server
from agroscore import publicar
from agroscore.pipeline import TZ_AR
from tests.conftest import DATA, RAIZ

SCRIPTS = RAIZ.parent / "scripts"   # monorepo; si se corre pipeline/ aislado los tests de scripts se saltean
from tests.test_server import esperar, pedir
from tests.test_server import feature as feature_server

IDS = ["ejemplo_roca_norte", "ejemplo_roca_sur", "ejemplo_rio_cuarto_este"]


@pytest.fixture(scope="module")
def salida_ejemplo(tmp_path_factory):
    """Salida del pipeline con el proveedor de EJEMPLO (sin GEE): <out>/index.json + <out>/<id>/..."""
    out = tmp_path_factory.mktemp("salida") / "out"
    assert run_pipeline.main([str(DATA / "lotes.geojson"), "--ejemplo", "--out", str(out)]) == 0
    return out


@pytest.fixture
def out(salida_ejemplo, tmp_path):
    d = tmp_path / "out"
    shutil.copytree(salida_ejemplo, d)
    return d


def huella(carpeta: Path) -> dict:
    """{ruta relativa: sha1} de TODO lo que hay (incluye ocultos), para probar que algo quedó intacto."""
    return {str(p.relative_to(carpeta)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(carpeta.rglob("*")) if p.is_file() and p.name != ".publicar.lock"}


def ids_index(dest: Path) -> list[str]:
    return [l["id"] for l in json.loads((dest / "index.json").read_text())["lotes"]]


def assert_consistente(dest: Path):
    """index.json valida y lista exactamente las carpetas de lotes (que tienen lote.json válido)."""
    idx = json.loads((dest / "index.json").read_text())
    publicar.validar(idx, "index.schema.json")
    assert sorted(ids_index(dest)) == publicar.ids_publicados(dest)
    for l in idx["lotes"]:
        doc = json.loads((dest / l["id"] / "lote.json").read_text())
        publicar.validar(doc, "lote.schema.json")
        assert l["score"] == doc["score"]["valor"]
    assert not [p for p in dest.iterdir() if p.name.startswith(".")], "quedó basura oculta en lo que se sirve"
    meta = publicar.dir_meta(dest)
    if meta.exists():
        assert not [p for p in meta.iterdir() if p.name.startswith("staging-") or p.name.endswith(".tmp")
                    or p.name == publicar.DIARIO], "quedó staging/temporal/diario"


def modificar_lote(out: Path, id_: str, **cambios) -> None:
    p = out / id_ / "lote.json"
    d = json.loads(p.read_text())
    d.update(cambios)
    p.write_text(json.dumps(d, ensure_ascii=False))


# --- publicar: id duplicado ------------------------------------------------------------------------------

def test_publica_en_destino_vacio_y_queda_consistente(out, tmp_path):
    dest = tmp_path / "demo"
    publicar.publicar(out / IDS[0], [dest])
    assert ids_index(dest) == [IDS[0]]
    assert_consistente(dest)


def test_id_duplicado_sin_flag_no_pisa(out, tmp_path):
    dest = tmp_path / "demo"
    publicar.publicar(out / IDS[0], [dest])
    antes = huella(dest)
    modificar_lote(out, IDS[0], nombre="OTRO NOMBRE QUE NO DEBE PUBLICARSE")
    with pytest.raises(publicar.IdExistenteError) as e:
        publicar.publicar(out / IDS[0], [dest])
    assert e.value.ids == [IDS[0]]
    assert huella(dest) == antes          # ni un byte cambió (lote, index, sin .versiones)
    assert not (publicar.dir_versiones(dest)).exists()
    assert_consistente(dest)


def test_id_en_index_sin_carpeta_tambien_cuenta_como_existente(out, tmp_path):
    dest = tmp_path / "demo"
    publicar.publicar(out / IDS[0], [dest])
    shutil.move(dest / IDS[0], tmp_path / "movida")
    assert publicar.existe(IDS[0], [dest])


def test_con_flag_respalda_la_version_previa_y_reemplaza(out, tmp_path):
    dest = tmp_path / "demo"
    publicar.publicar(out / IDS[0], [dest])
    viejo = (dest / IDS[0] / "lote.json").read_bytes()
    idx_viejo = (dest / "index.json").read_bytes()
    modificar_lote(out, IDS[0], nombre="Nombre nuevo")
    ahora = datetime(2026, 11, 18, 10, 30, 5, tzinfo=TZ_AR)
    publicar.publicar_lotes([out / IDS[0]], dest, reemplazar=True, ahora=ahora)
    assert json.loads((dest / IDS[0] / "lote.json").read_text())["nombre"] == "Nombre nuevo"
    resp = publicar.dir_versiones(dest) / IDS[0] / "20261118-103005"
    assert (resp / "lote.json").read_bytes() == viejo                      # la anterior se conserva íntegra
    assert (resp / "informe.pdf").exists() and (resp / "overlay_ndvi.png").exists()
    assert (publicar.dir_versiones(dest) / "_index" / "20261118-103005.json").read_bytes() == idx_viejo
    assert ids_index(dest) == [IDS[0]]                                      # sin duplicar
    assert_consistente(dest)


def test_reemplazos_sucesivos_acumulan_versiones_sin_perder_ninguna(out, tmp_path):
    dest = tmp_path / "demo"
    publicar.publicar(out / IDS[0], [dest])
    for i in (1, 2, 3):
        modificar_lote(out, IDS[0], nombre=f"v{i}")
        publicar.publicar_lotes([out / IDS[0]], dest, reemplazar=True,
                                ahora=datetime(2026, 11, 18, 10, 0, i, tzinfo=TZ_AR))
    assert len(list((publicar.dir_versiones(dest) / IDS[0]).iterdir())) == 3
    assert_consistente(dest)


def test_mismo_segundo_no_pisa_el_respaldo(out, tmp_path):
    dest = tmp_path / "demo"
    publicar.publicar(out / IDS[0], [dest])
    ahora = datetime(2026, 11, 18, 10, 0, 0, tzinfo=TZ_AR)
    for _ in range(2):
        publicar.publicar_lotes([out / IDS[0]], dest, reemplazar=True, ahora=ahora)
    assert len(list((publicar.dir_versiones(dest) / IDS[0]).iterdir())) == 2


def test_publicar_en_dos_destinos_si_uno_tiene_el_id_no_se_escribe_en_ninguno(out, tmp_path):
    a, b = tmp_path / "public_demo", tmp_path / "dist_demo"
    publicar.publicar(out / IDS[0], [b])
    publicar.publicar(out / IDS[1], [a])          # a tiene IDS[1]; b tiene IDS[0]
    ha, hb = huella(a), huella(b)
    with pytest.raises(publicar.IdExistenteError):
        publicar.publicar(out / IDS[0], [a, b])   # a no lo tiene, b sí
    assert huella(a) == ha and huella(b) == hb


# --- validación y atomicidad -----------------------------------------------------------------------------

def previo(out, tmp_path):
    dest = tmp_path / "demo"
    publicar.publicar_lotes([out / IDS[0], out / IDS[1]], dest)
    return dest


def test_lote_invalido_no_toca_el_demo(out, tmp_path):
    dest = previo(out, tmp_path)
    antes = huella(dest)
    (out / IDS[2] / "lote.json").write_text('{"id": "x"}')                # no valida contra el schema
    with pytest.raises(publicar.PublicacionError, match="schema"):
        publicar.publicar(out / IDS[2], [dest])
    assert huella(dest) == antes
    assert_consistente(dest)


def test_json_roto_no_toca_el_demo(out, tmp_path):
    dest = previo(out, tmp_path)
    antes = huella(dest)
    (out / IDS[2] / "lote.json").write_text("{esto no es json")
    with pytest.raises(publicar.PublicacionError):
        publicar.publicar(out / IDS[2], [dest])
    assert huella(dest) == antes


def test_archivo_referenciado_faltante_no_toca_el_demo(out, tmp_path):
    dest = previo(out, tmp_path)
    antes = huella(dest)
    (out / IDS[2] / "informe.pdf").unlink()
    with pytest.raises(publicar.PublicacionError, match="falta informe.pdf"):
        publicar.publicar(out / IDS[2], [dest])
    assert huella(dest) == antes


def test_nombre_de_archivo_con_ruta_se_rechaza(out, tmp_path):
    dest = previo(out, tmp_path)
    antes = huella(dest)
    d = json.loads((out / IDS[2] / "lote.json").read_text())
    d["pdf"] = "../../etc/passwd"
    (out / IDS[2] / "lote.json").write_text(json.dumps(d))
    with pytest.raises(publicar.PublicacionError):
        publicar.publicar(out / IDS[2], [dest])
    assert huella(dest) == antes


def test_validacion_fallida_al_reemplazar_deja_intacta_la_version_vigente(out, tmp_path):
    dest = previo(out, tmp_path)
    antes = huella(dest)
    (out / IDS[0] / "lote.json").write_text('{"id": "x"}')
    with pytest.raises(publicar.PublicacionError):
        publicar.publicar_lotes([out / IDS[0]], dest, reemplazar=True)
    assert huella(dest) == antes and not (publicar.dir_versiones(dest)).exists()


def test_index_actual_danado_no_se_pisa(out, tmp_path):
    dest = previo(out, tmp_path)
    (dest / "index.json").write_text("{roto")
    antes = huella(dest)
    with pytest.raises(publicar.PublicacionError, match="dañado"):
        publicar.publicar(out / IDS[2], [dest])
    assert huella(dest) == antes


def test_falla_al_escribir_el_index_hace_rollback_del_swap(out, tmp_path, monkeypatch):
    dest = previo(out, tmp_path)
    antes = huella(dest)
    modificar_lote(out, IDS[0], nombre="no debe quedar")
    real = os.replace

    def falla(src, dst, *a, **k):
        if str(dst).endswith("index.json"):
            raise OSError("disco lleno (simulado)")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(os, "replace", falla)
    with pytest.raises(OSError, match="disco lleno"):
        publicar.publicar_lotes([out / IDS[0], out / IDS[2]], dest, reemplazar=True)
    monkeypatch.undo()
    # la carpeta vigente volvió, el lote nuevo no quedó, el index sigue igual (los respaldos viven fuera del destino)
    assert huella(dest) == antes
    assert not (dest / IDS[2]).exists()
    assert_consistente(dest)


def test_varios_lotes_es_todo_o_nada(out, tmp_path):
    dest = tmp_path / "demo"
    publicar.publicar(out / IDS[0], [dest])
    antes = huella(dest)
    with pytest.raises(publicar.IdExistenteError):
        publicar.publicar_lotes([out / IDS[1], out / IDS[0]], dest)         # el 2.º ya existe
    assert huella(dest) == antes and not (dest / IDS[1]).exists()
    (out / IDS[2] / "lote.json").write_text('{"id": "x"}')
    with pytest.raises(publicar.PublicacionError):
        publicar.publicar_lotes([out / IDS[1], out / IDS[2]], dest)         # el 2.º no valida
    assert huella(dest) == antes


def test_ids_repetidos_o_carpeta_distinta_del_id(out, tmp_path):
    dest = tmp_path / "demo"
    with pytest.raises(publicar.PublicacionError, match="repetidos"):
        publicar.publicar_lotes([out / IDS[0], out / IDS[0]], dest)
    shutil.copytree(out / IDS[0], out / "otro_nombre")
    with pytest.raises(publicar.PublicacionError, match="no coincide"):
        publicar.publicar_lotes([out / "otro_nombre"], dest)
    assert not (dest / "index.json").exists()


# --- reemplazar todo -------------------------------------------------------------------------------------

def test_reemplazar_todo_conserva_lo_anterior_completo(out, tmp_path):
    dest = previo(out, tmp_path)
    antes = huella(dest)
    # origen con SOLO un lote distinto
    out2 = tmp_path / "out2"
    out2.mkdir()
    shutil.copytree(out / IDS[2], out2 / IDS[2])
    idx = json.loads((out / "index.json").read_text())
    idx["lotes"] = [l for l in idx["lotes"] if l["id"] == IDS[2]]
    (out2 / "index.json").write_text(json.dumps(idx))
    publicar.reemplazar_todo(out2, dest, ahora=datetime(2026, 11, 18, 11, 0, 0, tzinfo=TZ_AR))
    assert ids_index(dest) == [IDS[2]]
    bk = publicar.dir_versiones(dest) / "_completo" / "20261118-110000"
    assert huella(bk) == antes                                              # TODO lo previo, byte a byte
    assert_consistente(dest)


def test_reemplazar_todo_con_origen_invalido_no_toca_nada(out, tmp_path):
    dest = previo(out, tmp_path)
    antes = huella(dest)
    (out / IDS[2] / "lote.json").write_text('{"id": "x"}')
    with pytest.raises(publicar.PublicacionError):
        publicar.reemplazar_todo(out, dest)
    assert huella(dest) == antes
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".staging")]
    assert not [p for p in publicar.dir_meta(dest).iterdir() if p.name.startswith("staging-")]


# --- scripts/copiar_salidas.py ---------------------------------------------------------------------------

def cargar_script(nombre):
    if not SCRIPTS.exists():
        pytest.skip("scripts/ no está (pipeline/ aislado)")
    spec = importlib.util.spec_from_file_location(nombre, SCRIPTS / f"{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def copiar():
    return cargar_script("copiar_salidas").main


def test_script_publica_en_destino_nuevo(copiar, out, tmp_path, capsys):
    dest = tmp_path / "demo"
    assert copiar(["--origen", str(out), "--destino", str(dest)]) == 0
    assert sorted(ids_index(dest)) == sorted(IDS)
    assert_consistente(dest)
    assert "score 83" in capsys.readouterr().out


def test_script_id_existente_sale_con_2_y_no_toca_nada(copiar, out, tmp_path, capsys):
    dest = tmp_path / "demo"
    assert copiar(["--origen", str(out), "--destino", str(dest)]) == 0
    antes = huella(dest)
    assert copiar(["--origen", str(out), "--destino", str(dest)]) == 2
    assert copiar(["--origen", str(out), "--destino", str(dest), "--agregar"]) == 2   # --agregar tampoco pisa
    assert huella(dest) == antes
    assert "No se tocó nada" in capsys.readouterr().err


def test_script_reemplazar_ids_respalda(copiar, out, tmp_path):
    dest = tmp_path / "demo"
    publicar.publicar(out / IDS[0], [dest])
    extra = tmp_path / "otro_out"
    shutil.copytree(out, extra)
    publicar.publicar(out / IDS[1], [dest])
    modificar_lote(extra, IDS[1], nombre="NUEVO")
    assert copiar(["--origen", str(extra), "--destino", str(dest), "--reemplazar-ids"]) == 0
    assert json.loads((dest / IDS[1] / "lote.json").read_text())["nombre"] == "NUEVO"
    assert len(list((publicar.dir_versiones(dest) / IDS[1]).iterdir())) == 1
    assert len(list((publicar.dir_versiones(dest) / IDS[0]).iterdir())) == 1
    assert_consistente(dest)


def test_script_no_borra_lotes_reales_que_no_estan_en_origen(copiar, out, tmp_path):
    dest = tmp_path / "demo"
    real = tmp_path / "out_real"
    shutil.copytree(out / IDS[2], real / "cargado_real_0001")
    d = json.loads((real / "cargado_real_0001" / "lote.json").read_text())
    d.update(id="cargado_real_0001", ejemplo=False)
    (real / "cargado_real_0001" / "lote.json").write_text(json.dumps(d))
    publicar.publicar(real / "cargado_real_0001", [dest])
    antes = huella(dest / "cargado_real_0001")
    assert copiar(["--origen", str(out), "--destino", str(dest), "--reemplazar-ids"]) == 0
    assert huella(dest / "cargado_real_0001") == antes
    assert "cargado_real_0001" in ids_index(dest) and len(ids_index(dest)) == 4


def test_script_validacion_fallida_sale_con_3_y_deja_el_demo_intacto(copiar, out, tmp_path, capsys):
    dest = tmp_path / "demo"
    assert copiar(["--origen", str(out), "--destino", str(dest)]) == 0
    antes = huella(dest)
    (out / IDS[1] / "lote.json").write_text('{"id": "x"}')
    for modo in ([], ["--reemplazar-ids"], ["--reemplazar-todo"]):
        assert copiar(["--origen", str(out), "--destino", str(dest), *modo]) == 3, modo
        assert huella(dest) == antes, modo
    assert "intacto" in capsys.readouterr().err


def test_script_index_de_origen_invalido_sale_distinto_de_0(copiar, out, tmp_path):
    dest = tmp_path / "demo"
    (out / "index.json").write_text('{"lotes": []}')
    assert copiar(["--origen", str(out), "--destino", str(dest)]) != 0
    assert not dest.exists() or not (dest / "index.json").exists()
    assert copiar(["--origen", str(tmp_path / "no_existe"), "--destino", str(dest)]) == 1


def test_script_reemplazar_todo_respalda_todo(copiar, out, tmp_path):
    dest = tmp_path / "demo"
    publicar.publicar(out / IDS[0], [dest])
    antes = huella(dest)
    assert copiar(["--origen", str(out), "--destino", str(dest), "--reemplazar-todo"]) == 0
    assert sorted(ids_index(dest)) == sorted(IDS)
    ts = next((publicar.dir_versiones(dest) / "_completo").iterdir())
    assert huella(ts) == antes
    assert_consistente(dest)


def test_scripts_no_usan_rmtree_sobre_el_demo():
    if SCRIPTS.exists():
        for f in ("copiar_salidas.py", "demo_ejemplo.sh", "copiar_salidas.sh"):
            assert "rmtree" not in (SCRIPTS / f).read_text(), f
        sh = (SCRIPTS / "demo_ejemplo.sh").read_text()
        borrados = [l for l in sh.splitlines() if "rm -r" in l]
        assert all('"$TMP"' in l for l in borrados), borrados      # solo su propia carpeta temporal (mktemp)
    # publicar.py solo borra su propio staging temporal (carpetas `.staging-*`), nunca datos publicados
    src = (RAIZ / "agroscore" / "publicar.py").read_text()
    for linea in (l for l in src.splitlines() if "rmtree" in l and "import" not in l):
        assert "stg" in linea or "ignore_errors" in linea, linea


# --- server.py: 409 y flag de reemplazo -------------------------------------------------------------------

@pytest.fixture
def levantar_pub():
    servidores = []

    def _lev(ejecutor, ya_publicado):
        app = server.App(lambda: (True, "mock"), ejecutor, ya_publicado=ya_publicado)
        srv = server.crear_servidor(app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servidores.append(srv)
        return app, f"http://127.0.0.1:{srv.server_address[1]}"
    yield _lev
    for s in servidores:
        s.shutdown()
        s.server_close()


def test_server_409_si_el_id_ya_esta_publicado(levantar_pub):
    llamadas = []
    _, base = levantar_pub(lambda lote, prog, *a: llamadas.append(a) or {"score": {"valor": 1}},
                           lambda i: i == "cargado_test_0001")
    code, r, _ = pedir(f"{base}/api/lotes", {"feature": feature_server()})
    assert code == 409 and r["puede_reemplazar"] is True and r["lote_id"] == "cargado_test_0001"
    assert "no se pisa" in r["error"]
    assert llamadas == []                                    # ni se encola el análisis (no se gasta GEE)
    code, r, _ = pedir(f"{base}/api/lotes", {"feature": feature_server(), "reemplazar": "si"})
    assert code == 409                                       # solo `true` booleano habilita el reemplazo


def test_server_con_reemplazar_true_pasa_la_bandera_al_ejecutor(levantar_pub):
    llamadas = []

    def ejecutor(lote, prog, *a):
        llamadas.append(a)
        return {"score": {"valor": 70}}
    _, base = levantar_pub(ejecutor, lambda i: True)
    code, t, _ = pedir(f"{base}/api/lotes", {"feature": feature_server(), "reemplazar": True})
    assert code == 202 and t["reemplazar"] is True
    assert esperar(base, t["id"])["estado"] == "listo" and llamadas == [(True,)]


def test_server_id_nuevo_no_pide_reemplazo(levantar_pub):
    llamadas = []

    def ejecutor(lote, prog, *a):
        llamadas.append(a)
        return {"score": {"valor": 70}}
    _, base = levantar_pub(ejecutor, lambda i: False)
    code, t, _ = pedir(f"{base}/api/lotes", {"feature": feature_server()})
    assert code == 202 and esperar(base, t["id"])["estado"] == "listo" and llamadas == [()]


def test_server_carrera_id_publicado_durante_el_analisis_falla_sin_pisar(out, tmp_path, levantar_pub):
    """Si otro proceso publicó el mismo id mientras se analizaba, el trabajo termina en error (no pisa)."""
    dest = tmp_path / "demo"

    def ejecutor(lote, prog, *a):
        publicar.publicar(out / IDS[0], [dest], reemplazar=bool(a))
        return {"score": {"valor": 1}}
    publicar.publicar(out / IDS[0], [dest])
    antes = huella(dest)
    _, base = levantar_pub(ejecutor, lambda i: False)        # el chequeo previo no lo vio (carrera)
    _, t, _ = pedir(f"{base}/api/lotes", {"feature": feature_server()})
    fin = esperar(base, t["id"])
    assert fin["estado"] == "error" and "no se pisa" in fin["error"]
    assert huella(dest) == antes
