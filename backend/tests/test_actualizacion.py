import json

import pytest
from fastapi.testclient import TestClient

from orquestador.actualizacion import leer_ultima

FICHA = {"version": "0.20261125.1430", "notas": "Entrega del 25/11", "fecha": "2026-11-25T14:30:00-03:00",
         "archivo": "Colmena_0.20261125.1430_x64-setup.exe", "firma": "dW50cnVzdGVk"}


def escribir(tmp_path, ficha=FICHA, exe=b"MZ-instalador"):
    d = tmp_path / "actualizaciones"
    d.mkdir(exist_ok=True)
    (d / "ultima.json").write_text(json.dumps(ficha) if isinstance(ficha, dict) else ficha)
    if exe is not None and isinstance(ficha, dict) and isinstance(ficha.get("archivo"), str):
        try:
            (d / ficha["archivo"]).write_bytes(exe)
        except OSError:
            pass
    return d


def test_sin_ficha_204_sin_sesion(client):
    r = client.get("/api/app/actualizacion")
    assert r.status_code == 204 and r.content == b""


def test_manifiesto_tauri_sin_sesion(client, tmp_path):
    escribir(tmp_path)
    r = client.get("/api/app/actualizacion")
    assert r.status_code == 200
    assert r.json() == {
        "version": "0.20261125.1430",
        "notes": "Entrega del 25/11",
        "pub_date": "2026-11-25T14:30:00-03:00",
        "platforms": {"windows-x86_64": {
            "signature": "dW50cnVzdGVk",
            "url": "https://testserver/api/app/actualizacion/instalador",
        }},
    }


def test_instalador_sin_sesion(client, tmp_path):
    escribir(tmp_path)
    r = client.get("/api/app/actualizacion/instalador")
    assert r.status_code == 200
    assert r.content == b"MZ-instalador"
    assert r.headers["content-type"] == "application/octet-stream"


def test_instalador_sin_ficha_404(client):
    assert client.get("/api/app/actualizacion/instalador").status_code == 404


def test_instalador_ficha_sin_archivo_404(client, tmp_path):
    escribir(tmp_path, exe=None)
    assert client.get("/api/app/actualizacion/instalador").status_code == 404


@pytest.mark.parametrize("archivo", ["../config.toml", "sub/x.exe", "sub\\x.exe", "..", ".", "", "a..b/c"])
def test_nombre_invalido_no_se_sirve(client, tmp_path, archivo):
    d = escribir(tmp_path, {**FICHA, "archivo": archivo}, exe=None)
    (tmp_path / "config.toml").write_text("secreto")
    assert client.get("/api/app/actualizacion").status_code == 204
    assert client.get("/api/app/actualizacion/instalador").status_code == 404
    assert d.exists()


@pytest.mark.parametrize("ficha", ["{roto", "[]", json.dumps({**FICHA, "firma": ""}),
                                   json.dumps({k: v for k, v in FICHA.items() if k != "version"}),
                                   json.dumps({**FICHA, "version": 7})])
def test_ficha_invalida_204(client, tmp_path, ficha):
    escribir(tmp_path, ficha)
    assert client.get("/api/app/actualizacion").status_code == 204
    assert client.get("/api/app/actualizacion/instalador").status_code == 404


def test_rutas_vecinas_siguen_con_sesion(client, tmp_path):
    escribir(tmp_path)
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/app/actualizacion").status_code in (401, 404, 405)
    assert client.get("/api/app/actualizacion/otra").status_code == 404
    assert client.get("/api/app/actualizacion/instalador/x").status_code == 404


def test_url_desde_app_origin(cfg, app, tmp_path):
    cfg.app_origin = "https://maquina.red.ts.net:8444"
    escribir(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8774", client=("127.0.0.1", 5000)) as c:
        r = c.get("/api/app/actualizacion")
    assert r.json()["platforms"]["windows-x86_64"]["url"] == (
        "https://maquina.red.ts.net:8444/api/app/actualizacion/instalador")


def test_leer_ultima_valida(tmp_path):
    d = escribir(tmp_path)
    assert leer_ultima(d) == FICHA
    assert leer_ultima(tmp_path / "no-existe") is None
