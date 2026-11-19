from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from conftest import ORIGIN, PIN, SID, make_snapshot
from fastapi.testclient import TestClient

from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.colmena_pestana import MARCA, pedido_desde_comando_bash
from orquestador.config import Config, hash_pin
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.ganchos.mensaje import Ids, MensajeGancho
from orquestador.pedidos_pestana import PedidosPestanaStore
from orquestador.push import PushService
from orquestador.state import StateStore

APPLE = "https://web.push.apple.com/QGxyz"
KEYS = {"p256dh": "BPubKeyPubKeyPubKeyPubKey", "auth": "AuthSecretAuth12"}


class Wall:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


class Mono:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Sender:
    def __init__(self):
        self.sent = []

    def __call__(self, info, data, vapid, claims, timeout):
        self.sent.append(json.loads(data))


def _msg_bash(sid, comando):
    return MensajeGancho(
        evento="PostToolUse",
        origen="claude",
        ids=Ids(None, None, None, None, sid),
        datos={"tool_name": "Bash", "tool_input": {"command": comando}},
    )


def _json_cmd(**kw):
    body = json.dumps(kw, ensure_ascii=False)
    return f"echo '{MARCA} {body}'"


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


@pytest.fixture
def wall():
    return Wall()


@pytest.fixture
def sender():
    return Sender()


def armar_app(tmp_path, projects, handoffs, enchufe, *, plan_cwds=None, push=None, protected=None):
    cfg = Config(
        pin=hash_pin(PIN),
        claude_projects_dir=str(projects),
        claude_cwd=str(tmp_path),
    )
    if plan_cwds is not None:
        cfg.plan_cwds = plan_cwds
    if protected is not None:
        cfg.protected_workspaces = protected
    digests = DigestService(cfg.projects_dir())
    app = create_app(
        cfg,
        b"secret",
        StateStore(tmp_path),
        hub=BoardHub(enchufe, digests),
        digests=digests,
        dist=tmp_path / "nodist",
        handoffs_dir=handoffs,
        uploads_dir=tmp_path / "uploads",
        enchufe=enchufe,
        push=push,
    )
    return app


@pytest.fixture
def apagada_app(tmp_path, projects, handoffs, enchufe, wall, sender):
    push = PushService(tmp_path, sender=sender, wall=wall)
    push.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "x", "prefs": {"texto": True, "pestana": True}})
    app = armar_app(tmp_path, projects, handoffs, enchufe, push=push, plan_cwds=["/tmp"])
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c, app, push, sender, wall


@pytest.fixture
def protegida_app(tmp_path, projects, handoffs, enchufe, wall, sender):
    push = PushService(tmp_path, sender=sender, wall=wall)
    push.store.upsert({"endpoint": APPLE, "keys": KEYS, "device": "x", "prefs": {"texto": True, "pestana": True}})
    app = armar_app(tmp_path, projects, handoffs, enchufe, push=push, plan_cwds=["/tmp"], protected=["Dos"])
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c, app, push, sender, wall


# --- hook parsing ---


def test_pedido_json_valido():
    cmd = _json_cmd(carpeta="/tmp", mensaje="hola")
    assert pedido_desde_comando_bash(cmd) == {"carpeta": "/tmp", "mensaje": "hola"}


def test_pedido_json_con_nombre():
    cmd = _json_cmd(carpeta="/tmp", mensaje="x", nombre="Mi tab")
    assert pedido_desde_comando_bash(cmd) == {"carpeta": "/tmp", "mensaje": "x", "nombre": "Mi tab"}


def test_pedido_json_invalido_ignora():
    assert pedido_desde_comando_bash(f"echo '{MARCA} no-json'") is None


def test_pedido_mensaje_largo_ignora():
    cmd = _json_cmd(carpeta="/tmp", mensaje="x" * 4001)
    assert pedido_desde_comando_bash(cmd) is None


def test_pedido_multi_tarjeta_y_pestanas():
    cmd = _json_cmd(
        carpeta="/tmp",
        tarjeta="Mi espacio",
        pestanas=[
            {"nombre": "API", "tipo": "claude", "mensaje": "arrancá acá"},
            {"nombre": "Logs", "tipo": "terminal", "carpeta": "/tmp", "comando": "tail -f log"},
        ],
    )
    out = pedido_desde_comando_bash(cmd)
    assert out and out["tarjeta"] == "Mi espacio"
    assert len(out["pestanas"]) == 2
    assert out["pestanas"][0]["tipo"] == "claude"
    assert out["pestanas"][1]["comando"] == "tail -f log"


def test_pedido_mas_de_seis_pestanas_ignora():
    tabs = [{"nombre": f"T{i}", "tipo": "terminal"} for i in range(7)]
    cmd = _json_cmd(carpeta="/tmp", pestanas=tabs)
    assert pedido_desde_comando_bash(cmd) is None


def test_pedido_tipo_invalido_ignora():
    cmd = _json_cmd(carpeta="/tmp", pestanas=[{"nombre": "X", "tipo": "vim"}])
    assert pedido_desde_comando_bash(cmd) is None


def test_comando_con_nueva_linea_o_cr_queda_en_una_linea():
    cmd = _json_cmd(
        carpeta="/tmp",
        pestanas=[{"nombre": "Shell", "tipo": "terminal", "comando": "ls\nrm -rf x"}],
    )
    out = pedido_desde_comando_bash(cmd)
    assert out is not None
    assert out["pestanas"][0]["comando"] == "ls rm -rf x"
    assert "\n" not in out["pestanas"][0]["comando"]
    assert "\r" not in out["pestanas"][0]["comando"]

    cmd2 = _json_cmd(
        carpeta="/tmp",
        pestanas=[{"nombre": "Shell2", "tipo": "terminal", "comando": "ls\r"}],
    )
    out2 = pedido_desde_comando_bash(cmd2)
    assert out2 is not None
    assert out2["pestanas"][0]["comando"] == "ls"


def test_mensaje_tope_3900():
    from orquestador.colmena_pestana import MAX_MENSAJE, PREFIJO_PEDIDO
    from orquestador.mensaje import MAX_TEXT

    assert MAX_MENSAJE == 3900
    assert len(PREFIJO_PEDIDO) + MAX_MENSAJE <= MAX_TEXT
    assert pedido_desde_comando_bash(_json_cmd(carpeta="/tmp", mensaje="x" * 3900)) is not None
    assert pedido_desde_comando_bash(_json_cmd(carpeta="/tmp", mensaje="x" * 3901)) is None
    tabs = [{"nombre": "A", "tipo": "claude", "mensaje": "x" * 3901}]
    assert pedido_desde_comando_bash(_json_cmd(carpeta="/tmp", pestanas=tabs)) is None


@pytest.mark.parametrize("raro", ["\u202e", "\u200b", "\u00a0"])
def test_comando_con_bidi_o_invisible_rechazado(raro):
    import codecs

    c = codecs.decode(raro, "unicode_escape")
    tabs = [{"nombre": "T", "tipo": "terminal", "comando": f"ls{c}-la"}]
    assert pedido_desde_comando_bash(_json_cmd(carpeta="/tmp", pestanas=tabs)) is None
    ok = [{"nombre": "T", "tipo": "terminal", "comando": "ls -la"}]
    assert pedido_desde_comando_bash(_json_cmd(carpeta="/tmp", pestanas=ok))["pestanas"][0]["comando"] == "ls -la"


# --- store ---


def test_store_fila_de_tres_por_sesion():
    mono = Mono()
    store = PedidosPestanaStore(monotonic=mono)
    o = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}
    creados = []
    for msg in ("a", "b", "c"):
        item, motivo = store.crear("/tmp", msg, None, o)
        assert item is not None and motivo is None
        creados.append(item)
        mono.t += 31
    for item in creados:
        assert store.get(item["id"])["estado"] == "pendiente"
    pendientes = store.listar_pendientes()
    assert sorted(p["mensaje"] for p in pendientes) == ["a", "b", "c"]
    assert store.pendientes_de(SID) == [it["id"] for it in creados]
    item, motivo = store.crear("/tmp", "d", None, o)
    assert item is None and motivo == "fila_llena"
    assert len(store.listar_pendientes()) == 3


