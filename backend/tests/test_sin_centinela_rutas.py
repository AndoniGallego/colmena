import pytest
from fastapi.routing import APIRoute

from orquestador import auth
from orquestador.state import StateStore

RUTAS_A = [("GET", "/api/planes"), ("POST", "/api/plan/validar"), ("POST", "/api/plan/aprobar"),
           ("POST", "/api/plan/paso"), ("POST", "/api/plan/corregir"), ("POST", "/api/plan/cancelar"),
           ("GET", "/api/cadenas"), ("POST", "/api/cadenas/cancelar"), ("GET", "/api/bandeja"),
           ("POST", "/api/bandeja/responder"), ("POST", "/api/engram/guardar"), ("GET", "/api/engram/gate")]

RUTAS_B = [("GET", "/api/centinela"), ("GET", "/api/centinela/lineas"), ("POST", "/api/centinela/mensaje"),
           ("POST", "/api/centinela/reintentar"), ("POST", "/api/centinela/nueva"),
           ("POST", "/api/centinela/aviso/x/descartar"),
           ("POST", "/api/chat"), ("POST", "/api/chat/stop"), ("POST", "/api/chat/reset"),
           ("GET", "/api/chat/history"), ("GET", "/api/dios/uso"), ("GET", "/api/dios/uso/historial"),
           ("PUT", "/api/dios/ajustes")]


@pytest.mark.parametrize("metodo,ruta", RUTAS_A)
def test_rutas_de_planes_y_bandeja_404(authed, metodo, ruta):
    assert authed.request(metodo, ruta, json={}).status_code == 404


def test_servicios_de_planes_no_arrancan(app):
    for attr in ("planes", "cadenas", "bandeja", "frentes", "engram_guardar"):
        assert not hasattr(app.state, attr), attr


@pytest.mark.parametrize("metodo,ruta", RUTAS_B)
def test_rutas_de_centinela_y_dios_404(authed, metodo, ruta):
    assert authed.request(metodo, ruta, json={}).status_code == 404


def test_todas_las_rutas_api_piden_sesion(app):
    abiertas = {"/api/login", "/api/{path:path}"}
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/") and r.path not in abiertas:
            assert any(d.call is auth.require_session for d in r.dependant.dependencies), r.path


def test_arranque_sin_servicios_de_centinela(app):
    for attr in ("chat", "novedades", "centinela", "ajustes", "centinela_lineas"):
        assert not hasattr(app.state, attr), attr


def test_state_viejo_con_mensajes_dios_carga(tmp_path):
    (tmp_path / "state.json").write_text(
        '{"messages": [{"id": "1", "role": "user", "text": "x"}], "dios_at": "t", "dios_day": "d", "dios_ctx": 5,'
        ' "orchestrator_session_id": "abc", "session_started": true}')
    store = StateStore(tmp_path)
    assert store.messages()[0]["id"] == "1"
    store.save()
    store.flush()
    assert StateStore(tmp_path).messages()[0]["id"] == "1"


def test_state_ya_no_escribe_mensajes_ni_dios(tmp_path):
    store = StateStore(tmp_path)
    for nombre in ("add_message", "touch_dios", "dios_info", "rotate_session"):
        assert not hasattr(store, nombre), nombre
