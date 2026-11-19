import json

import pytest

from test_limpieza import Clock, agent, ago, snapshot_of, tab, term, ws
from terminales_support import aplicar_snapshot, proceso_json, set_proceso_todos, snap_de

LOTE = "lote-aaaaaaaa-0001"


def sid(n):
    return f"item-{n:08d}"


@pytest.fixture
def world(app, enchufe):
    board = {"workspaces": [
        ws("w1", "Uno", [tab("w1:t1", [agent(1)], label="Viejo uno"), tab("w1:t2", [agent(2)], label="Viejo dos"),
                         tab("w1:t3", [agent(3, "working")])]),
        ws("w2", "Dos", [tab("w2:t1", [agent(4, "working")])]),
        ws("w3", "Super orquestador", [tab("w3:t1", [], [term(7)]), tab("w3:t2", [], [term(8)])]),
    ]}
    aplicar_snapshot(enchufe, snapshot_of(board))
    state = {"board": board}

    async def refresh(force=False):
        return state["board"]

    app.state.hub.refresh = refresh
    app.state.hub.board = board
    app.state.limpieza.clock = Clock()
    return state


def sse(text):
    events, name = [], None
    for line in text.splitlines():
        if line.startswith("event: "):
            name = line[7:]
        elif line.startswith("data: "):
            events.append((name, json.loads(line[6:])))
    return events


def huella(authed, target, tipo="tab"):
    r = authed.post("/api/limpieza/preview", json={"items": [{"tipo": tipo, "target_id": target}]})
    assert r.status_code == 200
    return r.json()[0]["preview"]["huella"]


def ejecutar(authed, targets, lote=LOTE, huellas=None, **extra):
    items = [{"id": sid(i), "tipo": "tab", "target_id": t, "huella": (huellas or {}).get(t) or huella(authed, t)}
             for i, t in enumerate(targets)]
    return authed.post("/api/limpieza/ejecutar", json={"lote_id": lote, "items": items, "sin_guardar": True, **extra})


def closes(enchufe):
    return enchufe.calls_of("cerrar")


def test_candidatos_endpoint_and_range(authed, world):
    r = authed.get("/api/limpieza/candidatos")
    assert r.status_code == 200 and r.json()["dias"] == 7
    assert sorted(i["target_id"] for i in r.json()["items"]) == ["w1:t1", "w1:t2"]
    assert authed.get("/api/limpieza/candidatos?dias=10").json()["items"] == []
    assert authed.get("/api/limpieza/candidatos?dias=0").status_code == 422
    assert authed.get("/api/limpieza/candidatos?dias=91").status_code == 422


def test_requires_login(client):
    assert client.get("/api/limpieza/candidatos").status_code == 401
    assert client.post("/api/limpieza/ejecutar", json={}).status_code == 401


def test_preview_per_item_with_error_for_unknown(authed, world):
    r = authed.post("/api/limpieza/preview", json={"items": [{"tipo": "tab", "target_id": "w1:t1"},
                                                           {"tipo": "tab", "target_id": "w9:t9"}]})
    out = r.json()
    assert out[0]["preview"]["label"] == "Viejo uno" and "error" not in out[0]
    assert out[1] == {"tipo": "tab", "target_id": "w9:t9", "error": "Ya no está abierto"}


def test_preview_limit_and_shape(authed, world):
    items = [{"tipo": "tab", "target_id": "w1:t1"}] * 13
    assert authed.post("/api/limpieza/preview", json={"items": items}).status_code == 400
    assert authed.post("/api/limpieza/preview", json={"items": [{"tipo": "pane", "target_id": "x"}]}).status_code == 400


def test_ejecutar_closes_in_order_records_origin_and_lote(authed, world, enchufe, app):
    r = ejecutar(authed, ["w1:t1", "w1:t2"])
    events = sse(r.text)
    assert [e[0] for e in events] == ["item", "item", "fin"]
    assert [e[1]["ok"] for e in events[:2]] == [True, True]
    assert events[0][1]["sesiones"][0]["session_id"] == agent(1)["session_id"]
    assert events[2][1] == {"cerrados": 2, "salteados": 0}
    assert closes(enchufe) == [("cerrar", "w1:t1"), ("cerrar", "w1:t2")]


