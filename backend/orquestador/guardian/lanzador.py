from __future__ import annotations

import json
import logging
import os
import re
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from orquestador.ganchos.copiloto_bash import definicion as definicion_bash
from orquestador.ganchos.definiciones import SCRIPT, definiciones_hooks

MODOS_PERMITIDOS = frozenset({"default", "acceptEdits", "plan", "auto", "dontAsk"})
# Por lanzamiento solo se puede endurecer: nunca auto, dontAsk, acceptEdits ni bypassPermissions.
MODOS_POR_LANZAMIENTO = frozenset({"default", "plan"})
# Modos que solo valen en una carpeta fija: llegan por el enchufe, pero el núcleo los rechaza en otra carpeta.
MODOS_INTERNOS = frozenset({"copiloto", "guia"})
REPO_ROOT = Path(__file__).resolve().parents[3]
AJUSTES_COPILOTO = "ajustes-copiloto.json"
MAX_DIRS_EXTRA = 32

log = logging.getLogger(__name__)


def _dentro(ruta: Path, base: Path) -> bool:
    return ruta == base or base in ruta.parents


def rutas_protegidas(entorno: Mapping[str, str]) -> list[str]:
    """El repo de Colmena y su data dir (secretos, charlas, diarios): el Copiloto nunca los lee."""
    datos = entorno.get("ORQ_DATA_DIR")
    data_dir = Path(os.path.expanduser(datos)) if datos else REPO_ROOT / "data"
    out: list[str] = []
    for ruta in (REPO_ROOT, data_dir):
        for forma in (str(ruta), os.path.realpath(ruta)):
            if forma not in out:
                out.append(forma)
    return out


def dirs_extra_validos(dirs: object, entorno: Mapping[str, str] | None = None) -> list[str]:
    """Rutas (realpath) que el Copiloto puede leer con --add-dir. Lo inválido se descarta con un log, sin fallar."""
    if not isinstance(dirs, (list, tuple)):
        return []
    protegidas = [Path(p) for p in rutas_protegidas(os.environ if entorno is None else entorno)]
    out: list[str] = []
    for crudo in dirs:
        if len(out) >= MAX_DIRS_EXTRA:
            log.warning("dirs_extra: más de %d, descarto el resto", MAX_DIRS_EXTRA)
            break
        motivo = None
        real = ""
        if not isinstance(crudo, str) or not crudo or not os.path.isabs(crudo):
            motivo = "no es una ruta absoluta"
        elif any(ord(c) < 32 or ord(c) == 127 for c in crudo):
            motivo = "tiene caracteres de control"
        else:
            try:
                real = os.path.realpath(crudo)
            except (OSError, ValueError):
                motivo = "no se pudo resolver"
            else:
                if not os.path.isdir(real):
                    motivo = "no es una carpeta"
                elif any(_dentro(Path(real), p) or _dentro(p, Path(real)) for p in protegidas):
                    motivo = "es de Colmena"
                elif real in out:
                    motivo = "duplicada"
        if motivo:
            log.warning("dirs_extra: descarto una ruta (%s)", motivo)
            continue
        out.append(real)
    return out


CARPETAS_INTERNAS = {"copiloto": "reunion-copiloto", "guia": "guia"}


def carpeta_interna(modo: str, entorno: Mapping[str, str]) -> Path:
    """Carpeta de trabajo de un modo interno, fuera del repo y del data dir: $XDG_DATA_HOME o ~/.local/share."""
    home = Path(entorno.get("HOME") or Path.home())
    por_defecto = home / ".local" / "share"
    xdg = entorno.get("XDG_DATA_HOME") or ""
    base = Path(xdg) if os.path.isabs(xdg) else por_defecto
    nombre = CARPETAS_INTERNAS[modo]
    destino = base / "orquestador" / nombre
    if any(_dentro(destino, Path(p)) for p in rutas_protegidas(entorno)):
        destino = por_defecto / "orquestador" / nombre
    return destino


def carpeta_copiloto(entorno: Mapping[str, str]) -> Path:
    return carpeta_interna("copiloto", entorno)


def carpeta_guia(entorno: Mapping[str, str]) -> Path:
    return carpeta_interna("guia", entorno)


CARPETA_COPILOTO = carpeta_copiloto(os.environ)
CARPETA_GUIA = carpeta_guia(os.environ)
ARGS_COPILOTO = (
    "--permission-mode",
    "dontAsk",
    "--tools",
    "Read,Grep,Glob,Bash",
    "--setting-sources",
    "project,local",
    "--strict-mcp-config",
    # Tareas cortas y repetidas (mirar una captura, seguir una reunión): no hace falta el modelo caro.
    "--model",
    "sonnet",
)
# Memoria de los ayudantes: cada uno en su proyecto de Engram (nunca el de Ando), y el servidor solo expone buscar
# y guardar. El contenedor sale de `guardian.memoria_contenedor`; sin él no hay memoria. Si el contenedor no está
# corriendo, Claude arranca igual, sin memoria.
HERRAMIENTAS_MEMORIA = ("mem_search", "mem_save")
_CONTENEDOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def args_memoria(modo: str, contenedor: str) -> list[str]:
    if not contenedor:
        return []
    server = {
        "command": "docker",
        "args": ["exec", "-i", contenedor, "engram", "mcp",
                 "--tools=" + ",".join(HERRAMIENTAS_MEMORIA), "--project", f"colmena-{modo}"],
    }
    return ["--mcp-config", json.dumps({"mcpServers": {"engram": server}}, ensure_ascii=False)]


