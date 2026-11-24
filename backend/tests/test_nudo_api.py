import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, make_snapshot
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.nudo import NudoStore, ServidorNudo, crear_manejador, ruta_socket
from orquestador.push import PushService
from orquestador.state import StateStore
from test_avisos import Sender

DEV = "device-abc123"
PANE = "w1:p1"
CONTROLES = {"foto": 3, "ventana": {"titulo": "Mail", "proceso": "mail.exe"}, "monitor": "1920x1080",
             "controles": [{"n": 1, "tipo": "boton", "nombre": "Enviar"}]}


@pytest.fixture
def pclient(cfg, tmp_path, handoffs):
    enchufe = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    push = PushService(tmp_path, sender=Sender(), wall=lambda: 1_800_000_000.0)
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, push=push, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


async def _esperar(q):
    return await asyncio.wait_for(q.get(), 5)


def pedido(c, op="controles", args=None, sesion=PANE):
    """Deja un pedido en vuelo con una PC falsa conectada; devuelve (future, id, token)."""
    store = c.app.state.nudo
    q: asyncio.Queue = asyncio.Queue(maxsize=8)
    store.pc_conectada(DEV, q)
    while not q.empty():
        q.get_nowait()
    fut = c.portal.start_task_soon(store.pedir, sesion, "n", op, args or {})
    _, ev = c.portal.call(_esperar, q)
    return fut, ev["id"], ev["token"]


def test_events_con_pc_registra_la_pc(app, authed):
    cookie = "; ".join(f"{k}={v}" for k, v in authed.cookies.items())
    visto = {}

    async def correr():
        headers = [(b"host", b"testserver"), (b"origin", b"http://testserver"), (b"cookie", cookie.encode())]
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
                 "scheme": "https", "path": "/api/events", "raw_path": b"/api/events",
                 "query_string": f"cid={DEV}&pc=1".encode(), "headers": headers,
                 "client": ("127.0.0.1", 5000), "server": ("testserver", 443)}
        llego, desconectar = asyncio.Event(), asyncio.Event()

        async def receive():
            await desconectar.wait()
            return {"type": "http.disconnect"}

        async def send(msg):
            if msg["type"] == "http.response.body" and msg.get("body"):
                llego.set()

        t = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(llego.wait(), 5)
        visto["dentro"] = app.state.nudo.pc_objetivo()
        desconectar.set()
        t.cancel()
        try:
            await t
        except BaseException:
            pass
        visto["fuera"] = app.state.nudo.pc_objetivo()

    asyncio.run(correr())
    assert visto == {"dentro": DEV, "fuera": None}


def test_sse_que_se_va_antes_del_primer_byte_no_deja_pc_fantasma(app, authed):
    cookie = "; ".join(f"{k}={v}" for k, v in authed.cookies.items())

    async def correr():
        headers = [(b"host", b"testserver"), (b"origin", b"http://testserver"), (b"cookie", cookie.encode())]
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
                 "scheme": "https", "path": "/api/events", "raw_path": b"/api/events",
                 "query_string": f"cid={DEV}&pc=1".encode(), "headers": headers,
                 "client": ("127.0.0.1", 5000), "server": ("testserver", 443)}

        async def receive():
            await asyncio.Event().wait()

        async def send(msg):
            raise OSError("cliente se fue")

        try:
            await app(scope, receive, send)
        except BaseException:
            pass

    asyncio.run(correr())
    assert app.state.nudo.pc_objetivo() is None


def test_respuesta_con_token_valido(pclient):
    fut, pid, token = pedido(pclient)
    r = pclient.post(f"/api/nudo/{pid}/respuesta", json={"device": DEV, "token": token, "resultado": CONTROLES})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert fut.result(5)["controles"][0]["nombre"] == "Enviar"


