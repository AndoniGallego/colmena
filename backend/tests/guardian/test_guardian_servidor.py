import asyncio
import json

import pytest

from orquestador.guardian.nucleo import Escucha
from orquestador.guardian.protocolo import INTERNO, INVALIDO, MAX_LINEA, NO_EXISTE, ErrorProtocolo
from orquestador.guardian.servidor import ServidorGuardian


class _WriterFalso:
    def __init__(self, *, drenar: asyncio.Event | None = None) -> None:
        self.buf = bytearray()
        self._cerrando = False
        self._drenar = drenar or asyncio.Event()
        if drenar is None:
            self._drenar.set()

    def write(self, data: bytes) -> None:
        self.buf.extend(data)

    async def drain(self) -> None:
        await self._drenar.wait()

    def is_closing(self) -> bool:
        return self._cerrando

    def close(self) -> None:
        self._cerrando = True

    async def wait_closed(self) -> None:
        return None

    def get_extra_info(self, _nombre: str, default=None):
        return default


class GuardianFalso:
    def __init__(self) -> None:
        self._seq = 0
        self._escuchas: list[Escucha] = []
        self.bloqueo_lento = asyncio.Event()
        self.bloqueo_lento.set()
        self.apagado_llamado = False

    @property
    def seq(self) -> int:
        return self._seq

    def tablero(self) -> dict:
        return {"revision": 0, "espacios": [], "lineas": [], "sesiones": []}

    async def arrancar_claude(
        self, sesion_id: str, nombre: str, resume: str | None = None
    ) -> dict:
        await self.bloqueo_lento.wait()
        return {"estado": "idle", "listo": True}

    def escuchar(self, cb, salida=()):
        esc = Escucha(_cb=cb, salida=set(salida))
        self._escuchas.append(esc)
        return esc

    def emitir(self, evento: dict) -> None:
        self._seq = evento.get("seq", self._seq + 1)
        for esc in self._escuchas:
            if esc._cerrada:
                continue
            if evento.get("evento") == "salida":
                sid = evento.get("sesion")
                if sid not in esc.salida:
                    continue
            esc._cb(evento)

    def foto(self, sesion_id: str) -> dict:
        if sesion_id == "g999:p999":
            raise ErrorProtocolo(NO_EXISTE, sesion_id)
        return {
            "columnas": 80,
            "filas": 24,
            "cursor": [0, 0],
            "cursor_visible": True,
            "historial": [],
            "pantalla": [""] * 24,
        }


def _lineas(buf: bytearray) -> list[dict]:
    out = []
    for raw in bytes(buf).split(b"\n"):
        if not raw.strip():
            continue
        out.append(json.loads(raw))
    return out


async def _atender_uno(servidor: ServidorGuardian, pedidos: bytes) -> tuple[bytearray, asyncio.Task]:
    reader = asyncio.StreamReader()
    reader.feed_data(pedidos)
    reader.feed_eof()
    writer = _WriterFalso()
    tarea = asyncio.create_task(servidor.atender(reader, writer))
    await tarea
    return writer.buf, tarea


def test_hola():
    g = GuardianFalso()
    srv = ServidorGuardian(g, "9.9.9", lambda: None)

    async def run():
        buf, _ = await _atender_uno(
            srv,
            (json.dumps({"id": 1, "op": "hola", "args": {}}) + "\n").encode(),
        )
        msgs = _lineas(buf)
        assert len(msgs) == 1
        assert msgs[0]["ok"] is True
        assert msgs[0]["res"]["guardian"] == "9.9.9"
        assert "pid" in msgs[0]["res"]

    asyncio.run(run())


def test_respuesta_con_id():
    g = GuardianFalso()
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        buf, _ = await _atender_uno(
            srv,
            (json.dumps({"id": 2, "op": "tablero", "args": {}}) + "\n").encode(),
        )
        msgs = _lineas(buf)
        assert msgs[0]["id"] == 2 and msgs[0]["ok"] is True

    asyncio.run(run())


def test_op_invalida():
    g = GuardianFalso()
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        buf, _ = await _atender_uno(
            srv,
            (json.dumps({"id": 3, "op": "no_existe", "args": {}}) + "\n").encode(),
        )
        msgs = _lineas(buf)
        assert msgs[0]["ok"] is False
        assert msgs[0]["error"]["codigo"] == INVALIDO

    asyncio.run(run())


def test_json_sin_id_cierra():
    g = GuardianFalso()
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        buf, _ = await _atender_uno(srv, b"{}\n")
        assert len(buf) == 0

    asyncio.run(run())


