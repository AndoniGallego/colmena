import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import ORIGIN
from orquestador.notas import NotasStore
from orquestador.notas_api import build_router


def test_crud_completo(authed, app):
    r = authed.post("/api/notas", json={"tipo": "recordatorio", "texto": "Revisar MR"}, headers=ORIGIN)
    assert r.status_code == 201
    nid = r.json()["id"]
    assert authed.get("/api/notas").json()["pendientes"] == 1
    assert authed.patch(f"/api/notas/{nid}", json={"hecha": True}, headers=ORIGIN).json()["hecha_at"]
    assert authed.delete(f"/api/notas/{nid}", headers=ORIGIN).status_code == 204
    assert authed.get("/api/notas").json()["notas"] == []


def test_patch_texto_y_tipo(authed):
    nid = authed.post("/api/notas", json={"tipo": "apunte", "texto": "uno"}, headers=ORIGIN).json()["id"]
    r = authed.patch(f"/api/notas/{nid}", json={"texto": "dos", "tipo": "recordatorio"}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["texto"] == "dos" and r.json()["tipo"] == "recordatorio"
    assert authed.patch(f"/api/notas/{nid}", json={}, headers=ORIGIN).status_code == 422


def test_sin_sesion_401(client):
    assert client.get("/api/notas").status_code == 401


@pytest.mark.parametrize("texto", ["", "   ", "a" * 4001])
def test_texto_invalido_422(authed, texto):
    assert authed.post("/api/notas", json={"tipo": "apunte", "texto": texto}, headers=ORIGIN).status_code == 422


def test_tipo_invalido_422(authed):
    assert authed.post("/api/notas", json={"tipo": "otro", "texto": "x"}, headers=ORIGIN).status_code == 422


def test_desconocida_404_e_id_raro_422(authed):
    assert authed.patch("/api/notas/n_noexiste1", json={"hecha": True}, headers=ORIGIN).status_code == 404
    assert authed.delete("/api/notas/n_noexiste1", headers=ORIGIN).status_code == 404
    assert authed.delete("/api/notas/..%2Fx", headers=ORIGIN).status_code in (404, 422)
    assert authed.patch("/api/notas/xx", json={"hecha": True}, headers=ORIGIN).status_code == 422


def _mini(tmp_path, store=None):
    emitidos = []
    store = store or NotasStore(tmp_path)
    app = FastAPI()
    app.include_router(build_router(store, lambda ev, data: emitidos.append((ev, data))), prefix="/api")
    return TestClient(app), store, emitidos


def test_emite_evento_notas(tmp_path):
    c, store, emitidos = _mini(tmp_path)
    nid = c.post("/api/notas", json={"tipo": "recordatorio", "texto": "a"}).json()["id"]
    assert emitidos[-1] == ("notas", {"version": store.version, "pendientes": 1})
    c.patch(f"/api/notas/{nid}", json={"hecha": True})
    assert emitidos[-1] == ("notas", {"version": store.version, "pendientes": 0})
    c.delete(f"/api/notas/{nid}")
    assert len(emitidos) == 3
    c.post("/api/notas", json={"tipo": "apunte", "texto": ""})
    assert len(emitidos) == 3


def test_notas_no_disponibles_503(tmp_path):
    (tmp_path / "notas.json").write_text("{}", encoding="utf-8")
    store = NotasStore(tmp_path)
    store._disponible = False
    c, _, emitidos = _mini(tmp_path, store)
    r = c.post("/api/notas", json={"tipo": "apunte", "texto": "a"})
    assert r.status_code == 503 and "reiniciá" in r.json()["detail"]
    assert c.patch("/api/notas/n_abcdefgh", json={"hecha": True}).status_code == 503
    assert c.delete("/api/notas/n_abcdefgh").status_code == 503
    assert c.get("/api/notas").json()["notas"] == []
    assert emitidos == []
