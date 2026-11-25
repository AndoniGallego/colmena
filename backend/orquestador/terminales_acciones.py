"""Acciones sobre terminales no-Claude: Ctrl+C y repetir (nivel 2). Auditoría y avisos. Solo con un POST del usuario."""
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .dialogo import visibles
from .enchufe import NoDisponible, TerminalesError, Tiempo
from .enchufe.modelo import Lanzamiento
from .guardian.lanzador import MODOS_INTERNOS, MODOS_POR_LANZAMIENTO, carpeta_de_modo, es_carpeta_interna
from .nueva_tarea import (Worktrees, borrar_copia, base_por_defecto, crear_worktree, es_raiz_repo, mensaje_ticket,
                          nombre_pestana, nombre_ticket, quitar_recien_creado, rama_existe, rama_para, ruta_libre,
                          slug_de, validar_rama, validar_ticket)
from .preparar_copia import (ConfianzaPreparar, ENV_RUTA, HEX64, coincide_en_copia, comando_setup, copiar_ignorados,
                             escribir_env, hay_compose, leer_setup, payload_confianza, sufijo_mensaje, sufijo_maximo,
                             validar_origenes, verificar_ignorados)
from .nueva_terminal import (NUEVA_LIMIT, agente_unico, enumerar_carpetas, grupos_desde_tablero, normalizar_nombre,
                             slug_agente, validar_carpeta)
from .sesiones_viejas import SesionesViejas, validar_uuid
from .terminales import (OCULTO, TECLAS, SlidingLimit, Terminales, clean, huella_de, merged_panes, pane_cwd, short_cwd,
                         redactar, titulo_de)
from .traspaso import CONTROL_RE, TraspasoError, _now, check_label

log = logging.getLogger("orquestador.terminales")

ESPERA_LISTO = 90.0

ID_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"
GRUPO_PATTERN = r"^g\d{1,6}$"
GRUPO_RE = re.compile(GRUPO_PATTERN)
AUDIT_FILE = "terminales-auditoria.jsonl"
AUDIT_MAX_BYTES = 1024 * 1024
AUDIT_MAX_LIMIT = 50
MAX_COMMAND = 500
MAX_RAPIDOS = 12
MAX_PENDIENTES = 50
MAX_IDS = 500
NOTIFY_TIMEOUT = 3.0
CTRL_C_LIMIT = (10, 60.0)
REPETIR_LIMIT = (6, 60.0)
CERRAR_LIMIT = (10, 60.0)
RENOMBRAR_LIMIT = (30, 60.0)
PREVIEW_LIMIT = (60, 60.0)
COMANDO_LIMITS = ((6, 60.0), (40, 3600.0))
VENTANA_OPENS = (10, 3600.0)
VENTANA_ABS = 300.0
VENTANA_IDLE = 120.0
HEADER_TOKEN = "x-orq-escritura"

