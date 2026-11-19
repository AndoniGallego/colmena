import asyncio
import json

import pytest

from orquestador.cierre import CierreBody
from orquestador.traspaso import TraspasoError
from conftest import ORIGIN, SID, make_snapshot
from orquestador.enchufe import FakeTerminales, GrupoRequerido, NoDisponible
from orquestador.enchufe.herdr import info_de_process_json
from terminales_support import aplicar_snapshot, proceso_argv_json, proceso_json, set_proceso_todos, snap_de

ID = "6f1c1e0b-4a55-4e1d-9d33-1f3c2a7d9e10"


@pytest.fixture
def cfg(cfg):
    # El default ya no protege nada: estos tests cubren el mecanismo para quien lo configure.
    cfg.protected_workspaces = ["Super orquestador"]
    return cfg


def preview(authed, tipo="tab", target="w1:t1"):
    return authed.post("/api/close/preview", json={"tipo": tipo, "target_id": target})


def execute(authed, huella, **over):
    body = {"id": ID, "tipo": "tab", "target_id": "w1:t1", "huella": huella, "origen": "manual",
            "destino": "Uno", "por_que": "", "sin_guardar": True}
    body.update(over)
    return authed.post("/api/close/execute", json=body)


def closes(enchufe):
    return enchufe.calls_of("cerrar")


def two_tabs(enchufe, status="idle"):
    snap = make_snapshot(status)
    snap["tabs"].append({"tab_id": "w1:t2", "workspace_id": "w1", "label": "Terminales"})
    snap["panes"].append({"pane_id": "w1:p2", "tab_id": "w1:t2", "workspace_id": "w1"})
    aplicar_snapshot(enchufe, snap)
    return snap


def two_tab_agents(enchufe, status="idle"):
    snap = two_tabs(enchufe, status)
    snap["agents"].append({"pane_id": "w1:p2", "tab_id": "w1:t2", "workspace_id": "w1", "agent": "claude",
                           "agent_status": "idle", "state_change_seq": 1})
    aplicar_snapshot(enchufe, snap)
    return snap


def protected_two_tabs(enchufe):
    snap = two_tabs(enchufe)
    snap["workspaces"][1]["label"] = "  super ORQUESTADOR "
    aplicar_snapshot(enchufe, snap)
    return snap


def _sync(enchufe, snap):
    aplicar_snapshot(enchufe, snap)
    return snap



def test_preview_lists_agent_and_terminal_panes_without_cmdline(authed, enchufe):
    snap = two_tabs(enchufe)
    snap["panes"].append({"pane_id": "w1:p3", "tab_id": "w1:t2", "workspace_id": "w1"})
    aplicar_snapshot(enchufe, snap)
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("node", 42)))
    r = preview(authed, target="w1:t2")
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Terminales" and body["workspace_label"] == "Uno" and not body["cierra_workspace"]
    assert [(p["pane_id"], p["kind"], p["proceso"]) for p in body["panes"]] == [("w1:p2", None, "node"), ("w1:p3", None, "node")]
    assert "SECRETO" not in r.text and "cmdline" not in r.text
    assert body["bloqueantes"] == []


def test_preview_agent_pane_and_only_tab_closes_workspace(authed, enchufe):
    body = preview(authed).json()
    assert body["cierra_workspace"] is True
    assert body["panes"] == [{"pane_id": "w1:p1", "kind": "claude", "status": "idle", "titulo": "Título terminal",
                              "session_id": SID, "cwd": "/tmp", "proceso": None}]
    assert not enchufe.calls_of("proceso")


def test_preview_blockers_and_shell_only_pane_has_no_process(authed, enchufe):
    for status in ("working", "blocked", "unknown"):
        aplicar_snapshot(enchufe, make_snapshot(status))
        assert preview(authed).json()["bloqueantes"] == [{"pane_id": "w1:p1", "status": status}]
    aplicar_snapshot(enchufe, make_snapshot())
    set_proceso_todos(enchufe, proceso_json(("bash", 1)))
    assert preview(authed, "workspace", "w2").status_code == 400


def test_preview_unknown_target_404_and_bad_id_400(authed):
    assert preview(authed, target="w9:t9").status_code == 404
    assert preview(authed, target="--evil").status_code == 400
    assert authed.post("/api/close/preview", json={"tipo": "pane", "target_id": "w1:t1"}).status_code == 400


