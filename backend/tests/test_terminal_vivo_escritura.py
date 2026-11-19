import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from orquestador import auth, terminal_vivo
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.config import Config, hash_pin
from orquestador.digest import DigestService
from orquestador.enchufe.guardian import FotoVivo
from orquestador.state import StateStore
from tests.conftest import PIN
from tests.test_terminal_vivo import ORIGIN, ORIGIN_HDR, SID, CanalFalso, _ws

XFF = "x-forwarded-for"


@pytest.fixture
def cfg_vivo(tmp_path, projects):
    c = Config(pin=hash_pin(PIN), claude_projects_dir=str(projects), claude_cwd=str(tmp_path))
    c.app_origin = ORIGIN
    c.terminales = {"vivo": True}
    c.terminales_escritura = True
    return c


@pytest.fixture
def app_vivo(cfg_vivo, tmp_path, handoffs, enchufe):
    digests = DigestService(cfg_vivo.projects_dir())
    hub = BoardHub(enchufe, digests)
    hub.self_pane_id = "w2:p9"
    app = create_app(
        cfg_vivo,
        b"secret",
        StateStore(tmp_path),
        hub=hub,
        digests=digests,
        dist=tmp_path / "nodist",
        handoffs_dir=handoffs,
        uploads_dir=tmp_path / "uploads",
        enchufe=enchufe,
    )
    return app


@pytest.fixture
def client_vivo(app_vivo):
    with TestClient(app_vivo, base_url=ORIGIN, headers=ORIGIN_HDR, client=("127.0.0.1", 5000)) as c:
        yield c


@pytest.fixture
def authed_vivo(client_vivo):
    assert client_vivo.post("/api/login", json={"pin": PIN}).status_code == 200
    return client_vivo


@pytest.fixture
def registro(enchufe):
    out = {"escribir": [], "teclas": []}

    async def escribir(sid, texto):
        out["escribir"].append((sid, texto))

    async def teclas(sid, keys):
        out["teclas"].append((sid, tuple(keys)))

    enchufe.escribir = escribir
    enchufe.teclas = teclas
    return out


def _abrir_canal(app):
    async def abrir(_sid):
        return CanalFalso()

    app.state.abrir_vivo = abrir


def _token(client):
    r = client.post("/api/terminales/ventana", json={"pin": PIN})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_mapear_teclas():
    assert terminal_vivo.mapear_tecla_vivo("ctrl-c") == ("teclas", ("ctrl-c",))
    assert terminal_vivo.mapear_tecla_vivo("arriba") == ("teclas", ("arriba",))
    assert terminal_vivo.mapear_tecla_vivo("tab") == ("escribir", "\t")
    assert terminal_vivo.mapear_tecla_vivo("abajo") == ("escribir", "\x1b[B")
    assert terminal_vivo.mapear_tecla_vivo("izquierda") == ("escribir", "\x1b[D")
    assert terminal_vivo.mapear_tecla_vivo("bogus") is None


def test_sin_token_error_y_sigue(authed_vivo, app_vivo, registro):
    _abrir_canal(app_vivo)
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"tipo": "entrada", "token": "", "texto": "hola"}))
        err = ws.receive_json()
        assert err == {"tipo": "error_escritura", "codigo": "ventana", "mensaje": "La ventana de escritura no es válida."}
        ws.send_text(json.dumps({"tipo": "entrada", "token": "x", "texto": "nope"}))
        err2 = ws.receive_json()
        assert err2["codigo"] == "ventana"
    assert registro["escribir"] == []