def test_respuesta_con_token_ajeno_es_404(pclient):
    fut, pid, token = pedido(pclient)
    r = pclient.post(f"/api/nudo/{pid}/respuesta", json={"device": DEV, "token": "otro", "resultado": CONTROLES})
    assert r.status_code == 404
    r = pclient.post(f"/api/nudo/{pid}/respuesta",
                     json={"device": "device-otro99", "token": token, "resultado": CONTROLES})
    assert r.status_code == 404
    pclient.app.state.nudo.cancelar(pid)


@pytest.mark.parametrize("body", [{"device": DEV, "token": "t"},
                                  {"device": "x", "token": "t", "resultado": {}},
                                  {"device": DEV, "token": "t" * 65, "resultado": {}}])
def test_respuesta_valida_el_cuerpo(pclient, body):
    assert pclient.post("/api/nudo/abc/respuesta", json=body).status_code == 422


def test_respuesta_con_controles_invalidos_es_422(pclient):
    fut, pid, token = pedido(pclient)
    malo = {**CONTROLES, "controles": [{"n": 1, "tipo": "imagen", "nombre": "x"}]}
    r = pclient.post(f"/api/nudo/{pid}/respuesta", json={"device": DEV, "token": token, "resultado": malo})
    assert r.status_code == 422
    pclient.app.state.nudo.cancelar(pid)


def test_salir_libera(pclient):
    store = pclient.app.state.nudo
    store.pc_conectada(DEV, asyncio.Queue())
    store._dueno = [PANE, "n", store._clock()]
    assert store.dueno() is not None
    assert pclient.post("/api/nudo/salir", json={"device": DEV}).json() == {"ok": True}
    assert store.dueno() is None


def test_salir_de_otro_dispositivo_no_libera(pclient):
    store = pclient.app.state.nudo
    store.pc_conectada(DEV, asyncio.Queue())
    store._dueno = [PANE, "n", store._clock()]
    assert pclient.post("/api/nudo/salir", json={"device": "device-otro99"}).status_code == 403
    assert store.dueno() is not None


def test_respuesta_necesita_sesion_y_origen(pclient, cfg, tmp_path, handoffs):
    body = {"device": DEV, "token": "t", "resultado": {}}
    assert pclient.post("/api/nudo/abc/respuesta", json=body,
                        headers={"Origin": "https://evil.example"}).status_code == 403
    enchufe = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    digests = DigestService(cfg.projects_dir())
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=BoardHub(enchufe, digests), digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as anon:
        assert anon.post("/api/nudo/abc/respuesta", json=body).status_code == 401
        assert anon.post("/api/nudo/salir", json={"device": DEV}).status_code == 401


# --- socket ---

def _tablero():
    return {"workspaces": [{"tabs": [{"agents": [{"pane_id": PANE, "title": "Mi sesión"}]}]}]}


class Banco:
    def __init__(self, con_pc=True):
        self.enviados: list = []
        self.cola: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.store = NudoStore(lambda q, ev: q.put_nowait(ev))
        if con_pc:
            self.store.pc_conectada(DEV, self.cola)
            while not self.cola.empty():
                self.cola.get_nowait()
        self.manejar = crear_manejador(self.store, _tablero)

    async def pc_responde(self, resultado):
        _, ev = await _esperar(self.cola)
        assert self.store.resolver(ev["id"], DEV, ev["token"], resultado)
        return ev


async def _cliente(ruta, msg):
    reader, writer = await asyncio.open_unix_connection(str(ruta))
    writer.write((json.dumps(msg) + "\n").encode() if not isinstance(msg, bytes) else msg)
    await writer.drain()
    try:
        linea = await asyncio.wait_for(reader.readline(), 5)
    except ConnectionResetError:
        linea = b""
    writer.close()
    return json.loads(linea) if linea else None