def test_concurrente_lento():
    g = GuardianFalso()
    g.bloqueo_lento.clear()
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        reader = asyncio.StreamReader()
        writer = _WriterFalso()
        pedido_lento = json.dumps(
            {"id": 1, "op": "arrancar_claude", "args": {"sesion_id": "g1:p1", "nombre": "x"}}
        ) + "\n"
        pedido_rapido = json.dumps({"id": 2, "op": "tablero", "args": {}}) + "\n"
        reader.feed_data((pedido_lento + pedido_rapido).encode())
        tarea = asyncio.create_task(srv.atender(reader, writer))
        await asyncio.sleep(0.05)
        g.bloqueo_lento.set()
        await asyncio.sleep(0.05)
        reader.feed_eof()
        await tarea
        msgs = _lineas(writer.buf)
        ids = [m["id"] for m in msgs if "id" in m]
        assert ids.index(2) < ids.index(1)

    asyncio.run(run())


def test_error_protocolo():
    g = GuardianFalso()

    async def arrancar_claude(sesion_id, nombre, resume=None):
        raise ErrorProtocolo("no_existe", "sesión", 5)

    g.arrancar_claude = arrancar_claude  # type: ignore[method-assign]
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        buf, _ = await _atender_uno(
            srv,
            (
                json.dumps(
                    {
                        "id": 5,
                        "op": "arrancar_claude",
                        "args": {"sesion_id": "g1:p1", "nombre": "x"},
                    }
                )
                + "\n"
            ).encode(),
        )
        msgs = _lineas(buf)
        assert msgs[0]["error"]["codigo"] == "no_existe"

    asyncio.run(run())


def test_interno_sin_detalle():
    g = GuardianFalso()

    def tablero():
        raise RuntimeError("secreto")

    g.tablero = tablero  # type: ignore[method-assign]
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        buf, _ = await _atender_uno(
            srv,
            (json.dumps({"id": 6, "op": "tablero", "args": {}}) + "\n").encode(),
        )
        msgs = _lineas(buf)
        assert msgs[0]["error"]["codigo"] == INTERNO
        assert msgs[0]["error"]["mensaje"] == "error interno"
        assert "secreto" not in msgs[0]["error"]["mensaje"]

    asyncio.run(run())


def test_vivo_cortado():
    g = GuardianFalso()
    drenar = asyncio.Event()
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        reader = asyncio.StreamReader()
        writer = _WriterFalso(drenar=drenar)
        sus = json.dumps(
            {"id": 1, "op": "suscribir", "args": {"salida": ["g1:p1", "g1:p2"]}}
        ) + "\n"
        reader.feed_data(sus.encode())
        tarea = asyncio.create_task(srv.atender(reader, writer))
        await asyncio.sleep(0.05)
        relleno = "x" * (MAX_LINEA - 200)
        g.emitir({"evento": "salida", "sesion": "g1:p1", "texto": relleno, "seq": 99})
        g.emitir({"evento": "salida", "sesion": "g1:p2", "texto": "y" * 500, "seq": 100})
        drenar.set()
        reader.feed_eof()
        await tarea
        msgs = _lineas(writer.buf)
        cortados = [m for m in msgs if m.get("evento") == "vivo_cortado"]
        assert len(cortados) == 2
        sesiones = {m["sesion"] for m in cortados}
        assert sesiones == {"g1:p1", "g1:p2"}
        assert all(m["seq"] == 100 for m in cortados)

    asyncio.run(run())


def test_apagar_ordenado():
    g = GuardianFalso()
    llamado = asyncio.Event()
    srv = ServidorGuardian(g, "1", llamado.set)

    async def run():
        buf, _ = await _atender_uno(
            srv,
            (json.dumps({"id": 7, "op": "apagar_ordenado", "args": {}}) + "\n").encode(),
        )
        msgs = _lineas(buf)
        assert msgs[0]["ok"] is True
        await asyncio.wait_for(llamado.wait(), 1.0)

    asyncio.run(run())


def test_suscribir_sin_foto():
    g = GuardianFalso()
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        reader = asyncio.StreamReader()
        writer = _WriterFalso()
        pedido = json.dumps(
            {"id": 10, "op": "suscribir", "args": {"salida": ["g1:p1"]}}
        ) + "\n"
        reader.feed_data(pedido.encode())
        reader.feed_eof()
        await srv.atender(reader, writer)
        msgs = _lineas(writer.buf)
        assert msgs[0]["ok"] is True
        assert "fotos" not in msgs[0]["res"]
        assert len(g._escuchas) == 1

    asyncio.run(run())


