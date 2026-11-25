"""Protocolo del socket del MCP de Colmena: ops cerradas, tamaños, permisos y cliente sin backend."""
import asyncio
import errno
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from orquestador import mcp_canal, mcp_colmena

pytestmark = pytest.mark.unix

UID = os.getuid()


@pytest.fixture
def corto():
    d = Path(tempfile.mkdtemp(prefix="cm", dir="/tmp"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _skip_sandbox(exc: BaseException) -> None:
    if isinstance(exc, PermissionError) or (isinstance(exc, OSError) and exc.errno in (errno.EPERM, errno.EACCES)):
        pytest.skip(str(exc))
    raise exc


def _proc_para(base: Path, pid_claude: int) -> Path:
    """/proc falso: este proceso (el que conecta) es hijo de `pid_claude`."""
    raiz = base / "proc"
    for pid, ppid in ((os.getpid(), pid_claude), (pid_claude, 1)):
        d = raiz / str(pid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "stat").write_text(f"{pid} (python) S {ppid} 1 1 0\n")
    return raiz


def _sesiones(pid_claude: int, modo=None):
    return [{"id": "g1:p1", "nombre": "Uno", "estado": "idle", "claude_session_id": "c1",
             "pid_claude": pid_claude, "pid": pid_claude, "modo": modo, "cwd": "/tmp"},
            {"id": "g2:p1", "nombre": "Dos", "estado": "idle", "claude_session_id": "c2",
             "pid_claude": 4242, "pid": 4242, "modo": None, "cwd": "/tmp"}]


class _Llamadas:
    def __init__(self):
        self.vistas: list[tuple[str, dict, dict]] = []

    def ops(self):
        def hacer(nombre):
            async def h(ident, args):
                self.vistas.append((nombre, ident, args))
                return {"op": nombre, "sesion": ident["sesion_id"]}
            return h
        return {op: hacer(op) for op in mcp_canal.OPS}


async def _con_servidor(corto, fn, *, modo=None, credenciales=None, timeout_linea=10.0, sin_ancestro=False):
    ruta = corto / "colmena" / "mcp.sock"
    pid_claude = 3131
    proc = _proc_para(corto, pid_claude)
    llamadas = _Llamadas()

    async def tablero():
        return _sesiones(9999 if sin_ancestro else pid_claude, modo)

    kw = {"credenciales": credenciales} if credenciales else {}
    srv = mcp_canal.ServidorMcp(tablero, llamadas.ops(), proc=proc, uid=UID, timeout_linea=timeout_linea, **kw)
    try:
        await srv.abrir(ruta)
    except (PermissionError, OSError) as e:
        _skip_sandbox(e)
    try:
        await fn(ruta, llamadas, srv)
    finally:
        await srv.cerrar()


async def _conectar(ruta):
    return await asyncio.open_unix_connection(str(ruta), limit=1 << 20)


async def _pedir(r, w, obj) -> dict:
    w.write(obj if isinstance(obj, bytes) else json.dumps(obj).encode() + b"\n")
    await w.drain()
    linea = await asyncio.wait_for(r.readline(), 5)
    return json.loads(linea)


def test_lista_de_ops_cerrada_y_sin_aprobar():
    assert mcp_canal.OPS == frozenset({"sesiones", "leer_sesion", "pedidos", "buscar_memoria", "abrir", "mensaje",
                                       "cerrar", "cursor", "programar", "tarea_ticket", "estado_pedido"})
    assert isinstance(mcp_canal.OPS, frozenset)
    for op in mcp_canal.OPS:
        assert "aprob" not in op and "rechaz" not in op


def test_ops_fuera_de_la_lista_devuelven_op_desconocida(corto):
    async def caso(ruta, llamadas, _srv):
        r, w = await _conectar(ruta)
        for op in ("aprobar", "abrir_pedido", "rechazar", "pedidos_pestana_abrir", "", "SESIONES"):
            res = await _pedir(r, w, {"id": "1", "op": op, "args": {}})
            assert res == {"id": "1", "ok": False, "error": {"codigo": "op_desconocida", "mensaje": res["error"]["mensaje"]}}
        res = await _pedir(r, w, {"id": "2", "op": "sesiones", "args": {}})
        assert res["ok"] is True and res["resultado"]["op"] == "sesiones"
        assert [v[0] for v in llamadas.vistas] == ["sesiones"]
        w.close()

    asyncio.run(_con_servidor(corto, caso))


def test_peticion_grande_o_json_invalido_no_cierra_el_servidor(corto):
    async def caso(ruta, llamadas, _srv):
        r, w = await _conectar(ruta)
        grande = json.dumps({"id": "g", "op": "sesiones", "args": {"x": "a" * (17 * 1024)}}).encode() + b"\n"
        res = await _pedir(r, w, grande)
        assert res["ok"] is False and res["error"]["codigo"] == "demasiado_grande"
        res = await _pedir(r, w, b"{no es json\n")
        assert res["ok"] is False and res["error"]["codigo"] == "argumentos_invalidos"
        res = await _pedir(r, w, b'["lista"]\n')
        assert res["error"]["codigo"] == "argumentos_invalidos"
        res = await _pedir(r, w, {"id": "x" * 65, "op": "sesiones", "args": {}})
        assert res["error"]["codigo"] == "argumentos_invalidos"
        res = await _pedir(r, w, {"id": "3", "op": "sesiones", "args": []})
        assert res["error"]["codigo"] == "argumentos_invalidos"
        res = await _pedir(r, w, {"id": "4", "op": "sesiones", "args": {}})
        assert res["ok"] is True
        w.close()
        # Otra conexión sigue andando.
        r2, w2 = await _conectar(ruta)
        assert (await _pedir(r2, w2, {"id": "5", "op": "sesiones"}))["ok"] is True
        w2.close()
        assert len(llamadas.vistas) == 2

    asyncio.run(_con_servidor(corto, caso))


def test_identidad_declarada_por_el_cliente_no_cuenta(corto):
    async def caso(ruta, llamadas, _srv):
        r, w = await _conectar(ruta)
        args = {"sesion": "g2:p1", "sesion_origen": "g2:p1", "pane_id": "g2:p1", "COLMENA_SESION": "g2:p1"}
        res = await _pedir(r, w, {"id": "1", "op": "pedidos", "args": args, "sesion": "g2:p1", "pane_id": "g2:p1"})
        assert res["ok"] is True and res["resultado"]["sesion"] == "g1:p1"
        assert llamadas.vistas[0][1]["sesion_id"] == "g1:p1"
        w.close()

    asyncio.run(_con_servidor(corto, caso))


def test_sin_ancestro_devuelve_sesion_no_identificada_sin_efectos(corto):
    async def caso(ruta, llamadas, _srv):
        r, w = await _conectar(ruta)
        res = await _pedir(r, w, {"id": "1", "op": "abrir", "args": {"carpeta": "/tmp"}})
        assert res["ok"] is False and res["error"]["codigo"] == "sesion_no_identificada"
        assert llamadas.vistas == []
        w.close()

    asyncio.run(_con_servidor(corto, caso, sin_ancestro=True))


def test_copiloto_recibe_sesion_no_permitida(corto):
    async def caso(ruta, llamadas, _srv):
        r, w = await _conectar(ruta)
        res = await _pedir(r, w, {"id": "1", "op": "sesiones", "args": {}})
        assert res["ok"] is False and res["error"]["codigo"] == "sesion_no_permitida"
        assert llamadas.vistas == []
        w.close()

    asyncio.run(_con_servidor(corto, caso, modo="copiloto"))


def test_otro_uid_se_cierra_sin_leer(corto):
    async def caso(ruta, llamadas, srv):
        r, w = await _conectar(ruta)
        w.write(b'{"id":"1","op":"sesiones","args":{}}\n')
        await w.drain()
        try:
            assert await asyncio.wait_for(r.read(), 5) == b""
        except ConnectionResetError:
            pass  # cerrar con datos sin leer manda un reset: es lo esperado
        assert llamadas.vistas == []
        assert srv.leidas == 0
        w.close()

    asyncio.run(_con_servidor(corto, caso, credenciales=lambda _w: (os.getpid(), UID + 1, 0)))


def test_timeout_de_lectura_cierra_la_conexion(corto):
    async def caso(ruta, llamadas, _srv):
        r, w = await _conectar(ruta)
        w.write(b'{"id":"1"')
        await w.drain()
        assert await asyncio.wait_for(r.read(), 5) == b""
        w.close()

    asyncio.run(_con_servidor(corto, caso, timeout_linea=0.3))


def test_maximo_cuatro_conexiones_por_sesion(corto):
    async def caso(ruta, llamadas, _srv):
        abiertas = []
        for i in range(4):
            r, w = await _conectar(ruta)
            assert (await _pedir(r, w, {"id": str(i), "op": "sesiones"}))["ok"] is True
            abiertas.append(w)
        r, w = await _conectar(ruta)
        w.write(b'{"id":"5","op":"sesiones"}\n')
        await w.drain()
        linea = await asyncio.wait_for(r.readline(), 5)
        assert linea == b"" or json.loads(linea)["error"]["codigo"] == "tope_alcanzado"
        for x in abiertas:
            x.close()

    asyncio.run(_con_servidor(corto, caso))


def test_socket_0600_en_directorio_0700(corto):
    async def caso(ruta, _llamadas, _srv):
        assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(ruta.parent).st_mode) == 0o700

    asyncio.run(_con_servidor(corto, caso))


def test_directorio_symlink_se_rechaza(corto):
    real = corto / "real"
    real.mkdir(mode=0o700)
    (corto / "colmena").symlink_to(real)

    async def caso():
        srv = mcp_canal.ServidorMcp(lambda: [], {}, uid=UID)
        with pytest.raises(PermissionError):
            await srv.abrir(corto / "colmena" / "mcp.sock")

    asyncio.run(caso())


# --- Cliente stdio sin backend (CA22) ---

def test_mcp_sin_socket_arranca_y_cada_herramienta_da_colmena_no_disponible(corto):
    srv = mcp_colmena.ServidorStdio(corto / "no-existe.sock")
    init = srv.manejar({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t"}}})
    assert init["result"]["serverInfo"]["name"] == "colmena"
    herramientas = srv.manejar({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    nombres = {h["name"] for h in herramientas}
    assert {"colmena_sesiones", "colmena_leer_sesion", "colmena_abrir", "colmena_estado_pedido"} <= nombres
    for h in herramientas:
        res = srv.manejar({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": h["name"], "arguments": {}}})["result"]
        assert res["isError"] is True
        assert res["structuredContent"]["codigo"] == "colmena_no_disponible"


def test_mcp_como_proceso_responde_sin_backend(corto):
    entrada = "\n".join(json.dumps(m) for m in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "colmena_sesiones", "arguments": {}}},
    )) + "\n"
    out = subprocess.run([sys.executable, "-m", "orquestador.mcp_colmena", "--socket", str(corto / "no.sock")],
                         input=entrada, capture_output=True, text=True, timeout=20)
    lineas = [json.loads(x) for x in out.stdout.splitlines() if x.strip()]
    assert [x["id"] for x in lineas] == [1, 2]
    assert lineas[1]["result"]["structuredContent"]["codigo"] == "colmena_no_disponible"


def _props(esquema):
    for nombre, p in esquema.get("properties", {}).items():
        yield nombre, p
        if p.get("type") == "array":
            yield from _props(p["items"])


def test_todo_parametro_tiene_description():
    from orquestador.mcp_colmena import HERRAMIENTAS
    sin = [(h[0], n) for h in HERRAMIENTAS for n, p in _props(h[4]) if not p.get("description")]
    assert sin == []


def test_anotaciones_de_lectura_y_destructivas():
    from orquestador.mcp_colmena import HERRAMIENTAS, ServidorStdio
    defs = {h[0]: ServidorStdio._definicion(h) for h in HERRAMIENTAS}
    for n in ("colmena_sesiones", "colmena_leer_sesion", "colmena_pedidos", "colmena_buscar_memoria",
              "colmena_estado_pedido"):
        assert defs[n]["annotations"]["readOnlyHint"] is True
    assert defs["colmena_cerrar"]["annotations"] == {"readOnlyHint": False, "destructiveHint": True,
                                                     "openWorldHint": False}
    for n in ("colmena_abrir", "colmena_cursor", "colmena_mensaje", "colmena_programar", "colmena_tarea_ticket"):
        assert defs[n]["annotations"]["readOnlyHint"] is False
        assert defs[n]["annotations"]["destructiveHint"] is False


def test_descripciones_de_herramientas_dicen_cuando_usar():
    from orquestador.mcp_colmena import _POR_NOMBRE
    abrir, cerrar = _POR_NOMBRE["colmena_abrir"][3], _POR_NOMBRE["colmena_cerrar"][3]
    assert "ruta absoluta" in abrir and "repo de Colmena" in abrir and "Devuelve" in abrir
    assert "pida explícitamente" in cerrar and "Devuelve" in cerrar