def test_store_cooldown_devuelve_motivo():
    mono = Mono()
    store = PedidosPestanaStore(monotonic=mono)
    o = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}
    item, motivo = store.crear("/tmp", "a", None, o)
    assert item and motivo is None
    item, motivo = store.crear("/tmp", "b", None, o)
    assert item is None and motivo == "cooldown"


def test_store_libera_lugar_en_la_fila_al_resolver():
    mono = Mono()
    store = PedidosPestanaStore(monotonic=mono)
    o = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}
    ids = []
    for msg in ("a", "b", "c"):
        ids.append(store.crear("/tmp", msg, None, o)[0]["id"])
        mono.t += 31
    store.marcar(ids[1], "abierto")
    assert store.pendientes_de(SID) == [ids[0], ids[2]]
    item, motivo = store.crear("/tmp", "d", None, o)
    assert item is not None and motivo is None


def _store_con_descartes(**kw):
    store = PedidosPestanaStore(**kw)
    descartes = []
    store.on_descarte(lambda origen, motivo: descartes.append((origen.get("session_id"), motivo)))
    return store, descartes


def test_descarte_fila_llena_avisa_al_origen():
    mono = Mono()
    store, descartes = _store_con_descartes(monotonic=mono)
    o = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}
    for msg in ("a", "b", "c"):
        store.crear("/tmp", msg, None, o)
        mono.t += 31
    assert descartes == []
    store.crear("/tmp", "d", None, o)
    assert descartes == [(SID, "fila_llena")]


def test_descarte_cooldown_avisa_al_origen():
    store, descartes = _store_con_descartes(monotonic=Mono())
    o = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}
    store.crear("/tmp", "a", None, o)
    store.crear("/tmp", "b", None, o)
    assert descartes == [(SID, "cooldown")]


def test_permitir_consume_el_cooldown_antes_de_crear():
    mono = Mono()
    store, descartes = _store_con_descartes(monotonic=mono)
    o = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}
    assert store.permitir(o) is True
    item, _ = store.crear("", "", None, o, accion="cerrar", cierre={"objetivo": "pestana"}, cooldown=False)
    assert item is not None
    assert store.permitir(o) is False
    assert descartes == [(SID, "cooldown")]
    mono.t += 31
    assert store.permitir(o) is True


def test_descarte_vencido_avisa_al_origen(wall):
    store, descartes = _store_con_descartes(wall=wall)
    o = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}
    store.crear("/tmp", "a", None, o)
    wall.now += 601
    store.listar_pendientes()
    store.listar_pendientes()
    assert descartes == [(SID, "vencido")]


def test_descarte_tope_avisa_al_mas_viejo(wall):
    store, descartes = _store_con_descartes(wall=wall, monotonic=Mono())
    for i in range(7):
        store.crear("/tmp", "x", None, {"pane_id": f"w{i}:p1", "nombre": "S", "session_id": f"sid-{i}"})
        wall.now += 1
    assert descartes and all(m == "tope" for _, m in descartes)
    assert descartes[0][0] == "sid-0"


def test_descarte_resuelto_no_avisa():
    store, descartes = _store_con_descartes(monotonic=Mono())
    o = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}
    item, _ = store.crear("/tmp", "a", None, o)
    store.marcar(item["id"], "rechazado")
    assert descartes == []


def test_descarte_listener_que_lanza_no_rompe(caplog):
    store = PedidosPestanaStore(monotonic=Mono())
    vistos = []

    def malo(origen, motivo):
        raise RuntimeError("boom")

    store.on_descarte(malo)
    store.on_descarte(lambda origen, motivo: vistos.append(motivo))
    o = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}
    store.crear("/tmp", "a", None, o)
    item, motivo = store.crear("/tmp", "b", None, o)
    assert item is None and motivo == "cooldown"
    assert vistos == ["cooldown"]
    assert "descarte" in caplog.text


def test_store_vence_a_los_10_min(wall):
    store = PedidosPestanaStore(wall=wall)
    o = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}
    p, _ = store.crear("/tmp", "msg", None, o)
    wall.now += 601
    assert store.get(p["id"])["estado"] == "vencido"
    assert store.listar_pendientes() == []


# --- integración app ---


def test_linea_valida_crea_pedido_aviso_y_push(apagada_app):
    c, app, push, sender, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="arrancá")), "w1:p1")
    lista = c.get("/api/pedidos-pestana").json()
    assert len(lista) == 1
    assert lista[0]["carpeta"] == "/tmp" and lista[0]["mensaje"] == "arrancá"
    avisos = [e for e in push.avisos.items if e["kind"] == "pestana"]
    assert len(avisos) == 1
    assert avisos[0]["titulo"] == "Pedido de pestaña"
    assert "/tmp" in avisos[0]["cuerpo"] and "pestaña" in avisos[0]["cuerpo"]
    assert avisos[0].get("pedido") == lista[0]["id"]
    assert sender.sent
    assert sender.sent[0].get("url") == f"/?pedido={lista[0]['id']}"


def test_pedido_crea_tarjeta_y_avisa(apagada_app):
    c, app, push, sender, _ = apagada_app
    app.state.pestana_desde_bash(
        _msg_bash("sid-otra", _json_cmd(carpeta="/tmp", mensaje="hacé X")),
        "w1:p1",
    )
    assert len(c.get("/api/pedidos-pestana").json()) == 1
    assert len([e for e in push.avisos.items if e["kind"] == "pestana"]) == 1
    assert sender.sent


def test_sesion_no_reconocida_descarta(apagada_app):
    _, app, push, sender, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="x")), None)
    assert not push.avisos.items and not sender.sent


def test_carpeta_no_permitida_descarta(apagada_app):
    _, app, push, sender, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/no-permitida", mensaje="x")), "w1:p1")
    assert not push.avisos.items and not sender.sent


def test_abrir_crea_pestana_y_pegado(apagada_app, enchufe):
    c, app, push, _, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="brief")), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]

    app.state.tacciones.abrir_desde_pedido_pestana = AsyncMock(
        return_value={
            "ok": True,
            "pane_id": "w2:p1",
            "pane_ids": ["w2:p1"],
            "detalle": [{"pane_id": "w2:p1", "tipo": "claude", "mensaje": "brief", "pegado": True}],
        }
    )
    mensaje = AsyncMock(return_value={"ok": True, "pane_id": "w2:p1"})
    app.state.mensajes.execute = mensaje

    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 200 and r.json() == {"ok": True, "pane_id": "w2:p1", "pane_ids": ["w2:p1"]}
    mensaje.assert_awaited_once()
    body = mensaje.await_args[0][0]
    assert body.texto.endswith("brief") and body.origen == "pedido-pestana" and body.pane_id == "w2:p1"
    assert app.state.pedidos_pestana.get(pid)["estado"] == "abierto"