def test_preview_too_many_panes_409(authed, enchufe):
    snap = two_tabs(enchufe)
    snap["panes"] += [{"pane_id": f"w1:q{i}", "tab_id": "w1:t2", "workspace_id": "w1"} for i in range(12)]
    aplicar_snapshot(enchufe, snap)
    assert preview(authed, target="w1:t2").status_code == 409


def test_protected_self_pane_and_label(authed, enchufe):
    r = preview(authed, "tab", "w2:t2")
    assert r.status_code == 400 and "orquestador" in r.json()["detail"]
    assert preview(authed, "workspace", "w2").status_code == 400
    snap = make_snapshot()
    snap["workspaces"][1]["label"] = "Super orquestador"
    aplicar_snapshot(enchufe, snap)
    r = preview(authed, "workspace", "w1")
    assert r.status_code == 400 and "protegido" in r.json()["detail"]
    assert preview(authed, "tab", "w1:t1").status_code == 400


def test_protected_env_pane(cfg, tmp_path, handoffs):
    from fastapi.testclient import TestClient
    from orquestador.app import create_app
    from orquestador.state import StateStore
    from conftest import PIN
    enchufe = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    app = create_app(cfg, b"s", StateStore(tmp_path), enchufe=enchufe, dist=tmp_path / "x", handoffs_dir=handoffs,
                     uploads_dir=tmp_path / "u", env_pane_id="w1:p1")
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 1)) as c:
        c.post("/api/login", json={"pin": PIN})
        assert c.post("/api/close/preview", json={"tipo": "tab", "target_id": "w1:t1"}).status_code == 400


def test_only_workspace_409(authed, enchufe):
    snap = make_snapshot()
    snap["workspaces"] = snap["workspaces"][1:]
    aplicar_snapshot(enchufe, snap)
    snap["tabs"] = [snap["tabs"][0]]
    snap["panes"] = snap["panes"][:1]
    snap["agents"] = snap["agents"][:1]
    aplicar_snapshot(enchufe, snap)
    r = preview(authed, "workspace", "w1")
    assert r.status_code == 409 and "único workspace" in r.json()["detail"]
    assert preview(authed).status_code == 409


def test_execute_closes_tab_and_records(authed, enchufe, tmp_path):
    two_tabs(enchufe)
    h = preview(authed, target="w1:t2").json()["huella"]
    r = execute(authed, h, target_id="w1:t2")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "sesiones": [], "closed_tab_id": "w1:t2"}
    assert closes(enchufe) == [("cerrar", "w1:t2")]
    assert ("cerrar", "w1:t1") not in enchufe.calls
    assert ("cerrar", "w1") not in enchufe.calls
    assert [c["id"] for c in authed.app.state.state.cierres()] == [ID]
    assert authed.app.state.state.messages() == []


def test_execute_session_records_resume_data_and_workspace(authed, enchufe):
    h = preview(authed).json()["huella"]
    r = execute(authed, h)
    assert r.status_code == 200
    body = r.json()
    assert body["closed_workspace_id"] == "w1"
    assert body["sesiones"] == [{"session_id": SID, "cwd": "/tmp", "titulo": "Título terminal"}]
    assert body["sesiones"][0]["session_id"] == SID and "event" not in body


def test_execute_workspace_and_event_only_for_jefe(authed, enchufe):
    h = preview(authed, "workspace", "w1").json()["huella"]
    r = execute(authed, h, tipo="workspace", target_id="w1", origen="jefe")
    assert r.status_code == 200
    assert r.json()["closed_workspace_id"] == "w1" and r.json()["event"]["text"] == "Cerré workspace Uno"
    assert authed.app.state.state.messages() == []
    assert closes(enchufe) == [("cerrar", "w1")]


@pytest.mark.parametrize("status,detail", [("working", "Frenala primero"), ("blocked", "Frenala primero"),
                                            ("unknown", "No sé si está trabajando")])
