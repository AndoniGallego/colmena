import asyncio
import json
import stat

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, SID, make_snapshot
from orquestador.enchufe import FakeTerminales
from orquestador.app import create_app
from orquestador.avisos import MAX_ITEMS, RETENTION, AvisosStore
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.push import PushService
from orquestador.state import StateStore

APPLE = "https://web.push.apple.com/QGxyz"
FCM = "https://fcm.googleapis.com/fcm/send/abc"
KEYS = {"p256dh": "BPubKeyPubKeyPubKeyPubKey", "auth": "AuthSecretAuth12"}


class Wall:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


class Sender:
    def __init__(self):
        self.sent = []
        self.error = None

    def __call__(self, info, data, vapid, claims, timeout):
        if self.error:
            raise self.error
        self.sent.append(json.loads(data))


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


@pytest.fixture
def wall():
    return Wall()


@pytest.fixture
def sender():
    return Sender()


@pytest.fixture
def svc(tmp_path, sender, wall):
    return PushService(tmp_path, sender=sender, wall=wall)


def sub(svc, endpoint=APPLE, **prefs):
    svc.store.upsert({"endpoint": endpoint, "keys": KEYS, "device": "x", "prefs": {"texto": True, **prefs}})


EVENT = {"kind": "asks", "session_id": SID, "name": "Uno", "pending": "¿Seguimos con el plan?"}


def test_one_entry_per_event_not_per_device(svc, sender):
    sub(svc)
    sub(svc, FCM)
    asyncio.run(svc.dispatch(EVENT))
    assert len(sender.sent) == 2
    [e] = svc.avisos.items
    assert (e["kind"], e["titulo"], e["cuerpo"], e["session_id"], e["entregado"]) == (
        "asks", "Uno te pregunta", "¿Seguimos con el plan?", SID, True)


def test_recorded_without_devices_with_generic_body(svc):
    asyncio.run(svc.dispatch(EVENT))
    [e] = svc.avisos.items
    assert e["entregado"] is False
    assert "plan" not in e["cuerpo"]


def test_body_is_generic_when_no_device_wants_text(svc):
    sub(svc, texto=False)
    asyncio.run(svc.dispatch(EVENT))
    assert svc.avisos.items[0]["cuerpo"] == "Revisá la sesión en Colmena."
    sub(svc, FCM, texto=True)
    asyncio.run(svc.dispatch(EVENT))
    assert svc.avisos.items[1]["cuerpo"] == "¿Seguimos con el plan?"


def test_failed_delivery_is_recorded_as_not_delivered(svc, sender):
    sub(svc)
    sender.error = RuntimeError("boom")
    assert asyncio.run(svc.dispatch(EVENT)) == 0
    assert svc.avisos.items[0]["entregado"] is False


def test_terminal_simple_and_test_are_recorded(svc):
    svc.avisos.registrar_kind("demo")
    sub(svc, texto=False)
    asyncio.run(svc.dispatch_terminal("Se escribió en una terminal", "texto privado", "t1", "pane:1"))
    asyncio.run(svc.dispatch_simple("demo", {"title": "Demo", "body": "b", "session_id": "", "kind": "demo", "tag": "demo", "fecha": "2026-10-28"}, "demo", fecha="2026-10-28"))
    asyncio.run(svc.send_test(None))
    term, demo, test = svc.avisos.items
    assert (term["kind"], term["pane_id"], term["cuerpo"]) == ("terminal", "pane:1", "Revisá la actividad de terminales.")
    assert (demo["kind"], demo["fecha"], demo["titulo"]) == ("demo", "2026-10-28", "Demo")
    assert test["kind"] == "test"


def test_invalid_pane_is_dropped(svc):
    asyncio.run(svc.dispatch_terminal("t", "b", "tag", "../etc"))
    assert svc.avisos.items[0]["pane_id"] == ""


def test_listener_is_called_and_failures_do_not_break_dispatch(svc):
    seen = []
    svc.listeners.append(seen.append)
    svc.listeners.append(lambda e: 1 / 0)
    asyncio.run(svc.dispatch(EVENT))
    assert [e["kind"] for e in seen] == ["asks"]


