import asyncio

import pytest

from conftest import make_snapshot
from orquestador.enchufe import FakeTerminales
from terminales_support import aplicar_snapshot


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


def test_endpoint_publico_no_acepta_directo(authed, enchufe):
    r = authed.post("/api/mensaje/execute", json={"id": "envio-0001", "pane_id": "w1:p1", "texto": "hola",
                                                  "origen": "directo"})
    assert r.status_code == 400
    assert not enchufe.calls_of("mandar_prompt")


def test_default_no_protege_ni_fija_ningun_workspace(app):
    from orquestador.config import Config

    assert Config().protected_workspaces == []
    assert app.state.hub.pinned == frozenset()


def test_super_orquestador_ya_no_esta_fijado(app, enchufe):
    snap = make_snapshot()
    snap["workspaces"][1]["label"] = "Super orquestador"
    aplicar_snapshot(enchufe, snap)
    b = run(app.state.hub.refresh(force=True))
    assert not any(w["pinned"] for w in b["workspaces"])
