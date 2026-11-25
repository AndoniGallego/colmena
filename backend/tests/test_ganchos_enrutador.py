import asyncio
import copy
import json

from conftest import SID
from fastapi.testclient import TestClient

from orquestador.board import fingerprint
from orquestador.ganchos.enrutador import Enrutador
from orquestador.ganchos.mensaje import Ids, MensajeGancho
from conftest import ORIGIN
from permisos_support import FakeConexion, enlazar_al_cambiar, esperar_pedido_abierto, pr


async def _flush_push(app):
    push = app.state._push_svc
    tareas = list(push._tasks)
    if tareas:
        await asyncio.gather(*tareas)


def test_enrutador_pr_bloquea_avisa_sin_contenido_y_post_resuelve(app_con_push):
    app = app_con_push
    recorder = app.state._push_recorder

    async def esc():
        enr = Enrutador(app.state.estados, app.state.permisos, app.state.hub)
        if app.state.hub.board is None:
            await app.state.hub.refresh()
        c = FakeConexion()
        ids = Ids(None, "w1:p1", None, None, SID)
        msg_pr = MensajeGancho(
            "PermissionRequest",
            "global",
            ids,
            {
                "tool_name": "Bash",
                "tool_use_id": "t1",
                "tool_input": {"command": "cat TOPSECRETO"},
                "cwd": "/home/u/p",
            },
        )
        t_pr = asyncio.create_task(enr.manejar(msg_pr, c))
        await esperar_pedido_abierto(app.state.permisos)
        assert app.state.estados.estado_de("w1:p1").estado == "blocked"
        await _flush_push(app)
        assert recorder.sent and "TOPSECRETO" not in str(recorder.sent)
        await enr.manejar(
            MensajeGancho("PostToolUse", "global", ids, {"tool_name": "Bash", "tool_use_id": "t1"}),
            FakeConexion(),
        )
        await asyncio.wait_for(t_pr, 1)
        assert app.state.permisos.abierto_para(SID) is None
        assert app.state.estados.estado_de("w1:p1").estado == "working"

    with TestClient(
        app,
        base_url="https://testserver",
        headers=ORIGIN,
        client=("127.0.0.1", 5000),
    ) as client:
        from conftest import PIN

        assert client.post("/api/login", json={"pin": PIN}).status_code == 200
        client.get("/api/board")
        client.portal.call(esc)


def test_enrutador_duplicado_atender_no_cuelga_si_conexion_distinta(app_con_push):
    app = app_con_push
    estados = app.state.estados
    real_recibir = estados.recibir

    def recibir_forzado(msg, pane):
        if msg.evento == "PermissionRequest" and app.state.permisos.abierto_para(SID):
            return True
        return real_recibir(msg, pane)

    estados.recibir = recibir_forzado

    async def esc():
        enr = Enrutador(estados, app.state.permisos, app.state.hub)
        if app.state.hub.board is None:
            await app.state.hub.refresh()
        ids = Ids(None, "w1:p1", None, None, SID)
        msg = MensajeGancho(
            "PermissionRequest",
            "global",
            ids,
            {
                "tool_name": "Bash",
                "tool_use_id": "t_dup",
                "tool_input": {"command": "touch foo"},
                "cwd": "/home/u/p",
            },
        )
        c1 = FakeConexion()
        c2 = FakeConexion()
        t1 = asyncio.create_task(enr.manejar(msg, c1))
        await esperar_pedido_abierto(app.state.permisos)
        t2 = asyncio.create_task(enr.manejar(msg, c2))
        await asyncio.wait_for(t2, 1)
        assert t2.done() and not t1.done()
        assert c2.cerrada.is_set()
        await enr.manejar(
            MensajeGancho("PostToolUse", "global", ids, {"tool_name": "Bash", "tool_use_id": "t_dup"}),
            FakeConexion(),
        )
        await asyncio.wait_for(t1, 1)

    with TestClient(
        app,
        base_url="https://testserver",
        headers=ORIGIN,
        client=("127.0.0.1", 5000),
    ) as client:
        from conftest import PIN

        assert client.post("/api/login", json={"pin": PIN}).status_code == 200
        client.get("/api/board")
        client.portal.call(esc)


def test_enrutador_duplicado_cierra_segunda_conexion(app_con_push):
    app = app_con_push

    async def esc():
        enr = Enrutador(app.state.estados, app.state.permisos, app.state.hub)
        if app.state.hub.board is None:
            await app.state.hub.refresh()
        ids = Ids(None, "w1:p1", None, None, SID)
        msg = MensajeGancho(
            "PermissionRequest",
            "global",
            ids,
            {
                "tool_name": "Bash",
                "tool_use_id": "t1",
                "tool_input": {"command": "touch foo"},
                "cwd": "/home/u/p",
            },
        )
        c1 = FakeConexion()
        c2 = FakeConexion()
        t1 = asyncio.create_task(enr.manejar(msg, c1))
        await esperar_pedido_abierto(app.state.permisos)
        t2 = asyncio.create_task(enr.manejar(msg, c2))
        await asyncio.wait_for(t2, 1)
        assert c2.cerrada.is_set() and c2.respuestas == []
        assert len(app.state.permisos.listar()) == 1
        await enr.manejar(
            MensajeGancho("PostToolUse", "global", ids, {"tool_name": "Bash", "tool_use_id": "t1"}),
            FakeConexion(),
        )
        await asyncio.wait_for(t1, 1)

    with TestClient(
        app,
        base_url="https://testserver",
        headers=ORIGIN,
        client=("127.0.0.1", 5000),
    ) as client:
        from conftest import PIN

        assert client.post("/api/login", json={"pin": PIN}).status_code == 200
        client.get("/api/board")
        client.portal.call(esc)