def test_execute_blockers_409_with_list(authed, enchufe, status, detail):
    two_tabs(enchufe)
    h = preview(authed, target="w1:t2").json()["huella"]
    snap = make_snapshot(status)
    snap["tabs"].append({"tab_id": "w1:t2", "workspace_id": "w1", "label": "T"})
    snap["agents"][0]["tab_id"] = "w1:t2"
    aplicar_snapshot(enchufe, snap)
    r = execute(authed, h, target_id="w1:t2")
    assert r.status_code == 409 and r.json()["detail"].startswith(detail)
    assert r.json()["bloqueantes"] == [{"pane_id": "w1:p1", "status": status}]
    assert closes(enchufe) == []


def test_execute_stale_huella_409(authed, enchufe):
    snap = two_tabs(enchufe)
    h = preview(authed, target="w1:t2").json()["huella"]
    snap["panes"].append({"pane_id": "w1:p7", "tab_id": "w1:t2", "workspace_id": "w1"})
    aplicar_snapshot(enchufe, snap)
    r = execute(authed, h, target_id="w1:t2")
    assert r.status_code == 409 and "cambió" in r.json()["detail"] and closes(enchufe) == []
    assert execute(authed, "x" * 64, target_id="w1:t2").status_code == 409


def test_execute_state_change_invalidates_huella(authed, enchufe):
    snap = two_tabs(enchufe)
    snap["agents"].append({"pane_id": "w1:p2", "tab_id": "w1:t2", "workspace_id": "w1", "agent": "claude",
                           "agent_status": "idle", "state_change_seq": 1})
    aplicar_snapshot(enchufe, snap)
    h = preview(authed, target="w1:t2").json()["huella"]
    snap["agents"][-1]["state_change_seq"] = 2
    aplicar_snapshot(enchufe, snap)
    assert execute(authed, h, target_id="w1:t2").status_code == 409


def test_execute_protected_and_missing(authed, enchufe):
    assert execute(authed, "h", tipo="tab", target_id="w2:t2").status_code == 400
    assert execute(authed, "h", target_id="w9:t9").status_code == 404
    assert closes(enchufe) == []


def test_group_close_required_409(authed, enchufe):
    h = preview(authed, "workspace", "w1").json()["huella"]
    enchufe.fallas["cerrar"] = GrupoRequerido('{"error":{"code":"workspace_group_close_required"}}')
    r = execute(authed, h, tipo="workspace", target_id="w1")
    assert r.status_code == 409 and "worktrees" in r.json()["detail"]


def test_herdr_failure_502_recorded_and_retryable(authed, enchufe, app):
    two_tabs(enchufe)
    h = preview(authed, target="w1:t2").json()["huella"]
    enchufe.fallas["cerrar"] = NoDisponible("boom")
    assert execute(authed, h, target_id="w1:t2").status_code == 502
    enchufe.fallas.pop("cerrar", None)
    assert execute(authed, h, target_id="w1:t2").status_code == 200
    assert execute(authed, h, target_id="w1:t2").status_code == 409


def test_target_still_alive_after_close_502(authed, enchufe):
    two_tabs(enchufe)
    h = preview(authed, target="w1:t2").json()["huella"]
    enchufe.aplicar_cierres = False
    r = execute(authed, h, target_id="w1:t2")
    assert r.status_code == 502 and "No se pudo cerrar" in r.json()["detail"]


def test_idempotent_id_409(authed, enchufe):
    two_tabs(enchufe)
    h = preview(authed, target="w1:t2").json()["huella"]
    assert execute(authed, h, target_id="w1:t2").status_code == 200
    r = execute(authed, h, target_id="w1:t2")
    assert r.status_code == 409 and "Ya se cerró" in r.json()["detail"]


def test_body_validation_400(authed):
    assert authed.post("/api/close/execute", json={"id": "corto"}).status_code == 400
    assert execute(authed, "h", origen="otro").status_code == 400


def test_cierres_trimmed_to_100(tmp_path):
    from orquestador.state import StateStore
    st = StateStore(tmp_path)
    for i in range(120):
        st.add_cierre({"id": str(i), "ok": True})
    st.flush()
    assert len(st.cierres()) == 100 and st.cierres()[0]["id"] == "20"
    assert len(StateStore(tmp_path).cierres()) == 100