def test_file_is_private_and_reloaded(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    store.add("done", "Uno terminó", "ok", True, session_id=SID)
    store.mark_read(1)
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    again = AvisosStore(tmp_path, wall)
    assert [e["titulo"] for e in again.items] == ["Uno terminó"]
    assert again.leidos == 1 and again.no_leidos == 0
    assert again.add("done", "otro", "", True)["id"] == 2


def test_retention_and_cap(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    store.add("done", "viejo", "", True)
    wall.now += RETENTION + 10
    store.add("done", "nuevo", "", True)
    assert [e["titulo"] for e in store.items] == ["nuevo"]
    for i in range(MAX_ITEMS + 20):
        store.add("done", f"n{i}", "", True)
    assert len(store.items) == MAX_ITEMS
    assert store.items[-1]["titulo"] == f"n{MAX_ITEMS + 19}"


def test_corrupt_file_and_bad_entries(tmp_path, wall):
    (tmp_path / "avisos.json").write_text("{no es json")
    assert AvisosStore(tmp_path, wall).items == []
    good = {"id": 5, "ts": wall.now, "kind": "done", "titulo": "ok", "cuerpo": "", "entregado": True}
    bad = [{"id": "x", "ts": 1, "kind": "done"}, {"id": 6, "ts": wall.now, "kind": "inventado"}, None, 3]
    (tmp_path / "avisos.json").write_text(json.dumps({"items": [good, *bad], "leidos": -4}))
    store = AvisosStore(tmp_path, wall)
    assert [e["id"] for e in store.items] == [5]
    # "inventado" tiene forma de kind: queda oculto (por si una pieza lo registra) y reserva su id.
    assert [e["id"] for e in store.ocultos] == [6]
    assert store.leidos == 0 and store.next_id == 7


def test_paging_newest_first(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    for i in range(5):
        store.add("done", f"n{i}", "", True)
    first = store.page(2)
    assert [e["titulo"] for e in first["items"]] == ["n4", "n3"] and first["hay_mas"] is True
    rest = store.page(10, before=first["items"][-1]["id"])
    assert [e["titulo"] for e in rest["items"]] == ["n2", "n1", "n0"] and rest["hay_mas"] is False
    assert first["no_leidos"] == 5


def test_mark_read_is_capped_and_monotonic(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    for _ in range(3):
        store.add("done", "x", "", True)
    assert store.mark_read(2) == 1
    assert store.mark_read(1) == 1
    assert store.mark_read(99) == 0 and store.leidos == 3


def test_tag_stored_validated_and_survives_reload(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    store.add("done", "t", "", True, tag=SID)
    store.add("done", "bad", "", True, tag="a b")
    store.add("done", "long", "", True, tag="x" * 200)
    assert [e["tag"] for e in store.items] == [SID, "", ""]
    again = AvisosStore(tmp_path, wall)
    assert again.items[0]["tag"] == SID and again.items[1]["tag"] == ""


def test_legacy_entries_load_with_empty_tag(tmp_path, wall):
    raw = {"id": 1, "ts": wall.now, "kind": "done", "titulo": "v", "cuerpo": "", "entregado": True}
    (tmp_path / "avisos.json").write_text(json.dumps({"items": [raw], "leidos": 0, "next": 2}))
    assert AvisosStore(tmp_path, wall).items[0]["tag"] == ""


def test_marcar_donde_returns_tags_and_cambiados(svc):
    a = svc.avisos
    a.add("done", "1", "", True, session_id=SID, tag=SID)
    a.add("cierre", "h", "", True, tag="cierre")
    out = a.marcar_donde(session_id=SID)
    assert out["cambiados"] == 1 and out["no_leidos"] == 1 and out["tags"] == [SID]
    assert a.marcar_donde(kind="cierre")["tags"] == ["cierre"]


def test_marcar_donde_omite_tag_con_otro_aviso_pendiente(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    store.add("done", "1", "", True, tag=SID)
    store.add("done", "2", "", True, tag=SID)
    out = store.marcar_hasta(1)
    assert out["cambiados"] == 1 and out["tags"] == []


def test_marcar_hasta_solo_tags_del_rango_nuevo(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    store.add("done", "1", "", True, tag="t1")
    store.add("done", "2", "", True, tag="t2")
    store.add("done", "3", "", True, tag="t3")
    out = store.marcar_hasta(2)
    assert out["cambiados"] == 2 and out["tags"] == ["t1", "t2"] and out["no_leidos"] == 1
    assert store.marcar_hasta(2)["cambiados"] == 0


def test_mark_wrappers_siguen_devolviendo_int(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    store.add("done", "x", "", True, session_id=SID, tag=SID)
    assert isinstance(store.mark_where(session_id=SID), int)
    store.add("done", "y", "", True)
    assert isinstance(store.mark_read(2), int)


@pytest.fixture
def aclient(cfg, tmp_path, handoffs, sender, wall, enchufe):
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    push = PushService(tmp_path, sender=sender, wall=wall)
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, push=push, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c, push, hub


def test_endpoints_require_session(cfg, tmp_path, handoffs, enchufe):
    digests = DigestService(cfg.projects_dir())
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=BoardHub(enchufe, digests),
                     digests=digests, dist=tmp_path / "nodist", handoffs_dir=handoffs, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.get("/api/avisos").status_code == 401
        assert c.post("/api/avisos/leidos", json={"hasta": 1}).status_code == 401


def test_list_and_mark_read(aclient):
    c, push, _ = aclient
    for i in range(3):
        push.avisos.add("done", f"n{i}", "", True)
    data = c.get("/api/avisos?limite=2").json()
    assert [e["titulo"] for e in data["items"]] == ["n2", "n1"]
    assert data["hay_mas"] is True and data["no_leidos"] == 3
    assert c.get("/api/avisos?limite=2").headers["cache-control"] == "no-store"
    older = c.get(f"/api/avisos?antes={data['items'][-1]['id']}").json()
    assert [e["titulo"] for e in older["items"]] == ["n0"]
    assert c.post("/api/avisos/leidos", json={"hasta": 2}).json() == {"ok": True, "no_leidos": 1}
    assert c.get("/api/avisos").json()["no_leidos"] == 1


@pytest.mark.parametrize("body", [{}, {"hasta": -1}, {"hasta": "2"}, {"hasta": 1.5}, {"hasta": True}, {"hasta": 1, "x": 1}])
def test_mark_read_validates(aclient, body):
    assert aclient[0].post("/api/avisos/leidos", json=body).status_code == 422


def test_mark_read_needs_same_origin(aclient):
    c = aclient[0]
    assert c.post("/api/avisos/leidos", json={"hasta": 1}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_push_hub_broadcasts_new_notice(aclient):
    _, push, hub = aclient
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    hub.subscribers.add(queue)
    asyncio.run(push.dispatch(EVENT))
    assert queue.get_nowait() == ("aviso", {"id": 1})
    hub.subscribers.discard(queue)


def test_terminal_notice_is_recorded_without_devices(aclient):
    _, push, _ = aclient
    asyncio.run(push.dispatch_terminal("Se escribió", "algo", "tag", "pane:2"))
    assert push.avisos.items[0]["kind"] == "terminal"


def test_mark_where_marks_only_that_destination(svc):
    a = svc.avisos
    a.add("done", "uno", "", True, session_id=SID)
    a.add("done", "otra", "", True, session_id="otra-sesion")
    a.add("terminal", "term", "", True, pane_id="w1:p2")
    a.add("cierre", "cierre", "", True, fecha="2026-10-28")
    assert a.mark_where(session_id=SID) == 3
    assert a.mark_where(pane_id="w1:p2") == 2
    assert a.mark_where(kind="cierre") == 1
    assert a.mark_where(session_id="no-existe") == 1
    assert a.page()["items"][-1]["leido"] is True
    assert a.mark_read(4) == 0


def test_mark_where_persists(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    store.add("done", "uno", "", True, session_id=SID)
    store.mark_where(session_id=SID)
    assert AvisosStore(tmp_path, wall).no_leidos == 0


def test_mark_read_by_filter_via_api(aclient):
    c, push, _ = aclient
    push.avisos.add("done", "a", "", True, session_id=SID)
    push.avisos.add("terminal", "b", "", True, pane_id="w1:p2")
    assert c.post("/api/avisos/leidos", json={"session_id": SID}).json() == {"ok": True, "no_leidos": 1}
    assert c.post("/api/avisos/leidos", json={"pane_id": "w1:p2"}).json()["no_leidos"] == 0
    push.avisos.add("cierre", "h", "", True, fecha="2026-10-28")
    assert c.post("/api/avisos/leidos", json={"kind": "cierre"}).json()["no_leidos"] == 0


@pytest.mark.parametrize("body", [{"session_id": "../x"}, {"pane_id": "a b"}, {"kind": "nada"}, {"kind": 3},
                                  {"hasta": 1, "kind": "cierre"}, {"session_id": SID, "pane_id": "w1:p2"}])
def test_mark_read_filter_validates(aclient, body):
    assert aclient[0].post("/api/avisos/leidos", json=body).status_code == 422


def test_leidos_con_endpoint_notifica_tags(aclient, sender):
    c, push, _ = aclient
    sub(push, endpoint=APPLE)
    sub(push, endpoint=FCM)
    asyncio.run(push.dispatch(EVENT))
    seen = []
    push.leidos_listeners.append(seen.extend)
    r = c.post("/api/avisos/leidos", json={"session_id": SID, "endpoint": APPLE})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert seen == [SID]

    async def drain():
        await asyncio.gather(*list(push._tasks))

    asyncio.run(drain())
    cerrar = [p for p in sender.sent if p.get("kind") == "cerrar"]
    assert len(cerrar) == 1 and cerrar[0]["tags"] == [SID]


def test_leidos_solo_endpoint_es_422(aclient):
    assert aclient[0].post("/api/avisos/leidos", json={"endpoint": APPLE}).status_code == 422


def test_kind_progreso(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    store.add("progreso", "Viene avanzando: X", "cuerpo", True, tag="progreso-enc-1")
    assert store.items[-1]["kind"] == "progreso"


def test_prueba_no_cuenta_en_campana(tmp_path, wall):
    store = AvisosStore(tmp_path, wall)
    store.add("done", "normal", "", True)
    store.add("done", "prueba", "", False, prueba=True)
    assert store.no_leidos == 1
    page = store.page()
    assert len(page["items"]) == 1 and page["items"][0]["titulo"] == "normal"
    assert len(store.page(incluir_prueba=True)["items"]) == 2


def test_kind_sin_registrar_queda_oculto_y_vuelve_al_registrarlo(tmp_path, wall):
    raw = [{"id": 1, "ts": wall.now, "kind": "demo", "titulo": "d", "cuerpo": "", "entregado": True},
           {"id": 2, "ts": wall.now, "kind": "done", "titulo": "v", "cuerpo": "", "entregado": True},
           {"id": 3, "ts": wall.now, "kind": "Mal-Kind", "titulo": "x", "cuerpo": "", "entregado": True}]
    (tmp_path / "avisos.json").write_text(json.dumps({"items": raw, "leidos": 0, "next": 4}))
    store = AvisosStore(tmp_path, wall)
    assert [e["kind"] for e in store.items] == ["done"] and store.no_leidos == 1
    store.add("done", "otra", "", True)
    assert [e["kind"] for e in AvisosStore(tmp_path, wall).ocultos] == ["demo"]
    store.registrar_kind("demo")
    assert [e["id"] for e in store.items] == [1, 2, 4]
    with pytest.raises(ValueError):
        store.add("otro", "t", "", True)


def test_mark_read_kind_registrado_por_una_pieza(aclient):
    c, push, _ = aclient
    assert c.post("/api/avisos/leidos", json={"kind": "demo"}).status_code == 422
    push.avisos.registrar_kind("demo")
    push.avisos.add("demo", "d", "", True)
    assert c.post("/api/avisos/leidos", json={"kind": "demo"}).json() == {"ok": True, "no_leidos": 0}
