import pytest

from conftest import ORIGIN, SID, make_snapshot
from orquestador.enchufe import FakeTerminales


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


def test_board_endpoint(authed):
    board = authed.get("/api/board").json()
    assert board["self_pane_id"] == "w2:p9"
    agents = [a for w in board["workspaces"] for t in w["tabs"] for a in t["agents"]]
    assert [a["pane_id"] for a in agents] == ["w1:p1"]


def test_digest_endpoint(authed):
    r = authed.get(f"/api/sessions/{SID}/digest?turns=2")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Título nuevo" and len(body["turns"]) == 2
    assert authed.get("/api/sessions/nada/digest").status_code == 404


def test_focus(authed, enchufe):
    assert authed.post("/api/focus", json={"tab_id": "w1:t1"}).status_code == 200
    assert enchufe.calls_of("enfocar") == [("enfocar", "w1:t1")]
    assert authed.post("/api/focus", json={"tab_id": "w9:t9"}).status_code == 404
    assert authed.post("/api/focus", json={"tab_id": "--evil"}).status_code == 422


def test_focus_herdr_caido_502_y_noexiste_404(authed, enchufe):
    enchufe.caer()
    assert authed.post("/api/focus", json={"tab_id": "w1:t1"}).status_code == 502
    enchufe.volver()
    assert authed.post("/api/focus", json={"tab_id": "w9:t9"}).status_code == 404
    assert authed.post("/api/focus", json={"tab_id": "w1:t1\n"}).status_code == 422


def test_limpieza_candidatos_herdr_caido_502(authed, enchufe):
    enchufe.caer()
    assert authed.get("/api/limpieza/candidatos").status_code == 502


def test_spa_fallback_without_build(client):
    r = client.get("/")
    assert r.status_code == 200 and "Falta el build" in r.text
    assert client.get("/api/nope").status_code == 404


def test_spa_serves_dist(cfg, tmp_path, enchufe):
    from fastapi.testclient import TestClient
    from orquestador.app import create_app
    from orquestador.state import StateStore
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<h1>app</h1>")
    (dist / "assets" / "a.js").write_text("1")
    app = create_app(cfg, b"s", StateStore(tmp_path), enchufe=enchufe, dist=dist,
                     uploads_dir=tmp_path / "uploads")
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 1)) as c:
        assert c.get("/assets/a.js").text == "1"
        assert c.get("/cualquier/ruta").text == "<h1>app</h1>"
        assert c.get("/notch").text == "<h1>app</h1>"
        assert "app" in c.get("/../../etc/passwd").text
