import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from orquestador import auth, terminal_vivo
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.config import Config, hash_pin
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales, NoDisponible, NoExiste
from orquestador.enchufe.guardian import FotoVivo
from orquestador.state import StateStore
from tests.conftest import PIN, make_snapshot

ORIGIN = "https://testserver"
ORIGIN_HDR = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}
SID = "g1:p1"


def _ws(client, path):
    headers = dict(ORIGIN_HDR)
    token = client.cookies.get(auth.COOKIE_NAME)
    if token:
        headers["Cookie"] = f"{auth.COOKIE_NAME}={token}"
    return client.websocket_connect(path, headers=headers)


def _cierre(ws, codigo: int) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        ws.receive_text()
    assert exc.value.code == codigo


class CanalFalso:
    def __init__(self, eventos=None, foto=None):
        self.foto = foto or FotoVivo(80, 24, (), ("linea1",), None)
        self._cola: asyncio.Queue = asyncio.Queue()
        for ev in eventos or []:
            self._cola.put_nowait(ev)
        self.cerrado = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self._cola.get()

    async def cerrar(self):
        self.cerrado = True


@pytest.fixture
def cfg_vivo(tmp_path, projects):
    c = Config(pin=hash_pin(PIN), claude_projects_dir=str(projects), claude_cwd=str(tmp_path))
    c.app_origin = ORIGIN
    c.terminales = {"vivo": True}
    return c


@pytest.fixture
def app_vivo(cfg_vivo, tmp_path, handoffs, enchufe):
    digests = DigestService(cfg_vivo.projects_dir())
    hub = BoardHub(enchufe, digests)
    hub.self_pane_id = "w2:p9"
    app = create_app(
        cfg_vivo,
        b"secret",
        StateStore(tmp_path),
        hub=hub,
        digests=digests,
        dist=tmp_path / "nodist",
        handoffs_dir=handoffs,
        uploads_dir=tmp_path / "uploads",
        enchufe=enchufe,
    )
    return app


@pytest.fixture
def client_vivo(app_vivo):
    with TestClient(app_vivo, base_url=ORIGIN, headers=ORIGIN_HDR, client=("127.0.0.1", 5000)) as c:
        yield c


@pytest.fixture
def authed_vivo(client_vivo):
    assert client_vivo.post("/api/login", json={"pin": PIN}).status_code == 200
    return client_vivo


def test_sin_cookie_rechazado(app_vivo):
    with TestClient(app_vivo, base_url=ORIGIN, headers=ORIGIN_HDR) as c:
        with pytest.raises(WebSocketDisconnect) as exc:
            with _ws(c, f"/api/terminal/{SID}/vivo"):
                pass
        assert exc.value.code == 1008


def test_origen_ajeno_rechazado(authed_vivo, app_vivo):
    with TestClient(app_vivo, base_url=ORIGIN, cookies=authed_vivo.cookies, client=("127.0.0.1", 5000)) as c:
        with pytest.raises(WebSocketDisconnect) as exc:
            with c.websocket_connect(
                f"/api/terminal/{SID}/vivo",
                headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "same-origin"},
            ):
                pass
        assert exc.value.code == 1008


def test_sin_origin_rechazado(authed_vivo, app_vivo):
    headers = {"Sec-Fetch-Site": "same-origin"}
    token = authed_vivo.cookies.get(auth.COOKIE_NAME)
    if token:
        headers["Cookie"] = f"{auth.COOKIE_NAME}={token}"
    with TestClient(app_vivo, base_url=ORIGIN, cookies=authed_vivo.cookies, client=("127.0.0.1", 5000)) as c:
        with pytest.raises(WebSocketDisconnect) as exc:
            with c.websocket_connect(f"/api/terminal/{SID}/vivo", headers=headers):
                pass
        assert exc.value.code == 1008


def test_sin_marca_origen_rechazado(cfg_vivo, tmp_path, handoffs, enchufe):
    digests = DigestService(cfg_vivo.projects_dir())
    hub = BoardHub(enchufe, digests)
    app = create_app(
        cfg_vivo,
        b"secret",
        StateStore(tmp_path),
        hub=hub,
        digests=digests,
        dist=tmp_path / "nodist",
        handoffs_dir=handoffs,
        uploads_dir=tmp_path / "uploads",
        enchufe=enchufe,
        entrada_interna=False,
    )
    abiertos = []

    async def abrir(sid):
        abiertos.append(sid)
        return CanalFalso()

    app.state.abrir_vivo = abrir
    with TestClient(app, base_url=ORIGIN, headers=ORIGIN_HDR) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        with pytest.raises(WebSocketDisconnect) as exc:
            with _ws(c, f"/api/terminal/{SID}/vivo"):
                pass
        assert exc.value.code == 1008
    assert abiertos == []


def test_foto_y_salida(authed_vivo, app_vivo):
    async def abrir(_sid):
        return CanalFalso([{"tipo": "salida", "texto": "hola"}])

    app_vivo.state.abrir_vivo = abrir
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        msg = ws.receive_json()
        assert msg["tipo"] == "foto" and msg["columnas"] == 80 and msg["filas"] == 24 and "linea1" in msg["texto"]
        msg2 = ws.receive_json()
        assert msg2 == {"tipo": "salida", "texto": "hola"}


def test_termino_cierra(authed_vivo, app_vivo):
    async def abrir(_sid):
        return CanalFalso([{"tipo": "termino", "codigo": 0}])

    app_vivo.state.abrir_vivo = abrir
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        msg = ws.receive_json()
        assert msg["tipo"] == "termino" and msg["codigo"] == 0
        _cierre(ws, 1000)


