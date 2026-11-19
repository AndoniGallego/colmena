import asyncio
import json
import os
import socket

import pytest
from fastapi.testclient import TestClient

from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.ganchos import canal, mensaje
from orquestador.state import StateStore
from tests.conftest import ORIGIN

SID = "8d889181-aaaa-bbbb-cccc-000000000001"


def linea(**over):
    m = {
        "v": 1,
        "evento": "PreToolUse",
        "origen": "global",
        "ids": {
            "colmena": None,
            "herdr_pane": "w1:p1",
            "herdr_tab": "w1:t1",
            "herdr_workspace": "w1",
            "claude": SID,
        },
        "datos": {
            "tool_name": "Bash",
            "tool_use_id": "toolu_1",
            "tool_input": {"command": "ls"},
        },
    }
    m.update(over)
    return (json.dumps(m) + "\n").encode()


class W:
    def __init__(self):
        self.buf, self.closed = b"", False

    def write(self, b):
        self.buf += b

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass

    def get_extra_info(self, k):
        return None

    def is_closing(self):
        return self.closed


def reader(datos: bytes, eof=True):
    r = asyncio.StreamReader(limit=canal.MAX_LINEA + 1)
    r.feed_data(datos)
    if eof:
        r.feed_eof()
    return r


def servidor(verificar=lambda w: True):
    vistos = []

    async def manejar(msg, conexion):
        vistos.append(msg)
        conexion.cerrar()

    return canal.ServidorGanchos(manejar, verificar=verificar), vistos


def test_linea_valida_llega():
    async def esc():
        s, vistos = servidor()
        await s.atender(reader(linea()), W())
        assert vistos[0].evento == "PreToolUse"
        assert vistos[0].ids.herdr_pane == "w1:p1"
        assert vistos[0].tool_use_id == "toolu_1"

    asyncio.run(esc())


@pytest.mark.parametrize(
    "datos",
    [
        b"x" * (70000) + b"\n",
        b"no json\n",
        linea(v=2),
        linea(evento="Raro"),
        linea(origen="otro"),
        linea(datos=[]),
        b"\xff\n",
    ],
)
def test_descarta_sin_matar(datos):
    async def esc():
        s, vistos = servidor()
        w = W()
        await s.atender(reader(datos), w)
        assert vistos == [] and w.closed and s.descartados == 1

    asyncio.run(esc())


def test_descarta_linea_vacia():
    async def esc():
        s, vistos = servidor()
        w = W()
        await s.atender(reader(b""), w)
        assert vistos == [] and w.closed and s.descartados == 1

    asyncio.run(esc())


@pytest.mark.parametrize(
    "ids",
    [
        {"herdr_pane": "w1:p1\n"},
        {"herdr_pane": "../x"},
        {"claude": "s" * 10000},
        {"claude": 5},
        {"colmena": "g1:p1;rm"},
        {"herdr_tab": ["w1"]},
    ],
)
def test_ids_hostiles_descartan(ids):
    base = {
        "colmena": None,
        "herdr_pane": None,
        "herdr_tab": None,
        "herdr_workspace": None,
        "claude": SID,
    }
    assert mensaje.parsear(linea(ids={**base, **ids})) is None


def test_tool_use_id_hostil():
    assert mensaje.parsear(linea(datos={"tool_use_id": "a\nb"})) is None


@pytest.mark.parametrize("v", [True, 1.0, "1"])
def test_parsear_v_debe_ser_int_1(v):
    assert mensaje.parsear(linea(v=v)) is None


def test_parsear_recursion_json_descartado_en_atender():
    async def esc():
        s, vistos = servidor()
        w = W()
        await asyncio.wait_for(s.atender(reader(b"[" * 50000 + b"\n"), w), 2)
        assert vistos == [] and s.descartados == 1 and w.closed

    asyncio.run(esc())


class ReaderProhibido(asyncio.StreamReader):
    async def readline(self):
        raise AssertionError("reader no debía leerse")


@pytest.mark.parametrize(
    "verificar,procesa",
    [
        (lambda w: True, True),
        (lambda w: False, False),
        (lambda w: (_ for _ in ()).throw(OSError()), False),
    ],
)
def test_peercred_inyectable(verificar, procesa):
    async def esc():
        s, vistos = servidor(verificar)
        w = W()
        await s.atender(reader(linea()), w)
        assert bool(vistos) is procesa and w.closed

    asyncio.run(esc())


