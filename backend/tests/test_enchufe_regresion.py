"""Regresión: ids Herdr guardados (wC:p1 / wC:t1 / wC) siguen resolviendo con FakeTerminales."""

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.push import PushService
from orquestador.state import StateStore


def snap_wc():
    return {
        "focused_tab_id": "wC:t1",
        "workspaces": [{"workspace_id": "wC", "number": 1, "label": "Colmena", "agent_status": "idle"}],
        "tabs": [{"tab_id": "wC:t1", "workspace_id": "wC", "label": "uno"}],
        "agents": [{"pane_id": "wC:p1", "tab_id": "wC:t1", "workspace_id": "wC", "agent": "claude",
                    "agent_status": "idle", "cwd": "/tmp", "agent_session": {"kind": "id", "value": "aaaaaaaa-1111"}}],
        "panes": [{"pane_id": "wC:p1", "tab_id": "wC:t1", "workspace_id": "wC"}],
    }


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(snap_wc(), poll=0.01)


@pytest.fixture
def authed(cfg, tmp_path, handoffs, enchufe):
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    hub.self_pane_id = "w2:p9"
    push = PushService(tmp_path)
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads",
                     enchufe=enchufe, push=push)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        c.push = push
        yield c


def test_mensaje_incierto_conserva_ids(authed, enchufe, tmp_path):
    st = authed.app.state.state
    mid = "msg-wc-reg01"
    st.data.update({
        "cierres": [{"id": "c-wc-1", "ok": True, "target_id": "wC:t1", "tipo": "tab", "pane_id": "wC:p1"}],
        "traspasos": [{"brief_path": "/x", "ok": True, "pane_id": "wC:p1"}],
        "mensajes": [{"id": mid, "pane_id": "wC:p1", "incierto": True, "ok": False, "texto": "x", "origen": "manual"}],
        "teclas": [["wC:p1", "toolu_1"]],
    })
    st.save()
    r = authed.post("/api/mensaje/execute", json={"id": mid, "pane_id": "wC:p1", "texto": "otra", "origen": "manual"})
    assert r.status_code == 409 and "ya haya llegado" in r.json()["detail"]
    assert enchufe.calls_of("mandar_prompt") == []
    assert st.cierres()[-1]["target_id"] == "wC:t1"


def test_avisos_y_auditoria_se_leen_sin_migrar(authed, enchufe):
    authed.push.avisos.add("done", "t", "", True, pane_id="wC:p1")
    authed.app.state.tacciones.audit.write({"accion": "teclas", "pane_id": "wC:p1", "ok": True, "ts": 1.0})
    avisos = authed.get("/api/avisos").json()["items"]
    assert avisos[-1]["pane_id"] == "wC:p1"
    entradas = authed.get("/api/terminales/auditoria").json()["entradas"]
    assert entradas[-1]["pane_id"] == "wC:p1"
