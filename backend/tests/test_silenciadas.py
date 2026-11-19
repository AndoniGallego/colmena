from conftest import SID
from orquestador.push import PushService
from orquestador.state import StateStore
from test_push import Clock, board


class FakeQueue:
    def __init__(self):
        self.items = []

    def put_nowait(self, item):
        self.items.append(item)


def test_alta_baja_e_idempotencia(tmp_path):
    s = StateStore(tmp_path)
    assert s.silenciadas() == []
    s.set_silenciada("a", True)
    s.set_silenciada("a", True)
    assert s.silenciadas() == ["a"]
    s.set_silenciada("a", False)
    s.set_silenciada("a", False)
    assert s.silenciadas() == []


def test_persiste_al_recargar(tmp_path):
    s = StateStore(tmp_path)
    s.set_silenciada("a", True)
    s.set_silenciada("b", True)
    s.flush()
    assert StateStore(tmp_path).silenciadas() == ["a", "b"]


def test_tope_500_descarta_los_mas_viejos(tmp_path):
    s = StateStore(tmp_path)
    for i in range(505):
        s.set_silenciada(f"s{i}", True)
    got = s.silenciadas()
    assert len(got) == 500
    assert got[0] == "s5" and got[-1] == "s504"


def _servicio_silenciado(tmp_path):
    svc = PushService(tmp_path, sender=lambda *a, **k: None, clock=Clock())
    svc.silenciada = lambda sid: sid == SID
    return svc


def test_silenciada_no_dispara_done(tmp_path):
    svc = _servicio_silenciado(tmp_path)
    assert svc.observe(board("working"), board("idle")) == []


def test_silenciada_si_dispara_blocked_y_asks(tmp_path):
    svc = _servicio_silenciado(tmp_path)
    assert [e["kind"] for e in svc.observe(board("working"), board("blocked"))] == ["blocked"]
    svc.clock.now += 100
    events = svc.observe(board("working"), board("idle", asks=True, pending="¿Seguimos?"))
    assert [e["kind"] for e in events] == ["asks"]


def test_no_silenciada_si_dispara_done(tmp_path):
    svc = PushService(tmp_path, sender=lambda *a, **k: None, clock=Clock())
    assert [e["kind"] for e in svc.observe(board("working"), board("idle"))] == ["done"]


def test_put_silencio_alta_baja_y_lista_en_orden(authed):
    r = authed.put(f"/api/sesiones/{SID}/silencio", json={"on": True})
    assert r.status_code == 200
    assert authed.get("/api/tablero/orden").json()["silenciadas"] == [SID]
    authed.put(f"/api/sesiones/{SID}/silencio", json={"on": False})
    assert authed.get("/api/tablero/orden").json()["silenciadas"] == []


def test_put_silencio_rechaza_sid_invalido(authed):
    assert authed.put("/api/sesiones/a$b/silencio", json={"on": True}).status_code == 400
    assert authed.put("/api/sesiones/" + "x" * 81 + "/silencio", json={"on": True}).status_code == 400


def test_put_silencio_rechaza_body_invalido(authed):
    assert authed.put(f"/api/sesiones/{SID}/silencio", json={"on": "si"}).status_code == 422


def test_put_silencio_requiere_login(client):
    assert client.put(f"/api/sesiones/{SID}/silencio", json={"on": True}).status_code == 401


def test_put_silencio_emite_sse(authed, app):
    q = FakeQueue()
    app.state.hub.subscribers.add(q)
    authed.put(f"/api/sesiones/{SID}/silencio", json={"on": True})
    assert ("silenciadas", {"silenciadas": [SID]}) in q.items
