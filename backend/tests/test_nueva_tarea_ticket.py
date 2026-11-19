from unittest.mock import AsyncMock

import pytest
from conftest import ORIGIN, PIN, make_snapshot

from orquestador.enchufe.fake import FakeTerminales
from orquestador.enchufe.mux import Mux
from orquestador.nueva_tarea import mensaje_ticket, nombre_ticket, validar_ticket
from orquestador.traspaso import TraspasoError

from test_nueva_tarea import _git, repo  # noqa: F401  (fixture de repo temporal)

IDT = "ticket001"


@pytest.mark.parametrize("raw,esperada", [("abc-123", "ABC-123"), ("  FRONT-9 ", "FRONT-9"), ("LRUN-100000", "LRUN-100000")])
def test_validar_ticket_normaliza(raw, esperada):
    assert validar_ticket(raw) == esperada


@pytest.mark.parametrize("malo", ["SITE-0", "S-1", "ABC-1234567", "SITE-12; rm -rf /", "", "SITE", "-1", "SITE-01",
                                  "SITE-1\nX", "ABCDEFGHIJK-1"])
def test_validar_ticket_rechaza(malo):
    with pytest.raises(TraspasoError) as exc:
        validar_ticket(malo)
    assert exc.value.status == 400


def test_mensaje_ticket_exacto_con_y_sin_nota():
    base = ("Arrancá el ticket ABC-123. Primero leelo con el agente analista de tickets (nunca la API de Jira directo) y "
            "después seguí /flujo-tickets desde el principio, con sus aprobaciones. Estás en una copia del repo solo "
            "para esta tarea, en la rama feature/ABC-123.")
    assert mensaje_ticket("ABC-123", "feature/ABC-123", "") == base
    assert mensaje_ticket("ABC-123", "feature/ABC-123", "  \n ") == base
    assert mensaje_ticket("ABC-123", "feature/ABC-123", "ojo con\nel carrito") == \
        base + " Nota de Ando: ojo con ⏎ el carrito"


def test_mensaje_ticket_nota_larga_se_rechaza_en_vez_de_recortar():
    from orquestador.mensaje import MAX_TEXT
    largo = len(mensaje_ticket("ABC-123", "feature/ABC-123", ""))
    justo = "x" * (MAX_TEXT - largo - len(" Nota de Ando: "))
    assert len(mensaje_ticket("ABC-123", "feature/ABC-123", justo)) == MAX_TEXT
    with pytest.raises(TraspasoError) as exc:
        mensaje_ticket("ABC-123", "feature/ABC-123", justo + "y")
    assert exc.value.status == 400 and str(len(justo)) in exc.value.detail
    with pytest.raises(TraspasoError):
        mensaje_ticket("ABC-123", "feature/ABC-123", "z" * 4000)


def test_nombre_ticket():
    assert nombre_ticket("ABC-123", "") == "ABC-123"
    assert nombre_ticket("ABC-123", "arreglar el carrito roto ahora mismo por favor gracias") == \
        "ABC-123 · arreglar el carrito roto ahora mismo"
    assert len(nombre_ticket("ABC-123", "x" * 200)) <= 60


@pytest.fixture
def mux_enchufe():
    g = FakeTerminales(nombre="guardian")
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    return Mux([h, g], nuevas_en="guardian"), g, h


@pytest.fixture
def authed_mux(app, mux_enchufe):
    mux, _, _ = mux_enchufe
    app.state.hub.enchufe = mux
    app.state.tacciones.enchufe = mux
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    with __import__("fastapi").testclient.TestClient(
        app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)
    ) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def _post(c, repo, **kw):
    cuerpo = {"id": IDT, "repo": str(repo), "tarea": ""}
    cuerpo.update(kw)
    return c.post("/api/terminales/nueva-tarea", json=cuerpo)


def test_nueva_tarea_con_ticket_fija_rama_y_mensaje(authed_mux, app, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    r = _post(authed_mux, repo, ticket="abc-123", tarea="ojo con el carrito")
    assert r.status_code == 200, r.text
    ruta = str(repo.parent / "proy-abc-123")
    assert r.json()["ruta"] == ruta and r.json()["rama"] == "feature/ABC-123"
    assert _git(ruta, "rev-parse", "--abbrev-ref", "HEAD") == "feature/ABC-123"
    assert g.calls_of("crear_espacio")[0][1] == "ABC-123 · ojo con el carrito"
    texto = app.state.mensajes.execute.await_args[0][0].texto
    assert texto == mensaje_ticket("ABC-123", "feature/ABC-123", "ojo con el carrito")


def test_nueva_tarea_con_ticket_sin_nota_es_valida(authed_mux, app, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    r = _post(authed_mux, repo, ticket="ABC-123")
    assert r.status_code == 200, r.text
    assert app.state.mensajes.execute.await_args[0][0].texto == mensaje_ticket("ABC-123", "feature/ABC-123", "")


def test_ticket_invalido_400_no_crea(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    assert _post(authed_mux, repo, ticket="SITE-12; rm -rf /").status_code == 400
    assert _post(authed_mux, repo, ticket="SITE-0").status_code == 400
    assert _post(authed_mux, repo, ticket="X" * 21).status_code in (400, 422)
    assert not list(repo.parent.glob("proy-*"))


def test_ticket_y_rama_distinta_400(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    r = _post(authed_mux, repo, ticket="ABC-123", rama="feature/otra")
    assert r.status_code == 400 and "feature/ABC-123" in r.json()["detail"]
    assert not list(repo.parent.glob("proy-*"))
    assert _post(authed_mux, repo, id="ticket002", ticket="ABC-123", rama="feature/ABC-123").status_code == 200


def test_rama_de_ticket_existente_409_no_crea_carpeta(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    _git(repo, "branch", "feature/ABC-123")
    r = _post(authed_mux, repo, ticket="ABC-123")
    assert r.status_code == 409 and "Ya hay una rama feature/ABC-123" in r.json()["detail"]
    assert not list(repo.parent.glob("proy-*"))


def test_sin_ticket_y_sin_tarea_sigue_400(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    assert _post(authed_mux, repo, tarea="  ").status_code == 400
