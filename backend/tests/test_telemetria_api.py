import json

import pytest


def lineas_de(app):
    d = app.state.telemetria.directorio
    return [json.loads(l) for f in sorted(d.glob("*.jsonl")) for l in f.read_text().splitlines()]


def texto_de(app):
    d = app.state.telemetria.directorio
    return "".join(f.read_text() for f in d.glob("*") if f.is_file())


def test_comando_no_cuenta_una_vez(authed, app):
    for _ in range(2):
        assert authed.post("/api/telemetria/comando-no", json={"clave": "0123456789abcdef"}).json() == {"ok": True}
    assert [l["resultado"] for l in lineas_de(app) if l["ev"] == "comando_sesion"] == ["no"]
    assert "0123456789abcdef" not in texto_de(app)


def test_clave_nueva_cuenta_aparte(authed, app):
    for clave in ("0123456789abcdef", "fedcba9876543210"):
        authed.post("/api/telemetria/comando-no", json={"clave": clave})
    assert len([l for l in lineas_de(app) if l["ev"] == "comando_sesion"]) == 2


def test_clave_vence_a_las_24h(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from orquestador.telemetria import Telemetria
    from orquestador.telemetria_api import build_router
    reloj = [1000.0]
    tel = Telemetria(tmp_path / "t")
    app = FastAPI()
    app.include_router(build_router(tel, wall=lambda: reloj[0]), prefix="/api")
    c = TestClient(app)
    for avance in (0, 10, 24 * 3600 + 1):
        reloj[0] += avance
        assert c.post("/api/telemetria/comando-no", json={"clave": "0123456789abcdef"}).json() == {"ok": True}
    assert len([l for l in lineas_de_dir(tel.directorio) if l["ev"] == "comando_sesion"]) == 2


def lineas_de_dir(d):
    return [json.loads(l) for f in sorted(d.glob("*.jsonl")) for l in f.read_text().splitlines()]


@pytest.mark.parametrize("body", [{"clave": "XYZ"}, {"clave": "0123456789abcdef", "extra": 1}, {}])
def test_comando_no_valida(authed, body):
    assert authed.post("/api/telemetria/comando-no", json=body).status_code == 422


def test_comando_no_sin_sesion(client):
    assert client.post("/api/telemetria/comando-no", json={"clave": "0" * 16}).status_code == 401


def test_tope_duro_olvida_la_clave_mas_vieja(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from orquestador import telemetria_api
    from orquestador.telemetria import Telemetria
    monkeypatch.setattr(telemetria_api, "MAX_VISTAS", 3)
    tel = Telemetria(tmp_path / "t")
    app = FastAPI()
    app.include_router(telemetria_api.build_router(tel, wall=lambda: 1000.0), prefix="/api")
    c = TestClient(app)
    claves = [f"{i:016x}" for i in range(4)]
    for k in claves:
        c.post("/api/telemetria/comando-no", json={"clave": k})
    assert len(lineas_de_dir(tel.directorio)) == 4
    c.post("/api/telemetria/comando-no", json={"clave": claves[3]})  # reciente: sigue recordada
    assert len(lineas_de_dir(tel.directorio)) == 4
    c.post("/api/telemetria/comando-no", json={"clave": claves[0]})  # la más vieja se olvidó: cuenta de nuevo
    assert len(lineas_de_dir(tel.directorio)) == 5
    assert telemetria_api.MAX_VISTAS == 3


PID = "0123456789ab"


def sembrar(app, pid=PID, regla="error_repetido"):
    store = app.state.propuestas
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({pid: {"regla": regla, "clave": "k", "metrica": {"nombre": "n"},
                                            "seguimiento": []}}))


def test_marcar_propuesta_hacer(authed, app):
    sembrar(app)
    r = authed.post(f"/api/telemetria/propuestas/{PID}", json={"decision": "hacer"})
    assert r.status_code == 200
    assert r.json() == {"id": PID, "estado": "hacer", "silenciada_hasta": None}
    assert app.state.propuestas.cargar()[PID]["estado"] == "hacer"
    ls = [l for l in lineas_de(app) if l["ev"] == "propuesta"]
    assert [(l["regla"], l["decision"]) for l in ls] == [("error_repetido", "hacer")]
    assert PID not in "".join(f.read_text() for f in app.state.telemetria.directorio.glob("*.jsonl"))


def test_marcar_ignorar_silencia(authed, app):
    sembrar(app)
    r = authed.post(f"/api/telemetria/propuestas/{PID}", json={"decision": "ignorar"}).json()
    assert r["estado"] == "ignorar" and r["silenciada_hasta"]


@pytest.mark.parametrize("pid,body", [("XYZ", {"decision": "hacer"}), ("0" * 12, {"decision": "lanzar"}),
                                      ("0" * 12, {"decision": "hacer", "extra": 1})])
def test_marcar_valida_id_y_decision(authed, pid, body):
    assert authed.post(f"/api/telemetria/propuestas/{pid}", json=body).status_code == 422


def test_marcar_inexistente_404(authed, app):
    assert authed.post(f"/api/telemetria/propuestas/{PID}", json={"decision": "hacer"}).status_code == 404
    assert not [l for l in lineas_de(app) if l["ev"] == "propuesta"]


def test_marcar_sin_sesion_401(client):
    assert client.post(f"/api/telemetria/propuestas/{PID}", json={"decision": "hacer"}).status_code == 401


def test_marcar_hacer_toma_la_metrica_actual(tmp_path):
    from datetime import datetime, timezone
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from orquestador.telemetria import Telemetria
    from orquestador.telemetria_api import build_router
    from orquestador.telemetria_resumen import PropuestasStore
    store = PropuestasStore(tmp_path / "p.json", wall=lambda: datetime(2026, 11, 25, tzinfo=timezone.utc))
    store.path.write_text(json.dumps({PID: {"regla": None, "clave": "k", "metrica": {"nombre": "n"},
                                            "seguimiento": []}}))
    app = FastAPI()
    app.include_router(build_router(Telemetria(tmp_path / "t"), propuestas=store,
                                    metrica_actual=lambda pid: 7.0), prefix="/api")
    assert TestClient(app).post(f"/api/telemetria/propuestas/{PID}", json={"decision": "hacer"}).status_code == 200
    m = store.cargar()[PID]["metrica"]
    assert m["base"] == 7.0 and m["semana_base"] == "2026-W48"
    ls = lineas_de_dir(tmp_path / "t")
    assert ls[0]["regla"] == "otro"