def test_verificar_falso_no_lee_reader_y_descarta():
    async def esc():
        s, vistos = servidor(verificar=lambda w: False)
        r = ReaderProhibido(limit=canal.MAX_LINEA + 1)
        r.feed_data(linea())
        r.feed_eof()
        w = W()
        await asyncio.wait_for(s.atender(r, w), 2)
        assert vistos == [] and s.descartados == 1 and w.closed

    asyncio.run(esc())


def test_manejar_excepcion_no_mata_servidor():
    async def esc():
        n = 0
        vistos = []

        async def manejar(msg, conexion):
            nonlocal n
            n += 1
            if n == 1:
                raise RuntimeError("boom")
            vistos.append(msg.evento)
            conexion.cerrar()

        s = canal.ServidorGanchos(manejar, verificar=lambda w: True)
        await asyncio.wait_for(s.atender(reader(linea()), W()), 2)
        w2 = W()
        await asyncio.wait_for(s.atender(reader(linea()), w2), 2)
        assert vistos == ["PreToolUse"] and w2.closed

    asyncio.run(esc())


def _loop_global_previo():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        return None


def test_mismo_uid_socketpair():
    try:
        a, b = socket.socketpair()
    except PermissionError:
        pytest.skip("socketpair no permitido en este entorno")
    prev = _loop_global_previo()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        r, w = loop.run_until_complete(asyncio.open_connection(sock=b))
        assert canal.mismo_uid(w) is True
        w.close()
        loop.run_until_complete(w.wait_closed())
        r.feed_eof()
        loop.close()
    finally:
        a.close()
        if prev is not None and not prev.is_closed():
            asyncio.set_event_loop(prev)


def test_mismo_uid_otro_uid(monkeypatch):
    try:
        a, b = socket.socketpair()
    except PermissionError:
        pytest.skip("socketpair no permitido en este entorno")
    prev = _loop_global_previo()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        r, w = loop.run_until_complete(asyncio.open_connection(sock=b))
        uid_real = os.getuid()
        monkeypatch.setattr(os, "getuid", lambda: uid_real + 1)
        assert canal.mismo_uid(w) is False
        w.close()
        loop.run_until_complete(w.wait_closed())
        r.feed_eof()
        loop.close()
    finally:
        a.close()
        if prev is not None and not prev.is_closed():
            asyncio.set_event_loop(prev)


def test_mismo_uid_sin_socket():
    assert canal.mismo_uid(W()) is False


def test_cerrar_marca_cerrada_sin_ceder_loop():
    async def esc():
        w = W()
        c = canal.Conexion(reader(b"", eof=False), w)
        c.cerrar()
        assert c.cerrada.is_set()

    asyncio.run(esc())


def test_responder_una_sola_vez_y_eof_cierra():
    async def esc():
        w = W()
        c = canal.Conexion(reader(b"", eof=False), w)
        assert await c.responder({"v": 1, "decision": "allow"}) is True
        assert await c.responder({"v": 1, "decision": "deny"}) is False
        assert w.buf.count(b"\n") == 1
        c2 = canal.Conexion(reader(b"", eof=True), W())
        await asyncio.wait_for(c2.cerrada.wait(), 1)
        assert await c2.responder({"v": 1, "decision": "allow"}) is False

    asyncio.run(esc())


def test_responder_concurrente_una_linea():
    async def esc():
        w = W()
        c = canal.Conexion(reader(b"", eof=False), w)
        r1, r2 = await asyncio.gather(
            c.responder({"v": 1, "decision": "allow"}),
            c.responder({"v": 1, "decision": "deny"}),
        )
        assert sorted([r1, r2]) == [False, True]
        assert w.buf.count(b"\n") == 1

    asyncio.run(esc())


class ReaderReset(asyncio.StreamReader):
    async def read(self, n=-1):
        raise ConnectionResetError()


def test_hasta_eof_reset_cierra_sin_excepcion_huérfana():
    async def esc():
        w = W()
        c = canal.Conexion(ReaderReset(limit=65536), w)
        await asyncio.wait_for(c.cerrada.wait(), 2)
        leer = c._leer
        c.cerrar()
        await asyncio.wait_for(asyncio.shield(leer), 2)
        assert leer.done() and leer.cancelled() is False and leer.exception() is None

    asyncio.run(esc())


