import asyncio
import json
from pathlib import Path

import pytest

from orquestador.enchufe.guardian import ClienteGuardian
from orquestador.enchufe.base import Evento, NoDisponible, NoExiste, NoTomado, Tiempo, TerminalesError
from orquestador.enchufe.modelo import Tablero
from orquestador.estado_sesiones import EstadoSesiones
from orquestador.ganchos.mensaje import Ids, MensajeGancho
from orquestador.guardian.protocolo import MAX_LINEA, VERSION
from orquestador.guardian.servidor import ServidorGuardian
from tests.guardian.test_guardian_servidor import GuardianFalso


class _WriterTubo:
    def __init__(self, peer_reader: asyncio.StreamReader) -> None:
        self._peer = peer_reader
        self._cerrando = False

    def write(self, data: bytes) -> None:
        self._peer.feed_data(data)

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self._cerrando

    def close(self) -> None:
        self._cerrando = True
        self._peer.feed_eof()

    async def wait_closed(self) -> None:
        return None

    def get_extra_info(self, _nombre: str, default=None):
        return default


def _par_duplex() -> tuple[asyncio.StreamReader, _WriterTubo, asyncio.StreamReader, _WriterTubo]:
    ra = asyncio.StreamReader(limit=MAX_LINEA + 1)
    rb = asyncio.StreamReader(limit=MAX_LINEA + 1)
    return ra, _WriterTubo(rb), rb, _WriterTubo(ra)


class GuardianEnchufe(GuardianFalso):
    def __init__(self) -> None:
        super().__init__()
        self._texto_leer = ""
        self._tablero_dict = {
            "revision": 1,
            "espacios": [{"id": "g1", "nombre": "G", "numero": 1, "lineas": ["g1:t1"]}],
            "lineas": [{"id": "g1:t1", "espacio_id": "g1", "nombre": "L", "sesiones": ["g1:p2"]}],
            "sesiones": [
                {
                    "id": "g1:p2",
                    "linea_id": "g1:t1",
                    "espacio_id": "g1",
                    "programa": "claude",
                    "estado": "idle",
                    "claude_session_id": "uuid-1",
                    "cwd": "/tmp",
                    "titulo": "claude",
                }
            ],
        }

    def tablero(self) -> dict:
        return self._tablero_dict

    def leer(self, sesion_id: str, fuente="visible", formato="texto", lineas=None) -> str:
        return self._texto_leer

    async def mandar_prompt(self, sesion_id: str, texto: str) -> None:
        return None

    def proceso(self, sesion_id: str) -> dict:
        return {
            "pid": 42,
            "comando": "claude",
            "cwd": "/tmp",
            "es_claude": True,
            "argv": ["claude"],
            "grupo": 42,
            "shell_pid": 40,
        }


@pytest.fixture
def tubo_servidor():
    g = GuardianEnchufe()
    srv = ServidorGuardian(g, "1.0", lambda: None)
    cr, cw, sr, sw = _par_duplex()
    tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
    yield g, srv, cr, cw, tarea
    sw.close()
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        asyncio.get_event_loop().run_until_complete(tarea)


def _cliente(cr, cw, **kw) -> ClienteGuardian:
    async def conectar():
        return cr, cw

    return ClienteGuardian(Path("/tmp/no-importa.sock"), conectar=conectar, timeout=2.0, **kw)


def test_tablero_mapeo():
    g = GuardianEnchufe()
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw)
            estados = EstadoSesiones()
            estados.recibir(
                MensajeGancho("UserPromptSubmit", "g", Ids("g1:p2", None, None, None, "s"), {}),
                "g1:p2",
            )
            c.conectar_estados(estados)
            t = await c.tablero()
            assert t.espacios[0].numero == 1001
            s = t.sesiones[0]
            assert s.backend == "guardian" and s.es_agente and s.agente == "claude"
            assert s.claude_session_tipo == "id"
            assert s.estado == "working" and s.estado_fuente == "ganchos"
        finally:
            sw.close()
            tarea.cancel()
            with pytest.raises(asyncio.CancelledError):
                await tarea

    asyncio.run(run())


def test_errores_mapeados():
    g = GuardianEnchufe()

    async def mandar_prompt(sesion_id, texto):
        from orquestador.guardian.protocolo import ErrorProtocolo

        raise ErrorProtocolo("no_tomado", "el prompt quedó en la entrada")

    g.mandar_prompt = mandar_prompt  # type: ignore[method-assign]
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw)
            with pytest.raises(NoTomado, match="el prompt quedó"):
                await c.mandar_prompt("g1:p2", "hola")
        finally:
            sw.close()
            tarea.cancel()
            with pytest.raises(asyncio.CancelledError):
                await tarea

    asyncio.run(run())


