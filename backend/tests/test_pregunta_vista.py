import asyncio
from datetime import timedelta

from orquestador.replies import ReplyTracker
from orquestador.state import StateStore

from conftest import SID
from test_replies import Clock, agent_of, tracker


def board_asks(status="idle", asks=True, sid=SID):
    agent = {"session_id": sid, "status": status, "asks_user": asks, "pregunta_real": asks, "preguntas": 2 if asks else 0,
             "pending": "¿Seguimos?", "estado": {"pide": "¿Seguimos?"}}
    return {"workspaces": [{"tabs": [{"agents": [agent]}]}]}


def ag(board):
    return board["workspaces"][0]["tabs"][0]["agents"][0]


def turno_con_pregunta(t):
    t.observe(board_asks("working", asks=False), board_asks())


def test_sin_marcar_sigue_preguntando(tmp_path):
    t, _ = tracker(tmp_path)
    turno_con_pregunta(t)
    a = ag(t.annotate(board_asks()))
    assert a["asks_user"] is True and a["pendiente"] is False


def test_marcada_deja_de_preguntar_y_queda_pendiente(tmp_path):
    t, clock = tracker(tmp_path)
    turno_con_pregunta(t)
    clock.now += timedelta(seconds=5)
    t.mark_pregunta_vista(SID)
    a = ag(t.annotate(board_asks()))
    assert a["asks_user"] is False and a["pendiente"] is True
    assert a["pregunta_real"] is False and a["preguntas"] == 0
    assert a["pending"] == "¿Seguimos?" and a["estado"] == {"pide": "¿Seguimos?"}


def test_anotar_dos_veces_es_estable(tmp_path):
    t, clock = tracker(tmp_path)
    turno_con_pregunta(t)
    clock.now += timedelta(seconds=5)
    t.mark_pregunta_vista(SID)
    once = t.annotate(board_asks())
    twice = t.annotate(once)
    assert ag(twice)["pendiente"] is True and ag(twice)["asks_user"] is False


def test_sin_pregunta_no_hay_pendiente(tmp_path):
    t, clock = tracker(tmp_path)
    t.observe(board_asks("working", asks=False), board_asks(asks=False))
    clock.now += timedelta(seconds=5)
    t.mark_pregunta_vista(SID)
    assert ag(t.annotate(board_asks(asks=False)))["pendiente"] is False


def test_turno_nuevo_vuelve_a_preguntar(tmp_path):
    t, clock = tracker(tmp_path)
    turno_con_pregunta(t)
    clock.now += timedelta(seconds=5)
    t.mark_pregunta_vista(SID)
    clock.now += timedelta(seconds=5)
    t.observe(board_asks("working", asks=False), board_asks())
    a = ag(t.annotate(board_asks()))
    assert a["asks_user"] is True and a["pendiente"] is False


def test_persiste_entre_reinicios(tmp_path):
    t, clock = tracker(tmp_path)
    turno_con_pregunta(t)
    clock.now += timedelta(seconds=5)
    t.mark_pregunta_vista(SID)
    t.state.flush()
    again = ReplyTracker(StateStore(tmp_path), clock)
    a = ag(again.annotate(board_asks()))
    assert a["asks_user"] is False and a["pendiente"] is True


def test_marcar_tambien_la_da_por_leida(tmp_path):
    t, clock = tracker(tmp_path)
    turno_con_pregunta(t)
    clock.now += timedelta(seconds=5)
    t.mark_pregunta_vista(SID)
    assert not t.is_unread(SID)


def test_hub_publica_sin_pregunta_a_los_observadores(app):
    hub = app.state.hub
    vistos = []
    hub.observers.append(lambda prev, board: vistos.append(board))
    hub._publicar(board_asks("working", asks=False))
    hub._publicar(board_asks())
    assert ag(vistos[-1])["asks_user"] is True
    hub.mark_pregunta_vista(SID)
    assert ag(hub.board)["asks_user"] is False and ag(hub.board)["pendiente"] is True
    hub._publicar(board_asks("working", asks=False))
    hub._publicar(board_asks())
    assert ag(vistos[-1])["asks_user"] is True and ag(vistos[-1])["pendiente"] is False


def test_endpoint_pregunta_vista(authed, app, enchufe):
    from test_replies import flip
    hub = app.state.hub
    flip(enchufe, "working")
    asyncio.run(hub.refresh())
    flip(enchufe, "idle")
    asyncio.run(hub.refresh())
    antes = agent_of(authed.get("/api/board").json())
    assert authed.post(f"/api/sessions/{SID}/pregunta-vista").status_code == 204
    despues = agent_of(authed.get("/api/board").json())
    assert despues["asks_user"] is False
    assert despues["pendiente"] is bool(antes["asks_user"])


def test_endpoint_requiere_login(client):
    assert client.post(f"/api/sessions/{SID}/pregunta-vista").status_code == 401


def test_endpoint_id_invalido(authed):
    assert authed.post("/api/sessions/a.b/pregunta-vista").status_code == 400


def test_endpoint_sesion_fuera_del_tablero(authed):
    assert authed.post("/api/sessions/99999999-2222-3333-4444-555555555555/pregunta-vista").status_code == 404
