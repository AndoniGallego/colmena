from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

from orquestador.ganchos.mensaje import redactar_entrada
from orquestador.listas_seguridad import (
    BASENAMES_SENSIBLES,
    SEGMENTOS_SENSIBLES,
    es_archivo_sensible,
)

_PERMITIDOS_LIST = """
ls cat head tail wc grep diff stat file pwd echo which date basename dirname
realpath readlink uname whoami id touch mkdir cut tr nl du df
""".split()

PERMITIDOS: frozenset[str] = frozenset(_PERMITIDOS_LIST)

_NEGADOS_BASE = """
sudo su doas rm rmdir dd mkfs shred chmod chown chgrp ln mv cp curl wget ssh scp rsync
nc ncat socat sh bash zsh fish dash env xargs eval exec nohup timeout watch python python3
node perl ruby php git npm npx pnpm yarn pip pip3 uv uvx docker podman kubectl systemctl
service kill pkill killall crontab at find awk sed tee herdr claude make
nice ionice setsid stdbuf chrt taskset flock script busybox time command builtin strace
chroot nsenter systemd-run unlink truncate install tar
unshare source vim vi less rg sort printenv pytest jq uniq
""".split()

NEGADOS: frozenset[str] = frozenset(_NEGADOS_BASE)

_TOKEN = re.compile(r"^[a-z][a-z0-9._-]{0,31}$")
_BASH_PROHIBIDO = frozenset(r"|&;$`<>(){}[]*?!#~\'\"=")
_GLOB = set("*?[]{}")
_BASENAMES_RECHAZADOS = BASENAMES_SENSIBLES
_SEGMENTOS_RECHAZADOS = SEGMENTOS_SENSIBLES


@dataclass(frozen=True)
class Regla:
    herramienta: str
    contenido: str
    archivo: str

    def como_permiso(self) -> dict:
        return {"toolName": self.herramienta, "ruleContent": self.contenido}

    def huella(self) -> str:
        material = f"{self.herramienta}\0{self.contenido}\0{self.archivo}"
        return hashlib.sha256(material.encode()).hexdigest()[:32]


def regla_acotada(
    herramienta: str,
    entrada: object,
    cwd: object,
    realpath=os.path.realpath,
    home=None,
) -> Regla | None:
    try:
        cwd_ok = _validar_cwd(cwd, realpath, home)
        if cwd_ok is None:
            return None
        archivo = f"{cwd_ok}/.claude/settings.local.json"
        if herramienta == "Bash":
            return _regla_bash(entrada, archivo, realpath)
        if herramienta in ("Edit", "Write", "MultiEdit"):
            return _regla_archivo(herramienta, entrada, cwd_ok, archivo, realpath)
        return None
    except Exception:
        return None


def _validar_cwd(cwd: object, realpath, home) -> str | None:
    if not isinstance(cwd, str) or not cwd:
        return None
    if ".." in cwd.split("/"):
        return None
    if not os.path.isabs(cwd):
        return None
    if realpath(cwd) != cwd:
        return None
    home_res = home if home is not None else os.path.expanduser("~")
    if cwd == "/" or cwd == home_res:
        return None
    return cwd


def _regla_bash(entrada: object, archivo: str, realpath) -> Regla | None:
    if not isinstance(entrada, dict):
        return None
    cmd = entrada.get("command")
    if not isinstance(cmd, str):
        return None
    if redactar_entrada(cmd) != cmd:
        return None
    if not _comando_bash_seguro(cmd):
        return None
    partes = cmd.split()
    if not partes:
        return None
    primero = partes[0]
    if _TOKEN.fullmatch(primero) is None:
        return None
    if primero not in PERMITIDOS or primero in NEGADOS:
        return None
    return Regla("Bash", f"{primero}:*", archivo)


def _comando_bash_seguro(cmd: str) -> bool:
    if not cmd.strip():
        return False
    if "\n" in cmd or "\r" in cmd:
        return False
    for c in cmd:
        if ord(c) < 32:
            return False
        if c.isspace() and c != " ":
            return False
        if c in _BASH_PROHIBIDO:
            return False
    return True


def _regla_archivo(
    herramienta: str,
    entrada: object,
    cwd: str,
    archivo: str,
    realpath,
) -> Regla | None:
    if not isinstance(entrada, dict):
        return None
    fp = entrada.get("file_path")
    if not isinstance(fp, str):
        return None
    if not os.path.isabs(fp):
        return None
    if ".." in fp.split("/"):
        return None
    if any(c in _GLOB for c in fp):
        return None
    if any(c in fp for c in ("\\", "!", "#")):
        return None
    if fp == cwd:
        return None
    resuelto = realpath(fp)
    if not _dentro_de_cwd(resuelto, cwd):
        return None
    if es_archivo_sensible(resuelto, cwd):
        return None
    return Regla(herramienta, f"/{resuelto}", archivo)


def _dentro_de_cwd(resuelto: str, cwd: str) -> bool:
    return resuelto.startswith(cwd + "/")