def test_cierres_json_gets_origin_limpieza(authed, world, enchufe, tmp_path):
    ejecutar(authed, ["w1:t1"])
    entries = authed.app.state.state.cierres()
    assert entries[-1]["origen"] == "limpieza" and entries[-1]["lote_id"] == LOTE and entries[-1]["ok"]


def test_huella_changed_between_review_and_close_is_skipped(authed, world, enchufe):
    stale = huella(authed, "w1:t1")
    snap = snap_de(enchufe)
    next(a for a in snap["agents"] if a["pane_id"] == "p1")["state_change_seq"] = 99
    aplicar_snapshot(enchufe, snap)
    events = sse(ejecutar(authed, ["w1:t1", "w1:t2"], huellas={"w1:t1": stale}).text)
    assert events[0][1]["ok"] is False and events[0][1]["salteado"] and "cambió" in events[0][1]["error"].lower()
    assert events[1][1]["ok"] is True
    assert events[2][1] == {"cerrados": 1, "salteados": 1}
    assert closes(enchufe) == [("cerrar", "w1:t2")]


def test_session_resumed_between_review_and_close_is_skipped(authed, world, enchufe):
    huellas = {t: huella(authed, t) for t in ("w1:t1", "w1:t2")}
    world["board"]["workspaces"][0]["tabs"][0]["agents"][0]["status"] = "working"
    events = sse(ejecutar(authed, ["w1:t1", "w1:t2"], huellas=huellas).text)
    assert events[0][1]["ok"] is False and events[1][1]["ok"] is True
    assert closes(enchufe) == [("cerrar", "w1:t2")]


def test_reply_arrives_between_review_and_close_is_skipped(authed, world, enchufe):
    huellas = {"w1:t1": huella(authed, "w1:t1")}
    world["board"]["workspaces"][0]["tabs"][0]["agents"][0]["unread"] = True
    events = sse(ejecutar(authed, ["w1:t1"], huellas=huellas).text)
    assert events[0][1]["ok"] is False and not closes(enchufe)


def test_not_a_candidate_is_never_closed_even_with_valid_huella(authed, world, enchufe):
    set_proceso_todos(enchufe, proceso_json(("bash", 1)))
    for target in ("w1:t3", "w3:t1", "w2:t1"):
        events = sse(ejecutar(authed, [target]).text)
        assert events[0][1]["ok"] is False
    assert not closes(enchufe)


def test_days_in_body_are_used_for_the_revalidation(authed, world, enchufe):
    events = sse(ejecutar(authed, ["w1:t1"], dias=30).text)
    assert events[0][1]["ok"] is False and not closes(enchufe)


def test_blocker_found_by_close_flow_is_skipped(authed, world, enchufe):
    huellas = {"w1:t1": huella(authed, "w1:t1")}
    snap = snap_de(enchufe)
    snap["panes"].append({"pane_id": "px", "tab_id": "w1:t1", "workspace_id": "w1"})
    aplicar_snapshot(enchufe, snap)
    world["board"]["workspaces"][0]["tabs"][0]["terminales"].append(
        {"pane_id": "px", "terminal_id": "t", "titulo": "", "cwd": "", "proceso": "", "estado": "prompt", "protegida": False})
    set_proceso_todos(enchufe, proceso_json(("claude", 7)))
    events = sse(ejecutar(authed, ["w1:t1"], huellas=huellas).text)
    assert events[0][1]["ok"] is False and not closes(enchufe)


def test_same_item_id_is_idempotent(authed, world, enchufe):
    h = huella(authed, "w1:t1")
    body = {"lote_id": LOTE, "items": [{"id": sid(1), "tipo": "tab", "target_id": "w1:t1", "huella": h}], "sin_guardar": True}
    sse(authed.post("/api/limpieza/ejecutar", json=body).text)
    events = sse(authed.post("/api/limpieza/ejecutar", json=body).text)
    assert events[0][1]["ok"] is False and len(closes(enchufe)) == 1


