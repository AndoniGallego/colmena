import asyncio
import copy
import logging

import pytest
from conftest import SID, make_snapshot
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.estado_sesiones import EstadoSesiones, aplicar_fuente
from orquestador.ganchos.mensaje import Ids, MensajeGancho


def ev(evento, **datos):
    return MensajeGancho(evento, "global", Ids(None, "w1:p1", None, None, SID), datos)


def agente(board):
    return board["workspaces"][0]["tabs"][0]["agents"][0]


def crudo_minimo():
    return {
        "workspaces": [
            {
                "id": "w1",
                "status": "working",
                "tabs": [{"agents": [{"pane_id": "w1:p1", "status": "working", "session_id": SID}]}],
            }
        ]
    }


@pytest.fixture
def hub(projects, tmp_path):
    from orquestador.replies import ReplyTracker
    from orquestador.state import StateStore

    h = BoardHub(FakeTerminales.desde_snapshot(make_snapshot("working"), poll=0.01), DigestService(projects))
    h.replies = ReplyTracker(StateStore(tmp_path))
    h.estados = EstadoSesiones()
    return h


@pytest.mark.parametrize(
    "fuente,esperado",
    [("herdr", "working"), ("ganchos_con_respaldo", "blocked"), ("ganchos", "blocked")],
)
def test_fuente_con_gancho(hub, fuente, esperado):
    async def esc():
        hub.fuente = lambda: fuente
        hub.estados.recibir(ev("PermissionRequest", tool_use_id="t1", tool_name="Bash"), "w1:p1")
        board = await hub.refresh()
        assert agente(board)["status"] == esperado
        assert board["workspaces"][0]["status"] == ("working" if fuente == "herdr" else "blocked")

    asyncio.run(esc())


@pytest.mark.parametrize("fuente,esperado", [("ganchos_con_respaldo", "working"), ("ganchos", "working")])
def test_sin_gancho(hub, fuente, esperado):
    async def esc():
        hub.fuente = lambda: fuente
        assert agente(await hub.refresh())["status"] == esperado

    asyncio.run(esc())


def test_cambio_de_fuente_sin_reiniciar_y_reaplicar_no_llama_herdr(hub):
    async def esc():
        modo = {"f": "herdr"}
        hub.fuente = lambda: modo["f"]
        await hub.refresh()
        hub.estados.recibir(ev("Stop"), "w1:p1")
        antes = len(hub.enchufe.calls)
        modo["f"] = "ganchos"
        hub.reaplicar()
        assert agente(hub.board)["status"] == "done" and len(hub.enchufe.calls) == antes

    asyncio.run(esc())


def test_done_a_idle_por_mark_seen(hub):
    async def esc():
        hub.fuente = lambda: "ganchos"
        hub.estados.recibir(ev("Stop"), "w1:p1")
        await hub.refresh()
        hub.mark_seen(SID)
        assert agente(hub.board)["status"] == "idle"

    asyncio.run(esc())


def test_observers_ven_estado_de_la_fuente(hub):
    async def esc():
        vistos = []
        hub.observers.append(lambda prev, new: vistos.append(agente(new)["status"]))
        hub.fuente = lambda: "ganchos"
        hub.estados.recibir(ev("PermissionRequest", tool_use_id="t1", tool_name="Bash"), "w1:p1")
        await hub.refresh()
        assert vistos[-1] == "blocked"

    asyncio.run(esc())


def test_aplicar_fuente_no_modifica_crudo():
    board = crudo_minimo()
    antes = copy.deepcopy(board)
    estados = EstadoSesiones()
    estados.recibir(ev("PermissionRequest", tool_use_id="t1", tool_name="Bash"), "w1:p1")
    aplicar_fuente(board, estados, "ganchos")
    assert board == antes


def test_status_herdr_en_todos_los_agentes_con_fuente_ganchos():
    board = crudo_minimo()
    board["workspaces"][0]["tabs"][0]["agents"].append(
        {"pane_id": "w1:p2", "status": "idle", "session_id": "otro"}
    )
    estados = EstadoSesiones()
    estados.recibir(ev("PermissionRequest", tool_use_id="t1", tool_name="Bash"), "w1:p1")
    out = aplicar_fuente(board, estados, "ganchos")
    agents = out["workspaces"][0]["tabs"][0]["agents"]
    assert agents[0]["status_herdr"] == "working"
    assert agents[1]["status_herdr"] == "idle"
    assert agents[0]["status"] == "blocked"
    assert agents[1]["status"] == "idle"
    assert "usando" not in agents[1]


