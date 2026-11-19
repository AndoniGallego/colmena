import builtins
import json
import os
import sys
from pathlib import Path

import pytest
from orquestador import cli
from orquestador.config import Config, load_config, save_config


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQ_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


def test_sin_si_no_toca(tmp_path, data, capsys):
    s = tmp_path / "settings.json"
    s.write_text("{}")
    assert cli.ganchos("instalar", s, si=False) == 1
    assert s.read_text() == "{}" and "--si" in capsys.readouterr().out


def test_desinstalar_sin_si_no_toca(tmp_path, data, capsys):
    s = tmp_path / "settings.json"
    s.write_text('{"hooks": {}}')
    assert cli.ganchos("desinstalar", s, si=False) == 1
    assert s.read_text() == '{"hooks": {}}' and "--si" in capsys.readouterr().out


def test_accion_ausente_devuelve_1(tmp_path, capsys):
    s = tmp_path / "settings.json"
    s.write_text("{}")
    assert cli.ganchos(None, s, si=False) == 1
    assert "instalar" in capsys.readouterr().err.lower()


def test_dry_run_no_crea_data_dir(tmp_path, monkeypatch):
    inexistente = tmp_path / "data_nueva"
    monkeypatch.setenv("ORQ_DATA_DIR", str(inexistente))
    s = tmp_path / "settings.json"
    s.write_text("{}")
    assert not inexistente.exists()
    assert cli.ganchos("instalar", s, si=False) == 1
    assert not inexistente.exists()


def test_config_toml_invalido_con_si(tmp_path, data, capsys):
    data.mkdir(parents=True)
    (data / "config.toml").write_text("pin = \n")
    s = tmp_path / "settings.json"
    s.write_text("{}")
    assert cli.ganchos("instalar", s, si=True) == 2
    assert s.read_text() == "{}"
    err = capsys.readouterr().err
    assert err.strip()
    assert "Traceback" not in err


def test_config_vieja_sin_estado_permisos(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "config.toml").write_text('pin = "pbkdf2$200000$abc$def"\nhost = "10.0.0.1"\n')
    cfg = load_config(data)
    assert cfg.host == "10.0.0.1"
    assert ajustes_defaults(cfg)
    save_config(cfg, data)
    texto = (data / "config.toml").read_text()
    assert 'host = "10.0.0.1"' in texto
    assert "estado" in texto and "permisos" in texto


def ajustes_defaults(cfg):
    from orquestador.ganchos import ajustes as a

    return (
        a.fuente_estado(cfg) == "herdr"
        and a.permisos_desde_app(cfg) is False
        and a.permisos_espera(cfg) == 120
    )


def test_main_con_settings(tmp_path, data, monkeypatch):
    s = tmp_path / "custom" / "settings.json"
    monkeypatch.setattr(sys, "argv", ["orquestador", "ganchos", "instalar", "--settings", str(s), "--si"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0 and s.exists()


def test_instalar_y_desinstalar_por_cli(tmp_path, data, capsys):
    s = tmp_path / "settings.json"
    s.write_text("{}")
    assert cli.ganchos("instalar", s, si=True) == 0
    out = capsys.readouterr().out
    assert str(s) in out and "respaldo" in out.lower()
    assert "PermissionRequest" in json.loads(s.read_text())["hooks"]
    assert cli.ganchos("desinstalar", s, si=True) == 0 and s.read_text() == "{}"


def test_settings_invalido_sale_2(tmp_path, data, capsys):
    s = tmp_path / "settings.json"
    s.write_text("{roto")
    assert cli.ganchos("instalar", s, si=True) == 2 and s.read_text() == "{roto"


def test_usa_espera_de_config(tmp_path, data):
    data.mkdir(parents=True)
    save_config(Config(permisos={"espera": 200}), data)
    s = tmp_path / "settings.json"
    cli.ganchos("instalar", s, si=True)
    (pr,) = json.loads(s.read_text())["hooks"]["PermissionRequest"]
    assert pr["hooks"][0]["timeout"] == 210


def test_no_abre_nada_fuera_de_tmp(tmp_path, data, monkeypatch):
    real_open = builtins.open

    def guardia(file, *a, **k):
        p = Path(file).resolve() if isinstance(file, (str, Path)) else None
        if p is not None and not str(p).startswith(str(tmp_path.resolve())) and "site-packages" not in str(p) and "/usr/" not in str(p):
            raise AssertionError(f"abrió {p}")
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", guardia)
    s = tmp_path / "settings.json"
    cli.ganchos("instalar", s, si=True)
    cli.ganchos("desinstalar", s, si=True)
    home = Path(os.environ["HOME"])
    assert not (home / ".claude").exists()


def test_serve_con_xdg_pasa_ruta_socket(tmp_path, monkeypatch):
    from orquestador.config import hash_pin

    directory = tmp_path / "d"
    directory.mkdir()
    save_config(Config(pin=hash_pin("43215678")), directory)
    runtime = tmp_path / "xdg-runtime"
    runtime.mkdir()
    monkeypatch.setenv("ORQ_DATA_DIR", str(directory))
    monkeypatch.setenv("ORQ_APP_ORIGIN", "https://colmena.test")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    capturado: dict = {}

    def fake_create_app(cfg, secret, store, **kw):
        capturado["ganchos_socket"] = kw.get("ganchos_socket")
        raise SystemExit(0)

    monkeypatch.setattr("orquestador.app.create_app", fake_create_app)
    with pytest.raises(SystemExit):
        cli.serve()
    assert capturado.get("ganchos_socket") == Path(runtime / "colmena" / "ganchos.sock")


def test_serve_sin_xdg_pasa_ganchos_none(tmp_path, monkeypatch, caplog):
    import logging

    from orquestador.config import hash_pin

    directory = tmp_path / "d"
    directory.mkdir()
    save_config(Config(pin=hash_pin("43215678")), directory)
    monkeypatch.setenv("ORQ_DATA_DIR", str(directory))
    monkeypatch.setenv("ORQ_APP_ORIGIN", "https://colmena.test")
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    capturado: dict = {}

    def fake_create_app(cfg, secret, store, **kw):
        capturado["ganchos_socket"] = kw.get("ganchos_socket")
        raise SystemExit(0)

    monkeypatch.setattr("orquestador.app.create_app", fake_create_app)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(SystemExit):
            cli.serve()
    assert capturado.get("ganchos_socket") is None
    assert any("XDG_RUNTIME_DIR" in r.message for r in caplog.records)


def test_main_sin_settings_resuelve_a_home(tmp_path, data, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setattr(sys, "argv", ["orquestador", "ganchos", "instalar", "--si"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0 and (tmp_path / "h" / ".claude" / "settings.json").exists()