def test_second_batch_while_one_runs_is_409(authed, world, enchufe, app):
    app.state.limpieza.lote_activo = True
    r = ejecutar(authed, ["w1:t1"])
    assert r.status_code == 409 and not closes(enchufe)
    app.state.limpieza.lote_activo = False
    assert ejecutar(authed, ["w1:t1"]).status_code == 200
    assert app.state.limpieza.lote_activo is False


def test_batch_limits_and_validation(authed, world):
    item = {"id": sid(1), "tipo": "tab", "target_id": "w1:t1", "huella": "x"}
    assert authed.post("/api/limpieza/ejecutar", json={"lote_id": LOTE, "items": [item] * 13}).status_code == 400
    assert authed.post("/api/limpieza/ejecutar", json={"lote_id": LOTE, "items": []}).status_code == 400
    assert authed.post("/api/limpieza/ejecutar", json={"lote_id": "x", "items": [item]}).status_code == 400
    assert authed.post("/api/limpieza/ejecutar", json={"lote_id": LOTE, "items": [{**item, "tipo": "pane"}]}).status_code == 400


def test_disconnect_stops_after_current_item(authed, world, enchufe, monkeypatch):
    from starlette.requests import Request
    calls = []

    async def gone(self):
        calls.append(1)
        return len(calls) > 1

    monkeypatch.setattr(Request, "is_disconnected", gone)
    huellas = {t: huella(authed, t) for t in ("w1:t1", "w1:t2")}
    ejecutar(authed, ["w1:t1", "w1:t2"], huellas=huellas)
    assert closes(enchufe) == [("cerrar", "w1:t1")]


def test_workspace_item_closes_whole_workspace(authed, world, enchufe):
    world["board"]["workspaces"][0]["tabs"][2]["agents"][0]["status"] = "idle"
    world["board"]["workspaces"][0]["tabs"][2]["agents"][0]["last_activity"] = ago(20)
    aplicar_snapshot(enchufe, snapshot_of(world["board"]))
    cand = authed.get("/api/limpieza/candidatos").json()
    assert [(i["tipo"], i["target_id"]) for i in cand["items"]] == [("workspace", "w1")]
    h = huella(authed, "w1", "workspace")
    r = authed.post("/api/limpieza/ejecutar", json={"lote_id": LOTE, "items": [
        {"id": sid(1), "tipo": "workspace", "target_id": "w1", "huella": h}], "sin_guardar": True})
    assert sse(r.text)[-1][1] == {"cerrados": 1, "salteados": 0}
    assert closes(enchufe) == [("cerrar", "w1")]


def test_batch_is_released_when_client_leaves_before_first_byte(authed, world, enchufe, app, monkeypatch):
    from starlette.responses import StreamingResponse

    async def broken(self, send):
        raise OSError("client gone")

    monkeypatch.setattr(StreamingResponse, "stream_response", broken)
    h = huella(authed, "w1:t1")
    try:
        ejecutar(authed, ["w1:t1"], huellas={"w1:t1": h})
    except Exception:
        pass
    assert app.state.limpieza.lote_activo is False and not closes(enchufe)


# ---------- guardado en Engram (spec 16): sin `sin_guardar` y con sesiones Claude ----------

import asyncio
import copy


def con_estado(board, **estados):
    nuevo = copy.deepcopy(board)
    for w in nuevo["workspaces"]:
        for t in w["tabs"]:
            for a in t["agents"]:
                if a["pane_id"] in estados:
                    a["status"] = estados[a["pane_id"]]
    return nuevo


