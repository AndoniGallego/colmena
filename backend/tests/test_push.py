import asyncio
import json
import stat

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, SID, make_snapshot
from orquestador.app import create_app
from orquestador.enchufe import FakeTerminales
from terminales_support import aplicar_snapshot
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.push import PushService, VapidKeys, endpoint_allowed
from orquestador.state import StateStore

APPLE = "https://web.push.apple.com/QGxyz"
FCM = "https://fcm.googleapis.com/fcm/send/abc"
KEYS = {"p256dh": "BPubKeyPubKeyPubKeyPubKey", "auth": "AuthSecretAuth12"}


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class PushGone(Exception):
    def __init__(self, status_code):
        self.response = FakeResponse(status_code)


class Recorder:
    def __init__(self):
        self.sent = []
        self.error = None

    def __call__(self, info, data, vapid, claims, timeout):
        if self.error:
            raise self.error
        self.sent.append((info["endpoint"], json.loads(data), timeout))


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class DeferredTimers:
    """call_later inyectado: ejecuta callbacks a mano, sin espera real."""

    def __init__(self):
        self.pending = []

    def __call__(self, delay, fn):
        handle = type("Handle", (), {"cancelled": False})()
        entry = [delay, fn, handle]

        def cancel():
            handle.cancelled = True
            if entry in self.pending:
                self.pending.remove(entry)

        handle.cancel = cancel
        self.pending.append(entry)
        return handle

    def flush(self):
        while self.pending:
            delay, fn, handle = self.pending.pop(0)
            if not handle.cancelled:
                fn()


def service_with_defer(tmp_path, sender, clock, timers=None):
    timers = timers or DeferredTimers()
    return PushService(tmp_path, sender=sender, clock=clock, call_later=timers), timers


def flush_deferred_done(svc, timers):
    async def run():
        timers.flush()
        await asyncio.gather(*list(svc._tasks))

    asyncio.run(run())


def observe_and_dispatch(svc, prev, new):
    events = svc.observe(prev, new)

    async def run():
        for event in events:
            await svc.dispatch(event)
        await asyncio.gather(*list(svc._tasks))

    asyncio.run(run())
    return events


def board(status="idle", asks=False, pending="", session=SID, label="Uno", fondo=None):
    agent = {"pane_id": "p1", "status": status, "asks_user": asks, "pending": pending, "session_id": session,
             "fondo": fondo if fondo is not None else []}
    return {"workspaces": [{"label": label, "tabs": [{"agents": [agent]}]}]}


def subscribe_body(endpoint=APPLE, **prefs):
    return {"subscription": {"endpoint": endpoint, "keys": dict(KEYS)}, "device": "iPhone",
            "prefs": {"asks": True, "blocked": True, "done": True, "texto": True, **prefs}}


@pytest.fixture
def sender():
    return Recorder()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def service(tmp_path, sender, clock):
    return PushService(tmp_path, sender=sender, clock=clock)


def test_allowlist():
    assert endpoint_allowed(APPLE)
    assert endpoint_allowed(FCM)
    assert endpoint_allowed("https://wns2-par02p.notify.windows.com/w/?token=x")
    assert endpoint_allowed("https://updates.push.services.mozilla.com/wpush/v2/x")
    assert endpoint_allowed("https://a.push.services.mozilla.com/x")
    for bad in ["http://fcm.googleapis.com/x", "https://evil.com/x", "https://push.apple.com.evil.com/x",
                "https://fcm.googleapis.com@evil.com/x", "https://user:pw@fcm.googleapis.com/x",
                "https://fcm.googleapis.com:8443/x", "https://127.0.0.1/x", "https://notify.windows.com/x",
                "file:///etc/passwd", "", "https://fcm.googleapis.com.evil.com/"]:
        assert not endpoint_allowed(bad), bad


def test_vapid_keys_generated_once_with_private_mode(tmp_path):
    first = VapidKeys(tmp_path)
    assert stat.S_IMODE((tmp_path / "vapid.json").stat().st_mode) == 0o600
    assert VapidKeys(tmp_path).public == first.public
    assert len(first.public) == 87


