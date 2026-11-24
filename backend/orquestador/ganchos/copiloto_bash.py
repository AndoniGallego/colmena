"""Hook PreToolUse del Copiloto de reuniones: de Bash solo pasa `orquestador nudo <op> ...`.

Claude Code deja correr sin preguntar los comandos de solo lectura (cat, grep, find...) aun en dontAsk;
este hook los niega antes. Corre con `python -I -S`: solo biblioteca estándar.
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

OPERACIONES = frozenset({"controles", "senalar", "marcar", "limpiar", "estado", "senalar-zona", "marcar-zonas"})
# Metacaracteres de shell (encadenar, sustituir, redirigir, expandir): con cualquiera se niega.
_PROHIBIDOS = frozenset(";&|`$<>\\\n\r\x00*?[]{}~!#")
MOTIVO = "El Copiloto solo puede correr `orquestador nudo <operación>`, sin encadenar ni redirigir."


def permitido(cmd: object) -> bool:
    if not isinstance(cmd, str) or not cmd.startswith("orquestador nudo "):
        return False
    if any(c in _PROHIBIDOS for c in cmd):
        return False
    try:
        partes = shlex.split(cmd)
    except ValueError:
        return False
    return len(partes) >= 3 and partes[:2] == ["orquestador", "nudo"] and partes[2] in OPERACIONES


def definicion(python: str) -> dict:
    """Bloque `hooks` para el settings.json del Copiloto. Sin `|| true`: si el hook falla, que bloquee."""
    cmd = f"{shlex.quote(python)} -I -S {shlex.quote(str(Path(__file__).resolve()))}"
    return {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": cmd, "timeout": 10}]}]}


def _negar(motivo: str) -> None:
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": motivo}}))


def main() -> int:
    try:
        datos = json.loads(sys.stdin.read() or "null")
        if not isinstance(datos, dict):
            raise ValueError
        entrada = datos.get("tool_input")
        cmd = entrada.get("command") if isinstance(entrada, dict) else None
        if datos.get("tool_name") == "Bash" and permitido(cmd):
            return 0
        _negar(MOTIVO)
        return 0
    except Exception:
        # Salir con 2 bloquea la herramienta en Claude Code.
        sys.stderr.write(MOTIVO + "\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