# Ocupan lugar pero no se ven, o parecen un espacio común: lo que se confirma tiene que ser lo que se lee.
_INVISIBLES = frozenset("\u115f\u1160\u3164\uffa0\u2800")
_PROHIBIDAS = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")
# Default_Ignorable_Code_Point (Unicode DerivedCoreProperties): incluye marcas Mn que no se ven, como los
# selectores de variación, que pegados a una ruta la cambian sin que se note.
_IGNORABLES = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
               (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
               (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
               (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF))


def _ignorable(c: str) -> bool:
    o = ord(c)
    return any(a <= o <= b for a, b in _IGNORABLES)


def _caracter_prohibido(c: str) -> bool:
    cat = unicodedata.category(c)
    return cat in _PROHIBIDAS or (cat == "Zs" and c != " ") or c in _INVISIBLES or _ignorable(c)


def validar_comando(raw: str) -> str:
    """Normaliza a NFC y valida una línea de comando; devuelve el texto o lanza TraspasoError(400)."""
    text = unicodedata.normalize("NFC", raw or "")
    bad = "el comando tiene caracteres no permitidos"
    if not 1 <= len(text) <= MAX_COMMAND:
        raise TraspasoError(400, f"el comando tiene que tener entre 1 y {MAX_COMMAND} caracteres")
    if any(_caracter_prohibido(c) for c in text):
        raise TraspasoError(400, bad)
    if text != text.strip(" ") or not text.strip():
        raise TraspasoError(400, "el comando no puede empezar ni terminar con espacios")
    if text.startswith("-"):
        raise TraspasoError(400, "el comando no puede empezar con -")
    if text.endswith("\\"):
        # Con `\` al final el Enter agrega una línea en vez de mandar el comando.
        raise TraspasoError(400, "el comando no puede terminar con \\")
    return text


def rapidos_validos(raw) -> list:
    out = []
    for item in raw if isinstance(raw, list) else []:
        try:
            if not isinstance(item, str):
                raise TraspasoError(400, "no es texto")
            out.append(validar_comando(item))
        except TraspasoError as exc:
            log.warning("comando rápido descartado: %s", exc.detail)
        if len(out) >= MAX_RAPIDOS:
            break
    return out


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreviewBody(_Body):
    pane_id: str = Field(..., max_length=64)


class AccionBody(_Body):
    id: str = Field(..., pattern=ID_PATTERN)
    pane_id: str = Field(..., max_length=64)
    huella: str = Field(..., min_length=1, max_length=64)


class ConfirmarBody(_Body):
    id: str = Field(..., pattern=ID_PATTERN)
    pane_id: str = Field(..., max_length=64)
    huella2: str = Field(..., min_length=1, max_length=64)
    ejecutar: bool


class VentanaBody(_Body):
    pin: str = Field(..., min_length=1, max_length=64)


class ComandoBody(_Body):
    id: str = Field(..., pattern=ID_PATTERN)
    pane_id: str = Field(..., max_length=64)
    huella: str = Field(..., min_length=1, max_length=64)
    comando: str = Field("", max_length=MAX_COMMAND + 100)
    rapido: Optional[int] = Field(None, ge=0, lt=MAX_RAPIDOS)


class RenombrarBody(_Body):
    tipo: Literal["grupo", "pestana"]
    id: str = Field(..., pattern=r"^g\d{1,6}(:t\d{1,6})?$")
    nombre: str = Field(..., max_length=200)


class NuevaBody(_Body):
    id: str = Field(..., pattern=ID_PATTERN)
    carpeta: str = Field(..., max_length=1024)
    tipo: Literal["shell", "claude"]
    nombre: Optional[str] = Field(None, max_length=60)
    grupo: Optional[str] = Field(None, pattern=GRUPO_PATTERN)


class NuevaTareaBody(_Body):
    id: str = Field(..., pattern=ID_PATTERN)
    repo: str = Field(..., max_length=1024)
    tarea: str = Field(..., max_length=4000)
    nombre: Optional[str] = Field(None, max_length=60)
    rama: Optional[str] = Field(None, max_length=80)
    grupo: Optional[str] = Field(None, pattern=GRUPO_PATTERN)
    ticket: Optional[str] = Field(None, max_length=20)


class ConfiarPrepararBody(_Body):
    repo: str = Field(..., max_length=1024)
    setup_sha256: str = Field(..., pattern=HEX64.pattern)
    script_sha256: Optional[str] = Field(None, pattern=HEX64.pattern)


class BorrarCopiaBody(_Body):
    ruta: str = Field(..., max_length=1024)


class RetomarViejaBody(_Body):
    id: str = Field(..., pattern=ID_PATTERN)
    session_id: str = Field(..., min_length=8, max_length=80)
    nombre: Optional[str] = Field(None, max_length=60)
    grupo: Optional[str] = Field(None, pattern=GRUPO_PATTERN)
    nombre_tarjeta: Optional[str] = Field(None, max_length=60)


@dataclass
class Ctx:
    ip: str = "?"
    user: str = ""
    device: str = ""
    cookie: str = ""
    token: str = ""


class Ventana:
    """Una sola ventana de escritura en todo el servidor, solo en memoria; el token nunca se guarda en claro."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._w: Optional[dict] = None

    def abrir(self, cookie: str, ip: str) -> str:
        token = secrets.token_urlsafe(32)
        now = self.clock()
        self._w = {"token": _hash(token), "cookie": _hash(cookie), "ip": ip, "abierta": now, "uso": now}
        return token

    def cerrar(self) -> bool:
        was = self.abierta()
        self._w = None
        return was

    def _remaining(self) -> tuple:
        now = self.clock()
        w = self._w
        return (w["abierta"] + VENTANA_ABS - now, w["uso"] + VENTANA_IDLE - now) if w else (0.0, 0.0)

    def abierta(self) -> bool:
        if self._w is None:
            return False
        absolute, idle = self._remaining()
        if absolute <= 0 or idle <= 0:
            self._w = None
            return False
        return True

    def estado(self) -> dict:
        if not self.abierta():
            return {"abierta": False, "vence_en": 0, "inactividad_en": 0}
        absolute, idle = self._remaining()
        return {"abierta": True, "vence_en": int(absolute), "inactividad_en": int(min(idle, absolute))}

    def validar(self, token: str, cookie: str, ip: str) -> str:
        """Devuelve "" si sirve; si no, el motivo ("vencida" o "invalida") y la ventana queda cerrada."""
        if self._w is None:
            return "invalida"
        if not self.abierta():
            return "vencida"
        w = self._w
        same = (secrets.compare_digest(w["token"], _hash(token or "")) and
                secrets.compare_digest(w["cookie"], _hash(cookie or "")) and w["ip"] == ip)
        if not same:
            self._w = None
            return "invalida"
        return ""

    def usar(self) -> None:
        if self._w is not None:
            self._w["uso"] = self.clock()


class Audit:
    """JSONL 0600 con rotación a `.1` al pasar 1 MB: nunca más de dos archivos."""

    def __init__(self, directory: Path, max_bytes: int = AUDIT_MAX_BYTES):
        self.path = directory / AUDIT_FILE
        self.old = directory / (AUDIT_FILE + ".1")
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    def write(self, entry: dict) -> None:
        line = (json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        with self._lock:
            try:
                if self.path.exists() and self.path.stat().st_size > self.max_bytes:
                    os.replace(self.path, self.old)
                    os.chmod(self.old, 0o600)
                fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
                try:
                    os.fchmod(fd, 0o600)
                    os.write(fd, line)
                finally:
                    os.close(fd)
            except OSError as exc:
                log.warning("no pude escribir la auditoría: %s", type(exc).__name__)

    def recent(self, limit: int = 20) -> list:
        limit = min(max(limit, 1), AUDIT_MAX_LIMIT)
        out: list = []
        with self._lock:
            for path in (self.path, self.old):
                try:
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                for raw in reversed(lines):
                    try:
                        item = json.loads(raw)
                    except ValueError:
                        continue
                    if isinstance(item, dict):
                        out.append(item)
                    if len(out) >= limit:
                        return out
        return out


def last_line(text: str) -> str:
    for line in reversed((text or "").splitlines()):
        if line.strip():
            return visibles(CONTROL_RE.sub(" ", line.rstrip()))[:MAX_COMMAND]
    return ""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class _Op:
    """Lo que se sabe de una acción mientras avanza, para auditar también los rechazos."""

    def __init__(self, ctx: Ctx, accion: str, pane_id: str = ""):
        self.ctx = ctx
        self.accion = accion
        self.pane_id = pane_id
        self.pane: Optional[dict] = None
        self.snapshot: Optional[dict] = None
        self.proceso = ""
        self.comando = ""
        self.rapido = False
        self.estado = "desconocido"
        # Desde que se manda la primera tecla, el id queda gastado aunque herdr falle o no conteste.
        self.tocado = False


class TerminalActions:
    def __init__(self, terminales: Terminales, enchufe, locks, audit: Audit, enabled: Callable[[], bool],
                 notify: Optional[Callable[[str, str, str], Awaitable]] = None, rapidos: Optional[list] = None,
                 clock: Optional[Callable[[], float]] = None, limiter=None, verify=None, pin: str = "",
                 plan_cwds: Callable[[], list] = lambda: [],
                 sesiones_viejas: Optional[SesionesViejas] = None, estados=None,
                 worktrees: Optional[Worktrees] = None, cierres=None,
                 fijados: Callable[[], frozenset] = lambda: frozenset(),
                 confianza: Optional[ConfianzaPreparar] = None, preparar: Callable[[], dict] = lambda: {},
                 puertos_colmena: Callable[[], frozenset] = lambda: frozenset()):
        self.t = terminales
        self.fijados = fijados
        self.cierres = cierres
        self.enchufe = enchufe
        self.estados = estados
        self.locks = locks
        self.audit = audit
        self.enabled = enabled
        self.notify = notify
        self.rapidos = rapidos or []
        self.limit = SlidingLimit(clock) if clock else SlidingLimit()
        self._ids: OrderedDict = OrderedDict()
        self._inflight: set = set()
        self._pendientes: OrderedDict = OrderedDict()
        self._nueva_cache: OrderedDict = OrderedDict()
        self.ventana = Ventana(clock) if clock else Ventana()
        self.limiter = limiter
        self.verify = verify
        self.pin = pin
        self.worktrees = worktrees
        self.confianza = confianza
        self.preparar = preparar
        self.puertos_colmena = puertos_colmena
        self.plan_cwds = lambda: [*plan_cwds(), *(worktrees.rutas() if worktrees else [])]
        self.sesiones_viejas = sesiones_viejas
        self._retomar_cache: OrderedDict = OrderedDict()

    # ---------- piezas comunes ----------

    def _record(self, op: _Op, ok: bool, error: str = "", accion: Optional[str] = None) -> None:
        pane = op.pane or {}
        snap = op.snapshot or {}
        self.audit.write({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "accion": accion or op.accion,
            "ip": op.ctx.ip, "tailscale_user": op.ctx.user, "dispositivo": op.ctx.device[:80],
            "pane_id": op.pane_id, "terminal_id": pane.get("terminal_id") or "",
            "workspace": clean(self.t.workspace_label(snap, pane.get("workspace_id")), 60) if pane else "",
            "tab": clean(self.t.tab_label(snap, pane.get("tab_id")), 60) if pane else "",
            "cwd": clean(pane_cwd(pane), 200) if pane else "", "proceso": op.proceso,
            "comando": redactar(op.comando)[:MAX_COMMAND], "rapido": op.rapido, "ok": ok,
            "error": redactar(error)[:200],
        })

    async def _push(self, op: _Op, title: str, body: str, tag: str) -> None:
        if self.notify is None:
            return
        try:
            await self.notify(title, body, tag, op.pane_id)
        except Exception as exc:
            log.warning("aviso de terminal falló: %s", type(exc).__name__)

    def _workspace(self, op: _Op) -> str:
        if not (op.pane and op.snapshot):
            return "terminal"
        return clean(self.t.workspace_label(op.snapshot, op.pane.get("workspace_id")), 60) or "terminal"

    def _gate(self, op: _Op) -> None:
        if not self.enabled():
            raise TraspasoError(403, "escritura apagada")

    def _fresh_id(self, op_id: str) -> None:
        if op_id in self._ids or op_id in self._inflight:
            raise TraspasoError(409, "ya se hizo")

    def _used(self, op_id: str) -> None:
        self._ids[op_id] = True
        while len(self._ids) > MAX_IDS:
            self._ids.popitem(last=False)

    def _rate(self, key: str, *limits: tuple) -> None:
        wait = self.limit.hit(key, *limits)
        if wait:
            raise TraspasoError(429, "demasiadas acciones seguidas", {"retry_after": wait})

    async def _check_target(self, op: _Op, huella: str) -> dict:
        """Snapshot y proceso frescos (nunca la caché del tablero): la huella cubre pane, cwd y proceso."""
        snap = await self.t.snapshot(fresh=True)
        op.snapshot = snap
        pane = self.t.locate(snap, op.pane_id)
        op.pane = pane
        info = await self.t.info.get(op.pane_id, ttl=0)
        op.proceso = info["proceso"] or ""
        op.estado = info["estado"]
        self.t.check_proceso(info)
        if not secrets.compare_digest(huella_de(pane, op.proceso), huella or ""):
            raise TraspasoError(409, "la terminal cambió, revisala de nuevo")
        return pane

    def _need_shell(self, op: _Op) -> None:
        if op.estado == "prompt":
            return
        if op.estado == "desconocido":
            raise TraspasoError(409, "no pude confirmar qué programa corre: probá de nuevo")
        raise TraspasoError(409, f"hay un programa corriendo ({op.proceso}): frenalo primero")

    async def _llamar(self, coro: Awaitable) -> str:
        try:
            return await coro
        except (TerminalesError, OSError) as exc:
            raise TraspasoError(502, f"Las terminales no respondieron: {str(exc)[:150]}")

    async def _read_visible(self, op: _Op) -> str:
        return await self._llamar(self.enchufe.leer(op.pane_id, fuente="visible"))

    def _pane_info(self, snap: dict, pane: dict) -> dict:
        return {
            "workspace": clean(self.t.workspace_label(snap, pane.get("workspace_id")), 60),
            "tab": clean(self.t.tab_label(snap, pane.get("tab_id")), 60),
            "titulo": titulo_de(pane),
            "cwd": clean(pane_cwd(pane), 500),
        }

    def rechazo(self, ctx: Ctx, accion: str) -> None:
        self._record(_Op(ctx, accion), False, "escritura apagada", "rechazo")

    # ---------- lectura ----------

    def config(self) -> dict:
        return {"escritura": bool(self.enabled()), "comandos_rapidos": list(self.rapidos),
                "ventana": self.ventana.estado()}

    async def preview(self, body: PreviewBody) -> dict:
        # Cada vista previa lanza herdr (snapshot y proceso frescos): con tope, aunque no escriba nada.
        self._rate("preview", PREVIEW_LIMIT)
        snap = await self.t.snapshot(fresh=True)
        pane = self.t.locate(snap, body.pane_id)
        info = await self.t.info.get(body.pane_id, ttl=0)
        self.t.check_proceso(info)
        estado = info["estado"]
        return {"huella": huella_de(pane, info["proceso"] or ""), "pane_id": body.pane_id, **self._pane_info(snap, pane),
                "proceso": info["proceso"] or "", "estado": estado, "protegida": False,
                "cierra": self.alcance_de_cierre(snap, pane), **self.t.escritura(estado)}

    def entradas(self, limit: int) -> dict:
        return {"entradas": self.audit.recent(limit)}

    async def carpetas_disponibles(self) -> dict:
        plan = self.plan_cwds()
        out = {"carpetas": enumerar_carpetas(plan), "grupos": []}
        g = self._guardian_backend_optional()
        if g is not None:
            try:
                tab = await g.tablero()
                out["grupos"] = grupos_desde_tablero(tab, plan)
            except (NoDisponible, TerminalesError):
                pass
        return out

    async def grupo_de_sesion(self, pane_id: str) -> Optional[str]:
        g = self._guardian_backend_optional()
        if g is None or not pane_id:
            return None
        try:
            tab = await g.tablero()
        except (NoDisponible, TerminalesError):
            return None
        ses = next((s for s in tab.sesiones if s.id == pane_id), None)
        if ses is None or not GRUPO_RE.fullmatch(ses.espacio_id or ""):
            return None
        return ses.espacio_id

    def _guardian_backend_optional(self):
        fn = getattr(self.enchufe, "_backend_nombre", None)
        if fn is None:
            return None
        try:
            return fn("guardian")
        except (NoDisponible, TerminalesError):
            return None

    def _guardian_backend(self):
        fn = getattr(self.enchufe, "_backend_nombre", None)
        if fn is None:
            raise TraspasoError(503, "Las terminales propias no responden: no abrí nada")
        try:
            return fn("guardian")
        except (NoDisponible, TerminalesError):
            raise TraspasoError(503, "Las terminales propias no responden: no abrí nada")

    async def renombrar(self, ctx: Ctx, body: RenombrarBody) -> dict:
        """Renombra un grupo (g1) o una pestaña (g1:t1) del guardián. Los grupos fijados no se tocan."""
        op = _Op(ctx, "renombrar_grupo" if body.tipo == "grupo" else "renombrar_pestana", body.id)
        try:
            es_pestana = ":" in body.id
            if es_pestana != (body.tipo == "pestana"):
                raise TraspasoError(400, "el id no coincide con el tipo")
            nombre = CONTROL_RE.sub(" ", body.nombre).strip()
            if not nombre:
                raise TraspasoError(400, "El nombre no puede estar vacío")
            nombre = check_label(nombre)
            self._rate("renombrar", RENOMBRAR_LIMIT)
            g = self._guardian_backend()
            try:
                tab = await g.tablero()
                espacio_id = body.id.split(":", 1)[0]
                espacio = next((e for e in tab.espacios if e.id == espacio_id), None)
                if espacio is None or (es_pestana and not any(l.id == body.id for l in tab.lineas)):
                    raise TraspasoError(409, "Eso ya no está: no cambié nada")
                if espacio.nombre.strip().casefold() in self.fijados():
                    raise TraspasoError(403, "Ese grupo está fijado: no se renombra")
                await g.renombrar(body.id, nombre)
            except (NoDisponible, TerminalesError) as exc:
                raise TraspasoError(503, "Las terminales propias no responden: no cambié nada") from exc
        except TraspasoError as exc:
            self._record(op, False, exc.detail, "rechazo")
            raise
        self._record(op, True)
        return {"ok": True, "id": body.id, "nombre": nombre}

    async def nueva(self, ctx: Ctx, body: NuevaBody) -> dict:
        cached = self._nueva_cache.get(body.id)
        if cached is not None:
            return cached
        if body.id in self._inflight:
            raise TraspasoError(409, "Ya la estoy abriendo")
        self._inflight.add(body.id)
        try:
            return await self._nueva(ctx, body)
        finally:
            self._inflight.discard(body.id)

    async def _nueva(self, ctx: Ctx, body: NuevaBody) -> dict:
        op = _Op(ctx, "nueva_terminal")
        try:
            wait = self.limit.hit("nueva", NUEVA_LIMIT)
            if wait:
                raise TraspasoError(429, "Llegaste al tope de 6 terminales nuevas por hora", {"retry_after": wait})
            cwd = validar_carpeta(body.carpeta, self.plan_cwds())
            nombre = normalizar_nombre(body.nombre, cwd)
            g = self._guardian_backend()
            try:
                if body.grupo:
                    tab = await g.tablero()
                    if not any(e.id == body.grupo for e in tab.espacios):
                        raise TraspasoError(409, "Ese grupo ya no está: no abrí nada")
                    creado = await g.crear_linea(body.grupo, nombre, cwd)
                else:
                    creado = await g.crear_espacio(nombre, cwd)
            except TraspasoError:
                raise
            except (NoDisponible, TerminalesError) as exc:
                raise TraspasoError(503, "Las terminales propias no responden: no abrí nada") from exc
            op.pane_id = creado.sesion_id
            if body.tipo == "claude":
                snap = await self.t.snapshot(fresh=True)
                usados = set()
                for agent in snap.get("agents", []):
                    for key in ("name", "agent_name"):
                        if agent.get(key):
                            usados.add(agent[key])
                agente = agente_unico(slug_agente(nombre), usados)
                try:
                    await g.arrancar_claude(creado.sesion_id, agente)
                except (NoDisponible, TerminalesError) as exc:
                    raise TraspasoError(503, "Abrí la terminal pero Claude no arrancó: podés arrancarlo desde ahí") from exc
            espacio_id = creado.espacio_id or body.grupo
            out = {"ok": True, "espacio_id": espacio_id, "sesion_id": creado.sesion_id}
        except TraspasoError as exc:
            self._record(op, False, exc.detail, "rechazo")
            raise
        self._record(op, True, accion=f"nueva_{body.tipo}")
        titulo = f"Claude nuevo en {nombre}" if body.tipo == "claude" else f"Terminal nueva en {nombre}"
        await self._push(op, titulo, ctx.device, f"terminal-nueva-{body.tipo}")
        self._nueva_cache[body.id] = out
        while len(self._nueva_cache) > MAX_IDS:
            self._nueva_cache.popitem(last=False)
        return out

    async def nueva_tarea(self, ctx: Ctx, body: NuevaTareaBody, *, permiso: str | None = None,
                          nota_ajena: bool = False) -> dict:
        """Copia del repo (git worktree) con rama propia y una sesión de Claude adentro con la tarea."""
        clave = f"nt-{body.id}"
        cached = self._nueva_cache.get(clave)
        if cached is not None:
            return {**cached, "repetido": True}
        if clave in self._inflight:
            raise TraspasoError(409, "Ya la estoy abriendo")
        if self.worktrees is None:
            raise TraspasoError(503, "Nueva tarea no está disponible")
        self._inflight.add(clave)
        try:
            out = await self._nueva_tarea(ctx, body, permiso, nota_ajena)
        finally:
            self._inflight.discard(clave)
        self._nueva_cache[clave] = out
        while len(self._nueva_cache) > MAX_IDS:
            self._nueva_cache.popitem(last=False)
        return out

    def _override_preparar(self, repo: str) -> Optional[dict]:
        for clave, valor in (self.preparar() or {}).items():
            if isinstance(valor, dict) and os.path.realpath(os.path.expanduser(str(clave))) == repo:
                return valor
        return None

    @staticmethod
    def _requiere_confianza(repo: str, base: str, setup) -> TraspasoError:
        detalle = ("Este repo prepara la copia con un script: revisalo antes de confiar" if setup.script
                   else "Este repo prepara la copia (copia archivos ignorados): revisalo antes de confiar")
        return TraspasoError(409, detalle, {"codigo": "requiere_confianza",
                                            "confianza": payload_confianza(repo, base, setup)})

    def _preparar_copia(self, repo: str, ruta: str, rama: str, base: str, setup, existentes: list) -> Optional[int]:
        """Pasos sincrónicos sobre la copia ya creada. Devuelve el puerto reservado (None si no se pidió)."""
        if not coincide_en_copia(ruta, setup):
            actual = leer_setup(repo, base, self._override_preparar(repo)) or setup
            raise self._requiere_confianza(repo, base, actual)
        verificar_ignorados(ruta, [ENV_RUTA, *existentes])
        copiar_ignorados(repo, ruta, existentes)
        compose = hay_compose(ruta)
        pedir = setup.puertos is not None and not (compose and setup.docker != "puertos-variables")
        puerto = self.worktrees.reservar({"ruta": ruta, "repo": repo, "rama": rama, "base": base,
                                          "puertos": setup.puertos}, pedir,
                                         frozenset(self.puertos_colmena()))
        escribir_env(ruta, puerto, setup.puertos if puerto is not None else None, compose)
        return puerto

    async def _nueva_tarea(self, ctx: Ctx, body: NuevaTareaBody, permiso: str | None = None,
                           nota_ajena: bool = False) -> dict:
        op = _Op(ctx, "nueva_tarea")
        tarea = body.tarea.strip()
        try:
            clave = validar_ticket(body.ticket) if body.ticket and body.ticket.strip() else None
            if not clave and not tarea:
                raise TraspasoError(400, "Contá qué hay que hacer")
            repo = validar_carpeta(body.repo, [r for r in self.plan_cwds() if r not in self.worktrees.rutas()])
            if not es_raiz_repo(repo):
                raise TraspasoError(400, "Esa carpeta no es la raíz de un repo de git")
            base = await asyncio.to_thread(base_por_defecto, repo)
            setup = existentes = omitidos = None
            if clave:
                rama = f"feature/{clave}"
                if body.rama and body.rama.strip() and body.rama.strip() != rama:
                    raise TraspasoError(400, f"Con ticket la rama es {rama}")
                if await asyncio.to_thread(rama_existe, repo, rama):
                    raise TraspasoError(409, f"Ya hay una rama {rama}: retomá esa tarea o borrala antes")
                if self.confianza is not None:
                    setup = await asyncio.to_thread(leer_setup, repo, base, self._override_preparar(repo))
                nota, slug = tarea, slug_de(clave)
                tarea = mensaje_ticket(clave, rama, nota, sufijo_maximo(setup.script) if setup else "", ajena=nota_ajena)
                nombre_base = nombre_ticket(clave, nota)
            else:
                rama = validar_rama(body.rama.strip()) if body.rama and body.rama.strip() else \
                    rama_para(os.path.basename(repo), tarea)
                slug, nombre_base = slug_de(tarea), nombre_pestana(tarea)
            nombre = normalizar_nombre(body.nombre.strip() if body.nombre else nombre_base, repo)
            if setup:
                if not self.confianza.hay(repo, setup.toml_sha, setup.script_sha):
                    raise self._requiere_confianza(repo, base, setup)
                existentes, omitidos = await asyncio.to_thread(validar_origenes, repo, base, setup)
            ruta = ruta_libre(repo, slug)
            await asyncio.to_thread(crear_worktree, repo, rama, ruta, base)
            try:
                preparar = None
                if setup:
                    puerto = await asyncio.to_thread(self._preparar_copia, repo, ruta, rama, base, setup, existentes)
                    compose = hay_compose(ruta)
                    fijos = compose and setup.docker != "puertos-variables"
                    tarea = mensaje_ticket(clave, rama, nota, sufijo_mensaje(setup.script, puerto, setup.puertos, fijos),
                                           ajena=nota_ajena)
                    preparar = {"puerto": puerto, "puertos": setup.puertos if puerto is not None else None,
                                "copiados": existentes, "omitidos": omitidos, "setup_pane_id": None,
                                "puertos_fijos": fijos}
                else:
                    self.worktrees.agregar({"ruta": ruta, "repo": repo, "rama": rama, "base": base})
                if setup and setup.script:
                    comando = comando_setup(setup.script)
                    item = {"pestanas": [{"tipo": "claude", "nombre": nombre, "carpeta": ruta, "mensaje": tarea},
                                         {"tipo": "terminal", "nombre": "setup", "carpeta": ruta, "comando": comando}]}
                else:
                    item = {"carpeta": ruta, "nombre": nombre, "mensaje": tarea}
                creado = await self.abrir_desde_pedido_pestana(ctx, item, idempotencia=body.id, grupo=body.grupo,
                                                               permiso=permiso,
                                                               **({"ejecutar_comandos": True} if setup and setup.script else {}))
            except BaseException as exc:
                abiertos = exc.extra.get("abiertos") if isinstance(exc, TraspasoError) else None
                if abiertos:
                    # Claude ya está adentro de la copia: borrarla sería peor que dejarla sin la terminal de setup.
                    raise TraspasoError(503, f"Abrí Claude pero no la terminal de setup: corré `{comando}` a mano en la copia"
                                        if setup and setup.script else exc.detail, exc.extra) from exc
                self.worktrees.quitar(ruta)
                await asyncio.to_thread(quitar_recien_creado, repo, rama, ruta, base)
                raise
        except TraspasoError as exc:
            self._record(op, False, exc.detail, "rechazo")
            raise
        self._record(op, True, accion="nueva_tarea")
        out = {**creado, "ruta": ruta, "rama": rama, "base": base, "tarea": tarea}
        if preparar is not None:
            if setup.script and len(creado.get("pane_ids") or []) > 1:
                preparar["setup_pane_id"] = creado["pane_ids"][1]
            out["preparar"] = preparar
        return out

    async def confiar_preparar(self, ctx: Ctx, body: ConfiarPrepararBody) -> dict:
        """Guarda la confianza en el setup (toml + script) del repo, atada a los hashes que Ando vio."""
        op = _Op(ctx, "confiar_preparar")
        try:
            if self.worktrees is None or self.confianza is None:
                raise TraspasoError(503, "Nueva tarea no está disponible")
            repo = validar_carpeta(body.repo, [r for r in self.plan_cwds() if r not in self.worktrees.rutas()])
            if not es_raiz_repo(repo):
                raise TraspasoError(400, "Esa carpeta no es la raíz de un repo de git")
            base = await asyncio.to_thread(base_por_defecto, repo)
            setup = await asyncio.to_thread(leer_setup, repo, base, self._override_preparar(repo))
            if setup is None:
                raise TraspasoError(400, "Este repo no tiene nada que preparar")
            if body.setup_sha256 != setup.toml_sha or body.script_sha256 != setup.script_sha:
                raise self._requiere_confianza(repo, base, setup)
            self.confianza.guardar(repo, setup.toml_sha, setup.script_sha)
        except TraspasoError as exc:
            self._record(op, False, exc.detail, "rechazo")
            raise
        self._record(op, True, accion="confiar_preparar")
        return {"ok": True}

    async def borrar_copia(self, ctx: Ctx, body: BorrarCopiaBody) -> dict:
        """Quita la copia que creó Colmena si no se pierde trabajo (sin cambios y rama integrada)."""
        op = _Op(ctx, "borrar_copia")
        try:
            entrada = self.worktrees.get(body.ruta) if self.worktrees else None
            if entrada is None:
                raise TraspasoError(404, "Esa copia no la creó Colmena")
            await asyncio.to_thread(borrar_copia, entrada)
            self.worktrees.quitar(entrada["ruta"])
        except TraspasoError as exc:
            self._record(op, False, exc.detail, "rechazo")
            raise
        self._record(op, True, accion="borrar_copia")
        return {"ok": True}

    def listar_sesiones_viejas(self, q: str = "") -> list:
        if self.sesiones_viejas is None:
            return []
        return self.sesiones_viejas.listar(q)

    async def retomar_sesion_vieja(self, ctx: Ctx, body: RetomarViejaBody) -> dict:
        cached = self._retomar_cache.get(body.id)
        if cached is not None:
            return cached
        if body.id in self._inflight:
            raise TraspasoError(409, "Ya la estoy abriendo")
        self._inflight.add(body.id)
        try:
            return await self._retomar_sesion_vieja(ctx, body)
        finally:
            self._inflight.discard(body.id)

    async def _retomar_sesion_vieja(self, ctx: Ctx, body: RetomarViejaBody) -> dict:
        if self.sesiones_viejas is None:
            raise TraspasoError(503, "No pude retomarla")
        op = _Op(ctx, "retomar_sesion_vieja")
        try:
            validar_uuid(body.session_id)
            wait = self.limit.hit("nueva", NUEVA_LIMIT)
            if wait:
                raise TraspasoError(429, "Llegaste al tope de pestañas por hora", {"retry_after": wait})
            found = self.sesiones_viejas.encontrar(body.session_id)
            if found is None:
                raise TraspasoError(404, "Esa sesión ya no se puede retomar")
            _path, meta = found
            cwd = validar_carpeta(meta.cwd, self.plan_cwds())
            sid = body.session_id
            if sid in self.sesiones_viejas.abiertas():
                raise TraspasoError(409, "Esa sesión ya está abierta en el tablero")
            g = self._guardian_backend()
            try:
                tab = await g.tablero()
            except (NoDisponible, TerminalesError) as exc:
                raise TraspasoError(503, "No pude retomarla") from exc
            if any(s.claude_session_id == sid for s in tab.sesiones if s.claude_session_id):
                raise TraspasoError(409, "Esa sesión ya está abierta en el tablero")
            nombre_tab = normalizar_nombre(body.nombre, cwd)
            if body.grupo:
                if not any(e.id == body.grupo for e in tab.espacios):
                    raise TraspasoError(409, "Ese grupo ya no está: no abrí nada")
                creado = await g.crear_linea(body.grupo, nombre_tab, cwd, Lanzamiento("claude", resume=sid))
            else:
                ws = normalizar_nombre(body.nombre_tarjeta or body.nombre, cwd)
                creado = await g.crear_espacio(ws, cwd)
                snap = await self.t.snapshot(fresh=True)
                usados = set()
                for agent in snap.get("agents", []):
                    for key in ("name", "agent_name"):
                        if agent.get(key):
                            usados.add(agent[key])
                agente = agente_unico(slug_agente(nombre_tab), usados)
                try:
                    await g.arrancar_claude(creado.sesion_id, agente, resume=sid)
                except (NoDisponible, TerminalesError) as exc:
                    raise TraspasoError(503, "No pude retomarla") from exc
                if creado.linea_id and nombre_tab.strip().casefold() != ws.strip().casefold():
                    try:
                        await g.renombrar(creado.linea_id, nombre_tab)
                    except (NoDisponible, TerminalesError):
                        pass
            op.pane_id = creado.sesion_id
            espacio_id = creado.espacio_id or body.grupo
            out = {"ok": True, "espacio_id": espacio_id, "sesion_id": creado.sesion_id, "pane_id": creado.sesion_id}
        except TraspasoError as exc:
            self._record(op, False, exc.detail, "rechazo")
            raise
        self._record(op, True, accion="retomar_sesion_vieja")
        titulo = f"Claude retomado: {nombre_tab}"
        await self._push(op, titulo, ctx.device, "terminal-retomar")
        self._retomar_cache[body.id] = out
        while len(self._retomar_cache) > MAX_IDS:
            self._retomar_cache.popitem(last=False)
        return out

    async def _agente_claude(self, nombre_tab: str) -> str:
        snap = await self.t.snapshot(fresh=True)
        usados: set[str] = set()
        for agent in snap.get("agents", []):
            for key in ("name", "agent_name"):
                if agent.get(key):
                    usados.add(agent[key])
        return agente_unico(slug_agente(nombre_tab), usados)

    @staticmethod
    def _lanzamiento(tipo: str, permiso: str | None) -> tuple[Lanzamiento, bool]:
        """Con `permiso`, Claude no se lanza al crear la línea (iría en el modo global): se abre un shell
        y después se arranca Claude con el modo pedido."""
        if tipo != "claude":
            return Lanzamiento("shell"), False
        if permiso is None:
            return Lanzamiento("claude"), False
        return Lanzamiento("shell"), True

    async def abrir_desde_pedido_pestana(
        self,
        ctx: Ctx,
        item: dict,
        *,
        idempotencia: str,
        grupo: str | None,
        al_crear: Callable[[], None] | None = None,
        permiso: str | None = None,
        dirs_extra: list[str] | None = None,
        ejecutar_comandos: bool = False,
    ) -> dict:
        """`ejecutar_comandos` (solo por keyword, nunca desde un pedido externo) manda Enter al `comando` de las pestañas terminal.

        `permiso` (`default`/`plan`, o `copiloto`/`guia` solo en su carpeta fija) endurece el modo de cada Claude; None usa el global.

        `dirs_extra` (solo con `copiloto`) son los repos que el guardián agrega con --add-dir."""
        if permiso is not None and permiso not in MODOS_POR_LANZAMIENTO | MODOS_INTERNOS:
            raise ValueError("permiso por lanzamiento inválido")
        if dirs_extra and permiso != "copiloto":
            raise ValueError("dirs_extra solo vale con el permiso copiloto")
        if permiso in MODOS_INTERNOS:
            carpetas = [item.get("carpeta")] if not item.get("pestanas") else [
                p.get("carpeta") or item.get("carpeta") for p in item["pestanas"]]
            if not all(isinstance(c, str) and es_carpeta_interna(permiso, os.path.expanduser(c)) for c in carpetas):
                raise ValueError("permiso interno fuera de su carpeta")
        cached = self._nueva_cache.get(idempotencia)
        if cached is not None:
            return cached
        if idempotencia in self._inflight:
            raise TraspasoError(409, "Ya la estoy abriendo")
        permitidas = self.plan_cwds()
        if permiso in MODOS_INTERNOS:
            # Ya se verificó que todas las carpetas son la del modo: solo esa se suma, solo para este modo.
            permitidas = [*permitidas, str(carpeta_de_modo(permiso))]
        raw_pest = item.get("pestanas")
        if raw_pest:
            plan = [dict(p) for p in raw_pest]
        else:
            plan = [
                {
                    "nombre": item.get("nombre") or "",
                    "tipo": "claude",
                    "carpeta": item["carpeta"],
                    "mensaje": item.get("mensaje") or "",
                }
            ]
        for pest in plan:
            if pest.get("tipo") == "terminal" and pest.get("comando"):
                # Defensa en profundidad: lo que se escribe es exactamente lo que valida la tarjeta.
                pest["comando"] = validar_comando(pest["comando"])
        n = len(plan)
        wait = self.limit.consumir("nueva", n, NUEVA_LIMIT)
        if wait:
            raise TraspasoError(
                429,
                f"Este pedido necesita {n} pestaña{'s' if n != 1 else ''} nuevas y el tope por hora no alcanza",
                {"retry_after": wait},
            )
        tarjeta = (item.get("tarjeta") or "").strip()
        usar_grupo = grupo if not tarjeta else None
        op = _Op(ctx, "nueva_terminal")
        abiertos: list[dict] = []
        espacio_id: str | None = None
        self._inflight.add(idempotencia)
        esperar_claude: list[tuple[str, int]] = []
        try:
            g = self._guardian_backend()
            for idx, pest in enumerate(plan):
                cwd = validar_carpeta(pest["carpeta"], permitidas)
                nombre_tab = normalizar_nombre(pest.get("nombre") or None, cwd)
                tipo = pest["tipo"]
                arrancar_claude = False
                try:
                    if idx == 0:
                        if tarjeta:
                            ws = normalizar_nombre(tarjeta, cwd)
                            creado = await g.crear_espacio(ws, cwd)
                            espacio_id = creado.espacio_id
                            pane = creado.sesion_id
                            if (
                                nombre_tab.strip().casefold() != ws.strip().casefold()
                                and creado.linea_id
                            ):
                                with contextlib.suppress(NoDisponible, TerminalesError):
                                    await g.renombrar(creado.linea_id, nombre_tab)
                            arrancar_claude = tipo == "claude"
                        elif usar_grupo:
                            tab = await g.tablero()
                            if not any(e.id == usar_grupo for e in tab.espacios):
                                raise TraspasoError(409, "Ese grupo ya no está: no abrí nada")
                            prog, arrancar_claude = self._lanzamiento(tipo, permiso)
                            creado = await g.crear_linea(usar_grupo, nombre_tab, cwd, prog)
                            espacio_id = usar_grupo
                            pane = creado.sesion_id
                        else:
                            ws = normalizar_nombre(nombre_tab, cwd)
                            creado = await g.crear_espacio(ws, cwd)
                            espacio_id = creado.espacio_id
                            pane = creado.sesion_id
                            arrancar_claude = tipo == "claude"
                    else:
                        dest = espacio_id or usar_grupo
                        if not dest:
                            raise TraspasoError(503, "No pude abrir más pestañas en este pedido")
                        prog, arrancar_claude = self._lanzamiento(tipo, permiso)
                        creado = await g.crear_linea(dest, nombre_tab, cwd, prog)
                        pane = creado.sesion_id
                    if arrancar_claude:
                        agente = await self._agente_claude(nombre_tab)
                        try:
                            if permiso is None:
                                await g.arrancar_claude(pane, agente)
                            elif not dirs_extra:
                                await g.arrancar_claude(pane, agente, modo=permiso)
                            else:
                                await g.arrancar_claude(pane, agente, modo=permiso, dirs_extra=dirs_extra)
                        except (NoDisponible, TerminalesError) as exc:
                            raise TraspasoError(
                                503,
                                "Abrí la terminal pero Claude no arrancó: podés arrancarlo desde ahí",
                            ) from exc
                    if tipo == "terminal" and pest.get("comando"):
                        await (g.ejecutar if ejecutar_comandos else g.escribir)(pane, pest["comando"])
                    entry = {
                        "pane_id": pane,
                        "tipo": tipo,
                        "mensaje": pest.get("mensaje") if tipo == "claude" else None,
                        "pegado": None,
                        "nombre": nombre_tab,
                    }
                    abiertos.append(entry)
                    if tipo == "claude":
                        esperar_claude.append((pane, len(abiertos) - 1))
                    op.pane_id = pane
                    accion = "nueva_claude" if tipo == "claude" else "nueva_shell"
                    self._record(op, True, accion=accion)
                except TraspasoError:
                    if abiertos:
                        panes = ", ".join(a["pane_id"] for a in abiertos)
                        raise TraspasoError(503, f"Quedó abierto {panes}; no pude seguir con «{nombre_tab}»",
                                            {"abiertos": [a["pane_id"] for a in abiertos]})
                    raise
                except (NoDisponible, TerminalesError) as exc:
                    if abiertos:
                        panes = ", ".join(a["pane_id"] for a in abiertos)
                        raise TraspasoError(503, f"Quedó abierto {panes}; no pude seguir con «{nombre_tab}»",
                                            {"abiertos": [a["pane_id"] for a in abiertos]}) from exc
                    raise TraspasoError(503, "Las terminales propias no responden: no abrí nada") from exc

            async def _esperar_claude(pane_id: str, indice: int) -> tuple[int, bool]:
                try:
                    await self.enchufe.esperar_listo(pane_id, ESPERA_LISTO)
                    return indice, True
                except Tiempo as exc:
                    # Un guardián que publica `listo` y vence ve otra cosa en pantalla (un diálogo): no se pega.
                    # Con uno viejo (sin `listo`) el registro de ganchos alcanza para pegar.
                    if (not exc.listo_conocido and self.estados is not None
                            and self.estados.estado_de(pane_id) is not None):
                        return indice, True
                except (TerminalesError, asyncio.TimeoutError):
                    pass
                log.warning("pedido-pestana: %s no quedó listo", pane_id)
                return indice, False

            # `al_crear` es síncrono: avisa que las pestañas ya existen antes de la espera larga.
            if al_crear is not None:
                try:
                    al_crear()
                except Exception:
                    log.exception("pedido-pestana: falló al_crear")

            if esperar_claude:
                for indice, pegado in await asyncio.gather(
                    *[_esperar_claude(p, i) for p, i in esperar_claude]
                ):
                    abiertos[indice]["pegado"] = pegado

            out = {
                "ok": True,
                "pane_id": abiertos[0]["pane_id"],
                "pane_ids": [a["pane_id"] for a in abiertos],
                "detalle": abiertos,
                "espacio_id": espacio_id or usar_grupo,
            }
            self._nueva_cache[idempotencia] = out
            while len(self._nueva_cache) > MAX_IDS:
                self._nueva_cache.popitem(last=False)
            if n > 1:
                titulo = f"{n} pestañas abiertas"
            elif abiertos[0]["tipo"] == "claude":
                titulo = f"Claude nuevo en {abiertos[0]['nombre']}"
            else:
                titulo = f"Terminal nueva en {abiertos[0]['nombre']}"
            tag = "terminal-nueva-claude" if abiertos[0]["tipo"] == "claude" else "terminal-nueva-shell"
            # La guía y el Copiloto son ayudantes internos: abrirlos no es algo que tenga que llegar al celu.
            if permiso not in MODOS_INTERNOS:
                await self._push(op, titulo, ctx.device, tag)
            return out
        except TraspasoError as exc:
            if not abiertos:
                self._record(op, False, exc.detail, "rechazo")
            raise
        finally:
            self._inflight.discard(idempotencia)

    # ---------- acciones ----------

    async def _guarded(self, op: _Op, op_id: str, work, push=None):
        """Orden de 5.1: interruptor, id, límite (lo pone `work`), lock del pane, destino, ejecución, auditoría."""
        try:
            self._gate(op)
            self._fresh_id(op_id)
            self._inflight.add(op_id)
            try:
                result = await work()
            finally:
                self._inflight.discard(op_id)
        except TraspasoError as exc:
            if op.tocado:
                self._used(op_id)
            self._record(op, False, exc.detail, "rechazo")
            raise
        except Exception:
            if op.tocado:
                self._used(op_id)
            self._record(op, False, "error interno", "rechazo")
            raise
        self._used(op_id)
        return result

    async def ctrl_c(self, ctx: Ctx, body: AccionBody) -> dict:
        op = _Op(ctx, "ctrl_c", body.pane_id)

        async def work():
            self._rate("ctrl_c", CTRL_C_LIMIT)
            async with self.locks.get(body.pane_id):
                await self._check_target(op, body.huella)
                await self._keys(op, TECLAS["ctrl_c"])
            return {"ok": True}

        result = await self._guarded(op, body.id, work)
        self._record(op, True)
        await self._push(op, f"Ctrl+C en {self._workspace(op)}", f"{op.proceso or 'terminal'} · {ctx.device}".strip(" ·"),
                         "terminal-ctrl-c")
        return result

    async def repetir_preparar(self, ctx: Ctx, body: AccionBody) -> dict:
        op = _Op(ctx, "repetir_preparar", body.pane_id)

        async def work():
            self._rate("repetir", REPETIR_LIMIT)
            async with self.locks.get(body.pane_id):
                await self._check_target(op, body.huella)
                self._need_shell(op)
                antes = last_line(await self._read_visible(op))
                await self._keys(op, TECLAS["arriba"])
                despues = last_line(await self._read_visible(op))
                if not despues or despues == antes:
                    op.comando = ""
                    return {"linea": None, "antes": antes, "huella2": ""}
                huella2 = _hash(f"{body.huella}|{_hash(despues)}")[:32]
                self._pendientes[huella2] = {"pane_id": op.pane_id, "huella": body.huella, "linea": _hash(despues)}
                while len(self._pendientes) > MAX_PENDIENTES:
                    self._pendientes.popitem(last=False)
                op.comando = despues
                return {"linea": despues, "antes": antes, "huella2": huella2}

        result = await self._guarded(op, body.id, work)
        self._record(op, True)
        return result

    async def repetir_confirmar(self, ctx: Ctx, body: ConfirmarBody) -> dict:
        op = _Op(ctx, "repetir_ejecutar" if body.ejecutar else "repetir_cancelar", body.pane_id)
        pending: dict = {}

        async def work():
            found = self._pendientes.pop(body.huella2, None)
            if found is None or found["pane_id"] != body.pane_id:
                raise TraspasoError(409, "la confirmación venció, preparala de nuevo")
            pending.update(found)
            async with self.locks.get(body.pane_id):
                await self._check_target(op, found["huella"])
                if not body.ejecutar:
                    await self._clean_line(op)
                    return {"ok": True, "ejecutado": False}
                actual = last_line(await self._read_visible(op))
                op.comando = actual
                if _hash(actual) != found["linea"]:
                    await self._clean_line(op)
                    raise TraspasoError(409, "la línea cambió, preparala de nuevo")
                self._need_shell(op)
                await self._keys(op, TECLAS["enter"])
                return {"ok": True, "ejecutado": True}

        result = await self._guarded(op, body.id, work)
        self._record(op, True)
        if body.ejecutar:
            await self._push(op, f"Comando en {self._workspace(op)}", f"{redactar(op.comando)[:80]} · {ctx.device}".strip(" ·"),
                             "terminal-repetir")
        return result

    async def cerrar(self, ctx: Ctx, body: AccionBody, origen: str = "manual",
                     esperado: Optional[dict] = None) -> dict:
        """Cierra una terminal común. Sola en su pestaña: se cierra la pestaña con el servicio de cierre.

        No pide la escritura prendida: cerrar una pestaña desde el tablero tampoco la pide.
        """
        op = _Op(ctx, "cerrar_terminal" if origen == "manual" else "cerrar_terminal_pedido", body.pane_id)
        try:
            self._fresh_id(body.id)
            self._inflight.add(body.id)
            try:
                result = await self._cerrar(op, body, origen, esperado)
            finally:
                self._inflight.discard(body.id)
        except TraspasoError as exc:
            if op.tocado:
                self._used(body.id)
            self._record(op, False, exc.detail, op.accion)
            raise
        except Exception:
            if op.tocado:
                self._used(body.id)
            self._record(op, False, "error interno", op.accion)
            raise
        self._used(body.id)
        self._record(op, True)
        await self._push(op, f"Terminal cerrada en {self._workspace(op)}",
                         f"{op.proceso or 'terminal'} · {ctx.device}".strip(" ·"), "terminal-cerrar")
        return result

    def id_gastado(self, op_id: str) -> bool:
        return op_id in self._ids

    @staticmethod
    def _sola_en_su_pestana(snap: dict, pane: dict) -> Optional[bool]:
        """None si no se ubica su pestaña."""
        tab_id = pane.get("tab_id") or ""
        tab = next((t for t in snap.get("tabs", []) if t.get("tab_id") == tab_id), None)
        if tab is None:
            return None
        hermanos = [p for p in merged_panes(snap).values() if p.get("tab_id") == tab_id]
        return len(hermanos) <= 1 and (tab.get("pane_count") or 1) <= 1

    def alcance_de_cierre(self, snap: dict, pane: dict) -> str:
        """Qué se lleva cerrar esta terminal: solo ella, su pestaña o el workspace entero."""
        if self._sola_en_su_pestana(snap, pane) is False:
            return "terminal"
        ws_id = pane.get("workspace_id") or ""
        tabs = [t for t in snap.get("tabs", []) if t.get("workspace_id") == ws_id]
        return "espacio" if len(tabs) <= 1 else "pestana"

    @staticmethod
    def _check_esperado(op: _Op, pane: dict, esperado: Optional[dict]) -> None:
        """Lo que vio el pedido al crearse: si ahora es otra terminal o se movió, no se cierra."""
        if esperado is None:
            return
        if "terminal_id" in esperado and (esperado.get("terminal_id") or "") != (pane.get("terminal_id") or ""):
            raise TraspasoError(409, "ya es otra terminal: descarté el pedido", {"otra_terminal": True})
        for clave, actual in (("cwd", short_cwd(pane_cwd(pane))), ("workspace_id", pane.get("workspace_id") or ""),
                              ("tab_id", pane.get("tab_id") or "")):
            if clave in esperado and (esperado.get(clave) or "") != actual:
                raise TraspasoError(409, "la terminal se movió o cambió de carpeta desde el pedido")
        if "proceso" in esperado and (esperado.get("proceso") or "") != op.proceso:
            raise TraspasoError(409, "la terminal cambió, revisala de nuevo")

    async def _cerrar(self, op: _Op, body: AccionBody, origen: str, esperado: Optional[dict]) -> dict:
        from .cierre import CierreBody, PreviewBody as CierrePreview

        if self.cierres is None:
            raise TraspasoError(503, "no puedo cerrar terminales")
        self._rate("cerrar", CERRAR_LIMIT)
        pane = await self._check_target(op, body.huella)
        self._check_esperado(op, pane, esperado)
        tab_id = pane.get("tab_id") or ""
        snap = op.snapshot or {}
        sola = self._sola_en_su_pestana(snap, pane)
        if sola is None:
            raise TraspasoError(409, "no pude ubicar su pestaña: revisala de nuevo")
        if sola:
            previa = await self.cierres.preview(CierrePreview(tipo="tab", target_id=tab_id))
            if [p["pane_id"] for p in previa["panes"]] != [op.pane_id]:
                raise TraspasoError(409, "la terminal cambió, revisala de nuevo")
            if previa["bloqueantes"]:
                raise TraspasoError(403, "es una sesión de agente")
            op.tocado = True
            out = await self.cierres.execute(CierreBody(id=body.id, tipo="tab", target_id=tab_id,
                                                        huella=previa["huella"], origen=origen))
            res = {"ok": True, "cerro": "pestana", "closed_tab_id": tab_id}
            if out.get("closed_workspace_id"):
                res["closed_workspace_id"] = out["closed_workspace_id"]
            if out.get("aviso"):
                res["aviso"] = out["aviso"]
            return res
        async with self.locks.structure:
            async with self.locks.get(op.pane_id):
                pane = await self._check_target(op, body.huella)
                self._check_esperado(op, pane, esperado)
                # Lo de afuera del lock pudo cambiar: sola en su pestaña, el cierre pasa por el servicio de cierre.
                if self._sola_en_su_pestana(op.snapshot or {}, pane) is not False:
                    raise TraspasoError(409, "la terminal quedó sola en su pestaña: revisala de nuevo")
                op.tocado = True
                await self._llamar(self.enchufe.cerrar(op.pane_id))
        self.cierres.state.add_cierre({
            "id": body.id, "tipo": "terminal", "target_id": op.pane_id,
            "label": clean(titulo_de(pane) or self.t.tab_label(snap, tab_id), 200), "origen": origen,
            "ts": _now(), "ok": True, "sesiones": [],
            "guardado": "saltado"})
        if self.cierres.refresh:
            try:
                await self.cierres.refresh()
            except Exception as exc:
                log.warning("refresh tras cerrar terminal falló: %s", type(exc).__name__)
        return {"ok": True, "cerro": "terminal"}

    async def _keys(self, op: _Op, *keys: str) -> None:
        op.tocado = True
        await self._llamar(self.enchufe.teclas(op.pane_id, keys))

    async def _clean_line(self, op: _Op) -> None:
        op.tocado = True
        await self._llamar(self.enchufe.teclas(op.pane_id, (TECLAS["fin_linea"], TECLAS["borrar_linea"])))

    # ---------- ventana de escritura y comando ----------

    async def abrir_ventana(self, ctx: Ctx, body: VentanaBody) -> dict:
        op = _Op(ctx, "ventana_abierta")
        if not self.enabled():
            self._record(op, False, "escritura apagada", "rechazo")
            raise TraspasoError(403, "escritura apagada")
        async with self.limiter.gate:
            wait = self.limiter.retry_after(ctx.ip)
            if not wait:
                wait = self.limit.hit("ventana", VENTANA_OPENS)
            if wait:
                self._record(op, False, "demasiados intentos", "rechazo")
                raise TraspasoError(429, "demasiados intentos", {"retry_after": wait})
            failed = not await asyncio.to_thread(self.verify, body.pin, self.pin)
            if failed:
                self.limiter.fail(ctx.ip)
                self._record(op, False, "PIN incorrecto", "ventana_pin_fallido")
            else:
                self.limiter.ok(ctx.ip)
        if failed:
            await self._push(op, "PIN incorrecto al abrir la escritura", ctx.device, "terminal-pin")
            raise TraspasoError(401, "PIN incorrecto")
        token = self.ventana.abrir(ctx.cookie, ctx.ip)
        self._record(op, True)
        await self._push(op, "Se abrió la escritura de terminales", ctx.device, "terminal-ventana")
        return {"token": token, "vence_en": int(VENTANA_ABS), "inactividad": int(VENTANA_IDLE)}

    def cerrar_ventana(self, ctx: Ctx, motivo: str = "ventana_cerrada") -> dict:
        if self.ventana.cerrar():
            self._record(_Op(ctx, motivo), True)
        return {"ok": True}

    def _check_ventana(self, ctx: Ctx) -> None:
        reason = self.ventana.validar(ctx.token, ctx.cookie, ctx.ip)
        if reason == "vencida":
            self._record(_Op(ctx, "ventana_vencida"), True)
        if reason:
            raise TraspasoError(401, "abrí la escritura de nuevo")

    async def comando(self, ctx: Ctx, body: ComandoBody) -> dict:
        op = _Op(ctx, "comando", body.pane_id)

        async def work():
            self._check_ventana(ctx)
            if body.rapido is not None:
                if body.rapido >= len(self.rapidos):
                    raise TraspasoError(400, "comando rápido inexistente")
                text = self.rapidos[body.rapido]
                op.rapido = True
                # Lo confirmado tiene que ser lo que corre: si la lista cambió (reinicio), el índice ya no sirve.
                if unicodedata.normalize("NFC", body.comando or "") != text:
                    raise TraspasoError(409, "la lista de comandos rápidos cambió, elegilo de nuevo")
            else:
                text = validar_comando(body.comando)
            op.comando = text
            self._rate("comando", *COMANDO_LIMITS)
            async with self.locks.get(body.pane_id):
                await self._check_target(op, body.huella)
                self._need_shell(op)
                await self._clean_line(op)
                await self._llamar(self.enchufe.ejecutar(op.pane_id, text))
            self.ventana.usar()
            return {"ok": True}

        result = await self._guarded(op, body.id, work)
        self._record(op, True)
        await self._push(op, f"Comando en {self._workspace(op)}", f"{redactar(op.comando)[:80]} · {ctx.device}".strip(" ·"),
                         "terminal-comando")
        return result