def test_first_board_and_new_agents_are_silent(service):
    assert service.observe(None, board("blocked")) == []
    assert service.observe({"workspaces": []}, board("blocked")) == []


def test_blocked_and_asks(service, clock):
    assert [e["kind"] for e in service.observe(board("working"), board("blocked"))] == ["blocked"]
    clock.now += 100
    events = service.observe(board("working"), board("idle", asks=True, pending="¿Seguimos?"))
    assert [e["kind"] for e in events] == ["asks"]
    assert events[0]["name"] == "Uno" and events[0]["pending"] == "¿Seguimos?"
    clock.now += 100
    assert service.observe(board("idle", asks=True), board("idle", asks=True)) == []


def test_asks_when_digest_lags_behind_status(service):
    assert [e["kind"] for e in service.observe(board("idle"), board("idle", asks=True))] == ["asks"]


def test_done_suprimido_con_fondo_y_luego_avisa(tmp_path, sender, clock):
    svc, timers = service_with_defer(tmp_path, sender, clock)
    tarea = [{"id": "t1", "tipo": "cursor", "texto": "Tests", "desde": 1.0}]
    assert svc.observe(board("working"), board("idle", fondo=tarea)) == []
    clock.now += 5
    assert svc.observe(board("idle", fondo=tarea), board("idle", fondo=tarea)) == []
    clock.now += 6
    assert svc.observe(board("idle", fondo=tarea), board("idle")) == []
    flush_deferred_done(svc, timers)
    assert svc.avisos.items[-1]["kind"] == "done"


def test_done_on_every_turn_end_even_short(tmp_path, sender, clock):
    svc, timers = service_with_defer(tmp_path, sender, clock)
    svc.observe(None, board("working"))
    clock.now += 3
    assert svc.observe(board("working"), board("idle")) == []
    flush_deferred_done(svc, timers)
    assert svc.avisos.items[-1]["kind"] == "done"
    clock.now += 12
    svc.observe(board("idle"), board("working"))
    clock.now += 2
    assert svc.observe(board("working"), board("done")) == []
    flush_deferred_done(svc, timers)
    assert svc.avisos.items[-1]["kind"] == "done"


def test_done_after_server_restart_mid_turn(tmp_path, sender, clock):
    svc, timers = service_with_defer(tmp_path, sender, clock)
    assert svc.observe(board("working"), board("idle")) == []
    flush_deferred_done(svc, timers)
    assert svc.avisos.items[-1]["kind"] == "done"


def test_done_not_sent_when_it_asks(service, clock):
    service.observe(None, board("working"))
    clock.now += 60
    events = service.observe(board("working"), board("idle", asks=True))
    assert [e["kind"] for e in events] == ["asks"]


def test_antispam_per_session(service, clock):
    assert service.observe(board("working"), board("blocked"))
    clock.now += 5
    assert service.observe(board("blocked"), board("working")) == []
    assert service.observe(board("working"), board("blocked")) == []
    clock.now += 6
    assert service.observe(board("working"), board("blocked"))
    other = board("working", session="other")
    assert service.observe(other, board("blocked", session="other"))


def test_payload_respects_text_pref_and_clips(service):
    event = {"kind": "asks", "session_id": SID, "name": "Uno", "pending": "palabra " * 40}
    on = service.payload(event, {"texto": True})
    assert on["title"] == "Uno te pregunta" and on["tag"] == SID and on["session_id"] == SID
    assert 0 < len(on["body"]) <= 125
    assert service.payload(event, {"texto": False})["body"] == ""


def test_blocked_dialog_push_is_generic_and_flags_deep_link(service, sender):
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {"blocked": True, "texto": True}})
    seen = []

    async def describe(session_id):
        seen.append(session_id)
        return "Quiere correr un comando"

    service.describe_blocked = describe
    event = {"kind": "blocked", "session_id": SID, "name": "Uno", "pending": "rm -rf /tmp/secreto"}
    assert asyncio.run(service.dispatch(event)) == 1
    _, data, _ = sender.sent[0]
    assert seen == [SID] and data["body"] == "Quiere correr un comando" and data["dialogo"] is True
    assert "secreto" not in json.dumps(data) and "actions" not in data


