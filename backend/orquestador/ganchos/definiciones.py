"""Forma de las entradas de hooks de Colmena en settings.json de Claude."""

from __future__ import annotations

import shlex
from pathlib import Path

EVENTOS_ASYNC = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Notification",
    "Stop",
)
TIMEOUT_ASYNC = 10
SCRIPT = Path(__file__).with_name("colmena_gancho.py").resolve()

_EVENTOS_CON_MATCHER = frozenset({"PreToolUse", "PostToolUse", "PermissionRequest"})


def comando(script: Path, origen: str = "global", espera: int | None = None) -> str:
    partes = [f"COLMENA_GANCHO_ORIGEN={origen}"]
    if espera is not None:
        partes.append(f"COLMENA_GANCHO_ESPERA={espera + 5}")
    partes.extend(["python3", "-I", "-S", shlex.quote(str(script.resolve())), "||", "true"])
    return " ".join(partes)


def es_de_colmena(cmd: object) -> bool:
    if not isinstance(cmd, str):
        return False
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return False
    if not tokens:
        return False
    tiene_origen = any(t.startswith("COLMENA_GANCHO_ORIGEN=") for t in tokens)
    if not tiene_origen:
        return False
    if "python3" not in tokens or "-I" not in tokens or "-S" not in tokens:
        return False
    script_idx = len(tokens) - 1
    if len(tokens) >= 3 and tokens[-2] == "||" and tokens[-1] == "true":
        script_idx = len(tokens) - 3
    return Path(tokens[script_idx]).name == "colmena_gancho.py"


def _hook_entrada(script: Path, espera: int, origen: str, evento: str) -> dict:
    if evento == "PermissionRequest":
        return {
            "type": "command",
            "command": comando(script, origen=origen, espera=espera),
            "timeout": espera + 10,
        }
    return {
        "type": "command",
        "command": comando(script, origen=origen),
        "async": True,
        "timeout": TIMEOUT_ASYNC,
    }


def definiciones_hooks(script: Path, espera: int, origen: str = "global") -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for evento in EVENTOS_ASYNC:
        bloque: dict = {"hooks": [_hook_entrada(script, espera, origen, evento)]}
        if evento in _EVENTOS_CON_MATCHER:
            bloque["matcher"] = "*"
        out[evento] = [bloque]
    out["PermissionRequest"] = [
        {
            "matcher": "*",
            "hooks": [_hook_entrada(script, espera, origen, "PermissionRequest")],
        }
    ]
    return out