@pytest.fixture
def guardando(app, world, enchufe):
    """Al recibir el pedido de guardado, cada sesión hace su turno (o se traba) y el timer vence al instante."""
    svc = app.state.guardado
    plan = {"terminan": ["p1", "p2"], "traban": [], "vence": False, "cerrar_igual": False}
    orig = enchufe.mandar_prompt
    visto = {"board": world["board"], "pedidos": []}

    timers = []

    async def mandar_prompt(sesion_id, texto, **kw):
        out = await orig(sesion_id, texto, **kw)
        visto["pedidos"].append(sesion_id)
        loop = asyncio.get_running_loop()
        if plan["vence"] and timers:
            loop.call_soon(timers[0])
        if sesion_id in plan["terminan"] or sesion_id in plan["traban"]:
            antes = visto["board"]
            trabajando = con_estado(antes, **{sesion_id: "working"})
            svc.on_board(antes, trabajando)
            final = con_estado(trabajando, **{sesion_id: "blocked" if sesion_id in plan["traban"] else "idle"})
            svc.on_board(trabajando, final)
            visto["board"] = final
        if plan["cerrar_igual"]:
            loop.call_soon(lambda: loop.create_task(svc.accion(LOTE, "cerrar_igual")))
        return out

    enchufe.mandar_prompt = mandar_prompt

    def later(delay, fn):
        timers.append(fn)
        return type("H", (), {"cancel": lambda self: None})()

    svc.call_later = later
    visto["plan"] = plan
    return visto


def ejecutar_con_guardado(authed, targets, **extra):
    items = [{"id": sid(i), "tipo": "tab", "target_id": t, "huella": huella(authed, t)} for i, t in enumerate(targets)]
    return authed.post("/api/limpieza/ejecutar", json={"lote_id": LOTE, "items": items, **extra})


def test_con_sesiones_claude_pide_guardar_a_todas_y_procesa_todos_los_items(authed, world, enchufe, guardando):
    events = sse(ejecutar_con_guardado(authed, ["w1:t1", "w1:t2"]).text)
    nombres = [e[0] for e in events]
    assert "guardando" in nombres and nombres.count("item") == 2 and nombres[-1] == "fin"
    assert events[-1][1] == {"cerrados": 2, "salteados": 0}
    assert sorted(guardando["pedidos"]) == ["p1", "p2"]
    assert sorted(c[1] for c in closes(enchufe)) == ["w1:t1", "w1:t2"]


def cierres_json(authed):
    return authed.app.state.state.cierres()


def test_audita_guardado_ok_en_cada_cierre_de_la_limpieza(authed, world, enchufe, tmp_path, guardando):
    sse(ejecutar_con_guardado(authed, ["w1:t1"]).text)
    assert [c["guardado"] for c in cierres_json(authed)] == ["ok"]


def test_al_vencer_no_cierra_solo_y_el_usuario_elige_cerrar_igual(authed, world, enchufe, tmp_path, guardando):
    guardando["plan"].update(terminan=[], vence=True, cerrar_igual=True)
    events = sse(ejecutar_con_guardado(authed, ["w1:t1"]).text)
    assert any(e[0] == "guardando" and e[1]["vencido"] and not e[1]["terminado"] for e in events)
    assert events[-1] == ("fin", {"cerrados": 1, "salteados": 0})
    assert [c["guardado"] for c in cierres_json(authed)] == ["vencido"]


def test_sesion_bloqueada_ofrece_cerrar_igual_sin_cancelar_y_las_demas_siguen(authed, world, enchufe, tmp_path, guardando):
    guardando["plan"].update(terminan=["p1", "p2"], traban=["p2"], cerrar_igual=True)
    events = sse(ejecutar_con_guardado(authed, ["w1:t1", "w1:t2"]).text)
    assert events[-1] == ("fin", {"cerrados": 2, "salteados": 0})
    assert any(e[0] == "guardando" and e[1]["puede_cerrar_igual"] for e in events)
    assert {c["target_id"]: c["guardado"] for c in cierres_json(authed)} == {"w1:t1": "ok", "w1:t2": "vencido"}


def test_con_guardado_un_item_que_ya_no_es_candidato_se_saltea_y_el_resto_sigue(authed, world, enchufe, guardando):
    items = [{"id": sid(0), "tipo": "tab", "target_id": "w1:t1", "huella": huella(authed, "w1:t1")},
             {"id": sid(1), "tipo": "tab", "target_id": "w1:t3", "huella": "x"}]
    events = sse(authed.post("/api/limpieza/ejecutar", json={"lote_id": LOTE, "items": items}).text)
    assert events[-1] == ("fin", {"cerrados": 1, "salteados": 1})
    assert [c[1] for c in closes(enchufe)] == ["w1:t1"]
