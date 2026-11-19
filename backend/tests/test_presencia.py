import asyncio

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, SID, make_snapshot
from orquestador.enchufe import FakeTerminales
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.presencia import MAX_CLIENTS, TTL, Presencia
from orquestador.push import PushService
from orquestador.state import StateStore
from test_avisos import APPLE, EVENT, KEYS, Sender, sub

DEV = "device-abc123"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def pres(clock):
    return Presencia(clock)


def test_present_needs_visible_and_connected_stream(pres):
    assert not pres.present()
    pres.report(DEV, True)
    assert not pres.present()
    pres.connect(DEV)
    assert pres.present()
    pres.report(DEV, False)
    assert not pres.present()


def test_report_before_connect_counts_once_connected(pres):
    pres.report(DEV, True)
    pres.connect(DEV)
    assert pres.present()


def test_disconnect_ends_presence_even_if_it_was_visible(pres):
    pres.report(DEV, True)
    pres.connect(DEV)
    pres.disconnect(DEV)
    assert not pres.present()
    pres.connect(DEV)
    assert not pres.present()


def test_reconnect_overlap_keeps_presence_until_last_stream_closes(pres):
    pres.connect(DEV)
    pres.connect(DEV)
    pres.report(DEV, True)
    pres.disconnect(DEV)
    assert pres.present()
    pres.disconnect(DEV)
    assert not pres.present()


def test_expires_without_signal_and_renews(pres, clock):
    pres.report(DEV, True)
    pres.connect(DEV)
    clock.now += TTL - 1
    assert pres.present()
    pres.report(DEV, True)
    clock.now += TTL - 1
    assert pres.present()
    clock.now += 2
    assert not pres.present()


def test_any_present_client_is_enough(pres):
    for dev in ("device-aaaa1", "device-bbbb2"):
        pres.connect(dev)
    pres.report("device-aaaa1", False)
    pres.report("device-bbbb2", True)
    assert pres.present()


def test_hay_escritorio_con_stream_conectado(pres):
    pres.report(DEV, False, escritorio=True)
    assert not pres.hay_escritorio()
    pres.connect(DEV)
    assert pres.hay_escritorio()


def test_hay_escritorio_sin_stream(pres):
    pres.report(DEV, True, escritorio=True)
    assert not pres.hay_escritorio()


def test_escritorio_false_desmarca(pres):
    pres.report(DEV, True, escritorio=True)
    pres.connect(DEV)
    pres.report(DEV, True, escritorio=False)
    assert not pres.hay_escritorio()


def test_report_sin_escritorio_no_desmarca(pres):
    pres.report(DEV, True, escritorio=True)
    pres.connect(DEV)
    pres.report(DEV, True)
    assert pres.hay_escritorio()


def test_escritorio_evicta_sin_stream_cuando_lleno(pres):
    for i in range(MAX_CLIENTS):
        pres.report(f"device-stale{i:04d}", True, escritorio=True)
    assert len(pres.escritorio) == MAX_CLIENTS
    nuevo = "device-nuevo1"
    pres.report(nuevo, True, escritorio=True)
    pres.connect(nuevo)
    assert nuevo in pres.escritorio
    assert pres.hay_escritorio()


@pytest.fixture
def svc(tmp_path, clock):
    sender = Sender()
    service = PushService(tmp_path, sender=sender, clock=clock, wall=lambda: 1_800_000_000.0)
    return service, sender


def present(service):
    service.presencia.connect(DEV)
    service.presencia.report(DEV, True)


def test_dispatch_skips_push_but_records_notice(svc):
    service, sender = svc
    sub(service)
    present(service)
    assert asyncio.run(service.dispatch(EVENT)) == 0
    assert sender.sent == []
    [e] = service.avisos.items
    assert (e["entregado"], e["motivo"], e["session_id"]) == (False, "en la app", SID)


def test_terminal_and_simple_also_skip(svc):
    service, sender = svc
    service.avisos.registrar_kind("demo")
    sub(service)
    present(service)
    asyncio.run(service.dispatch_terminal("t", "b", "tag", "w1:p2"))
    asyncio.run(service.dispatch_simple("demo", {"title": "Demo", "body": "b", "session_id": "", "kind": "demo", "tag": "demo", "fecha": "2026-10-28"}, "demo"))
    assert sender.sent == []
    assert [(e["kind"], e["motivo"]) for e in service.avisos.items] == [("terminal", "en la app"), ("demo", "en la app")]