_ENV_EXTRA_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_ALLOWLIST = frozenset({"HOME", "USER", "LOGNAME", "SHELL", "LANG", "COLORTERM", "XDG_RUNTIME_DIR"})


def carpeta_de_modo(modo: str) -> Path:
    return CARPETA_GUIA if modo == "guia" else CARPETA_COPILOTO


def es_carpeta_interna(modo: str, cwd: str) -> bool:
    if modo not in CARPETAS_INTERNAS:
        return False
    try:
        return os.path.realpath(cwd) == os.path.realpath(carpeta_de_modo(modo))
    except (OSError, ValueError):
        return False


def es_carpeta_copiloto(cwd: str) -> bool:
    return es_carpeta_interna("copiloto", cwd)


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
    memoria_contenedor: str = ""


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
    memoria = _exigir_str(raw, "memoria_contenedor", "")
    if memoria and not _CONTENEDOR_RE.fullmatch(memoria):
        raise ConfigInvalida("guardian.memoria_contenedor inválido")
    return AjustesGuardian(
        permission_mode=modo,
        columnas=columnas,
        filas=filas,
        path=path,
        env_extra=env_extra,
        claude_bin=claude_bin,
        shell=shell,
        memoria_contenedor=memoria,
    )


def _path_copiloto(path: str) -> str:
    """El Copiloto corre `orquestador nudo`: suma el bin del venv del guardián si el ejecutable está ahí."""
    bin_dir = str(Path(sys.executable).parent)
    if not os.path.isfile(os.path.join(bin_dir, "orquestador")) or bin_dir in path.split(os.pathsep):
        return path
    return f"{path}{os.pathsep}{bin_dir}" if path else bin_dir


def entorno_hijo(base: Mapping[str, str], sesion_id: str, ajustes: AjustesGuardian,
                 copiloto: bool = False) -> dict[str, str]:
    nombres = set(ajustes.env_extra) - {"CLAUDECODE"}
    out = {
        clave: valor
        for clave, valor in base.items()
        if (clave in _ALLOWLIST or clave.startswith("LC_") or clave in nombres)
        and not clave.startswith("HERDR_")
    }
    out["TERM"] = "xterm-256color"
    out["PATH"] = _path_copiloto(ajustes.path) if copiloto else ajustes.path
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
    dirs_extra: list[str] | None = None,
    entorno: Mapping[str, str] | None = None,
) -> list[str]:
    if (session_id is None) == (resume is None):
        raise ValueError("exactamente uno de session_id o resume")
    if modo is not None and modo not in MODOS_POR_LANZAMIENTO | MODOS_INTERNOS:
        raise ValueError("modo de permisos por lanzamiento inválido")
    clave, valor = ("--session-id", session_id) if session_id is not None else ("--resume", resume)
    try:
        uuid.UUID(valor)
    except ValueError as exc:
        raise ValueError("uuid inválido") from exc
    if dirs_extra and modo != "copiloto":
        raise ValueError("dirs_extra solo vale en modo copiloto")
    if modo in MODOS_INTERNOS:
        # --mcp-config toma varios valores: va antes de otras opciones para que nunca se trague un argumento suelto.
        argv = [ajustes.claude_bin, clave, valor, "--settings", str(ajustes_copiloto(settings)), *args_memoria(modo, ajustes.memoria_contenedor), *ARGS_COPILOTO]
        # `blockReadsOutsideWorkingDirectories` ignora additionalDirectories del proyecto: solo --add-dir cuenta.
        # La guía nunca lleva --add-dir: solo ve su carpeta.
        if modo == "copiloto":
            for ruta in dirs_extra_validos(dirs_extra or [], entorno):
                argv += ["--add-dir", ruta]
        return argv
    base = [ajustes.claude_bin, clave, valor, "--settings", str(settings)]
    return [*base, "--permission-mode", modo if modo is not None else ajustes.permission_mode]


def argv_shell(ajustes: AjustesGuardian, entorno: Mapping[str, str]) -> list[str]:
    shell = ajustes.shell or entorno.get("SHELL") or "/bin/bash"
    return [shell, "-l"]


def ajustes_copiloto(settings: Path) -> Path:
    return Path(settings).with_name(AJUSTES_COPILOTO)


def escribir_hooks(directorio: Path, espera: int, protegidos: list[str] | None = None) -> Path:
    """Escribe hooks.json y, al lado, los ajustes del Copiloto (hooks + límite de Bash + bloqueo de lecturas).

    `workingDirectoriesExclude` solo vale en --settings: por eso va acá y no en la carpeta del Copiloto.
    """
    directorio.mkdir(parents=True, mode=0o700, exist_ok=True)
    hooks = definiciones_hooks(SCRIPT, espera, origen="settings")
    excluir = list(rutas_protegidas(os.environ) if protegidos is None else protegidos)
    # El hook que limita Bash al nudo va también acá: corre aunque no se cargue el settings del proyecto.
    hooks_copiloto = {evento: list(bloques) for evento, bloques in hooks.items()}
    for evento, bloques in definicion_bash(sys.executable).items():
        hooks_copiloto.setdefault(evento, []).extend(bloques)
    _escribir_json(directorio / AJUSTES_COPILOTO, {
        "hooks": hooks_copiloto,
        "permissions": {"blockReadsOutsideWorkingDirectories": True, "workingDirectoriesExclude": excluir},
    })
    return _escribir_json(directorio / "hooks.json", {"hooks": hooks})


def _escribir_json(destino: Path, datos: dict) -> Path:
    contenido = json.dumps(datos, ensure_ascii=False, indent=2).encode("utf-8")
    tmp = destino.with_name(f"{destino.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, contenido)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, destino)
    return destino