def test_abrir_pedido_pega_con_prefijo(apagada_app):
    from orquestador.colmena_pestana import PREFIJO_PEDIDO
    from orquestador.mensaje import MAX_TEXT

    c, app, _, _, _ = apagada_app
    largo = "y" * 3900
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", pestanas=[
        {"nombre": "A", "tipo": "claude", "mensaje": "uno"},
        {"nombre": "B", "tipo": "claude", "mensaje": largo}])), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    app.state.tacciones.abrir_desde_pedido_pestana = AsyncMock(return_value={
        "ok": True, "pane_id": "w2:p1", "pane_ids": ["w2:p1", "w2:p2"],
        "detalle": [{"pane_id": "w2:p1", "tipo": "claude", "mensaje": "uno", "pegado": True},
                    {"pane_id": "w2:p2", "tipo": "claude", "mensaje": largo + "zzzz", "pegado": True}]})
    mensaje = AsyncMock(return_value={"ok": True})
    app.state.mensajes.execute = mensaje
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 200
    textos = [call[0][0].texto for call in mensaje.await_args_list]
    assert textos[0] == PREFIJO_PEDIDO + "uno"
    assert textos[1].startswith(PREFIJO_PEDIDO + "yyy") and len(textos[1]) <= MAX_TEXT


def test_abrir_pedido_arranca_en_default(apagada_app):
    c, app, _, _, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="brief")), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    abrir = AsyncMock(return_value={"ok": True, "pane_id": "w2:p1",
                                    "detalle": [{"pane_id": "w2:p1", "tipo": "claude", "mensaje": "brief",
                                                 "pegado": True}]})
    app.state.tacciones.abrir_desde_pedido_pestana = abrir
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 200
    assert abrir.await_args.kwargs.get("permiso") == "default"


def test_abrir_dos_veces_409(apagada_app):
    c, app, _, _, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="x")), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    app.state.tacciones.abrir_desde_pedido_pestana = AsyncMock(
        return_value={
            "ok": True,
            "pane_id": "w9:p9",
            "detalle": [{"pane_id": "w9:p9", "tipo": "claude", "mensaje": "x", "pegado": True}],
        }
    )
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 200
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 409


def test_rechazar_y_reabrir_409(apagada_app):
    c, app, _, _, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="x")), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    assert c.post(f"/api/pedidos-pestana/{pid}/rechazar").status_code == 200
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 409


def test_inexistente_404(apagada_app):
    c, _, _, _, _ = apagada_app
    fake = "00000000-0000-4000-8000-000000000099"
    assert c.post(f"/api/pedidos-pestana/{fake}/abrir").status_code == 404
    assert c.post(f"/api/pedidos-pestana/{fake}/rechazar").status_code == 404


def test_sse_pedido_pestana(apagada_app):
    _, app, _, _, _ = apagada_app
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    app.state.hub.subscribers.add(queue)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="x")), "w1:p1")
    evt = queue.get_nowait()
    assert evt[0] == "pedido_pestana" and evt[1]["estado"] == "pendiente"
    app.state.hub.subscribers.discard(queue)


# --- abrir en el grupo de la pestaña que pidió ---


def _abrir_con_mocks(c, app, enchufe, origen_pane, grupo):
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="brief")), origen_pane)
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    app.state.tacciones.grupo_de_sesion = AsyncMock(return_value=grupo)
    abrir = AsyncMock(
        return_value={
            "ok": True,
            "pane_id": "g3:p9",
            "detalle": [{"pane_id": "g3:p9", "tipo": "claude", "mensaje": "brief", "pegado": True}],
        }
    )
    app.state.tacciones.abrir_desde_pedido_pestana = abrir
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    return pid, abrir


def test_abrir_usa_el_grupo_del_origen(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    pid, abrir = _abrir_con_mocks(c, app, enchufe, "g3:p7", "g3")
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 200
    app.state.tacciones.grupo_de_sesion.assert_awaited_once_with("g3:p7")
    assert abrir.await_args.kwargs.get("grupo") == "g3"


def test_abrir_sin_grupo_del_origen_abre_aparte(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    pid, abrir = _abrir_con_mocks(c, app, enchufe, "w1:p1", None)
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 200
    assert abrir.await_args.kwargs.get("grupo") is None


def test_abrir_grupo_cerrado_reintenta_sin_grupo(apagada_app, enchufe):
    from orquestador.traspaso import TraspasoError

    c, app, _, _, _ = apagada_app
    pid, abrir = _abrir_con_mocks(c, app, enchufe, "g3:p7", "g3")
    abrir.side_effect = [
        TraspasoError(409, "Ese grupo ya no está: no abrí nada"),
        {
            "ok": True,
            "pane_id": "g4:p1",
            "detalle": [{"pane_id": "g4:p1", "tipo": "claude", "mensaje": "brief", "pegado": True}],
        },
    ]
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 200 and r.json()["pane_id"] == "g4:p1"
    assert [call.kwargs.get("grupo") for call in abrir.await_args_list] == ["g3", None]


@pytest.fixture
def guardian_app(apagada_app):
    from orquestador.enchufe.mux import Mux

    c, app, _, _, _ = apagada_app
    g = FakeTerminales(nombre="guardian")
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    mux = Mux([h, g], nuevas_en="guardian")
    app.state.tacciones.enchufe = mux
    return app.state.tacciones, g


def test_grupo_de_sesion_devuelve_su_espacio(guardian_app):
    tacc, g = guardian_app
    g.proximos_ids = [("g3", None, None)]
    creado = asyncio.run(g.crear_espacio("uno", "/tmp"))
    assert asyncio.run(tacc.grupo_de_sesion(creado.sesion_id)) == "g3"


def test_grupo_de_sesion_inexistente_o_herdr_es_none(guardian_app):
    tacc, _ = guardian_app
    assert asyncio.run(tacc.grupo_de_sesion("g8:p1")) is None
    assert asyncio.run(tacc.grupo_de_sesion("w1:p1")) is None
    assert asyncio.run(tacc.grupo_de_sesion("")) is None


def test_grupo_de_sesion_sin_guardian_es_none(apagada_app):
    _, app, _, _, _ = apagada_app
    assert asyncio.run(app.state.tacciones.grupo_de_sesion("g3:p7")) is None


def test_crear_pedido_multi_en_api(apagada_app):
    c, app, push, _, _ = apagada_app
    body = {
        "carpeta": "/tmp",
        "pestanas": [
            {"nombre": "API", "tipo": "claude", "mensaje": "hola"},
            {"nombre": "Shell", "tipo": "terminal"},
        ],
    }
    cmd = _json_cmd(**body)
    app.state.pestana_desde_bash(_msg_bash(SID, cmd), "w1:p1")
    lista = c.get("/api/pedidos-pestana").json()
    assert len(lista) == 1
    assert len(lista[0]["pestanas"]) == 2


def test_abrir_multi_pestanas(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    cmd = _json_cmd(
        carpeta="/tmp",
        tarjeta="Workspace",
        pestanas=[
            {"nombre": "API", "tipo": "claude", "mensaje": "brief"},
            {"nombre": "Log", "tipo": "terminal", "comando": "ls"},
        ],
    )
    app.state.pestana_desde_bash(_msg_bash(SID, cmd), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    app.state.tacciones.grupo_de_sesion = AsyncMock(return_value=None)
    abrir = AsyncMock(
        return_value={
            "ok": True,
            "pane_id": "g1:p1",
            "pane_ids": ["g1:p1", "g1:p2"],
            "detalle": [
                {"pane_id": "g1:p1", "tipo": "claude", "mensaje": "brief", "pegado": True},
                {"pane_id": "g1:p2", "tipo": "terminal", "pegado": None},
            ],
        }
    )
    app.state.tacciones.abrir_desde_pedido_pestana = abrir
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 200
    data = r.json()
    assert data["pane_ids"] == ["g1:p1", "g1:p2"]
    abrir.assert_awaited()


def test_abrir_multi_tope_hora(apagada_app):
    c, app, _, _, _ = apagada_app
    app.state.pestana_desde_bash(
        _msg_bash(
            SID,
            _json_cmd(
                carpeta="/tmp",
                pestanas=[{"nombre": "A", "tipo": "claude", "mensaje": "x"}],
            ),
        ),
        "w1:p1",
    )
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    from orquestador.traspaso import TraspasoError

    app.state.tacciones.abrir_desde_pedido_pestana = AsyncMock(
        side_effect=TraspasoError(429, "tope", {"retry_after": 60})
    )
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 429


def test_abrir_marca_abierto_al_crear_aunque_no_pegue(apagada_app):
    c, app, _, _, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="brief")), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    app.state.tacciones.grupo_de_sesion = AsyncMock(return_value=None)
    queue: asyncio.Queue = asyncio.Queue(maxsize=32)
    app.state.hub.subscribers.add(queue)
    visto: list[str] = []

    async def abrir(*a, **kw):
        kw["al_crear"]()
        visto.append(app.state.pedidos_pestana.get(pid)["estado"])
        return {
            "ok": True,
            "pane_id": "g1:p1",
            "detalle": [{"pane_id": "g1:p1", "tipo": "claude", "mensaje": "brief", "pegado": False, "nombre": "A"}],
        }

    app.state.tacciones.abrir_desde_pedido_pestana = abrir
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    app.state.hub.subscribers.discard(queue)
    assert r.status_code == 200 and r.json()["pegado"] is False
    assert visto == ["abierto"]
    assert app.state.pedidos_pestana.get(pid)["estado"] == "abierto"
    eventos = []
    while not queue.empty():
        eventos.append(queue.get_nowait())
    abiertos = [e for e in eventos if e[0] == "pedido_pestana" and e[1].get("estado") == "abierto"]
    assert len(abiertos) == 1


@pytest.mark.parametrize("pegado", [False, True])
def test_abrir_sin_pegado_avisa(apagada_app, caplog, pegado):
    c, app, push, _, _ = apagada_app
    texto = "texto-secreto-del-pedido"
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje=texto)), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    app.state.tacciones.grupo_de_sesion = AsyncMock(return_value=None)
    app.state.tacciones.abrir_desde_pedido_pestana = AsyncMock(
        return_value={
            "ok": True,
            "pane_id": "g1:p1",
            "detalle": [{"pane_id": "g1:p1", "tipo": "claude", "mensaje": texto, "pegado": pegado, "nombre": "API"}],
        }
    )
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    dispatch = AsyncMock(return_value=1)
    push.dispatch_terminal = dispatch
    with caplog.at_level("WARNING"):
        assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 200
    if pegado:
        dispatch.assert_not_awaited()
        return
    dispatch.assert_awaited_once()
    args = dispatch.await_args
    titulo, cuerpo = args.args[0], args.args[1]
    assert titulo == "No pude pegar el mensaje"
    assert "API" in cuerpo
    assert texto not in repr(args)
    avisos = [r for r in caplog.records if "no pude pegar" in r.getMessage().lower()]
    assert avisos and all(texto not in r.getMessage() for r in avisos)


