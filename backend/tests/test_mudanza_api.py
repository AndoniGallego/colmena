from orquestador.enchufe import FakeTerminales

from conftest import make_snapshot

OP = "op-mudanza-0001"


def test_sin_guardian_no_disponible_y_no_cierra(authed, enchufe):
    data = authed.get("/api/mudanza").json()
    assert data["disponible"] is False
    r = authed.post("/api/mudanza/execute", json={"id": OP, "pane_id": "w1:p1", "confirmado": True})
    assert r.status_code == 503
    assert not [c for c in enchufe.calls if c[0] == "cerrar"]


def test_confirmacion_obligatoria(authed):
    for ruta, body in (("/api/mudanza/execute", {"id": OP, "pane_id": "w1:p1"}),
                       ("/api/mudanza/todas", {"id": OP, "pane_ids": ["w1:p1"], "confirmado": False}),
                       ("/api/mudanza/retomar", {"id": OP, "mudanza_id": OP})):
        assert authed.post(ruta, json=body).status_code == 400


def test_requiere_sesion(client):
    assert client.get("/api/mudanza").status_code == 401


def test_remapeos_cableados(app):
    mudanzas = app.state.mudanzas
    assert {n for n, _ in mudanzas.remapeos} == {"avisos", "permisos", "estados"}
    assert {n: fn("w1:p1", "g1:p1") for n, fn in mudanzas.remapeos}["avisos"] == 0


def test_guardian_presente_lista_candidatas(cfg, tmp_path, handoffs):
    from orquestador.app import create_app
    from orquestador.board import BoardHub
    from orquestador.digest import DigestService
    from orquestador.state import StateStore

    herdr = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    herdr.nombre = "herdr"
    guardian = FakeTerminales(nombre="guardian")
    herdr.backends = (herdr, guardian)
    digests = DigestService(cfg.projects_dir())
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=BoardHub(herdr, digests), digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads", enchufe=herdr)
    mudanzas = app.state.mudanzas
    assert mudanzas.herdr is herdr and mudanzas.guardian() is guardian
