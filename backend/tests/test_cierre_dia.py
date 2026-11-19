import asyncio
import json
import os
import subprocess
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, make_snapshot
from orquestador.app import create_app
from orquestador import cierre_dia
from orquestador.board import BoardHub
from orquestador.cierre_dia import (
    CierreDiaAviso,
    contenido_cierre_dia,
    frase_resumen_cierre,
    ramas_sin_integrar,
    terminado_hoy,
    te_esperan,
)
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.agenda import seconds_until_next
from orquestador.push import PushService
from orquestador.state import StateStore
from test_limpieza import agent, ago, tab, ws
from test_push import APPLE, KEYS, Recorder, subscribe_body

TZ = timezone.utc


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


class Reloj:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def board_agents(**kw):
    a1 = agent(1, **kw)
    a2 = agent(2, status="blocked", **kw)
    return {
        "workspaces": [
            ws("w1", "Acmekit", [tab("w1:t1", [a1], label="checkout"), tab("w1:t2", [a2], label="otro")]),
        ],
        "centinela": {"session_id": "cent-1", "pane_id": "c:p1", "status": "idle"},
    }


def msg_reporte(filas, ts="2026-11-04T20:00:00+00:00"):
    return {"id": "r1", "role": "reporte", "ts": ts, "items": filas, "mas": 0}


def fila(sid, nombre, quedo="listo", fin="2026-11-04T18:00:00+00:00"):
    return {
        "session_id": sid,
        "pane_id": "w1:p1",
        "nombre": nombre,
        "donde": "Acmekit / checkout",
        "pedido": "",
        "quedo": quedo,
        "pregunta": False,
        "cadena": False,
        "plan_id": "",
        "fin": fin,
    }


def test_terminado_hoy_dedupe_y_solo_hoy():
    now = at(4, 18)
    msgs = [
        msg_reporte([fila("s1", "Acmekit · checkout"), fila("s1", "Acmekit · checkout", quedo="otro")]),
        msg_reporte([fila("s2", "Tienda · home", fin="2026-11-03T18:00:00+00:00")], ts="2026-11-03T20:00:00+00:00"),
    ]
    out = terminado_hoy(msgs, now)
    assert len(out) == 1
    assert out[0]["session_id"] == "s1"
    assert "g16" not in out[0]["nombre"]


def test_te_esperan_blocked_asks_unread():
    b = board_agents(unread=True)
    b["workspaces"][0]["tabs"][0]["agents"][0]["status"] = "idle"
    b["workspaces"][0]["tabs"][0]["agents"][0]["asks_user"] = True
    b["workspaces"][0]["tabs"][1]["agents"][0]["unread"] = True
    out = te_esperan(b)
    sids = {x["session_id"] for x in out}
    assert len(out) == 2
    assert all("g16" not in x["nombre"] and ":p" not in x["nombre"] for x in out)


def test_te_esperan_con_board_viejo_incluye_a_la_sesion_que_era_centinela():
    b = board_agents(unread=True)
    sid = b["workspaces"][0]["tabs"][1]["agents"][0]["session_id"]
    b["centinela"] = {"session_id": sid, "pane_id": "c:p1", "status": "idle"}
    assert sid in {x["session_id"] for x in te_esperan(b)}


def test_contenido_vacio_devuelve_none():
    now = at(4, 18)
    assert contenido_cierre_dia({}, [], now, ramas=[]) is None


def test_contenido_y_frase():
    now = at(4, 18)
    msgs = [msg_reporte([fila("s1", "Acmekit · checkout")])]
    esperan = [{"session_id": "s2", "nombre": "Tienda · home", "motivo": "blocked"}]
    ramas = [{"repo": "orquestador", "rama": "feature/x", "commits": 3, "base": "origin/main"}]
    c = contenido_cierre_dia(board_agents(), msgs, now, esperan=esperan, ramas=ramas)
    assert c["fecha"] == "2026-11-04"
    assert frase_resumen_cierre(c) == "Terminó 1 · te espera 1 · 1 rama sin integrar"


def test_frase_plural():
    c = {
        "termino": [{}, {}],
        "esperan": [{}, {}],
        "ramas": [{}, {}, {}],
    }
    assert frase_resumen_cierre(c) == "Terminaron 2 · te esperan 2 · 3 ramas sin integrar"