# --- aviso al origen ---


def test_cuarto_pedido_avisa_fila_llena_al_origen(apagada_app):
    from orquestador.avisos_origen import ORIGEN, TEXTOS

    c, app, _, _, _ = apagada_app
    mensaje = AsyncMock(return_value={"ok": True})
    app.state.mensajes.execute = mensaje
    app.state.hub.board = {"workspaces": [{"tabs": [{"agents": [
        {"pane_id": "w1:p1", "session_id": SID, "status": "idle"}]}]}]}
    store = app.state.pedidos_pestana
    mono = Mono()
    store.monotonic = mono
    for i in range(4):
        app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje=f"secreto-{i}")), "w1:p1")
        mono.t += 31
    assert len(c.get("/api/pedidos-pestana").json()) == 3
    # El transcript del fixture termina en una pregunta a Ando: el aviso espera.
    mensaje.assert_not_awaited()
    al_tablero = next(o for o in app.state.hub.observers
                      if type(getattr(o, "__self__", None)).__name__ == "AvisosOrigen")
    al_tablero(None, {"workspaces": [{"tabs": [{"agents": [
        {"pane_id": "w1:p1", "session_id": SID, "status": "idle", "asks_user": False}]}]}]})
    mensaje.assert_awaited_once()
    body = mensaje.await_args[0][0]
    assert body.pane_id == "w1:p1" and body.origen == ORIGEN
    assert body.texto == TEXTOS["fila_llena"]
    assert "secreto" not in body.texto


def test_aviso_al_origen_no_se_pide_desde_la_api(apagada_app):
    c, _, _, _, _ = apagada_app
    r = c.post("/api/mensaje/execute", json={"id": "aviso-12345678", "pane_id": "w1:p1", "texto": "x",
                                             "origen": "pedido-pestana-aviso"})
    assert r.status_code == 400



# --- pedido para cerrar una terminal común ---


def test_pedido_cerrar_sin_carpeta():
    cmd = _json_cmd(accion="cerrar", terminal="w2:p1")
    assert pedido_desde_comando_bash(cmd) == {"accion": "cerrar", "terminal": "w2:p1"}


def test_pedido_cerrar_terminal_invalida_ignora():
    assert pedido_desde_comando_bash(_json_cmd(accion="cerrar")) is None
    assert pedido_desde_comando_bash(_json_cmd(accion="cerrar", terminal="")) is None
    assert pedido_desde_comando_bash(_json_cmd(accion="cerrar", terminal="x" * 65)) is None
    assert pedido_desde_comando_bash(_json_cmd(accion="cerrar", terminal=3)) is None
    assert pedido_desde_comando_bash(_json_cmd(accion="borrar", terminal="w2:p1")) is None


def _tablero_con_terminal(app, **extra):
    # Igual a lo que da el enchufe de prueba para w2:p1 (sin terminal_id ni carpeta).
    term = {"pane_id": "w2:p1", "terminal_id": "", "titulo": "logs", "cwd": "",
            "proceso": "", "estado": "prompt", "protegida": False, **extra}
    app.state.hub.board = {"workspaces": [{"id": "w2", "label": "Back", "tabs": [
        {"id": "w2:t1", "label": "Logs", "agents": [], "terminales": [term]},
        {"id": "w1:t1", "label": "API", "agents": [{"pane_id": "w1:p1", "session_id": SID, "status": "idle"}],
         "terminales": []}]}]}


@pytest.mark.parametrize("sel", ["w2:p1", "logs", "LOGS"])
def test_pedido_cerrar_crea_tarjeta(apagada_app, sel):
    c, app, _, sender, _ = apagada_app
    _tablero_con_terminal(app, cwd="~/tmp", terminal_id="t1")
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", terminal=sel)), "w1:p1")
    filas = c.get("/api/pedidos-pestana").json()
    assert len(filas) == 1
    assert filas[0]["accion"] == "cerrar"
    assert filas[0]["terminal"]["pane_id"] == "w2:p1"
    assert filas[0]["terminal"]["cwd"] == "~/tmp"
    item = app.state.pedidos_pestana.get(filas[0]["id"])
    assert item["terminal"]["terminal_id"] == "t1"
    assert item["terminal"]["workspace_id"] == "w2" and item["terminal"]["tab_id"] == "w2:t1"
    assert sender.sent and sender.sent[-1]["title"] == "Pedido para cerrar una terminal"


@pytest.mark.parametrize("sel", ["w1:p1", "w9:p9", "nada", "API"])
def test_pedido_cerrar_terminal_que_no_es_comun_no_crea(apagada_app, sel):
    c, app, _, _, _ = apagada_app
    _tablero_con_terminal(app)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", terminal=sel)), "w1:p1")
    assert c.get("/api/pedidos-pestana").json() == []


def test_pedido_cerrar_nombre_ambiguo_no_crea(apagada_app):
    c, app, _, _, _ = apagada_app
    _tablero_con_terminal(app)
    tabs = app.state.hub.board["workspaces"][0]["tabs"]
    tabs[1]["terminales"] = [dict(tabs[0]["terminales"][0], pane_id="w1:p5")]
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", terminal="logs")), "w1:p1")
    assert c.get("/api/pedidos-pestana").json() == []