def test_version_incompatible():
    async def mini_atender(reader: asyncio.StreamReader, writer: _WriterTubo) -> None:
        line = await reader.readline()
        req = json.loads(line)
        payload = json.dumps({"id": req["id"], "ok": True, "res": {"protocolo": 0}}) + "\n"
        writer.write(payload.encode())
        await writer.drain()
        writer.close()

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(mini_atender(sr, _WriterTubo(cr)))
        try:
            async def conectar():
                return cr, cw

            c = ClienteGuardian(Path("/x"), conectar=conectar, timeout=1.0)
            with pytest.raises(NoDisponible, match="incompatible"):
                await c.tablero()
        finally:
            sw.close()
            await tarea

    asyncio.run(run())


def test_reconexion_tras_caida():
    g = GuardianEnchufe()
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        c = _cliente(cr, cw)
        await c.tablero()
        sw.close()
        await asyncio.sleep(0.05)
        cr2, cw2, sr2, sw2 = _par_duplex()
        t2 = asyncio.create_task(srv.atender(sr2, _WriterTubo(cr2)))

        async def reconectar():
            return cr2, cw2

        c._conectar_fn = reconectar  # type: ignore[method-assign]
        await c.cerrar_enchufe()
        t = await c.tablero()
        assert t.sesiones[0].id == "g1:p2"
        sw2.close()
        tarea.cancel()
        t2.cancel()

    asyncio.run(run())


def test_mandar_prompt_gancho():
    g = GuardianEnchufe()
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw, espera_toma=2.0)
            estados = EstadoSesiones()
            c.conectar_estados(estados)

            async def mandar():
                await asyncio.sleep(0.05)
                c.al_gancho("g1:p2", "UserPromptSubmit")

            asyncio.create_task(mandar())
            r = await c.mandar_prompt("g1:p2", "hola mundo")
            assert r.tomado and r.via == "gancho"
        finally:
            sw.close()
            tarea.cancel()
            with pytest.raises(asyncio.CancelledError):
                await tarea

    asyncio.run(run())


def test_mandar_prompt_no_tomado_en_entrada():
    g = GuardianEnchufe()
    g._texto_leer = "❯ hola mundo en pantalla"
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw, espera_toma=0.05)
            with pytest.raises(NoTomado):
                await c.mandar_prompt("g1:p2", "hola mundo en pantalla")
        finally:
            sw.close()
            tarea.cancel()

    asyncio.run(run())


def test_mandar_prompt_via_pantalla():
    """Sin ❯ en pantalla (Claude todavía cargando) no se da por pegado."""
    g = GuardianEnchufe()
    g._texto_leer = "listo sin prompt"
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw, espera_toma=0.05)
            with pytest.raises(NoTomado):
                await c.mandar_prompt("g1:p2", "algo")
        finally:
            sw.close()
            tarea.cancel()

    asyncio.run(run())


def test_mandar_prompt_pantalla_con_prompt_sin_prefijo():
    """Con ❯ visible y sin el texto en la entrada se toma como enviado (Claude ocupado también muestra ❯)."""
    g = GuardianEnchufe()
    g._texto_leer = "● trabajando\n❯ "
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw, espera_toma=0.05)
            r = await c.mandar_prompt("g1:p2", "algo")
            assert r.tomado and r.via == "pantalla" and r.estado == "working"
        finally:
            sw.close()
            tarea.cancel()

    asyncio.run(run())


def test_esperar_gancho_y_tiempo():
    g = GuardianEnchufe()
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw)
            estados = EstadoSesiones()
            c.conectar_estados(estados)

            async def despertar():
                await asyncio.sleep(0.05)
                estados.recibir(
                    MensajeGancho("UserPromptSubmit", "g", Ids("g1:p2", None, None, None, "s"), {}),
                    "g1:p2",
                )
                c.al_gancho("g1:p2", "UserPromptSubmit")

            asyncio.create_task(despertar())
            assert await c.esperar("g1:p2", frozenset({"working"}), 2.0) == "working"
            with pytest.raises(Tiempo):
                await c.esperar("g1:p2", frozenset({"done"}), 0.1)
            with pytest.raises(NoExiste):
                await c.esperar("g9:p9", frozenset({"idle"}), 0.5)
        finally:
            sw.close()
            tarea.cancel()

    asyncio.run(run())