def test_pushes_again_when_the_app_is_left(svc):
    service, sender = svc
    sub(service)
    present(service)
    service.presencia.report(DEV, False)
    assert asyncio.run(service.dispatch(EVENT)) == 1
    assert service.avisos.items[0]["motivo"] == ""


def test_test_buttons_always_deliver(svc):
    service, sender = svc
    sub(service)
    present(service)
    service.avisos.registrar_kind("demo")
    assert asyncio.run(service.send_test(APPLE)) == 1
    assert asyncio.run(service.dispatch_simple("demo", {"title": "Demo", "body": "b", "session_id": "", "kind": "demo", "tag": "demo", "fecha": "2026-10-28"}, "demo", APPLE)) == 1
    assert len(sender.sent) == 2


def test_listeners_still_fire_when_present(svc):
    service, _ = svc
    seen = []
    service.listeners.append(seen.append)
    present(service)
    asyncio.run(service.dispatch(EVENT))
    assert len(seen) == 1


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


@pytest.fixture
def pclient(cfg, tmp_path, handoffs, enchufe):
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    push = PushService(tmp_path, sender=Sender(), wall=lambda: 1_800_000_000.0)
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, push=push, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c, push, hub


def test_presencia_endpoint(pclient):
    c, push, _hub = pclient
    push.presencia.connect(DEV)
    assert c.post("/api/presencia", json={"visible": True, "device": DEV}).json() == {"ok": True}
    assert push.presencia.present()
    c.post("/api/presencia", json={"visible": False, "device": DEV})
    assert not push.presencia.present()


@pytest.mark.parametrize("body", [{"visible": True}, {"visible": "si", "device": DEV}, {"visible": True, "device": "x"},
                                  {"visible": True, "device": "../../etc/passwd"}, {"visible": True, "device": DEV, "x": 1}])
def test_presencia_validates(pclient, body):
    assert pclient[0].post("/api/presencia", json=body).status_code == 422


def test_abrir_en_pc_sin_escritorio(pclient):
    c, push, hub = pclient
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    hub.subscribers.add(queue)
    assert c.post("/api/abrir-en-pc", json={"pane_id": "w1:p1", "titulo": "x"}).json() == {"ok": False, "motivo": "sin_pc"}
    assert queue.empty()
    hub.subscribers.discard(queue)


def test_abrir_en_pc_broadcast(pclient):
    c, push, hub = pclient
    push.presencia.report(DEV, False, escritorio=True)
    push.presencia.connect(DEV)
    queues = [asyncio.Queue(maxsize=8) for _ in range(2)]
    hub.subscribers.update(queues)
    assert c.post("/api/abrir-en-pc", json={"pane_id": "w1:p1", "titulo": "Mi sesión"}).json() == {"ok": True}
    payload = ("abrir_terminal", {"pane_id": "w1:p1", "titulo": "Mi sesión"})
    assert queues[0].get_nowait() == payload
    assert queues[1].get_nowait() == payload
    for q in queues:
        hub.subscribers.discard(q)


@pytest.mark.parametrize("body", [{"pane_id": "w1:p1", "titulo": "", "extra": 1}])
def test_abrir_en_pc_validates(pclient, body):
    assert pclient[0].post("/api/abrir-en-pc", json=body).status_code == 422


def test_presencia_needs_session_and_origin(pclient, cfg, tmp_path, handoffs, enchufe):
    c, _, _hub = pclient
    assert c.post("/api/presencia", json={"visible": True, "device": DEV},
                  headers={"Origin": "https://evil.example"}).status_code == 403
    digests = DigestService(cfg.projects_dir())
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=BoardHub(enchufe, digests),
                     digests=digests, dist=tmp_path / "nodist", handoffs_dir=handoffs, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as anon:
        assert anon.post("/api/presencia", json={"visible": True, "device": DEV}).status_code == 401