def test_pedido_cerrar_terminal_inexistente_avisa_al_origen(apagada_app):
    from orquestador.avisos_origen import TEXTOS

    _, app, _, _, _ = apagada_app
    mensaje = AsyncMock(return_value={"ok": True})
    app.state.mensajes.execute = mensaje
    _tablero_con_terminal(app)
    app.state.hub.board["workspaces"][0]["tabs"][1]["agents"][0]["asks_user"] = False
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", terminal="nada")), "w1:p1")
    mensaje.assert_awaited_once()
    assert mensaje.await_args[0][0].texto == TEXTOS["terminal_no_encontrada"]


def test_aprobar_pedido_cerrar_cierra_la_terminal(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    _tablero_con_terminal(app)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", terminal="w2:p1")), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 200, r.text
    assert r.json()["cerrada"] is True
    assert [x[1] for x in enchufe.calls_of("cerrar")] == ["w2:t1"]
    cierres = app.state.tacciones.cierres.state.cierres()
    assert cierres[-1]["origen"] == "pedido-pestana"
    assert c.get("/api/pedidos-pestana").json() == []
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 409


def test_aprobar_pedido_cerrar_si_cambio_el_proceso_no_cierra(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    _tablero_con_terminal(app, proceso="vim", estado="corriendo")
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", terminal="w2:p1")), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 409
    assert enchufe.calls_of("cerrar") == []
    assert len(c.get("/api/pedidos-pestana").json()) == 1


def test_aprobar_pedido_cerrar_de_una_terminal_que_ya_no_esta_lo_saca(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    _tablero_con_terminal(app, pane_id="w7:p7")
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", terminal="w7:p7")), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 404 and r.json()["detail"] == "la terminal ya no está"
    assert c.get("/api/pedidos-pestana").json() == []


def _pedir_cierre(c, app):
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", terminal="w2:p1")), "w1:p1")
    return c.get("/api/pedidos-pestana").json()[0]["id"]


def _cambiar_pane(enchufe, **campos):
    from terminales_support import aplicar_snapshot, snap_de

    snap = snap_de(enchufe)
    for p in snap["panes"]:
        if p["pane_id"] == "w2:p1":
            p.update(campos)
    aplicar_snapshot(enchufe, snap)


def test_aprobar_pedido_cerrar_si_ahora_es_otra_terminal_no_cierra_y_lo_descarta(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    _tablero_con_terminal(app)
    pid = _pedir_cierre(c, app)
    _cambiar_pane(enchufe, terminal_id="otra")
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 409 and r.json()["detail"] == "ya es otra terminal: descarté el pedido"
    assert enchufe.calls_of("cerrar") == []
    assert c.get("/api/pedidos-pestana").json() == []


def test_aprobar_pedido_cerrar_si_cambio_de_carpeta_no_cierra_y_sigue_pendiente(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    _tablero_con_terminal(app)
    pid = _pedir_cierre(c, app)
    _cambiar_pane(enchufe, foreground_cwd="/otra/carpeta")
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 409 and r.json()["detail"] == "la terminal se movió o cambió de carpeta desde el pedido"
    assert enchufe.calls_of("cerrar") == []
    assert len(c.get("/api/pedidos-pestana").json()) == 1


def test_aprobar_pedido_cerrar_compara_dentro_del_lock(apagada_app, enchufe, monkeypatch):
    c, app, _, _, _ = apagada_app
    _tablero_con_terminal(app)
    # Comparte pestaña con otra terminal: el cierre pasa por el lock.
    from terminales_support import aplicar_snapshot, snap_de

    snap = snap_de(enchufe)
    snap["panes"].append({"pane_id": "w2:p3", "tab_id": "w2:t1", "workspace_id": "w2"})
    for t in snap["tabs"]:
        if t["tab_id"] == "w2:t1":
            t["pane_count"] = 2
    aplicar_snapshot(enchufe, snap)
    pid = _pedir_cierre(c, app)
    tacciones = app.state.tacciones
    orig = tacciones._check_target
    n = {"v": 0}

    async def envuelto(op, h):
        n["v"] += 1
        if n["v"] == 2:
            _cambiar_pane(enchufe, tab_id="w2:t2")
        return await orig(op, h)

    monkeypatch.setattr(tacciones, "_check_target", envuelto)
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 409
    assert enchufe.calls_of("cerrar") == []
    assert len(c.get("/api/pedidos-pestana").json()) == 1


def test_aprobar_pedido_cerrar_si_falla_despues_de_tocar_no_queda_trabado(apagada_app, enchufe):
    from orquestador.enchufe import NoDisponible

    c, app, _, _, _ = apagada_app
    _tablero_con_terminal(app)
    pid = _pedir_cierre(c, app)
    enchufe.fallas["cerrar"] = NoDisponible("herdr salió con 1")
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 502
    assert r.json()["detail"] == "no pude cerrar la terminal: descarté el pedido"
    assert c.get("/api/pedidos-pestana").json() == []


def test_aprobar_pedido_cerrar_error_inesperado_antes_de_tocar_sigue_pendiente(apagada_app, enchufe, monkeypatch):
    c, app, _, _, _ = apagada_app
    _tablero_con_terminal(app)
    pid = _pedir_cierre(c, app)

    async def roto(*a, **k):
        raise RuntimeError("raro")

    monkeypatch.setattr(app.state.tacciones.t, "snapshot", roto)
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 500 and r.json()["detail"] == "falló al cerrar la terminal"
    assert len(c.get("/api/pedidos-pestana").json()) == 1


# --- repo de Colmena y push con mensajes (auditoría A1) ---


def _colmena_falsa(tmp_path, monkeypatch):
    from orquestador import config

    raiz = tmp_path / "colmena"
    (raiz / ".git").mkdir(parents=True)
    (raiz / "backend").mkdir()
    monkeypatch.setattr(config, "REPO_ROOT", raiz)
    return raiz


@pytest.mark.parametrize("forma", ["una", "pestanas", "pestana_hija"])
def test_pedido_en_repo_colmena_descartado_con_aviso(apagada_app, tmp_path, monkeypatch, forma):
    c, app, push, sender, _ = apagada_app
    raiz = _colmena_falsa(tmp_path, monkeypatch)
    descartes = []
    app.state.pedidos_pestana.on_descarte(lambda o, m: descartes.append(m))
    if forma == "una":
        cmd = _json_cmd(carpeta=str(raiz / "backend"), mensaje="x")
    elif forma == "pestanas":
        cmd = _json_cmd(carpeta=str(raiz), pestanas=[{"nombre": "A", "tipo": "claude", "mensaje": "x"}])
    else:
        cmd = _json_cmd(carpeta="/tmp", pestanas=[{"nombre": "A", "tipo": "terminal"},
                                                  {"nombre": "B", "tipo": "claude", "mensaje": "x",
                                                   "carpeta": str(raiz)}])
    app.state.pestana_desde_bash(_msg_bash(SID, cmd), "w1:p1")
    assert c.get("/api/pedidos-pestana").json() == []
    assert not push.avisos.items and not sender.sent
    assert descartes == ["carpeta_colmena"]


def test_aviso_carpeta_colmena_tiene_texto():
    from orquestador.avisos_origen import TEXTOS

    assert TEXTOS["carpeta_colmena"] == ("Colmena no abre pedidos en su propio repo: si hace falta, "
                                         "Ando lo abre a mano desde el tablero.")


def test_abrir_pedido_en_repo_colmena_se_rechaza(apagada_app, tmp_path, monkeypatch):
    from orquestador import config

    c, app, _, _, _ = apagada_app
    raiz = tmp_path / "colmena"
    (raiz / ".git").mkdir(parents=True)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta=str(raiz), mensaje="x")), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    monkeypatch.setattr(config, "REPO_ROOT", raiz)
    abrir = AsyncMock()
    app.state.tacciones.abrir_desde_pedido_pestana = abrir
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 400
    abrir.assert_not_awaited()
    assert app.state.pedidos_pestana.get(pid)["estado"] == "rechazado"


def test_push_incluye_mensajes(apagada_app):
    c, app, push, _, _ = apagada_app
    largo = "Hacé esto " + "z" * 200
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", tarjeta="W", pestanas=[
        {"nombre": "A", "tipo": "claude", "mensaje": largo},
        {"nombre": "B", "tipo": "terminal"},
        {"nombre": "C", "tipo": "claude", "mensaje": "otro"}])), "w1:p1")
    cuerpo = [e for e in push.avisos.items if e["kind"] == "pestana"][0]["cuerpo"]
    assert "quiere abrir 3 pestañas en la tarjeta «W»" in cuerpo
    assert f" · 2 con mensaje para Claude: «{largo[:80]}…»" in cuerpo


