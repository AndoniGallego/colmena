import asyncio

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, SID
from orquestador import auth
from orquestador.ganchos.mensaje import Ids, MensajeGancho


def enlazar_al_cambiar(permisos):
    """Devuelve (evento, restaurar). El evento se setea en cada al_cambiar del servicio."""
    cambio = asyncio.Event()
    previo = permisos.al_cambiar

    def envuelto():
        previo()
        cambio.set()

    permisos.al_cambiar = envuelto

    def restaurar():
        permisos.al_cambiar = previo

    return cambio, restaurar


async def esperar_pedido_abierto(permisos, session_id=SID, timeout=1.0):
    if permisos.abierto_para(session_id) is not None:
        return
    cambio, restaurar = enlazar_al_cambiar(permisos)
    try:
        if permisos.abierto_para(session_id) is not None:
            return
        cambio.clear()
        await asyncio.wait_for(cambio.wait(), timeout)
    finally:
        restaurar()


class FakeConexion:
    def __init__(self, ok=True, bloquear=None):
        self.cerrada, self.respuestas, self.ok, self.bloquear = (
            asyncio.Event(),
            [],
            ok,
            bloquear,
        )

    async def responder(self, r):
        if self.bloquear:
            await self.bloquear.wait()
        if self.cerrada.is_set() or not self.ok:
            return False
        self.respuestas.append(r)
        self.cerrada.set()
        return True

    def cerrar(self):
        self.cerrada.set()


def pr(cmd="touch foo", tool_use_id="t1", sid=None):
    session = sid or SID
    datos = {
        "tool_name": "Bash",
        "tool_use_id": tool_use_id,
        "tool_input": {"command": cmd},
        "cwd": "/home/u/p",
    }
    return MensajeGancho(
        "PermissionRequest",
        "global",
        Ids(None, "w1:p1", None, None, session),
        datos,
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
def cliente_sin_login(app):
    with TestClient(
        app,
        base_url="https://testserver",
        headers=ORIGIN,
        client=("127.0.0.1", 5000),
    ) as c:
        yield c


@pytest.fixture
def cliente_logueado_sin_origin(app, cfg):
    cfg.permisos = {"desde_app": True}
    with TestClient(
        app,
        base_url="https://testserver",
        headers=ORIGIN,
        client=("127.0.0.1", 5000),
    ) as login_client:
        assert login_client.post("/api/login", json={"pin": PIN}).status_code == 200
        cookie = login_client.cookies.get(auth.COOKIE_NAME)
    with TestClient(app, base_url="https://testserver", client=("127.0.0.1", 5000)) as c:
        if cookie:
            c.cookies.set(auth.COOKIE_NAME, cookie)
        yield c


@pytest.fixture
def pedido(cliente, app, cfg):
    def _pedido(msg=None):
        cfg.permisos = {"desde_app": True}
        app.state.permisos.realpath = lambda p: p
        cliente.get("/api/board")
        m = msg or pr()
        c = FakeConexion()
        p = cliente.portal.call(app.state.permisos.atender, m, "w1:p1", c)
        return p, c

    return _pedido


@pytest.fixture
def app_con_push(cfg, tmp_path, handoffs, enchufe):
    from orquestador.app import create_app
    from orquestador.board import BoardHub
    from orquestador.digest import DigestService
    from orquestador.push import PushService
    from orquestador.state import StateStore
    from test_push import Clock, Recorder

    cfg.permisos = {"desde_app": True}
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    hub.self_pane_id = "w2:p9"
    recorder = Recorder()
    push = PushService(tmp_path, sender=recorder, clock=Clock())
    push.store.upsert(
        {
            "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
            "keys": {"p256dh": "BPubKeyPubKeyPubKeyPubKey", "auth": "AuthSecretAuth12"},
            "device": "test",
            "prefs": {"asks": True, "blocked": True, "done": True, "texto": True},
        }
    )
    app = create_app(
        cfg,
        b"secret",
        StateStore(tmp_path),
        hub=hub,
        digests=digests,
        dist=tmp_path / "nodist",
        handoffs_dir=handoffs,
        uploads_dir=tmp_path / "uploads",
        enchufe=enchufe,
        push=push,
    )
    app.state._push_recorder = recorder
    app.state._push_svc = push
    return app