@pytest.mark.unix
def test_socket_controles_ida_y_vuelta(tmp_path):
    async def run():
        b = Banco()
        srv = ServidorNudo(b.manejar)
        ruta = tmp_path / "x" / "nudo.sock"
        await srv.abrir(ruta)
        try:
            pc = asyncio.ensure_future(b.pc_responde(CONTROLES))
            resp = await _cliente(ruta, {"op": "controles", "sesion": PANE, "args": {}})
            ev = await pc
            assert ev["sesion"] == "Mi sesión"
        finally:
            await srv.cerrar()
        return resp

    assert asyncio.run(run()) == {"ok": True, "datos": {
        "ventana": {"titulo": "Mail", "proceso": "mail.exe"}, "monitor": "1920x1080",
        "controles": [{"n": 1, "tipo": "boton", "nombre": "Enviar"}]}}


@pytest.mark.unix
def test_socket_error_con_mensaje(tmp_path):
    async def run():
        srv = ServidorNudo(Banco(con_pc=False).manejar)
        ruta = tmp_path / "x" / "nudo.sock"
        await srv.abrir(ruta)
        try:
            return await _cliente(ruta, {"op": "controles", "sesion": PANE, "args": {}})
        finally:
            await srv.cerrar()

    assert asyncio.run(run()) == {"ok": False, "error": "sin_pc",
                                  "mensaje": "PC no conectada: la app de Windows no está abierta."}


@pytest.mark.unix
def test_socket_rechaza_otro_uid(tmp_path):
    async def run():
        srv = ServidorNudo(Banco().manejar, verificar=lambda w: False)
        ruta = tmp_path / "x" / "nudo.sock"
        await srv.abrir(ruta)
        try:
            return await _cliente(ruta, {"op": "estado", "sesion": PANE, "args": {}})
        finally:
            await srv.cerrar()

    assert asyncio.run(run()) is None


@pytest.mark.unix
@pytest.mark.parametrize("msg", [
    {"op": "borrar", "sesion": PANE, "args": {}},
    {"op": "controles", "sesion": "../x", "args": {}},
    {"op": "senalar", "sesion": PANE, "args": {"n": 1, "texto": "a\nb"}},
    {"op": "controles", "sesion": PANE, "args": []},
    [1, 2],
    b"no es json\n",
    b"x" * 9000 + b"\n",
])
def test_socket_valida_op_sesion_y_args(tmp_path, msg):
    async def run():
        b = Banco()
        srv = ServidorNudo(b.manejar)
        ruta = tmp_path / "x" / "nudo.sock"
        await srv.abrir(ruta)
        try:
            resp = await _cliente(ruta, msg)
            assert b.cola.empty()
            return resp
        finally:
            await srv.cerrar()

    resp = asyncio.run(run())
    assert resp["ok"] is False and resp["error"] == "invalido" and resp["mensaje"]


@pytest.mark.unix
def test_cli_que_corta_libera_el_pedido(tmp_path):
    async def run():
        b = Banco()
        srv = ServidorNudo(b.manejar)
        ruta = tmp_path / "x" / "nudo.sock"
        await srv.abrir(ruta)
        try:
            # lectura previa para que haya foto
            pc = asyncio.ensure_future(b.pc_responde(CONTROLES))
            await _cliente(ruta, {"op": "controles", "sesion": PANE, "args": {}})
            await pc
            reader, writer = await asyncio.open_unix_connection(str(ruta))
            writer.write((json.dumps({"op": "senalar", "sesion": PANE,
                                      "args": {"n": 1, "texto": "hola", "esperar": 60}}) + "\n").encode())
            await writer.drain()
            await _esperar(b.cola)
            assert b.store._pend is not None
            writer.close()
            await writer.wait_closed()
            await asyncio.sleep(0.2)
            assert b.store._pend is None
            pc = asyncio.ensure_future(b.pc_responde(CONTROLES))
            resp = await _cliente(ruta, {"op": "controles", "sesion": PANE, "args": {}})
            await pc
            return resp
        finally:
            await srv.cerrar()

    resp = asyncio.run(run())
    assert resp["ok"] is True


def test_ruta_socket():
    assert ruta_socket({"XDG_RUNTIME_DIR": "/run/user/1000"}) == Path("/run/user/1000/colmena/nudo.sock")
    assert ruta_socket({}) is None