def test_close_waits_for_pane_lock_shared_with_messages(app, enchufe):
    from httpx import ASGITransport, AsyncClient
    snap = two_tabs(enchufe)
    snap["agents"].append({"pane_id": "w1:p2", "tab_id": "w1:t2", "workspace_id": "w1", "agent": "claude",
                                    "agent_status": "idle", "state_change_seq": 1})
    aplicar_snapshot(enchufe, snap)
    order = []
    orig_mp = enchufe.mandar_prompt
    orig_c = enchufe.cerrar

    async def slow_mp(sesion_id, texto, **kw):
        order.append("prompt-start")
        await asyncio.sleep(0.05)
        order.append("prompt-end")
        return await orig_mp(sesion_id, texto, **kw)

    async def slow_c(objetivo_id):
        order.append("close")
        return await orig_c(objetivo_id)

    enchufe.mandar_prompt = slow_mp
    enchufe.cerrar = slow_c

    async def go():
        async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 5000)), base_url="https://t", headers={"Origin": "https://t"}) as c:
            await c.post("/api/login", json={"pin": "43215678"})
            h = (await c.post("/api/close/preview", json={"tipo": "tab", "target_id": "w1:t2"})).json()["huella"]
            msg = asyncio.create_task(c.post("/api/mensaje/execute", json={
                "id": "mensaje-id-1", "pane_id": "w1:p2", "texto": "hola", "origen": "manual"}))
            await asyncio.sleep(0.01)
            clo = await c.post("/api/close/execute", json={
                "id": ID, "tipo": "tab", "target_id": "w1:t2", "huella": h, "origen": "manual",
                "sin_guardar": True})
            await msg
            return clo.status_code

    code = asyncio.run(go())
    assert order[:2] == ["prompt-start", "prompt-end"] and order[-1] == "close"
    assert code in (200, 409)


def test_huella_covers_terminal_identity_and_labels(authed, enchufe):
    snap = two_tab_agents(enchufe)
    h = preview(authed, target="w1:t2").json()["huella"]
    snap["agents"][-1]["terminal_id"] = "otra-terminal"
    aplicar_snapshot(enchufe, snap)
    assert execute(authed, h, target_id="w1:t2").status_code == 409
    snap["agents"][-1].pop("terminal_id")
    h = preview(authed, target="w1:t2").json()["huella"]
    snap["tabs"][-1]["label"] = "Reusado"
    aplicar_snapshot(enchufe, snap)
    assert execute(authed, h, target_id="w1:t2").status_code == 409
    snap["tabs"][-1]["label"] = "Terminales"
    h = preview(authed, target="w1:t2").json()["huella"]
    snap["workspaces"][1]["label"] = "Otro"
    aplicar_snapshot(enchufe, snap)
    assert execute(authed, h, target_id="w1:t2").status_code == 409
    assert closes(enchufe) == []


def test_protected_tab_without_claude_closes(authed, enchufe):
    protected_two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("node", 42)))
    body = preview(authed, target="w1:t2").json()
    assert body["bloqueantes"] == [] and body["cierra_workspace"] is False
    r = execute(authed, body["huella"], target_id="w1:t2")
    assert r.status_code == 200 and r.json()["closed_tab_id"] == "w1:t2"
    assert closes(enchufe) == [("cerrar", "w1:t2")]


def test_protected_tab_at_shell_prompt_closes(authed, enchufe):
    protected_two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1)))
    h = preview(authed, target="w1:t2").json()["huella"]
    assert execute(authed, h, target_id="w1:t2").status_code == 200


def test_protected_tab_with_marked_claude_is_403(authed, enchufe):
    snap = protected_two_tabs(enchufe)
    snap["agents"].append({"pane_id": "w1:p2", "tab_id": "w1:t2", "workspace_id": "w1", "agent": "claude",
                           "agent_status": "idle", "state_change_seq": 1})
    aplicar_snapshot(enchufe, snap)
    r = preview(authed, target="w1:t2")
    assert r.status_code == 403 and "Claude" in r.json()["detail"]
    assert execute(authed, "h" * 64, target_id="w1:t2").status_code == 403
    assert not enchufe.calls_of("proceso")
    assert closes(enchufe) == []


