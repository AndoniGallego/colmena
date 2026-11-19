"""Nueva tarea: cada tarea trabaja en su propia copia del repo (git worktree) y su rama."""
import os
import json
import re
import subprocess
import threading
import unicodedata
from pathlib import Path
from typing import Optional

from . import kit_trabajo
from .config import private_write
from .envio_sesion import linea_unica
from .mensaje import MAX_TEXT
from .traspaso import TraspasoError

MAX_SLUG = 40
PALABRAS_NOMBRE = 6
REPOS_KIT = frozenset({"orquestador"})
TICKET_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]{1,9}-\d{1,6})(?![A-Za-z0-9-])")


def slug_de(tarea: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", tarea or "").encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:MAX_SLUG].strip("-")
    return slug or "tarea"


def ticket_de(tarea: str) -> Optional[str]:
    found = TICKET_RE.search(tarea or "")
    return found.group(1) if found else None


def nombre_pestana(tarea: str) -> str:
    palabras = (tarea or "").split()[:PALABRAS_NOMBRE]
    return " ".join(palabras)[:60].strip().lstrip("-").strip() or "Tarea"


def rama_para(repo_nombre: str, tarea: str) -> str:
    ticket = ticket_de(tarea)
    if ticket:
        return f"feature/{ticket}"
    prefijo = "feature/kit-" if repo_nombre in REPOS_KIT else "feature/"
    return prefijo + slug_de(tarea)


TICKET_ESTRICTO = re.compile(r"^[A-Z][A-Z0-9]{1,9}-[1-9][0-9]{0,5}$")
NOMBRE_TICKET_MAX = 60


def validar_ticket(raw: str) -> str:
    clave = (raw or "").strip().upper() if isinstance(raw, str) else ""
    if not TICKET_ESTRICTO.fullmatch(clave):
        raise TraspasoError(400, "Ese ticket no tiene forma de clave de Jira (p. ej. ABC-123)")
    return clave


def mensaje_ticket(clave: str, rama: str, nota: str) -> str:
    texto = (f"Arrancá el ticket {clave}. Primero leelo con el agente {kit_trabajo.valor('agente_tickets')} (nunca la API de Jira directo) y "
             f"después seguí {kit_trabajo.valor('comando_flujo')} desde el principio, con sus aprobaciones. Estás en una copia del repo "
             f"solo para esta tarea, en la rama {rama}.")
    nota = linea_unica(nota, MAX_TEXT)
    armado = f"{texto} Nota de Ando: {nota}" if nota else texto
    if len(armado) > MAX_TEXT:
        maximo = MAX_TEXT - (len(armado) - len(nota))
        raise TraspasoError(400, f"La nota es muy larga para un ticket: máximo {maximo} caracteres")
    return armado


def nombre_ticket(clave: str, nota: str) -> str:
    resto = nombre_pestana(linea_unica(nota, 300)) if linea_unica(nota, 300) else ""
    return f"{clave} · {resto}"[:NOMBRE_TICKET_MAX].rstrip() if resto else clave


RAMA_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,79}$")
GIT_TIMEOUT = 30.0
_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}


def validar_rama(rama: str) -> str:
    malo = (not isinstance(rama, str) or not RAMA_RE.fullmatch(rama) or ".." in rama or "//" in rama
            or rama.endswith(("/", ".", ".lock")) or rama == "@"
            or any(seg.startswith(".") or seg.endswith(".lock") for seg in rama.split("/")))
    if malo:
        raise TraspasoError(400, "Ese nombre de rama no sirve: usá letras, números, guiones y barras")
    return rama


def _git(cwd: str, *args: str, ok: tuple = (0,)) -> subprocess.CompletedProcess:
    """git sin shell, sin red ni preguntas, con tope de tiempo."""
    try:
        res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=GIT_TIMEOUT,
                             env={**os.environ, **_GIT_ENV}, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TraspasoError(503, "Git no respondió: no hice nada") from exc
    if res.returncode not in ok:
        raise TraspasoError(409, (res.stderr or res.stdout or "git falló").strip().splitlines()[-1][:200])
    return res


def _existe(repo: str, ref: str) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", ok=(0, 1)).returncode == 0


def rama_existe(repo: str, rama: str) -> bool:
    return _git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{rama}", ok=(0, 1)).returncode == 0


def es_raiz_repo(ruta: str) -> bool:
    return os.path.isdir(ruta) and os.path.exists(os.path.join(ruta, ".git"))