def test_blocked_push_without_recognized_dialog_has_no_flag(service, sender):
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {"blocked": True}})

    async def describe(session_id):
        raise RuntimeError("boom")

    service.describe_blocked = describe
    event = {"kind": "blocked", "session_id": SID, "name": "Uno", "pending": "hola"}
    assert asyncio.run(service.dispatch(event)) == 1
    assert "dialogo" not in sender.sent[0][1]


def test_dispatch_filters_by_prefs_and_sends_to_each_device(service, sender):
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {"asks": True, "texto": False}})
    service.store.upsert({"endpoint": FCM, "keys": KEYS, "device": "b", "prefs": {"asks": False}})
    event = {"kind": "asks", "session_id": SID, "name": "Uno", "pending": "hola"}
    assert asyncio.run(service.dispatch(event)) == 1
    assert [(e, p["body"], t) for e, p, t in sender.sent] == [(APPLE, "", 10)]


@pytest.mark.parametrize("status", [404, 410])
def test_gone_subscription_is_removed(service, sender, status):
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    sender.error = PushGone(status)
    assert asyncio.run(service.send_test(None)) == 0
    assert service.store.subs == []


def test_other_errors_keep_subscription(service, sender):
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    sender.error = PushGone(500)
    assert asyncio.run(service.send_test(None)) == 0
    assert len(service.store.subs) == 1


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


@pytest.fixture
def push_app(cfg, tmp_path, handoffs, sender, clock, enchufe):
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    svc = PushService(tmp_path, sender=sender, clock=clock)
    app = create_app(cfg, b"secret", StateStore(tmp_path), enchufe=enchufe, hub=hub, digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, push=svc)
    return app, svc, hub