@pytest.mark.parametrize("raw", [
    proceso_json(("bash", 1), ("claude", 42)),
    proceso_argv_json(("bash", 1, ["bash"]), ("node", 42, ["node", "/usr/lib/node_modules/@anthropic-ai/claude-code/cli.js"])),
    proceso_argv_json(("bash", 1, ["bash"]), ("npx", 42, ["npx", "claude"])),
    proceso_argv_json(("bash", 1, ["bash"]), ("2.1.316", 42, ["/home/u/.local/share/claude/versions/2.1.316"])),
])
def test_protected_tab_with_unmarked_claude_is_403_in_preview_and_execute(authed, enchufe, raw):
    protected_two_tabs(enchufe)
    set_proceso_todos(enchufe, raw)
    r = preview(authed, target="w1:t2")
    assert r.status_code == 403 and "Claude" in r.json()["detail"]
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("node", 42)))
    h = preview(authed, target="w1:t2").json()["huella"]
    set_proceso_todos(enchufe, raw)
    r = execute(authed, h, target_id="w1:t2")
    assert r.status_code == 403 and "Claude" in r.json()["detail"]
    assert closes(enchufe) == []


def test_protected_tab_claude_marked_between_preview_and_execute(authed, enchufe):
    snap = protected_two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1)))
    h = preview(authed, target="w1:t2").json()["huella"]
    snap["agents"].append({"pane_id": "w1:p2", "tab_id": "w1:t2", "workspace_id": "w1", "agent": "claude",
                           "agent_status": "idle", "state_change_seq": 1})
    aplicar_snapshot(enchufe, snap)
    r = execute(authed, h, target_id="w1:t2")
    assert r.status_code == 403 and closes(enchufe) == []


def test_protected_tab_claude_starts_after_locks_are_taken(authed, enchufe):
    protected_two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1)))
    h = preview(authed, target="w1:t2").json()["huella"]
    reads = []

    async def late_proceso(sesion_id):
        reads.append(sesion_id)
        return info_de_process_json(proceso_json(("bash", 1), ("claude", 42)))

    enchufe.proceso = late_proceso
    r = execute(authed, h, target_id="w1:t2")
    assert r.status_code == 403 and reads and closes(enchufe) == []


@pytest.mark.parametrize("raw", [NoDisponible("sin respuesta"), "{}", "no es json",
                                 json.dumps({"result": {"process_info": {"foreground_processes": []}}})])
def test_protected_tab_with_unreadable_process_is_rejected(authed, enchufe, raw):
    protected_two_tabs(enchufe)
    set_proceso_todos(enchufe, raw)
    r = preview(authed, target="w1:t2")
    assert r.status_code == 403 and "No pude ver" in r.json()["detail"]
    set_proceso_todos(enchufe, proceso_json(("bash", 1)))
    h = preview(authed, target="w1:t2").json()["huella"]
    set_proceso_todos(enchufe, raw)
    assert execute(authed, h, target_id="w1:t2").status_code == 403
    assert closes(enchufe) == []


def test_protected_tab_with_one_unreadable_pane_among_many_is_rejected(authed, enchufe):
    snap = protected_two_tabs(enchufe)
    snap["panes"].append({"pane_id": "w1:p3", "tab_id": "w1:t2", "workspace_id": "w1"})
    aplicar_snapshot(enchufe, snap)
    enchufe.procesos["w1:p3"] = info_de_process_json("{}")
    assert preview(authed, target="w1:t2").status_code == 403


def test_protected_tab_without_panes_is_rejected(authed, enchufe):
    snap = protected_two_tabs(enchufe)
    snap["panes"] = [p for p in snap["panes"] if p["pane_id"] != "w1:p2"]
    aplicar_snapshot(enchufe, snap)
    assert preview(authed, target="w1:t2").status_code == 403
    assert closes(enchufe) == []


def test_protected_workspace_and_its_last_tab_stay_untouchable(authed, enchufe):
    protected_two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1)))
    r = preview(authed, "workspace", "w1")
    assert r.status_code == 400 and "protegido" in r.json()["detail"]
    assert execute(authed, "h", tipo="workspace", target_id="w1").status_code == 400
    snap = make_snapshot()
    snap["workspaces"][1]["label"] = "Super orquestador"
    aplicar_snapshot(enchufe, snap)
    snap["agents"] = [a for a in snap["agents"] if a["pane_id"] != "w1:p1"]
    aplicar_snapshot(enchufe, snap)
    r = preview(authed, "tab", "w1:t1")
    assert r.status_code == 400 and "protegido" in r.json()["detail"]
    assert execute(authed, "h", target_id="w1:t1").status_code == 400
    assert closes(enchufe) == []


