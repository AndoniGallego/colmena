import asyncio
import contextlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from orquestador.enchufe.base import NoDisponible, NoExiste
from orquestador.enchufe.guardian import ClienteGuardian
from orquestador.enchufe.mux import Mux
from orquestador.enchufe.fake import FakeTerminales
from orquestador.guardian.protocolo import VERSION
from tests.conftest import make_snapshot


class GuardianVivoFalso:
    def __init__(self, sesion_id: str = "g1:p1", *, con_fotos: bool = True, texto_leer: str = "a\nb"):
        self.sesion_id = sesion_id
        self.con_fotos = con_fotos
        self.texto_leer = texto_leer
        self.sesiones_tablero = [sesion_id]
        self.eventos: asyncio.Queue[dict | None] = asyncio.Queue()
        self.cerrado = asyncio.Event()

    async def atender(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async def emisor() -> None:
            while True:
                ev = await self.eventos.get()
                if ev is None:
                    return
                writer.write(json.dumps(ev, ensure_ascii=False).encode() + b"\n")
                await writer.drain()

        emitir = asyncio.create_task(emisor())
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                msg = json.loads(raw.decode())
                pid = msg["id"]
                op = msg["op"]
                if op == "hola":
                    writer.write(json.dumps({"id": pid, "ok": True, "res": {"protocolo": VERSION}}).encode() + b"\n")
                elif op == "suscribir":
                    if self.con_fotos:
                        fotos = {
                            self.sesion_id: {
                                "columnas": 80,
                                "filas": 24,
                                "cursor": [2, 1],
                                "cursor_visible": True,
                                "historial": ["h1"],
                                "pantalla": ["p1"],
                            }
                        }
                        res = {"fotos": fotos}
                    else:
                        res = {}
                    writer.write(json.dumps({"id": pid, "ok": True, "res": res}).encode() + b"\n")
                elif op == "leer":
                    writer.write(
                        json.dumps({"id": pid, "ok": True, "res": {"texto": self.texto_leer}}).encode() + b"\n"
                    )
                elif op == "tablero":
                    sesiones = [{"id": s} for s in self.sesiones_tablero]
                    writer.write(json.dumps({"id": pid, "ok": True, "res": {"sesiones": sesiones}}).encode() + b"\n")
                else:
                    writer.write(
                        json.dumps({"id": pid, "ok": False, "error": {"codigo": "invalido", "mensaje": "x"}}).encode()
                        + b"\n"
                    )
                await writer.drain()
        finally:
            self.eventos.put_nowait(None)
            emitir.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await emitir
            self.cerrado.set()
            writer.close()
            await writer.wait_closed()

    def empujar(self, ev: dict) -> None:
        self.eventos.put_nowait(ev)


@pytest.fixture
def sock_dir():
    d = tempfile.mkdtemp(dir="/tmp", prefix="gv-")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _cliente(ruta: Path, **kw) -> ClienteGuardian:
    return ClienteGuardian(ruta, timeout=2.0, **kw)


async def _con_servidor(fake: GuardianVivoFalso, ruta: Path, prueba):
    srv = await asyncio.start_unix_server(fake.atender, path=str(ruta))
    try:
        await prueba(fake, ruta)
    finally:
        srv.close()
        await srv.wait_closed()


def test_foto_con_fotos(sock_dir):
    fake = GuardianVivoFalso()
    ruta = sock_dir / "g.sock"

    async def prueba(f, path):
        c = _cliente(path)
        canal = await c.abrir_vivo(f.sesion_id)
        assert canal.foto.columnas == 80 and canal.foto.pantalla == ("p1",)
        await canal.cerrar()

    asyncio.run(_con_servidor(fake, ruta, prueba))


def test_fallback_sin_fotos(sock_dir):
    fake = GuardianVivoFalso(con_fotos=False, texto_leer="uno\ndos")
    ruta = sock_dir / "b.sock"

    async def prueba(_f, path):
        c = _cliente(path)
        canal = await c.abrir_vivo("g1:p1", tamano=(100, 30))
        assert canal.foto.columnas == 100 and canal.foto.filas == 30
        assert canal.foto.pantalla == ("uno", "dos")
        await canal.cerrar()

    asyncio.run(_con_servidor(fake, ruta, prueba))


def test_no_existe(sock_dir):
    ruta = sock_dir / "ne.sock"

    async def atender(reader, writer):
        raw = await reader.readline()
        msg = json.loads(raw.decode())
        if msg["op"] == "hola":
            writer.write(json.dumps({"id": msg["id"], "ok": True, "res": {"protocolo": VERSION}}).encode() + b"\n")
            await writer.drain()
        raw = await reader.readline()
        msg = json.loads(raw.decode())
        writer.write(
            json.dumps(
                {"id": msg["id"], "ok": False, "error": {"codigo": "no_existe", "mensaje": "no está"}}
            ).encode()
            + b"\n"
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def prueba(_f, path):
        c = _cliente(path)
        with pytest.raises(NoExiste):
            await c.abrir_vivo("g1:p1")

    async def main():
        srv = await asyncio.start_unix_server(atender, path=str(ruta))
        try:
            await prueba(None, ruta)
        finally:
            srv.close()
            await srv.wait_closed()

    asyncio.run(main())


def test_socket_inexistente(sock_dir):
    async def run():
        c = _cliente(sock_dir / "nada.sock")
        with pytest.raises(NoDisponible):
            await c.abrir_vivo("g1:p1")

    asyncio.run(run())


def test_eventos_traducidos(sock_dir):
    fake = GuardianVivoFalso()
    ruta = sock_dir / "ev.sock"

    async def prueba(f, path):
        c = _cliente(path)
        canal = await c.abrir_vivo(f.sesion_id)
        f.empujar({"evento": "salida", "sesion": "g9:p9", "texto": "ignorar", "seq": 1})
        f.empujar({"evento": "salida", "sesion": f.sesion_id, "texto": "hola", "seq": 2})
        ev = await canal.__anext__()
        assert ev == {"tipo": "salida", "texto": "hola"}
        f.empujar({"evento": "termino", "sesion": f.sesion_id, "codigo": 3, "seq": 3})
        ev2 = await canal.__anext__()
        assert ev2 == {"tipo": "termino", "codigo": 3}
        f.empujar({"evento": "vivo_cortado", "sesion": f.sesion_id, "seq": 4})
        ev3 = await canal.__anext__()
        assert ev3 == {"tipo": "desfasado"}
        await canal.cerrar()

    asyncio.run(_con_servidor(fake, ruta, prueba))


def test_tablero_cerrada(sock_dir):
    fake = GuardianVivoFalso()
    fake.sesiones_tablero = []
    ruta = sock_dir / "tc.sock"

    async def prueba(f, path):
        c = _cliente(path)
        canal = await c.abrir_vivo(f.sesion_id)
        f.empujar({"evento": "tablero", "seq": 1})
        ev = await asyncio.wait_for(canal.__anext__(), 2)
        assert ev == {"tipo": "cerrada"}
        await canal.cerrar()

    asyncio.run(_con_servidor(fake, ruta, prueba))


def test_tablero_sigue(sock_dir):
    fake = GuardianVivoFalso()
    ruta = sock_dir / "ts.sock"

    async def prueba(f, path):
        c = _cliente(path)
        canal = await c.abrir_vivo(f.sesion_id)
        f.empujar({"evento": "tablero", "seq": 1})
        f.empujar({"evento": "salida", "sesion": f.sesion_id, "texto": "siguiente", "seq": 2})
        ev = await asyncio.wait_for(canal.__anext__(), 2)
        assert ev == {"tipo": "salida", "texto": "siguiente"}
        await canal.cerrar()

    asyncio.run(_con_servidor(fake, ruta, prueba))


def test_eof_caido(sock_dir):
    ruta = sock_dir / "eof.sock"

    async def atender(reader, writer):
        raw = await reader.readline()
        msg = json.loads(raw.decode())
        if msg["op"] == "hola":
            writer.write(json.dumps({"id": msg["id"], "ok": True, "res": {"protocolo": VERSION}}).encode() + b"\n")
            await writer.drain()
        raw = await reader.readline()
        msg = json.loads(raw.decode())
        writer.write(json.dumps({"id": msg["id"], "ok": True, "res": {"fotos": {}}}).encode() + b"\n")
        await writer.drain()
        raw = await reader.readline()
        msg = json.loads(raw.decode())
        writer.write(json.dumps({"id": msg["id"], "ok": True, "res": {"texto": "x"}}).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def prueba(_f, path):
        c = _cliente(path)
        canal = await c.abrir_vivo("g1:p1")
        ev = await canal.__anext__()
        assert ev == {"tipo": "caido"}
        with pytest.raises(StopAsyncIteration):
            await canal.__anext__()

    async def main():
        srv = await asyncio.start_unix_server(atender, path=str(ruta))
        try:
            await prueba(None, ruta)
        finally:
            srv.close()
            await srv.wait_closed()

    asyncio.run(main())


def test_cerrar_cierra_socket(sock_dir):
    fake = GuardianVivoFalso()
    ruta = sock_dir / "cc.sock"

    async def prueba(f, path):
        c = _cliente(path)
        canal = await c.abrir_vivo(f.sesion_id)
        await canal.cerrar()
        await asyncio.wait_for(f.cerrado.wait(), 2)

    asyncio.run(_con_servidor(fake, ruta, prueba))


def test_mux_abrir_vivo():
    fake = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)

    async def run():
        mux = Mux((fake,))
        with pytest.raises(NoExiste):
            await mux.abrir_vivo("w1:p1")
        mux2 = Mux(())
        with pytest.raises(NoDisponible):
            await mux2.abrir_vivo("g1:p1")

    asyncio.run(run())
