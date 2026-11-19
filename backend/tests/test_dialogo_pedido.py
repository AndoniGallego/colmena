import asyncio

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, SID
from orquestador.dialogos import RespuestaBody
from orquestador.traspaso import TraspasoError
from permisos_support import FakeConexion, pr
from test_dialogo_answer import PANE, Scripted, body, post


@pytest.fixture
def herd(projects):
    return Scripted(projects)


@pytest.fixture
def app(cfg, tmp_path, herd, handoffs):
    from orquestador.app import create_app
    from orquestador.board import BoardHub
    from orquestador.digest import DigestService
    from orquestador.state import StateStore

    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(herd, digests)
    hub.self_pane_id = "w2:p9"

    async def no_sleep(_):
        return None

    return create_app(
        cfg,
        b"secret",
        StateStore(tmp_path),
        hub=hub,
        digests=digests,
        dist=tmp_path / "nodist",
        handoffs_dir=handoffs,
        uploads_dir=tmp_path / "uploads",
        dialog_sleep=no_sleep,
        enchufe=herd,
    )


@pytest.fixture
def cliente(app, cfg):
    cfg.permisos = {"desde_app": True}
    with TestClient(
        app,
        base_url="https://testserver",
        headers=ORIGIN,
        client=("127.0.0.1", 5000),
    ) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


@pytest.fixture
def pedido(cliente, app, cfg):
    def _pedido(msg=None):
        cfg.permisos = {"desde_app": True}
        app.state.permisos.realpath = lambda p: p
        cliente.get("/api/board")
        m = msg or pr()
        c = FakeConexion()
        p = cliente.portal.call(app.state.permisos.atender, m, PANE, c)
        return p, c

    return _pedido


def test_pedido_abierto_no_ofrece_tarjeta_ni_teclas(cliente, herd, pedido):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    hu = cliente.get(f"/api/sessions/{SID}/dialog").json()["huella"]
    pedido(pr())
    r = cliente.get(f"/api/sessions/{SID}/dialog")
    assert r.json()["tipo"] == "pedido"
    res = post(cliente, hu)
    assert res.status_code == 409 and herd.calls_of("teclas") == []


def test_pedido_resuelto_vuelve_al_camino_de_hoy(cliente, herd, pedido, app):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    p, _ = pedido(pr())
    cliente.portal.call(app.state.permisos.resolver_en_terminal, p, "vencido")
    assert cliente.get(f"/api/sessions/{SID}/dialog").json()["tipo"] == "permiso"


def test_pedido_de_otra_sesion_no_inhibe(cliente, herd, pedido):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    pedido(pr(sid="otra-sesion-0000"))
    assert cliente.get(f"/api/sessions/{SID}/dialog").json()["tipo"] == "permiso"


def test_lock_compartido_sin_deadlock(app, cliente, herd, pedido):
    """Mientras decidir responde (bloqueado en Event), answer espera el mismo lock; al soltar, termina sin deadlock."""
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    payload = body(cliente, cliente.get(f"/api/sessions/{SID}/dialog").json()["huella"])

    async def esc():
        soltar = asyncio.Event()
        c = FakeConexion(bloquear=soltar)
        p = await app.state.permisos.atender(pr(), PANE, c)
        t_dec = asyncio.create_task(app.state.permisos.decidir(p.id, "permitir"))
        await asyncio.sleep(0)
        assert app.state.locks.get(PANE).locked()
        t_ans = asyncio.create_task(
            app.state.dialogos.answer(RespuestaBody(**payload), "?")
        )
        await asyncio.sleep(0)
        assert not t_ans.done()
        soltar.set()
        await asyncio.wait_for(t_dec, 1)
        try:
            await asyncio.wait_for(t_ans, 1)
        except TraspasoError:
            pass
        async with asyncio.timeout(1):
            async with app.state.locks.structure:
                pass

    cliente.portal.call(esc)