def test_tab_renamed_into_protected_workspace_after_preview_is_checked_fresh(authed, enchufe):
    snap = two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1)))
    h = preview(authed, target="w1:t2").json()["huella"]
    snap["workspaces"][1]["label"] = "Super orquestador"
    aplicar_snapshot(enchufe, snap)
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("claude", 42)))
    assert execute(authed, h, target_id="w1:t2").status_code == 403
    assert closes(enchufe) == []


def test_protected_tab_with_orchestrator_pane_is_400(cfg, tmp_path, enchufe, handoffs):
    from fastapi.testclient import TestClient
    from orquestador.app import create_app
    from orquestador.state import StateStore
    from conftest import PIN
    protected_two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1)))
    app = create_app(cfg, b"s", StateStore(tmp_path), enchufe=enchufe, dist=tmp_path / "x", handoffs_dir=handoffs,
                     uploads_dir=tmp_path / "u", env_pane_id="w1:p2")
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 1)) as c:
        c.post("/api/login", json={"pin": PIN})
        r = c.post("/api/close/preview", json={"tipo": "tab", "target_id": "w1:t2"})
        assert r.status_code == 400 and "orquestador" in r.json()["detail"]
    assert closes(enchufe) == []


def test_unmarked_node_claude_blocks_closing_a_normal_tab(authed, enchufe):
    two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_argv_json(
        ("bash", 1, ["bash"]), ("node", 42, ["node", "/x/@anthropic-ai/claude-code/cli.js"])))
    body = preview(authed, target="w1:t2").json()
    assert body["bloqueantes"] == [{"pane_id": "w1:p2", "status": "unknown"}]
    assert execute(authed, body["huella"], target_id="w1:t2").status_code == 409
    assert closes(enchufe) == []


def test_pane_count_mismatch_fails_closed(authed, enchufe):
    snap = two_tabs(enchufe)
    snap["tabs"][-1]["pane_count"] = 3
    aplicar_snapshot(enchufe, snap)
    r = preview(authed, target="w1:t2")
    assert r.status_code == 409 and "todos sus paneles" in r.json()["detail"]
    snap["tabs"][-1]["pane_count"] = 1
    snap["workspaces"][1]["pane_count"] = 9
    aplicar_snapshot(enchufe, snap)
    assert preview(authed, "workspace", "w1").status_code == 409
    assert closes(enchufe) == []


def test_tab_without_known_workspace_is_409_not_500(authed, enchufe):
    import copy

    snap = two_tabs(enchufe)
    snap["tabs"][-1]["workspace_id"] = "w77"
    snap["panes"][-1]["workspace_id"] = "w77"
    aplicar_snapshot(enchufe, snap)
    assert preview(authed, target="w1:t2").status_code in (404, 409)
    two_tabs(enchufe)
    cierres = authed.app.state.guardado.cierres
    orig = cierres._snapshot

    async def sin_workspace_id():
        s = copy.deepcopy(await orig())
        del next(t for t in s["tabs"] if t["tab_id"] == "w1:t2")["workspace_id"]
        return s

    cierres._snapshot = sin_workspace_id
    assert preview(authed, target="w1:t2").status_code == 409


def test_claude_in_a_terminal_without_agent_blocks_as_unknown(authed, enchufe):
    two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("claude", 42)))
    body = preview(authed, target="w1:t2").json()
    assert body["bloqueantes"] == [{"pane_id": "w1:p2", "status": "unknown"}]
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("node", 42)))
    h = preview(authed, target="w1:t2").json()["huella"]
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("claude", 42)))
    r = execute(authed, h, target_id="w1:t2")
    assert r.status_code == 409 and r.json()["bloqueantes"] == [{"pane_id": "w1:p2", "status": "unknown"}]
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("python", 42)))
    assert execute(authed, h, target_id="w1:t2").status_code == 409
    assert closes(enchufe) == []


