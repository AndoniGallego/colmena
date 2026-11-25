import asyncio
import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from pydantic import BaseModel, ConfigDict, Field, model_validator
from py_vapid import Vapid02

from .avisos import AvisosStore, SESSION_RE, TAG_RE
from .config import private_write
from .enchufe.ids import PANE_RE, valido
from .digest import clip_words, fin_de_turno
from .presencia import Presencia
from .tareas import vigilar

log = logging.getLogger("orquestador.push")
MAX_SUBSCRIPTIONS = 10
# Solo frena rebotes de estado dentro de un mismo turno; cada fin de turno avisa.
SESSION_COOLDOWN = 10.0
DONE_DIFERIDO_S = 3.0
SEND_TIMEOUT = 10
ENTREGAS_TTL = 7 * 86400
BODY_CHARS = 120
VAPID_SUB = os.environ.get("ORQ_VAPID_SUB") or "mailto:orquestador@example.com"
HOST_SUFFIXES = (".push.apple.com", ".notify.windows.com", ".push.services.mozilla.com")
HOSTS = {"fcm.googleapis.com", "updates.push.services.mozilla.com"}
B64URL = re.compile(r"^[A-Za-z0-9_-]{8,200}={0,2}$")
KINDS = ("asks", "blocked", "done")
EN_APP = "en la app"
GENERICO = "Revisá la sesión en Colmena."
TITLES = {"asks": "{} te pregunta", "blocked": "{} espera una aprobación", "done": "{} terminó"}
NOTCH_PRUEBA_KINDS = frozenset(("asks", "blocked", "done"))
PRUEBA_PREFIX = "Prueba: "
PRUEBA_SID = "00000000-0000-4000-8000-000000000001"


class Keys(BaseModel):
    p256dh: str = Field(pattern=B64URL.pattern)
    auth: str = Field(pattern=B64URL.pattern)


class Subscription(BaseModel):
    endpoint: str = Field(max_length=1024)
    keys: Keys


PREF_EXTRA_RE = re.compile(r"^[a-z]{1,20}$")
MAX_PREFS_EXTRA = 10


class Prefs(BaseModel):
    """Preferencias del núcleo; las piezas suman las suyas como extras bool (nombre en minúsculas, hasta 10)."""
    model_config = ConfigDict(extra="allow")

    asks: bool = True
    blocked: bool = True
    done: bool = True
    texto: bool = True
    cierre: bool = True
    mrs: bool = True
    entornos: bool = True
    progreso: bool = True
    pestana: bool = True
    trabada: bool = True

    @model_validator(mode="after")
    def _extras_validos(self):
        extras = self.model_extra or {}
        if len(extras) > MAX_PREFS_EXTRA:
            raise ValueError("demasiadas preferencias")
        for clave, valor in extras.items():
            if not PREF_EXTRA_RE.match(clave) or not isinstance(valor, bool):
                raise ValueError("preferencia inválida")
        return self


class SubscribeBody(BaseModel):
    subscription: Subscription
    device: str = Field(default="", max_length=60)
    prefs: Prefs = Prefs()


class EndpointBody(BaseModel):
    endpoint: str = Field(max_length=1024)


class TestBody(BaseModel):
    endpoint: Optional[str] = Field(default=None, max_length=1024)