def test_suscribir_con_foto():
    g = GuardianFalso()
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        buf, _ = await _atender_uno(
            srv,
            (
                json.dumps(
                    {
                        "id": 11,
                        "op": "suscribir",
                        "args": {"salida": ["g1:p1", "g1:p2"], "foto": True},
                    }
                )
                + "\n"
            ).encode(),
        )
        msgs = _lineas(buf)
        assert msgs[0]["ok"] is True
        fotos = msgs[0]["res"]["fotos"]
        assert set(fotos.keys()) == {"g1:p1", "g1:p2"}
        assert fotos["g1:p1"]["filas"] == 24

    asyncio.run(run())


def test_suscribir_foto_id_inexistente_no_registra_escucha():
    g = GuardianFalso()
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        reader = asyncio.StreamReader()
        writer = _WriterFalso()
        sus_ok = json.dumps(
            {"id": 12, "op": "suscribir", "args": {"salida": ["g1:p1"]}}
        ) + "\n"
        sus_fail = json.dumps(
            {
                "id": 13,
                "op": "suscribir",
                "args": {"salida": ["g1:p1", "g999:p999"], "foto": True},
            }
        ) + "\n"
        reader.feed_data((sus_ok + sus_fail).encode())
        tarea = asyncio.create_task(srv.atender(reader, writer))
        await asyncio.sleep(0.05)
        reader.feed_eof()
        await tarea
        msgs = _lineas(writer.buf)
        ok = next(m for m in msgs if m.get("id") == 12)
        fail = next(m for m in msgs if m.get("id") == 13)
        assert ok["ok"] is True
        assert fail["ok"] is False
        assert fail["error"]["codigo"] == NO_EXISTE
        assert len(g._escuchas) == 1
        assert g._escuchas[0].salida == {"g1:p1"}

    asyncio.run(run())


def test_suscribir_foto_invalido():
    g = GuardianFalso()
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        buf, _ = await _atender_uno(
            srv,
            (
                json.dumps(
                    {"id": 14, "op": "suscribir", "args": {"salida": [], "foto": 1}}
                )
                + "\n"
            ).encode(),
        )
        msgs = _lineas(buf)
        assert msgs[0]["ok"] is False
        assert msgs[0]["error"]["codigo"] == INVALIDO
        assert msgs[0]["error"]["mensaje"] == "foto inválido"
        assert len(g._escuchas) == 0

    asyncio.run(run())


def test_protocolo_modo_invalido():
    g = GuardianFalso()
    llamadas = []

    async def arrancar_claude(sesion_id, nombre, resume=None, modo=None):
        llamadas.append(modo)
        return {"estado": "idle", "listo": True, "modo": modo}

    g.arrancar_claude = arrancar_claude  # type: ignore[method-assign]
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        pedidos = b""
        for i, modo in enumerate(["auto", "bypassPermissions", 3, "acceptEdits"], start=1):
            pedidos += (json.dumps({"id": i, "op": "arrancar_claude",
                                    "args": {"sesion_id": "g1:p1", "nombre": "x", "modo": modo}}) + "\n").encode()
        buf, _ = await _atender_uno(srv, pedidos)
        msgs = _lineas(buf)
        assert len(msgs) == 4
        assert all(m["error"]["codigo"] == INVALIDO for m in msgs)
        assert llamadas == []

    asyncio.run(run())


def test_respuesta_trae_eco_del_modo():
    g = GuardianFalso()
    llamadas = []

    async def arrancar_claude(sesion_id, nombre, resume=None, modo=None):
        llamadas.append(modo)
        return {"estado": "idle", "listo": True, "modo": modo}

    g.arrancar_claude = arrancar_claude  # type: ignore[method-assign]
    srv = ServidorGuardian(g, "1", lambda: None)

    async def run():
        pedidos = (json.dumps({"id": 1, "op": "arrancar_claude",
                               "args": {"sesion_id": "g1:p1", "nombre": "x", "modo": "default"}}) + "\n"
                   + json.dumps({"id": 2, "op": "arrancar_claude",
                                 "args": {"sesion_id": "g1:p1", "nombre": "x"}}) + "\n").encode()
        buf, _ = await _atender_uno(srv, pedidos)
        msgs = {m["id"]: m for m in _lineas(buf)}
        assert msgs[1]["res"]["modo"] == "default"
        assert llamadas == ["default", None]

    asyncio.run(run())
