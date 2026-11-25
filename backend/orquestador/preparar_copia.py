"""Preparar la copia (worktree) de una tarea de ticket: copiar ignorados, puertos y `.colmena/env`.

El setup se lee de la base (`git show`), no del árbol de trabajo: la copia nace de la base y es lo que se confía.
Nunca se devuelve ni se registra el contenido de los archivos copiados.
"""
import hashlib
import json
import os
import re
import stat
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import private_write
from .nueva_tarea import _GIT_ENV, GIT_TIMEOUT, _git
from .traspaso import TraspasoError

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

SETUP_RUTA = ".colmena/setup.toml"
ENV_RUTA = ".colmena/env"
CLAVES = ("copiar", "script", "puertos", "docker")
MAX_TOML = 16 * 1024
MAX_SCRIPT = 64 * 1024
MAX_ORIGEN = 1024 * 1024
MAX_COPIAR = 20
RUTA_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
COMPOSES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
BLOQUE = 10
PUERTO_INICIO = 41000
BLOQUES = 100
BLOQUEADOS_BASE = frozenset({8770, 8771, 2375, 2376, 2377, 7437})


@dataclass
class Setup:
    copiar: list = field(default_factory=list)
    script: Optional[str] = None
    puertos: Optional[int] = None
    docker: Optional[str] = None
    origen: str = "repo"
    toml_texto: str = ""
    toml_sha: str = ""
    script_texto: Optional[str] = None
    script_sha: Optional[str] = None


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _ruta_valida(ruta) -> bool:
    if not isinstance(ruta, str) or not RUTA_RE.fullmatch(ruta) or ruta.startswith(("/", "-")):
        return False
    return not any(seg in ("", ".", "..") or seg.lower() == ".git" for seg in ruta.split("/"))


def _no_permitida(ruta) -> TraspasoError:
    return TraspasoError(400, f"ruta no permitida: {str(ruta)[:60]}")


def _validar_datos(datos: dict) -> dict:
    for clave in datos:
        if clave not in CLAVES:
            raise TraspasoError(400, f"clave desconocida: {str(clave)[:40]}")
    copiar = datos.get("copiar", [])
    if not isinstance(copiar, list) or len(copiar) > MAX_COPIAR or len(set(map(repr, copiar))) != len(copiar) \
            or not all(isinstance(r, str) for r in copiar):
        raise TraspasoError(400, f"`copiar` tiene que ser una lista de hasta {MAX_COPIAR} rutas")
    for ruta in copiar:
        if not _ruta_valida(ruta) or ruta.startswith(".colmena/") or ruta == ENV_RUTA:
            raise _no_permitida(ruta)
    script = datos.get("script")
    if script is not None and not _ruta_valida(script):
        raise _no_permitida(script)
    puertos = datos.get("puertos")
    if puertos is not None and (isinstance(puertos, bool) or not isinstance(puertos, int) or not 1 <= puertos <= 10):
        raise TraspasoError(400, "`puertos` va de 1 a 10")
    docker = datos.get("docker")
    if docker is not None and docker != "puertos-variables":
        raise TraspasoError(400, '`docker` solo acepta "puertos-variables"')
    return {"copiar": list(copiar), "script": script, "puertos": puertos, "docker": docker}


def _entrada_arbol(repo: str, base: str, ruta: str) -> Optional[tuple]:
    """(modo, sha) de la entrada `ruta` en la base, o None si no existe."""
    salida = _git(repo, "ls-tree", base, "--", ruta).stdout.strip()
    if not salida:
        return None
    meta, _, _ = salida.partition("\t")
    modo, _tipo, sha = meta.split(" ")
    return modo, sha