@pytest.fixture
def pclient(push_app):
    with TestClient(push_app[0], base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        from conftest import PIN
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def test_endpoints_require_session(push_app):
    with TestClient(push_app[0], base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.get("/api/push/key").status_code == 401
        assert c.post("/api/push/subscribe", json=subscribe_body()).status_code == 401


def test_key_subscribe_unsubscribe(pclient, push_app):
    svc = push_app[1]
    assert pclient.get("/api/push/key").json()["key"] == svc.keys.public
    assert pclient.post("/api/push/subscribe", json=subscribe_body()).json() == {"ok": True}
    assert push_app[2].keep_alive is True
    saved = json.loads((svc.store.path).read_text())
    assert saved["subs"][0]["device"] == "iPhone"
    assert stat.S_IMODE(svc.store.path.stat().st_mode) == 0o600
    assert pclient.post("/api/push/subscribe", json=subscribe_body(done=False)).status_code == 200
    assert len(svc.store.subs) == 1 and svc.store.subs[0]["prefs"]["done"] is False
    assert pclient.post("/api/push/unsubscribe", json={"endpoint": APPLE}).json() == {"ok": True}
    assert svc.store.subs == [] and push_app[2].keep_alive is False


def test_subscribe_rejects_foreign_host_and_bad_keys(pclient):
    assert pclient.post("/api/push/subscribe", json=subscribe_body("https://evil.com/x")).status_code == 400
    assert pclient.post("/api/push/subscribe", json=subscribe_body("http://fcm.googleapis.com/x")).status_code == 400
    bad = subscribe_body()
    bad["subscription"]["keys"]["auth"] = "../../etc"
    assert pclient.post("/api/push/subscribe", json=bad).status_code == 422


def test_subscribe_max_ten(pclient):
    for i in range(10):
        assert pclient.post("/api/push/subscribe", json=subscribe_body(f"https://fcm.googleapis.com/{i}")).status_code == 200
    assert pclient.post("/api/push/subscribe", json=subscribe_body("https://fcm.googleapis.com/x")).status_code == 409
    assert pclient.post("/api/push/subscribe", json=subscribe_body("https://fcm.googleapis.com/3")).status_code == 200


def test_test_endpoint(pclient, sender, push_app):
    assert pclient.post("/api/push/test", json={}).status_code == 404
    pclient.post("/api/push/subscribe", json=subscribe_body())
    assert pclient.post("/api/push/test", json={}).json() == {"ok": True}
    assert sender.sent[0][1]["kind"] == "test"
    sender.error = PushGone(410)
    assert pclient.post("/api/push/test", json={}).status_code == 502
    assert push_app[1].store.subs == []


def test_hub_feeds_push_on_status_change(projects, sender, clock, tmp_path, enchufe):
    async def scenario():
        svc = PushService(tmp_path, sender=sender, clock=clock)
        svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
        hub = BoardHub(enchufe, DigestService(projects))
        hub.observers.append(svc.on_board)
        aplicar_snapshot(enchufe, make_snapshot("working"))
        await hub.refresh()
        assert sender.sent == []
        aplicar_snapshot(enchufe, make_snapshot("blocked"))
        await hub.refresh()
        await asyncio.gather(*list(svc._tasks))
        return svc
    asyncio.run(scenario())
    assert [p["kind"] for _, p, _ in sender.sent] == ["blocked"]
    assert sender.sent[0][1]["session_id"] == SID


def test_hub_stays_alive_while_push_is_active(projects, enchufe):
    async def scenario():
        hub = BoardHub(enchufe, DigestService(projects))
        hub.set_keep_alive(True)
        queue = hub.subscribe()
        hub.unsubscribe(queue)
        assert hub._task is not None and not hub._task.done()
        hub.set_keep_alive(False)
        assert hub._task is None
    asyncio.run(scenario())


def test_turn_end_notifies_even_if_previous_turn_asked(tmp_path, sender, clock):
    svc, timers = service_with_defer(tmp_path, sender, clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    svc.observe(board("idle", asks=True), board("working", asks=True))
    clock.now += 45
    events = svc.observe(board("working", asks=True), board("done", asks=True, pending="¿Te llegó?"))
    assert [e["kind"] for e in events] == ["asks"]
    clock.now += 100
    svc.observe(board("done", asks=True), board("working", asks=True))
    clock.now += 45
    assert svc.observe(board("working", asks=True), board("done")) == []
    flush_deferred_done(svc, timers)
    assert svc.avisos.items[-1]["kind"] == "done"


def test_done_upgrades_to_asks_when_transcript_lags(tmp_path, sender, clock):
    svc, timers = service_with_defer(tmp_path, sender, clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    svc.observe(board("idle"), board("working"))
    clock.now += 45
    assert svc.observe(board("working"), board("done", pending="texto viejo")) == []
    clock.now += 2
    assert [e["kind"] for e in observe_and_dispatch(svc, board("done"), board("done", asks=True, pending="¿Seguimos?"))] == ["asks"]
    flush_deferred_done(svc, timers)
    kinds = [e["kind"] for e in svc.avisos.items]
    assert kinds.count("done") == 0
    assert kinds[-1] == "asks"
    clock.now += 2
    assert svc.observe(board("done", asks=True), board("blocked")) == []


def test_dispatch_entorno_respeta_prefs(sender, clock, tmp_path):
    svc = PushService(tmp_path, sender=sender, clock=clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {"entornos": False}})
    assert asyncio.run(svc.dispatch_entorno("Entornos", "Se cayó x", "p/s")) == 0
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {"entornos": True, "texto": False}})
    asyncio.run(svc.dispatch_entorno("Entornos", "Se cayó hs-api (hybrid-search)", "hybrid-search/hs-api"))
    assert sender.sent[0][1]["body"] == "Revisá Entornos en Colmena."


def test_dispatch_registra_tag_en_aviso(service, sender):
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    event = {"kind": "asks", "session_id": SID, "name": "Uno", "pending": "hola"}
    asyncio.run(service.dispatch(event))
    assert service.avisos.items[-1]["tag"] == SID
    asyncio.run(service.dispatch_mr("t", "b", "12:34"))
    assert service.avisos.items[-1]["tag"] == "mr-12:34"
    service.avisos.registrar_kind("demo")
    asyncio.run(service.dispatch_simple("demo", {"title": "Demo", "body": "b", "session_id": "", "kind": "demo", "tag": "demo", "fecha": "2026-10-28"}, "demo"))
    assert service.avisos.items[-1]["tag"] == "demo"


def test_deliver_registra_entregas_no_test_ni_cerrar(service, sender):
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    asyncio.run(service.send_test(None))
    assert service._entregas.get(APPLE, {}) == {}
    asyncio.run(service.dispatch({"kind": "done", "session_id": SID, "name": "U", "pending": ""}))
    assert SID in service._entregas[APPLE]
    asyncio.run(service.cerrar([SID]))
    assert service._entregas.get(APPLE, {}) == {}


def test_cerrar_solo_a_dispositivos_con_tag_y_respeta_excluir(service, sender):
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    service.store.upsert({"endpoint": FCM, "keys": KEYS, "device": "b", "prefs": {}})
    asyncio.run(service.dispatch({"kind": "asks", "session_id": SID, "name": "U", "pending": "x"}))
    service._entregas[FCM] = {}
    antes = len(sender.sent)
    n = asyncio.run(service.cerrar([SID], excluir=APPLE))
    assert n == 0 and len(sender.sent) == antes
    n = asyncio.run(service.cerrar([SID], excluir=FCM))
    assert n == 1
    _, msg, _ = sender.sent[-1]
    assert msg == {"kind": "cerrar", "tags": [SID]}
    assert asyncio.run(service.cerrar([SID])) == 0


@pytest.mark.parametrize("status", [404, 410])
def test_gone_borra_entregas(service, sender, status):
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    service._entregas[APPLE] = {"t1": 1}
    sender.error = PushGone(status)
    asyncio.run(service.send_test(None))
    assert APPLE not in service._entregas


async def _marcar_y_cerrar(service, **kw):
    service.marcar(**kw)
    await asyncio.gather(*list(service._tasks))


def test_marcar_notifica_y_cierra_push(service, sender):
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    service.store.upsert({"endpoint": FCM, "keys": KEYS, "device": "b", "prefs": {}})
    service.avisos.add("done", "a", "", True, session_id=SID, tag=SID)
    asyncio.run(service.dispatch({"kind": "asks", "session_id": SID, "name": "U", "pending": "h"}))
    seen = []
    service.leidos_listeners.append(seen.extend)
    asyncio.run(_marcar_y_cerrar(service, session_id=SID, excluir=APPLE))
    assert seen == [SID]
    cerrar = [p for _, p, _ in sender.sent if p.get("kind") == "cerrar"]
    assert len(cerrar) == 1 and cerrar[0]["tags"] == [SID]


def test_marcar_sin_cambios_no_llama_listener(service):
    seen = []
    service.leidos_listeners.append(seen.append)
    assert service.marcar(session_id="no") == service.avisos.no_leidos
    assert seen == []


def test_marcar_visto_un_mensaje_marca_solo_sus_avisos(pclient, push_app):
    app, svc, _ = push_app
    svc.avisos.add("done", "t", "b", False, mensaje="a" * 32)
    svc.avisos.add("done", "t", "b", False, mensaje="b" * 32)
    r = pclient.post("/api/avisos/leidos", json={"mensaje": "a" * 32})
    assert r.status_code == 200 and r.json()["no_leidos"] == 1
    assert [e["leido"] for e in svc.avisos.items] == [True, False]
    assert pclient.post("/api/avisos/leidos", json={"mensaje": "zz"}).status_code == 422


def test_prefs_progreso_default_true():
    assert subscribe_body()["prefs"].get("progreso", True) is True


def test_observe_incluye_pane_id(service):
    events = service.observe(board("working"), board("blocked"))
    assert events[0]["pane_id"] == "p1"


def test_dispatch_cierre_en_app_marca_tag(sender, clock, tmp_path):
    svc = PushService(tmp_path, sender=sender, clock=clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {"cierre": True}})
    svc.presencia.connect("d")
    svc.presencia.report("d", True, "")
    seen = []
    svc.leidos_listeners.append(seen.extend)
    asyncio.run(svc.dispatch_cierre("Resumen"))
    assert seen == ["cierre"]
    assert svc.avisos.items[-1]["leido"] is True


