import asyncio
import logging

import pytest
from conftest import FakeHerdr
from orquestador.enchufe.herdr import HerdrError
from orquestador.enchufe.base import Ilegible, NoDisponible
from orquestador.enchufe.herdr import AdaptadorHerdr

async def _siguiente(it, t=1.0):
    return await asyncio.wait_for(it.__anext__(), t)

def test_poll_emite_tablero_cada_intervalo():
    async def escenario():
        it = AdaptadorHerdr(FakeHerdr(), poll=0.01).suscribir()
        ev = await _siguiente(it)
        assert (ev.tipo, ev.datos["motivo"], ev.datos["via"]) == ("tablero", "poll", "polling")
        await it.aclose()
    asyncio.run(escenario())

def test_caido_y_volvio_una_sola_vez():
    async def escenario():
        fh = FakeHerdr()
        ad = AdaptadorHerdr(fh, poll=60)
        it = ad.suscribir()
        await ad.tablero()
        fh.caido = True
        for _ in range(2):
            try:
                await ad.tablero()
            except NoDisponible:
                pass
        assert (await _siguiente(it)).tipo == "caido"
        fh.caido = False
        t = await ad.tablero()
        assert (await _siguiente(it)).tipo == "volvio"
        assert {s.id for s in t.sesiones} == {"w1:p1", "w2:p1", "w2:p9"}
        await it.aclose()
    asyncio.run(escenario())

class SocketFalso(FakeHerdr):
    supports_socket = True
    def __init__(self, eventos, *, resuscribio=None):
        super().__init__()
        self.eventos, self.suscripciones = eventos, []
        self.resuscribio = resuscribio or asyncio.Event()
    async def events(self, pane_ids, idle_timeout):
        self.suscripciones.append(list(pane_ids))
        for ev in self.eventos.pop(0) if self.eventos else []:
            yield ev
        self.resuscribio.set()
        await asyncio.sleep(3600)

def test_traduce_eventos_del_socket():
    async def escenario():
        fh = SocketFalso([[None, {"event": "pane.agent_status_changed", "pane_id": "w1:p1", "agent_status": "working"},
                           {"event": "pane.exited", "pane_id": "w1:p1"}, {"event": "tab.created"}]])
        ad = AdaptadorHerdr(fh, poll=60)
        await ad.tablero()
        it = ad.suscribir()
        tipos = [(e.tipo, e.sesion_id, e.estado) for e in [await _siguiente(it) for _ in range(4)]]
        assert tipos == [("tablero", None, None), ("estado", "w1:p1", "working"), ("termino", "w1:p1", None), ("tablero", None, None)]
        assert fh.suscripciones[0] == ["w1:p1", "w2:p9"]
        await it.aclose()
    asyncio.run(escenario())

def test_socket_se_resuscribe_si_cambian_las_sesiones():
    async def escenario():
        resuscribio = asyncio.Event()
        fh = SocketFalso([[{"event": "pane.created"}], []], resuscribio=resuscribio)
        ad = AdaptadorHerdr(fh, poll=60)
        await ad.tablero()
        it = ad.suscribir()
        fh.current["agents"] = [a for a in fh.current["agents"] if a["pane_id"] != "w2:p9"]
        await ad.tablero()
        await _siguiente(it)
        await asyncio.wait_for(resuscribio.wait(), 1.0)
        assert fh.suscripciones[-1] == ["w1:p1"]
        await it.aclose()
    asyncio.run(escenario())


class SocketQueFallaUnaVez(SocketFalso):
    def __init__(self, eventos_tras_fallo):
        super().__init__(eventos_tras_fallo)
        self._intentos = 0

    async def events(self, pane_ids, idle_timeout):
        self._intentos += 1
        if self._intentos == 1:
            raise HerdrError("socket roto")
        async for ev in super().events(pane_ids, idle_timeout):
            yield ev


def test_socket_reintenta_tras_fallo():
    async def escenario():
        fh = SocketQueFallaUnaVez([[{"event": "tab.created"}]])
        ad = AdaptadorHerdr(fh, poll=0.01)
        await ad.tablero()
        it = ad.suscribir()
        ev_poll = await _siguiente(it, 2.0)
        assert (ev_poll.tipo, ev_poll.datos.get("motivo"), ev_poll.datos.get("via")) == (
            "tablero",
            "poll",
            "polling",
        )
        ev_socket = await _siguiente(it, 2.0)
        assert ev_socket.datos.get("via") == "socket"
        assert fh._intentos >= 2
        await it.aclose()

    asyncio.run(escenario())


def test_cancelar_consumidor_en_anext_limpia_colas_y_fuente():
    async def escenario():
        ad = AdaptadorHerdr(FakeHerdr(), poll=60)
        it = ad.suscribir()
        tarea = asyncio.create_task(it.__anext__())

        async def cancelar():
            await asyncio.sleep(0)
            tarea.cancel()

        asyncio.create_task(cancelar())
        with pytest.raises(asyncio.CancelledError):
            await tarea
        await asyncio.sleep(0)
        assert ad._colas == set()
        assert ad._tarea_fuente is None or ad._tarea_fuente.done()

    asyncio.run(escenario())


