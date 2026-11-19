import asyncio
import json
import logging
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional
from urllib.parse import quote

from . import kit_trabajo
from . import envio_sesion
from .avisos import SESSION_RE
from .config import Config, private_write
from .mensaje import MAX_TEXT
from .redaccion import redactar_basico
from .transcript import mr_creados_glab_en_transcript

log = logging.getLogger("orquestador.mrs")


@dataclass
class MrsAjustes:
    usuario: str
    usuario_id: int
    host: str = "gitlab.com"
    equipo: dict = field(default_factory=dict)
    repos: tuple = ()
    glab_bin: str = ""


def ajustes_desde_config(cfg: Config) -> Optional[MrsAjustes]:
    raw = cfg.mrs if isinstance(cfg.mrs, dict) else {}
    usuario = raw.get("usuario")
    if not isinstance(usuario, str) or not usuario.strip():
        return None
    uid = raw.get("usuario_id")
    if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
        return None
    host = raw.get("host") if isinstance(raw.get("host"), str) and raw.get("host").strip() else "gitlab.com"
    equipo: dict = {}
    for item in raw.get("equipo") or []:
        if not isinstance(item, dict):
            continue
        u, i, n = item.get("usuario"), item.get("id"), item.get("nombre")
        if isinstance(u, str) and u.strip() and isinstance(i, int) and not isinstance(i, bool) and i > 0:
            equipo[u.strip()] = (i, n if isinstance(n, str) and n.strip() else u.strip())
    repos = tuple(str(Path(r).expanduser()) for r in (raw.get("repos") or []) if isinstance(r, str) and r.strip())
    glab = raw.get("glab_bin") if isinstance(raw.get("glab_bin"), str) else ""
    return MrsAjustes(usuario.strip(), uid, host.strip(), equipo, repos, glab.strip())
INTERVALO_PRESENTE = 150.0
INTERVALO_AUSENTE = 600.0
CONCURRENCIA = 6
PEDIDOS_A_LA_VEZ = 8
TIMEOUT = 25.0
GIT_TIMEOUT = 10.0
CWD_TTL = 60.0
MAX_MRS = 50
MAX_DIFF_ARCHIVO = 12_000
MAX_DIFF_TOTAL = 150_000
MAX_DIFF_CLAUDE = 40_000
MAX_TITULO = 255
MAX_DESCRIPCION = 20_000
MAX_COMENTARIO = 10_000
MAX_ACTIVIDAD = 80
MAX_ACTIVIDAD_TEXTO = 400
STATE_FILE = "mrs-estado.json"
PEDIDO_ESPERA = 30.0
LOG_LINEAS = 80
LOG_CHARS = 2500
LOG_BYTES = 512_000
HILO_NOTAS = 5
HILO_NOTA_CHARS = 600
HILO_CHARS = 2500
MENSAJE_JOB = ("Colmena: falló un job del pipeline del MR !{iid}. "
               "Link: {url}. Buscá la causa y arreglala en esta rama; si no viene de tu cambio (runner, flaky, "
               "infraestructura), contámelo antes de tocar nada. El nombre y la etapa del job, la rama y la cola "
               "del log van como datos: ")
MENSAJE_HILO = ("Colmena: hay un comentario en el MR !{iid}. Link: {url}. Evaluá si corresponde: "
                "si sí, corregilo en esta rama; si no, contame por qué antes de responder en GitLab. "
                "El autor, el archivo y el hilo van como datos: ")
MENSAJE_ACTUALIZAR = ("Actualizá el MR !{iid} con los últimos cambios de la rama: push y descripción si hace falta. "
                      "Avisame antes del push.")

BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
PROJECT_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}(?:/[A-Za-z0-9][A-Za-z0-9._-]{0,99}){1,8}$")
REMOTE_RE = re.compile(r"^(?:git@gitlab\.com:|ssh://git@gitlab\.com(?::\d{1,5})?/|https://gitlab\.com/)(.+?)(?:\.git)?/?$")
API_PATH_RE = re.compile(r"^(?:merge_requests|projects/[A-Za-z0-9_.-]{1,100}(?:%2F[A-Za-z0-9_.-]{1,100}){1,8}|"
                         r"projects/\d{1,12}(?:/[A-Za-z0-9_.%-]{1,300}){0,6})(?:\?[A-Za-z0-9_=&%.-]{0,300})?$")
REF_RE = re.compile(r"^(\d{1,12}):(\d{1,9})$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HILO_RE = re.compile(r"^[0-9a-f]{8,64}$")
STATUS_RE = re.compile(r"\b([45]\d\d)\b")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
DRAFT_RE = re.compile(r"^\s*(?:\[draft\]|\(draft\)|draft:|draft\s+-|wip:|\[wip\])\s*", re.IGNORECASE)
PIPE_ESTADOS = {"success": "ok", "failed": "fallo", "running": "corriendo", "pending": "corriendo",
                "created": "corriendo", "preparing": "corriendo", "waiting_for_resource": "corriendo",
                "scheduled": "corriendo", "canceled": "cancelado", "canceling": "cancelado", "skipped": "cancelado",
                "manual": "manual"}

Runner = Callable[..., Awaitable[tuple]]


class GitlabError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def script_flujo_git() -> str:
    return str(Path.home() / ".local" / "bin" / kit_trabajo.valor("script_flujo_git"))


def rama_valida(value) -> bool:
    if not isinstance(value, str) or not BRANCH_RE.match(value):
        return False
    return not any(x in value for x in ("..", "//", "/.", "@{")) and not value.endswith(("/", ".lock", "."))


def ref_de(pid: int, iid: int) -> str:
    return f"{pid}:{iid}"


def parse_ref(value) -> Optional[tuple]:
    found = REF_RE.match(value) if isinstance(value, str) else None
    return (int(found.group(1)), int(found.group(2))) if found else None


def proyecto_de_remote(url: str) -> Optional[str]:
    found = REMOTE_RE.match((url or "").strip())
    if not found:
        return None
    path = found.group(1)
    return path if PROJECT_PATH_RE.match(path) else None


def texto_limpio(value: str, limit: int) -> str:
    return CONTROL_RE.sub("", value or "")[:limit]


def _str(value, limit: int = 300) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _url(value, prefix: str) -> str:
    return value[:500] if isinstance(value, str) and value.startswith(prefix) else ""


def _persona(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {"username": _str(raw.get("username"), 80), "nombre": _str(raw.get("name"), 120)}


_BOT_USER_RE = re.compile(r"^(?:project_\d+_bot|group_\d+_bot)", re.IGNORECASE)


def _autor_es_bot(raw) -> bool:
    raw = raw if isinstance(raw, dict) else {}
    if raw.get("bot") is True:
        return True
    u = _str(raw.get("username"), 80)
    return bool(u.endswith("_bot") or _BOT_USER_RE.match(u))


def _parse_firma(firma: str) -> tuple:
    parts = (firma or "").split("|", 2)
    sha = parts[0] if parts else ""
    max_n = 0
    if len(parts) > 1 and isinstance(parts[1], str) and parts[1].isdigit():
        max_n = int(parts[1])
    reviewers = parts[2] if len(parts) > 2 else ""
    return sha, max_n, reviewers


def actividad_despausa(firma_guardada: str, firma_actual: str, notas_otros: list) -> bool:
    """Commit o reviewers nuevos despausan; una nota de persona solo si supera el id guardado (borrar no cuenta)."""
    g_sha, g_max, g_rev = _parse_firma(firma_guardada)
    a_sha, _, a_rev = _parse_firma(firma_actual)
    if g_sha != a_sha or g_rev != a_rev:
        return True
    max_person = max((n["id"] for n in notas_otros), default=0)
    return max_person > g_max


def glab_env() -> dict:
    # GITLAB_TOKEN pisa el login de `glab auth`: el subprocess usa solo la sesión guardada.
    env = {k: v for k, v in os.environ.items() if k not in ("GITLAB_TOKEN", "GITLAB_ACCESS_TOKEN", "OAUTH_TOKEN")}
    env["NO_COLOR"] = "1"
    return env


def git_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
    return env


async def _exec(args: list, stdin: Optional[bytes], cwd: Optional[str], env: dict, timeout: float) -> tuple:
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=cwd, env=env, stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin), timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        raise GitlabError(504, "tardó demasiado")
    return proc.returncode, out, err


async def real_runner(args: list, stdin: Optional[bytes] = None, cwd: Optional[str] = None) -> tuple:
    return await _exec(args, stdin, cwd, glab_env(), TIMEOUT)


async def real_local(args: list, cwd: Optional[str] = None) -> tuple:
    return await _exec(args, None, cwd, git_env(), GIT_TIMEOUT)


def _error_from(rc: int, out: bytes, err: bytes) -> GitlabError:
    text = (err or b"").decode(errors="replace")
    found = STATUS_RE.search(text)
    status = int(found.group(1)) if found else 0
    message = ""
    try:
        body = json.loads(out or b"null")
        raw = body.get("message") or body.get("error") if isinstance(body, dict) else None
        message = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False) if raw else ""
    except ValueError:
        pass
    message = texto_limpio(message, 200)
    if status == 401:
        return GitlabError(502, "glab no tiene sesión en GitLab: corré `glab auth login` en la notebook")
    if status == 404:
        return GitlabError(404, message or "GitLab no lo encontró")
    if 400 <= status < 500:
        return GitlabError(409, f"GitLab no te deja: {message}" if message else "GitLab rechazó el pedido")
    if "executable file not found" in text or rc == 127:
        return GitlabError(503, "No encuentro glab en la notebook")
    return GitlabError(502, "GitLab no responde")