def test_deferido_turno_con_transcript_viejo_solo_asks(tmp_path, sender, clock):
    svc, timers = service_with_defer(tmp_path, sender, clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    svc.observe(board("working", pending="turno anterior"), board("idle", pending="turno anterior"))
    assert timers.pending and timers.pending[0][0] == 3.0
    observe_and_dispatch(svc, board("idle", pending="turno anterior"), board("idle", asks=True, pending="¿Seguimos?"))
    flush_deferred_done(svc, timers)
    kinds = [e["kind"] for e in svc.avisos.items]
    assert "done" not in kinds
    assert kinds == ["asks"]


def test_deferido_done_usa_pending_actualizado(tmp_path, sender, clock):
    svc, timers = service_with_defer(tmp_path, sender, clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    svc.observe(board("working"), board("idle", pending="viejo"))
    svc._latest_board = board("idle", pending="texto nuevo")
    flush_deferred_done(svc, timers)
    assert svc.avisos.items[-1]["kind"] == "done"
    assert "texto nuevo" in svc.avisos.items[-1]["cuerpo"]


def test_deferido_cancelado_si_vuelve_a_working(tmp_path, sender, clock):
    svc, timers = service_with_defer(tmp_path, sender, clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    svc.observe(board("working"), board("idle"))
    svc._latest_board = board("working")
    flush_deferred_done(svc, timers)
    assert svc.avisos.items == []


def test_marcar_log_quien_filtro_y_cantidades(service, sender, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="orquestador.push")
    pc = "https://fcm.googleapis.com/pc-device"
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "iPhone", "prefs": {}})
    service.store.upsert({"endpoint": pc, "keys": KEYS, "device": "PC", "prefs": {}})
    asyncio.run(service.dispatch({"kind": "asks", "session_id": SID, "name": "U", "pending": "h"}))
    caplog.clear()
    asyncio.run(_marcar_y_cerrar(service, session_id=SID, excluir=pc))
    marcar_logs = [r.message for r in caplog.records if "marcados como vistos" in r.message]
    assert len(marcar_logs) == 1
    assert "por PC" in marcar_logs[0] and f"session_id={SID[:12]}…" in marcar_logs[0]
    assert "1 aviso" in marcar_logs[0] and "cierra 1 notificación" in marcar_logs[0]
    cerrar_logs = [r.message for r in caplog.records if "cierre push" in r.message]
    assert len(cerrar_logs) == 1 and "iPhone" in cerrar_logs[0]


def test_marcar_log_sin_dispositivo_con_hasta(service, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="orquestador.push")
    service.avisos.add("done", "a", "", True, session_id=SID, tag=SID)
    aviso_id = service.avisos.items[-1]["id"]
    caplog.clear()
    service.marcar(hasta=aviso_id, excluir="")
    marcar_logs = [r.message for r in caplog.records if "marcados como vistos" in r.message]
    assert len(marcar_logs) == 1
    assert "sin dispositivo" in marcar_logs[0] and f"hasta={aviso_id}" in marcar_logs[0]


def test_marcar_sin_cambios_no_loguea_marcado(service, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="orquestador.push")
    caplog.clear()
    service.marcar(session_id="no-existe", excluir=APPLE)
    assert not [r for r in caplog.records if "marcados como vistos" in r.message]


def test_cerrar_loguea_dispositivos_destino(service, sender, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="orquestador.push")
    service.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "iPhone", "prefs": {}})
    asyncio.run(service.dispatch({"kind": "asks", "session_id": SID, "name": "U", "pending": "h"}))
    caplog.clear()
    asyncio.run(service.cerrar([SID]))
    cerrar_logs = [r.message for r in caplog.records if "cierre push" in r.message]
    assert len(cerrar_logs) == 1 and "iPhone" in cerrar_logs[0]