def base_por_defecto(repo: str) -> str:
    """Rama por defecto del repo sin tocar la red: origin/HEAD, si no main, master o la actual."""
    res = _git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", ok=(0, 1))
    remota = res.stdout.strip()
    if res.returncode == 0 and remota and _existe(repo, remota):
        return remota
    for nombre in ("main", "master"):
        if _existe(repo, f"refs/heads/{nombre}"):
            return nombre
    return "HEAD"


def ruta_libre(repo: str, slug: str) -> str:
    base = repo.rstrip(os.sep)
    candidata, n = f"{base}-{slug}", 1
    while os.path.lexists(candidata):
        n += 1
        candidata = f"{base}-{slug}-{n}"
    return candidata


def crear_worktree(repo: str, rama: str, ruta: str, base: str) -> None:
    validar_rama(rama)
    if _git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{rama}", ok=(0, 1)).returncode == 0:
        raise TraspasoError(409, "Esa rama ya existe: elegí otro nombre en «Más opciones»")
    if os.path.lexists(ruta):
        raise TraspasoError(409, "Esa carpeta ya existe")
    _git(repo, "worktree", "add", "--no-track", "-b", rama, ruta, base)


def quitar_recien_creado(repo: str, rama: str, ruta: str, base: str) -> None:
    """Deshace un crear_worktree cuya sesión no abrió. Solo borra la rama si sigue sin commits propios."""
    _git(repo, "worktree", "remove", ruta, ok=(0, 128))
    if _existe(repo, f"refs/heads/{rama}") and _git(repo, "rev-parse", f"refs/heads/{rama}").stdout == \
            _git(repo, "rev-parse", base).stdout:
        _git(repo, "branch", "-D", rama, ok=(0, 1))


class Worktrees:
    """Registro de las copias que creó Colmena (json privado en el directorio de datos)."""

    ARCHIVO = "nueva-tarea-worktrees.json"

    def __init__(self, directory):
        self.path = Path(directory) / self.ARCHIVO
        self._lock = threading.Lock()

    def todas(self) -> list:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("copias") if isinstance(data, dict) else None
        claves = ("ruta", "repo", "rama", "base")
        return [e for e in items or [] if isinstance(e, dict) and all(isinstance(e.get(k), str) for k in claves)]

    def _guardar(self, items: list) -> None:
        private_write(self.path, json.dumps({"v": 1, "copias": items}, ensure_ascii=False))

    def rutas(self) -> list:
        return [e["ruta"] for e in self.todas()]

    def get(self, ruta: str):
        return next((e for e in self.todas() if e["ruta"] == ruta), None)

    def agregar(self, entrada: dict) -> None:
        with self._lock:
            items = [e for e in self.todas() if e["ruta"] != entrada["ruta"]]
            self._guardar([*items, {k: entrada[k] for k in ("ruta", "repo", "rama", "base")}])

    def quitar(self, ruta: str) -> None:
        with self._lock:
            self._guardar([e for e in self.todas() if e["ruta"] != ruta])


def _bases(entrada: dict) -> list:
    base = entrada["base"]
    local = base.split("/", 1)[1] if base.startswith("origin/") else None
    return [base, *([local] if local else [])]


def estado_copia(entrada: dict) -> dict:
    """Si la copia se puede borrar sin perder trabajo: sin cambios sin guardar y rama integrada en la base."""
    ruta, repo, rama = entrada["ruta"], entrada["repo"], entrada["rama"]
    if not os.path.isdir(ruta):
        return {"borrable": False, "motivo": "La copia ya no está"}
    if _git(ruta, "status", "--porcelain").stdout.strip():
        return {"borrable": False, "motivo": "Tiene cambios sin guardar"}
    for base in _bases(entrada):
        if _existe(repo, base) and _git(repo, "merge-base", "--is-ancestor", f"refs/heads/{rama}", base,
                                        ok=(0, 1)).returncode == 0:
            return {"borrable": True, "motivo": ""}
    return {"borrable": False, "motivo": "La rama no está mergeada"}


def borrar_copia(entrada: dict) -> None:
    """Quita la carpeta de la copia (nunca con --force) y deja la rama. Falla si el estado no es borrable."""
    estado = estado_copia(entrada)
    if not estado["borrable"]:
        raise TraspasoError(409, estado["motivo"])
    _git(entrada["repo"], "worktree", "remove", entrada["ruta"])