def endpoint_allowed(url: str) -> bool:
    try:
        parts = urlparse(url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username or parts.password or port not in (None, 443):
        return False
    return host in HOSTS or host.endswith(HOST_SUFFIXES)


class VapidKeys:
    def __init__(self, directory: Path):
        self.path = directory / "vapid.json"
        data = None
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.vapid = Vapid02.from_pem(data["private"].encode())
                self.public = data["public"]
                return
            except (ValueError, KeyError, TypeError):
                log.warning("vapid.json ilegible, genero claves nuevas")
                try:
                    private_write(self.path.with_name("vapid.json.roto"),
                                  self.path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    log.warning("No se pudo respaldar el vapid.json ilegible")
        self.vapid = Vapid02()
        self.vapid.generate_keys()
        raw = self.vapid.public_key.public_bytes(serialization.Encoding.X962,
                                                 serialization.PublicFormat.UncompressedPoint)
        self.public = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        private_write(self.path, json.dumps({"private": self.vapid.private_pem().decode(), "public": self.public}))


class PushStore:
    def __init__(self, directory: Path):
        self.path = directory / "push.json"
        self.subs: list = []
        if self.path.exists():
            try:
                self.subs = list(json.loads(self.path.read_text(encoding="utf-8")).get("subs", []))
            except (ValueError, AttributeError):
                pass

    def _save(self) -> None:
        private_write(self.path, json.dumps({"subs": self.subs}, ensure_ascii=False))

    def find(self, endpoint: str) -> Optional[dict]:
        return next((s for s in self.subs if s["endpoint"] == endpoint), None)

    def upsert(self, entry: dict) -> bool:
        current = self.find(entry["endpoint"])
        if current is None and len(self.subs) >= MAX_SUBSCRIPTIONS:
            return False
        if current is None:
            self.subs.append(entry)
        else:
            current.update(entry)
        self._save()
        return True

    def remove(self, endpoint: str) -> bool:
        before = len(self.subs)
        self.subs = [s for s in self.subs if s["endpoint"] != endpoint]
        if len(self.subs) != before:
            self._save()
        return len(self.subs) != before


def _fondo(agent: dict) -> bool:
    f = agent.get("fondo")
    return isinstance(f, list) and len(f) > 0


def _agents(board: Optional[dict]) -> dict:
    out = {}
    for ws in (board or {}).get("workspaces", []):
        for tab in ws.get("tabs", []):
            for agent in tab.get("agents", []):
                if agent.get("pane_id"):
                    out[agent["pane_id"]] = (ws.get("label") or agent.get("title") or "Sesión", agent)
    return out


def _real_send(info: dict, data: str, vapid, claims: dict, timeout: float):
    from pywebpush import webpush
    return webpush(info, data=data, vapid_private_key=vapid, vapid_claims=claims, timeout=timeout)


def _default_call_later(delay: float, fn: Callable[[], None]):
    return asyncio.get_running_loop().call_later(delay, fn)


def _loop_corriendo() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _clip_log(val: str, max_len: int = 12) -> str:
    if len(val) <= max_len:
        return val
    return val[:max_len] + "…"


def _quien_marco(store: PushStore, excluir: str) -> str:
    if not excluir:
        return "sin dispositivo (app sin notificaciones o servidor)"
    sub = store.find(excluir)
    if sub is None:
        return "dispositivo desconocido"
    return sub.get("device") or "dispositivo"


def _filtro_marcar(hasta: Optional[int], filtro: dict) -> str:
    if hasta is not None:
        return f"hasta={hasta}"
    parts = []
    for key in ("session_id", "pane_id", "kind", "mr", "mensaje", "tag"):
        val = filtro.get(key) or ""
        if val:
            parts.append(f"{key}={_clip_log(val)}")
    return ", ".join(parts)


def _plural(n: int, uno: str, muchos: str) -> str:
    return uno if n == 1 else muchos


class PushService:
    def __init__(self, directory: Path, sender: Callable = _real_send, clock: Callable = time.monotonic,
                 wall: Callable = time.time, presencia: Optional[Presencia] = None,
                 call_later: Callable[[float, Callable[[], None]], object] = _default_call_later):
        self.keys = VapidKeys(directory)
        self.store = PushStore(directory)
        self.avisos = AvisosStore(directory, wall)
        self.presencia = presencia or Presencia(clock)
        self.wall = wall
        self.listeners: list = []
        self.leidos_listeners: list = []
        self.sender = sender
        self.clock = clock
        self.call_later = call_later
        self._last_sent: dict = {}
        self._entregas: dict = {}
        self._tasks: set = set()
        self._latest_board: Optional[dict] = None
        self._pending_done: dict = {}
        self._pruebas: dict = {}
        self.describe_blocked: Optional[Callable] = None
        self.silenciada: Callable[[str], bool] = lambda sid: False

    def _en_la_app(self) -> bool:
        return self.presencia.present()

    def _record(self, kind: str, title: str, body: str, generic: str, entregados: int, motivo: str = "",
                tag: str = "", **dest) -> None:
        """Un registro por evento. El cuerpo completo solo se guarda si algún dispositivo lo recibe con texto."""
        texto = any(s.get("prefs", {}).get("texto", True) for s in self.store.subs)
        try:
            entry = self.avisos.add(kind, title, body if texto else generic, entregados > 0, motivo=motivo, tag=tag,
                                    **dest)
        except Exception as exc:
            log.warning("no pude registrar el aviso: %s", type(exc).__name__)
            return
        for listener in self.listeners:
            try:
                listener(entry)
            except Exception as exc:
                log.warning("listener de avisos falló: %s", type(exc).__name__)

    def _emit_aviso_listeners(self, entry: dict) -> None:
        for listener in self.listeners:
            try:
                listener(entry)
            except Exception as exc:
                log.warning("listener de avisos falló: %s", type(exc).__name__)

    def registrar_aviso_prueba_notch(
        self, kind: str, titulo: str, cuerpo: str, session_id: str = "", pane_id: str = "", fecha: str = "",
        mr: str = "", mensaje: str = "", tag: str = "",
    ) -> dict:
        """Aviso de prueba para el notch: persiste con prueba=true, sin push; notifica listeners (SSE)."""
        texto = any(s.get("prefs", {}).get("texto", True) for s in self.store.subs)
        body = cuerpo if texto else GENERICO
        entry = self.avisos.add(kind, titulo, body, False, prueba=True, session_id=session_id, pane_id=pane_id,
                                fecha=fecha, mr=mr, mensaje=mensaje, tag=tag)
        self._emit_aviso_listeners(entry)
        return entry

    def registrar_prueba(self, kind: str, mensaje: Callable[[], dict]) -> None:
        """Una pieza aporta su aviso de prueba para el celular: `mensaje()` arma el payload sin el prefijo de prueba."""
        self._pruebas[kind] = mensaje

    def instantanea_piezas(self) -> tuple:
        """Lo que las piezas registran (kinds y pruebas), para deshacerlo si una falla al montarse."""
        return list(self.avisos.kinds), dict(self._pruebas)

    def restaurar_piezas(self, instantanea: tuple) -> None:
        kinds, pruebas = instantanea
        self.avisos.kinds[:] = kinds
        self._pruebas.clear()
        self._pruebas.update(pruebas)

    def prueba_kinds(self) -> frozenset:
        """Kinds que admiten aviso de prueba: los del historial (base y los que sumaron las piezas) menos `test`."""
        return frozenset(k for k in self.avisos.kinds if k != "test")

    def _titulo_prueba(self, titulo: str) -> str:
        return titulo if titulo.startswith(PRUEBA_PREFIX) else f"{PRUEBA_PREFIX}{titulo}"

    def prueba_aviso_notch(self, kind: str) -> dict:
        """Registra un aviso de prueba para el notch (solo asks/blocked/done)."""
        tag = PRUEBA_SID
        if kind == "asks":
            titulo = self._titulo_prueba(TITLES["asks"].format("Sesión de prueba"))
            return self.registrar_aviso_prueba_notch("asks", titulo, "¿Seguimos con la prueba?", session_id=PRUEBA_SID, tag=tag)
        if kind == "blocked":
            titulo = self._titulo_prueba(TITLES["blocked"].format("Sesión de prueba"))
            return self.registrar_aviso_prueba_notch(
                "blocked", titulo, "Ejemplo: el modelo pidió permiso para un comando.", session_id=PRUEBA_SID, tag=tag)
        if kind == "done":
            titulo = self._titulo_prueba(TITLES["done"].format("Sesión de prueba"))
            return self.registrar_aviso_prueba_notch("done", titulo, "Listo el trabajo de ejemplo.", session_id=PRUEBA_SID, tag=tag)
        raise ValueError(kind)

    async def prueba_push_celu(self, kind: str) -> int:
        """Envía push de prueba a todos los suscriptos ignorando presencia y preferencias; no registra aviso."""
        if not self.store.subs:
            return 0
        if kind == "asks":
            event = {"kind": "asks", "session_id": PRUEBA_SID, "name": "Sesión de prueba", "pending": "¿Seguimos con la prueba?"}
            message = self.payload(event, {"texto": True})
            message["title"] = self._titulo_prueba(message["title"])
            message["body"] = message.get("body") or "Texto de ejemplo para la prueba."
            results = await asyncio.gather(*(self._deliver(s, message) for s in list(self.store.subs)))
            return sum(results)
        if kind == "blocked":
            event = {
                "kind": "blocked",
                "session_id": PRUEBA_SID,
                "name": "Sesión de prueba",
                "pending": "",
                "dialogo_texto": "Ejemplo: el modelo pidió permiso para un comando.",
            }
            message = self.payload(event, {"texto": True})
            message["title"] = self._titulo_prueba(message["title"])
            results = await asyncio.gather(*(self._deliver(s, message) for s in list(self.store.subs)))
            return sum(results)
        if kind == "done":
            event = {"kind": "done", "session_id": PRUEBA_SID, "name": "Sesión de prueba", "pending": "Listo el trabajo de ejemplo."}
            message = self.payload(event, {"texto": True})
            message["title"] = self._titulo_prueba(message["title"])
            results = await asyncio.gather(*(self._deliver(s, message) for s in list(self.store.subs)))
            return sum(results)
        if kind == "terminal":
            title = self._titulo_prueba("Salida en terminal")
            body = "Ejemplo: se escribió en una terminal."
            pane_ok = "p-w1"
            results = []
            for sub in list(self.store.subs):
                text = body if sub.get("prefs", {}).get("texto", True) else "Revisá la actividad de terminales."
                msg = {"title": title, "body": text, "session_id": "", "kind": "terminal", "tag": "prueba-terminal",
                       "pane_id": pane_ok}
                results.append(await self._deliver(sub, msg))
            return sum(results)
        if kind == "encadenar":
            title = self._titulo_prueba("Encadenar sesiones")
            body = "Ejemplo de texto para encadenar sesiones."
            results = []
            for sub in list(self.store.subs):
                text = body if sub.get("prefs", {}).get("texto", True) else "Revisá la propuesta en Colmena."
                results.append(await self._deliver(sub, {"title": title, "body": text, "session_id": "", "kind": "encadenar",
                                                         "tag": "encadenar"}))
            return sum(results)
        if kind == "vigia":
            title = self._titulo_prueba("Aviso del vigía")
            body = "Ejemplo de aviso del vigía."
            results = []
            for sub in list(self.store.subs):
                text = body if sub.get("prefs", {}).get("texto", True) else "Abrí Colmena para ver cómo va."
                sid = PRUEBA_SID
                msg = {"title": title, "body": text, "session_id": sid, "kind": "vigia",
                       "tag": f"vigia-done-{sid}"}
                results.append(await self._deliver(sub, msg))
            return sum(results)
        if kind in self._pruebas and kind in self.avisos.kinds:
            message = dict(self._pruebas[kind]())
            message["title"] = self._titulo_prueba(message.get("title", ""))
            results = await asyncio.gather(*(self._deliver(s, message) for s in list(self.store.subs)))
            return sum(results)
        if kind == "cierre":
            message = {"title": self._titulo_prueba("Cierre del día"), "body": "Resumen de ejemplo para la prueba.",
                       "session_id": "", "kind": "cierre", "tag": "cierre"}
            results = await asyncio.gather(*(self._deliver(s, message) for s in list(self.store.subs)))
            return sum(results)
        if kind == "mr":
            title = self._titulo_prueba("MR actualizado")
            body = "Pipeline en verde (ejemplo)."
            ref = "1:1"
            results = []
            for sub in list(self.store.subs):
                text = body if sub.get("prefs", {}).get("texto", True) else "Revisá tus MRs en Colmena."
                results.append(await self._deliver(sub, {"title": title, "body": text, "session_id": "", "kind": "mr",
                                                         "tag": f"mr-{ref}", "mr": ref}))
            return sum(results)
        if kind == "entorno":
            title = self._titulo_prueba("Entornos")
            body = "Se cayó hs-api (hybrid-search)"
            ref = "hybrid-search:hs-api"
            results = []
            for sub in list(self.store.subs):
                text = body if sub.get("prefs", {}).get("texto", True) else "Revisá Entornos en Colmena."
                results.append(await self._deliver(sub, {"title": title, "body": text, "session_id": "", "kind": "entorno",
                                                         "tag": f"entorno-{ref}"}))
            return sum(results)
        if kind == "progreso":
            encargo = "prueba"
            title = self._titulo_prueba("Viene avanzando: Encargo de prueba")
            texto = "Así va el encargo de ejemplo (prueba)."
            generic = "Abrí Colmena para ver cómo va."
            results = []
            for sub in list(self.store.subs):
                text = texto if sub.get("prefs", {}).get("texto", True) else generic
                results.append(await self._deliver(sub, {"title": title, "body": text, "session_id": "", "kind": "progreso",
                                                         "tag": f"progreso-{encargo}"}))
            return sum(results)
        raise ValueError(kind)

    @property
    def active(self) -> bool:
        return bool(self.store.subs)

    def _cancel_deferred_done(self, key: str) -> None:
        handle = self._pending_done.pop(key, None)
        if handle is not None:
            cancel = getattr(handle, "cancel", None)
            if callable(cancel):
                cancel()

    def _schedule_deferred_done(self, key: str, pane: str, name: str, session_id: str) -> None:
        self._cancel_deferred_done(key)
        self._pending_done[key] = self.call_later(
            DONE_DIFERIDO_S, lambda k=key, p=pane, n=name, sid=session_id: self._complete_deferred_done(k, p, n, sid))

    def _complete_deferred_done(self, key: str, pane: str, name: str, session_id: str) -> None:
        self._pending_done.pop(key, None)
        agents = _agents(self._latest_board)
        entry = agents.get(pane)
        if entry is None:
            return
        name, agent = entry
        status = agent.get("status")
        if status in ("working", "blocked"):
            return
        if agent.get("asks_user"):
            return
        if agent.get("session_id") and self.silenciada(agent["session_id"]):
            return
        now = self.clock()
        last_at, _ = self._last_sent.get(key, (-SESSION_COOLDOWN, None))
        if now - last_at < SESSION_COOLDOWN:
            return
        self._last_sent[key] = (now, "done")
        event = {"kind": "done", "session_id": session_id or agent.get("session_id") or "", "name": name,
                   "pending": agent.get("pending") or "", "pane_id": pane}
        log.info("aviso done para %s", name)
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self.dispatch(event))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            vigilar(task, "PushService.dispatch")
        except RuntimeError:
            asyncio.run(self.dispatch(event))

    def observe(self, prev: Optional[dict], new: dict) -> list:
        self._latest_board = new
        now = self.clock()
        before = _agents(prev)
        events = []
        for pane, (name, agent) in _agents(new).items():
            status = agent.get("status")
            old = before.get(pane)
            if prev is None or old is None:
                continue
            was = old[1]
            asks = bool(agent.get("asks_user"))
            # Mientras trabaja, asks_user puede venir del turno anterior: el fin de turno se evalúa siempre.
            turn_ended = fin_de_turno(was, agent)
            local = bool(agent.get("turno_local"))
            kind = None
            if status == "blocked" and was.get("status") != "blocked":
                kind = "blocked"
            elif turn_ended and asks:
                kind = "asks"
            elif status not in ("working", "blocked") and asks and not was.get("asks_user") and not local:
                kind = "asks"
            elif turn_ended and _fondo(agent):
                kind = None
            elif turn_ended:
                kind = "done"
            elif (status in ("idle", "done") and was.get("status") in ("idle", "done")
                  and _fondo(was) and not _fondo(agent)):
                kind = "done"
            if kind is None:
                continue
            key = agent.get("session_id") or pane
            if kind not in ("blocked", "asks") and agent.get("session_id") and self.silenciada(agent["session_id"]):
                continue
            if kind == "done":
                sync_observe = self.call_later is _default_call_later and not _loop_corriendo()
                if not sync_observe:
                    self._schedule_deferred_done(key, pane, name, agent.get("session_id") or "")
                    continue
            last_at, last_kind = self._last_sent.get(key, (-SESSION_COOLDOWN, None))
            # El transcript puede llegar después del cambio de estado: un "terminó" se corrige a "te pregunta".
            upgrade = kind == "asks" and last_kind == "done"
            if now - last_at < SESSION_COOLDOWN and not upgrade:
                continue
            self._last_sent[key] = (now, kind)
            events.append({"kind": kind, "session_id": agent.get("session_id") or "", "name": name,
                           "pending": agent.get("pending") or "", "pane_id": pane})
        return events

    def on_board(self, prev: Optional[dict], new: dict) -> None:
        events = self.observe(prev, new)
        if not events:
            return
        for event in events:
            log.info("aviso %s para %s", event["kind"], event["name"])
            task = asyncio.get_running_loop().create_task(self.dispatch(event))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            vigilar(task, "PushService.dispatch")

    @staticmethod
    def payload(event: dict, prefs: dict) -> dict:
        generic = event.get("dialogo_texto")
        body = (generic or clip_words(event["pending"], BODY_CHARS)) if prefs.get("texto", True) else ""
        message = {"title": TITLES[event["kind"]].format(event["name"]), "body": body, "session_id": event["session_id"],
                   "kind": event["kind"], "tag": event["session_id"] or event["kind"]}
        if generic:
            message["dialogo"] = True
        return message

    def avisar_bloqueo(self, session_id: str, nombre: str, texto: str) -> None:
        now = self.clock()
        key = session_id or nombre
        last_at, _ = self._last_sent.get(key, (-SESSION_COOLDOWN, None))
        if now - last_at < SESSION_COOLDOWN:
            return
        self._last_sent[key] = (now, "blocked")
        event = {
            "kind": "blocked",
            "session_id": session_id,
            "name": nombre,
            "pending": "",
            "dialogo_texto": texto,
        }
        log.info("aviso blocked para %s", nombre)
        task = asyncio.get_running_loop().create_task(self.dispatch(event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        vigilar(task, "PushService.dispatch")

    async def dispatch(self, event: dict) -> int:
        if (
            event["kind"] == "blocked"
            and self.describe_blocked
            and event.get("session_id")
            and "dialogo_texto" not in event
        ):
            try:
                event = {**event, "dialogo_texto": await self.describe_blocked(event["session_id"])}
            except Exception as exc:
                log.warning("no pude describir el diálogo: %s", type(exc).__name__)
        en_app = self._en_la_app()
        targets = [] if en_app else [s for s in list(self.store.subs) if s.get("prefs", {}).get(event["kind"], True)]
        results = await asyncio.gather(*(self._deliver(s, self.payload(event, s.get("prefs", {}))) for s in targets))
        full = self.payload(event, {"texto": True})
        self._record(event["kind"], full["title"], full["body"], GENERICO, sum(results),
                     motivo=EN_APP if en_app else "", session_id=event["session_id"], tag=full["tag"])
        return sum(results)

    async def dispatch_terminal(self, title: str, body: str, tag: str, pane_id: str = "") -> int:
        """Aviso de una acción sobre una terminal: sin preferencia para apagarlo; `texto` apagado deja el cuerpo genérico."""
        async def one(sub: dict) -> bool:
            text = body if sub.get("prefs", {}).get("texto", True) else "Revisá la actividad de terminales."
            message = {"title": title, "body": text, "session_id": "", "kind": "terminal", "tag": tag,
                       "pane_id": pane_id if valido(PANE_RE, pane_id or "") else ""}
            return await self._deliver(sub, message)
        en_app = self._en_la_app()
        results = await asyncio.gather(*(one(s) for s in ([] if en_app else list(self.store.subs))))
        self._record("terminal", title, body, "Revisá la actividad de terminales.", sum(results),
                     motivo=EN_APP if en_app else "", tag=tag,
                     pane_id=pane_id if valido(PANE_RE, pane_id or "") else "")
        return sum(results)

    async def dispatch_simple(self, kind: str, message: dict, pref: str, endpoint: Optional[str] = None,
                              **registro) -> int:
        """Aviso de un solo mensaje a quien tenga `pref` prendida; con `endpoint` (prueba) llega a ese dispositivo
        aunque lo tenga apagado. Si estás en la app no manda push, pero queda en el historial."""
        en_app = endpoint is None and self._en_la_app()
        if endpoint is None:
            targets = [] if en_app else [s for s in list(self.store.subs) if s.get("prefs", {}).get(pref, True)]
        else:
            targets = [s for s in list(self.store.subs) if s["endpoint"] == endpoint]
        results = await asyncio.gather(*(self._deliver(s, message) for s in targets))
        self._record(kind, message["title"], message["body"], message["body"], sum(results),
                     motivo=EN_APP if en_app else "", tag=message.get("tag", ""), **registro)
        return sum(results)

    async def dispatch_pestana(self, pedido_id: str, titulo: str, cuerpo: str, session_id: str = "",
                               pane_id: str = "") -> int:
        generic = "Abrí Colmena para ver el pedido de pestaña."
        sid = session_id if SESSION_RE.match(session_id or "") else ""
        pane = pane_id if valido(PANE_RE, pane_id or "") else ""
        tag = f"pestana-{pedido_id}"
        url = f"/?pedido={pedido_id}"

        async def one(sub: dict) -> bool:
            text = cuerpo if sub.get("prefs", {}).get("texto", True) else generic
            return await self._deliver(sub, {"title": titulo, "body": text, "session_id": sid, "kind": "pestana",
                                             "tag": tag, "url": url})

        en_app = self._en_la_app()
        targets = [] if en_app else [s for s in list(self.store.subs) if s.get("prefs", {}).get("pestana", True)]
        results = await asyncio.gather(*(one(s) for s in targets))
        self._record("pestana", titulo, cuerpo, generic, sum(results), motivo=EN_APP if en_app else "",
                     session_id=sid, pane_id=pane, pedido=pedido_id, tag=tag)
        return sum(results)

    async def dispatch_cierre(self, body: str, endpoint: Optional[str] = None) -> int:
        """Resumen del cierre del día; con `endpoint` (prueba) llega aunque tenga el aviso apagado."""
        message = {"title": "Cierre del día", "body": body, "session_id": "", "kind": "cierre", "tag": "cierre"}
        en_app = endpoint is None and self._en_la_app()
        if endpoint is None:
            targets = [] if en_app else [s for s in list(self.store.subs) if s.get("prefs", {}).get("cierre", True)]
        else:
            targets = [s for s in list(self.store.subs) if s["endpoint"] == endpoint]
        results = await asyncio.gather(*(self._deliver(s, message) for s in targets))
        self._record("cierre", message["title"], message["body"], message["body"], sum(results),
                     motivo=EN_APP if en_app else "", tag="cierre")
        if en_app:
            self.marcar(tag="cierre")
        return sum(results)

    async def dispatch_mr(self, title: str, body: str, ref: str) -> int:
        """Novedad de un MR de GitLab; `texto` apagado deja el cuerpo genérico."""
        generic = "Revisá tus MRs en Colmena."
        tag = f"mr-{ref}"

        async def one(sub: dict) -> bool:
            text = body if sub.get("prefs", {}).get("texto", True) else generic
            return await self._deliver(sub, {"title": title, "body": text, "session_id": "", "kind": "mr",
                                             "tag": tag, "mr": ref})
        en_app = self._en_la_app()
        targets = [] if en_app else [s for s in list(self.store.subs) if s.get("prefs", {}).get("mrs", True)]
        results = await asyncio.gather(*(one(s) for s in targets))
        self._record("mr", title, body, generic, sum(results), motivo=EN_APP if en_app else "", mr=ref, tag=tag)
        return sum(results)

    async def dispatch_entorno(self, title: str, body: str, ref: str) -> int:
        generic = "Revisá Entornos en Colmena."
        tag = f"entorno-{ref}"

        async def one(sub: dict) -> bool:
            text = body if sub.get("prefs", {}).get("texto", True) else generic
            return await self._deliver(sub, {"title": title, "body": text, "session_id": "", "kind": "entorno",
                                             "tag": tag})

        en_app = self._en_la_app()
        targets = [] if en_app else [s for s in list(self.store.subs) if s.get("prefs", {}).get("entornos", True)]
        results = await asyncio.gather(*(one(s) for s in targets))
        self._record("entorno", title, body, generic, sum(results), motivo=EN_APP if en_app else "", tag=tag)
        return sum(results)

    async def dispatch_traba(self, nombre: str, detalle: str, session_id: str = "", pane_id: str = "") -> int:
        """Sesión trabada o en loop: un push por episodio; `texto` apagado deja título y cuerpo genéricos."""
        sid = session_id if SESSION_RE.match(session_id or "") else ""
        pane = pane_id if valido(PANE_RE, pane_id or "") else ""
        tag = f"trabada-{sid}" if sid else "trabada"
        title = f"{nombre} parece trabada"

        async def one(sub: dict) -> bool:
            con_texto = sub.get("prefs", {}).get("texto", True)
            return await self._deliver(sub, {"title": title if con_texto else "Una sesión parece trabada",
                                             "body": detalle if con_texto else GENERICO, "session_id": sid,
                                             "kind": "trabada", "tag": tag})

        en_app = self._en_la_app()
        targets = [] if en_app else [s for s in list(self.store.subs) if s.get("prefs", {}).get("trabada", True)]
        results = await asyncio.gather(*(one(s) for s in targets))
        self._record("trabada", title, detalle, GENERICO, sum(results), motivo=EN_APP if en_app else "",
                     session_id=sid, pane_id=pane, tag=tag)
        return sum(results)

    async def send_test(self, endpoint: Optional[str]) -> int:
        targets = [s for s in list(self.store.subs) if endpoint in (None, s["endpoint"])]
        message = {"title": "Colmena", "body": "Las notificaciones funcionan.", "session_id": "", "kind": "test",
                   "tag": "test"}
        results = await asyncio.gather(*(self._deliver(s, message) for s in targets))
        self._record("test", message["title"], message["body"], message["body"], sum(results), tag="test")
        return sum(results)

    def marcar(self, hasta: Optional[int] = None, excluir: str = "", **filtro) -> int:
        if hasta is not None:
            out = self.avisos.marcar_hasta(hasta)
        else:
            out = self.avisos.marcar_donde(**filtro)
        if out["cambiados"] > 0:
            tags = out["tags"]
            filtro_txt = _filtro_marcar(hasta, filtro)
            quien = _quien_marco(self.store, excluir)
            n = out["cambiados"]
            n_tags = len(tags)
            extra = f" ({filtro_txt})" if filtro_txt else ""
            log.info(
                "avisos marcados como vistos por %s%s: %d %s, cierra %d %s",
                quien,
                extra,
                n,
                _plural(n, "aviso", "avisos"),
                n_tags,
                _plural(n_tags, "notificación", "notificaciones"),
            )
            for listener in self.leidos_listeners:
                try:
                    listener(tags)
                except Exception as exc:
                    log.warning("listener de leídos falló: %s", type(exc).__name__)
            if tags:
                try:
                    task = asyncio.get_running_loop().create_task(self.cerrar(tags, excluir))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                    vigilar(task, "PushService.cerrar")
                except RuntimeError:
                    pass
        return out["no_leidos"]

    async def cerrar(self, tags: list, excluir: str = "") -> int:
        valid = list(dict.fromkeys(t for t in tags if isinstance(t, str) and TAG_RE.match(t)))
        if not valid:
            return 0

        async def one(sub: dict) -> bool:
            endpoint = sub["endpoint"]
            mine = [t for t in valid if t in self._entregas.get(endpoint, {})]
            if not mine:
                return False
            ok = await self._deliver(sub, {"kind": "cerrar", "tags": mine})
            if ok:
                ent = self._entregas.get(endpoint, {})
                for t in mine:
                    ent.pop(t, None)
            return ok

        subs = [s for s in list(self.store.subs) if not excluir or s["endpoint"] != excluir]
        results = await asyncio.gather(*(one(s) for s in subs))
        enviados = [s.get("device") or "dispositivo" for s, ok in zip(subs, results) if ok]
        if enviados:
            log.info("cierre push enviado a %s", ", ".join(enviados))
        return sum(1 for r in results if r)

    async def _deliver(self, sub: dict, message: dict) -> bool:
        info = {"endpoint": sub["endpoint"], "keys": sub["keys"]}
        claims = {"sub": VAPID_SUB}
        try:
            await asyncio.to_thread(self.sender, info, json.dumps(message, ensure_ascii=False), self.keys.vapid,
                                    claims, SEND_TIMEOUT)
            log.info("aviso entregado al servicio de push (%s)", sub.get("device") or "dispositivo")
            tag, kind = message.get("tag"), message.get("kind")
            if tag and kind not in ("cerrar", "test"):
                endpoint = sub["endpoint"]
                ent = self._entregas.setdefault(endpoint, {})
                ent[tag] = self.wall()
                cutoff = self.wall() - ENTREGAS_TTL
                for t, ts in list(ent.items()):
                    if ts < cutoff:
                        del ent[t]
            return True
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                self.store.remove(sub["endpoint"])
                self._entregas.pop(sub["endpoint"], None)
                log.info("suscripción caducada, la borro")
            else:
                log.warning("push falló (%s): %s", status, type(exc).__name__)
            return False
