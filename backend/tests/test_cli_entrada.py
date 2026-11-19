import asyncio
import os
import sys

import pytest
from starlette.applications import Starlette

from asgi_support import correr
from orquestador import cli
from orquestador.config import Config, hash_pin, save_config

PROD = dict(app_origin="https://app.example:8444", viewer_origin="https://app.example:8445")


def test_servidores_por_defecto_igual_que_hoy():
    s = cli.servidores(Starlette(), Starlette(), Config(**PROD))
    assert [(x.config.host, x.config.port) for x in s] == [("127.0.0.1", 8770), ("127.0.0.1", 8771)]
    assert [x.config.lifespan for x in s] == ["on", "off"]


def test_solo_local_suma_listener_8774():
    s = cli.servidores(Starlette(), Starlette(), Config(**PROD, entrada={"modos": ["tailscale", "solo-local"]}))
    assert [x.config.port for x in s] == [8770, 8771, 8774]
    assert all(x.config.host == "127.0.0.1" for x in s)


def test_cada_servidor_trae_su_pila():
    s = cli.servidores(Starlette(), Starlette(), Config(**PROD, entrada={"modos": ["tailscale", "solo-local"]}))
    assert correr(lambda _: s[2].config.app, headers=[("host", "app.example")]).status == 400
    assert correr(lambda _: s[0].config.app, headers=[("host", "evil.example")]).status == 400


def test_serve_sin_app_origin_en_tailscale_devuelve_1(tmp_path, monkeypatch, capsys):
    d = tmp_path / "d"
    d.mkdir()
    save_config(Config(pin=hash_pin("unpinlargo"), app_origin=""), d)
    monkeypatch.setenv("ORQ_DATA_DIR", str(d))
    monkeypatch.delenv("ORQ_APP_ORIGIN", raising=False)
    old = os.umask(0o022)
    try:
        assert cli.serve() == 1
    finally:
        os.umask(old)
    assert "app_origin" in capsys.readouterr().err.lower()


def test_serve_con_modo_invalido_devuelve_1(tmp_path, monkeypatch, capsys):
    d = tmp_path / "d"
    d.mkdir()
    save_config(Config(pin=hash_pin("unpinlargo"), entrada={"modos": ["nada"]}), d)
    monkeypatch.setenv("ORQ_DATA_DIR", str(d))
    old = os.umask(0o022)
    try:
        assert cli.serve() == 1
    finally:
        os.umask(old)
    assert "entrada" in capsys.readouterr().err.lower()


def test_uvicorn_no_reescribe_cliente_desde_x_forwarded_for():
    vistos: list = []

    async def inner(scope, receive, send):
        vistos.append(scope.get("client"))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    cfg = Config(
        **PROD,
        tailscale_user="yo@example.com",
        entrada={"modos": ["tailscale", "solo-local"]},
    )
    casos = [
        (0, [("host", "app.example"), ("x-forwarded-for", "100.64.0.9"), ("tailscale-user-login", "yo@example.com")]),
        (1, [("host", "app.example"), ("x-forwarded-for", "100.64.0.9"), ("tailscale-user-login", "yo@example.com")]),
        (2, [("host", "localhost:8774"), ("x-forwarded-for", "100.64.0.9")]),
    ]
    servers = cli.servidores(inner, inner, cfg)
    assert len(servers) == 3
    for idx, headers in casos:
        vistos.clear()
        srv = servers[idx]
        srv.config.load()
        correr(lambda _: srv.config.loaded_app, headers=headers, client=("127.0.0.1", 5000), path="/")
        assert vistos, idx
        assert vistos[-1] == ("127.0.0.1", 5000), idx


def test_lifespan_llega_a_app_a_traves_de_pila():
    tipos: list[str] = []

    async def inner(scope, receive, send):
        tipos.append(scope["type"])
        if scope["type"] != "lifespan":
            return
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    s = cli.servidores(inner, None, Config(**PROD))
    app = s[0].config.app
    paso = 0

    async def receive():
        nonlocal paso
        paso += 1
        return {"type": "lifespan.startup" if paso == 1 else "lifespan.shutdown"}

    async def send(_message):
        pass

    scope = {"type": "lifespan", "asgi": {"spec_version": "2.3", "version": "3.0"}}
    asyncio.run(app(scope, receive, send))
    assert "lifespan" in tipos


def test_main_exportar_pasa_destino_posicional(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    llamadas: list = []

    def fake_exportar(ruta, permitir_hallazgos=False):
        llamadas.append((ruta, permitir_hallazgos))
        return 0

    monkeypatch.setattr("orquestador.exportar.exportar", fake_exportar)
    monkeypatch.setattr(sys, "argv", ["orquestador", "exportar", str(dest)])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0
    assert llamadas == [(str(dest), False)]


def test_main_ganchos_accion_invalida(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["orquestador", "ganchos", "cualquiera"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1
    assert "instalar" in capsys.readouterr().err.lower()


def test_main_exportar_sin_destino(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["orquestador", "exportar"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1
    assert "destino" in capsys.readouterr().err.lower()
