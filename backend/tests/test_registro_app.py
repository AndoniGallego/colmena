import json
import os
import pwd
from datetime import date
from pathlib import Path

import pytest
from conftest import ORIGIN

from orquestador.registro_app import LINEA_MAX, RegistroApp, carpeta_registro_app, limpiar_linea

L = "2026-11-23T14:05:09.123 error nudo no arrancó UIA"


@pytest.fixture
def carpeta_reg():
    return carpeta_registro_app(os.environ)


def test_post_guarda_y_responde_conteos(authed, carpeta_reg):
    r = authed.post("/api/registro/app", json={"lineas": [L, "basura"]}, headers=ORIGIN)
    assert r.status_code == 200 and r.json() == {"ok": True, "guardadas": 1, "descartadas": 1}
    (f,) = carpeta_reg.glob("*.log")
    assert f.read_text() == L + "\n"
    assert f.stat().st_mode & 0o777 == 0o600 and carpeta_reg.stat().st_mode & 0o777 == 0o700


def test_sin_sesion_401(client):
    assert client.post("/api/registro/app", json={"lineas": [L]}, headers=ORIGIN).status_code == 401


@pytest.mark.parametrize("body", [{"lineas": []}, {"lineas": [L] * 201}, {"lineas": [L], "x": 1},
                                  {"lineas": ["a" * 2001]}, {"lineas": "L"}])
def test_body_invalido_422(authed, carpeta_reg, body):
    assert authed.post("/api/registro/app", json=body, headers=ORIGIN).status_code == 422
    assert not carpeta_reg.exists()


def test_limpiar_linea_saca_control_y_valida():
    assert limpiar_linea(L.replace("UIA", "UIA\n2026-01-01T00:00:00.000 info app falsa")) == L.replace(
        "UIA", "UIA 2026-01-01T00:00:00.000 info app falsa")
    assert limpiar_linea("2026-11-23T14:05:09.123 debug app x") is None
    assert len(limpiar_linea(L + "x" * 900)) == LINEA_MAX


def test_borra_archivos_de_mas_de_7_dias(tmp_path):
    reg = RegistroApp(tmp_path, hoy=lambda: date(2026, 11, 23))
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "2026-11-15.log").write_text("x")
    (tmp_path / "2026-11-16.log").write_text("x")
    (tmp_path / "notas.txt").write_text("x")
    reg.agregar([L])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-11-16.log", "2026-11-23.log", "notas.txt"]


def test_carpeta_respeta_xdg_y_home():
    assert carpeta_registro_app({"XDG_DATA_HOME": "/x", "HOME": "/h"}) == Path("/x/orquestador/registro-app")
    assert carpeta_registro_app({"XDG_DATA_HOME": "", "HOME": "/h"}) == Path("/h/.local/share/orquestador/registro-app")


def test_tests_no_tocan_el_home_real():
    assert not str(carpeta_registro_app(os.environ)).startswith(str(Path(pwd.getpwuid(os.getuid()).pw_dir)))


EV = {"ts": "2026-11-25T10:00:00-03:00", "origen": "tuneles", "evento": "tunel_fallo", "ok": False,
      "codigo": "ssh_rechazado", "ms": 1200}


def lineas_tel(app):
    d = app.state.telemetria.directorio
    return [json.loads(l) for f in sorted(d.glob("*.jsonl")) for l in f.read_text().splitlines()]


def test_eventos_validos_van_a_telemetria(authed, app):
    r = authed.post("/api/registro/app", json={"eventos": [EV]}, headers=ORIGIN)
    assert r.status_code == 200 and r.json() == {"ok": True, "guardadas": 0, "descartadas": 0, "eventos": 1}
    (l,) = lineas_tel(app)
    assert l["fuente"] == "windows" and l["ts"] == EV["ts"] and l["ev"] == "app"
    assert l["evento"] == "tunel_fallo" and l["codigo"] == "ssh_rechazado" and l["ok"] is False and l["ms"] == 1200


def test_lineas_y_eventos_en_el_mismo_lote(authed, app, carpeta_reg):
    r = authed.post("/api/registro/app", json={"lineas": [L], "eventos": [EV]}, headers=ORIGIN)
    assert r.json() == {"ok": True, "guardadas": 1, "descartadas": 0, "eventos": 1}
    assert len(lineas_tel(app)) == 1 and next(carpeta_reg.glob("*.log")).read_text() == L + "\n"


def test_evento_con_texto_libre_pasa_a_otro(authed, app):
    ev = {**EV, "evento": "C:\\Users\\ana", "codigo": "/home/ana/x"}
    assert authed.post("/api/registro/app", json={"eventos": [ev]}, headers=ORIGIN).json()["eventos"] == 1
    (l,) = lineas_tel(app)
    assert l["evento"] == "otro" and l["codigo"] == "otro"
    assert "ana" not in json.dumps(l)


@pytest.mark.parametrize("body", [
    {"eventos": [{**EV, "x": 1}]},
    {"lineas": [L] * 100, "eventos": [EV] * 101},
    {},
    {"eventos": []},
    {"eventos": [{**EV, "ms": -1}]},
    {"eventos": [{**EV, "evento": "a" * 41}]},
])
def test_eventos_invalidos_422(authed, app, body):
    assert authed.post("/api/registro/app", json=body, headers=ORIGIN).status_code == 422
    assert lineas_tel(app) == []


def test_solo_lineas_sigue_igual(authed, app):
    r = authed.post("/api/registro/app", json={"lineas": [L]}, headers=ORIGIN)
    assert r.json() == {"ok": True, "guardadas": 1, "descartadas": 0}
    assert lineas_tel(app) == []