def test_suscripcion_eventos():
    g = GuardianEnchufe()
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        async def conectar():
            return cr, cw

        c = ClienteGuardian(
            Path("/x"),
            conectar=conectar,
            timeout=2.0,
            reintento=0.05,
            reintento_max=0.1,
        )
        sub = c.suscribir()
        vistos: list[Evento] = []

        async def consumir():
            async for ev in sub:
                vistos.append(ev)
                if ev.tipo == "estado" and ev.sesion_id == "g1:p2":
                    break

        t_con = asyncio.create_task(consumir())
        await asyncio.sleep(0.1)
        g.emitir({"evento": "estado", "sesion": "g1:p2", "estado": "working", "seq": 1})
        await asyncio.wait_for(t_con, 2.0)
        tipos = [e.tipo for e in vistos]
        assert "volvio" in tipos
        assert any(e.tipo == "estado" and e.estado == "working" for e in vistos)
        await sub.aclose()
        sw.close()
        tarea.cancel()

    asyncio.run(run())


def test_suscripcion_caido_volvio():
    g = GuardianEnchufe()
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cierres: list[_WriterTubo] = []

        async def conectar():
            cr, cw, sr, sw = _par_duplex()
            cierres.append(sw)
            asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
            return cr, cw

        c = ClienteGuardian(
            Path("/x"),
            conectar=conectar,
            timeout=1.0,
            reintento=0.05,
            reintento_max=0.1,
        )
        sub = c.suscribir()
        vistos: list[str] = []

        async def consumir():
            async for ev in sub:
                vistos.append(ev.tipo)
                if vistos.count("caido") >= 1 and vistos.count("volvio") >= 2:
                    break

        t_con = asyncio.create_task(consumir())
        await asyncio.sleep(0.08)
        if cierres:
            cierres[0].close()
        await asyncio.wait_for(t_con, 3.0)
        assert "caido" in vistos
        await sub.aclose()

    asyncio.run(run())


def test_suscripcion_via_mux_arranca_y_traduce_caido():
    from orquestador.enchufe import FakeTerminales, Mux
    from conftest import make_snapshot

    async def run():
        async def conectar():
            raise NoDisponible("guardián no disponible")

        c = ClienteGuardian(Path("/x"), conectar=conectar, reintento=0.05, reintento_max=0.1)
        m = Mux([FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr"), c])
        it = m.suscribir()
        try:
            ev = await asyncio.wait_for(it.__anext__(), 2.0)
            assert ev.tipo == "tablero" and ev.datos.get("motivo") == "seguridad"
        finally:
            await it.aclose()

    asyncio.run(run())


def _sesion_dict(g: GuardianEnchufe) -> dict:
    return g._tablero_dict["sesiones"][0]


def test_tablero_mapea_listo():
    g = GuardianEnchufe()
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw)
            assert (await c.tablero()).sesiones[0].listo is None
            _sesion_dict(g)["listo"] = True
            assert (await c.tablero()).sesiones[0].listo is True
            _sesion_dict(g)["listo"] = "si"
            assert (await c.tablero()).sesiones[0].listo is None
        finally:
            sw.close()
            tarea.cancel()

    asyncio.run(run())


def test_esperar_listo_no_sale_sin_registro():
    g = GuardianEnchufe()
    _sesion_dict(g)["listo"] = False
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw)
            c.conectar_estados(EstadoSesiones())
            with pytest.raises(Tiempo) as exc:
                await c.esperar_listo("g1:p2", 0.1)
            assert exc.value.listo_conocido is True
        finally:
            sw.close()
            tarea.cancel()

    asyncio.run(run())


def test_esperar_listo_despierta_con_evento():
    g = GuardianEnchufe()
    _sesion_dict(g)["listo"] = False
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        pares = [_par_duplex(), _par_duplex()]
        tareas = [asyncio.create_task(srv.atender(sr, _WriterTubo(cr))) for cr, _, sr, _ in pares]
        cola = [(cr, cw) for cr, cw, _, _ in pares]

        async def conectar():
            return cola.pop(0)

        c = ClienteGuardian(Path("/x"), conectar=conectar, timeout=2.0)
        c.conectar_estados(EstadoSesiones())
        await c.tablero()
        sub = c.suscribir()
        vistos: list[Evento] = []

        async def consumir():
            async for ev in sub:
                vistos.append(ev)

        t_con = asyncio.create_task(consumir())
        try:
            async def conectada():
                while not any(e.tipo == "volvio" for e in vistos):
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(conectada(), 2.0)

            async def avisar():
                await asyncio.sleep(0.1)
                _sesion_dict(g)["listo"] = True
                g.emitir({"evento": "estado", "sesion": "g1:p2", "estado": "idle", "seq": 1})

            asyncio.create_task(avisar())
            loop = asyncio.get_running_loop()
            inicio = loop.time()
            assert await c.esperar_listo("g1:p2", 0.8) == "guardian"
            assert loop.time() - inicio < 0.5
        finally:
            t_con.cancel()
            await sub.aclose()
            for _, _, _, sw in pares:
                sw.close()
            for t in tareas:
                t.cancel()

    asyncio.run(run())