def _blob(repo: str, sha: str, tope: int, mensaje: str) -> bytes:
    try:
        res = subprocess.run(["git", "cat-file", "blob", sha], cwd=repo, capture_output=True, timeout=GIT_TIMEOUT,
                             env={**os.environ, **_GIT_ENV}, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TraspasoError(503, "Git no respondió: no hice nada") from exc
    if res.returncode != 0 or len(res.stdout) > tope:
        raise TraspasoError(400, mensaje)
    return res.stdout


def _texto(datos: bytes, mensaje: str) -> str:
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TraspasoError(400, mensaje) from exc


def leer_setup(repo: str, base: str, override: Optional[dict] = None) -> Optional[Setup]:
    """Setup de la base (o el override de la config). None = sin setup. Lanza 400 si es inválido."""
    if override is not None:
        bruto = override
        datos = _validar_datos(override)
        texto, origen = json.dumps(override, sort_keys=True, separators=(",", ":"), ensure_ascii=False), "config"
    else:
        entrada = _entrada_arbol(repo, base, SETUP_RUTA)
        if entrada is None:
            return None
        modo, sha = entrada
        if modo not in ("100644", "100755"):
            raise TraspasoError(400, "`.colmena/setup.toml` no es válido: tiene que ser un archivo común, no un enlace")
        crudo = _blob(repo, sha, MAX_TOML, "`.colmena/setup.toml` no es válido: pesa más de 16 KiB")
        texto = _texto(crudo, "`.colmena/setup.toml` no es válido: no es UTF-8")
        try:
            bruto = tomllib.loads(texto)
        except tomllib.TOMLDecodeError as exc:
            raise TraspasoError(400, f"`.colmena/setup.toml` no es válido: {str(exc)[:80]}") from exc
        datos, origen = _validar_datos(bruto), "repo"
    if not bruto:
        return None
    setup = Setup(copiar=datos["copiar"], script=datos["script"], puertos=datos["puertos"], docker=datos["docker"],
                  origen=origen, toml_texto=texto, toml_sha=_sha(texto))
    if setup.script:
        entrada = _entrada_arbol(repo, base, setup.script)
        if entrada is None:
            raise TraspasoError(400, f"el script {setup.script} no está versionado en la base")
        modo, sha = entrada
        if modo == "120000":
            raise TraspasoError(400, f"el script {setup.script} es un enlace")
        if modo != "100755":
            raise TraspasoError(400, f"el script {setup.script} tiene que ser ejecutable (modo 755)")
        setup.script_texto = _texto(_blob(repo, sha, MAX_SCRIPT, f"el script {setup.script} pesa más de 64 KiB"), f"el script {setup.script} no es UTF-8")
        setup.script_sha = _sha(setup.script_texto)
    return setup




def _versionado(repo: str, base: str, ruta: str) -> bool:
    if _git(repo, "ls-files", "--error-unmatch", "--", ruta, ok=(0, 1, 128)).returncode == 0:
        return True
    return _entrada_arbol(repo, base, ruta) is not None


def _ignorado(carpeta: str, ruta: str) -> bool:
    return _git(carpeta, "check-ignore", "-q", "--", ruta, ok=(0, 1, 128)).returncode == 0


def _sin_enlaces(raiz_real: str, ruta: str, origen: str) -> bool:
    """El origen resuelto es exactamente raiz/ruta: ningún componente es un enlace."""
    return os.path.realpath(origen) == os.path.normpath(os.path.join(raiz_real, ruta))


def validar_origenes(repo: str, base: str, setup: Setup) -> tuple:
    """(existentes, omitidos) de `copiar`. Lanza 400 si alguno es peligroso. No escribe nada."""
    real = os.path.realpath(repo)
    existentes, omitidos = [], []
    for ruta in setup.copiar:
        if _versionado(repo, base, ruta):
            raise TraspasoError(400, f"{ruta} está versionado: no se copia")
        origen = os.path.join(repo, ruta)
        try:
            st = os.lstat(origen)
        except (FileNotFoundError, NotADirectoryError):
            omitidos.append(ruta)
            continue
        except OSError as exc:
            raise TraspasoError(400, f"no puedo leer {ruta}") from exc
        if not stat.S_ISREG(st.st_mode) or not _sin_enlaces(real, ruta, origen):
            raise TraspasoError(400, f"{ruta} es un enlace o no es un archivo")
        if st.st_size > MAX_ORIGEN:
            raise TraspasoError(400, f"{ruta} pesa más de 1 MiB")
        if not _ignorado(repo, ruta):
            raise TraspasoError(400, f"{ruta} no está ignorado por git")
        existentes.append(ruta)
    return existentes, omitidos


def _leer_sin_seguir(ruta: str, tope: int) -> Optional[bytes]:
    """Contenido de un archivo regular (sin seguir enlaces en el último componente) o None."""
    try:
        fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > tope:
            return None
        return os.read(fd, tope + 1) if st.st_size else b""
    finally:
        os.close(fd)


def _padre_seguro(copia_real: str, ruta: str, padre: str) -> bool:
    return os.path.realpath(padre) == os.path.normpath(os.path.join(copia_real, os.path.dirname(ruta)))


def _crear_padres(copia_real: str, ruta: str) -> str:
    """Crea los directorios de `ruta` dentro de la copia (0700), verificando que ninguno salga de ella."""
    destino = os.path.join(copia_real, ruta)
    padre = os.path.dirname(destino)
    if not _padre_seguro(copia_real, ruta, padre):
        raise TraspasoError(400, f"{ruta} caería fuera de la copia")
    actual = copia_real
    for seg in [s for s in os.path.dirname(ruta).split("/") if s]:
        actual = os.path.join(actual, seg)
        if not os.path.lexists(actual):
            os.mkdir(actual, 0o700)
    if not _padre_seguro(copia_real, ruta, padre):
        raise TraspasoError(400, f"{ruta} caería fuera de la copia")
    return destino


def copiar_ignorados(repo: str, copia: str, rutas: list) -> None:
    """Copia cada archivo ignorado a la copia con 0600. Nunca sigue enlaces ni pisa nada; no registra contenido."""
    real_repo, real_copia = os.path.realpath(repo), os.path.realpath(copia)
    try:
        for ruta in rutas:
            origen = os.path.join(repo, ruta)
            if not _sin_enlaces(real_repo, ruta, origen):
                raise TraspasoError(400, f"{ruta} es un enlace o no es un archivo")
            datos = _leer_sin_seguir(origen, MAX_ORIGEN)
            if datos is None or len(datos) > MAX_ORIGEN:
                raise TraspasoError(400, f"{ruta} es un enlace, no es un archivo o pesa más de 1 MiB")
            destino = _crear_padres(real_copia, ruta)
            try:
                fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError as exc:
                raise TraspasoError(400, f"{ruta} ya existe en la copia") from exc
            with os.fdopen(fd, "wb") as fh:
                fh.write(datos)
            os.chmod(destino, 0o600)
    except OSError as exc:
        raise TraspasoError(500, "No pude preparar la copia: no quedó nada") from exc


def verificar_ignorados(copia: str, rutas: list) -> None:
    for ruta in rutas:
        if not _ignorado(copia, ruta):
            raise TraspasoError(400, f"{ruta} no está ignorado por git")


def coincide_en_copia(copia: str, setup: Setup) -> bool:
    """Los archivos que quedaron en la copia son los que se confiaron (la base pudo moverse en el medio)."""
    if setup.origen == "repo":
        crudo = _leer_sin_seguir(os.path.join(copia, SETUP_RUTA), MAX_TOML)
        if crudo is None or hashlib.sha256(crudo).hexdigest() != setup.toml_sha:
            return False
    if setup.script:
        ruta = os.path.join(copia, setup.script)
        crudo = _leer_sin_seguir(ruta, MAX_SCRIPT)
        if crudo is None or hashlib.sha256(crudo).hexdigest() != setup.script_sha or not os.stat(ruta).st_mode & 0o100:
            return False
    return True


def hay_compose(carpeta: str) -> bool:
    return any(os.path.isfile(os.path.join(carpeta, nombre)) for nombre in COMPOSES)


def escribir_env(copia: str, puerto, puertos, compose: bool) -> None:
    """Escribe `.colmena/env` (0600) en la copia. Rechaza enlaces y no pisa un archivo existente."""
    carpeta = os.path.join(copia, ".colmena")
    lineas = []
    if puerto is not None:
        lineas += [f"COLMENA_PORT={puerto}", f"COLMENA_PORT_COUNT={puertos}"]
    if compose:
        lineas.append("COMPOSE_PROJECT_NAME=" + re.sub(r"[^a-z0-9_-]", "-", os.path.basename(copia.rstrip(os.sep)).lower()))
    try:
        if os.path.islink(carpeta):
            raise TraspasoError(400, "`.colmena` es un enlace: no escribo ahí")
        os.makedirs(carpeta, exist_ok=True)
        if os.path.realpath(carpeta) != os.path.join(os.path.realpath(copia), ".colmena"):
            raise TraspasoError(400, "`.colmena` es un enlace: no escribo ahí")
        try:
            fd = os.open(os.path.join(carpeta, "env"), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError as exc:
            raise TraspasoError(400, "`.colmena/env` ya existe en la copia") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("".join(f"{linea}\n" for linea in lineas))
        os.chmod(os.path.join(carpeta, "env"), 0o600)
    except OSError as exc:
        raise TraspasoError(500, "No pude preparar la copia: no quedó nada") from exc


def payload_confianza(repo: str, base: str, setup: Setup) -> dict:
    """Lo que Ando revisa antes de confiar: el toml y el script (versionados), nunca el contenido de los `.env`."""
    return {"repo": repo, "base": base, "origen": setup.origen, "setup_toml": setup.toml_texto,
            "setup_sha256": setup.toml_sha, "script": setup.script, "script_contenido": setup.script_texto,
            "script_sha256": setup.script_sha, "copiar": list(setup.copiar), "puertos": setup.puertos,
            "docker": setup.docker}


class ConfianzaPreparar:
    """Repos cuyo setup (toml + script) confió Ando, atado a los hashes. Fail-closed si el archivo no se lee."""

    ARCHIVO = "preparar-confianza.json"

    def __init__(self, directory):
        self.path = Path(directory) / self.ARCHIVO
        self._lock = threading.Lock()

    def _repos(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        repos = data.get("repos") if isinstance(data, dict) else None
        return {k: v for k, v in repos.items() if isinstance(v, dict)} if isinstance(repos, dict) else {}

    def hay(self, repo: str, setup_sha: str, script_sha: Optional[str]) -> bool:
        e = self._repos().get(repo)
        return e is not None and e.get("setup_sha256") == setup_sha and e.get("script_sha256") == script_sha

    def guardar(self, repo: str, setup_sha: str, script_sha: Optional[str]) -> None:
        with self._lock:
            repos = self._repos()
            repos[repo] = {"setup_sha256": setup_sha, "script_sha256": script_sha,
                           "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            private_write(self.path, json.dumps({"v": 1, "repos": repos}))


def comando_setup(script: str) -> str:
    """Comando fijo de la pestaña «setup». La ruta ya pasó la regex: no admite comillas ni metacaracteres."""
    return f"sh -c 'set -a; . ./.colmena/env; set +a; exec ./{script}'"


def sufijo_mensaje(script: Optional[str], puerto: Optional[int], puertos: Optional[int], fijos: bool) -> str:
    partes = []
    if script:
        partes.append(f"La copia se está preparando en la pestaña «setup» (`{script}`): esperá a que termine antes de "
                      "correr tests o levantar servicios.")
    if fijos:
        partes.append("Los puertos son fijos: una copia corriendo a la vez.")
    elif puerto is not None:
        partes.append(f"Puertos: COLMENA_PORT={puerto} ({puertos} {'puerto' if puertos == 1 else 'puertos'}), "
                      "en .colmena/env.")
    return " ".join(partes)


def sufijo_maximo(script: Optional[str]) -> str:
    """El sufijo más largo posible: sirve para validar el largo de la nota antes de reservar el puerto."""
    return max(sufijo_mensaje(script, 41990, 10, False), sufijo_mensaje(script, None, None, True), key=len)