class Gitlab:
    """`glab api` como subprocess: rutas solo desde enteros validados, cuerpo JSON por stdin."""

    def __init__(self, runner: Optional[Runner] = None, glab_bin: Optional[str] = None, cwd: Optional[Path] = None,
                 host: str = "gitlab.com"):
        self.runner = runner
        self.glab_bin = glab_bin
        self.cwd = cwd
        self.host = host or "gitlab.com"
        self.url_prefix = f"https://{self.host}/"
        self._vuelo: dict = {}
        self._tope: Optional[tuple] = None

    def _semaforo(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self._tope is None or self._tope[0] is not loop:
            self._tope = (loop, asyncio.Semaphore(PEDIDOS_A_LA_VEZ))
        return self._tope[1]

    def _bin(self) -> str:
        if self.glab_bin:
            return self.glab_bin
        found = shutil.which("glab")
        if found:
            return found
        fallback = Path.home() / ".local" / "bin" / "glab"
        return str(fallback) if fallback.is_file() else "glab"

    def disponible(self) -> bool:
        if self.runner is not None:
            return True
        b = self._bin()
        return b != "glab" or Path(b).is_file()

    async def _ejecutar(self, method: str, path: str, body: Optional[dict] = None) -> bytes:
        if method not in ("GET", "POST", "PUT") or not API_PATH_RE.match(path) or ".." in path or "%2e" in path.lower():
            raise GitlabError(400, "pedido inválido")
        args = [self._bin(), "api", "--hostname", self.host, "-X", method]
        stdin = None
        if body is not None:
            args += ["-H", "Content-Type: application/json", "--input", "-"]
            stdin = json.dumps(body, ensure_ascii=False).encode()
        args.append(path)
        runner = self.runner or real_runner
        try:
            async with self._semaforo():
                rc, out, err = await runner(args, stdin, str(self.cwd) if self.cwd else None)
        except FileNotFoundError:
            raise GitlabError(503, "No encuentro glab en la notebook")
        except OSError:
            raise GitlabError(502, "No pude ejecutar glab")
        if rc != 0:
            raise _error_from(rc, out, err)
        return out

    async def call(self, method: str, path: str, body: Optional[dict] = None):
        out = await self._ejecutar(method, path, body)
        try:
            return json.loads(out or b"null")
        except ValueError:
            raise GitlabError(502, "GitLab devolvió algo ilegible")

    async def texto(self, path: str, max_bytes: int = 512_000) -> str:
        """GET de una respuesta que no es JSON (el log de un job): se queda con los últimos `max_bytes`.

        El tope se aplica DESPUÉS de leer: `glab api` no tiene una opción para pedir solo la cola (solo `-H` para
        headers y no hay garantía de que el endpoint del trace respete `Range`), así que el log se lee entero
        y recién después se recorta. Solo el tiempo queda acotado, por el TIMEOUT del runner (25 s); la
        memoria no tiene tope de lectura propio."""
        out = await self._ejecutar("GET", path)
        return (out or b"")[-max_bytes:].decode(errors="replace")

    async def get(self, path: str):
        """GET que comparte el pedido con otro idéntico que ya está en vuelo."""
        loop = asyncio.get_running_loop()
        hit = self._vuelo.get(path)
        if hit is None or hit.get_loop() is not loop or hit.done():
            hit = loop.create_task(self.call("GET", path))
            self._vuelo[path] = hit
            hit.add_done_callback(lambda t, p=path: self._vuelo.pop(p, None) if self._vuelo.get(p) is t else None)
            hit.add_done_callback(lambda t: t.cancelled() or t.exception())
        return await asyncio.shield(hit)


def _pipeline(raw, url_prefix: str) -> dict:
    if not isinstance(raw, dict) or not _int(raw.get("id")):
        return {"estado": "sin", "id": 0, "url": ""}
    return {"estado": PIPE_ESTADOS.get(raw.get("status"), "sin"), "id": _int(raw.get("id")),
            "url": _url(raw.get("web_url"), url_prefix)}


def firma_actividad(mr: dict, notas: dict) -> str:
    sha = _str(mr.get("sha"), 40)
    max_otro = max((n["id"] for n in notas["otros"]), default=0)
    reviewers = sorted(_persona(r)["username"] for r in mr.get("reviewers") or [] if isinstance(r, dict)
                       and _persona(r)["username"])
    return f"{sha}|{max_otro}|{','.join(reviewers)}"


def _notas_resumen(discussions, yo: str) -> dict:
    sin_resolver = 0
    otros: list = []
    for disc in discussions if isinstance(discussions, list) else []:
        notes = [n for n in (disc.get("notes") or []) if isinstance(n, dict)] if isinstance(disc, dict) else []
        if any(n.get("resolvable") and not n.get("resolved") for n in notes):
            sin_resolver += 1
        for n in notes:
            if n.get("system") or not _int(n.get("id")):
                continue
            if _autor_es_bot(n.get("author")):
                continue
            autor = _persona(n.get("author"))
            if autor["username"] and autor["username"] != yo:
                otros.append({"id": _int(n.get("id")), "autor": autor, "cuerpo": _str(n.get("body"), 400)})
    otros.sort(key=lambda n: n["id"])
    return {"sin_resolver": sin_resolver, "otros": otros}


def _titulo_draft(titulo: str, draft: bool) -> str:
    base = DRAFT_RE.sub("", titulo or "").strip() or (titulo or "").strip()
    return f"Draft: {base}"[:MAX_TITULO] if draft else base[:MAX_TITULO]


CREADOS_V = 2


class MrsService:
    def __init__(self, directory: Path, gitlab: Optional[Gitlab] = None, local: Optional[Runner] = None,
                 board: Callable[[], Optional[dict]] = lambda: None, presente: Callable[[], bool] = lambda: False,
                 avisar: Optional[Callable] = None, clock: Callable[[], float] = time.monotonic,
                 repos_fijos: Optional[Callable[[], list]] = None, flow_bin: Optional[str] = None,
                 ajustes: Optional[MrsAjustes] = None):
        self.path = directory / STATE_FILE
        self.ajustes = ajustes
        if gitlab is not None:
            self.gitlab = gitlab
        elif ajustes is not None:
            self.gitlab = Gitlab(cwd=directory, host=ajustes.host, glab_bin=ajustes.glab_bin or None)
        else:
            self.gitlab = Gitlab(cwd=directory)
        self.local = local
        self.board = board
        self.presente = presente
        self.avisar = avisar
        self.clock = clock
        if repos_fijos is not None:
            self.repos_fijos = repos_fijos
        elif ajustes is not None and ajustes.repos:
            self.repos_fijos = lambda: list(ajustes.repos)
        else:
            self.repos_fijos = lambda: []
        self.flow_bin = flow_bin
        self.items: list = []
        self.error = ""
        self.actualizado = 0.0
        self.actualizado_wall = 0
        self.version = 0
        self.listeners: list = []
        self._notas: dict = {}
        self._cwd_cache: dict = {}
        self._proyectos: dict = {}
        self._inflight: Optional[asyncio.Task] = None
        self._wake: Optional[asyncio.Event] = None
        self.estado = self._load()
        self.find_transcript: Optional[Callable[[str], Optional[Path]]] = None
        self.enviar: Optional[Callable[[str, str, str], Awaitable]] = None
        self.enviar_origen: Optional[Callable[[str, str, str, str], Awaitable]] = None
        self._pedidos: dict = {}
        self._transcript_scan_cache: dict = {}

    @property
    def habilitado(self) -> bool:
        return self.ajustes is not None

    def _yo(self) -> str:
        return self.ajustes.usuario if self.ajustes else ""

    def _yo_id(self) -> int:
        return self.ajustes.usuario_id if self.ajustes else 0

    def _equipo(self) -> dict:
        return self.ajustes.equipo if self.ajustes else {}

    def _exigir_habilitado(self) -> None:
        if not self.habilitado:
            raise GitlabError(503, "Los MRs no están configurados")

    # ---------- estado persistido ----------
    def _load(self) -> dict:
        base = {"sembrado": False, "fallados": [], "aprobadores": {}, "avisado_nota": {}, "visto": {}, "revisiones": [],
                "pausas": {}, "creados": {}, "creados_v": CREADOS_V}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return base
        if not isinstance(raw, dict):
            return base
        out = dict(base)
        out["sembrado"] = raw.get("sembrado") is True
        out["fallados"] = [x for x in raw.get("fallados", []) if _int(x)][-300:] if isinstance(raw.get("fallados"), list) else []
        out["revisiones"] = [x for x in raw.get("revisiones", []) if parse_ref(x)][-200:] if isinstance(raw.get("revisiones"), list) else []
        for key in ("avisado_nota", "visto"):
            src = raw.get(key)
            out[key] = {k: v for k, v in src.items() if parse_ref(k) and _int(v)} if isinstance(src, dict) else {}
        src = raw.get("aprobadores")
        out["aprobadores"] = {k: [u for u in v if isinstance(u, str)][:50] for k, v in src.items()
                              if parse_ref(k) and isinstance(v, list)} if isinstance(src, dict) else {}
        pausas: list = []
        src = raw.get("pausas")
        if isinstance(src, dict):
            for k, v in src.items():
                if not parse_ref(k) or not isinstance(v, dict):
                    continue
                firma = _str(v.get("firma"), 400)
                if not firma:
                    continue
                pausas.append((k, {"firma": firma, "desde": _int(v.get("desde"))}))
        out["pausas"] = dict(pausas[-300:])
        creados: list = []
        src = raw.get("creados")
        if isinstance(src, dict):
            for k, v in src.items():
                if not parse_ref(k) or not isinstance(v, str) or not SESSION_RE.match(v):
                    continue
                creados.append((k, v))
        out["creados"] = dict(creados[-300:]) if raw.get("creados_v") == CREADOS_V else {}
        return out

    def _save(self) -> None:
        try:
            private_write(self.path, json.dumps(self.estado, ensure_ascii=False))
        except OSError as exc:
            log.warning("no pude guardar el estado de MRs: %s", type(exc).__name__)

    # ---------- refresco ----------
    def disponible(self) -> bool:
        return self.habilitado and self.gitlab.disponible()

    def viejo(self) -> bool:
        return not self.actualizado or self.clock() - self.actualizado >= INTERVALO_PRESENTE

    async def refresh(self) -> None:
        if self._inflight is None or self._inflight.done():
            self._inflight = asyncio.get_running_loop().create_task(self._refresh())
        await asyncio.shield(self._inflight)

    def refresh_soon(self) -> None:
        if self._inflight is None or self._inflight.done():
            self._inflight = asyncio.get_running_loop().create_task(self._refresh())

    @property
    def refrescando(self) -> bool:
        return self._inflight is not None and not self._inflight.done()

    async def run(self) -> None:
        if not self.habilitado:
            return
        self._wake = asyncio.Event()
        while True:
            try:
                await self.refresh()
            except Exception as exc:
                log.warning("refresco de MRs falló: %s", type(exc).__name__)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), INTERVALO_PRESENTE if self.presente() else INTERVALO_AUSENTE)
            except asyncio.TimeoutError:
                pass

    def nudge(self) -> None:
        """Alguien abrió la app: si el caché está viejo, el timer no espera a su próximo turno."""
        if self._wake is not None and self.viejo():
            self._wake.set()

    def _notificar(self) -> None:
        self.version += 1
        for listener in list(self.listeners):
            try:
                listener(self.version)
            except Exception as exc:
                log.warning("listener de MRs falló: %s", type(exc).__name__)

    async def _refresh(self) -> None:
        if not self.habilitado:
            self.actualizado = self.clock()
            self._notificar()
            return
        try:
            items, listados = await self._fetch()
        except GitlabError as exc:
            self.error = exc.detail
            log.info("MRs: %s", exc.detail)
        else:
            self.error = ""
            await self._eventos(items, listados)
            self.items = items
            self.actualizado_wall = int(time.time())
        self.actualizado = self.clock()
        self._notificar()

    async def _fetch(self) -> tuple:
        mios, revision = await asyncio.gather(
            self.gitlab.get(f"merge_requests?scope=created_by_me&state=opened&per_page={MAX_MRS}"),
            self.gitlab.get(f"merge_requests?scope=all&state=opened&reviewer_id={self._yo_id()}&per_page={MAX_MRS}"))
        base: dict = {}
        for rol, lista in (("autor", mios), ("revisor", revision)):
            for mr in lista if isinstance(lista, list) else []:
                pid, iid = _int(mr.get("project_id")) if isinstance(mr, dict) else 0, _int(mr.get("iid")) if isinstance(mr, dict) else 0
                if not pid or not iid:
                    continue
                key = ref_de(pid, iid)
                if key in base:
                    base[key]["roles"].add(rol)
                else:
                    base[key] = {"mr": mr, "roles": {rol}}
        sem = asyncio.Semaphore(CONCURRENCIA)

        async def one(key: str, entry: dict) -> Optional[dict]:
            async with sem:
                try:
                    return await self._armar(key, entry["mr"], entry["roles"])
                except GitlabError as exc:
                    log.info("MR %s: %s", key, exc.detail)
                    return None

        listados = set(base)
        armados = await asyncio.gather(*(one(k, e) for k, e in base.items()))
        self._notas = {k: v for k, v in self._notas.items() if k in listados}
        out = [i for i in armados if i]
        out.sort(key=lambda i: i["actualizado"], reverse=True)
        return out, listados

    async def _armar(self, key: str, mr: dict, roles: set) -> dict:
        pid, iid = _int(mr.get("project_id")), _int(mr.get("iid"))
        base = f"projects/{pid}/merge_requests/{iid}"
        cached = self._notas.get(key)
        # El conteo de notas viene en la lista: con él se pide el detalle, las aprobaciones y los hilos a la vez.
        count = _int(mr.get("user_notes_count"))
        hilos = cached is None or cached[0] != count
        pedidos = [self.gitlab.get(base), self.gitlab.get(f"{base}/approvals")]
        if hilos:
            pedidos.append(self.gitlab.get(f"{base}/discussions?per_page=100"))
        detalle, aprob, *disc = await asyncio.gather(*pedidos)
        detalle = detalle if isinstance(detalle, dict) else mr
        aprob = aprob if isinstance(aprob, dict) else {}
        if hilos:
            cached = (count, _notas_resumen(disc[0], self._yo()))
            self._notas[key] = cached
        return self._item(detalle, aprob, cached[1], roles)

    def _item(self, mr: dict, aprob: dict, notas: dict, roles: set) -> dict:
        pid, iid = _int(mr.get("project_id")), _int(mr.get("iid"))
        key = ref_de(pid, iid)
        refs = mr.get("references") if isinstance(mr.get("references"), dict) else {}
        full = _str(refs.get("full"), 300)
        repo = full.rsplit("!", 1)[0] if "!" in full else ""
        por = [_persona(a.get("user")) for a in aprob.get("approved_by") or [] if isinstance(a, dict)]
        visto = self.estado["visto"].get(key, 0)
        user = mr.get("user") if isinstance(mr.get("user"), dict) else {}
        firma = firma_actividad(mr, notas)
        return {
            "ref": key, "project_id": pid, "iid": iid, "repo": repo, "repo_corto": repo.rsplit("/", 1)[-1],
            "titulo": _str(mr.get("title"), MAX_TITULO), "rama": _str(mr.get("source_branch"), 200),
            "target": _str(mr.get("target_branch"), 200), "rol": "autor" if "autor" in roles else "revisor",
            "autor": _persona(mr.get("author")), "draft": mr.get("draft") is True,
            "conflictos": mr.get("has_conflicts") is True, "estado_merge": _str(mr.get("detailed_merge_status"), 40),
            "puede_mergear": user.get("can_merge") is True, "sha": _str(mr.get("sha"), 40),
            "pipeline": _pipeline(mr.get("head_pipeline"), self.gitlab.url_prefix),
            "aprobaciones": {"dadas": len(por), "requeridas": _int(aprob.get("approvals_required")),
                             "faltan": _int(aprob.get("approvals_left")), "por": por,
                             "yo": aprob.get("user_has_approved") is True,
                             "puedo": aprob.get("user_can_approve") is True},
            "reviewers": [_persona(r) for r in mr.get("reviewers") or [] if isinstance(r, dict)],
            "hilos_sin_resolver": notas["sin_resolver"],
            "comentarios_nuevos": sum(1 for n in notas["otros"] if n["id"] > visto) if key in self.estado["visto"] else 0,
            "url": _url(mr.get("web_url"), self.gitlab.url_prefix), "actualizado": _str(mr.get("updated_at"), 40),
            "creado": _str(mr.get("created_at"), 40), "firma": firma, "pausado": key in self.estado["pausas"],
        }

    # ---------- avisos ----------
    async def _eventos(self, items: list, listados: set) -> None:
        est = self.estado
        sembrar = not est["sembrado"]
        eventos: list = []
        revisiones = set(est["revisiones"])
        for item in items:
            key = item["ref"]
            notas = (self._notas.get(key) or (0, {"otros": []}))[1]["otros"]
            if key in est["pausas"] and actividad_despausa(est["pausas"][key]["firma"], item["firma"], notas):
                del est["pausas"][key]
            item["pausado"] = key in est["pausas"]
            max_otro = max((n["id"] for n in notas), default=0)
            nuevo = key not in est["avisado_nota"] and key not in est["aprobadores"]
            if key not in est["visto"]:
                est["visto"][key] = max_otro or 1
            if item["rol"] == "autor":
                pipe = item["pipeline"]
                if pipe["estado"] == "fallo" and pipe["id"] not in est["fallados"]:
                    est["fallados"] = (est["fallados"] + [pipe["id"]])[-300:]
                    eventos.append(("Falló el pipeline", f"{item['repo_corto']} !{item['iid']}: {item['titulo']}", key))
                antes = set(est["aprobadores"].get(key, []))
                ahora = [p for p in item["aprobaciones"]["por"] if p["username"] and p["username"] != self._yo()]
                for p in ahora:
                    if p["username"] not in antes and not nuevo:
                        eventos.append((f"{p['nombre'] or p['username']} aprobó tu MR",
                                        f"{item['repo_corto']} !{item['iid']}: {item['titulo']}", key))
                est["aprobadores"][key] = [p["username"] for p in ahora]
                ultimo = est["avisado_nota"].get(key)
                if ultimo is not None:
                    frescas = [n for n in notas if n["id"] > ultimo]
                    if frescas:
                        n = frescas[-1]
                        extra = f" (+{len(frescas) - 1})" if len(frescas) > 1 else ""
                        eventos.append((f"{n['autor']['nombre'] or n['autor']['username']} comentó en tu MR{extra}",
                                        f"!{item['iid']}: {n['cuerpo'][:160]}", key))
                if max_otro or ultimo is None:
                    est["avisado_nota"][key] = max(max_otro, ultimo or 0) or 1
            else:
                if key not in revisiones:
                    revisiones.add(key)
                    autor = item["autor"]["nombre"] or item["autor"]["username"]
                    eventos.append((f"{autor} te pidió revisión", f"{item['repo_corto']} !{item['iid']}: {item['titulo']}", key))
        est["revisiones"] = sorted(r for r in revisiones if r in listados)[-200:]
        for bucket in ("aprobadores", "avisado_nota", "visto", "pausas", "creados"):
            est[bucket] = {k: v for k, v in est[bucket].items() if k in listados}
        est["sembrado"] = True
        self._save()
        if sembrar or self.avisar is None:
            return
        for titulo, cuerpo, key in eventos:
            try:
                await self.avisar(titulo, cuerpo, key)
            except Exception as exc:
                log.warning("aviso de MR falló: %s", type(exc).__name__)

    # ---------- lectura ----------
    def item(self, pid: int, iid: int) -> Optional[dict]:
        key = ref_de(pid, iid)
        return next((i for i in self.items if i["ref"] == key), None)

    async def listado(self) -> dict:
        sesiones = await self.sesiones() if self.habilitado else {}
        return {"items": self.items, "error": self.error, "actualizado": self.actualizado_wall,
                "refrescando": self.refrescando, "disponible": self.disponible(), "habilitado": self.habilitado,
                "sesiones": sesiones, "version": self.version}

    async def detalle(self, pid: int, iid: int) -> dict:
        item = await self._exigir(pid, iid)
        base = f"projects/{pid}/merge_requests/{iid}"
        pipe_previo = item["pipeline"]["id"]

        async def jobs_de(pipeline_id: int):
            return await self.gitlab.get(f"projects/{pid}/pipelines/{pipeline_id}/jobs?per_page=100") if pipeline_id else None

        mr, disc, diffs, raw = await asyncio.gather(
            self.gitlab.get(base), self.gitlab.get(f"{base}/discussions?per_page=100"),
            self.gitlab.get(f"{base}/diffs?per_page=100"), jobs_de(pipe_previo))
        mr = mr if isinstance(mr, dict) else {}
        pipe = _pipeline(mr.get("head_pipeline"), self.gitlab.url_prefix) if mr else item["pipeline"]
        jobs = []
        if pipe["id"] != pipe_previo:
            raw = await jobs_de(pipe["id"])
        if pipe["id"]:
            for j in raw if isinstance(raw, list) else []:
                if not isinstance(j, dict) or not _int(j.get("id")):
                    continue
                status = j.get("status")
                jobs.append({"id": _int(j.get("id")), "nombre": _str(j.get("name"), 120),
                             "etapa": _str(j.get("stage"), 80), "estado": PIPE_ESTADOS.get(status, "sin"),
                             "status": _str(status, 30), "url": _url(j.get("web_url"), self.gitlab.url_prefix),
                             "duracion": round(j["duration"]) if isinstance(j.get("duration"), (int, float)) else 0,
                             "reintentable": status in ("failed", "canceled"), "permitido_fallar": j.get("allow_failure") is True})
        hilos = []
        actividad = []
        resumen = _notas_resumen(disc, self._yo())
        for d in disc if isinstance(disc, list) else []:
            for n in (d.get("notes") or []) if isinstance(d, dict) else []:
                if isinstance(n, dict) and n.get("system") and _int(n.get("id")):
                    actividad.append({"id": _int(n.get("id")), "autor": _persona(n.get("author")),
                                      "cuerpo": _str(n.get("body"), MAX_ACTIVIDAD_TEXTO), "fecha": _str(n.get("created_at"), 40),
                                      "mio": _persona(n.get("author"))["username"] == self._yo()})
            notes = [n for n in (d.get("notes") or []) if isinstance(n, dict) and not n.get("system")] if isinstance(d, dict) else []
            if not notes:
                continue
            pos = notes[0].get("position") if isinstance(notes[0].get("position"), dict) else {}
            hilos.append({
                "id": _str(d.get("id"), 64), "resoluble": any(n.get("resolvable") for n in notes),
                "resuelto": all(n.get("resolved") for n in notes if n.get("resolvable")) and any(n.get("resolvable") for n in notes),
                "archivo": _str(pos.get("new_path") or pos.get("old_path"), 300),
                "linea": _int(pos.get("new_line") or pos.get("old_line")),
                "notas": [{"id": _int(n.get("id")), "autor": _persona(n.get("author")),
                           "cuerpo": _str(n.get("body"), 5000), "fecha": _str(n.get("created_at"), 40),
                           "mio": _persona(n.get("author"))["username"] == self._yo()} for n in notes],
            })
        archivos = []
        total = 0
        for f in diffs if isinstance(diffs, list) else []:
            if not isinstance(f, dict):
                continue
            diff = f.get("diff") if isinstance(f.get("diff"), str) else ""
            cabe = max(0, min(MAX_DIFF_ARCHIVO, MAX_DIFF_TOTAL - total))
            total += min(len(diff), cabe)
            archivos.append({"path": _str(f.get("new_path"), 400), "viejo": _str(f.get("old_path"), 400),
                             "nuevo": f.get("new_file") is True, "borrado": f.get("deleted_file") is True,
                             "renombrado": f.get("renamed_file") is True, "diff": diff[:cabe],
                             "truncado": len(diff) > cabe or f.get("too_large") is True})
        key = ref_de(pid, iid)
        max_otro = max((n["id"] for n in resumen["otros"]), default=0)
        if max_otro and self.estado["visto"].get(key, 0) < max_otro:
            self.estado["visto"][key] = max_otro
            self._save()
        item = dict(item, comentarios_nuevos=0, hilos_sin_resolver=resumen["sin_resolver"], pipeline=pipe)
        if mr:
            item.update(sha=_str(mr.get("sha"), 40), conflictos=mr.get("has_conflicts") is True,
                        draft=mr.get("draft") is True, titulo=_str(mr.get("title"), MAX_TITULO),
                        creado=_str(mr.get("created_at"), 40))
        return {**item, "descripcion": _str(mr.get("description"), MAX_DESCRIPCION), "jobs": jobs, "hilos": hilos,
                "actividad": actividad[-MAX_ACTIVIDAD:], "archivos": archivos}

    async def _exigir(self, pid: int, iid: int) -> dict:
        self._exigir_habilitado()
        if not self.actualizado:
            await self.refresh()
        item = self.item(pid, iid)
        if item is None:
            raise GitlabError(404, "Ese MR no está en tu lista")
        return item

    # ---------- acciones ----------
    async def aprobar(self, pid: int, iid: int, aprobar: bool) -> None:
        await self._exigir(pid, iid)
        await self.gitlab.call("POST", f"projects/{pid}/merge_requests/{iid}/{'approve' if aprobar else 'unapprove'}")
        self.refresh_soon()

    async def comentar(self, pid: int, iid: int, texto: str) -> None:
        await self._exigir(pid, iid)
        body = texto_limpio(texto, MAX_COMENTARIO).strip()
        if not body:
            raise GitlabError(422, "El comentario está vacío")
        await self.gitlab.call("POST", f"projects/{pid}/merge_requests/{iid}/notes", {"body": body})
        self.refresh_soon()

    async def reintentar(self, pid: int, iid: int, pipeline_id: int = 0, job_id: int = 0) -> None:
        await self._exigir(pid, iid)
        mr = await self.gitlab.get(f"projects/{pid}/merge_requests/{iid}")
        pipe = _pipeline(mr.get("head_pipeline") if isinstance(mr, dict) else None, self.gitlab.url_prefix)
        if not pipe["id"]:
            raise GitlabError(409, "Ese MR no tiene pipeline")
        if pipeline_id:
            if pipeline_id != pipe["id"]:
                raise GitlabError(409, "El pipeline cambió, actualizá")
            await self.gitlab.call("POST", f"projects/{pid}/pipelines/{pipe['id']}/retry")
        else:
            jobs = await self.gitlab.get(f"projects/{pid}/pipelines/{pipe['id']}/jobs?per_page=100")
            job = next((j for j in jobs if isinstance(j, dict) and j.get("id") == job_id), None) if isinstance(jobs, list) else None
            if job is None:
                raise GitlabError(409, "Ese job no es del pipeline del MR")
            if job.get("status") not in ("failed", "canceled"):
                raise GitlabError(409, "Ese job no falló")
            await self.gitlab.call("POST", f"projects/{pid}/jobs/{job_id}/retry")
        self.refresh_soon()

    async def reviewers(self, pid: int, iid: int, usernames: list) -> None:
        item = await self._exigir(pid, iid)
        if item["rol"] != "autor":
            raise GitlabError(403, "Solo cambiás reviewers en tus MRs")
        eq = self._equipo()
        limpios = list(dict.fromkeys(usernames))
        if any(u not in eq for u in limpios):
            raise GitlabError(422, "reviewer inválido")
        ids = [eq[u][0] for u in limpios]
        await self.gitlab.call("PUT", f"projects/{pid}/merge_requests/{iid}", {"reviewer_ids": ids})
        self.refresh_soon()

    async def draft(self, pid: int, iid: int, draft: bool) -> None:
        item = await self._exigir(pid, iid)
        if item["rol"] != "autor":
            raise GitlabError(403, "Solo marcás draft tus MRs")
        mr = await self.gitlab.get(f"projects/{pid}/merge_requests/{iid}")
        titulo = _str(mr.get("title") if isinstance(mr, dict) else "", MAX_TITULO) or item["titulo"]
        await self.gitlab.call("PUT", f"projects/{pid}/merge_requests/{iid}", {"title": _titulo_draft(titulo, draft)})
        self.refresh_soon()

    async def pausar(self, pid: int, iid: int, pausar: bool) -> dict:
        item = await self._exigir(pid, iid)
        key = ref_de(pid, iid)
        if pausar:
            self.estado["pausas"][key] = {"firma": item["firma"], "desde": int(time.time())}
        else:
            self.estado["pausas"].pop(key, None)
        item["pausado"] = pausar
        self._save()
        self._notificar()
        return {"pausado": pausar}

    async def mergear(self, pid: int, iid: int, sha: str) -> None:
        await self._exigir(pid, iid)
        if not SHA_RE.match(sha or ""):
            raise GitlabError(422, "sha inválido")
        await self.gitlab.call("PUT", f"projects/{pid}/merge_requests/{iid}/merge", {"sha": sha})
        self.refresh_soon()

    async def cerrar(self, pid: int, iid: int) -> None:
        item = await self._exigir(pid, iid)
        if item["rol"] != "autor":
            raise GitlabError(403, "Solo cerrás tus MRs")
        await self.gitlab.call("PUT", f"projects/{pid}/merge_requests/{iid}", {"state_event": "close"})
        self.refresh_soon()

    async def pedir_actualizacion(self, pid: int, iid: int) -> dict:
        """Le manda a la sesión del MR un mensaje fijo (sin texto del usuario) si está esperando que le hablen."""
        await self._exigir(pid, iid)
        if self.enviar is None:
            raise GitlabError(503, "No puedo hablarle a las sesiones")
        key = ref_de(pid, iid)
        agentes = {a.get("session_id"): a for a in self._agentes() if a.get("session_id") and a.get("pane_id")}
        asociadas = await self.sesiones()
        sids = [sid for sid, ref in asociadas.items() if ref == key and sid in agentes]
        if not sids:
            raise GitlabError(404, "Ese MR no tiene una sesión abierta")
        dueno = (self.estado.get("creados") or {}).get(key)
        sids.sort(key=lambda sid: (sid != dueno, agentes[sid].get("status") not in ("idle", "done")))
        agente = agentes[sids[0]]
        status = agente.get("status")
        if status == "working":
            raise GitlabError(409, "La sesión está trabajando: esperá a que termine.")
        if status == "blocked":
            raise GitlabError(409, "La sesión espera una aprobación tuya en la terminal.")
        if status not in ("idle", "done"):
            raise GitlabError(409, "La sesión no está esperando todavía.")
        ahora = self.clock()
        previo = self._pedidos.get(key)
        if previo is not None and ahora - previo < PEDIDO_ESPERA:
            raise GitlabError(409, "Ya se lo pediste hace un momento.")
        self._pedidos[key] = ahora
        try:
            await self.enviar(agente["pane_id"], MENSAJE_ACTUALIZAR.format(iid=iid), f"mr-{pid}-{iid}-{uuid.uuid4().hex[:12]}")
        except Exception:
            self._pedidos.pop(key, None)
            raise
        return {"ok": True}

    def _ordenar_asociadas(self, key: str, sids: list, agentes: dict) -> list:
        dueno = (self.estado.get("creados") or {}).get(key)
        return sorted(sids, key=lambda sid: (sid != dueno, agentes[sid].get("status") not in ("idle", "done")))

    async def destinos(self, pid: int, iid: int) -> dict:
        """Sesiones de Claude abiertas a las que se puede mandar algo de este MR; la sugerida es la asociada a su rama."""
        await self._exigir(pid, iid)
        key = ref_de(pid, iid)
        agentes = {a["session_id"]: a for a in self._agentes()
                   if a.get("session_id") and a.get("pane_id") and a.get("kind", "claude") == "claude"}
        asociadas = await self.sesiones()
        sids_asoc = [sid for sid, ref in asociadas.items() if ref == key and sid in agentes]
        orden = self._ordenar_asociadas(key, sids_asoc, agentes)
        resto = [sid for sid in agentes if sid not in sids_asoc]
        sesiones = []
        for sid in [*orden, *resto]:
            a = agentes[sid]
            partes = [p for p in str(a.get("cwd") or "").split("/") if p]
            corta = "/".join(partes[-2:])
            sesiones.append({"session_id": sid, "pane_id": a["pane_id"],
                             "nombre": envio_sesion.linea_unica(a.get("title") or "", 120) or corta or "Sesión",
                             "status": _str(a.get("status"), 30), "carpeta_corta": corta,
                             "asociada": sid in sids_asoc})
        return {"sugerida": orden[0] if orden else None, "sesiones": sesiones}

    def _agente_libre(self, session_id: str) -> dict:
        if self.enviar_origen is None:
            raise GitlabError(503, "No puedo hablarle a las sesiones")
        agente = envio_sesion.agente_por_sesion(self.board(), session_id)
        if agente is None or not agente.get("pane_id"):
            raise GitlabError(404, "Esa sesión ya no está abierta")
        status = agente.get("status")
        if status == "working":
            raise GitlabError(409, "La sesión está trabajando. Reintentá cuando termine.")
        if status == "blocked":
            raise GitlabError(409, "La sesión espera una aprobación tuya en la terminal. Reintentá cuando la resuelvas.")
        if status not in ("idle", "done"):
            raise GitlabError(409, "La sesión no está esperando todavía. Reintentá en un momento.")
        return agente

    async def _enviar_unico(self, clave: tuple, agente: dict, texto: str, ident: str, origen: str) -> dict:
        ahora = self.clock()
        previo = self._pedidos.get(clave)
        if previo is not None and ahora - previo < PEDIDO_ESPERA:
            raise GitlabError(409, "Ya se lo mandaste hace un momento.")
        self._pedidos[clave] = ahora
        if len(self._pedidos) > 200:
            for k in [k for k, t in self._pedidos.items() if ahora - t >= PEDIDO_ESPERA][:100]:
                self._pedidos.pop(k, None)
        try:
            await self.enviar_origen(agente["pane_id"], texto, ident, origen)
        except Exception:
            self._pedidos.pop(clave, None)
            raise
        return {"ok": True}

    async def mandar_job(self, pid: int, iid: int, job_id: int, session_id: str) -> dict:
        """Le manda a una sesión la cola del log de un job fallido del pipeline de cabeza. Solo recibe ids."""
        item = await self._exigir(pid, iid)
        agente = self._agente_libre(session_id)
        mr = await self.gitlab.call("GET", f"projects/{pid}/merge_requests/{iid}")
        mr = mr if isinstance(mr, dict) else {}
        pipe = _pipeline(mr.get("head_pipeline"), self.gitlab.url_prefix)
        jobs = await self.gitlab.call("GET", f"projects/{pid}/pipelines/{pipe['id']}/jobs?per_page=100") if pipe["id"] else []
        job = next((j for j in jobs if isinstance(j, dict) and _int(j.get("id")) == job_id), None) if isinstance(jobs, list) else None
        if job is None or job.get("status") not in ("failed", "canceled"):
            raise GitlabError(409, "Ese job no falló en el último pipeline")
        traza = await self.gitlab.texto(f"projects/{pid}/jobs/{job_id}/trace", LOG_BYTES)
        unica = envio_sesion.linea_unica
        cab = MENSAJE_JOB.format(iid=iid, url=_url(job.get("web_url"), self.gitlab.url_prefix) or item["url"])
        ficha = (f"job «{unica(_str(job.get('name'), 300), 120)}» (etapa {unica(_str(job.get('stage'), 300), 120)}) "
                 f"en la rama {unica(_str(mr.get('source_branch'), 300) or item['rama'], 120)}")
        origen = "log del job en GitLab (nombre, etapa, rama y últimas líneas)"

        def armar(tope: int) -> str:
            libre = max(0, tope - len(ficha) - len(envio_sesion.SEP))
            cuerpo = ficha + envio_sesion.SEP + envio_sesion.cola(traza, LOG_LINEAS, libre)
            return cab + envio_sesion.bloque_datos(origen, cuerpo, tope)

        tope = LOG_CHARS
        texto = armar(tope)
        if len(texto) > MAX_TEXT:
            tope = max(0, tope - (len(texto) - MAX_TEXT) - 1)
            texto = armar(tope)
        return await self._enviar_unico((ref_de(pid, iid), f"job:{job_id}", session_id), agente, texto,
                                        f"mrj-{pid}-{iid}-{job_id}-{uuid.uuid4().hex[:8]}", "mr-job")

    async def mandar_hilo(self, pid: int, iid: int, hilo_id: str, session_id: str) -> dict:
        """Le manda a una sesión los últimos comentarios de un hilo del MR. Solo recibe ids."""
        item = await self._exigir(pid, iid)
        if not isinstance(hilo_id, str) or not HILO_RE.match(hilo_id):
            raise GitlabError(422, "hilo inválido")
        agente = self._agente_libre(session_id)
        disc = await self.gitlab.call("GET", f"projects/{pid}/merge_requests/{iid}/discussions/{hilo_id}")
        notas = [n for n in (disc.get("notes") or []) if isinstance(n, dict) and not n.get("system")] \
            if isinstance(disc, dict) and isinstance(disc.get("notes"), list) else []
        if not notas:
            raise GitlabError(404, "Ese comentario ya no está")
        unica = envio_sesion.linea_unica
        primera = notas[0]
        pos = primera.get("position") if isinstance(primera.get("position"), dict) else {}
        archivo = unica(_str(pos.get("new_path") or pos.get("old_path"), 300), 120)
        linea = _int(pos.get("new_line") or pos.get("old_line"))
        donde = f"{archivo}:{linea}" if archivo and linea else archivo
        autor = unica(_persona(primera.get("author"))["username"], 120) or "alguien"
        url = f"{item['url']}#note_{_int(primera.get('id'))}" if item["url"] else ""
        ultimas = notas[-HILO_NOTAS:]
        prefijos = [f"{unica(_persona(n.get('author'))['username'], 120)}: " for n in ultimas]
        libre = HILO_CHARS - sum(len(p) for p in prefijos) - len(envio_sesion.SEP) * (len(ultimas) - 1)
        tope_nota = max(40, min(HILO_NOTA_CHARS, libre // len(ultimas)))
        cuerpo = envio_sesion.SEP.join(p + unica(redactar_basico(_str(n.get("body"), 5000)), tope_nota) for p, n in zip(prefijos, ultimas))
        ficha = f"comentario de {autor}" + (f" sobre {donde}" if donde else "") + envio_sesion.SEP
        texto = MENSAJE_HILO.format(iid=iid, url=url) + envio_sesion.bloque_datos(
            "comentarios del MR en GitLab", ficha + cuerpo, HILO_CHARS + len(ficha))
        return await self._enviar_unico((ref_de(pid, iid), f"hilo:{hilo_id}", session_id), agente, texto,
                                        f"mrh-{pid}-{iid}-{uuid.uuid4().hex[:12]}", "mr-hilo")

    # ---------- git local ----------
    async def _git(self, args: list, cwd: str) -> Optional[str]:
        runner = self.local or real_local
        try:
            rc, out, _err = await runner(["git", *args], cwd)
        except (OSError, GitlabError):
            return None
        return out.decode(errors="replace") if rc == 0 else None

    async def _repo_de(self, cwd: str) -> Optional[dict]:
        """(toplevel, proyecto de GitLab, rama actual) del cwd; caché corto porque la rama cambia."""
        now = self.clock()
        hit = self._cwd_cache.get(cwd)
        if hit and now - hit[0] < CWD_TTL:
            return hit[1]
        info = None
        if cwd and Path(cwd).is_absolute() and Path(cwd).is_dir():
            top = await self._git(["rev-parse", "--show-toplevel"], cwd)
            top = (top or "").strip()
            if top:
                remote, rama = await asyncio.gather(self._git(["remote", "get-url", "origin"], top),
                                                    self._git(["branch", "--show-current"], top))
                proyecto = proyecto_de_remote(remote or "")
                rama = (rama or "").strip()
                if proyecto:
                    info = {"path": top, "proyecto": proyecto, "rama": rama if rama_valida(rama) else ""}
        self._cwd_cache[cwd] = (now, info)
        if len(self._cwd_cache) > 200:
            self._cwd_cache.pop(next(iter(self._cwd_cache)))
        return info

    def _agentes(self):
        for ws in (self.board() or {}).get("workspaces", []):
            for tab in ws.get("tabs", []):
                for agent in tab.get("agents", []):
                    yield agent

    def _registrar_creador(self, ref: str, session_id: str) -> None:
        if not parse_ref(ref) or not SESSION_RE.match(session_id or ""):
            return
        creados = self.estado.setdefault("creados", {})
        if ref in creados:
            return
        creados[ref] = session_id
        if len(creados) > 300:
            for k in list(creados.keys())[:-300]:
                creados.pop(k, None)
        self._save()

    def _mr_creados_transcript(self, path: Path) -> list[tuple[str, int]]:
        try:
            stat = path.stat()
        except OSError:
            return []
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        cached = self._transcript_scan_cache.get(key)
        if cached is not None:
            return cached
        found = mr_creados_glab_en_transcript(path)
        self._transcript_scan_cache[key] = found
        while len(self._transcript_scan_cache) > 200:
            self._transcript_scan_cache.pop(next(iter(self._transcript_scan_cache)))
        return found

    async def _inferir_creadores_transcript(self) -> None:
        find = self.find_transcript
        if not find:
            return
        creados = self.estado.setdefault("creados", {})
        pending = {i["ref"] for i in self.items if i["ref"] and i["ref"] not in creados}
        if not pending:
            return
        by_repo_iid = {(i["repo"].lower(), i["iid"]): i["ref"] for i in self.items if i["ref"] in pending}
        changed = False
        for agent in self._agentes():
            if not pending:
                break
            sid = agent.get("session_id")
            if not isinstance(sid, str) or not sid:
                continue
            path = find(sid)
            if path is None:
                continue
            for proyecto, iid in self._mr_creados_transcript(path):
                ref = by_repo_iid.get((proyecto.lower(), iid))
                if ref and ref in pending:
                    creados[ref] = sid
                    pending.discard(ref)
                    changed = True
        if changed:
            self._save()

    async def sesiones(self) -> dict:
        if not self.items:
            return {}
        await self._inferir_creadores_transcript()
        por_rama = {(i["repo"].lower(), i["rama"]): i["ref"] for i in self.items if i["repo"] and i["rol"] == "autor"}
        for i in self.items:
            por_rama.setdefault((i["repo"].lower(), i["rama"]), i["ref"])
        creados = self.estado.get("creados") or {}
        board_sids = {a.get("session_id") for a in self._agentes() if a.get("session_id")}
        out = {}
        sids = []
        con_sid = [(a.get("session_id"), a.get("cwd")) for a in self._agentes() if a.get("session_id")]
        cwds = list(dict.fromkeys(c for _s, c in con_sid if isinstance(c, str) and c))
        infos = dict(zip(cwds, await asyncio.gather(*(self._repo_de(c) for c in cwds))))
        for sid, cwd in con_sid:
            sids.append(sid)
            if not isinstance(cwd, str) or not cwd:
                continue
            info = infos.get(cwd)
            if not info or not info["rama"]:
                continue
            ref = por_rama.get((info["proyecto"].lower(), info["rama"]))
            if not ref:
                continue
            dueno = creados.get(ref)
            if dueno and dueno in board_sids:
                if sid == dueno:
                    out[sid] = ref
            else:
                out[sid] = ref
        # Creadora de un MR de otra rama (p. ej. lo armó desde otro worktree): se lo asocia aunque su cwd no coincida
        # ni sea un repo. Dentro de un proyecto gana el mayor iid; entre proyectos, el de actualizado más reciente
        # (items) y, si empatan o no hay fecha, el de mayor iid.
        por_ref = {i["ref"]: i for i in self.items if i["ref"]}
        for sid in sids:
            if sid in out:
                continue
            mejor_por_proyecto: dict = {}
            for ref, creador in creados.items():
                item = por_ref.get(ref)
                if creador != sid or not item:
                    continue
                actual = mejor_por_proyecto.get(item["project_id"])
                if actual is None or item["iid"] > actual["iid"]:
                    mejor_por_proyecto[item["project_id"]] = item
            if mejor_por_proyecto:
                out[sid] = max(mejor_por_proyecto.values(), key=lambda i: (i.get("actualizado") or "", i["iid"]))["ref"]
        return out

    async def repos(self) -> list:
        vistos: dict = {}
        cwds = [a.get("cwd") for a in self._agentes() if isinstance(a.get("cwd"), str)]
        for cwd in [*cwds, *(str(p) for p in self.repos_fijos())]:
            info = await self._repo_de(cwd)
            if info and info["path"] not in vistos:
                vistos[info["path"]] = info
        return list(vistos.values())

    async def ramas(self, repo: str) -> list:
        out = await self._git(["for-each-ref", "--sort=-committerdate", "--count=60", "--format=%(refname:short)",
                               "refs/heads"], repo)
        return [r for r in (out or "").splitlines() if rama_valida(r)]

    async def _repo_permitido(self, repo: str) -> dict:
        if not isinstance(repo, str) or not repo:
            raise GitlabError(422, "repo inválido")
        found = next((r for r in await self.repos() if r["path"] == repo), None)
        if found is None:
            raise GitlabError(422, "Ese repo no está en la lista")
        return found

    async def _proyecto(self, path: str) -> dict:
        hit = self._proyectos.get(path)
        if hit:
            return hit
        raw = await self.gitlab.get(f"projects/{quote(path, safe='')}")
        if not isinstance(raw, dict) or not _int(raw.get("id")):
            raise GitlabError(502, "GitLab no devolvió el proyecto")
        default = raw.get("default_branch")
        info = {"id": _int(raw["id"]), "default": default if rama_valida(default) else ""}
        self._proyectos[path] = info
        return info

    async def _target_flow(self, repo: str, rama: str) -> str:
        script = self.flow_bin or script_flujo_git()
        if self.flow_bin is None and not Path(script).is_file():
            return ""
        runner = self.local or real_local
        try:
            rc, out, _err = await runner([script, "--dir", repo, "target", rama], repo)
            data = json.loads(out or b"null") if rc == 0 else None
        except (OSError, ValueError, GitlabError):
            return ""
        target = data.get("target") if isinstance(data, dict) else None
        return target if rama_valida(target) else ""

    async def opciones(self, session_id: str = "") -> dict:
        repos = await self.repos()
        sugerido = {"repo": "", "rama": ""}
        if session_id:
            agent = next((a for a in self._agentes() if a.get("session_id") == session_id), None)
            info = await self._repo_de(agent.get("cwd") or "") if agent else None
            if info:
                sugerido = {"repo": info["path"], "rama": info["rama"]}
        out = []
        for r in repos:
            out.append({"path": r["path"], "proyecto": r["proyecto"], "nombre": r["proyecto"].rsplit("/", 1)[-1],
                        "rama": r["rama"], "ramas": await self.ramas(r["path"])})
        return {"repos": out, "sugerido": sugerido,
                "equipo": [{"username": u, "nombre": n} for u, (_i, n) in self._equipo().items()]}

    async def rama_info(self, repo: str, rama: str) -> dict:
        if not rama_valida(rama):
            raise GitlabError(422, "rama inválida")
        info = await self._repo_permitido(repo)
        proyecto = await self._proyecto(info["proyecto"])
        try:
            await self.gitlab.get(f"projects/{proyecto['id']}/repository/branches/{quote(rama, safe='')}")
            pusheada = True
        except GitlabError as exc:
            if exc.status != 404:
                raise
            pusheada = False
        target = await self._target_flow(info["path"], rama) or proyecto["default"]
        existente = None
        if pusheada:
            abiertos = await self.gitlab.get(
                f"projects/{proyecto['id']}/merge_requests?state=opened&source_branch={quote(rama, safe='')}")
            mr = abiertos[0] if isinstance(abiertos, list) and abiertos and isinstance(abiertos[0], dict) else None
            if mr and _int(mr.get("iid")):
                existente = {"ref": ref_de(proyecto["id"], _int(mr["iid"])), "iid": _int(mr["iid"]),
                             "url": _url(mr.get("web_url"), self.gitlab.url_prefix)}
        return {"pusheada": pusheada, "target": target if target != rama else "", "existente": existente,
                "project_id": proyecto["id"]}

    async def contexto_git(self, repo: str, rama: str, target: str) -> dict:
        if not rama_valida(rama) or not rama_valida(target):
            raise GitlabError(422, "rama inválida")
        info = await self._repo_permitido(repo)
        base = f"origin/{target}"
        if await self._git(["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{target}"], info["path"]) is None:
            base = target
        log_txt = await self._git(["log", "--no-merges", "-n", "60", "--format=- %s%n%b", f"{base}..{rama}", "--"], info["path"])
        stat = await self._git(["diff", "--stat", f"{base}...{rama}", "--"], info["path"])
        diff = await self._git(["diff", f"{base}...{rama}", "--"], info["path"])
        if log_txt is None and diff is None:
            raise GitlabError(409, "No pude leer la rama en el repo local")
        return {"proyecto": info["proyecto"], "log": (log_txt or "")[:8000], "stat": (stat or "")[:4000],
                "diff": (diff or "")[:MAX_DIFF_CLAUDE], "truncado": len(diff or "") > MAX_DIFF_CLAUDE}

    async def crear(self, repo: str, rama: str, target: str, titulo: str, descripcion: str, reviewers: list,
                    session_id: Optional[str] = None) -> dict:
        if not rama_valida(rama) or not rama_valida(target) or rama == target:
            raise GitlabError(422, "rama inválida")
        titulo = texto_limpio(titulo, MAX_TITULO + 1).strip()
        if not titulo or len(titulo) > MAX_TITULO:
            raise GitlabError(422, "título inválido")
        info = await self._repo_permitido(repo)
        proyecto = await self._proyecto(info["proyecto"])
        data = await self.rama_info(repo, rama)
        if not data["pusheada"]:
            raise GitlabError(409, "La rama no está en GitLab, pusheala primero")
        if data["existente"]:
            raise GitlabError(409, "Esa rama ya tiene un MR abierto")
        eq = self._equipo()
        rev = list(dict.fromkeys(reviewers))
        if any(u not in eq for u in rev):
            raise GitlabError(422, "reviewer inválido")
        body = {"source_branch": rama, "target_branch": target, "title": titulo,
                "description": texto_limpio(descripcion, MAX_DESCRIPCION), "assignee_id": self._yo_id(),
                "reviewer_ids": [eq[u][0] for u in rev]}
        mr = await self.gitlab.call("POST", f"projects/{proyecto['id']}/merge_requests", body)
        iid = _int(mr.get("iid")) if isinstance(mr, dict) else 0
        ref = ref_de(proyecto["id"], iid) if iid else ""
        if ref and session_id:
            self._registrar_creador(ref, session_id)
        self.refresh_soon()
        return {"ref": ref, "url": _url(mr.get("web_url"), self.gitlab.url_prefix) if isinstance(mr, dict) else ""}
