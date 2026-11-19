from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from orquestador.ganchos.definiciones import SCRIPT, definiciones_hooks

MODOS_PERMITIDOS = frozenset({"default", "acceptEdits", "plan", "auto", "dontAsk"})
# Por lanzamiento solo se puede endurecer: nunca auto, dontAsk, acceptEdits ni bypassPermissions.
MODOS_POR_LANZAMIENTO = frozenset({"default", "plan"})
_ENV_EXTRA_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_ALLOWLIST = frozenset({"HOME", "USER", "LOGNAME", "SHELL", "LANG", "COLORTERM", "XDG_RUNTIME_DIR"})


class ConfigInvalida(ValueError):
    pass


@dataclass(frozen=True)
class AjustesGuardian:
    permission_mode: str = "auto"
    columnas: int = 120
    filas: int = 40
    path: str = "/usr/local/bin:/usr/bin:/bin"
    env_extra: tuple[str, ...] = ()
    claude_bin: str = "claude"
    shell: str = ""


def _exigir_str(raw: dict, clave: str, default: str) -> str:
    if clave not in raw:
        return default
    valor = raw[clave]
    if not isinstance(valor, str):
        raise ConfigInvalida(f"guardian.{clave} debe ser texto")
    return valor


def ajustes_de(raw: dict | None, entorno: Mapping[str, str]) -> AjustesGuardian:
    if not raw:
        path = entorno.get("PATH") or AjustesGuardian.path
        return AjustesGuardian(path=path)
    modo = _exigir_str(raw, "permission_mode", "auto")
    if modo not in MODOS_PERMITIDOS:
        raise ConfigInvalida(f"guardian.permission_mode inválido: {modo}")
    columnas = AjustesGuardian.columnas
    filas = AjustesGuardian.filas
    if "tamano" in raw:
        tam = raw["tamano"]
        if not isinstance(tam, list) or len(tam) != 2:
            raise ConfigInvalida("guardian.tamano debe ser [columnas, filas]")
        c, f = tam
        if not isinstance(c, int) or not isinstance(f, int):
            raise ConfigInvalida("guardian.tamano debe ser [columnas, filas]")
        if not (20 <= c <= 500 and 5 <= f <= 200):
            raise ConfigInvalida("guardian.tamano fuera de rango")
        columnas, filas = c, f
    path = _exigir_str(raw, "path", entorno.get("PATH") or AjustesGuardian.path)
    env_extra: tuple[str, ...] = ()
    if "env_extra" in raw:
        extra = raw["env_extra"]
        if not isinstance(extra, list):
            raise ConfigInvalida("guardian.env_extra debe ser una lista")
        nombres: list[str] = []
        for item in extra:
            if not isinstance(item, str) or not _ENV_EXTRA_RE.fullmatch(item):
                raise ConfigInvalida(f"guardian.env_extra nombre inválido: {item!r}")
            nombres.append(item)
        env_extra = tuple(nombres)
    claude_bin = _exigir_str(raw, "claude_bin", "claude")
    shell = _exigir_str(raw, "shell", "")
    return AjustesGuardian(
        permission_mode=modo,
        columnas=columnas,
        filas=filas,
        path=path,
        env_extra=env_extra,
        claude_bin=claude_bin,
        shell=shell,
    )


def entorno_hijo(base: Mapping[str, str], sesion_id: str, ajustes: AjustesGuardian) -> dict[str, str]:
    nombres = set(ajustes.env_extra) - {"CLAUDECODE"}
    out = {
        clave: valor
        for clave, valor in base.items()
        if (clave in _ALLOWLIST or clave.startswith("LC_") or clave in nombres)
        and not clave.startswith("HERDR_")
    }
    out["TERM"] = "xterm-256color"
    out["PATH"] = ajustes.path
    out["COLMENA_SESION"] = sesion_id
    out["COLMENA_TERMINAL"] = "1"
    return out


def argv_claude(
    ajustes: AjustesGuardian,
    settings: Path,
    *,
    session_id: str | None = None,
    resume: str | None = None,
    modo: str | None = None,
) -> list[str]:
    if (session_id is None) == (resume is None):
        raise ValueError("exactamente uno de session_id o resume")
    if modo is not None and modo not in MODOS_POR_LANZAMIENTO:
        raise ValueError("modo de permisos por lanzamiento inválido")
    clave, valor = ("--session-id", session_id) if session_id is not None else ("--resume", resume)
    try:
        uuid.UUID(valor)
    except ValueError as exc:
        raise ValueError("uuid inválido") from exc
    return [
        ajustes.claude_bin,
        clave,
        valor,
        "--settings",
        str(settings),
        "--permission-mode",
        modo if modo is not None else ajustes.permission_mode,
    ]


def argv_shell(ajustes: AjustesGuardian, entorno: Mapping[str, str]) -> list[str]:
    shell = ajustes.shell or entorno.get("SHELL") or "/bin/bash"
    return [shell, "-l"]


def escribir_hooks(directorio: Path, espera: int) -> Path:
    directorio.mkdir(parents=True, mode=0o700, exist_ok=True)
    destino = directorio / "hooks.json"
    contenido = json.dumps(
        {"hooks": definiciones_hooks(SCRIPT, espera, origen="settings")},
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    tmp = destino.with_name(f"hooks.json.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, contenido)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, destino)
    return destino