def test_push_de_una_pestana_recorta_el_mensaje(apagada_app):
    c, app, push, _, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="m" * 300)), "w1:p1")
    cuerpo = [e for e in push.avisos.items if e["kind"] == "pestana"][0]["cuerpo"]
    assert cuerpo.endswith(f" · 1 con mensaje para Claude: «{'m' * 80}…»")


@pytest.mark.parametrize("clave", ["sesion", "pestana", "tarjeta"])
def test_pedido_cerrar_objetivo_nuevo(clave):
    cmd = _json_cmd(accion="cerrar", **{clave: " w2:t1 "})
    assert pedido_desde_comando_bash(cmd) == {"accion": "cerrar", "objetivo": clave, "sel": "w2:t1"}


def test_pedido_cerrar_objetivo_invalido_ignora():
    assert pedido_desde_comando_bash(_json_cmd(accion="cerrar", sesion="a", pestana="b")) is None
    assert pedido_desde_comando_bash(_json_cmd(accion="cerrar", terminal="a", tarjeta="b")) is None
    assert pedido_desde_comando_bash(_json_cmd(accion="cerrar", sesion="")) is None
    assert pedido_desde_comando_bash(_json_cmd(accion="cerrar", tarjeta="x" * 65)) is None
    assert pedido_desde_comando_bash(_json_cmd(accion="cerrar", pestana=3)) is None


def test_listar_expone_session_id_del_origen():
    store = PedidosPestanaStore(wall=Wall(), monotonic=Mono())
    store.crear("/tmp", "hola", None, {"pane_id": "w1:p1", "nombre": "A", "session_id": SID})
    assert store.listar_pendientes()[0]["origen"] == {"pane_id": "w1:p1", "nombre": "A", "session_id": SID}


def test_cierre_se_lista_sin_estructura_ni_huella():
    store = PedidosPestanaStore(wall=Wall(), monotonic=Mono())
    cierre = {"objetivo": "pestana", "tipo": "tab", "target_id": "w2:t1", "label": "vacío", "workspace_label": "Dos",
              "carpeta": "/tmp", "sesiones": 0, "terminales": 1, "estructura": "abc"}
    item, _ = store.crear("", "", None, {"pane_id": "w1:p1", "nombre": "A", "session_id": SID},
                          accion="cerrar", cierre=cierre)
    assert "terminal" not in item
    assert store.marcar_aviso_cierre(item["id"], "h1") is True
    fila = store.listar_pendientes()[0]
    assert fila["cierre"] == {k: v for k, v in cierre.items() if k != "estructura"}
    assert "terminal" not in fila
    assert store.get(item["id"])["cierre"]["aviso_huella"] == "h1"


def test_marcar_aviso_cierre_sin_cierre_o_resuelto_no_marca():
    store = PedidosPestanaStore(wall=Wall(), monotonic=Mono())
    item, _ = store.crear("/tmp", "hola", None, {"pane_id": "w1:p1", "nombre": "A", "session_id": SID})
    assert store.marcar_aviso_cierre(item["id"], "h1") is False


def _tablero_snapshot(app, pinned_dos=False):
    app.state.hub.board = {"workspaces": [
        {"id": "w2", "label": "Dos", "pinned": pinned_dos, "tabs": [
            {"id": "w2:t1", "label": "vacío", "agents": [], "terminales": [
                {"pane_id": "w2:p1", "terminal_id": "", "titulo": "", "cwd": "", "proceso": "", "estado": "prompt",
                 "protegida": False}]},
            {"id": "w2:t2", "label": "propio", "agents": [
                {"pane_id": "w2:p9", "session_id": "nope", "status": "unknown", "title": "Propio"}], "terminales": []}]},
        {"id": "w1", "label": "Uno", "pinned": False, "tabs": [
            {"id": "w1:t1", "label": "1", "agents": [
                {"pane_id": "w1:p1", "session_id": SID, "status": "idle", "title": "Título terminal"}],
             "terminales": []}]}]}


def test_pedido_cerrar_pestana_crea_tarjeta_y_push(apagada_app):
    c, app, _, sender, _ = apagada_app
    _tablero_snapshot(app)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", pestana="vacío")), "w1:p1")
    filas = c.get("/api/pedidos-pestana").json()
    assert len(filas) == 1 and filas[0]["accion"] == "cerrar"
    assert filas[0]["cierre"]["target_id"] == "w2:t1" and filas[0]["cierre"]["terminales"] == 1
    assert filas[0]["origen"]["session_id"] == SID
    assert app.state.pedidos_pestana.get(filas[0]["id"])["cierre"]["estructura"]
    assert sender.sent[-1]["title"] == "Pedido para cerrar una pestaña"


def test_sesion_puede_pedir_cerrarse_a_si_misma(apagada_app):
    c, app, _, _, _ = apagada_app
    _tablero_snapshot(app)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", sesion="w1:p1")), "w1:p1")
    fila = c.get("/api/pedidos-pestana").json()[0]
    assert fila["cierre"]["objetivo"] == "sesion" and fila["cierre"]["target_id"] == "w1:t1"


def test_cerrar_espacio_protegido_se_rechaza_y_avisa(protegida_app):
    from orquestador.avisos_origen import TEXTOS

    c, app, _, _, _ = protegida_app
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    _tablero_snapshot(app)  # sin pinned: lo frena el preview
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", tarjeta="Dos")), "w1:p1")
    assert c.get("/api/pedidos-pestana").json() == []
    assert app.state.mensajes.execute.await_args[0][0].texto == TEXTOS["cierre_protegido"]


def test_cerrar_tarjeta_con_el_panel_de_colmena_se_rechaza(apagada_app):
    from orquestador.avisos_origen import TEXTOS

    c, app, _, _, _ = apagada_app
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    _tablero_snapshot(app)
    app.state.hub.self_pane_id = "w2:p9"
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", tarjeta="w2")), "w1:p1")
    assert c.get("/api/pedidos-pestana").json() == []
    assert app.state.mensajes.execute.await_args[0][0].texto == TEXTOS["cierre_protegido"]


def test_pedido_cerrar_no_encontrado_avisa(apagada_app):
    from orquestador.avisos_origen import TEXTOS

    c, app, _, _, _ = apagada_app
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    _tablero_snapshot(app)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", pestana="nada")), "w1:p1")
    assert c.get("/api/pedidos-pestana").json() == []
    assert app.state.mensajes.execute.await_args[0][0].texto == TEXTOS["cierre_no_encontrado"]


def test_pedido_cerrar_sesion_sola_en_su_pestana_se_crea(apagada_app):
    c, app, _, _, _ = apagada_app
    _tablero_snapshot(app)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", sesion="w2:p9")), "w1:p1")
    filas = c.get("/api/pedidos-pestana").json()
    assert len(filas) == 1 and filas[0]["cierre"]["target_id"] == "w2:t2"