def test_desconexion_cliente_cierra_canal(authed_vivo, app_vivo):
    canal = CanalFalso()

    async def abrir(_sid):
        return canal

    app_vivo.state.abrir_vivo = abrir
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
    assert canal.cerrado
    assert app_vivo.state.cupos_vivo._total == 0


def test_vivo_apagado(cfg_vivo, tmp_path, handoffs, enchufe):
    cfg_vivo.terminales = {"vivo": False}
    digests = DigestService(cfg_vivo.projects_dir())
    app = create_app(
        cfg_vivo,
        b"secret",
        StateStore(tmp_path),
        hub=BoardHub(enchufe, digests),
        digests=digests,
        dist=tmp_path / "nodist",
        handoffs_dir=handoffs,
        uploads_dir=tmp_path / "uploads",
        enchufe=enchufe,
    )
    with TestClient(app, base_url=ORIGIN, headers=ORIGIN_HDR, client=("127.0.0.1", 5000)) as c:
        c.post("/api/login", json={"pin": PIN})
        with _ws(c, f"/api/terminal/{SID}/vivo") as ws:
            msg = ws.receive_json()
            assert msg["codigo"] == "apagado"
            _cierre(ws, 4403)


def test_no_es_propia(authed_vivo, app_vivo):
    async def abrir(_sid):
        raise AssertionError("no debería abrir")

    app_vivo.state.abrir_vivo = abrir
    with _ws(authed_vivo, "/api/terminal/w1:p1/vivo") as ws:
        msg = ws.receive_json()
        assert msg["codigo"] == "no_es_propia"
        _cierre(ws, 4404)


def test_no_existe(authed_vivo, app_vivo):
    async def abrir(_sid):
        raise NoExiste("x")

    app_vivo.state.abrir_vivo = abrir
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        msg = ws.receive_json()
        assert msg["codigo"] == "no_existe"
        _cierre(ws, 4404)


def test_caido_al_abrir(authed_vivo, app_vivo):
    async def abrir(_sid):
        raise NoDisponible("x")

    app_vivo.state.abrir_vivo = abrir
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        msg = ws.receive_json()
        assert msg["tipo"] == "caido"
        _cierre(ws, 4503)


def test_cupo_por_sesion(app_vivo):
    async def abrir(_sid):
        return CanalFalso()

    app_vivo.state.abrir_vivo = abrir
    abiertas = []
    for _ in range(3):
        c = TestClient(app_vivo, base_url=ORIGIN, headers=ORIGIN_HDR, client=("127.0.0.1", 5000))
        c.post("/api/login", json={"pin": PIN})
        cm = _ws(c, f"/api/terminal/{SID}/vivo")
        ws = cm.__enter__()
        ws.receive_json()
        abiertas.append((c, cm))
    c4 = TestClient(app_vivo, base_url=ORIGIN, headers=ORIGIN_HDR, client=("127.0.0.1", 5000))
    c4.post("/api/login", json={"pin": PIN})
    with _ws(c4, f"/api/terminal/{SID}/vivo") as ws:
        msg = ws.receive_json()
        assert msg["codigo"] == "cupo"
        _cierre(ws, 4429)
    for c, cm in abiertas:
        cm.__exit__(None, None, None)
        c.close()


def test_cupo_global():
    cupos = terminal_vivo.Cupos()
    sids = [f"g1:p{i}" for i in range(8)]
    for sid in sids:
        assert cupos.tomar(sid)
    assert not cupos.tomar("g2:p1")
    for sid in sids:
        cupos.soltar(sid)
    assert cupos._total == 0


def test_mensaje_largo_cierra(authed_vivo, app_vivo):
    async def abrir(_sid):
        return CanalFalso()

    app_vivo.state.abrir_vivo = abrir
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        ws.send_text("x" * (terminal_vivo.MAX_ENTRADA + 1))


def test_mensaje_binario_cierra(authed_vivo, app_vivo):
    async def abrir(_sid):
        return CanalFalso()

    app_vivo.state.abrir_vivo = abrir
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        ws.send_bytes(b"\x00")


def test_sesion_revalidada(authed_vivo, app_vivo, monkeypatch):
    liberar = asyncio.Event()

    class CanalEspera(CanalFalso):
        async def __anext__(self):
            await liberar.wait()
            return {"tipo": "salida", "texto": "x"}

    async def abrir(_sid):
        return CanalEspera()

    app_vivo.state.abrir_vivo = abrir
    monkeypatch.setattr(terminal_vivo, "REVALIDAR_S", 0)
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        authed_vivo.post("/api/sessions/revoke-all")
        liberar.set()
        msg = ws.receive_json()
        assert msg["codigo"] == "sesion"
        _cierre(ws, 4401)


def test_config_incluye_vivo(authed_vivo):
    cfg = authed_vivo.get("/api/terminales/config").json()
    assert cfg["vivo"] is True


def test_armar_foto():
    foto = FotoVivo(
        10,
        3,
        ("ok\x07", "hist"),
        ("a", "b", "c", "sobra"),
        (5, 1),
        cursor_visible=False,
    )
    texto = terminal_vivo.armar_foto(foto)
    assert texto.endswith("\x1b[?25l")
    assert "\x1b[2;6H" in texto
    assert "ok" in texto and "\x07" not in texto
    assert texto.count("\r\n") >= 4
