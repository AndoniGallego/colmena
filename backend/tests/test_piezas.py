"""Piezas opcionales: el núcleo descubre subpaquetes con `montar(ctx)` y arranca igual sin ninguno."""
import itertools
import logging
import textwrap

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, make_snapshot
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.piezas import descubrir
from orquestador.push import PushService
from orquestador.state import StateStore

_contador = itertools.count()

DEMO = """
from fastapi import APIRouter

def montar(ctx):
    router = APIRouter()

    @router.get("/demo/ping")
    async def ping():
        return {"pong": True, "opcion": ctx.opciones.get("eco", "")}

    ctx.api.include_router(router)
    ctx.push.avisos.registrar_kind("demo")
    ctx.al_iniciar(lambda: ctx.opciones.setdefault("arranco", []).append(1))
"""


def _paquete(tmp_path, monkeypatch, piezas: dict) -> str:
    nombre = f"piezas_falsas_{next(_contador)}"
    raiz = tmp_path / "paquetes" / nombre
    raiz.mkdir(parents=True)
    (raiz / "__init__.py").write_text("")
    for pieza, codigo in piezas.items():
        (raiz / pieza).mkdir()
        (raiz / pieza / "__init__.py").write_text(textwrap.dedent(codigo))
    monkeypatch.syspath_prepend(str(tmp_path / "paquetes"))
    return nombre


def _app(tmp_path, cfg, handoffs, **kw):
    enchufe = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    digests = DigestService(cfg.projects_dir())
    push = PushService(tmp_path)
    app = create_app(cfg, b"secret", StateStore(tmp_path), enchufe=enchufe, hub=BoardHub(enchufe, digests),
                     digests=digests, dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "u",
                     push=push, **kw)
    return app, push


def _cliente(app):
    c = TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000))
    return c


def test_monta_la_pieza_descubierta(tmp_path, cfg, handoffs, monkeypatch):
    paquete = _paquete(tmp_path, monkeypatch, {"demo": DEMO})
    opciones = {"eco": "hola"}
    app, push = _app(tmp_path, cfg, handoffs, piezas_paquete=paquete, piezas_opts={"demo": opciones})
    with _cliente(app) as c:
        assert c.get("/api/demo/ping").status_code == 401
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        assert c.get("/api/demo/ping").json() == {"pong": True, "opcion": "hola"}
    assert "demo" in push.avisos.kinds
    assert opciones["arranco"] == [1]


def test_paquete_vacio_arranca_sin_piezas(tmp_path, cfg, handoffs, monkeypatch):
    paquete = _paquete(tmp_path, monkeypatch, {})
    assert descubrir(paquete) == []
    app, push = _app(tmp_path, cfg, handoffs, piezas_paquete=paquete)
    with _cliente(app) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        assert c.get("/api/demo/ping").status_code == 404
    assert "demo" not in push.avisos.kinds


def test_lista_vacia_no_monta_ni_las_descubiertas(tmp_path, cfg, handoffs, monkeypatch):
    paquete = _paquete(tmp_path, monkeypatch, {"demo": DEMO})
    app, push = _app(tmp_path, cfg, handoffs, piezas_paquete=paquete, piezas=[])
    with _cliente(app) as c:
        c.post("/api/login", json={"pin": PIN})
        assert c.get("/api/demo/ping").status_code == 404
    assert "demo" not in push.avisos.kinds


def test_pieza_rota_se_loguea_y_no_tumba_la_app(tmp_path, cfg, handoffs, monkeypatch, caplog):
    paquete = _paquete(tmp_path, monkeypatch, {"demo": DEMO, "rota": "raise RuntimeError('boom')\n",
                                               "falla": "def montar(ctx):\n    raise ValueError('mal')\n"})
    caplog.set_level(logging.WARNING)
    assert [m.__name__.rsplit(".", 1)[-1] for m in descubrir(paquete)] == ["demo", "falla"]
    app, push = _app(tmp_path, cfg, handoffs, piezas_paquete=paquete)
    with _cliente(app) as c:
        c.post("/api/login", json={"pin": PIN})
        assert c.get("/api/demo/ping").status_code == 200
    textos = " ".join(r.getMessage() for r in caplog.records)
    assert "rota" in textos and "falla" in textos


def test_subpaquete_sin_montar_se_ignora(tmp_path, monkeypatch):
    paquete = _paquete(tmp_path, monkeypatch, {"suelto": "X = 1\n"})
    assert descubrir(paquete) == []


def test_al_cerrar_corre_al_apagar(tmp_path, cfg, handoffs, monkeypatch):
    codigo = """
    def montar(ctx):
        async def cerrar():
            ctx.opciones["cerrado"] = True
        ctx.al_cerrar(cerrar)
    """
    paquete = _paquete(tmp_path, monkeypatch, {"demo": codigo})
    opciones: dict = {}
    app, _ = _app(tmp_path, cfg, handoffs, piezas_paquete=paquete, piezas_opts={"demo": opciones})
    with _cliente(app):
        assert "cerrado" not in opciones
    assert opciones["cerrado"] is True


@pytest.mark.parametrize("kind", ["Demo", "de-mo", "", "x" * 21, "demo1"])
def test_registrar_kind_valida_el_nombre(tmp_path, kind):
    with pytest.raises(ValueError):
        PushService(tmp_path).avisos.registrar_kind(kind)


def test_pieza_que_falla_a_mitad_de_montar_no_deja_nada_activo(tmp_path, cfg, handoffs, monkeypatch):
    codigo = """
    from fastapi import APIRouter

    def montar(ctx):
        router = APIRouter()

        @router.get("/media/ping")
        async def ping():
            return {"pong": True}

        ctx.api.include_router(router)
        ctx.push.avisos.registrar_kind("media")
        ctx.push.registrar_prueba("media", lambda: {})
        ctx.al_iniciar(lambda: ctx.opciones.setdefault("arranco", []).append(1))
        raise RuntimeError("a mitad de camino")
    """
    paquete = _paquete(tmp_path, monkeypatch, {"media": codigo, "demo": DEMO})
    opciones: dict = {}
    app, push = _app(tmp_path, cfg, handoffs, piezas_paquete=paquete, piezas_opts={"media": opciones})
    with _cliente(app) as c:
        c.post("/api/login", json={"pin": PIN})
        assert c.get("/api/media/ping").status_code == 404
        assert c.get("/api/demo/ping").status_code == 200
    assert "media" not in push.avisos.kinds
    assert "media" not in push.prueba_kinds()
    assert "arranco" not in opciones
    assert "demo" in push.avisos.kinds
