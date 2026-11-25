"""Inyección del MCP de Colmena en el lanzador (CA10) y nunca en copiloto ni guía (CA5)."""
import json
import stat
import sys
import uuid
from pathlib import Path

import pytest

from orquestador.guardian import lanzador as lz

UID = str(uuid.uuid4())
CFG = Path("/run/x/colmena-guardian/mcp-colmena.json")


def _argv(**kw):
    return lz.argv_claude(lz.AjustesGuardian(permission_mode="auto"), Path("/s.json"), session_id=UID, **kw)


def test_modo_normal_con_version_nueva_lleva_mcp_config_antes_de_settings():
    argv = _argv(mcp_config=CFG, claude_version=(2, 1, 304))
    assert argv[:5] == ["claude", "--session-id", UID, "--mcp-config", str(CFG)]
    assert argv[5:] == ["--settings", "/s.json", "--permission-mode", "auto"]
    assert "--strict-mcp-config" not in argv


@pytest.mark.parametrize("version", [None, (2, 1, 303), (2, 0, 999), (1, 9, 400)])
def test_version_vieja_o_desconocida_no_lleva_mcp_y_el_resto_no_cambia(version):
    assert _argv(mcp_config=CFG, claude_version=version) == _argv()


def test_sin_config_no_lleva_mcp():
    assert _argv(mcp_config=None, claude_version=(2, 2, 0)) == _argv()


@pytest.mark.parametrize("modo", sorted(lz.MODOS_INTERNOS))
def test_copiloto_y_guia_nunca_llevan_mcp(modo):
    argv = _argv(modo=modo, mcp_config=CFG, claude_version=(3, 0, 0))
    assert str(CFG) not in argv
    assert argv == _argv(modo=modo)


@pytest.mark.parametrize("texto,esperado", [
    ("2.1.304 (Claude Code)\n", (2, 1, 304)),
    ("2.10.0", (2, 10, 0)),
    ("claude 2.1.331-beta (Claude Code)", (2, 1, 331)),
    ("", None),
    ("sin versión", None),
])
def test_parsear_version_claude(texto, esperado):
    assert lz.parsear_version_claude(texto) == esperado


def test_detectar_version_usa_el_binario_y_cae_a_none(tmp_path):
    falso = tmp_path / "falso-cli"
    falso.write_text("#!/bin/sh\necho '2.1.320 (Claude Code)'\n")
    falso.chmod(0o755)
    assert lz.detectar_version_claude(str(falso), {"PATH": "/usr/bin:/bin"}) == (2, 1, 320)
    roto = tmp_path / "roto"
    roto.write_text("#!/bin/sh\nexit 3\n")
    roto.chmod(0o755)
    assert lz.detectar_version_claude(str(roto), {"PATH": "/usr/bin:/bin"}) is None
    assert lz.detectar_version_claude(str(tmp_path / "no-existe"), {}) is None


def test_escribir_mcp_config_0600_con_python_del_backend(tmp_path):
    sock = tmp_path / "colmena" / "mcp.sock"
    ruta = lz.escribir_mcp_config(tmp_path / "datos", sock)
    assert ruta.name == "mcp-colmena.json"
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    assert json.loads(ruta.read_text()) == {"mcpServers": {"colmena": {
        "command": sys.executable, "args": ["-I", "-m", "orquestador.mcp_colmena", "--socket", str(sock)]}}}


def test_el_mcp_no_importa_codigo_de_la_carpeta_de_la_sesion(tmp_path):
    """Claude lanza el MCP con cwd en el repo de la sesión: un `json.py` ahí no se tiene que importar."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    marca = tmp_path / "importado"
    (repo / "json.py").write_text(f"open({str(marca)!r}, 'w').close()\nraise SystemExit(7)\n")
    cfg = json.loads(lz.escribir_mcp_config(tmp_path / "datos", tmp_path / "no.sock").read_text())
    srv = cfg["mcpServers"]["colmena"]
    res = subprocess.run([srv["command"], *srv["args"]], cwd=repo, input="", capture_output=True, text=True,
                         timeout=30, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(repo)})
    assert not marca.exists(), res.stderr
    assert res.returncode == 0, res.stderr


def _guardian_con_sesion(tmp_path, **kw):
    import asyncio

    from orquestador.guardian.nucleo import Guardian, _RuntimeSesion
    from orquestador.guardian.pantalla import Pantalla
    from orquestador.guardian.registro import Registro

    reg = Registro(tmp_path / "registro.json")
    esp = reg.nuevo_espacio("E", str(tmp_path))
    lin = reg.nueva_linea(esp.id, "L")
    ses = reg.nueva_sesion(lin.id, "S", str(tmp_path), "claude", None)
    g = Guardian(reg, lz.AjustesGuardian(), tmp_path / "hooks.json", entorno={"PATH": "/usr/bin"},
                 cwd_confiable=lambda c: True, **kw)
    lanzados = []

    async def lanzar(rt, argv, **_):
        lanzados.append(argv)

    g._lanzar = lanzar
    rt = _RuntimeSesion(registro=ses, pantalla=Pantalla(10, 5, 10))
    asyncio.run(g._lanzar_claude(rt, session_id=UID))
    return lanzados[0]


def test_el_guardian_pasa_config_y_version_al_lanzar(tmp_path):
    argv = _guardian_con_sesion(tmp_path, mcp_config=CFG, claude_version=(2, 1, 310))
    assert argv[3:5] == ["--mcp-config", str(CFG)]


def test_el_guardian_sin_mcp_lanza_igual_que_antes(tmp_path):
    assert "--mcp-config" not in _guardian_con_sesion(tmp_path)
