"""Rutas /api/cursor/*: solo lectura y cancelar; ninguna acepta argv, binario ni flags."""
from __future__ import annotations

from conftest import ORIGIN
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_pedidos_pestana import apagada_app, armar_app, enchufe, sender, wall  # noqa: F401

from orquestador.cursor_api import build_router

TID = "a" * 32


class RunnerFalso:
    MAX_SIMULTANEOS = 2

    def __init__(self):
        self.cancelados = []
        self.items = {TID: {"id": TID, "nombre": "X", "estado": "corriendo", "pedido": "p" * 200, "ruta": "/r"}}

    def disponible(self):
        return True

    def corriendo(self):
        return 1

    def listar(self):
        return [dict(t) for t in self.items.values()]

    def get(self, tid):
        return self.items.get(tid)

    def cola_log(self, tid):
        return "línea 1\nlínea 2"

    def cancelar(self, tid):
        self.cancelados.append(tid)
        return self.items[tid]["estado"] == "corriendo"


def _cliente(runner):
    app = FastAPI()
    app.include_router(build_router(runner), prefix="/api")
    return TestClient(app)


def test_estado_y_lista():
    c = _cliente(RunnerFalso())
    r = c.get("/api/cursor/estado")
    assert r.json() == {"disponible": True, "corriendo": 1, "max_simultaneos": 2}
    assert r.headers["cache-control"] == "no-store"
    lista = c.get("/api/cursor/trabajadores").json()["trabajadores"]
    assert lista[0]["id"] == TID and len(lista[0]["pedido"]) == 200


def test_log_y_404():
    c = _cliente(RunnerFalso())
    assert c.get(f"/api/cursor/trabajadores/{TID}/log").json() == {"texto": "línea 1\nlínea 2"}
    assert c.get("/api/cursor/trabajadores/" + "b" * 32 + "/log").status_code == 404
    assert c.get("/api/cursor/trabajadores/NOHEX/log").status_code == 404
    assert c.get("/api/cursor/trabajadores/" + "a" * 31 + "/log").status_code == 404


def test_cancelar():
    runner = RunnerFalso()
    c = _cliente(runner)
    assert c.post(f"/api/cursor/trabajadores/{TID}/cancelar").json() == {"ok": True}
    assert runner.cancelados == [TID]
    runner.items[TID]["estado"] = "ok"
    assert c.post(f"/api/cursor/trabajadores/{TID}/cancelar").status_code == 409
    assert c.post("/api/cursor/trabajadores/" + "c" * 32 + "/cancelar").status_code == 404


def test_no_hay_ruta_para_lanzar():
    rutas = {(m, r.path) for r in build_router(RunnerFalso()).routes for m in r.methods}
    assert rutas == {("GET", "/cursor/estado"), ("GET", "/cursor/trabajadores"),
                     ("GET", "/cursor/trabajadores/{tid}/log"), ("POST", "/cursor/trabajadores/{tid}/cancelar")}


def test_sin_cookie_401(tmp_path, projects, handoffs, enchufe):
    app = armar_app(tmp_path, projects, handoffs, enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.get("/api/cursor/estado").status_code == 401
        assert c.get("/api/cursor/trabajadores").status_code == 401
        assert c.post(f"/api/cursor/trabajadores/{TID}/cancelar").status_code in (401, 403)


def test_montado_en_la_app_con_sesion(apagada_app):
    c, app, _, _, _ = apagada_app
    r = c.get("/api/cursor/estado")
    assert r.status_code == 200 and r.json()["max_simultaneos"] == 2
    assert c.get("/api/cursor/trabajadores").json() == {"trabajadores": []}
    assert c.get(f"/api/cursor/trabajadores/{TID}/log").status_code == 404
    assert c.post(f"/api/cursor/trabajadores/{TID}/cancelar").status_code == 404
