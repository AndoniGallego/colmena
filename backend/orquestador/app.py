import asyncio
import inspect
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError, model_validator

from . import auth
from .biblioteca import ITEM_ID, Library
from .sse_gzip import acepta_gzip, comprimir
from .board import BoardHub, _agents as board_agents, find_session_agent, fingerprint, session_activity
from .fondo import FondoService
from .cierre import CierreBody, CierreService, PreviewBody
from .ir_a_pc import IrAPc, IrAPcError
from .limpieza import LimpiezaService
from .memoria import Demasiado, MemoriaService
from .config import HANDOFFS_DIR, REPO_ROOT, UPLOADS_DIR, Config, bump_epoch, load_epoch, verify_pin
from .dialogos import PUSH_TEXTS, DialogService, RespuestaBody
from .hook_andokit import DetectorHookAndokit
from .estado_sesiones import EstadoSesiones
from .ganchos import ajustes as ganchos_ajustes
from .ganchos.enrutador import Enrutador
from .permisos import AuditoriaPermisos, PermisoError, PermisosService
from .digest import SESSION_ID, DigestService
from .hardening import HardeningMiddleware, build_csp
from .heap import devolver_periodicamente
from .locks import PaneLocks
from . import envio_sesion
from .mensaje import MAX_TEXT, ORIGENES_PUBLICOS, MensajeBody, MensajeService, StopBody
from .pregunta_sesion import PreguntaBody, PreguntaSesionService
from .comando_sesion import ComandoSesionBody, ComandoSesionService
from .mrs import GitlabError, MrsService
from .cambios import CambiosService
from .mrs_api import Redactor, build_router as mrs_router
from .entornos import build_router as entornos_router, docker_bin as entornos_docker_bin
from .entornos_vigia import VigiaEntornos
from .kit_vista import build_router as kit_router
from . import piezas as piezas_mod
from .replies import ReplyTracker
from .agenda import parse_hora
from .cierre_dia import CierreDiaAviso, contenido_cierre_dia, frase_resumen_cierre, ramas_sin_integrar
from .avisos import (
    KIND_RE as AVISO_KIND_RE,
    MENSAJE_RE as AVISO_MENSAJE_RE,
    MR_RE as AVISO_MR_RE,
    PANE_RE as AVISO_PANE_RE,
    PEDIDO_RE as AVISO_PEDIDO_RE,
    SESSION_RE,
)
from .colmena_pestana import pedido_desde_comando_bash
from .nueva_tarea import Worktrees
from .nueva_terminal import es_repo_colmena, validar_carpeta
from .pedidos_pestana import PedidosPestanaStore
from .avisos_origen import AvisosOrigen
from .pedido_cierre import motivo_fin_lote, resolver_objetivo, resumen_cierre, vista_cierre
from .presencia import DEVICE_RE
from .push import NOTCH_PRUEBA_KINDS, EndpointBody, PushService, SubscribeBody, TestBody, _agents, endpoint_allowed
from .orden_tablero import OrdenPestanasBody, OrdenTableroBody, PlegadasBody, SilencioBody
from .state import StateStore
from .sombra import Sombra
from .internas import predicado_de_carpetas
from .terminales import Terminales, merged_panes
from . import terminales_acciones as tacc
from .sesiones_viejas import SesionesViejas
from .uso_claude import project_key
from .subagentes import SubagentService
from .tareas import vigilar
from .transcript import DEFAULT_LIMIT, MAX_LIMIT, TranscriptService
from .enchufe import NoDisponible, NoExiste, TerminalesError, crear_terminales, sesion_propia
from . import terminal_vivo
from .guardian.lanzador import CARPETA_COPILOTO, CARPETA_GUIA, ConfigInvalida, ajustes_de, rutas_protegidas
from .copiloto import PuenteCopiloto, relacionada
from . import mostrar as mostrar_mod
from . import guia as guia_mod
from .guia import GuiaError, GuiaStore
from .guia_puente import PuenteGuia
from .reunion import TEXTO_POST_MAX, ReunionError, ReunionStore, ajustes_reunion
from .reunion_detector import Detector
from .enchufe.ids import ID_RE, valido
from .traspaso import TraspasoBody, TraspasoError, TraspasoService
from .guardado import GuardadoService, Lote
from .mudanza import MudanzaBody, MudanzaService, MudanzaStore, MudarTodasBody, RetomarBody, pid_vivo_proc, remapear_en
from .uso import UsoStore
from .uso_claude import ClaudeUso, nombres_herdr, project_key
from .statusline import ctx_dir
from .variante import proponer
from . import silencio
from . import uploads as uploads_mod
from . import voz as voz_mod

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HANDOFF_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}\.md$")
KEEPALIVE = 15.0
BUILD_ID = re.compile(r"const VERSION = '([A-Za-z0-9]{1,32})'")


def build_id(dist: Path, cache: dict) -> str:
    """Id del build que el front ya instalado compara con el suyo; el que sella vite en sw.js."""
    sw = dist / "sw.js"
    try:
        mtime = sw.stat().st_mtime_ns
        if cache.get("mtime") != mtime:
            found = BUILD_ID.search(sw.read_text(encoding="utf-8"))
            cache.update(mtime=mtime, id=found.group(1) if found else "")
    except OSError:
        return ""
    return cache.get("id", "")
MAX_BODY = 64 * 1024
MAX_LOTE = 12
PERMISSIONS_POLICY = b"microphone=(self), camera=(), geolocation=(), usb=(), payment=(), display-capture=()"
MAX_SUBSCRIBERS = 10
log = logging.getLogger("orquestador.app")
MISSING_BUILD = (
    "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>Colmena</title><body style='font-family:system-ui;background:#111;color:#ddd;padding:2rem'>"
    "<h1>Colmena</h1><p>Falta el build del frontend. Corré <code>npm run build</code> en "
    "<code>frontend/</code> y recargá.</p>"
)


class LoginBody(BaseModel):
    pin: str = Field(max_length=128)


class QuitarBody(BaseModel):
    ids: list = Field(max_length=500)


class AvisoPruebaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(..., max_length=20)
    destino: Literal["notch", "celu"]


class LeidosBody(BaseModel):
    """Una marca general (`hasta`) o los avisos de un único destino."""
    model_config = ConfigDict(extra="forbid")
    hasta: Optional[StrictInt] = Field(default=None, ge=0)
    session_id: Optional[str] = Field(default=None, pattern=SESSION_RE.pattern)
    pane_id: Optional[str] = Field(default=None, pattern=AVISO_PANE_RE.pattern)
    kind: Optional[str] = Field(default=None, pattern=AVISO_KIND_RE.pattern)
    mr: Optional[str] = Field(default=None, pattern=AVISO_MR_RE.pattern)
    mensaje: Optional[str] = Field(default=None, pattern=AVISO_MENSAJE_RE.pattern)
    endpoint: Optional[str] = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _uno_solo(self):
        if sum(v is not None for v in (self.hasta, self.session_id, self.pane_id, self.kind, self.mr, self.mensaje)) != 1:
            raise ValueError("indicá una sola condición")
        return self


class PresenciaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visible: StrictBool
    device: str = Field(pattern=DEVICE_RE.pattern)
    mirando: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9_-]{1,128}$")
    escritorio: Optional[StrictBool] = None


NUDO_PID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class NudoRespuestaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device: str = Field(..., pattern=DEVICE_RE.pattern)
    token: str = Field(..., min_length=1, max_length=64)
    resultado: dict


class NudoSalirBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device: str = Field(..., pattern=DEVICE_RE.pattern)


class AbrirEnPcBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pane_id: str = Field(..., pattern=AVISO_PANE_RE.pattern)
    titulo: str = Field("", max_length=200)


class _ReleasingStream(StreamingResponse):
    """Libera el lote pase lo que pase: si el cliente se va antes del primer byte, el generador nunca arranca."""

    def __init__(self, content, release, **kwargs):
        super().__init__(content, **kwargs)
        self._release = release

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._release()


class LimpiezaItem(BaseModel):
    tipo: Literal["tab", "workspace"]
    target_id: str = Field(..., max_length=64)


class LimpiezaPreviewBody(BaseModel):
    items: list[LimpiezaItem] = Field(..., max_length=MAX_LOTE)


class LimpiezaEjecutarItem(LimpiezaItem):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    huella: str = Field(..., max_length=128)


class GuardadoAccionBody(BaseModel):
    lote_id: str = Field(..., max_length=128)
    accion: Literal["cerrar_igual", "esperar_mas"]


class LimpiezaEjecutarBody(BaseModel):
    lote_id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    dias: Optional[int] = Field(None, ge=1, le=90)
    items: list[LimpiezaEjecutarItem] = Field(..., min_length=1, max_length=MAX_LOTE)
    sin_guardar: bool = False


class DecidirBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    accion: Literal["permitir", "rechazar", "siempre"]
    motivo: str | None = Field(None, max_length=2000)
    pin: str | None = None
    huella_regla: str | None = None


class AbrirPedidoBody(BaseModel):
    huella: str = Field("", max_length=128)
    forzar: bool = False


class EmpezarReunionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device: str = Field(..., max_length=64)
    repos: list[str] = Field(default_factory=list, max_length=60)
    todos: StrictBool = False


class TextoReunionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reunion: str = Field(..., max_length=64)
    device: str = Field(..., max_length=64)
    texto: str = Field(..., min_length=1, max_length=TEXTO_POST_MAX)


class TocarReunionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reunion: str = Field(..., max_length=64)
    linea: str = Field(..., pattern=r"^l\d{1,4}$")


class MostrarReunionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reunion: str = Field(..., max_length=64)
    device: str = Field(..., pattern=DEVICE_RE.pattern)
    pregunta: str = Field("", max_length=mostrar_mod.PREGUNTA_MOSTRAR_MAX)
    foto: dict
    imagen: dict


class ReunionIdBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reunion: str = Field(..., max_length=64)


class PedirGuiaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device: str = Field(..., pattern=DEVICE_RE.pattern)
    pregunta: str = Field(..., max_length=guia_mod.PREGUNTA_MAX)
    foto: dict
    imagen: dict


class SiguienteGuiaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device: str = Field(..., pattern=DEVICE_RE.pattern)
    foto: dict
    imagen: dict


class SalirGuiaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device: str = Field(..., pattern=DEVICE_RE.pattern)


RUTAS_CAPTURA = frozenset({"/api/reunion/mostrar", "/api/guia/pedir", "/api/guia/siguiente"})


REPOS_REUNION_MAX = 60
DEV_ESCANEO_MAX = 200


class FocusBody(BaseModel):
    tab_id: str


class SecurityMiddleware:
    def __init__(self, app, csp: str):
        self.app = app
        self.csp = csp.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        length = headers.get(b"content-length", b"0")
        chunked = b"chunked" in headers.get(b"transfer-encoding", b"")
        if scope["method"] == "POST" and scope["path"] == "/api/uploads":
            too_big = not length.isdigit() or int(length) > uploads_mod.MAX_UPLOAD + uploads_mod.MAX_BODY_OVERHEAD
        elif scope["method"] == "POST" and scope["path"] in RUTAS_CAPTURA:
            too_big = not length.isdigit() or int(length) > mostrar_mod.CUERPO_MAX or chunked
        elif scope["method"] == "POST" and scope["path"] == "/api/voz/transcribir":
            too_big = not length.isdigit() or int(length) > voz_mod.MAX_AUDIO + voz_mod.MAX_BODY_OVERHEAD
        else:
            too_big = not length.isdigit() or int(length) > MAX_BODY or chunked
        is_api = scope["path"].startswith("/api/")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                extra = [(b"content-security-policy", self.csp), (b"x-content-type-options", b"nosniff"),
                         (b"referrer-policy", b"no-referrer"), (b"permissions-policy", PERMISSIONS_POLICY)]
                existentes = {k.lower() for k, _ in message["headers"]}
                if is_api and b"cache-control" not in existentes:
                    extra.append((b"cache-control", b"no-store"))
                nuevas = [(k, v) for k, v in extra if k.lower() not in existentes]
                message = {**message, "headers": list(message["headers"]) + nuevas}
            await send(message)

        if too_big:
            await JSONResponse({"detail": "cuerpo demasiado grande"}, status_code=413)(scope, receive,
                                                                                    send_with_headers)
            return
        await self.app(scope, receive, send_with_headers)


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def carpetas_internas(data_directory: Path, carpeta_copiloto: Path, carpeta_guia: Path) -> tuple[str, ...]:
    """Carpetas de sesiones que no son trabajo de Ando: detector, Copiloto y guía (fuera del uso y de las viejas)."""
    return (project_key(data_directory / "context"), project_key(data_directory / "mrs-claude"),
            project_key(data_directory / "reunion-claude"), project_key(carpeta_copiloto),
            project_key(carpeta_guia))


REUNION_ACTIVA = frozenset({"escuchando", "pausada", "sin_pc", "llena", "terminando"})


def panes_en_carpeta(snapshot: dict, carpeta: Path) -> list[str]:
    """Los panes de Claude cuyo cwd es esa carpeta (comparando rutas reales)."""
    try:
        destino = os.path.realpath(carpeta)
    except (OSError, ValueError):
        return []
    out: list[str] = []
    for agente in snapshot.get("agents", []):
        cwd, pane = agente.get("cwd"), agente.get("pane_id")
        if not (isinstance(cwd, str) and cwd and isinstance(pane, str) and pane):
            continue
        try:
            if os.path.realpath(cwd) == destino and pane not in out:
                out.append(pane)
        except (OSError, ValueError):
            continue
    return out


def frontend_dir() -> Path:
    env = os.environ.get("ORQ_FRONTEND_DIR")
    return Path(env) if env else REPO_ROOT / "frontend" / "dist"


def _armar_mudanzas(enchufe, cierres, locks, data_directory, estados, digests, push, permisos, emit_all, spawn,
                    hub) -> MudanzaService:
    backends = {getattr(b, "nombre", ""): b for b in getattr(enchufe, "backends", ())}
    herdr = next((b for n, b in backends.items() if n != "guardian"), enchufe)

    def estado_ganchos(pane: str):
        reg = estados.estado_de(pane)
        return getattr(reg, "estado", None) if reg is not None else None

    def en_store(objs, guardar):
        def fn(viejo: str, nuevo: str) -> int:
            n = sum(remapear_en(o, viejo, nuevo) for o in objs())
            if n:
                guardar()
            return n
        return fn

    def en_permisos(viejo: str, nuevo: str) -> int:
        n = 0
        for ped in list(permisos._por_id.values()):
            if ped.pane_id == viejo:
                ped.pane_id = nuevo
                n += 1
        return n

    def en_estados(viejo: str, nuevo: str) -> int:
        return 1 if estados._registros.pop(viejo, None) is not None else 0

    remapeos = [
        ("avisos", en_store(lambda: (push.avisos.items,), push.avisos._save)),
        ("permisos", en_permisos),
        ("estados", en_estados),
    ]

    def al_mudar(entry: dict) -> None:
        emit_all("mudanza", {"pane_viejo": entry.get("pane_viejo"), "pane_nuevo": entry.get("pane_nuevo"),
                             "session_id": entry.get("session_id")})
        spawn(hub.refresh(force=True))

    return MudanzaService(
        herdr=herdr,
        guardian=lambda: backends.get("guardian"),
        cierre=cierres,
        locks=locks,
        store=MudanzaStore(data_directory / "mudanzas.json"),
        estado_ganchos=estado_ganchos,
        transcript=digests.find,
        pid_vivo=pid_vivo_proc,
        remapeos=remapeos,
        al_mudar=al_mudar,
    )