def test_forzar_closes_a_shell_running_claude_by_hand(authed, enchufe):
    two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("node", 42)))
    h = preview(authed, target="w1:t2").json()["huella"]
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("claude", 42)))
    h = preview(authed, target="w1:t2").json()["huella"]
    cierres = authed.app.state.guardado.cierres
    body = CierreBody(id=ID, tipo="tab", target_id="w1:t2", huella=h, origen="manual")
    with pytest.raises(TraspasoError) as exc:
        asyncio.run(cierres.execute(body))
    assert exc.value.status == 409 and closes(enchufe) == []
    out = asyncio.run(cierres.execute(body, forzar=True))
    assert out["ok"] is True and closes(enchufe) == [("cerrar", "w1:t2")]


@pytest.mark.parametrize("sin_guardar", [True, False])
def test_http_forzar_closes_a_shell_running_claude_by_hand(authed, enchufe, sin_guardar):
    two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("claude", 42)))
    h = preview(authed, target="w1:t2").json()["huella"]
    r = execute(authed, h, target_id="w1:t2", sin_guardar=sin_guardar)
    assert r.status_code == 409 and r.json()["bloqueantes"] == [{"pane_id": "w1:p2", "status": "unknown"}]
    assert closes(enchufe) == []
    r = execute(authed, h, target_id="w1:t2", sin_guardar=sin_guardar, forzar=True)
    assert r.status_code == 200 and closes(enchufe) == [("cerrar", "w1:t2")]


@pytest.mark.parametrize("sin_guardar", [True, False])
@pytest.mark.parametrize("status", ["working", "blocked"])
def test_http_forzar_never_closes_a_busy_agent(authed, enchufe, status, sin_guardar):
    snap = two_tab_agents(enchufe)
    for src in ("agents", "panes"):
        for a in snap[src]:
            if a["pane_id"] == "w1:p2" and "agent" in a:
                a["agent_status"] = status
    aplicar_snapshot(enchufe, snap)
    h = preview(authed, target="w1:t2").json()["huella"]
    r = execute(authed, h, target_id="w1:t2", sin_guardar=sin_guardar, forzar=True)
    assert closes(enchufe) == []
    if status == "blocked" and not sin_guardar:
        assert r.status_code == 200 and "guardando" in r.json()  # el diálogo abierto espera al usuario en el lote
    else:
        assert r.status_code == 409


class _FondoActivo:
    def for_session(self, sid):
        return [{"tarea": "x"}]


@pytest.mark.parametrize("sin_guardar", [True, False])
def test_http_forzar_never_closes_an_agent_with_background_work(authed, enchufe, sin_guardar):
    snap = two_tab_agents(enchufe)
    snap["agents"][-1]["agent_session"] = {"kind": "id", "value": SID}
    aplicar_snapshot(enchufe, snap)
    authed.app.state.guardado.cierres.fondo = _FondoActivo()
    h = preview(authed, target="w1:t2").json()["huella"]
    r = execute(authed, h, target_id="w1:t2", sin_guardar=sin_guardar, forzar=True)
    assert closes(enchufe) == []
    assert r.status_code == 409 and r.json()["bloqueantes"] == [{"pane_id": "w1:p2", "status": "fondo"}]


def test_rejected_forced_close_logs_that_it_was_forced(authed, enchufe, caplog):
    snap = two_tab_agents(enchufe)
    for a in snap["agents"] + snap["panes"]:
        if a["pane_id"] == "w1:p2" and "agent" in a:
            a["agent_status"] = "working"
    aplicar_snapshot(enchufe, snap)
    h = preview(authed, target="w1:t2").json()["huella"]
    with caplog.at_level("INFO", logger="orquestador"):
        assert execute(authed, h, target_id="w1:t2", sin_guardar=True, forzar=True).status_code == 409
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "w1:p2=working" in msgs and "forzar=publico" in msgs


@pytest.mark.parametrize("sin_guardar", [True, False])
def test_rejected_close_is_logged_with_pane_and_reason(authed, enchufe, caplog, sin_guardar):
    two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1), ("claude", 42)))
    h = preview(authed, target="w1:t2").json()["huella"]
    with caplog.at_level("INFO", logger="orquestador"):
        assert execute(authed, h, target_id="w1:t2", sin_guardar=sin_guardar).status_code == 409
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "w1:p2" in msgs and "unknown" in msgs and "SECRETO" not in msgs


