"""Config neutra: MRs, Centinela, Engram, separadores y carpetas (instalador)."""
import asyncio
from pathlib import Path

import pytest

from orquestador.config import Config, load_config
from orquestador.engram import argv_docker
from orquestador.mrs import MrsService, ajustes_desde_config


def test_config_defaults_neutros(tmp_path):
    cfg = Config()
    assert cfg.nombre == ""
    assert cfg.plan_cwds == []
    assert cfg.mrs == {}
    assert cfg.engram == {}


def test_load_config_ignora_claves_desconocidas(tmp_path):
    (tmp_path / "config.toml").write_text('host = "127.0.0.1"\nfoo = "bar"\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.host == "127.0.0.1"
    assert not hasattr(cfg, "foo")


def test_mrs_apagado_sin_usuario():
    assert ajustes_desde_config(Config()) is None
    svc = MrsService(Path("/tmp/x"), ajustes=None)
    assert svc.habilitado is False
    out = asyncio.run(svc.listado())
    assert out["habilitado"] is False and out["items"] == []


def test_mrs_desde_tabla_config():
    cfg = Config(mrs={
        "usuario": "dev",
        "usuario_id": 1,
        "host": "gitlab.example.com",
        "equipo": [{"usuario": "a", "id": 2, "nombre": "Ana"}],
        "repos": ["~/Proyectos/app"],
    })
    aj = ajustes_desde_config(cfg)
    assert aj.usuario == "dev" and aj.usuario_id == 1 and aj.host == "gitlab.example.com"
    assert aj.equipo["a"] == (2, "Ana")
    assert aj.repos[0].endswith("Proyectos/app")


def test_engram_argv_requiere_contenedor_y_proyecto():
    with pytest.raises(ValueError):
        argv_docker("/usr/bin/docker", "", "acme")
    args = argv_docker("/usr/bin/docker", "mi-engram", "mi-proy")
    assert "mi-engram" in args and "--project" in args and args[args.index("--project") + 1] == "mi-proy"


def test_api_mrs_deshabilitado_sin_usuario(cfg, tmp_path, handoffs, enchufe):
    from conftest import ORIGIN, PIN
    from fastapi.testclient import TestClient
    from orquestador.app import create_app
    from orquestador.board import BoardHub
    from orquestador.digest import DigestService
    from orquestador.state import StateStore

    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    app = create_app(cfg, b"s", StateStore(tmp_path), hub=hub, digests=digests, dist=tmp_path / "nd",
                     handoffs_dir=handoffs, uploads_dir=tmp_path / "up", enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        data = c.get("/api/mrs").json()
        assert data["habilitado"] is False and data["items"] == []
