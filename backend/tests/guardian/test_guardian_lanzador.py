import json
import os
import stat
import uuid
from pathlib import Path

import pytest

from orquestador.guardian import lanzador as lz


def test_bypass_rechazado():
    with pytest.raises(lz.ConfigInvalida):
        lz.ajustes_de({"permission_mode": "bypassPermissions"}, {})


def test_entorno_hijo_filtra():
    base = {
        "HOME": "/home/u",
        "HERDR_PANE_ID": "w1:p1",
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "x",
        "LC_ALL": "es_AR.UTF-8",
        "SECRET": "no",
    }
    env = lz.entorno_hijo(base, "g1:p2", lz.AjustesGuardian())
    assert "HERDR_PANE_ID" not in env
    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_SESSION_ID" not in env
    assert env["LC_ALL"] == "es_AR.UTF-8"
    assert env["COLMENA_SESION"] == "g1:p2"


def test_env_extra():
    base = {"HOME": "/h", "MI_VAR": "ok", "CLAUDE_CODE_FOO": "bar"}
    a = lz.ajustes_de({"env_extra": ["MI_VAR", "CLAUDE_CODE_FOO"]}, base)
    env = lz.entorno_hijo(base, "g1:p1", a)
    assert env["MI_VAR"] == "ok"
    assert env["CLAUDE_CODE_FOO"] == "bar"


def test_argv_claude_nuevo():
    uid = str(uuid.uuid4())
    a = lz.AjustesGuardian(permission_mode="plan")
    argv = lz.argv_claude(a, Path("/tmp/hooks.json"), session_id=uid)
    assert argv == [
        "claude",
        "--session-id",
        uid,
        "--settings",
        "/tmp/hooks.json",
        "--permission-mode",
        "plan",
    ]


def test_argv_claude_resume():
    uid = str(uuid.uuid4())
    a = lz.AjustesGuardian()
    argv = lz.argv_claude(a, Path("/s.json"), resume=uid)
    assert argv[1] == "--resume" and argv[2] == uid


def test_argv_shell():
    assert lz.argv_shell(lz.AjustesGuardian(), {"SHELL": "/bin/zsh"}) == ["/bin/zsh", "-l"]


def test_hooks_json(tmp_path):
    ruta = lz.escribir_hooks(tmp_path, 15)
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    data = json.loads(ruta.read_text())
    cmds = []
    for bloques in data["hooks"].values():
        for bloque in bloques:
            for hook in bloque.get("hooks", []):
                cmds.append(hook["command"])
    assert cmds and all("COLMENA_GANCHO_ORIGEN=settings" in c for c in cmds)


def test_argv_claude_modo_por_lanzamiento_default():
    uid = str(uuid.uuid4())
    a = lz.AjustesGuardian(permission_mode="auto")
    argv = lz.argv_claude(a, Path("/s.json"), session_id=uid, modo="default")
    assert argv[-2:] == ["--permission-mode", "default"]
    argv = lz.argv_claude(a, Path("/s.json"), resume=uid, modo="plan")
    assert argv[-2:] == ["--permission-mode", "plan"]
    argv = lz.argv_claude(a, Path("/s.json"), resume=uid, modo=None)
    assert argv[-2:] == ["--permission-mode", "auto"]


@pytest.mark.parametrize("modo", ["auto", "dontAsk", "acceptEdits", "bypassPermissions", "", "DEFAULT"])
def test_argv_claude_rechaza_modos_que_relajan(modo):
    uid = str(uuid.uuid4())
    with pytest.raises(ValueError):
        lz.argv_claude(lz.AjustesGuardian(), Path("/s.json"), session_id=uid, modo=modo)
    assert lz.MODOS_POR_LANZAMIENTO == frozenset({"default", "plan"})