def test_atender_cancelado_antes_de_vivas_cierra_writer():
    en_readline = asyncio.Event()

    class ReaderSinDatos(asyncio.StreamReader):
        async def readline(self):
            en_readline.set()
            await asyncio.Event().wait()

    async def esc():
        s, _ = servidor()
        r = ReaderSinDatos(limit=canal.MAX_LINEA + 1)
        w = W()
        t = asyncio.create_task(s.atender(r, w))
        await asyncio.wait_for(en_readline.wait(), 2)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(t), 2)
        assert w.closed

    asyncio.run(esc())


def test_cerrar_desde_manejar_no_se_cancela_a_si_mismo():
    async def esc():
        terminado = asyncio.Event()

        async def manejar(msg, conexion):
            await asyncio.wait_for(s.cerrar(), 2)
            conexion.cerrar()
            terminado.set()

        s = canal.ServidorGanchos(manejar, verificar=lambda w: True)
        await asyncio.wait_for(s.atender(reader(linea()), W()), 2)
        await asyncio.wait_for(terminado.wait(), 2)

    asyncio.run(esc())


def test_servidor_cerrar_idempotente_y_sin_abrir():
    async def esc():
        s = canal.ServidorGanchos(lambda m, c: None)
        await asyncio.wait_for(s.cerrar(), 2)
        await asyncio.wait_for(s.cerrar(), 2)

    asyncio.run(esc())


def test_create_app_sin_socket_no_abre(app):
    ganchos = getattr(app.state, "ganchos", None)
    assert ganchos is None or ganchos._server is None


def test_ganchos_shutdown_cancela_tareas_observer(cfg, tmp_path, handoffs, enchufe, monkeypatch):
    import copy

    from tests.permisos_support import FakeConexion, pr

    canceladas: list[str] = []

    async def observar_colgado(pane, status):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            canceladas.append(pane)
            raise

    async def abrir_noop(self, ruta):
        return None

    async def cerrar_noop(self):
        return None

    monkeypatch.setattr(canal.ServidorGanchos, "abrir", abrir_noop)
    monkeypatch.setattr(canal.ServidorGanchos, "cerrar", cerrar_noop)

    cfg.permisos = {"desde_app": True}
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
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
        ganchos_socket=tmp_path / "colmena" / "ganchos.sock",
    )

    async def preparar():
        permisos = app.state.permisos
        permisos.observar_herdr = observar_colgado
        p = await permisos.atender(pr(tool_use_id="t_shut"), "w1:p1", FakeConexion())
        assert p is not None
        await hub.refresh()
        hub._publicar(copy.deepcopy(hub.board))

    asyncio.run(preparar())
    with TestClient(app, base_url="https://testserver", headers=ORIGIN):
        pass
    assert "w1:p1" in canceladas


def test_create_app_shutdown_llama_cerrar_ganchos(cfg, tmp_path, handoffs, enchufe, monkeypatch, flush_falla=False):
    cerrado = {"ok": False}
    if flush_falla:
        from orquestador.biblioteca import Library

        def flush_roto(self):
            raise OSError("disco lleno")

        monkeypatch.setattr(Library, "flush", flush_roto)

    async def abrir_noop(self, ruta):
        return None

    async def cerrar_marca(self):
        cerrado["ok"] = True

    monkeypatch.setattr(canal.ServidorGanchos, "abrir", abrir_noop)
    monkeypatch.setattr(canal.ServidorGanchos, "cerrar", cerrar_marca)
    socket_ruta = tmp_path / "colmena" / "ganchos.sock"
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
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
        ganchos_socket=socket_ruta,
    )
    with TestClient(app, base_url="https://testserver", headers=ORIGIN) as client:
        assert client.get("/api/board").status_code in (401, 403)
    assert cerrado["ok"] is True


def test_shutdown_sigue_con_los_demas_handlers_si_library_flush_falla(cfg, tmp_path, handoffs, enchufe, monkeypatch):
    test_create_app_shutdown_llama_cerrar_ganchos(cfg, tmp_path, handoffs, enchufe, monkeypatch, flush_falla=True)


def test_redaccion_de_secretos():
    sucio = {
        "command": "curl -H 'Authorization: Bearer abcdef0123456789abcdef' --password hunter2xyz",
        "otro": ["token=ghp_" + "a" * 36],
    }
    limpio = json.dumps(mensaje.redactar_entrada(sucio))
    for secreto in ("abcdef0123456789abcdef", "hunter2xyz", "ghp_" + "a" * 36):
        assert secreto not in limpio