def test_deferido_dos_fines_de_turno_un_solo_done(tmp_path, sender, clock):
    svc, timers = service_with_defer(tmp_path, sender, clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    svc.observe(board("working"), board("idle", pending="a"))
    clock.now += 1
    svc.observe(board("idle", pending="a"), board("working"))
    clock.now += 1
    svc.observe(board("working"), board("idle", pending="b"))
    assert len(timers.pending) == 1
    flush_deferred_done(svc, timers)
    assert [e["kind"] for e in svc.avisos.items].count("done") == 1
    assert "b" in svc.avisos.items[-1]["cuerpo"]


def test_avisos_prueba_valida_rechaza_kind_y_notch(pclient):
    assert pclient.post("/api/avisos/prueba", json={"kind": "nada", "destino": "celu"}).status_code == 422
    assert pclient.post("/api/avisos/prueba", json={"kind": "test", "destino": "celu"}).status_code == 422
    r = pclient.post("/api/avisos/prueba", json={"kind": "terminal", "destino": "notch"})
    assert r.status_code == 422


def test_avisos_prueba_notch_registra_y_sse_sin_push(pclient, push_app, sender):
    svc, hub = push_app[1], push_app[2]
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    hub.subscribers.add(queue)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "iPhone", "prefs": {"texto": True}})
    before = len(sender.sent)
    r = pclient.post("/api/avisos/prueba", json={"kind": "asks", "destino": "notch"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert len(sender.sent) == before
    assert queue.get_nowait() == ("aviso", {"id": r.json()["id"]})
    hub.subscribers.discard(queue)
    ent = svc.avisos.items[-1]
    assert ent["kind"] == "asks" and ent.get("prueba") is True
    assert ent["titulo"].startswith("Prueba:")


def test_avisos_prueba_celu_con_presencia_sigue_enviando(pclient, push_app, sender):
    svc = push_app[1]
    pclient.post("/api/push/subscribe", json=subscribe_body())
    svc.presencia.connect("testdev12")
    assert pclient.post("/api/presencia", json={"device": "testdev12", "visible": True}).status_code == 200
    assert svc.presencia.present() is True
    before = len(sender.sent)
    assert pclient.post("/api/avisos/prueba", json={"kind": "done", "destino": "celu"}).json() == {"ok": True}
    assert len(sender.sent) == before + 1
    assert sender.sent[-1][1]["kind"] == "done"
    assert sender.sent[-1][1]["title"].startswith("Prueba:")
    assert svc.avisos.items == []


def test_avisos_prueba_celu_404_sin_suscriptos(pclient, push_app):
    svc = push_app[1]
    assert svc.store.subs == []
    assert pclient.post("/api/avisos/prueba", json={"kind": "asks", "destino": "celu"}).status_code == 404


def test_avisos_list_excluye_prueba_y_contador(pclient, push_app):
    svc = push_app[1]
    svc.avisos.add("done", "real", "", True)
    svc.prueba_aviso_notch("blocked")
    data = pclient.get("/api/avisos").json()
    assert len(data["items"]) == 1 and data["items"][0]["titulo"] == "real"
    assert data["no_leidos"] == 1
    with_pr = pclient.get("/api/avisos?incluir_prueba=1").json()
    assert len(with_pr["items"]) == 2


def test_prueba_celu_entorno_usa_el_kind_del_frontend(sender, clock, tmp_path):
    from orquestador.avisos import KINDS_BASE as AVISO_KINDS
    svc = PushService(tmp_path, sender=sender, clock=clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    assert asyncio.run(svc.prueba_push_celu("entorno")) == 1
    assert sender.sent[0][1]["kind"] == "entorno"
    assert sender.sent[0][1]["body"] == "Se cayó hs-api (hybrid-search)"
    assert "entornos" not in AVISO_KINDS


def test_dispatch_entorno_guarda_tag_valido(sender, clock, tmp_path):
    svc = PushService(tmp_path, sender=sender, clock=clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {}})
    asyncio.run(svc.dispatch_entorno("Entornos", "Se cayó hs-api (hybrid-search)", "hybrid-search:hs-api"))
    assert svc.avisos.items[-1]["tag"] == "entorno-hybrid-search:hs-api"


def test_vapid_ilegible_se_respalda_antes_de_regenerar(tmp_path):
    (tmp_path / "vapid.json").write_text("{roto", encoding="utf-8")
    keys = VapidKeys(tmp_path)
    assert (tmp_path / "vapid.json.roto").read_text(encoding="utf-8") == "{roto"
    assert keys.public


def test_push_no_conoce_a_centinela_ni_cadenas_ni_progreso():
    import inspect
    assert "centinela_on" not in inspect.signature(PushService.__init__).parameters
    for nombre in ("dispatch_cadena", "dispatch_progreso", "cerrar_progreso"):
        assert not hasattr(PushService, nombre)


def test_ningun_aviso_manda_a_mirar_el_chat_de_centinela(sender, clock, tmp_path):
    svc = PushService(tmp_path, sender=sender, clock=clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {"texto": False}})
    asyncio.run(svc.prueba_push_celu("progreso"))
    asyncio.run(svc.prueba_push_celu("vigia"))
    assert sender.sent and all("Centinela" not in p[1]["body"] for p in sender.sent)


def _demo(**over):
    return {"title": "Algo de demo", "body": "Cuerpo demo", "session_id": "", "kind": "demo", "tag": "demo", **over}


def test_dispatch_simple_respeta_la_pref_y_registra(sender, clock, tmp_path):
    svc = PushService(tmp_path, sender=sender, clock=clock)
    svc.avisos.registrar_kind("demo")
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {"demo": True}})
    svc.store.upsert({"endpoint": "https://fcm.googleapis.com/x", "keys": KEYS, "device": "b", "prefs": {"demo": False}})
    msg = _demo(fecha="2026-10-30")
    assert asyncio.run(svc.dispatch_simple("demo", msg, "demo", fecha="2026-10-30")) == 1
    assert [s[:2] for s in sender.sent] == [(APPLE, msg)]
    item = svc.avisos.items[-1]
    assert (item["kind"], item["titulo"], item["fecha"], item["tag"]) == ("demo", "Algo de demo", "2026-10-30", "demo")
    assert asyncio.run(svc.dispatch_simple("demo", msg, "demo", "https://fcm.googleapis.com/x")) == 1