def create_app(cfg: Config, secret: bytes, state: StateStore, hub: Optional[BoardHub] = None,
               digests: Optional[DigestService] = None,
               dist: Optional[Path] = None, handoffs_dir: Path = HANDOFFS_DIR,
               uploads_dir: Path = UPLOADS_DIR, push: Optional[PushService] = None,
               env_pane_id: Optional[str] = None, dialog_sleep=asyncio.sleep,
               library: Optional[Library] = None, voz: Optional[voz_mod.VozService] = None,
               memoria: Optional[MemoriaService] = None,
               mrs: Optional[MrsService] = None, redactor: Optional[Redactor] = None,
               entrada_interna: bool = True, enchufe=None,
               ganchos_socket: Optional[Path] = None,
               recarga_socket: Optional[Path] = None, nudo_socket: Optional[Path] = None, entornos_runner=None,
               kit_opts: Optional[dict] = None, piezas: Optional[list] = None,
               piezas_opts: Optional[dict] = None, piezas_paquete: str = "orquestador.piezas",
               reunion_opts: Optional[dict] = None) -> FastAPI:
    # entrada_interna=False: sin Host/CIDR/Tailscale/Hardening aquí; envolver con entrada.pila_para.
    if enchufe is None:
        enchufe = crear_terminales(cfg)
    digests = digests or DigestService(cfg.projects_dir())
    fondo = FondoService(digests.find)
    hub = hub or BoardHub(enchufe, digests, fondo=fondo)
    hub.pinned = frozenset(w.strip().casefold() for w in cfg.protected_workspaces)
    data_directory = state.path.parent
    env_pane = sesion_propia() if env_pane_id is None else env_pane_id
    epoch = [load_epoch(data_directory)]
    silencio.configurar(data_directory / silencio.MARCA)

    uso = UsoStore(data_directory)
    reunion_opts = reunion_opts or {}
    carpeta_copiloto = Path(reunion_opts.get("carpeta") or CARPETA_COPILOTO)
    carpeta_guia = Path(reunion_opts.get("carpeta_guia") or CARPETA_GUIA)
    # Las sesiones del detector, del Copiloto y de la guía no son trabajo de Ando: fuera del uso y de las viejas.
    internas = carpetas_internas(data_directory, carpeta_copiloto, carpeta_guia)
    destinos_internos = {os.path.realpath(c) for c in (carpeta_copiloto, carpeta_guia)}
    hub.interna = predicado_de_carpetas(destinos_internos)
    uso_claude = ClaudeUso(cfg.projects_dir(), data_directory, excluir=internas, limits_dir=ctx_dir())
    memoria = memoria or MemoriaService(cfg, data_directory)
    locks = PaneLocks()
    hub.env_pane = env_pane
    terminales = Terminales(enchufe, hub.terminals, lambda: {p for p in (hub.self_pane_id, env_pane) if p},
                            writes=lambda: cfg.terminales_escritura is True)
    terminales.interna = hub.interna
    traspasos = TraspasoService(enchufe, state, handoffs_dir, locks, cfg.protected_workspaces, lambda: {p for p in (hub.self_pane_id, env_pane) if p},
                                lambda event, data: emit_all(event, data))

    mensajes = MensajeService(enchufe, state, lambda: hub.self_pane_id, uploads_dir, locks, cfg.protected_workspaces,
                              lambda: {p for p in (hub.self_pane_id, env_pane) if p})
    pregunta_sesion = PreguntaSesionService(hub.current, digests, mensajes, cfg.protected_workspaces,
                                            lambda: {p for p in (hub.self_pane_id, env_pane) if p},
                                            lambda: hub.refresh(force=True))
    worktrees_nt = Worktrees(data_directory)
    cierres = CierreService(enchufe, state, locks, lambda: {p for p in (hub.self_pane_id, env_pane) if p},
                            cfg.protected_workspaces, lambda: hub.refresh(force=True), fondo=fondo,
                            worktrees=worktrees_nt)
    guardado = GuardadoService(cierres, enchufe, locks, call_later=lambda d, fn: asyncio.get_running_loop().call_later(d, fn),
                               emit=lambda event, data: emit_all(event, data), spawn=lambda coro: spawn(coro))
    limpieza = LimpiezaService(enchufe, hub, lambda: {p for p in (hub.self_pane_id, env_pane) if p},
                               cfg.protected_workspaces, data_directory, lambda: cfg.limpieza_dias)
    transcripts = TranscriptService(digests)
    subagentes = SubagentService(digests.projects_dir, digests.find)
    library = library or Library(cfg, data_directory, secret, epoch=lambda: epoch[0], uploads_dir=uploads_dir)
    transcripts.library = library
    tasks: set = set()
    loop_ref: list = []

    def spawn(coro) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return
        task = loop.create_task(coro)
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        vigilar(task, getattr(coro, "__qualname__", None) or repr(coro))

    def lib_observer(previous, board) -> None:
        changed = library.on_board(previous, board)

        if changed:
            spawn(asyncio.to_thread(library.index_sessions, changed))

    def lib_broadcast(ids: list) -> None:
        for queue in list(hub.subscribers):
            hub._offer(queue, ("biblioteca", {"nuevos": ids}))

    def lib_listener(ids: list) -> None:
        if loop_ref:
            loop_ref[0].call_soon_threadsafe(lib_broadcast, ids)

    library.listeners.append(lib_listener)
    hub.observers.append(lib_observer)
    hub.observers.append(memoria.on_board)
    uploads_mod.cleanup(uploads_dir)
    voz = voz or voz_mod.VozService(cfg.voz_habilitada, cfg.voz_modelo, data_directory)
    push = push or PushService(
        data_directory,
        call_later=lambda delay, fn: asyncio.get_running_loop().call_later(delay, fn),
    )
    push.silenciada = lambda sid: sid in state.silenciadas()
    hub.observers.append(push.on_board)

    def avisos_broadcast(entry: dict) -> None:
        for queue in list(hub.subscribers):
            hub._offer(queue, ("aviso", {"id": entry["id"]}))

    push.listeners.append(avisos_broadcast)

    def emit_all(event: str, data: dict) -> None:
        for queue in list(hub.subscribers):
            hub._offer(queue, (event, data))

    from .nudo import NudoStore, validar_respuesta
    nudo = NudoStore(lambda queue, item: hub._offer(queue, item))

    from .notas import NotasStore
    notas = NotasStore(data_directory)

    pedidos_pestana = PedidosPestanaStore()
    pedidos_pestana.on_change(lambda pid, estado: emit_all("pedido_pestana", {"id": pid, "estado": estado}))
    avisos_origen = AvisosOrigen(lambda body: mensajes.execute(body), lambda: hub.board, spawn)
    pedidos_pestana.on_descarte(avisos_origen.al_descarte)
    hub.observers.append(avisos_origen.al_tablero)

    push.leidos_listeners.append(lambda tags: emit_all("avisos_leidos", {"tags": tags}))

    hub.observers.append(guardado.on_board)
    hub.replies = ReplyTracker(state)
    limiter = auth.LoginLimiter()
    dialogos = DialogService(enchufe, state, locks, transcripts, lambda: {p for p in (hub.self_pane_id, env_pane) if p},
                             limiter, cfg.pin, verify_pin, lambda: hub.refresh(force=True), sleep=dialog_sleep)
    push.describe_blocked = dialogos.push_text
    estados = EstadoSesiones(hook_instalado=DetectorHookAndokit())
    if hasattr(enchufe, "conectar_estados"):
        enchufe.conectar_estados(estados)
    hub.estados = estados
    estados.al_cierre_diferido = hub.reaplicar
    hub.fuente = lambda: ganchos_ajustes.fuente_estado(cfg)

    from .recarga import RecargaService, ServidorRecarga, sesiones_desde_board

    recarga_svc = RecargaService(
        sesiones=lambda: sesiones_desde_board(hub.board),
        mandar=enchufe.mandar_prompt,
        marcar_silencio=silencio.marcar,
        self_pane=lambda: hub.self_pane_id,
        protected_panes=lambda: {p for p in (hub.self_pane_id, env_pane) if p},
    )

    def _recarga_al_estado(pane_id: str, _evento: str) -> None:
        spawn(recarga_svc.al_cambio(pane_id))

    def _recarga_al_board(_previous, _board) -> None:
        spawn(recarga_svc.al_cambio(None))

    estados.observadores.append(_recarga_al_estado)
    hub.observers.append(_recarga_al_board)

    def avisar_pedido(p) -> None:
        board = hub.board or {}
        name = _agents(board).get(p.pane_id, ("Sesión", {}))[0]
        texto = PUSH_TEXTS.get(p.herramienta, "Quiere usar una herramienta")
        push.avisar_bloqueo(p.session_id, name, texto)

    def estado_pane(pane_id: str) -> str | None:
        board = hub.board
        if not board:
            return None
        agentes = _agents(board)
        if pane_id not in agentes:
            return None
        agent = agentes[pane_id][1]
        fuente = ganchos_ajustes.fuente_estado(cfg)
        status = agent.get("status") if fuente == "herdr" else agent.get("status_herdr")
        return status if isinstance(status, str) else None

    permisos = PermisosService(
        AuditoriaPermisos(data_directory / "permisos.jsonl"),
        locks,
        espera=lambda: ganchos_ajustes.permisos_espera(cfg),
        desde_app=lambda: ganchos_ajustes.permisos_desde_app(cfg),
        avisar=avisar_pedido,
        al_cambiar=lambda: None,
        estado_pane=estado_pane,
    )

    def permisos_broadcast() -> None:
        for queue in list(hub.subscribers):
            hub._offer(queue, ("permisos", {"pedidos": permisos.listar()}))

    permisos.al_cambiar = permisos_broadcast
    dialogos.permisos = permisos

    _permisos_observer_tasks: set = set()

    def permisos_observer(_previous, board) -> None:
        if not board or board.get("terminales") == "sin_conexion":
            return
        panes_abiertos = {
            item.get("pane_id")
            for item in permisos.listar()
            if item.get("estado") == "abierto" and item.get("pane_id")
        }
        if not panes_abiertos:
            return
        agentes = _agents(board)
        fuente = ganchos_ajustes.fuente_estado(cfg)
        for pane in panes_abiertos:
            if pane not in agentes:
                status = None
            else:
                agent = agentes[pane][1]
                status = agent.get("status") if fuente == "herdr" else agent.get("status_herdr")
                if not isinstance(status, str):
                    continue
            coro = permisos.observar_herdr(pane, status)
            tarea = asyncio.create_task(coro)
            _permisos_observer_tasks.add(tarea)
            tarea.add_done_callback(_permisos_observer_tasks.discard)
            vigilar(tarea, getattr(coro, "__qualname__", None) or repr(coro))

    hub.observers.append(permisos_observer)
    def _nombre_sesion_permiso(pane_id: str, session_id: str) -> tuple[str, str]:
        board = hub.board
        if board:
            nombres = nombres_herdr(board)
            for agent in board_agents(board):
                if agent.get("pane_id") == pane_id and agent.get("session_id") == session_id:
                    nom = nombres.get(session_id) or agent.get("label") or pane_id
                    return nom, pane_id
        return pane_id, pane_id

    mudanzas = _armar_mudanzas(enchufe, cierres, locks, data_directory, estados, digests, push, permisos, emit_all,
                               spawn, hub)
    if mrs is None:
        from .mrs import MrsService, ajustes_desde_config
        mrs = MrsService(data_directory, ajustes=ajustes_desde_config(cfg))
    mrs.board = lambda: hub.board
    mrs.presente = push.presencia.present
    mrs.avisar = push.dispatch_mr
    mrs.find_transcript = digests.find

    async def mrs_enviar(pane_id: str, texto: str, ident: str) -> None:
        try:
            await mensajes.execute(MensajeBody(id=ident, pane_id=pane_id, texto=texto, origen="pedido-mr", destino="MR"))
        except TraspasoError as exc:
            raise GitlabError(exc.status, exc.detail)

    mrs.enviar = mrs_enviar
    redactor = redactor or Redactor(cfg, uso, data_directory, data_directory / "mrs-claude")
    cambios_svc = CambiosService()

    def mrs_broadcast(version: int) -> None:
        for queue in list(hub.subscribers):
            hub._offer(queue, ("mrs", {"version": version}))

    mrs.listeners.append(mrs_broadcast)
    dist = dist if dist is not None else frontend_dir()
    build_cache: dict = {}
    sombra = Sombra(data_directory)
    hub.sombra = sombra

    app = FastAPI(title="Colmena", docs_url=None, redoc_url=None, openapi_url=None)
    cupos_vivo = terminal_vivo.Cupos()
    app.state.cupos_vivo = cupos_vivo
    app.state.library = library
    app.state.notas = notas
    app.state.locks = locks
    app.state.terminales = terminales
    app.state.dialogos = dialogos
    app.state.secret = secret
    app.state.hub = hub
    app.state.state = state
    app.state.limpieza = limpieza
    app.state.guardado = guardado
    app.state.memoria = memoria
    app.state.mrs = mrs
    app.state.enchufe = enchufe
    app.state.sombra = sombra
    app.state.estados = estados
    app.state.uso_claude = uso_claude
    app.state.recarga = recarga_svc
    app.state.nudo = nudo
    app.state.permisos = permisos
    app.state.mudanzas = mudanzas
    app.state.ir_a_pc = IrAPc()
    app.state.epoch = lambda: epoch[0]

    def vivo_habilitado() -> bool:
        return isinstance(cfg.terminales, dict) and cfg.terminales.get("vivo") is True

    def _tamano_vivo() -> tuple[int, int]:
        try:
            aj = ajustes_de(cfg.guardian if isinstance(cfg.guardian, dict) else None, os.environ)
            return (aj.columnas, aj.filas)
        except ConfigInvalida:
            return (120, 40)

    async def _abrir_vivo_default(sid: str):
        if not hasattr(enchufe, "abrir_vivo"):
            raise NoDisponible("el guardián no está configurado")
        return await enchufe.abrir_vivo(sid, tamano=_tamano_vivo())

    async def _abrir_vivo(sid: str):
        fn = getattr(app.state, "abrir_vivo", None)
        if fn is not None:
            return await fn(sid)
        return await _abrir_vivo_default(sid)

    if entrada_interna:
        app.add_middleware(HardeningMiddleware, app_origin=cfg.app_origin)
        app.add_middleware(auth.TailscaleUserMiddleware, user=cfg.tailscale_user, estricto=False)
        app.add_middleware(auth.CidrMiddleware, networks=auth.parse_networks(cfg.allowed_cidrs))
    app.add_middleware(SecurityMiddleware, csp=build_csp(cfg.viewer_origin))
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    public = APIRouter(prefix="/api")
    api = APIRouter(prefix="/api", dependencies=[Depends(auth.require_session)])

    @public.post("/login")
    async def login(body: LoginBody, request: Request):
        ip = request.client.host if request.client else "?"
        async with limiter.gate:
            wait = limiter.retry_after(ip)
            if wait:
                return JSONResponse({"detail": "demasiados intentos"}, status_code=429,
                                    headers={"Retry-After": str(wait)})
            if not await asyncio.to_thread(verify_pin, body.pin, cfg.pin):
                limiter.fail(ip)
                log.warning("login fallido desde %s", ip)
                raise HTTPException(status_code=401, detail="PIN incorrecto")
            limiter.ok(ip)
        log.info("login ok desde %s", ip)
        response = JSONResponse({"ok": True})
        response.set_cookie(auth.COOKIE_NAME, auth.sign_session(secret, epoch=epoch[0]), max_age=auth.COOKIE_TTL,
                            httponly=True, samesite="strict", path="/", secure=True)
        return response

    @api.post("/logout")
    async def logout():
        tacciones.ventana.cerrar()
        response = JSONResponse({"ok": True})
        response.delete_cookie(auth.COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
        return response

    @api.post("/sessions/revoke-all")
    async def revoke_all():
        epoch[0] = bump_epoch(data_directory)
        tacciones.ventana.cerrar()
        response = JSONResponse({"ok": True})
        response.delete_cookie(auth.COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
        return response

    @api.get("/me")
    async def me():
        return {"ok": True}

    @api.get("/board")
    async def board():
        try:
            return await hub.current()
        except (TerminalesError, OSError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"Las terminales no responden: {exc}")

    @api.get("/tablero/orden")
    async def tablero_orden_get():
        return {"orden": state.orden_tablero(), "pestanas": state.orden_pestanas(), "plegadas": state.plegadas(),
                "silenciadas": state.silenciadas()}

    @api.put("/tablero/orden")
    async def tablero_orden_put(body: OrdenTableroBody):
        orden = body.orden
        state.set_orden_tablero(orden)
        emit_all("orden_tablero", {"orden": orden})
        if not orden:
            had = bool(state.orden_pestanas())
            state.clear_orden_pestanas()
            if had:
                emit_all("orden_pestanas", {"grupo": "", "orden": []})
        return {"ok": True}

    @api.put("/tablero/orden-pestanas")
    async def tablero_orden_pestanas_put(body: OrdenPestanasBody):
        grupo = body.grupo
        orden = body.orden
        state.set_orden_pestanas_grupo(grupo, orden)
        emit_all("orden_pestanas", {"grupo": grupo, "orden": orden})
        return {"ok": True}

    @api.put("/tablero/plegadas")
    async def tablero_plegadas_put(body: PlegadasBody):
        plegadas = body.plegadas
        state.set_plegadas(plegadas)
        emit_all("plegadas", {"plegadas": plegadas})
        return {"ok": True}

    @api.put("/sesiones/{sid}/silencio")
    async def sesion_silencio_put(sid: str, body: SilencioBody):
        if not SESSION_RE.match(sid):
            raise HTTPException(status_code=400, detail="sid inválido")
        state.set_silenciada(sid, body.on)
        emit_all("silenciadas", {"silenciadas": state.silenciadas()})
        return {"ok": True}

    @api.post("/sesiones/{sid}/ir-a-pc")
    async def sesion_ir_a_pc(sid: str):
        if not SESSION_RE.match(sid):
            raise HTTPException(status_code=400, detail="sid inválido")
        try:
            agent = find_session_agent(await hub.current(), sid)
        except (TerminalesError, OSError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"Las terminales no responden: {exc}")
        if not agent:
            raise HTTPException(status_code=404, detail="sesión no encontrada")
        try:
            await app.state.ir_a_pc.abrir(sid, agent.get("pane_id"), agent.get("title") or agent.get("doing") or "")
        except IrAPcError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)
        return {"ok": True}

    @api.get("/sesiones/{sid}/cambios")
    async def sesion_cambios(sid: str, refrescar: bool = False):
        if not SESSION_RE.match(sid):
            raise HTTPException(status_code=400, detail="sid inválido")
        try:
            agent = find_session_agent(await hub.current(), sid)
        except (TerminalesError, OSError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"Las terminales no responden: {exc}")
        if not agent:
            raise HTTPException(status_code=404, detail="sesión no encontrada")
        try:
            carpeta = validar_carpeta(agent.get("cwd") or "", cfg.plan_cwds_con_self())
        except TraspasoError:
            raise HTTPException(status_code=403, detail="La carpeta de la sesión no está entre las permitidas")
        return await cambios_svc.cambios(carpeta, refrescar=refrescar)

    @api.get("/events")
    async def events(request: Request, cid: str = "", pc: int = 0):
        if len(hub.subscribers) >= MAX_SUBSCRIBERS:
            raise HTTPException(status_code=503, detail="demasiados clientes conectados")
        device = cid if DEVICE_RE.match(cid) else ""
        queue = hub.subscribe()
        es_pc = bool(device) and pc == 1

        async def stream():
            last = None
            seen: dict = {}
            if device:
                push.presencia.connect(device)
            if es_pc:
                nudo.pc_conectada(device, queue)
                reunion.pc_volvio(device, queue)
                guia.pc_conectada(device, queue)
            try:
                yield sse("build", {"id": build_id(dist, build_cache)})
                try:
                    first = await hub.current()
                    last = hub.fp_for(first)
                    seen = session_activity(first)
                    yield sse("board", first)
                except (TerminalesError, OSError, ValueError):
                    pass
                while True:
                    try:
                        board = await asyncio.wait_for(queue.get(), KEEPALIVE)
                    except asyncio.TimeoutError:
                        # Evento con nombre (no comentario) para que el cliente detecte conexiones muertas.
                        yield sse("ping", {"build": build_id(dist, build_cache)})
                        continue
                    if isinstance(board, tuple):
                        yield sse(*board)
                        continue
                    fp = hub.fp_for(board)
                    if fp != last:
                        last = fp
                        yield sse("board", board)
                        current = session_activity(board)
                        for session_id, mtime in current.items():
                            if seen.get(session_id) not in (None, mtime):
                                yield sse("session", {"session_id": session_id, "mtime": mtime})
                        seen = current
            finally:
                if es_pc:
                    nudo.pc_desconectada(device, queue)
                    reunion.pc_caida(device, queue)
                    guia.pc_desconectada(device, queue)
                if device:
                    push.presencia.disconnect(device)
                hub.unsubscribe(queue)

        headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        body = stream()
        if cfg.sse_gzip and acepta_gzip(request.headers.get("accept-encoding", "")):
            body = comprimir(body)
            headers["Content-Encoding"] = "gzip"
            headers["Vary"] = "Accept-Encoding"
        return StreamingResponse(body, media_type="text/event-stream", headers=headers)

    @api.get("/sessions/{session_id}/digest")
    async def digest(session_id: str, turns: int = 8):
        result = await asyncio.to_thread(digests.summary, session_id, min(max(turns, 1), 50))
        if result is None:
            raise HTTPException(status_code=404, detail="transcript no encontrado")
        return result

    @api.post("/focus")
    async def focus(body: FocusBody):
        if not valido(ID_RE, body.tab_id):
            raise HTTPException(status_code=422, detail="tab_id inválido")
        try:
            board = await hub.current()
            workspace_id = next((w["id"] for w in board["workspaces"]
                                 if any(t["id"] == body.tab_id for t in w["tabs"])), None)
            if workspace_id is None:
                raise HTTPException(status_code=404, detail="tab desconocido")
            await enchufe.enfocar(body.tab_id)
        except NoExiste:
            raise HTTPException(status_code=404, detail="tab desconocido")
        except TerminalesError as exc:
            raise HTTPException(status_code=502, detail=f"Las terminales no responden: {exc}")
        return {"ok": True}

    @api.get("/handoffs/{name}")
    async def handoff(name: str):
        if not HANDOFF_NAME_RE.match(name):
            raise HTTPException(status_code=404, detail="brief no encontrado")
        base = handoffs_dir.resolve()
        path = (base / name).resolve()
        if path.parent != base or not path.is_file():
            raise HTTPException(status_code=404, detail="brief no encontrado")
        return {"name": name, "text": await asyncio.to_thread(path.read_text, "utf-8", "replace")}

    @api.post("/traspaso/execute")
    async def traspaso_execute(request: Request):
        try:
            body = TraspasoBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        try:
            return await traspasos.execute(body)
        except TraspasoError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)

    @api.post("/traspaso/variante")
    async def traspaso_variante(request: Request):
        try:
            body = TraspasoBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        try:
            message = proponer(body, hub.board or {"workspaces": []}, handoffs_dir)
        except TraspasoError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)
        return {"message": message}

    @api.post("/mensaje/execute")
    async def mensaje_execute(request: Request):
        try:
            body = MensajeBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        if body.origen not in ORIGENES_PUBLICOS:
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        try:
            return await mensajes.execute(body)
        except TraspasoError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)

    @api.get("/sessions/{session_id}/pregunta")
    async def session_pregunta(session_id: str):
        if not SESSION_ID.match(session_id):
            raise HTTPException(status_code=400, detail="session_id inválido")
        try:
            return JSONResponse(await pregunta_sesion.leer(session_id), headers={"Cache-Control": "no-store"})
        except TraspasoError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)

    @api.post("/sessions/{session_id}/pregunta/responder")
    async def session_pregunta_responder(session_id: str, request: Request):
        if not SESSION_ID.match(session_id):
            raise HTTPException(status_code=400, detail="session_id inválido")
        try:
            body = PreguntaBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        try:
            return await pregunta_sesion.responder(session_id, body)
        except TraspasoError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)

    @api.post("/sessions/stop")
    async def session_stop(request: Request):
        try:
            body = StopBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        try:
            return await mensajes.stop(body)
        except TraspasoError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)

    @api.post("/close/preview")
    async def close_preview(request: Request):
        try:
            body = PreviewBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        try:
            return await cierres.preview(body)
        except TraspasoError as exc:
            return JSONResponse({"detail": exc.detail, **exc.extra}, status_code=exc.status)

    @api.post("/close/execute")
    async def close_execute(request: Request):
        try:
            body = CierreBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        if body.origen in ("plan", "pedido-pestana"):
            raise HTTPException(status_code=400, detail="origen inválido")
        try:
            out = await guardado.iniciar_uno(body, sin_guardar=body.sin_guardar)
        except TraspasoError as exc:
            return JSONResponse({"detail": exc.detail, **exc.extra}, status_code=exc.status)
        return {"ok": True, "guardando": out.public()} if isinstance(out, Lote) else out

    @api.get("/mudanza")
    async def mudanza_candidatas():
        return await mudanzas.candidatas()

    async def _mudanza(request: Request, modelo, accion):
        try:
            body = modelo.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        try:
            return await accion(body)
        except TraspasoError as exc:
            return JSONResponse({"detail": exc.detail, **exc.extra}, status_code=exc.status)

    @api.post("/mudanza/execute")
    async def mudanza_execute(request: Request):
        return await _mudanza(request, MudanzaBody, mudanzas.mudar)

    @api.post("/mudanza/todas")
    async def mudanza_todas(request: Request):
        return await _mudanza(request, MudarTodasBody, mudanzas.mudar_todas)

    @api.post("/mudanza/retomar")
    async def mudanza_retomar(request: Request):
        return await _mudanza(request, RetomarBody, mudanzas.retomar)

    @api.get("/close/guardado")
    async def close_guardado_lista():
        return {"lotes": guardado.listar()}

    @api.post("/close/guardado")
    async def close_guardado_accion(request: Request):
        try:
            body = GuardadoAccionBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        try:
            return {"guardando": await guardado.accion(body.lote_id, body.accion)}
        except TraspasoError as exc:
            return JSONResponse({"detail": exc.detail, **exc.extra}, status_code=exc.status)

    @api.get("/ganchos/sombra")
    def ganchos_sombra(dias: int = Query(7, ge=1, le=30)):
        return {"dias": sombra.resumen(dias)}

    @api.get("/limpieza/candidatos")
    async def limpieza_candidatos(dias: Optional[int] = None):
        if dias is not None and not 1 <= dias <= 90:
            raise HTTPException(status_code=422, detail="dias fuera de rango")
        try:
            return await limpieza.candidatos(dias)
        except (TerminalesError, TraspasoError):
            raise HTTPException(status_code=502, detail="Las terminales no responden")

    @api.post("/limpieza/preview")
    async def limpieza_preview(request: Request):
        try:
            body = LimpiezaPreviewBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        out = []
        for item in body.items:
            try:
                out.append({"tipo": item.tipo, "target_id": item.target_id,
                            "preview": await cierres.preview(PreviewBody(tipo=item.tipo, target_id=item.target_id))})
            except TraspasoError as exc:
                out.append({"tipo": item.tipo, "target_id": item.target_id, "error": exc.detail, **exc.extra})
        return out

    @api.post("/limpieza/ejecutar")
    async def limpieza_ejecutar(request: Request):
        try:
            body = LimpiezaEjecutarBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")
        if limpieza.lote_activo:
            raise HTTPException(status_code=409, detail="ya hay una limpieza en curso")
        limpieza.lote_activo = True

        async def close_one(item: LimpiezaEjecutarItem) -> dict:
            """Sin guardado (a pedido del usuario): se cierra de a uno, como antes."""
            try:
                if not await limpieza.sigue_siendo_candidato(item.tipo, item.target_id, body.dias):
                    return {"target_id": item.target_id, "ok": False, "salteado": True,
                            "error": "Cambió, revisalo de nuevo"}
                result = await guardado.iniciar_uno(CierreBody(
                    id=item.id, tipo=item.tipo, target_id=item.target_id, huella=item.huella, origen="limpieza",
                    lote_id=body.lote_id), sin_guardar=True)
                return {"target_id": item.target_id, "ok": True, "sesiones": result.get("sesiones", [])}
            except TraspasoError as exc:
                return {"target_id": item.target_id, "ok": False, "salteado": True, "error": exc.detail}
            except (TerminalesError, ValueError):
                return {"target_id": item.target_id, "ok": False, "salteado": True, "error": "No pude revisarlo"}

        async def stream_sin_guardar():
            cerrados = salteados = 0
            try:
                for item in body.items:
                    if await request.is_disconnected():
                        break
                    task = asyncio.ensure_future(close_one(item))
                    try:
                        result = await asyncio.shield(task)
                    except asyncio.CancelledError:
                        await asyncio.gather(task, return_exceptions=True)
                        raise
                    cerrados += 1 if result["ok"] else 0
                    salteados += 0 if result["ok"] else 1
                    yield sse("item", result)
                yield sse("fin", {"cerrados": cerrados, "salteados": salteados})
            finally:
                limpieza.lote_activo = False

        def resultado_item(item: LimpiezaEjecutarItem, target: dict) -> dict:
            if target["estado"] == "cerrado":
                return {"target_id": item.target_id, "ok": True, "sesiones": (target.get("resultado") or {}).get("sesiones", [])}
            return {"target_id": item.target_id, "ok": False, "salteado": True,
                    "error": target["error"] or "No se cerró: revisalo"}

        async def stream_con_guardado():
            """Un solo lote para toda la limpieza (spec 20.3 / 16): un pedido a todas las sesiones, un timeout, y la
            hoja ve el estado "guardando" por el evento `guardando`. Nunca cierra por vencimiento: lo decide el usuario."""
            cerrados = salteados = 0
            emitidos: set = set()
            por_id = {i.id: i for i in body.items}
            lote_id = body.lote_id
            cola: asyncio.Queue = asyncio.Queue()
            tarea = None
            try:
                entradas = []
                for item in body.items:
                    try:
                        if await limpieza.sigue_siendo_candidato(item.tipo, item.target_id, body.dias):
                            entradas.append((item.id, CierreBody(
                                id=item.id, tipo=item.tipo, target_id=item.target_id, huella=item.huella,
                                origen="limpieza", lote_id=body.lote_id), item.huella))
                            continue
                        error = "Cambió, revisalo de nuevo"
                    except (TerminalesError, TraspasoError, ValueError):
                        error = "No pude revisarlo"
                    salteados += 1
                    yield sse("item", {"target_id": item.target_id, "ok": False, "salteado": True, "error": error})
                if entradas:
                    tarea = asyncio.ensure_future(guardado.iniciar_tanda(
                        lote_id, entradas, origen="limpieza", listener=lambda l: cola.put_nowait(l.public())))
                    tarea.add_done_callback(lambda t: cola.put_nowait(None))
                while entradas:
                    pub = await cola.get()
                    if pub is None:
                        if tarea.cancelled() or tarea.exception() is not None:
                            for key, _cuerpo, _h in entradas:
                                if key not in emitidos:
                                    salteados += 1
                                    yield sse("item", {"target_id": por_id[key].target_id, "ok": False, "salteado": True,
                                                       "error": "No pude revisarlo"})
                            break
                        continue
                    yield sse("guardando", pub)
                    for target in pub["targets"]:
                        if target["key"] in emitidos or target["estado"] not in ("cerrado", "error", "cancelado"):
                            continue
                        emitidos.add(target["key"])
                        result = resultado_item(por_id[target["key"]], target)
                        cerrados += 1 if result["ok"] else 0
                        salteados += 0 if result["ok"] else 1
                        yield sse("item", result)
                    if pub["terminado"]:
                        break
                yield sse("fin", {"cerrados": cerrados, "salteados": salteados})
            finally:
                if tarea is not None and not tarea.done():
                    tarea.cancel()
                actual = guardado.lote(lote_id)
                if actual is not None and not actual.terminado:
                    guardado.cancelar(lote_id)
                limpieza.lote_activo = False

        stream = stream_sin_guardar if body.sin_guardar else stream_con_guardado

        def release() -> None:
            limpieza.lote_activo = False

        return _ReleasingStream(stream(), release, media_type="text/event-stream",
                                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @api.get("/sessions/{session_id}/dialog")
    async def session_dialog(session_id: str):
        if not SESSION_ID.match(session_id):
            raise HTTPException(status_code=400, detail="session_id inválido")
        try:
            return await dialogos.read(session_id)
        except TraspasoError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)

    @api.get("/permisos")
    def permisos_listar():
        return {"pedidos": permisos.listar()}

    @api.get("/permisos/registro")
    def permisos_registro():
        board = hub.board
        nombres = nombres_herdr(board)
        items = []
        for row in permisos.auditoria.leer_clasificados():
            pane_id = row.get("pane_id")
            session_id = row.get("session_id")
            sesion = None
            if pane_id and session_id and board:
                for agent in board_agents(board):
                    if agent.get("pane_id") == pane_id and agent.get("session_id") == session_id:
                        sesion = nombres.get(session_id)
                        break
            items.append({**row, "sesion": sesion})
        return {"items": items}

    @api.post("/permisos/{pedido_id}/decidir")
    async def permisos_decidir(pedido_id: str, body: DecidirBody, request: Request):
        if body.accion == "siempre":
            try:
                await dialogos.verificar_pin(
                    body.pin, request.client.host if request.client else "?"
                )
            except TraspasoError as exc:
                headers = (
                    {"Retry-After": str(exc.extra["retry_after"])}
                    if "retry_after" in exc.extra
                    else None
                )
                return JSONResponse(
                    {"detail": exc.detail}, status_code=exc.status, headers=headers
                )
        try:
            return await permisos.decidir(
                pedido_id, body.accion, body.motivo, body.huella_regla
            )
        except PermisoError as exc:
            return JSONResponse({"detail": exc.detalle}, status_code=exc.status)
        except TraspasoError as exc:
            headers = (
                {"Retry-After": str(exc.extra["retry_after"])}
                if "retry_after" in exc.extra
                else None
            )
            return JSONResponse(
                {"detail": exc.detail}, status_code=exc.status, headers=headers
            )

    @api.post("/sessions/dialog/answer")
    async def dialog_answer(request: Request):
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(status_code=415, detail="Content-Type debe ser application/json")
        try:
            body = RespuestaBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            # Sin el detalle de pydantic: devolvería el cuerpo recibido, que puede traer el PIN.
            raise HTTPException(status_code=422, detail="cuerpo inválido")
        try:
            return await dialogos.answer(body, request.client.host if request.client else "?")
        except TraspasoError as exc:
            headers = {"Retry-After": str(exc.extra["retry_after"])} if "retry_after" in exc.extra else None
            return JSONResponse({"detail": exc.detail}, status_code=exc.status, headers=headers)

    @api.get("/terminales/{pane_id}/salida")
    async def terminal_salida(pane_id: str, rev: str = ""):
        if len(rev) > 64:
            raise HTTPException(status_code=400, detail="rev inválido")
        try:
            data = await terminales.salida(pane_id, rev)
        except TraspasoError as exc:
            headers = {"Retry-After": str(exc.extra["retry_after"])} if "retry_after" in exc.extra else None
            return JSONResponse({"detail": exc.detail}, status_code=exc.status, headers=headers)
        return JSONResponse(data, headers={"Cache-Control": "no-store"})

    def tctx(request: Request) -> tacc.Ctx:
        return tacc.Ctx(ip=request.client.host if request.client else "?",
                        user=request.headers.get("tailscale-user-login", "")[:80],
                        device=request.headers.get("user-agent", "")[:80],
                        cookie=request.cookies.get(auth.COOKIE_NAME, ""),
                        token=request.headers.get(tacc.HEADER_TOKEN, ""))

    async def tnotify(title: str, body: str, tag: str, pane_id: str = "") -> None:
        await asyncio.wait_for(push.dispatch_terminal(title, body, tag, pane_id), 3)

    def escritura() -> bool:
        # Solo un `true` de TOML: un "false" entre comillas o cualquier otro valor deja la escritura apagada.
        return cfg.terminales_escritura is True

    def sesiones_abiertas() -> set[str]:
        board = hub.board or {}
        out: set[str] = set()
        for agent in board.get("agents", []):
            sess = agent.get("agent_session") or {}
            if sess.get("kind") == "id" and isinstance(sess.get("value"), str):
                out.add(sess["value"])
        for agent in board_agents(board):
            sid = agent.get("session_id")
            if isinstance(sid, str) and sid:
                out.add(sid)
        return out

    viejas = SesionesViejas(
        cfg.projects_dir(),
        plan_cwds=lambda: cfg.plan_cwds,
        excluir_carpetas=internas,
        abiertas=sesiones_abiertas,
    )

    tacciones = tacc.TerminalActions(terminales, enchufe, locks, tacc.Audit(data_directory),
                                     escritura, tnotify,
                                     tacc.rapidos_validos(cfg.terminales_comandos_rapidos),
                                     limiter=limiter, verify=verify_pin, pin=cfg.pin,
                                     plan_cwds=lambda: cfg.plan_cwds,
                                     sesiones_viejas=viejas, estados=estados,
                                     worktrees=worktrees_nt, cierres=cierres,
                                     fijados=lambda: hub.pinned)
    app.state.tacciones = tacciones
    comando_sesion = ComandoSesionService(lambda: hub.refresh(force=True), digests, enchufe, locks, tacciones.audit,
                                          tacciones.limit, escritura, tnotify,
                                          lambda: {p for p in (hub.self_pane_id, env_pane) if p},
                                          protected_workspaces=cfg.protected_workspaces)
    app.state.comando_sesion = comando_sesion
    app.state.pedidos_pestana = pedidos_pestana
    app.state.mensajes = mensajes
    app.state.pregunta_sesion = pregunta_sesion

    def tfail(exc: TraspasoError) -> JSONResponse:
        headers = {"Retry-After": str(exc.extra["retry_after"])} if "retry_after" in exc.extra else None
        return JSONResponse({"detail": exc.detail}, status_code=exc.status, headers=headers)

    async def tbody(request: Request, model):
        # Sin el detalle de pydantic: devolvería el cuerpo recibido.
        try:
            return model.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="cuerpo inválido")

    @api.get("/terminales/config")
    async def terminales_config():
        body = dict(tacciones.config())
        body["vivo"] = vivo_habilitado()
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @api.get("/terminales/auditoria")
    async def terminales_auditoria(limit: int = 20):
        return JSONResponse(tacciones.entradas(limit), headers={"Cache-Control": "no-store"})

    @api.get("/terminales/carpetas")
    async def terminales_carpetas():
        return JSONResponse(await tacciones.carpetas_disponibles(), headers={"Cache-Control": "no-store"})

    @api.post("/terminales/preview")
    async def terminales_preview(request: Request):
        body = await tbody(request, tacc.PreviewBody)
        try:
            return JSONResponse(await tacciones.preview(body), headers={"Cache-Control": "no-store"})
        except TraspasoError as exc:
            return tfail(exc)

    @api.post("/terminales/nueva")
    async def terminales_nueva(request: Request):
        body = await tbody(request, tacc.NuevaBody)
        try:
            return JSONResponse(await tacciones.nueva(tctx(request), body), headers={"Cache-Control": "no-store"})
        except TraspasoError as exc:
            return tfail(exc)

    @api.post("/terminales/nueva-tarea")
    async def terminales_nueva_tarea(request: Request):
        body = await tbody(request, tacc.NuevaTareaBody)
        try:
            creado = await tacciones.nueva_tarea(tctx(request), body)
        except TraspasoError as exc:
            return tfail(exc)
        sin_pegar = [] if creado.get("repetido") else \
            await pegar_mensajes_nuevos(creado, f"ntm-{body.id[:40]}", body.nombre or creado["tarea"])
        out = {"ok": True, "pane_id": creado["pane_id"], "ruta": creado["ruta"], "rama": creado["rama"]}
        if sin_pegar:
            out["pegado"] = False
        return JSONResponse(out, headers={"Cache-Control": "no-store"})

    @api.post("/terminales/nueva-tarea/borrar-copia")
    async def terminales_borrar_copia(request: Request):
        body = await tbody(request, tacc.BorrarCopiaBody)
        try:
            return JSONResponse(await tacciones.borrar_copia(tctx(request), body), headers={"Cache-Control": "no-store"})
        except TraspasoError as exc:
            return tfail(exc)

    @api.get("/sesiones/viejas")
    async def sesiones_viejas_list(q: str = ""):
        return JSONResponse(
            await asyncio.to_thread(tacciones.listar_sesiones_viejas, q),
            headers={"Cache-Control": "no-store"},
        )

    @api.post("/sesiones/viejas/retomar")
    async def sesiones_viejas_retomar(request: Request):
        try:
            body = tacc.RetomarViejaBody.model_validate(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="cuerpo inválido") from exc
        try:
            return JSONResponse(
                await tacciones.retomar_sesion_vieja(tctx(request), body),
                headers={"Cache-Control": "no-store"},
            )
        except TraspasoError as exc:
            return tfail(exc)

    @api.get("/pedidos-pestana")
    async def pedidos_pestana_listar():
        return JSONResponse(pedidos_pestana.listar_pendientes(), headers={"Cache-Control": "no-store"})

    async def pegar_mensajes_nuevos(creado: dict, base_id: str, destino: str, origen: str = "manual") -> list:
        """Pega el mensaje inicial en cada Claude recién abierto; devuelve las filas que no se pudieron pegar."""
        sin_pegar: list = []
        for fila in creado.get("detalle") or []:
            if fila.get("tipo") != "claude" or not fila.get("mensaje"):
                continue
            if not fila.get("pegado"):
                sin_pegar.append(fila)
                continue
            cuerpo = MensajeBody(id=f"{base_id}-{fila['pane_id'].replace(':', '')[:8]}", pane_id=fila["pane_id"],
                                 texto=fila["mensaje"], origen=origen, destino=destino[:200])
            try:
                await mensajes.execute(cuerpo)
            except TraspasoError:
                sin_pegar.append(fila)
        if sin_pegar:
            try:
                await tnotify("No pude pegar el mensaje",
                              "La tarea quedó sin pegar en la sesión nueva: pegala a mano.",
                              "terminal-pedido-sin-pegar", sin_pegar[0]["pane_id"])
            except Exception:
                log.warning("nueva-tarea: no pude avisar que no pegó", exc_info=True)
        return sin_pegar

    # ---- copiloto de reuniones
    reunion_tareas: set = set()

    def lanzar_reunion(coro) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        reunion_tareas.add(task)
        task.add_done_callback(reunion_tareas.discard)
        vigilar(task, getattr(coro, "__qualname__", None) or repr(coro))

    ajustes_reu = ajustes_reunion(cfg.reunion)

    def protegidos_copiloto() -> list[str]:
        """Lo que el Copiloto nunca lee: el repo de Colmena (configurado y real) y el data dir."""
        rutas = [*rutas_protegidas(os.environ), str(data_directory), str(cfg.self_repo_path())]
        return list(dict.fromkeys(rutas))
    ctx_reunion: list = [tacc.Ctx(ip="127.0.0.1", device="copiloto")]

    async def cerrar_pane_copiloto(pane_id: str) -> None:
        """Cierra la pestaña del Copiloto, solo si ese pane es lo único que hay en ella."""
        snap = await terminales.snapshot(fresh=True)
        tab_id = (merged_panes(snap).get(pane_id) or {}).get("tab_id")
        if not tab_id:
            return
        vista = await cierres.preview(PreviewBody(tipo="tab", target_id=tab_id))
        if [p.get("pane_id") for p in vista.get("panes", [])] != [pane_id]:
            log.warning("reunión: la pestaña del Copiloto tiene otras terminales, no la cierro")
            return
        await cierres.execute(CierreBody(id=f"cop-cerrar-{uuid.uuid4().hex[:12]}", tipo="tab", target_id=tab_id,
                                         huella=vista["huella"], origen="manual", destino="Copiloto"),
                              guardado="saltado", forzar=True)

    detector_reu = Detector(cfg, uso, data_directory / "reunion-claude", ajustes_reu, runner=reunion_opts.get("runner"))
    puente_reu = PuenteCopiloto(tacciones, pegar_mensajes_nuevos, mensajes, ctx=lambda: ctx_reunion[0],
                                carpeta=carpeta_copiloto, home=Path.home(), extra=[], cerrar_pane=cerrar_pane_copiloto,
                                protegidos=protegidos_copiloto, transcripts=cfg.projects_dir(),
                                regla=reunion_opts.get("regla", REPO_ROOT / "kit" / "reglas" / "copiloto" / "copiloto.md"))
    reunion = ReunionStore(
        emitir=emit_all,
        programar=reunion_opts.get("programar") or (lambda d, fn: asyncio.get_running_loop().call_later(d, fn)),
        lanzar=lanzar_reunion, clock=time.time, detector=detector_reu, puente=puente_reu,
        biblioteca=SimpleNamespace(guardar=library.agregar_reunion), journal_dir=data_directory / "reuniones",
        ajustes=ajustes_reu, registrar_foto=nudo.registrar_foto, notas=notas)
    estados.al_stop.append(reunion.al_stop)
    app.state.reunion = reunion
    app.state.reunion_tareas = reunion_tareas

    # ---- guía por atajo
    puente_guia = PuenteGuia(tacciones, pegar_mensajes_nuevos, mensajes,
                             ctx=lambda: tacc.Ctx(ip="127.0.0.1", device="guia"), carpeta=carpeta_guia,
                             cerrar_pane=cerrar_pane_copiloto, protegidos=protegidos_copiloto,
                             transcripts=cfg.projects_dir(),
                             regla=reunion_opts.get("regla_guia", REPO_ROOT / "kit" / "reglas" / "guia" / "guia.md"))

    def soltar_nudo_guia(pane: str) -> None:
        """Suelta el nudo solo si lo tiene el ayudante de la guía (no le saca el nudo a otra sesión)."""
        dueno = nudo.dueno()
        if dueno is not None and dueno[0] == pane:
            nudo.soltar(limpiar=True)

    guia = GuiaStore(
        puente=puente_guia, ofrecer=lambda q, item: hub._offer(q, item),
        programar=reunion_opts.get("programar") or (lambda d, fn: asyncio.get_running_loop().call_later(d, fn)),
        lanzar=lanzar_reunion, pc_objetivo=nudo.pc_objetivo,
        reunion_activa=lambda: (reunion.snapshot() or {}).get("estado") in REUNION_ACTIVA,
        registrar_foto=nudo.registrar_foto, soltar_nudo=soltar_nudo_guia)
    nudo.es_guia = guia.es_guia
    estados.al_stop.append(guia.al_stop)
    app.state.guia = guia
    app.state.puente_guia = puente_guia

    async def cerrar_guias_huerfanas() -> None:
        """Al arrancar: cierra los ayudantes de guía que quedaron de la corrida anterior (nadie los usa)."""
        try:
            snap = await terminales.snapshot(fresh=True)
        except (TerminalesError, OSError, ValueError):
            log.warning("guía: no pude ver las terminales para cerrar ayudantes huérfanos")
            return
        for pane in panes_en_carpeta(snap, carpeta_guia):
            if pane == guia.snapshot()["pane"]:
                continue
            try:
                await puente_guia.cerrar_pane(pane)
            except Exception:
                log.exception("guía: no pude cerrar el ayudante huérfano %s", pane)

    def repos_reunion() -> list[dict]:
        out: list[dict] = []
        vistos: set = set()
        copiloto_real = os.path.realpath(carpeta_copiloto)
        protegidos = protegidos_copiloto()

        def sumar(real: str) -> None:
            if real in vistos or real == copiloto_real or len(out) >= REPOS_REUNION_MAX:
                return
            if relacionada(real, protegidos):
                return
            vistos.add(real)
            out.append({"ruta": real, "nombre": os.path.basename(real) or real})

        dev = Path.home() / "development"
        try:
            hijos = sorted(dev.iterdir(), key=lambda x: x.name.casefold())[:DEV_ESCANEO_MAX]
        except OSError:
            hijos = []
        for hijo in hijos:
            if hijo.name.startswith(".") or hijo.is_symlink() or not hijo.is_dir():
                continue
            sumar(os.path.realpath(hijo))
        for agente in board_agents(hub.board or {}):
            cwd = agente.get("cwd")
            if not isinstance(cwd, str) or not cwd:
                continue
            try:
                sumar(validar_carpeta(cwd, cfg.plan_cwds_con_self()))
            except TraspasoError:
                continue
        return out

    def error_reunion(exc: ReunionError, no_existe: int = 404) -> HTTPException:
        return HTTPException(status_code=no_existe if exc.status == 404 else exc.status, detail=exc.mensaje)

    def misma_reunion(rid: str) -> None:
        if (reunion.snapshot() or {}).get("reunion") != rid:
            raise HTTPException(status_code=409, detail="No hay una reunión con ese id.")

    @api.get("/reunion/repos")
    async def reunion_repos():
        repos = await asyncio.to_thread(repos_reunion)
        return JSONResponse({"repos": repos, "todos": str(Path.home() / "development")},
                            headers={"Cache-Control": "no-store"})

    @api.post("/reunion/empezar")
    async def reunion_empezar(body: EmpezarReunionBody, request: Request):
        if not DEVICE_RE.match(body.device):
            raise HTTPException(status_code=422, detail="dispositivo inválido")
        permitidas = {r["ruta"] for r in await asyncio.to_thread(repos_reunion)}
        if any(r not in permitidas for r in body.repos):
            raise HTTPException(status_code=422, detail="Ese repo no está en la lista.")
        ctx_reunion[0] = tctx(request)
        try:
            resultado = await reunion.empezar(body.device, list(dict.fromkeys(body.repos)), body.todos)
        except ReunionError as exc:
            raise error_reunion(exc) from None
        lanzar_reunion(guia.por_reunion())
        return resultado

    @api.post("/reunion/texto", status_code=202)
    async def reunion_texto(body: TextoReunionBody):
        try:
            reunion.texto(body.reunion, body.device, body.texto)
        except ReunionError as exc:
            raise error_reunion(exc, 409) from None
        return {"ok": True}

    @api.post("/reunion/tocar", status_code=202)
    async def reunion_tocar(body: TocarReunionBody):
        misma_reunion(body.reunion)
        try:
            return {"estado": await reunion.tocar(body.reunion, body.linea)}
        except ReunionError as exc:
            raise error_reunion(exc) from None

    @api.post("/reunion/descartar", status_code=202)
    async def reunion_descartar(body: TocarReunionBody):
        misma_reunion(body.reunion)
        try:
            return {"estado": await reunion.descartar(body.reunion, body.linea)}
        except ReunionError as exc:
            raise error_reunion(exc) from None

    @api.post("/reunion/anotar", status_code=202)
    async def reunion_anotar(body: TocarReunionBody):
        misma_reunion(body.reunion)
        try:
            return await reunion.anotar(body.reunion, body.linea)
        except ReunionError as exc:
            raise error_reunion(exc) from None

    @api.post("/reunion/preguntar-ultimo", status_code=202)
    async def reunion_preguntar_ultimo(body: ReunionIdBody):
        misma_reunion(body.reunion)
        try:
            return {"linea": await reunion.preguntar_ultimo(body.reunion)}
        except ReunionError as exc:
            raise error_reunion(exc) from None

    @api.post("/reunion/mostrar", status_code=202)
    async def reunion_mostrar(body: MostrarReunionBody):
        misma_reunion(body.reunion)
        try:
            imagen = await asyncio.to_thread(mostrar_mod.decodificar_imagen, body.imagen)
            foto = await asyncio.to_thread(mostrar_mod.validar_foto, body.foto)
        except ValueError:
            raise HTTPException(status_code=422, detail="La captura no es válida.") from None
        try:
            return await reunion.mostrar(body.reunion, body.device, body.pregunta, foto, imagen)
        except ReunionError as exc:
            raise error_reunion(exc) from None

    @api.post("/reunion/pausar", status_code=202)
    async def reunion_pausar(body: ReunionIdBody):
        try:
            reunion.pausar(body.reunion)
        except ReunionError as exc:
            raise error_reunion(exc, 409) from None
        return {"ok": True}

    @api.post("/reunion/seguir", status_code=202)
    async def reunion_seguir(body: ReunionIdBody):
        try:
            reunion.seguir(body.reunion)
        except ReunionError as exc:
            raise error_reunion(exc, 409) from None
        return {"ok": True}

    async def _terminar_reunion(rid: str) -> None:
        try:
            await reunion.terminar(rid)
        except ReunionError:
            log.warning("reunión: no pude terminar %s", rid)

    @api.post("/reunion/terminar", status_code=202)
    async def reunion_terminar(body: ReunionIdBody):
        misma_reunion(body.reunion)
        lanzar_reunion(_terminar_reunion(body.reunion))
        return {"ok": True}

    @api.get("/reunion/estado")
    async def reunion_estado():
        return JSONResponse(reunion.snapshot() or None, headers={"Cache-Control": "no-store"})

    def error_guia(exc: GuiaError) -> HTTPException:
        return HTTPException(status_code=exc.status, detail={"codigo": exc.codigo, "mensaje": exc.mensaje})

    async def captura_guia(foto_raw: dict, imagen_raw: dict) -> tuple:
        try:
            imagen = await asyncio.to_thread(mostrar_mod.decodificar_imagen, imagen_raw)
            foto = await asyncio.to_thread(mostrar_mod.validar_foto, foto_raw)
        except ValueError:
            raise HTTPException(status_code=422, detail={"codigo": "invalida",
                                                         "mensaje": "La captura no es válida."}) from None
        return foto, imagen

    async def correr_guia(coro):
        try:
            return await coro
        except GuiaError as exc:
            raise error_guia(exc) from None
        except OSError:
            # guardar_captura no pudo escribir (disco, enlace): la guía ya se limpió sola.
            log.exception("guía: no pude guardar la captura")
            raise HTTPException(status_code=500, detail={"codigo": "fallo",
                                                         "mensaje": "No pude guardar la captura."}) from None

    @api.post("/guia/pedir", status_code=202)
    async def guia_pedir(body: PedirGuiaBody):
        if not body.pregunta.strip():
            raise error_guia(GuiaError(422, "sin_pregunta", guia_mod.SIN_PREGUNTA))
        foto, imagen = await captura_guia(body.foto, body.imagen)
        return await correr_guia(guia.pedir(body.device, body.pregunta, foto, imagen))

    @api.post("/guia/siguiente", status_code=202)
    async def guia_siguiente(body: SiguienteGuiaBody):
        foto, imagen = await captura_guia(body.foto, body.imagen)
        return await correr_guia(guia.siguiente(body.device, foto, imagen))

    @api.post("/guia/salir")
    async def guia_salir(body: SalirGuiaBody):
        await correr_guia(guia.salir(body.device))
        return {"ok": True}

    async def _aprobar_cierre_de_terminal(pedido_id: str, item: dict, request: Request):
        """Ando aprobó el pedido de cerrar una terminal: misma acción que el botón Cerrar del tablero.

        Se compara contra lo que vio el pedido al crearse (terminal, carpeta, lugar y proceso). Si ya es otra
        terminal, o el intento tocó la terminal y falló, el pedido se descarta; si solo se movió, sigue pendiente."""
        term = item.get("terminal") or {}
        pane_id = term.get("pane_id") or ""
        op_id = f"cerrar-{pedido_id}"
        esperado = {k: term.get(k) or "" for k in ("terminal_id", "cwd", "workspace_id", "tab_id", "proceso")
                    if k in term}
        try:
            previa = await tacciones.preview(tacc.PreviewBody(pane_id=pane_id))
            await tacciones.cerrar(
                tctx(request),
                tacc.AccionBody(id=op_id, pane_id=pane_id, huella=previa["huella"]),
                origen="pedido-pestana",
                esperado=esperado,
            )
        except TraspasoError as exc:
            if exc.status == 404 or exc.extra.get("otra_terminal"):
                # La terminal ya no existe o es otra: el pedido no puede cumplirse, no queda pendiente.
                pedidos_pestana.marcar(pedido_id, "rechazado")
            elif tacciones.id_gastado(op_id):
                # Se tocó la terminal y falló: con el mismo id el reintento diría "ya se hizo" hasta vencer.
                pedidos_pestana.marcar(pedido_id, "rechazado")
                return JSONResponse({"detail": "no pude cerrar la terminal: descarté el pedido"},
                                    status_code=exc.status)
            return tfail(exc)
        except Exception:
            log.exception("pedido-pestana: falló al cerrar %s", pane_id)
            if tacciones.id_gastado(op_id):
                pedidos_pestana.marcar(pedido_id, "rechazado")
                return JSONResponse({"detail": "no pude cerrar la terminal: descarté el pedido"}, status_code=500)
            return JSONResponse({"detail": "falló al cerrar la terminal"}, status_code=500)
        pedidos_pestana.marcar(pedido_id, "abierto")
        push.avisos.marcar_donde(pedido=pedido_id)
        return {"ok": True, "pane_id": pane_id, "cerrada": True}

    async def _aprobar_trabajador_cursor(pedido_id: str, item: dict, request: Request):
        runner = request.app.state.cursor_runner
        origen = {"tipo": "claude", **{k: v for k, v in item["origen"].items() if isinstance(v, str) and v}}
        # Antes del await: un doble toque, el celu y la PC a la vez o un "No" en el medio ven 409.
        if not pedidos_pestana.tomar_para_lanzar(pedido_id):
            raise HTTPException(status_code=409, detail="el pedido ya no está pendiente")
        final = "pendiente"
        try:
            trabajador = await runner.lanzar(carpeta=item["carpeta"], pedido=item["mensaje"], nombre=item["nombre"],
                                             origen=origen, base="head",
                                             modelo=(item.get("cursor") or {}).get("modelo") or "")
            final = "abierto"
        except TraspasoError as exc:
            if exc.status in (400, 503):
                # Reintentar no lo arregla: sin cursor-agent o con una carpeta que no sirve.
                final = "rechazado"
            return tfail(exc)
        finally:
            pedidos_pestana.soltar_lanzamiento(pedido_id, final)
            if final != "pendiente":
                push.avisos.marcar_donde(pedido=pedido_id)
        return JSONResponse({"ok": True, "trabajador": trabajador}, headers={"Cache-Control": "no-store"})

    def _pedido_en_repo_colmena(item: dict) -> bool:

        carpetas = [item.get("carpeta") or ""] + [p.get("carpeta") or "" for p in item.get("pestanas") or []]
        return any(c and es_repo_colmena(c) for c in carpetas)

    async def _verificar_cierre(item: dict):
        """Preview + protección + estructura de un pedido de cierre. Devuelve (preview, final, motivo, respuesta);
        con `respuesta` el pedido no se puede cerrar: `final` dice cómo queda y `motivo` qué avisar al origen."""
        cierre = item["cierre"]
        try:
            preview = await cierres.preview(PreviewBody(tipo=cierre["tipo"], target_id=cierre["target_id"]))
        except TraspasoError as exc:
            if exc.status in (400, 403):
                return None, "rechazado", "cierre_protegido", tfail(exc)
            if exc.status == 404:
                return None, "rechazado", "cierre_cambio", tfail(exc)
            return None, "pendiente", None, tfail(exc)
        except Exception:
            log.exception("pedido-pestana: falló el preview del cierre")
            return None, "rechazado", "cierre_no_hecho", JSONResponse(
                {"detail": "falló al revisar lo que había que cerrar"}, status_code=500)
        if preview.get("protegido"):
            return None, "rechazado", "cierre_protegido", JSONResponse(
                {"detail": "Eso no se puede cerrar: descarté el pedido"}, status_code=409)
        if CierreService.estructura(preview) != cierre.get("estructura"):
            return None, "rechazado", "cierre_cambio", JSONResponse(
                {"detail": "Cambió lo que había que cerrar: descarté el pedido"}, status_code=409)
        return preview, "pendiente", None, None

    @api.post("/pedidos-pestana/{pedido_id}/vista-cierre")
    async def pedidos_pestana_vista_cierre(pedido_id: str):
        item = pedidos_pestana.get(pedido_id) if AVISO_PEDIDO_RE.match(pedido_id or "") else None
        if item is None or item["estado"] != "pendiente" or not item.get("cierre"):
            raise HTTPException(status_code=404, detail="pedido no encontrado")
        preview, final, motivo, respuesta = await _verificar_cierre(item)
        if respuesta is not None:
            if final != "pendiente":
                # Si una aprobación lo tomó mientras tanto, `marcar` no lo cambia y no se avisa dos veces.
                marcado = pedidos_pestana.marcar(pedido_id, final)
                if marcado is not None and marcado["estado"] == final:
                    pedidos_pestana.descartar(item.get("origen") or {}, motivo)
                    push.avisos.marcar_donde(pedido=pedido_id)
            return respuesta
        vista = vista_cierre(preview)
        pedidos_pestana.marcar_vista_cierre(pedido_id, vista["huella"])
        if vista["trabajando"]:
            pedidos_pestana.marcar_aviso_cierre(pedido_id, vista["huella"])
        return JSONResponse(vista, headers={"Cache-Control": "no-store"})

    async def _aprobar_cierre_objetivo(pedido_id: str, item: dict, body: AbrirPedidoBody):
        """Ando aprobó cerrar una sesión, pestaña o tarjeta: guarda en Engram antes y respeta el aviso de "trabajando"."""
        cierre = item["cierre"]
        origen = item.get("origen") or {}
        if not pedidos_pestana.tomar_para_lanzar(pedido_id):
            raise HTTPException(status_code=409, detail="el pedido ya no está pendiente")
        final = "pendiente"
        try:
            preview, final, motivo, respuesta = await _verificar_cierre(item)
            if respuesta is not None:
                if motivo:
                    pedidos_pestana.descartar(origen, motivo)
                return respuesta
            cuerpo = CierreBody(id=f"pc-{pedido_id.replace('-', '')[:48]}", tipo=cierre["tipo"],
                                target_id=cierre["target_id"], huella=preview["huella"], origen="pedido-pestana",
                                destino=(cierre.get("label") or "")[:200], confirmado_por="usuario")
            if preview.get("bloqueantes"):
                aviso = cierre.get("aviso_huella")
                if not (body.forzar and body.huella and body.huella == aviso == preview["huella"]):
                    return JSONResponse({"detail": "Está trabajando: revisalo", "bloqueantes": preview["bloqueantes"]},
                                        status_code=409)
                await cierres.execute(cuerpo, guardado="saltado", forzar=True)
                final = "abierto"
                return {"ok": True, "pane_id": "", "cerrada": True}
            if not (body.huella and body.huella == cierre.get("vista_huella") == preview["huella"]):
                # Sin la vista, o con otra huella: lo que se aprobó no es lo que hay ahora.
                final = "rechazado"
                pedidos_pestana.descartar(origen, "cierre_cambio")
                return JSONResponse({"detail": "Cambió lo que había que cerrar: descarté el pedido"}, status_code=409)
            avisado = False

            def al_lote(lote) -> None:
                nonlocal avisado
                if avisado:
                    return
                motivo = motivo_fin_lote(lote.public())
                if not motivo:
                    return
                avisado = True
                if lote.vencido:
                    guardado.cancelar(lote.id)
                pedidos_pestana.descartar(origen, motivo)

            out = await guardado.iniciar_uno(cuerpo, listener=al_lote)
            final = "abierto"
            es_lote = isinstance(out, Lote)
            return {"ok": True, "pane_id": "", "cerrada": not es_lote, "guardando": es_lote}
        except TraspasoError as exc:
            if exc.status != 409:
                final = "rechazado"
                pedidos_pestana.descartar(origen, "cierre_protegido" if exc.status in (400, 403)
                                          else "cierre_no_hecho")
            return JSONResponse({"detail": exc.detail, **({"bloqueantes": exc.extra["bloqueantes"]}
                                                          if "bloqueantes" in exc.extra else {})},
                                status_code=exc.status)
        except Exception:
            log.exception("pedido-pestana: falló al cerrar %s", cierre.get("target_id"))
            final = "rechazado"
            pedidos_pestana.descartar(origen, "cierre_no_hecho")
            return JSONResponse({"detail": "falló al cerrar"}, status_code=500)
        finally:
            pedidos_pestana.soltar_lanzamiento(pedido_id, final)
            if final != "pendiente":
                push.avisos.marcar_donde(pedido=pedido_id)

    @api.post("/pedidos-pestana/{pedido_id}/abrir")
    async def pedidos_pestana_abrir(pedido_id: str, request: Request):
        if not AVISO_PEDIDO_RE.match(pedido_id or ""):
            raise HTTPException(status_code=404, detail="pedido no encontrado")
        item = pedidos_pestana.get(pedido_id)
        if item is None:
            raise HTTPException(status_code=404, detail="pedido no encontrado")
        if item["estado"] == "vencido":
            raise HTTPException(status_code=404, detail="pedido no encontrado")
        if item["estado"] != "pendiente":
            raise HTTPException(status_code=409, detail="el pedido ya no está pendiente")
        if item.get("accion") == "cerrar" and item.get("cierre"):
            try:
                crudo = await request.body()
                body = AbrirPedidoBody.model_validate_json(crudo) if crudo.strip() else AbrirPedidoBody()
            except ValidationError:
                raise HTTPException(status_code=400, detail="cuerpo inválido")
            return await _aprobar_cierre_objetivo(pedido_id, item, body)
        if item.get("accion") == "cerrar":
            return await _aprobar_cierre_de_terminal(pedido_id, item, request)
        if _pedido_en_repo_colmena(item):
            pedidos_pestana.marcar(pedido_id, "rechazado")
            push.avisos.marcar_donde(pedido=pedido_id)
            return JSONResponse({"detail": "Colmena no abre pedidos en su propio repo"}, status_code=400)
        if item.get("accion") == "cursor":
            return await _aprobar_trabajador_cursor(pedido_id, item, request)
        grupo = await tacciones.grupo_de_sesion(item["origen"].get("pane_id") or "")
        idem = pedidos_pestana.idempotencia_nueva(pedido_id)
        marcado = False

        def marcar_abierto() -> None:
            # Se llama apenas existen las pestañas (antes de esperar a Claude) y, de respaldo, al terminar.
            nonlocal marcado
            if marcado:
                return
            marcado = True
            pedidos_pestana.marcar(pedido_id, "abierto")
            push.avisos.marcar_donde(pedido=pedido_id)

        try:
            try:
                creado = await tacciones.abrir_desde_pedido_pestana(
                    tctx(request),
                    item,
                    idempotencia=idem,
                    grupo=grupo,
                    al_crear=marcar_abierto,
                    permiso="default",
                )
            except TraspasoError as exc:
                if not grupo or exc.status != 409:
                    raise
                creado = await tacciones.abrir_desde_pedido_pestana(
                    tctx(request),
                    item,
                    idempotencia=idem,
                    grupo=None,
                    al_crear=marcar_abierto,
                    permiso="default",
                )
        except TraspasoError as exc:
            return tfail(exc)
        from .colmena_pestana import PREFIJO_PEDIDO

        sin_pegar: list[dict] = []
        for fila in creado.get("detalle") or []:
            if fila.get("tipo") != "claude":
                continue
            if not fila.get("pegado"):
                sin_pegar.append(fila)
                continue
            texto = fila.get("mensaje")
            if not texto:
                continue
            msg_id = f"ppm-{pedido_id.replace('-', '')[:52]}-{fila['pane_id'].replace(':', '')[:8]}"
            cuerpo = MensajeBody(
                id=msg_id,
                pane_id=fila["pane_id"],
                texto=(PREFIJO_PEDIDO + texto)[:MAX_TEXT],
                origen="pedido-pestana",
                destino=item["origen"].get("nombre") or fila["pane_id"],
            )
            try:
                await mensajes.execute(cuerpo)
            except TraspasoError:
                fila["pegado"] = False
                sin_pegar.append(fila)
        marcar_abierto()
        if sin_pegar:
            nombres = ", ".join(f"«{f.get('nombre') or f['pane_id']}»" for f in sin_pegar)
            log.warning("pedido-pestana %s: no pude pegar el mensaje en %s",
                        pedido_id, ", ".join(f["pane_id"] for f in sin_pegar))
            try:
                await tnotify("No pude pegar el mensaje",
                              f"En {nombres} el mensaje quedó sin pegar: pegalo a mano.",
                              "terminal-pedido-sin-pegar", sin_pegar[0]["pane_id"])
            except Exception:
                log.warning("pedido-pestana %s: no pude avisar que no pegó", pedido_id, exc_info=True)
        out: dict = {"ok": True, "pane_id": creado["pane_id"]}
        if creado.get("pane_ids"):
            out["pane_ids"] = creado["pane_ids"]
        if sin_pegar:
            out["pegado"] = False
        return JSONResponse(out, headers={"Cache-Control": "no-store"})

    @api.post("/pedidos-pestana/{pedido_id}/rechazar")
    async def pedidos_pestana_rechazar(pedido_id: str):
        if not AVISO_PEDIDO_RE.match(pedido_id or ""):
            raise HTTPException(status_code=404, detail="pedido no encontrado")
        item = pedidos_pestana.get(pedido_id)
        if item is None:
            raise HTTPException(status_code=404, detail="pedido no encontrado")
        if item["estado"] == "vencido":
            raise HTTPException(status_code=404, detail="pedido no encontrado")
        if item["estado"] != "pendiente":
            raise HTTPException(status_code=409, detail="el pedido ya no está pendiente")
        pedidos_pestana.marcar(pedido_id, "rechazado")
        push.avisos.marcar_donde(pedido=pedido_id)
        return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})

    @api.post("/terminales/ctrl-c")
    async def terminales_ctrl_c(request: Request):
        if not escritura():
            tacciones.rechazo(tctx(request), "ctrl_c")
            raise HTTPException(status_code=403, detail="escritura apagada")
        body = await tbody(request, tacc.AccionBody)
        try:
            return await tacciones.ctrl_c(tctx(request), body)
        except TraspasoError as exc:
            return tfail(exc)

    @api.post("/terminales/cerrar")
    async def terminales_cerrar(request: Request):
        body = await tbody(request, tacc.AccionBody)
        try:
            return await tacciones.cerrar(tctx(request), body)
        except TraspasoError as exc:
            return tfail(exc)

    @api.post("/terminales/renombrar")
    async def terminales_renombrar(request: Request):
        body = await tbody(request, tacc.RenombrarBody)
        try:
            return await tacciones.renombrar(tctx(request), body)
        except TraspasoError as exc:
            return tfail(exc)

    @api.post("/terminales/repetir/preparar")
    async def terminales_repetir_preparar(request: Request):
        if not escritura():
            tacciones.rechazo(tctx(request), "repetir_preparar")
            raise HTTPException(status_code=403, detail="escritura apagada")
        body = await tbody(request, tacc.AccionBody)
        try:
            return await tacciones.repetir_preparar(tctx(request), body)
        except TraspasoError as exc:
            return tfail(exc)

    @api.post("/terminales/repetir/confirmar")
    async def terminales_repetir_confirmar(request: Request):
        if not escritura():
            tacciones.rechazo(tctx(request), "repetir_confirmar")
            raise HTTPException(status_code=403, detail="escritura apagada")
        body = await tbody(request, tacc.ConfirmarBody)
        try:
            return await tacciones.repetir_confirmar(tctx(request), body)
        except TraspasoError as exc:
            return tfail(exc)

    @api.post("/terminales/ventana")
    async def terminales_ventana(request: Request):
        if not escritura():
            tacciones.rechazo(tctx(request), "ventana_abierta")
            raise HTTPException(status_code=403, detail="escritura apagada")
        try:
            body = tacc.VentanaBody.model_validate(await request.json())
        except (ValidationError, ValueError):
            raise HTTPException(status_code=422, detail="cuerpo inválido")
        try:
            return JSONResponse(await tacciones.abrir_ventana(tctx(request), body), headers={"Cache-Control": "no-store"})
        except TraspasoError as exc:
            return tfail(exc)

    @api.post("/terminales/ventana/cerrar")
    async def terminales_ventana_cerrar(request: Request):
        return tacciones.cerrar_ventana(tctx(request))

    @api.post("/terminales/comando")
    async def terminales_comando(request: Request):
        if not escritura():
            tacciones.rechazo(tctx(request), "comando")
            raise HTTPException(status_code=403, detail="escritura apagada")
        body = await tbody(request, tacc.ComandoBody)
        try:
            return await tacciones.comando(tctx(request), body)
        except TraspasoError as exc:
            return tfail(exc)

    @api.post("/sessions/{session_id}/comando")
    async def session_comando(session_id: str, request: Request):
        if not SESSION_ID.match(session_id):
            raise HTTPException(status_code=400, detail="session_id inválido")
        body = await tbody(request, ComandoSesionBody)
        try:
            return JSONResponse(await comando_sesion.correr(session_id, body, tctx(request)),
                                headers={"Cache-Control": "no-store"})
        except TraspasoError as exc:
            return tfail(exc)

    @api.get("/sessions/{session_id}/comando")
    async def session_comando_get(session_id: str):
        return JSONResponse({"detail": "método no permitido"}, status_code=405, headers={"Allow": "POST"})

    for _path in ("/terminales/ventana", "/terminales/ventana/cerrar", "/terminales/comando",
                  "/terminales/ctrl-c", "/terminales/repetir/preparar", "/terminales/repetir/confirmar",
                  "/terminales/preview", "/terminales/nueva", "/terminales/renombrar", "/terminales/nueva-tarea", "/terminales/nueva-tarea/borrar-copia"):
        api.add_api_route(_path, lambda: JSONResponse({"detail": "método no permitido"}, status_code=405,
                                                     headers={"Allow": "POST"}), methods=["GET"])

    @api.get("/sessions/{session_id}/transcript")
    async def transcript(session_id: str, before: Optional[int] = None, limit: int = DEFAULT_LIMIT,
                         desde: Optional[int] = None):
        if not SESSION_ID.match(session_id):
            raise HTTPException(status_code=400, detail="session_id inválido")
        try:
            agent = find_session_agent(await hub.current(), session_id)
        except (TerminalesError, OSError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"Las terminales no responden: {exc}")
        if not agent:
            raise HTTPException(status_code=404, detail="sesión no encontrada")
        page = await asyncio.to_thread(transcripts.page, session_id, before, min(max(limit, 1), MAX_LIMIT), desde)
        if page is None:
            page = await asyncio.to_thread(transcripts.vacia, session_id)
        return {**page, "title": agent["doing"], "status": agent["status"], "pane_id": agent["pane_id"]}

    @api.get("/sessions/{session_id}/subagentes")
    async def subagentes_de(session_id: str):
        if not SESSION_ID.match(session_id):
            raise HTTPException(status_code=400, detail="session_id inválido")
        return {"items": await asyncio.to_thread(subagentes.listar, session_id)}

    @api.post("/sessions/{session_id}/seen", status_code=204)
    async def seen(session_id: str):
        if not SESSION_ID.match(session_id):
            raise HTTPException(status_code=400, detail="session_id inválido")
        try:
            agent = find_session_agent(await hub.current(), session_id)
        except (TerminalesError, OSError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"Las terminales no responden: {exc}")
        if agent is None:
            raise HTTPException(status_code=404, detail="sesión no encontrada")
        hub.mark_seen(session_id)
        return Response(status_code=204)

    @api.post("/sessions/{session_id}/pregunta-vista", status_code=204)
    async def pregunta_vista(session_id: str):
        if not SESSION_ID.match(session_id):
            raise HTTPException(status_code=400, detail="session_id inválido")
        try:
            agent = find_session_agent(await hub.current(), session_id)
        except (TerminalesError, OSError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"Las terminales no responden: {exc}")
        if agent is None:
            raise HTTPException(status_code=404, detail="sesión no encontrada")
        hub.mark_pregunta_vista(session_id)
        return Response(status_code=204)

    @api.post("/uploads")
    async def upload(request: Request):
        try:
            return await uploads_mod.save_upload(request.stream(), request.headers.get("content-type", ""),
                                                 uploads_dir)
        except TraspasoError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)

    @api.get("/uploads/{ident}")
    async def upload_get(ident: str):
        path = uploads_mod.upload_path(uploads_dir, ident)
        if path is None:
            raise HTTPException(status_code=404, detail="adjunto no encontrado")
        inline = uploads_mod.kind_of(ident.rsplit(".", 1)[-1]) != "text"
        return FileResponse(path, media_type=uploads_mod.media_type(ident), filename=ident,
                            content_disposition_type="inline" if inline else "attachment",
                            headers={"Cache-Control": "private, max-age=3600"})

    @api.get("/voz/estado")
    async def voz_estado():
        return voz.estado()

    @api.post("/voz/transcribir")
    async def voz_transcribir(request: Request):
        try:
            return await voz.transcribe(request.stream(), request.headers.get("content-type", ""))
        except TraspasoError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)

    @api.get("/uso/claude")
    async def uso_claude_endpoint():
        nombres = nombres_herdr(hub.board)
        return JSONResponse(await asyncio.to_thread(uso_claude.summary, nombres), headers={"Cache-Control": "no-store"})

    @api.get("/memoria/estado")
    async def memoria_estado():
        return JSONResponse(await asyncio.to_thread(memoria.estado), headers={"Cache-Control": "no-store"})

    @api.post("/memoria/reindexar")
    async def memoria_reindexar():
        if not memoria.habilitada:
            raise HTTPException(status_code=409, detail="la memoria está deshabilitada")
        try:
            memoria.reindexar()
        except Demasiado:
            raise HTTPException(status_code=429, detail="Ya se reindexó hace poco: probá en unos minutos")
        return {"ok": True}

    @api.delete("/memoria/indice")
    async def memoria_borrar():
        await asyncio.to_thread(memoria.borrar)
        return {"ok": True}

    @api.get("/memoria/cita")
    async def memoria_cita(session_id: str = "", turno: Optional[int] = None, engram: Optional[int] = None):
        if engram is not None:
            if engram < 1:
                raise HTTPException(status_code=400, detail="id inválido")
            cita = await asyncio.to_thread(memoria.cita_engram, engram)
        else:
            if not SESSION_ID.match(session_id) or turno is None or turno < 0:
                raise HTTPException(status_code=400, detail="cita inválida")
            cita = await asyncio.to_thread(memoria.cita_sesion, session_id, turno)
        if cita is None:
            raise HTTPException(status_code=404, detail="No encontré ese fragmento")
        return JSONResponse(cita, headers={"Cache-Control": "no-store"})

    def lib_filters(tipo: str, session: str, desde: str, hasta: str, q: str) -> dict:
        if session and not SESSION_ID.match(session):
            raise HTTPException(status_code=400, detail="session inválido")
        if any(d and not DATE_RE.match(d) for d in (desde, hasta)) or len(q) > 100 or len(tipo) > 80:
            raise HTTPException(status_code=422, detail="filtro inválido")
        return {"tipo": tipo, "session": session, "desde": desde, "hasta": hasta, "q": q}

    @api.get("/biblioteca")
    async def biblioteca_list(tipo: str = "", session: str = "", desde: str = "", hasta: str = "", q: str = "",
                              cursor: Optional[str] = None, limit: int = 60):
        filters = lib_filters(tipo, session, desde, hasta, q)
        if not cursor:
            await asyncio.to_thread(library.rescan_on_demand)
        return await asyncio.to_thread(library.listing, cursor, limit, **filters)

    @api.post("/biblioteca/quitar")
    async def biblioteca_quitar(body: QuitarBody):
        if not body.ids or any(not isinstance(i, str) or not ITEM_ID.match(i) for i in body.ids):
            raise HTTPException(status_code=422, detail="ids inválidos")
        quitados = await asyncio.to_thread(library.quitar, body.ids)
        return {"quitados": quitados}

    @api.get("/biblioteca/sesiones")
    async def biblioteca_sessions():
        return await asyncio.to_thread(library.session_list)

    @api.get("/biblioteca/{ident}")
    async def biblioteca_item(ident: str, tipo: str = "", session: str = "", desde: str = "", hasta: str = "",
                              q: str = ""):
        filters = lib_filters(tipo, session, desde, hasta, q)
        found = await asyncio.to_thread(library.detail, ident, **filters)
        if found is None:
            raise HTTPException(status_code=404, detail="no encontrado")
        return found

    @api.get("/biblioteca/{ident}/texto")
    async def biblioteca_text(ident: str):
        text = await asyncio.to_thread(library.text_of, ident)
        if text is None:
            raise HTTPException(status_code=404, detail="no encontrado")
        return {"text": text}

    @api.get("/biblioteca/{ident}/charla")
    async def biblioteca_charla(ident: str):
        charla = await asyncio.to_thread(library.charla_de, ident)
        if charla is None:
            raise HTTPException(status_code=404, detail="no encontrado")
        return JSONResponse({"charla": charla}, headers={"Cache-Control": "no-store"})

    @api.get("/avisos")
    async def avisos_list(limite: int = 50, antes: int = 0, incluir_prueba: bool = False):
        return JSONResponse(push.avisos.page(limite, antes, incluir_prueba=incluir_prueba), headers={"Cache-Control": "no-store"})

    @api.post("/avisos/prueba")
    async def avisos_prueba(body: AvisoPruebaBody):
        if body.kind not in push.prueba_kinds():
            raise HTTPException(status_code=422, detail="kind inválido")
        if body.destino == "notch":
            if body.kind not in NOTCH_PRUEBA_KINDS:
                raise HTTPException(status_code=422, detail="este tipo solo va al celular")
            entry = push.prueba_aviso_notch(body.kind)
            return {"ok": True, "id": entry["id"]}
        if not push.active:
            raise HTTPException(status_code=404, detail="no hay dispositivos suscriptos")
        enviados = await push.prueba_push_celu(body.kind)
        if not enviados:
            raise HTTPException(status_code=502, detail="no se pudo enviar el aviso")
        return {"ok": True}

    @api.post("/avisos/leidos")
    async def avisos_leidos(body: LeidosBody):
        excluir = body.endpoint or ""
        if body.kind is not None and body.kind not in push.avisos.kinds:
            raise HTTPException(status_code=422, detail="kind inválido")
        if body.hasta is not None:
            return {"ok": True, "no_leidos": push.marcar(hasta=body.hasta, excluir=excluir)}
        return {"ok": True, "no_leidos": push.marcar(excluir=excluir, session_id=body.session_id or "",
                                                      pane_id=body.pane_id or "", kind=body.kind or "",
                                                      mr=body.mr or "", mensaje=body.mensaje or "")}

    @api.post("/presencia")
    async def presencia(body: PresenciaBody):
        push.presencia.report(body.device, body.visible, body.mirando, escritorio=body.escritorio)
        if body.visible:
            mrs.nudge()
        return {"ok": True}

    @api.post("/abrir-en-pc")
    async def abrir_en_pc(body: AbrirEnPcBody):
        if not push.presencia.hay_escritorio():
            return {"ok": False, "motivo": "sin_pc"}
        payload = {"pane_id": body.pane_id, "titulo": body.titulo}
        for queue in list(hub.subscribers):
            hub._offer(queue, ("abrir_terminal", payload))
        return {"ok": True}

    @api.post("/nudo/salir")
    async def nudo_salir(body: NudoSalirBody):
        if nudo.pc_objetivo() != body.device:
            raise HTTPException(status_code=403, detail="No es la PC conectada")
        nudo.salir(body.device)
        return {"ok": True}

    @api.post("/nudo/{pid}/respuesta")
    async def nudo_respuesta(pid: str, body: NudoRespuestaBody):
        if not NUDO_PID_RE.match(pid):
            raise HTTPException(status_code=404, detail="Pedido desconocido")
        op = nudo.op_de(pid)
        invalido = False
        if op:
            try:
                validar_respuesta(op, body.resultado)
            except ValueError:
                invalido = True
        if not nudo.resolver(pid, body.device, body.token, body.resultado):
            raise HTTPException(status_code=404, detail="Pedido desconocido")
        if invalido:
            raise HTTPException(status_code=422, detail="Respuesta inválida")
        return {"ok": True}

    @api.get("/push/key")
    async def push_key():
        return {"key": push.keys.public}

    @api.post("/push/subscribe")
    async def push_subscribe(body: SubscribeBody):
        if not endpoint_allowed(body.subscription.endpoint):
            raise HTTPException(status_code=400, detail="endpoint de push no permitido")
        entry = {"endpoint": body.subscription.endpoint, "keys": body.subscription.keys.model_dump(),
                 "device": body.device.strip(), "prefs": body.prefs.model_dump()}
        if not push.store.upsert(entry):
            raise HTTPException(status_code=409, detail="demasiados dispositivos suscriptos")
        hub.set_keep_alive(True)
        return {"ok": True}

    @api.post("/push/unsubscribe")
    async def push_unsubscribe(body: EndpointBody):
        removed = push.store.remove(body.endpoint)
        hub.set_keep_alive(push.active)
        return {"ok": removed}

    @api.post("/push/test")
    async def push_test(body: TestBody):
        if not push.active:
            raise HTTPException(status_code=404, detail="no hay dispositivos suscriptos")
        if not await push.send_test(body.endpoint):
            raise HTTPException(status_code=502, detail="no se pudo enviar el aviso")
        return {"ok": True}

    async def enviar_cierre_dia(endpoint: Optional[str] = None) -> int:
        board = hub.board
        msgs = state.messages()
        now = datetime.now().astimezone()
        ramas = await ramas_sin_integrar(board, msgs, now)
        contenido = contenido_cierre_dia(board, msgs, now, ramas=ramas)
        if contenido is None:
            return 0
        frase = frase_resumen_cierre(contenido)
        return await push.dispatch_cierre(frase, endpoint)

    @api.post("/push/cierre/test")
    async def push_cierre_test(body: TestBody):
        if not push.active:
            raise HTTPException(status_code=404, detail="no hay dispositivos suscriptos")
        if body.endpoint is None:
            raise HTTPException(status_code=422, detail="falta el dispositivo")
        if not await enviar_cierre_dia(body.endpoint):
            raise HTTPException(status_code=422, detail="hoy no hay nada para cerrar")
        return {"ok": True}

    cierre_aviso = CierreDiaAviso(data_directory, lambda: cfg.cierre_hora, lambda: cfg.cierre_dias, enviar_cierre_dia)

    vigia_entornos = VigiaEntornos(entornos_docker_bin(cfg) or None, push.dispatch_entorno)

    inicio_piezas: list = []
    cierre_piezas: list = []

    async def push_startup():
        hub.set_keep_alive(push.active)
        for fn in list(inicio_piezas):
            try:
                resultado = fn()
                if inspect.isawaitable(resultado):
                    await resultado
            except Exception:
                log.exception("una pieza falló al iniciar")
        if parse_hora(cfg.cierre_hora) and not os.environ.get("ORQ_NO_AUTOINDEX"):
            spawn(cierre_aviso.run())
        if not os.environ.get("ORQ_NO_AUTOINDEX"):
            spawn(vigia_entornos.run())
        loop_ref[:] = [asyncio.get_running_loop()]
        try:
            reunion.recuperar()
        except Exception:
            log.exception("no pude recuperar las reuniones del diario")
        try:
            puente_reu.borrar_capturas()
        except OSError:
            log.exception("no pude borrar las capturas viejas del Copiloto")
        try:
            puente_guia.borrar_capturas()
        except OSError:
            log.exception("no pude borrar las capturas viejas de la guía")
        try:
            puente_guia.borrar_transcripts()
        except OSError:
            log.exception("no pude borrar los transcripts viejos de la guía")
        lanzar_reunion(cerrar_guias_huerfanas())
        if not os.environ.get("ORQ_NO_AUTOINDEX"):
            spawn(asyncio.to_thread(library.index_all))
            spawn(asyncio.to_thread(library.run_capturas_backfill))
            spawn(asyncio.to_thread(uso_claude.scan))
            memoria.fondo()
            spawn(devolver_periodicamente())
            if mrs.habilitado and mrs.disponible():
                spawn(mrs.run())

    app.router.on_startup.append(push_startup)

    async def piezas_shutdown():
        for fn in list(cierre_piezas):
            try:
                resultado = fn()
                if inspect.isawaitable(resultado):
                    await resultado
            except Exception:
                log.exception("una pieza falló al cerrar")

    app.router.on_shutdown.append(piezas_shutdown)

    def state_shutdown() -> None:
        for nombre, flush in (("estado", state.flush), ("biblioteca", library.flush), ("notas", notas.flush)):
            try:
                flush()
            except Exception:
                log.exception("no pude guardar %s al apagar", nombre)

    app.router.on_shutdown.append(state_shutdown)

    def _terminal_comun(sel: str) -> dict | None:
        """Busca en el tablero una terminal común por pane_id o, sin distinguir mayúsculas, por su título o
        el nombre de su pestaña. Las sesiones de Claude no están en esa lista; si hay más de una, no elige."""
        clave = sel.strip().casefold()
        halladas: dict = {}
        for ws in (hub.board or {}).get("workspaces") or []:
            for tab in ws.get("tabs") or []:
                for t in tab.get("terminales") or []:
                    if t.get("protegida") or not t.get("pane_id"):
                        continue
                    nombres = {(t.get("titulo") or "").strip().casefold(), (tab.get("label") or "").strip().casefold()}
                    if t["pane_id"] == sel.strip() or clave in nombres - {""}:
                        donde = " / ".join(x for x in (ws.get("label"), tab.get("label")) if x)
                        halladas[t["pane_id"]] = {
                            "pane_id": t["pane_id"],
                            # Para comparar al aprobar: si el pane pasó a ser otra terminal o se movió, no se cierra.
                            "terminal_id": t.get("terminal_id") or "",
                            "workspace_id": ws.get("id") or "",
                            "tab_id": tab.get("id") or "",
                            "titulo": t.get("titulo") or "",
                            "cwd": t.get("cwd") or "",
                            "proceso": t.get("proceso") or "",
                            "estado": t.get("estado") or "",
                            "donde": donde,
                        }
        return next(iter(halladas.values())) if len(halladas) == 1 else None

    def _pedido_cerrar_terminal(sel: str, pane: str, sid: str, nombre: str) -> None:
        origen = {"pane_id": pane, "nombre": nombre, "session_id": sid}
        term = _terminal_comun(sel)
        if term is None:
            log.info("colmena-pestana: terminal a cerrar no encontrada (%s)", pane)
            pedidos_pestana.descartar(origen, "terminal_no_encontrada")
            return
        item, _motivo = pedidos_pestana.crear("", "", None, origen, accion="cerrar", terminal=term)
        if item is None:
            return
        label = term["titulo"] or term["cwd"] or term["pane_id"]
        spawn(push.dispatch_pestana(item["id"], "Pedido para cerrar una terminal",
                                    f"{nombre} quiere cerrar la terminal {label}", session_id=sid, pane_id=pane))

    async def _crear_pedido_cierre(hallado: dict, origen: dict, nombre: str) -> None:
        objetivo = hallado["objetivo"]
        try:
            preview = await cierres.preview(PreviewBody(tipo=hallado["tipo"], target_id=hallado["target_id"]))
        except TraspasoError as exc:
            motivo = {400: "cierre_protegido", 403: "cierre_protegido", 404: "cierre_no_encontrado"}.get(
                exc.status, "cierre_no_posible")
            log.info("colmena-pestana: pedido de cierre rechazado (%s)", motivo)
            pedidos_pestana.descartar(origen, motivo)
            return
        except Exception:
            log.exception("colmena-pestana: falló el preview del pedido de cierre")
            pedidos_pestana.descartar(origen, "cierre_no_posible")
            return
        if preview.get("protegido"):
            pedidos_pestana.descartar(origen, "cierre_protegido")
            return
        resumen = resumen_cierre(objetivo, preview)
        item, _motivo = pedidos_pestana.crear("", "", None, origen, accion="cerrar", cierre=resumen, cooldown=False)
        if item is None:
            return
        titulos = {"sesion": "Pedido para cerrar una sesión", "pestana": "Pedido para cerrar una pestaña",
                   "tarjeta": "Pedido para cerrar una tarjeta"}
        await push.dispatch_pestana(item["id"], titulos[objetivo], f"{nombre} quiere cerrar «{resumen['label']}»",
                                    session_id=origen["session_id"], pane_id=origen["pane_id"])

    def _pedido_cerrar_objetivo(payload: dict, pane: str, sid: str, nombre: str) -> None:
        origen = {"pane_id": pane, "nombre": nombre, "session_id": sid}
        if not pedidos_pestana.permitir(origen):
            return
        hallado, motivo = resolver_objetivo(hub.board, payload["objetivo"], payload["sel"])
        if motivo:
            log.info("colmena-pestana: pedido de cierre descartado (%s)", motivo)
            pedidos_pestana.descartar(origen, motivo)
            return
        spawn(_crear_pedido_cierre(hallado, origen, nombre))

    def _pestana_desde_bash(msg, pane: str | None) -> None:
        if not pane:
            return
        datos = msg.datos if isinstance(msg.datos, dict) else {}
        if datos.get("tool_name") != "Bash":
            return
        entrada = datos.get("tool_input")
        cmd = entrada.get("command") if isinstance(entrada, dict) else None
        if not isinstance(cmd, str):
            return
        payload = pedido_desde_comando_bash(cmd)
        if not payload:
            return
        sid = msg.ids.claude or ""
        nombre, donde = _nombre_sesion_permiso(pane, sid)
        if payload.get("accion") == "cerrar":
            if payload.get("objetivo"):
                _pedido_cerrar_objetivo(payload, pane, sid, nombre)
            else:
                _pedido_cerrar_terminal(payload["terminal"], pane, sid, nombre)
            return
        if payload.get("accion") == "cursor":
            _pedido_trabajador_cursor(payload, pane, sid, nombre)
            return
        try:
            carpeta = validar_carpeta(payload["carpeta"], cfg.plan_cwds)
        except TraspasoError:
            log.info("colmena-pestana carpeta no permitida: %s", pane)
            return
        pestanas = payload.get("pestanas")
        carpetas = [carpeta]
        if pestanas:
            for p in pestanas:
                try:
                    carpetas.append(validar_carpeta(p["carpeta"], cfg.plan_cwds))
                except TraspasoError:
                    log.info("colmena-pestana carpeta no permitida (pestaña): %s", pane)
                    return

        origen_pedido = {"pane_id": pane, "nombre": nombre, "session_id": sid}
        if any(es_repo_colmena(c) for c in carpetas):
            log.info("colmena-pestana carpeta de Colmena: %s", pane)
            pedidos_pestana.descartar(origen_pedido, "carpeta_colmena")
            return
        nombre_tab = payload.get("nombre") or ""
        item, _motivo = pedidos_pestana.crear(
            carpeta,
            payload.get("mensaje") or "",
            nombre_tab or None,
            {
                "pane_id": pane,
                "nombre": nombre,
                "session_id": sid,
            },
            tarjeta=payload.get("tarjeta"),
            pestanas=pestanas,
        )
        if item is None:
            return
        titulo = "Pedido de pestañas" if pestanas and len(pestanas) > 1 else "Pedido de pestaña"
        tarjeta_nom = (payload.get("tarjeta") or "").strip()
        if pestanas:
            cuerpo = f"{nombre} quiere abrir {len(pestanas)} pestañas"
            if tarjeta_nom:
                cuerpo += f" en la tarjeta «{tarjeta_nom}»"
            else:
                cuerpo += f" en {carpeta}"
        else:
            cuerpo = f"{nombre} quiere abrir una pestaña en {carpeta}"
        cuerpo += _resumen_mensajes(pestanas or [{"tipo": "claude", "mensaje": payload.get("mensaje") or ""}])
        spawn(push.dispatch_pestana(item["id"], titulo, cuerpo, session_id=sid, pane_id=pane))

    def _pedido_trabajador_cursor(payload: dict, pane: str, sid: str, nombre: str) -> None:

        try:
            carpeta = validar_carpeta(payload["carpeta"], cfg.plan_cwds)
        except TraspasoError:
            log.info("colmena-pestana cursor carpeta no permitida: %s", pane)
            return
        origen_pedido = {"pane_id": pane, "nombre": nombre, "session_id": sid}
        if es_repo_colmena(carpeta):
            log.info("colmena-pestana cursor carpeta de Colmena: %s", pane)
            pedidos_pestana.descartar(origen_pedido, "carpeta_colmena")
            return
        item, _motivo = pedidos_pestana.crear(carpeta, payload["pedido"], payload["nombre"], origen_pedido,
                                              accion="cursor", cursor={"modelo": payload.get("modelo") or ""})
        if item is None:
            return
        spawn(push.dispatch_pestana(item["id"], "Pedido de trabajador Cursor",
                                    f"{nombre} quiere que Cursor haga: {payload['nombre']}",
                                    session_id=sid, pane_id=pane))

    def _resumen_mensajes(pestanas: list) -> str:
        """` · {k} con mensaje para Claude: «…»`: el push dice que el pedido le va a escribir a Claude."""
        from .envio_sesion import linea_unica

        mensajes_claude = [p["mensaje"] for p in pestanas if p.get("tipo") == "claude" and p.get("mensaje")]
        if not mensajes_claude:
            return ""
        primero = linea_unica(mensajes_claude[0], MAX_TEXT)
        muestra = primero[:80] + ("…" if len(primero) > 80 else "")
        return f" · {len(mensajes_claude)} con mensaje para Claude: «{muestra}»"

    def _post_tool_use(msg, pane: str | None) -> None:
        _pestana_desde_bash(msg, pane)

    app.state.pestana_desde_bash = _pestana_desde_bash
    enrutador = Enrutador(estados, permisos, hub, post_tool_use=_post_tool_use)

    if ganchos_socket is not None:
        from .ganchos.canal import ServidorGanchos

        ganchos_srv = ServidorGanchos(enrutador.manejar)
        app.state.ganchos = ganchos_srv

        async def ganchos_startup():
            try:
                await ganchos_srv.abrir(ganchos_socket)
            except (PermissionError, OSError) as exc:
                log.error("no se pudo abrir el canal de ganchos: %s", exc)

        async def ganchos_shutdown():
            tareas = list(_permisos_observer_tasks)
            for t in tareas:
                t.cancel()
            if tareas:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tareas, return_exceptions=True),
                        2.0,
                    )
                except asyncio.TimeoutError:
                    pass
            await permisos.cerrar_todo()
            await ganchos_srv.cerrar()

        app.router.on_startup.append(ganchos_startup)
        app.router.on_shutdown.append(ganchos_shutdown)
    else:
        app.state.ganchos = None

        async def permisos_shutdown():
            await permisos.cerrar_todo()

        app.router.on_shutdown.append(permisos_shutdown)

    if recarga_socket is not None:
        recarga_srv = ServidorRecarga(recarga_svc.pedir)
        app.state.recarga_socket = recarga_srv

        async def recarga_startup():
            try:
                await recarga_srv.abrir(recarga_socket)
            except (PermissionError, OSError) as exc:
                log.error("no se pudo abrir el socket de recarga: %s", exc)

        async def recarga_shutdown():
            try:
                await asyncio.wait_for(recarga_svc.esperar_envios(), 5)
            except asyncio.TimeoutError:
                log.warning("timeout esperando envíos de recarga en curso")
            await recarga_srv.cerrar()

        app.router.on_startup.append(recarga_startup)
        app.router.on_shutdown.append(recarga_shutdown)
    else:
        app.state.recarga_socket = None

    if nudo_socket is not None:
        from .nudo import ServidorNudo, crear_manejador
        nudo_srv = ServidorNudo(crear_manejador(nudo, lambda: hub.board))
        app.state.nudo_socket = nudo_srv

        async def nudo_startup():
            try:
                await nudo_srv.abrir(nudo_socket)
            except (PermissionError, OSError) as exc:
                log.error("no se pudo abrir el socket del nudo: %s", exc)

        app.router.on_startup.append(nudo_startup)
        app.router.on_shutdown.append(nudo_srv.cerrar)
    else:
        app.state.nudo_socket = None

    def wctx(ws: WebSocket) -> tacc.Ctx:
        client = ws.scope.get("client")
        return tacc.Ctx(
            ip=client[0] if client else "?",
            user=ws.headers.get("tailscale-user-login", "")[:80],
            device=ws.headers.get("user-agent", "")[:80],
            cookie=ws.cookies.get(auth.COOKIE_NAME, ""),
            token="",
        )

    @app.websocket("/api/terminal/{sesion_id}/vivo")
    async def ws_terminal_vivo(websocket: WebSocket, sesion_id: str):
        ctx = wctx(websocket)
        await terminal_vivo.atender(
            websocket,
            sesion_id,
            secret=secret,
            epoch=app.state.epoch,
            habilitado=vivo_habilitado,
            abrir=_abrir_vivo,
            cupos=cupos_vivo,
            escritura_habilitada=escritura,
            ventana=tacciones.ventana,
            escribir=enchufe.escribir,
            teclas=enchufe.teclas,
            audit=tacciones.audit,
            ip_cliente=ctx.ip,
            cookie_sesion=ctx.cookie,
        )

    # ── [pista-A] comentarios del diff ──
    from .comentarios_diff import build_router as comentarios_router
    api.include_router(comentarios_router(hub=hub, cambios_svc=cambios_svc, mensajes=mensajes, cfg=cfg))
    # (fin pista-A)
    # ── [pista-B] MR a la sesión ──
    async def mrs_enviar_origen(pane_id: str, texto: str, ident: str, origen: str) -> None:
        try:
            destino = {"mr-job": "MR job", "mr-hilo": "MR hilo"}.get(origen, "MR")
            await envio_sesion.mandar(mensajes, pane_id=pane_id, texto=texto, origen=origen, ident=ident, destino=destino)
        except TraspasoError as exc:
            raise GitlabError(exc.status, exc.detail)

    mrs.enviar_origen = mrs_enviar_origen
    # (fin pista-B)
    # ── [pista-C] uso del plan ──
    from time import time as _ahora
    from .uso_claude import read_limits

    def uso_limites_actuales():
        return read_limits(ctx_dir(), _ahora()) or {"sin_datos": True}

    @api.get("/uso/limites")
    async def uso_limites():
        return JSONResponse(await asyncio.to_thread(uso_limites_actuales), headers={"Cache-Control": "no-store"})

    # (fin pista-C)
    # ── [pista-E1] trabajador Cursor ──
    from .avisos_origen import AvisoLibre
    from .cursor_api import build_router as cursor_router
    from .cursor_runner import CursorRunner, texto_fin_trabajador
    cursor_runner = CursorRunner(data_directory, worktrees_nt, lambda: cfg.plan_cwds, spawn=spawn,
                                 emit=emit_all, avisar=lambda t, b: tnotify(t, b, "cursor-fin"))
    app.state.cursor_runner = cursor_runner
    aviso_libre = AvisoLibre(lambda body: mensajes.execute(body), lambda: hub.board, spawn)
    hub.observers.append(aviso_libre.al_tablero)
    cursor_runner.al_terminar.append(lambda t: aviso_libre.encolar(t["origen"], texto_fin_trabajador(t))
                                     if t["origen"].get("tipo") == "claude" else None)
    app.router.on_startup.append(cursor_runner.al_arrancar)   # marca interrumpidos
    app.router.on_shutdown.append(cursor_runner.cerrar)
    api.include_router(cursor_router(cursor_runner))
    # (fin pista-E1)
    # ── [pista-E2] tareas programadas ──
    import secrets as _secrets
    import time as _time
    from .nueva_tarea import rama_para
    from .programadas import Programadas
    from .programadas_api import build_router as programadas_router
    from .notas_api import build_router as notas_router

    async def lanzar_programada_claude(repo: str, mensaje: str, nombre: str, ident: str) -> dict:
        # Claude programado: Nueva tarea en modo `default` (cada herramienta pide aprobación a Ando); Colmena no aprueba nada.
        ctx = tacc.Ctx(ip="programada", user="colmena", device="tarea programada")
        # La rama sale del texto y se repetiría cada día: fecha y sufijo al azar como hace Cursor.
        rama = f"{rama_para(os.path.basename(repo), mensaje)}-{_time.strftime('%y%m%d')}-{_secrets.token_hex(2)}"
        creado = await tacciones.nueva_tarea(ctx, tacc.NuevaTareaBody(id=ident, repo=repo, tarea=mensaje, nombre=nombre,
                                                                      rama=rama), permiso="default")
        sin_pegar = await pegar_mensajes_nuevos(creado, f"ntm-{ident[:40]}", nombre, origen="programada")
        return {**creado, "pegado": not sin_pegar}

    def pane_abierto(pane_id: str) -> bool:
        return any(a.get("pane_id") == pane_id for a in board_agents(hub.board or {}))

    programadas = Programadas(data_directory, lanzar_claude=lanzar_programada_claude,
                              cursor_runner=lambda: getattr(app.state, "cursor_runner", None),
                              plan_cwds=lambda: cfg.plan_cwds, sesion_abierta=pane_abierto,
                              emit=emit_all, avisar=tnotify)
    app.state.programadas = programadas

    async def programadas_startup():
        if not os.environ.get("ORQ_NO_AUTOINDEX"):
            spawn(programadas.bucle())

    app.router.on_startup.append(programadas_startup)
    api.include_router(programadas_router(programadas, limiter, verify_pin, cfg.pin))
    api.include_router(notas_router(notas, emit_all))
    # (fin pista-E2)
    api.include_router(mrs_router(mrs, redactor, limiter, verify_pin, cfg.pin))
    api.include_router(entornos_router(cfg, entornos_runner))
    api.include_router(kit_router(**(kit_opts or {})))

    def contexto_pieza(nombre: str) -> piezas_mod.ContextoPieza:
        return piezas_mod.ContextoPieza(api=api, cfg=cfg, data_directory=data_directory, push=push, spawn=spawn,
                                        opciones=(piezas_opts or {}).get(nombre, {}),
                                        inicio=inicio_piezas, cierre=cierre_piezas)

    if piezas is None or piezas:
        piezas_mod.montar_todas(piezas_mod.descubrir(piezas_paquete), contexto_pieza, piezas)
    app.include_router(public)
    app.include_router(api)

    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def api_inexistente(path: str):
        raise HTTPException(status_code=404)

    def _spa_cache_headers(rel: str, *, fallback_index: bool = False) -> Optional[dict]:
        if fallback_index or rel == "index.html" or rel == "sw.js":
            return {"Cache-Control": "no-cache"}
        if rel.startswith("assets/"):
            return {"Cache-Control": "public, max-age=31536000, immutable"}
        return None

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = dist / "index.html"
        if not index.is_file():
            return HTMLResponse(MISSING_BUILD)
        target = (dist / path).resolve()
        if path and target.is_file() and dist.resolve() in target.parents:
            hdrs = _spa_cache_headers(path.replace("\\", "/"))
            if hdrs:
                return FileResponse(target, headers=hdrs)
            return FileResponse(target)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