def test_esperar_listo_respaldo_sessionstart():
    g = GuardianEnchufe()
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw)
            estados = EstadoSesiones()
            c.conectar_estados(estados)
            with pytest.raises(Tiempo) as exc:
                await c.esperar_listo("g1:p2", 0.1)
            assert exc.value.listo_conocido is False
            estados.recibir(
                MensajeGancho("SessionStart", "g", Ids("g1:p2", None, None, None, "s"), {}),
                "g1:p2",
            )
            assert await c.esperar_listo("g1:p2", 0.5) == "ganchos"
        finally:
            sw.close()
            tarea.cancel()

    asyncio.run(run())


def test_esperar_listo_terminada_no_disponible():
    g = GuardianEnchufe()
    _sesion_dict(g)["estado"] = "terminada"
    _sesion_dict(g)["listo"] = False
    srv = ServidorGuardian(g, "1.0", lambda: None)

    async def run():
        cr, cw, sr, sw = _par_duplex()
        tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
        try:
            c = _cliente(cr, cw)
            with pytest.raises(NoDisponible):
                await c.esperar_listo("g1:p2", 0.5)
            with pytest.raises(NoExiste):
                await c.esperar_listo("g9:p9", 0.5)
        finally:
            sw.close()
            tarea.cancel()

    asyncio.run(run())


async def _con_cliente(g, fn):
    srv = ServidorGuardian(g, "1.0", lambda: None)
    cr, cw, sr, sw = _par_duplex()
    tarea = asyncio.create_task(srv.atender(sr, _WriterTubo(cr)))
    try:
        await fn(_cliente(cr, cw))
    finally:
        sw.close()
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea


def test_arrancar_claude_manda_modo_y_exige_eco():
    g = GuardianEnchufe()
    pedidos: list = []
    cerrados: list = []

    async def arrancar_claude(sesion_id, nombre, resume=None, modo=None):
        pedidos.append(modo)
        return {"estado": "idle", "listo": True, "modo": modo}

    async def cerrar(objetivo_id):
        cerrados.append(objetivo_id)

    g.arrancar_claude = arrancar_claude  # type: ignore[method-assign]
    g.cerrar = cerrar  # type: ignore[method-assign]

    async def caso(c):
        await c.arrancar_claude("g1:p2", "x", modo="default")
        await c.arrancar_claude("g1:p2", "x")
        assert pedidos == ["default", None]
        assert cerrados == []

    asyncio.run(_con_cliente(g, caso))


def test_arrancar_claude_guardian_viejo_sin_eco_cierra_y_falla():
    g = GuardianEnchufe()
    cerrados: list = []

    async def arrancar_claude(sesion_id, nombre, resume=None, modo=None):
        return {"estado": "idle", "listo": True}

    async def cerrar(objetivo_id):
        cerrados.append(objetivo_id)

    g.arrancar_claude = arrancar_claude  # type: ignore[method-assign]
    g.cerrar = cerrar  # type: ignore[method-assign]

    async def caso(c):
        with pytest.raises(NoDisponible, match="modo seguro"):
            await c.arrancar_claude("g1:p2", "x", modo="default")
        assert cerrados == ["g1:p2"]

    asyncio.run(_con_cliente(g, caso))


def test_arrancar_claude_modo_que_relaja_no_se_manda():
    g = GuardianEnchufe()
    pedidos: list = []

    async def arrancar_claude(sesion_id, nombre, resume=None, modo=None):
        pedidos.append(modo)
        return {"estado": "idle", "listo": True, "modo": modo}

    g.arrancar_claude = arrancar_claude  # type: ignore[method-assign]

    async def caso(c):
        with pytest.raises(ValueError):
            await c.arrancar_claude("g1:p2", "x", modo="auto")
        assert pedidos == []

    asyncio.run(_con_cliente(g, caso))


def test_arrancar_claude_manda_dirs_extra_solo_con_copiloto():
    g = GuardianEnchufe()
    pedidos: list = []

    async def arrancar_claude(sesion_id, nombre, resume=None, modo=None, dirs_extra=None):
        pedidos.append((modo, dirs_extra))
        return {"estado": "idle", "listo": True, "modo": modo}

    g.arrancar_claude = arrancar_claude  # type: ignore[method-assign]

    async def caso(c):
        await c.arrancar_claude("g1:p2", "x", modo="copiloto", dirs_extra=["/a", "/b"])
        await c.arrancar_claude("g1:p2", "x", modo="copiloto")
        assert pedidos == [("copiloto", ["/a", "/b"]), ("copiloto", None)]
        with pytest.raises(ValueError):
            await c.arrancar_claude("g1:p2", "x", modo="default", dirs_extra=["/a"])
        with pytest.raises(ValueError):
            await c.arrancar_claude("g1:p2", "x", dirs_extra=["/a"])

    asyncio.run(_con_cliente(g, caso))
