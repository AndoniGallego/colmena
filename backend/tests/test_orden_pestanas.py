import pytest
from pydantic import ValidationError
from orquestador.orden_tablero import OrdenPestanasBody, normalizar_grupo
from orquestador.state import StateStore


class FakeQueue:
    def __init__(self):
        self.items = []

    def put_nowait(self, item):
        self.items.append(item)


def test_state_orden_pestanas(tmp_path):
    s = StateStore(tmp_path)
    assert s.orden_pestanas() == {}
    s.set_orden_pestanas_grupo("w1:t1", ["p1", "p2"])
    assert s.orden_pestanas() == {"w1:t1": ["p1", "p2"]}
    s.set_orden_pestanas_grupo("w1:t1", [])
    assert s.orden_pestanas() == {}


def test_get_incluye_pestanas(authed):
    assert authed.get("/api/tablero/orden").json() == {"orden": [], "pestanas": {}, "plegadas": [], "silenciadas": []}


def test_put_y_get_pestanas(authed):
    r = authed.put("/api/tablero/orden-pestanas", json={"grupo": "w1:t1", "orden": ["p2", "p1"]})
    assert r.status_code == 200 and r.json() == {"ok": True}
    body = authed.get("/api/tablero/orden").json()
    assert body["pestanas"] == {"w1:t1": ["p2", "p1"]}


def test_pestanas_vacio_borra(authed):
    authed.put("/api/tablero/orden-pestanas", json={"grupo": "w1:t1", "orden": ["p1"]})
    assert authed.put("/api/tablero/orden-pestanas", json={"grupo": "w1:t1", "orden": []}).status_code == 200
    assert authed.get("/api/tablero/orden").json()["pestanas"] == {}


@pytest.mark.parametrize(
    "body",
    [
        {"grupo": "", "orden": []},
        {"grupo": "x" * 201, "orden": []},
        {"grupo": "g", "orden": "x"},
        {"grupo": "g", "orden": [""]},
        {"grupo": "g", "orden": ["x" * 201]},
        {"grupo": "g", "orden": ["ok"] * 201},
    ],
)
def test_pestanas_validacion_422(authed, body):
    assert authed.put("/api/tablero/orden-pestanas", json=body).status_code == 422


def test_tope_grupos(tmp_path):
    s = StateStore(tmp_path)
    for i in range(201):
        s.set_orden_pestanas_grupo(f"g{i:03d}", [f"p{i}"])
    p = s.orden_pestanas()
    assert len(p) == 200
    assert "g000" not in p
    assert "g200" in p


def test_emite_sse_pestanas(authed, app):
    q = FakeQueue()
    app.state.hub.subscribers.add(q)
    r = authed.put("/api/tablero/orden-pestanas", json={"grupo": "w1:t1", "orden": ["p1"]})
    assert r.status_code == 200
    assert ("orden_pestanas", {"grupo": "w1:t1", "orden": ["p1"]}) in q.items


def test_reset_orden_limpia_pestanas(authed, app):
    authed.put("/api/tablero/orden-pestanas", json={"grupo": "w1:t1", "orden": ["p1"]})
    authed.put("/api/tablero/orden", json={"orden": ["w1"]})
    q = FakeQueue()
    app.state.hub.subscribers.add(q)
    authed.put("/api/tablero/orden", json={"orden": []})
    assert authed.get("/api/tablero/orden").json() == {"orden": [], "pestanas": {}, "plegadas": [], "silenciadas": []}
    assert any(ev[0] == "orden_pestanas" and ev[1].get("grupo") == "" for ev in q.items)


def test_normalizar_grupo():
    assert normalizar_grupo("w1:t1") == "w1:t1"
    with pytest.raises(ValueError):
        normalizar_grupo("")


def test_modelo_pestanas_rechaza_no_lista():
    with pytest.raises(ValidationError):
        OrdenPestanasBody.model_validate({"grupo": "g", "orden": 1})
