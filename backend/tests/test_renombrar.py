import pytest

from test_nueva_terminal import _tablero_g, authed_mux, app_mux, mux_enchufe  # noqa: F401


def _post(c, **kw):
    return c.post("/api/terminales/renombrar", json=kw)


def test_renombra_grupo(authed_mux, mux_enchufe):
    _, g, h = mux_enchufe
    g.tablero_actual = _tablero_g(("g1", "Viejo", "/tmp"))
    r = _post(authed_mux, tipo="grupo", id="g1", nombre="  Nuevo  ")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert g.calls_of("renombrar") == [("renombrar", "g1", "Nuevo")]
    assert not h.calls_of("renombrar")


def test_renombra_pestana(authed_mux, mux_enchufe):
    _, g, _ = mux_enchufe
    g.tablero_actual = _tablero_g(("g1", "Viejo", "/tmp"))
    r = _post(authed_mux, tipo="pestana", id="g1:t1", nombre="Logs")
    assert r.status_code == 200
    assert g.calls_of("renombrar") == [("renombrar", "g1:t1", "Logs")]


@pytest.mark.parametrize("nombre", ["", "   ", "\n\t"])
def test_nombre_vacio_rechazado(authed_mux, mux_enchufe, nombre):
    _, g, _ = mux_enchufe
    g.tablero_actual = _tablero_g(("g1", "Viejo", "/tmp"))
    r = _post(authed_mux, tipo="grupo", id="g1", nombre=nombre)
    assert r.status_code in (400, 422)
    assert not g.calls_of("renombrar")


@pytest.mark.parametrize("tipo,id_", [("grupo", "w1"), ("grupo", "g1:t1"), ("pestana", "g1"), ("pestana", "w1:2"),
                                       ("grupo", "g1:p1")])
def test_id_o_tipo_incoherente(authed_mux, mux_enchufe, tipo, id_):
    _, g, _ = mux_enchufe
    g.tablero_actual = _tablero_g(("g1", "Viejo", "/tmp"))
    r = _post(authed_mux, tipo=tipo, id=id_, nombre="X")
    assert r.status_code in (400, 422)
    assert not g.calls_of("renombrar")


def test_grupo_inexistente_409(authed_mux, mux_enchufe):
    _, g, _ = mux_enchufe
    g.tablero_actual = _tablero_g(("g1", "Viejo", "/tmp"))
    r = _post(authed_mux, tipo="grupo", id="g9", nombre="X")
    assert r.status_code == 409
    assert not g.calls_of("renombrar")


def test_grupo_fijado_rechazado(app_mux, authed_mux, mux_enchufe):
    _, g, _ = mux_enchufe
    g.tablero_actual = _tablero_g(("g1", "Fijo", "/tmp"))
    app_mux.state.hub.pinned = frozenset({"fijo"})
    r = _post(authed_mux, tipo="grupo", id="g1", nombre="Otro")
    assert r.status_code == 403
    r = _post(authed_mux, tipo="pestana", id="g1:t1", nombre="Otro")
    assert r.status_code == 403
    assert not g.calls_of("renombrar")


def test_renombrar_requiere_login(app_mux):
    from fastapi.testclient import TestClient
    from conftest import ORIGIN
    with TestClient(app_mux, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        r = c.post("/api/terminales/renombrar", json={"tipo": "grupo", "id": "g1", "nombre": "X"})
    assert r.status_code in (401, 403)


def test_renombrar_get_405(authed_mux):
    assert authed_mux.get("/api/terminales/renombrar").status_code == 405