def test_cierre_aviso_horario_y_catchup(tmp_path):
    enviados = []

    async def ejecutar():
        enviados.append(1)

    reloj = Reloj(at(4, 17, 29))
    aviso = CierreDiaAviso(tmp_path, lambda: "17:30", lambda: [0, 1, 2, 3, 4], ejecutar, now=reloj)
    assert asyncio.run(aviso.tick()) is False
    reloj.now = at(4, 17, 30)
    assert asyncio.run(aviso.tick()) is True
    assert asyncio.run(aviso.tick()) is False
    assert json.loads((tmp_path / "cierre-dia.json").read_text()) == {"ultimo": "2026-11-04"}


def test_cierre_no_corre_fin_de_semana(tmp_path):
    enviados = []

    async def ejecutar():
        enviados.append(1)

    aviso = CierreDiaAviso(tmp_path, lambda: "17:30", lambda: [0, 1, 2, 3, 4], ejecutar, now=Reloj(at(1, 18)))
    assert asyncio.run(aviso.tick()) is False
    assert enviados == []


def test_run_sigue_tras_fallo_en_seconds_until_next(tmp_path, caplog):
    import logging
    from unittest.mock import patch

    caplog.set_level(logging.ERROR, logger="orquestador.cierre_dia")
    enviados = []

    async def ejecutar():
        enviados.append(1)

    aviso = CierreDiaAviso(tmp_path, lambda: "17:30", lambda: [0, 1, 2, 3, 4], ejecutar, now=Reloj(at(4, 17, 0)))
    esperas = []
    llamadas = {"n": 0}

    def seconds_patch(*args, **kwargs):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise RuntimeError("seconds-roto")
        return seconds_until_next(*args, **kwargs)

    async def sleep(seconds):
        esperas.append(seconds)
        raise asyncio.CancelledError

    aviso._sleep = sleep
    with patch("orquestador.cierre_dia.seconds_until_next", side_effect=seconds_patch):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(aviso.run())
    assert esperas[0] == 600


def test_run_sigue_tras_error_en_tick(tmp_path, caplog):
    import logging

    caplog.set_level(logging.ERROR, logger="orquestador.cierre_dia")
    enviados = []

    async def ejecutar():
        enviados.append(1)

    aviso = CierreDiaAviso(tmp_path, lambda: "17:30", lambda: [0, 1, 2, 3, 4], ejecutar, now=Reloj(at(4, 17, 30)))
    llamadas = {"tick": 0}
    real_tick = aviso.tick

    async def tick_patched():
        llamadas["tick"] += 1
        if llamadas["tick"] == 1:
            raise RuntimeError("tick-roto")
        return await real_tick()

    aviso.tick = tick_patched
    esperas = []

    async def sleep(seconds):
        esperas.append(seconds)
        if len(esperas) >= 3:
            raise asyncio.CancelledError

    aviso._sleep = sleep
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(aviso.run())
    assert llamadas["tick"] >= 2
    assert any("el aviso de cierre del día falló" in r.message for r in caplog.records)
    assert len(enviados) >= 1
    assert esperas[0] <= 600


def test_cierre_catchup_tras_reinicio(tmp_path):
    enviados = []

    async def ejecutar():
        enviados.append(1)

    aviso = CierreDiaAviso(tmp_path, lambda: "17:30", lambda: [0, 1, 2, 3, 4], ejecutar, now=Reloj(at(4, 20)))
    assert asyncio.run(aviso.tick()) is True
    otro = CierreDiaAviso(tmp_path, lambda: "17:30", lambda: [0, 1, 2, 3, 4], ejecutar, now=Reloj(at(4, 21)))
    assert asyncio.run(otro.tick()) is False
    assert len(enviados) == 1


def test_seconds_until_cierre_lun_vie():
    lun = [0, 1, 2, 3, 4]
    assert seconds_until_next((17, 30), lun, at(4, 17, 0)) == 30 * 60


def git(cwd, *args):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    (path / "a").write_text("1")
    git(path, "add", "a")
    git(path, "commit", "-qm", "uno")
    git(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return path


def run(coro):
    return asyncio.run(coro)


def test_ramas_sin_integrar_feature(tmp_path, repo):
    git(repo, "checkout", "-qb", "feature/x")
    (repo / "b").write_text("2")
    git(repo, "add", "b")
    git(repo, "commit", "-qm", "dos")
    git(repo, "commit", "-qm", "tres", "--allow-empty")
    now = at(4, 18)
    board = board_agents(cwd=str(repo))
    msgs = [msg_reporte([fila("aaaaaaaa-2222-3333-4444-555555555501", "Acmekit · checkout")])]
    out = run(ramas_sin_integrar(board, msgs, now))
    assert len(out) == 1
    assert out[0]["rama"] == "feature/x" and out[0]["commits"] == 2


def test_rama_mergeada_no_cuenta(tmp_path, repo):
    git(repo, "checkout", "-qb", "feature/x")
    (repo / "b").write_text("2")
    git(repo, "add", "b")
    git(repo, "commit", "-qm", "dos")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "m", "feature/x")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "checkout", "-q", "feature/x")
    now = at(4, 18)
    board = board_agents(cwd=str(repo))
    msgs = [msg_reporte([fila("aaaaaaaa-2222-3333-4444-555555555501", "x")])]
    assert run(ramas_sin_integrar(board, msgs, now)) == []