def test_enrutador_sin_dueno_no_toca_tablero(app_con_push, tmp_path):
    app = app_con_push
    otro_sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    async def esc():
        enr = Enrutador(app.state.estados, app.state.permisos, app.state.hub)
        if app.state.hub.board is None:
            await app.state.hub.refresh()
        fp_antes = fingerprint(app.state.hub.board)
        ids = Ids(None, "w9:p9", None, None, otro_sid)
        c = FakeConexion()
        t = asyncio.create_task(
            enr.manejar(
                MensajeGancho(
                    "PermissionRequest",
                    "global",
                    ids,
                    {
                        "tool_name": "Bash",
                        "tool_use_id": "t1",
                        "tool_input": {"command": "touch foo"},
                        "cwd": "/home/u/p",
                    },
                ),
                c,
            )
        )
        await asyncio.wait_for(t, 1)
        assert fingerprint(app.state.hub.board) == fp_antes
        assert app.state.permisos.listar() == []
        assert c.cerrada.is_set()
        path = tmp_path / "permisos.jsonl"
        if path.is_file():
            ultima = json.loads(path.read_text().splitlines()[-1])
            assert ultima["tipo"] == "sin-dueno"

    with TestClient(
        app,
        base_url="https://testserver",
        headers=ORIGIN,
        client=("127.0.0.1", 5000),
    ) as client:
        from conftest import PIN

        assert client.post("/api/login", json={"pin": PIN}).status_code == 200
        client.get("/api/board")
        client.portal.call(esc)


def test_enrutador_pr_espera_decision_y_responde_allow(app_con_push):
    app = app_con_push

    async def esc():
        enr = Enrutador(app.state.estados, app.state.permisos, app.state.hub)
        if app.state.hub.board is None:
            await app.state.hub.refresh()
        c = FakeConexion()
        t = asyncio.create_task(enr.manejar(pr(), c))
        await esperar_pedido_abierto(app.state.permisos)
        assert not t.done()
        pedido = app.state.permisos.abierto_para(SID)
        await app.state.permisos.decidir(pedido.id, "permitir")
        await asyncio.wait_for(t, 1)
        assert c.respuestas == [{"v": 1, "decision": "allow"}]

    with TestClient(
        app,
        base_url="https://testserver",
        headers=ORIGIN,
        client=("127.0.0.1", 5000),
    ) as client:
        from conftest import PIN

        assert client.post("/api/login", json={"pin": PIN}).status_code == 200
        client.get("/api/board")
        client.portal.call(esc)


def test_enrutador_pr_desde_app_apagado_termina_enseguida(app_con_push, cfg):
    app = app_con_push
    cfg.permisos = {"desde_app": False}

    async def esc():
        enr = Enrutador(app.state.estados, app.state.permisos, app.state.hub)
        if app.state.hub.board is None:
            await app.state.hub.refresh()
        c = FakeConexion()
        t = asyncio.create_task(enr.manejar(pr(), c))
        await asyncio.wait_for(t, 1)
        assert c.cerrada.is_set()
        assert app.state.permisos.listar() == []

    with TestClient(
        app,
        base_url="https://testserver",
        headers=ORIGIN,
        client=("127.0.0.1", 5000),
    ) as client:
        from conftest import PIN

        assert client.post("/api/login", json={"pin": PIN}).status_code == 200
        client.get("/api/board")
        client.portal.call(esc)


def test_aviso_que_falla_no_frena_la_senal_de_permisos():
    import asyncio
    from types import SimpleNamespace
    from orquestador.ganchos.mensaje import Ids, MensajeGancho

    senales = []

    class Permisos:
        async def senal(self, sid, evento, tool_use_id):
            senales.append((sid, evento))

    def rompe(msg, pane):
        raise AttributeError("x")

    enr = Enrutador(SimpleNamespace(recibir=lambda msg, pane: None), Permisos(), SimpleNamespace(board=None),
                    post_tool_use=rompe)
    msg = MensajeGancho(evento="PostToolUse", origen="claude", ids=Ids(None, None, None, None, "sid-1"),
                        datos={"tool_name": "Bash", "tool_input": {"command": "ls"}})
    asyncio.run(enr.manejar(msg, SimpleNamespace(cerrada=asyncio.Event())))
    assert senales == [("sid-1", "PostToolUse")]


def test_enrutador_avisa_al_detector_en_herramientas_y_prompt():
    from types import SimpleNamespace

    vistos = []

    class Permisos:
        async def senal(self, sid, evento, tool_use_id):
            pass

    enr = Enrutador(SimpleNamespace(recibir=lambda msg, pane: False), Permisos(), SimpleNamespace(board=None),
                    al_evento=lambda msg, pane: vistos.append((msg.evento, pane)))
    ids = Ids(None, None, None, None, "sid-1")
    for ev in ("PreToolUse", "PostToolUse", "PostToolUseFailure", "UserPromptSubmit", "Stop"):
        asyncio.run(enr.manejar(MensajeGancho(ev, "global", ids, {"tool_name": "Bash", "tool_use_id": "t"}),
                                SimpleNamespace(cerrada=asyncio.Event())))
    assert [e for e, _ in vistos] == ["PreToolUse", "PostToolUse", "PostToolUseFailure", "UserPromptSubmit"]