def test_pedido_cerrar_ambiguo_avisa(apagada_app):
    from orquestador.avisos_origen import TEXTOS

    c, app, _, _, _ = apagada_app
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    _tablero_snapshot(app)
    app.state.hub.board["workspaces"][0]["tabs"][1]["label"] = "vacío"
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", pestana="vacío")), "w1:p1")
    assert c.get("/api/pedidos-pestana").json() == []
    assert app.state.mensajes.execute.await_args[0][0].texto == TEXTOS["cierre_ambiguo"]


# --- aprobar un pedido de cierre (sesión, pestaña o tarjeta) ---


def _espiar_descartes(app, monkeypatch):
    """El aviso al origen espera a que la sesión esté quieta (el tablero real la deja trabajando tras el
    pedido de guardar): se comprueba el motivo con el que se descartó, que es lo que decide el texto."""
    motivos = []
    original = app.state.pedidos_pestana.descartar
    monkeypatch.setattr(app.state.pedidos_pestana, "descartar",
                        lambda origen, motivo: (motivos.append(motivo), original(origen, motivo))[1])
    return motivos


def _pedir(c, app, **destino):
    _tablero_snapshot(app)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", **destino)), "w1:p1")
    return c.get("/api/pedidos-pestana").json()[0]["id"]


def test_aprobar_cierre_sin_claude_cierra(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    pid = _pedir(c, app, pestana="w2:t1")
    r = _aprobar(c, pid)
    assert r.status_code == 200, r.text
    assert r.json()["cerrada"] is True
    assert [x[1] for x in enchufe.calls_of("cerrar")] == ["w2:t1"]
    assert app.state.guardado.cierres.state.cierres()[-1]["origen"] == "pedido-pestana"
    assert c.get("/api/pedidos-pestana").json() == []


def test_aprobar_cierre_con_claude_pide_guardar_antes(apagada_app, enchufe):
    from orquestador.guardado import MENSAJE

    c, app, _, _, _ = apagada_app
    pid = _pedir(c, app, sesion="w1:p1")
    r = _aprobar(c, pid)
    assert r.status_code == 200 and r.json()["guardando"] is True
    assert enchufe.calls_of("mandar_prompt")[-1][1:] == ("w1:p1", MENSAJE)
    assert enchufe.calls_of("cerrar") == []
    assert c.get("/api/pedidos-pestana").json() == []


def test_trabajando_pide_cerrar_igual_y_forzar_cierra(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    pid = _pedir(c, app, pestana="propio")  # w2:p9 con estado desconocido: bloqueante
    primero = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert primero.status_code == 409
    assert primero.json()["detail"] == "Está trabajando: revisalo"
    assert primero.json()["bloqueantes"] == [{"pane_id": "w2:p9", "status": "unknown"}]
    v = c.post(f"/api/pedidos-pestana/{pid}/vista-cierre").json()
    assert v["trabajando"] is True and v["estados"] == ["unknown"]
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir", json={"forzar": True, "huella": v["huella"]})
    assert r.status_code == 200 and r.json()["cerrada"] is True
    assert [x[1] for x in enchufe.calls_of("cerrar")] == ["w2:t2"]


def test_forzar_sin_haber_mostrado_el_aviso_no_cierra(apagada_app, enchufe):
    from orquestador.cierre import PreviewBody

    c, app, _, _, _ = apagada_app
    pid = _pedir(c, app, pestana="propio")
    cierres = app.state.guardado.cierres  # huella real, con un preview directo (sin pasar por vista-cierre)
    real = asyncio.run(cierres.preview(PreviewBody(tipo="tab", target_id="w2:t2")))["huella"]
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir", json={"forzar": True, "huella": real})
    assert r.status_code == 409 and enchufe.calls_of("cerrar") == []
    assert len(c.get("/api/pedidos-pestana").json()) == 1


def test_forzar_con_huella_vieja_no_cierra(apagada_app, enchufe):
    from dataclasses import replace

    c, app, _, _, _ = apagada_app
    pid = _pedir(c, app, pestana="propio")
    v = c.post(f"/api/pedidos-pestana/{pid}/vista-cierre").json()
    assert v["trabajando"] is True
    # El agente cambia de estado después de mostrar el aviso: la huella vieja ya no vale.
    sesiones = tuple(replace(s, seq=(s.seq or 0) + 1) if s.id == "w2:p9" else s
                     for s in enchufe.tablero_actual.sesiones)
    enchufe.cambiar(sesiones=sesiones)
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir", json={"forzar": True, "huella": v["huella"]})
    assert r.status_code == 409
    assert enchufe.calls_of("cerrar") == []
    assert [f["id"] for f in c.get("/api/pedidos-pestana").json()] == [pid]


def test_si_cambio_la_estructura_descarta_y_avisa(apagada_app, enchufe, monkeypatch):
    from dataclasses import replace

    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, pestana="vacío")
    base = next(s for s in enchufe.tablero_actual.sesiones if s.id == "w2:p1")
    extra = replace(base, id="w2:p7")
    lineas = tuple(replace(l, sesiones=l.sesiones + ("w2:p7",)) if l.id == "w2:t1" else l
                   for l in enchufe.tablero_actual.lineas)
    enchufe.cambiar(sesiones=enchufe.tablero_actual.sesiones + (extra,), lineas=lineas)
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 409
    assert r.json()["detail"] == "Cambió lo que había que cerrar: descarté el pedido"
    assert enchufe.calls_of("cerrar") == []
    assert c.get("/api/pedidos-pestana").json() == []
    assert motivos == ["cierre_cambio"]


def test_aprobar_dos_veces_el_mismo_cierre(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    pid = _pedir(c, app, pestana="w2:t1")
    assert _aprobar(c, pid).status_code == 200
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 409 and r.json()["detail"] == "el pedido ya no está pendiente"
    assert len(enchufe.calls_of("cerrar")) == 1


def test_lote_que_vence_se_cancela_y_avisa(apagada_app, enchufe, monkeypatch):
    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, sesion="w1:p1")
    assert _aprobar(c, pid).json()["guardando"] is True
    lote = app.state.guardado.lote(f"pc-{pid.replace('-', '')[:48]}")
    assert lote is not None and lote.cancelado is False
    app.state.guardado._vencer(lote.id)
    assert lote.cancelado is True
    assert enchufe.calls_of("cerrar") == []
    assert motivos == ["cierre_no_hecho"]


def test_close_execute_publico_sigue_rechazando_pedido_pestana(apagada_app):
    c, _, _, _, _ = apagada_app
    body = {"id": "x" * 12, "tipo": "tab", "target_id": "w2:t1", "huella": "h", "origen": "pedido-pestana"}
    assert c.post("/api/close/execute", json=body).status_code == 400


def test_vista_de_un_pedido_que_no_es_cierre_es_404(apagada_app):
    c, app, _, _, _ = apagada_app
    app.state.pedidos_pestana.crear("/tmp", "hola", None, {"pane_id": "w1:p1", "nombre": "A", "session_id": SID})
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    assert c.post(f"/api/pedidos-pestana/{pid}/vista-cierre").status_code == 404


def test_error_inesperado_al_cerrar_no_deja_el_pedido_tomado(apagada_app, enchufe, monkeypatch):
    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, pestana="w2:t1")

    async def roto(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(app.state.guardado.cierres, "execute", roto)
    assert _aprobar(c, pid).status_code == 500
    assert app.state.pedidos_pestana.get(pid)["estado"] == "rechazado"
    assert motivos == ["cierre_no_hecho"]


# --- ronda 1: riesgo al aprobar ---


def _proteger(app, nombre="Dos"):
    app.state.guardado.cierres.protected_workspaces.add(nombre.casefold())


def test_al_aprobar_se_vuelve_a_verificar_la_proteccion(apagada_app, enchufe, monkeypatch):
    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, tarjeta="Dos")
    _proteger(app)
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 400 or r.status_code == 409
    assert enchufe.calls_of("cerrar") == []
    assert motivos == ["cierre_protegido"]
    assert app.state.pedidos_pestana.get(pid)["estado"] == "rechazado"