def test_registrar_prueba_suma_el_kind_al_aviso_de_prueba(sender, clock, tmp_path):
    svc = PushService(tmp_path, sender=sender, clock=clock)
    svc.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "a", "prefs": {"demo": False}})
    assert "demo" not in svc.prueba_kinds()
    with pytest.raises(ValueError):
        asyncio.run(svc.prueba_push_celu("demo"))
    svc.avisos.registrar_kind("demo")
    svc.registrar_prueba("demo", lambda: _demo())
    assert "demo" in svc.prueba_kinds()
    assert asyncio.run(svc.prueba_push_celu("demo")) == 1
    assert sender.sent[0][1] == _demo(title="Prueba: Algo de demo")


def test_prefs_acepta_extras_bool():
    from orquestador.push import Prefs
    assert Prefs(demo=False, otra=True).model_dump()["demo"] is False


@pytest.mark.parametrize("extra", [{"Demo": True}, {"de-mo": True}, {"x" * 21: True}, {"demo": "si"}, {"demo": 1},
                                   {"demo1": True}, {k * 2: True for k in "abcdefghijk"}])
def test_prefs_rechaza_extras_invalidos(extra):
    from pydantic import ValidationError

    from orquestador.push import Prefs
    with pytest.raises(ValidationError):
        Prefs(**extra)


def test_subscribe_rechaza_pref_invalida(pclient, push_app):
    assert pclient.post("/api/push/subscribe", json=subscribe_body(**{"no-va": True})).status_code == 422
    assert pclient.post("/api/push/subscribe", json=subscribe_body(demo=False)).status_code == 200
    assert push_app[1].store.subs[0]["prefs"]["demo"] is False