def test_aclose_despierta_anext_pendiente():
    async def escenario():
        ad = AdaptadorHerdr(FakeHerdr(), poll=60)
        it = ad.suscribir()
        tarea = asyncio.create_task(it.__anext__())
        await asyncio.sleep(0)
        await it.aclose()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(tarea, 1.0)

    asyncio.run(escenario())


class FakeHerdrSnapshotInvalido(FakeHerdr):
    async def snapshot(self):
        raise ValueError("json inválido")


def test_ilegible_en_snapshot_no_emite_caido():
    async def escenario():
        ad = AdaptadorHerdr(FakeHerdrSnapshotInvalido(), poll=60)
        it = ad.suscribir()
        with pytest.raises(Ilegible):
            await ad.tablero()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(it.__anext__(), 0.05)
        await it.aclose()

    asyncio.run(escenario())


class SinSocket:
    supports_socket = False


def test_fuente_muerta_no_cuelga_la_suscripcion(caplog):
    async def escenario():
        ad = AdaptadorHerdr(SinSocket(), poll=0.0)
        ad._empujar_a_colas = lambda ev: (_ for _ in ()).throw(RuntimeError("boom"))
        sub = ad.suscribir()
        with caplog.at_level(logging.WARNING):
            try:
                await asyncio.wait_for(sub.__anext__(), 2)
                raise AssertionError("debía terminar")
            except StopAsyncIteration:
                pass
        assert "boom" in caplog.text

    asyncio.run(escenario())


def test_events_se_cierra_al_resuscribir():
    cerrados: list[int] = []
    estado: dict = {"cerrados_al_resuscribir": None}
    sync = asyncio.Event()
    segunda_llamada = asyncio.Event()

    class ConSocket:
        supports_socket = True
        llamadas = 0

        async def events(self, ids, seguridad):
            ConSocket.llamadas += 1
            n = ConSocket.llamadas
            try:
                if n == 1:
                    yield {"type": "pane.agent_status_changed", "pane_id": "w1:p1"}
                    await sync.wait()
                    yield {"type": "pane.agent_status_changed", "pane_id": "w1:p2"}
                else:
                    estado["cerrados_al_resuscribir"] = list(cerrados)
                    segunda_llamada.set()
                    yield {"type": "pane.agent_status_changed", "pane_id": "w1:p1"}
            finally:
                cerrados.append(n)

    async def escenario():
        ad = AdaptadorHerdr(ConSocket(), poll=0.0)
        sub = ad.suscribir()
        ad._ids_agente = ["w1:p1"]
        await asyncio.wait_for(sub.__anext__(), 2)
        ad._ids_agente = ["w1:p1", "w1:p2"]
        sync.set()
        await asyncio.wait_for(sub.__anext__(), 2)
        await asyncio.wait_for(segunda_llamada.wait(), 2)
        await sub.aclose()

    asyncio.run(escenario())
    assert estado["cerrados_al_resuscribir"] == [1]


class ClienteConnectionRefused:
    supports_socket = True

    async def events(self, pane_ids, idle_timeout):
        raise ConnectionRefusedError("herdr no escucha")
        yield  # pragma: no cover


def test_events_connection_refused_degrada_a_polling():
    async def escenario():
        ad = AdaptadorHerdr(ClienteConnectionRefused(), poll=0.0)
        sub = ad.suscribir()
        ev = await asyncio.wait_for(sub.__anext__(), 2)
        assert (ev.tipo, ev.datos.get("motivo"), ev.datos.get("via")) == (
            "tablero",
            "poll",
            "polling",
        )
        ev2 = await asyncio.wait_for(sub.__anext__(), 2)
        assert ev2.datos.get("via") == "polling"
        await sub.aclose()

    asyncio.run(escenario())


def test_nueva_suscripcion_relanza_fuente_tras_muerte():
    async def escenario():
        ad = AdaptadorHerdr(SinSocket(), poll=0.0)
        original = ad._empujar_a_colas
        boom = {"hecho": False}

        def empujar(ev):
            if not boom["hecho"]:
                boom["hecho"] = True
                raise RuntimeError("boom en bucle")
            original(ev)

        ad._empujar_a_colas = empujar
        sub1 = ad.suscribir()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(sub1.__anext__(), 2)
        assert ad._tarea_fuente is not None and ad._tarea_fuente.done()

        sub2 = ad.suscribir()
        ev = await asyncio.wait_for(sub2.__anext__(), 2)
        assert (ev.tipo, ev.datos.get("motivo"), ev.datos.get("via")) == (
            "tablero",
            "poll",
            "polling",
        )
        assert ad._tarea_fuente is not None and not ad._tarea_fuente.done()
        await sub2.aclose()

    asyncio.run(escenario())
