"""Abrir terminales nuevas en el guardián (carpetas de plan_cwds)."""
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .enchufe.modelo import Tablero
from .nueva_tarea import es_raiz_repo
from .traspaso import CONTROL_RE, NAME_RE, TraspasoError, check_label

MAX_CARPETAS = 200
NUEVA_LIMIT = (6, 3600.0)


def plan_roots(entries) -> list:
    """Carpetas permitidas para planes, en realpath. `x/*` suma cada subcarpeta (sin symlinks ni ocultas)."""
    home = os.path.realpath(Path.home())
    out: list = []
    for entry in entries or []:
        if not isinstance(entry, str) or not entry.strip():
            continue
        path = os.path.expanduser(entry.strip())
        if not os.path.isabs(path):
            continue
        if path.endswith("/*"):
            parent = path[:-2]
            try:
                names = sorted(os.listdir(parent))
            except OSError:
                continue
            cands = [os.path.join(parent, n) for n in names
                     if not n.startswith(".") and not os.path.islink(os.path.join(parent, n))]
        else:
            cands = [path]
        for cand in cands:
            real = os.path.realpath(cand)
            if os.path.isdir(real) and real not in (home, os.sep) and real not in out:
                out.append(real)
    return out


def _home_real() -> str:
    return os.path.realpath(Path.home())


def _display_path(real: str) -> str:
    home = _home_real()
    if real == home or real.startswith(home + os.sep):
        return "~" + real[len(home):]
    return real


def enumerar_carpetas(plan_cwds: list) -> list[dict]:
    """Lista estable de carpetas permitidas para la UI."""
    home = _home_real()
    seen: set[str] = set()
    out: list[dict] = []
    for entry in plan_cwds or []:
        if not isinstance(entry, str) or not entry.strip():
            continue
        raw = entry.strip()
        expanded = os.path.expanduser(raw)
        if not os.path.isabs(expanded):
            continue
        if expanded.endswith("/*"):
            parent = expanded[:-2]
            try:
                names = sorted(os.listdir(parent))
            except OSError:
                continue
            cands = [os.path.join(parent, n) for n in names
                     if not n.startswith(".") and not os.path.islink(os.path.join(parent, n))]
        else:
            cands = [expanded]
        for cand in cands:
            real = os.path.realpath(cand)
            if not os.path.isdir(real) or real in (home, os.sep) or real in seen:
                continue
            seen.add(real)
            out.append({"ruta": _display_path(real), "nombre": os.path.basename(real.rstrip(os.sep)) or real,
                        "repo": es_raiz_repo(real)})
            if len(out) >= MAX_CARPETAS:
                return out
    return out


def validar_carpeta(raw: str, plan_cwds: list) -> str:
    if not raw or not isinstance(raw, str):
        raise TraspasoError(400, "Esa carpeta no está permitida")
    text = os.path.expanduser(raw.strip())
    if CONTROL_RE.search(text) or not os.path.isabs(text):
        raise TraspasoError(400, "Esa carpeta no está permitida")
    real = os.path.realpath(text)
    if not os.path.isdir(real):
        raise TraspasoError(400, "Esa carpeta no está permitida")
    roots = plan_roots(plan_cwds)
    if not any(real == root or real.startswith(root + os.sep) for root in roots):
        raise TraspasoError(400, "Esa carpeta no está permitida")
    return real


def normalizar_nombre(raw: Optional[str], carpeta_real: str) -> str:
    if raw is None or not str(raw).strip():
        base = os.path.basename(carpeta_real.rstrip(os.sep)) or "terminal"
        return check_label(base)
    return check_label(str(raw).strip())


def slug_agente(label: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9_-]+", "-", ascii_text).strip("-_")
    slug = re.sub(r"^[^a-z]+", "", slug)[:32].rstrip("-_")
    return slug if NAME_RE.match(slug) else "terminal"


def _primera_sesion_espacio(esp, tab: "Tablero"):
    lineas = {l.id: l for l in tab.lineas}
    sesiones = {s.id: s for s in tab.sesiones}
    for lid in esp.lineas:
        lin = lineas.get(lid)
        if not lin:
            continue
        for sid in lin.sesiones:
            ses = sesiones.get(sid)
            if ses is not None:
                return ses
    return None


def carpeta_sugerida_grupo(cwd: Optional[str], plan_cwds: list) -> Optional[str]:
    if not cwd:
        return None
    try:
        return _display_path(validar_carpeta(cwd, plan_cwds))
    except TraspasoError:
        return None


def grupos_desde_tablero(tab: "Tablero", plan_cwds: list) -> list[dict]:
    out: list[dict] = []
    for esp in tab.espacios:
        ses = _primera_sesion_espacio(esp, tab)
        carpeta = carpeta_sugerida_grupo(ses.cwd if ses else None, plan_cwds)
        out.append({"id": esp.id, "nombre": esp.nombre, "carpeta": carpeta})
    return out


def agente_unico(base: str, usados: set[str]) -> str:
    if not NAME_RE.match(base):
        base = "terminal"
    name, n = base, 1
    while name in usados:
        n += 1
        suffix = f"-{n}"
        name = base[: 32 - len(suffix)] + suffix
    return name


def _gitdir_de_archivo(archivo: str) -> Optional[str]:
    try:
        with open(archivo, encoding="utf-8") as f:
            primera = f.readline(4096).strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not primera.startswith("gitdir:"):
        return None
    destino = primera[len("gitdir:"):].strip()
    if not destino:
        return None
    if not os.path.isabs(destino):
        destino = os.path.join(os.path.dirname(archivo), destino)
    return os.path.realpath(destino)


def _git_comun(raiz: str) -> Optional[str]:
    """El `.git` principal del repo de `raiz` (si `raiz` es un worktree, el de su repo principal)."""
    punto_git = os.path.join(raiz, ".git")
    if os.path.isdir(punto_git):
        return os.path.realpath(punto_git)
    destino = _gitdir_de_archivo(punto_git)
    if destino and os.path.basename(os.path.dirname(destino)) == "worktrees":
        return os.path.dirname(os.path.dirname(destino))
    return None


def _dentro(ruta: str, base: str) -> bool:
    return ruta == base or ruta.startswith(base.rstrip(os.sep) + os.sep)


def es_repo_colmena(ruta: str) -> bool:
    """True si `ruta` está en el repo de Colmena o en uno de sus worktrees. Puro: solo lee `.git`."""
    from . import config

    real = os.path.realpath(ruta)
    raiz = os.path.realpath(config.REPO_ROOT)
    if _dentro(real, raiz):
        return True
    comun = _git_comun(raiz)
    if comun is None:
        return False
    if _dentro(real, os.path.dirname(comun)):
        return True
    actual = real
    while True:
        punto_git = os.path.join(actual, ".git")
        if os.path.isdir(punto_git):
            return False
        if os.path.isfile(punto_git):
            destino = _gitdir_de_archivo(punto_git)
            return bool(destino) and _dentro(destino, os.path.join(comun, "worktrees"))
        padre = os.path.dirname(actual)
        if padre == actual:
            return False
        actual = padre