def test_repo_sin_remoto_usa_main_local(tmp_path, repo):
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    git(repo, "checkout", "-qb", "feature/y")
    git(repo, "commit", "-qm", "dos", "--allow-empty")
    now = at(4, 18)
    board = board_agents(cwd=str(repo))
    msgs = [msg_reporte([fila("aaaaaaaa-2222-3333-4444-555555555501", "x")])]
    out = run(ramas_sin_integrar(board, msgs, now))
    assert [(r["rama"], r["commits"], r["base"]) for r in out] == [("feature/y", 1, "main")]


def test_repo_sin_remoto_rama_mergeada_no_cuenta(tmp_path, repo):
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    git(repo, "checkout", "-qb", "feature/y")
    git(repo, "commit", "-qm", "dos", "--allow-empty")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "m", "feature/y")
    git(repo, "checkout", "-q", "feature/y")
    now = at(4, 18)
    board = board_agents(cwd=str(repo))
    msgs = [msg_reporte([fila("aaaaaaaa-2222-3333-4444-555555555501", "x")])]
    assert run(ramas_sin_integrar(board, msgs, now)) == []


def test_rama_base_no_cuenta(tmp_path, repo):
    now = at(4, 18)
    board = board_agents(cwd=str(repo))
    msgs = [msg_reporte([fila("aaaaaaaa-2222-3333-4444-555555555501", "x")])]
    assert run(ramas_sin_integrar(board, msgs, now)) == []


def test_dispatch_cierre_prefs(tmp_path):
    sender = Recorder()
    svc = PushService(tmp_path, sender=sender)
    svc.store.upsert({"endpoint": APPLE, "keys": dict(KEYS), "device": "a", "prefs": {"cierre": True}})
    svc.store.upsert({"endpoint": "https://fcm.googleapis.com/x", "keys": dict(KEYS), "device": "b", "prefs": {"cierre": False}})
    body = "Terminó 1 · te espera 1 · 1 rama sin integrar"
    assert asyncio.run(svc.dispatch_cierre(body, endpoint=APPLE)) == 1
    msg = sender.sent[0][1]
    assert msg == {
        "title": "Cierre del día",
        "body": body,
        "session_id": "",
        "kind": "cierre",
        "tag": "cierre",
    }


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


@pytest.fixture
def hclient(cfg, tmp_path, handoffs, enchufe):
    sender = Recorder()
    digests = DigestService(cfg.projects_dir())
    svc = PushService(tmp_path, sender=sender)
    app = create_app(
        cfg,
        b"secret",
        StateStore(tmp_path),
        hub=BoardHub(enchufe, digests),
        digests=digests,
        dist=tmp_path / "nodist",
        handoffs_dir=handoffs,
        push=svc,
        enchufe=enchufe,
    )
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c, sender, svc, app


def test_endpoint_cierre_test_no_marca_hecho(hclient, tmp_path, monkeypatch):
    c, sender, svc, app = hclient
    # El tablero falso carga en segundo plano; sin esto el "nada para cerrar" depende de si ya llegó.
    monkeypatch.setattr(cierre_dia, "te_esperan", lambda board: [])
    assert c.post("/api/push/cierre/test", json={"endpoint": APPLE}).status_code == 404
    c.post("/api/push/subscribe", json=subscribe_body())
    assert c.post("/api/push/cierre/test", json={}).status_code == 422
    assert c.post("/api/push/cierre/test", json={"endpoint": APPLE}).status_code == 422
    hoy = date.today().isoformat()
    app.state.state.data.setdefault("messages", []).append(
        msg_reporte([fila("s-test-001", "Acmekit · checkout", fin=f"{hoy}T18:00:00+00:00")])
    )
    assert c.post("/api/push/cierre/test", json={"endpoint": APPLE}).json() == {"ok": True}
    assert sender.sent[-1][1]["kind"] == "cierre"
    assert not (tmp_path / "cierre-dia.json").exists()
