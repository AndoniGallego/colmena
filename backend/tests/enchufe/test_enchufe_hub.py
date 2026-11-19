import asyncio

import pytest
from conftest import FakeHerdr, ORIGIN, PIN, make_snapshot
from fastapi.testclient import TestClient
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.enchufe import Mux
from orquestador.enchufe.base import NoDisponible, TerminalesError
from orquestador.enchufe.herdr import AdaptadorHerdr
from orquestador.state import StateStore

_POLL = 0.05
_DEBOUNCE = 0.02


def _hub(projects, fh: FakeHerdr) -> BoardHub:
    ad = AdaptadorHerdr(fh, poll=_POLL)
    return BoardHub(Mux([ad]), DigestService(projects), debounce=_DEBOUNCE)


def test_hub_herdr_caido_antes_de_suscribirse(projects):
    async def escenario():
        fh = FakeHerdr(make_snapshot())
        fh.caido = True
        hub = _hub(projects, fh)
        q = hub.subscribe()
        board = await asyncio.wait_for(q.get(), 1.0)
        assert board["terminales"] == "sin_conexion"
        assert hub.board is None
        with pytest.raises(TerminalesError):
            await hub.current()
        hub.unsubscribe(q)

    asyncio.run(escenario())


def test_current_tras_caida_inicial_herdr_vuelve(projects):
    async def escenario():
        fh = FakeHerdr(make_snapshot())
        fh.caido = True
        hub = _hub(projects, fh)
        q = hub.subscribe()
        assert (await asyncio.wait_for(q.get(), 1.0))["terminales"] == "sin_conexion"
        fh.caido = False
        ok = await hub.current()
        assert ok["terminales"] == "ok"
        assert ok["workspaces"]
        hub.unsubscribe(q)

    asyncio.run(escenario())


def test_current_recupera_board_sin_conexion_con_hub_parado(projects):
    async def escenario():
        fh = FakeHerdr(make_snapshot())
        hub = _hub(projects, fh)
        q = hub.subscribe()
        assert (await asyncio.wait_for(q.get(), 1.0))["terminales"] == "ok"
        fh.caido = True
        caido = await asyncio.wait_for(q.get(), 2.0)
        assert caido["terminales"] == "sin_conexion" and caido["workspaces"]
        hub.unsubscribe(q)
        fh.caido = False
        ok = await hub.current()
        assert ok["terminales"] == "ok"

    asyncio.run(escenario())


def test_api_board_502_si_herdr_caido_desde_inicio(cfg, tmp_path, handoffs, projects):
    fh = FakeHerdr(make_snapshot())
    fh.caido = True
    ad = AdaptadorHerdr(fh, poll=_POLL)
    digests = DigestService(projects)
    hub = BoardHub(Mux([ad]), digests, debounce=_DEBOUNCE)
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads",
                     enchufe=Mux([ad]))
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        c.post("/api/login", json={"pin": PIN})
        r = c.get("/api/board")
    assert r.status_code == 502
    assert r.json()["detail"].startswith("Las terminales no responden:")


def test_hub_herdr_caida_tras_desuscribir_y_resuscribir(projects):
    async def escenario():
        fh = FakeHerdr(make_snapshot())
        hub = _hub(projects, fh)
        q1 = hub.subscribe()
        primero = await asyncio.wait_for(q1.get(), 1.0)
        assert primero["terminales"] == "ok"
        hub.unsubscribe(q1)
        fh.caido = True
        try:
            await hub.enchufe.tablero()
        except NoDisponible:
            pass
        q2 = hub.subscribe()
        caido = await asyncio.wait_for(q2.get(), 1.0)
        assert caido["terminales"] == "sin_conexion"
        assert caido["workspaces"] == primero["workspaces"]
        hub.unsubscribe(q2)

    asyncio.run(escenario())


def test_hub_herdr_recuperacion_vuelve_a_ok(projects):
    async def escenario():
        fh = FakeHerdr(make_snapshot())
        fh.caido = True
        hub = _hub(projects, fh)
        q = hub.subscribe()
        assert (await asyncio.wait_for(q.get(), 1.0))["terminales"] == "sin_conexion"
        fh.caido = False
        ok = await asyncio.wait_for(q.get(), 2.0)
        assert ok["terminales"] == "ok"
        assert (await hub.current())["terminales"] == "ok"
        hub.unsubscribe(q)

    asyncio.run(escenario())