def test_excepcion_inesperada_en_el_preview_al_aprobar(apagada_app, enchufe, monkeypatch):
    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, pestana="w2:t1")
    soltados = []
    original = app.state.pedidos_pestana.soltar_lanzamiento
    monkeypatch.setattr(app.state.pedidos_pestana, "soltar_lanzamiento",
                        lambda p, e: (soltados.append((p, e)), original(p, e))[1])

    async def roto(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(app.state.guardado.cierres, "preview", roto)
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 500
    assert soltados == [(pid, "rechazado")]
    assert app.state.pedidos_pestana.get(pid)["estado"] == "rechazado"
    assert motivos == ["cierre_no_hecho"]
    assert enchufe.calls_of("cerrar") == []


def test_vista_con_la_verificacion_fallida_descarta_el_pedido(apagada_app, enchufe, monkeypatch):
    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, tarjeta="Dos")
    _proteger(app)
    r = c.post(f"/api/pedidos-pestana/{pid}/vista-cierre")
    assert r.status_code in (400, 409)
    assert app.state.pedidos_pestana.get(pid)["estado"] == "rechazado"
    assert c.get("/api/pedidos-pestana").json() == []
    assert motivos == ["cierre_protegido"]


def test_vista_no_avisa_si_la_aprobacion_ya_tomo_el_pedido(apagada_app, enchufe, monkeypatch):
    from orquestador.traspaso import TraspasoError

    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, pestana="w2:t1")

    async def preview_cruzado(*a, **k):
        assert app.state.pedidos_pestana.tomar_para_lanzar(pid)  # la aprobación lo toma en medio de la vista
        raise TraspasoError(404, "Ya no está abierto")

    monkeypatch.setattr(app.state.guardado.cierres, "preview", preview_cruzado)
    c.post(f"/api/pedidos-pestana/{pid}/vista-cierre")
    assert motivos == []
    assert app.state.pedidos_pestana.get(pid)["estado"] == "lanzando"


def test_forzar_con_execute_que_lanza_no_deja_el_pedido_tomado(apagada_app, enchufe, monkeypatch):
    from orquestador.traspaso import TraspasoError

    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, pestana="propio")
    v = c.post(f"/api/pedidos-pestana/{pid}/vista-cierre").json()

    async def falla(*a, **k):
        raise TraspasoError(502, "Las terminales no responden")

    monkeypatch.setattr(app.state.guardado.cierres, "execute", falla)
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir", json={"forzar": True, "huella": v["huella"]})
    assert r.status_code == 502
    assert app.state.pedidos_pestana.get(pid)["estado"] == "rechazado"
    assert motivos == ["cierre_no_hecho"]


def test_cierre_que_pasa_a_protegido_entre_la_verificacion_y_el_cierre_avisa_protegido(apagada_app, enchufe, monkeypatch):
    from orquestador.traspaso import TraspasoError

    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, pestana="w2:t1")

    async def protegido(*a, **k):
        raise TraspasoError(403, "Ese workspace está protegido")

    monkeypatch.setattr(app.state.guardado, "iniciar_uno", protegido)
    assert _aprobar(c, pid).status_code == 403
    assert motivos == ["cierre_protegido"]
    assert app.state.pedidos_pestana.get(pid)["estado"] == "rechazado"


# --- arreglos de la revisión: la aprobación queda atada a lo que se mostró ---


def _aprobar(c, pid, **extra):
    v = c.post(f"/api/pedidos-pestana/{pid}/vista-cierre").json()
    return c.post(f"/api/pedidos-pestana/{pid}/abrir", json={"huella": v["huella"], **extra})


def test_aprobar_cierre_sin_haber_pedido_la_vista_no_cierra(apagada_app, enchufe, monkeypatch):
    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, pestana="w2:t1")
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 409
    assert r.json()["detail"] == "Cambió lo que había que cerrar: descarté el pedido"
    assert enchufe.calls_of("cerrar") == []
    assert app.state.pedidos_pestana.get(pid)["estado"] == "rechazado"
    assert motivos == ["cierre_cambio"]


def test_aprobar_cierre_con_huella_distinta_de_la_vista_no_cierra(apagada_app, enchufe, monkeypatch):
    from orquestador.cierre import PreviewBody

    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, pestana="w2:t1")
    c.post(f"/api/pedidos-pestana/{pid}/vista-cierre")
    # Otra huella "válida" para el objetivo (preview directo) no alcanza si no es la que devolvió la vista.
    otra = asyncio.run(app.state.guardado.cierres.preview(PreviewBody(tipo="tab", target_id="w2:t2")))["huella"]
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir", json={"huella": otra})
    assert r.status_code == 409
    assert enchufe.calls_of("cerrar") == []
    assert motivos == ["cierre_cambio"]


def test_aprobar_cierre_si_cambio_el_estado_desde_la_vista_no_cierra(apagada_app, enchufe, monkeypatch):
    from dataclasses import replace

    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    pid = _pedir(c, app, sesion="w1:p1")
    v = c.post(f"/api/pedidos-pestana/{pid}/vista-cierre").json()
    assert v["trabajando"] is False
    sesiones = tuple(replace(s, seq=(s.seq or 0) + 1) if s.id == "w1:p1" else s
                     for s in enchufe.tablero_actual.sesiones)
    enchufe.cambiar(sesiones=sesiones)
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir", json={"huella": v["huella"]})
    assert r.status_code == 409
    assert enchufe.calls_of("mandar_prompt") == [] and enchufe.calls_of("cerrar") == []
    assert motivos == ["cierre_cambio"]


def test_aprobar_cierre_con_la_huella_de_la_vista_cierra(apagada_app, enchufe):
    c, app, _, _, _ = apagada_app
    pid = _pedir(c, app, pestana="w2:t1")
    r = _aprobar(c, pid)
    assert r.status_code == 200, r.text
    assert [x[1] for x in enchufe.calls_of("cerrar")] == ["w2:t1"]


def test_cooldown_antes_de_resolver_el_objetivo(apagada_app, monkeypatch):
    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    _tablero_snapshot(app)
    llamados = []
    original = app.state.guardado.cierres.preview

    async def espia(body):
        llamados.append(body.target_id)
        return await original(body)

    monkeypatch.setattr(app.state.guardado.cierres, "preview", espia)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", pestana="nada")), "w1:p1")
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", pestana="vacío")), "w1:p1")
    assert motivos == ["cierre_no_encontrado", "cooldown"]
    assert llamados == []
    assert c.get("/api/pedidos-pestana").json() == []


def test_cooldown_frena_el_preview_de_un_segundo_pedido(apagada_app, monkeypatch):
    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    _tablero_snapshot(app)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", pestana="vacío")), "w1:p1")
    llamados = []

    async def espia(body):
        llamados.append(body.target_id)
        raise AssertionError("no debería armar el preview")

    monkeypatch.setattr(app.state.guardado.cierres, "preview", espia)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", pestana="propio")), "w1:p1")
    assert motivos == ["cooldown"]
    assert llamados == []
    assert len(c.get("/api/pedidos-pestana").json()) == 1


def test_excepcion_inesperada_en_el_preview_al_crear_avisa(apagada_app, monkeypatch):
    c, app, _, _, _ = apagada_app
    motivos = _espiar_descartes(app, monkeypatch)
    _tablero_snapshot(app)

    async def roto(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(app.state.guardado.cierres, "preview", roto)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cerrar", pestana="vacío")), "w1:p1")
    assert motivos == ["cierre_no_posible"]
    assert c.get("/api/pedidos-pestana").json() == []