def test_close_ok_but_snapshot_after_fails_still_succeeds_and_records(authed, enchufe):
    snap = two_tab_agents(enchufe)
    h = preview(authed, target="w1:t2").json()["huella"]
    _orig_cerrar = enchufe.cerrar
    async def _cerrar_y_caer(objetivo_id):
        await _orig_cerrar(objetivo_id)
        enchufe.caer()
    enchufe.cerrar = _cerrar_y_caer
    r = execute(authed, h, target_id="w1:t2")
    assert r.status_code == 200 and r.json()["ok"] is True and "aviso" in r.json()
    assert [c["id"] for c in authed.app.state.state.cierres()] == [ID]
    assert execute(authed, h, target_id="w1:t2").status_code == 409


def test_cwd_is_sanitized_in_preview_and_record(authed, enchufe, tmp_path):
    snap = two_tab_agents(enchufe)
    snap["agents"][-1]["cwd"] = "/a‮b\nc"
    aplicar_snapshot(enchufe, snap)
    snap["agents"][-1]["agent_session"] = {"kind": "id", "value": SID}
    aplicar_snapshot(enchufe, snap)
    body = preview(authed, target="w1:t2").json()
    assert body["panes"][0]["cwd"] == "/a b c"
    r = execute(authed, body["huella"], target_id="w1:t2")
    assert r.json()["sesiones"][0]["cwd"] == "/a b c"
    authed.app.state.state.flush()
    assert "‮" not in (tmp_path / "state.json").read_text() if (tmp_path / "state.json").exists() else True


def test_close_endpoints_require_a_session(client):
    assert client.post("/api/close/preview", json={"tipo": "tab", "target_id": "w1:t1"}).status_code == 401
    assert client.post("/api/close/execute", json={"id": ID, "tipo": "tab", "target_id": "w1:t1", "huella": "h",
                                                   "origen": "manual"}).status_code == 401


def test_traspaso_that_creates_waits_for_the_structure_lock(app, enchufe, handoffs):
    from httpx import ASGITransport, AsyncClient
    brief = handoffs / "2026-10-31-x.md"
    brief.write_text("# Traspaso")
    enchufe.proximos_ids = [(None, "w2:t3", "w2:p5")]
    body = {"origen": "Uno (w1:p1)", "destino": "Dos", "por_que": "x", "resumen_brief": "y", "destino_tipo": "tab_nuevo",
            "workspace_id": "w2", "label": "Logout", "cwd": "/tmp", "agent_name": "login-logout", "brief_path": str(brief)}

    async def go():
        async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 5000)), base_url="https://t", headers={"Origin": "https://t"}) as c:
            await c.post("/api/login", json={"pin": "43215678"})
            async with app.state.locks.structure:
                task = asyncio.create_task(c.post("/api/traspaso/execute", json=body))
                await asyncio.sleep(0.1)
                assert enchufe.calls == []
            return (await task).status_code

    assert asyncio.run(go()) == 200


def test_execute_rechaza_origen_plan_desde_afuera(authed, enchufe):
    h = preview(authed).json()["huella"]
    assert execute(authed, h, origen="plan").status_code == 400
    assert closes(enchufe) == []


def test_execute_sin_sin_guardar_pide_guardar_y_devuelve_el_lote(authed, enchufe):
    two_tab_agents(enchufe)
    h = preview(authed, target="w1:t2").json()["huella"]
    r = execute(authed, h, target_id="w1:t2", sin_guardar=False)
    assert r.status_code == 200 and r.json()["guardando"]["targets"][0]["panes"][0]["estado"] == "guardando"
    assert not closes(enchufe)
    assert authed.get("/api/close/guardado").json()["lotes"][0]["id"] == ID
    assert authed.post("/api/close/guardado", json={"lote_id": ID, "accion": "cerrar_igual"}).status_code == 409
    assert authed.post("/api/close/guardado", json={"lote_id": ID, "accion": "otra"}).status_code == 400


def test_preview_dice_si_es_protegido(authed, enchufe):
    protected_two_tabs(enchufe)
    set_proceso_todos(enchufe, proceso_json(("bash", 1)))
    assert preview(authed, target="w1:t2").json()["protegido"] is True
    assert preview(authed, tipo="tab", target="w2:t1").json()["protegido"] is False