def test_fuente_invalida_como_herdr():
    board = crudo_minimo()
    estados = EstadoSesiones()
    estados.recibir(ev("Stop"), "w1:p1")
    out = aplicar_fuente(board, estados, "no_existe")
    assert agente(out)["status"] == "working"
    assert "status_herdr" not in agente(out)


def test_fuente_que_lanza_como_herdr(hub, caplog):
    async def esc():
        hub.fuente = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        hub.estados.recibir(ev("Stop"), "w1:p1")
        with caplog.at_level(logging.WARNING):
            board = await hub.refresh()
        assert agente(board)["status"] == "working"
        assert any("fuente" in r.message.lower() or "boom" in r.message for r in caplog.records)

    asyncio.run(esc())


def test_reaplicar_sin_crudo_no_lanza(hub):
    hub.reaplicar()


def test_sin_conexion_perdura_tras_mark_seen(hub):
    async def esc():
        await hub.refresh()
        assert hub.crudo is not None and hub.crudo["terminales"] == "ok"
        hub.enchufe.caer()
        await hub._safe_refresh()
        assert hub.board["terminales"] == "sin_conexion"
        hub.estados.recibir(ev("Stop"), "w1:p1")
        hub.mark_seen(SID)
        assert hub.board["terminales"] == "sin_conexion"
        assert hub.crudo["terminales"] == "sin_conexion"

    asyncio.run(esc())


def test_mark_seen_sin_crudo_anota_replies(hub):
    async def esc():
        hub.fuente = lambda: "ganchos"
        await hub.refresh()
        hub.estados.recibir(ev("Stop"), "w1:p1")
        await hub.refresh()
        assert hub.replies.is_unread(SID)
        hub.crudo = None
        hub.mark_seen(SID)
        assert not hub.replies.is_unread(SID)
        assert agente(hub.board)["unread"] is False

    asyncio.run(esc())


def test_workspace_sin_agentes_conserva_status_herdr():
    board = {
        "workspaces": [
            {
                "id": "w1",
                "status": "working",
                "tabs": [{"agents": []}],
            }
        ]
    }
    estados = EstadoSesiones()
    out = aplicar_fuente(board, estados, "ganchos")
    assert out["workspaces"][0]["status"] == "working"


def test_crudo_deepcopy_solo_con_estados(hub):
    async def esc():
        hub.estados = None
        await hub.refresh()
        assert hub.crudo is None

        hub.estados = EstadoSesiones()
        await hub.refresh()
        assert hub.crudo is not None
        hub.board["terminales"] = "mutado"
        assert hub.crudo["terminales"] == "ok"

    asyncio.run(esc())


def test_mark_seen_notifica_suscriptores_done_a_idle(hub):
    async def esc():
        hub.fuente = lambda: "ganchos"
        hub.estados.recibir(ev("Stop"), "w1:p1")
        await hub.refresh()
        q = hub.subscribe()
        while not q.empty():
            q.get_nowait()
        hub.mark_seen(SID)
        actualizado = q.get_nowait()
        assert agente(actualizado)["status"] == "idle"
        hub.unsubscribe(q)

    asyncio.run(esc())



def test_reaplicar_no_modifica_crudo_ni_lo_comparte_con_el_publicado(hub):
    async def esc():
        await hub.refresh()
        antes = copy.deepcopy(hub.crudo)
        hub.estados.recibir(ev("PermissionRequest", tool_use_id="t1", tool_name="Bash"), "w1:p1")
        hub.fuente = lambda: "ganchos"
        hub.reaplicar()
        assert hub.crudo == antes
        hub.board["workspaces"][0]["status"] = "mutado"
        hub.board["workspaces"][0]["tabs"][0]["agents"][0]["status"] = "mutado"
        assert hub.crudo == antes

    asyncio.run(esc())
