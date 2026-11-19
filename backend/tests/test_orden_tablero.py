import pytest
from pydantic import ValidationError
from orquestador.orden_tablero import OrdenTableroBody, normalizar_orden
from orquestador.state import StateStore


class FakeQueue:
    def __init__(self):
        self.items = []

    def put_nowait(self, item):
        self.items.append(item)


def test_state_store_orden_vacio(tmp_path):
    s = StateStore(tmp_path)
    assert s.orden_tablero() == []
    s.set_orden_tablero(["w1", "w2"])
    assert s.orden_tablero() == ["w1", "w2"]
    s.set_orden_tablero([])
    assert s.orden_tablero() == []


def test_get_vacio(authed):
    assert authed.get("/api/tablero/orden").json() == {"orden": [], "pestanas": {}, "plegadas": [], "silenciadas": []}


def test_put_y_get(authed):
    r = authed.put("/api/tablero/orden", json={"orden": ["w2", "w1"]})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert authed.get("/api/tablero/orden").json()["orden"] == ["w2", "w1"]


@pytest.mark.parametrize(
    "body",
    [
        {"orden": "x"},
        {"orden": [""]},
        {"orden": ["x" * 201]},
        {"orden": ["ok"] * 201},
    ],
)
def test_validacion_422(authed, body):
    assert authed.put("/api/tablero/orden", json=body).status_code == 422


def test_dedup(authed):
    r = authed.put("/api/tablero/orden", json={"orden": ["a", "b", "a", "c", "b"]})
    assert r.status_code == 200
    assert authed.get("/api/tablero/orden").json()["orden"] == ["a", "b", "c"]


def test_vacio_borra(authed):
    authed.put("/api/tablero/orden", json={"orden": ["w1"]})
    assert authed.put("/api/tablero/orden", json={"orden": []}).status_code == 200
    assert authed.get("/api/tablero/orden").json() == {"orden": [], "pestanas": {}, "plegadas": [], "silenciadas": []}


def test_requiere_login(client):
    assert client.get("/api/tablero/orden").status_code == 401
    assert client.put("/api/tablero/orden", json={"orden": []}).status_code == 401


def test_emite_sse(authed, app):
    q = FakeQueue()
    app.state.hub.subscribers.add(q)
    r = authed.put("/api/tablero/orden", json={"orden": ["w1", "w2"]})
    assert r.status_code == 200
    assert ("orden_tablero", {"orden": ["w1", "w2"]}) in q.items


def test_normalizar_orden_dedup():
    assert normalizar_orden(["x", "y", "x"]) == ["x", "y"]


def test_modelo_rechaza_no_lista():
    with pytest.raises(ValidationError):
        OrdenTableroBody.model_validate({"orden": 1})