def test_escritura_apagada(authed_vivo, app_vivo, registro, cfg_vivo, tmp_path, handoffs, enchufe):
    cfg_vivo.terminales_escritura = False
    digests = DigestService(cfg_vivo.projects_dir())
    app = create_app(
        cfg_vivo,
        b"secret",
        StateStore(tmp_path),
        hub=BoardHub(enchufe, digests),
        digests=digests,
        dist=tmp_path / "nodist",
        handoffs_dir=handoffs,
        uploads_dir=tmp_path / "uploads",
        enchufe=enchufe,
    )
    _abrir_canal(app)
    with TestClient(app, base_url=ORIGIN, headers=ORIGIN_HDR, client=("127.0.0.1", 5000)) as c:
        c.post("/api/login", json={"pin": PIN})
        with _ws(c, f"/api/terminal/{SID}/vivo") as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"tipo": "entrada", "token": "cualquiera", "texto": "x"}))
            err = ws.receive_json()
            assert err["codigo"] == "apagado"
    assert registro["escribir"] == []


def test_token_valido_escribe(authed_vivo, app_vivo, registro):
    _abrir_canal(app_vivo)
    tok = _token(authed_vivo)
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"tipo": "entrada", "token": tok, "texto": "hola\r"}))
    assert registro["escribir"] == [(SID, "hola\r")]


def test_teclas_especiales(authed_vivo, app_vivo, registro):
    _abrir_canal(app_vivo)
    tok = _token(authed_vivo)
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"tipo": "tecla", "token": tok, "tecla": "ctrl-c"}))
        ws.send_text(json.dumps({"tipo": "tecla", "token": tok, "tecla": "arriba"}))
        ws.send_text(json.dumps({"tipo": "tecla", "token": tok, "tecla": "zzz"}))
    assert registro["teclas"] == [(SID, ("ctrl-c",)), (SID, ("arriba",))]
    assert registro["escribir"] == []


def test_texto_largo_no_escribe(authed_vivo, app_vivo, registro):
    _abrir_canal(app_vivo)
    tok = _token(authed_vivo)
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"tipo": "entrada", "token": tok, "texto": "a" * 4097}))
    assert registro["escribir"] == []


def test_auditoria_sin_texto(authed_vivo, app_vivo, registro):
    _abrir_canal(app_vivo)
    tok = _token(authed_vivo)
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"tipo": "entrada", "token": tok, "texto": "secreto"}))
    assert registro["escribir"]
    entradas = authed_vivo.get("/api/terminales/auditoria").json()["entradas"]
    blob = json.dumps(entradas)
    assert "secreto" not in blob
    assert any(e.get("accion") == "vivo_escritura" and e.get("caracteres") == 7 for e in entradas)


def test_ventana_vencida(authed_vivo, app_vivo, registro, monkeypatch):
    _abrir_canal(app_vivo)
    tok = _token(authed_vivo)
    v = authed_vivo.app.state.tacciones.ventana
    real = v.clock

    t = [real()]

    def clock():
        return t[0]

    v.clock = clock
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        t[0] += 3600
        ws.send_text(json.dumps({"tipo": "entrada", "token": tok, "texto": "x"}))
        err = ws.receive_json()
        assert err["codigo"] == "ventana"
    v.clock = real
    assert registro["escribir"] == []


def test_sin_campo_token_avisa(authed_vivo, app_vivo, registro):
    _abrir_canal(app_vivo)
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"tipo": "tecla", "tecla": "enter"}))
        err = ws.receive_json()
        assert err["tipo"] == "error_escritura" and err["codigo"] == "ventana"
    assert registro["teclas"] == []


def test_tipear_rapido_no_corta_el_visor(authed_vivo, app_vivo, registro):
    _abrir_canal(app_vivo)
    tok = _token(authed_vivo)
    with _ws(authed_vivo, f"/api/terminal/{SID}/vivo") as ws:
        ws.receive_json()
        for _ in range(120):
            ws.send_text(json.dumps({"tipo": "entrada", "token": tok, "texto": "a"}))
        ws.send_text(json.dumps({"tipo": "entrada", "token": "", "texto": "b"}))
        assert ws.receive_json()["tipo"] == "error_escritura"
    assert len(registro["escribir"]) == 120
