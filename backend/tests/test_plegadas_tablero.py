import pytest
from pydantic import ValidationError
from orquestador.orden_tablero import PlegadasBody, normalizar_orden
from orquestador.state import StateStore


class FakeQueue:
    def __init__(self):
        self.items = []

    def put_nowait(self, item):
        self.items.append(item)


def test_state_store_plegadas_vacio(tmp_path):
    s = StateStore(tmp_path)
    assert s.plegadas() == []
    s.set_plegadas(["w1"])
    assert s.plegadas() == ["w1"]
    s.set_plegadas([])
    assert s.plegadas() == []


def test_get_incluye_plegadas(authed):
    assert authed.get("/api/tablero/orden").json() == {"orden": [], "pestanas": {}, "plegadas": [], "silenciadas": []}


def test_put_y_get(authed):
    r = authed.put("/api/tablero/plegadas", json={"plegadas": ["w2", "w1"]})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert authed.get("/api/tablero/orden").json()["plegadas"] == ["w2", "w1"]


@pytest.mark.parametrize(
    "body",
    [
        {"plegadas": "x"},
        {"plegadas": [""]},
        {"plegadas": ["x" * 201]},
        {"plegadas": ["ok"] * 201},
    ],
)
def test_validacion_422(authed, body):
    assert authed.put("/api/tablero/plegadas", json=body).status_code == 422


def test_dedup(authed):
    r = authed.put("/api/tablero/plegadas", json={"plegadas": ["a", "b", "a", "c", "b"]})
    assert r.status_code == 200
    assert authed.get("/api/tablero/orden").json()["plegadas"] == ["a", "b", "c"]


def test_requiere_login(client):
    assert client.put("/api/tablero/plegadas", json={"plegadas": [], "silenciadas": []}).status_code == 401


def test_emite_sse(authed, app):
    q = FakeQueue()
    app.state.hub.subscribers.add(q)
    r = authed.put("/api/tablero/plegadas", json={"plegadas": ["w1"]})
    assert r.status_code == 200
    assert ("plegadas", {"plegadas": ["w1"]}) in q.items


def test_modelo_rechaza_no_lista():
    with pytest.raises(ValidationError):
        PlegadasBody.model_validate({"plegadas": 1})


def test_normalizar_plegadas_dedup():
    assert normalizar_orden(["x", "y", "x"]) == ["x", "y"]
