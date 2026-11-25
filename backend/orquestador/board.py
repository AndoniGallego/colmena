import asyncio
import copy
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Optional

from .contexto import ContextoService
from .digest import DigestService, PENDING_CHARS, clip_frase, parse_estado, quitar_estado, sin_bloques
from .fondo import FondoService
from .internas import filtrar_snapshot
from .enchufe import Terminales, como_snapshot, sesion_propia
from .enchufe.base import Ilegible, TerminalesError
from .estado_sesiones import EstadoSesiones, aplicar_fuente
from .opciones import analizar
from .terminales import ProcessInfoCache, terminal_panes, terminals_by_tab

log = logging.getLogger("orquestador.board")
DEBOUNCE = 0.3
STATUSES = {"idle", "working", "blocked", "done", "unknown"}


def _status(value) -> str:
    return value if value in STATUSES else "unknown"


def build_board(snapshot: dict, digests: DigestService, self_pane_id: Optional[str] = None,
                pinned: frozenset = frozenset(), terminal_info: Optional[dict] = None,
                hidden: frozenset = frozenset(), contexto: Optional[ContextoService] = None,
                hidden_workspaces: frozenset = frozenset(),
                fondo: Optional[FondoService] = None,
                interna: Optional[Callable[[str], bool]] = None,
                uso_hoy: Optional[Callable[[], dict]] = None) -> dict:
    snapshot = filtrar_snapshot(snapshot, interna)
    uso_cache: list = []

    def _uso(session_id: Optional[str]) -> Optional[dict]:
        if uso_hoy is None or not session_id:
            return None
        if not uso_cache:
            try:
                uso_cache.append(uso_hoy() or {})
            except Exception as exc:
                log.warning("uso de hoy falló: %s", exc)
                uso_cache.append({})
        return uso_cache[0].get(session_id)

    def _agent_entry(agent: dict) -> dict:
        pane_id = agent.get("pane_id")
        session = agent.get("agent_session") or {}
        session_id = session.get("value") if session.get("kind") == "id" else None
        title = agent.get("terminal_title_stripped") or agent.get("terminal_title") or ""
        digest = digests.get(session_id) if session_id else None
        doing = (digest.title if digest and digest.title else title)
        pending = ""
        asks_user = False
        preguntas = 0
        estado = None
        if digest:
            crudo = digest.last_claude_text().strip()
            estado = parse_estado(crudo)
            last = quitar_estado(crudo)
            pending = clip_frase(sin_bloques(last), PENDING_CHARS)
            tarjetas, termina = analizar(last)
            preguntas = len(tarjetas)
            asks_user = last.endswith("?") or termina or bool(estado and estado.get("pide"))
        status = _status(agent.get("agent_status"))
        # La pregunta del turno anterior no cuenta mientras ya está trabajando en otro; un comando local
        # (/reload-plugins) no le pide nada nuevo al modelo, así que la pregunta sigue en pie.
        sigue_en_pie = status == "working" and digest is not None and digest.tail == "claude_text"
        asks_user = asks_user and status != "blocked" and (status != "working" or sigue_en_pie)
        pregunta_real = asks_user and preguntas > 0
        tareas = fondo.for_session(session_id) if fondo and session_id else []
        return {
            "pane_id": pane_id,
            "kind": agent.get("agent") or "unknown",
            "status": status,
            "fondo": tareas,
            "session_id": session_id,
            "cwd": agent.get("cwd") or "",
            "title": title,
            "doing": doing,
            "pending": pending,
            "estado": estado,
            "asks_user": asks_user,
            "pregunta_real": pregunta_real,
            "preguntas": preguntas if asks_user else 0,
            "turno_local": bool(digest and digest.local_tail),
            "last_activity": (digest.last_message or digest.last_activity) if digest else None,
            "transcript_mtime": digest.last_activity if digest else None,
            "ctx": contexto.for_session(session_id) if contexto and session_id else None,
            "uso": _uso(session_id),
        }

    agents_by_tab: dict = {}
    for agent in snapshot.get("agents", []):
        pane_id = agent.get("pane_id")
        if pane_id and pane_id == self_pane_id:
            continue
        agents_by_tab.setdefault(agent.get("tab_id"), []).append(_agent_entry(agent))

    hidden = frozenset(hidden) | ({self_pane_id} if self_pane_id else frozenset())
    terminales = terminals_by_tab(snapshot, terminal_info or {}, hidden)
    ocultos = frozenset(hidden_workspaces)
    tabs_by_ws: dict = {}
    for tab in snapshot.get("tabs", []):
        if tab.get("workspace_id") in ocultos:
            continue
        tabs_by_ws.setdefault(tab.get("workspace_id"), []).append({
            "id": tab.get("tab_id"),
            "label": tab.get("label") or "",
            "agents": agents_by_tab.get(tab.get("tab_id"), []),
            "terminales": terminales.get(tab.get("tab_id"), []),
        })

    workspaces = []
    for ws in sorted(snapshot.get("workspaces", []), key=lambda w: w.get("number", 0)):
        if ws.get("workspace_id") in ocultos:
            continue
        workspaces.append({
            "id": ws.get("workspace_id"),
            "number": ws.get("number"),
            "label": ws.get("label") or "",
            "pinned": (ws.get("label") or "").strip().casefold() in pinned,
            "status": _status(ws.get("agent_status")),
            "tabs": tabs_by_ws.get(ws.get("workspace_id"), []),
        })

    board = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "focused_tab_id": snapshot.get("focused_tab_id"),
        "self_pane_id": self_pane_id,
        "workspaces": workspaces,
    }
    return board


def fingerprint(board: dict) -> str:
    return json.dumps({k: v for k, v in board.items() if k != "updated_at"}, sort_keys=True)


def _agents(board: dict):
    for ws in board.get("workspaces", []):
        for tab in ws.get("tabs", []):
            yield from tab.get("agents", [])


def find_session_agent(board: dict, session_id: str) -> Optional[dict]:
    return next((a for a in _agents(board) if a.get("session_id") == session_id), None)


def session_activity(board: dict) -> dict:
    return {a["session_id"]: a.get("transcript_mtime") for a in _agents(board) if a.get("session_id")}


class BoardHub:
    """Keeps the board fresh only while at least one SSE client is subscribed."""

    def __init__(self, enchufe: Terminales, digests: DigestService, debounce: float = DEBOUNCE,
                 fondo: Optional[FondoService] = None):
        self.enchufe = enchufe
        self.digests = digests
        self.fondo = fondo
        self.debounce = debounce
        # El orquestador corre headless, fuera de Herdr: no hay pane propio que ocultar.
        self.self_pane_id = None
        self.env_pane = sesion_propia()
        self.terminals = ProcessInfoCache(enchufe)
        self.contexto = ContextoService(digests)
        self.uso_hoy: Optional[Callable[[], dict]] = None
        self.pinned: frozenset = frozenset()
        self.board: Optional[dict] = None
        self.source = "idle"
        self.subscribers: set = set()
        self._task: Optional[asyncio.Task] = None
        self._fp = ""
        self.observers: list = []
        self.keep_alive = False
        self.replies = None
        self.estados: EstadoSesiones | None = None
        self.fuente: Callable[[], str] = lambda: "herdr"
        self.sombra = None
        self.crudo: dict | None = None
        self.interna: Callable[[str], bool] | None = None
        self.trabas: Callable[[str], Optional[dict]] | None = None

    def _marcar_trabas(self, board: dict) -> None:
        if self.trabas is None:
            return
        for agent in _agents(board):
            sid = agent.get("session_id")
            traba = self.trabas(sid) if sid else None
            if traba:
                agent["traba"] = traba
            else:
                agent.pop("traba", None)

    def _fuente_efectiva(self) -> str:
        try:
            return self.fuente()
        except Exception as exc:
            log.warning("fuente() falló, usando herdr: %s", exc)
            return "herdr"

    def fp_for(self, board: dict) -> str:
        """Huella del tablero publicado, sin recalcularla; un tablero viejo de la cola se calcula."""
        return self._fp if board is self.board else fingerprint(board)

    def _publicar(self, board: dict, force: bool = False) -> dict:
        self._marcar_trabas(board)
        if self.replies is not None:
            self.replies.observe(self.board, board)
            self.replies.annotate(board)
        fp = fingerprint(board)
        changed = fp != self._fp
        self._fp = fp
        previous, self.board = self.board, board
        if changed:
            for observer in self.observers:
                try:
                    observer(previous, board)
                except Exception as exc:
                    log.warning("observer del board falló: %s", exc)
        if changed or force:
            for queue in list(self.subscribers):
                self._offer(queue, board)
        return board

    def reaplicar(self) -> None:
        if self.crudo is None:
            return
        board = self.crudo
        if self.sombra is not None:
            self.sombra.observar(board, self.estados)
        if self.estados is not None:
            board = aplicar_fuente(board, self.estados, self._fuente_efectiva())
        self._publicar(board)

    async def refresh(self, force: bool = False) -> dict:
        snapshot = como_snapshot(await self.enchufe.tablero())
        hidden = frozenset(p for p in (self.self_pane_id, self.env_pane) if p)
        info = await self.terminals.many(terminal_panes(snapshot, hidden))
        board = await asyncio.to_thread(
            build_board, snapshot, self.digests, self.self_pane_id, self.pinned, info,
            hidden, self.contexto, frozenset(), self.fondo, self.interna, self.uso_hoy,
        )
        board["terminales"] = "ok"
        board["conflictos"] = snapshot.get("conflictos", [])
        board["caidos"] = snapshot.get("caidos", [])
        self.crudo = board if self.estados is not None else None
        if self.sombra is not None:
            self.sombra.observar(board, self.estados)
        if self.estados is not None:
            board = aplicar_fuente(board, self.estados, self._fuente_efectiva())
        return self._publicar(board, force)

    def _offer_sin_conexion(self) -> None:
        base = self.board or {"workspaces": [], "conflictos": [], "caidos": []}
        board = {
            **base,
            "terminales": "sin_conexion",
            "conflictos": base.get("conflictos", []),
            "caidos": base.get("caidos", []),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        fp = fingerprint(board)
        if fp == self._fp:
            return
        self._fp = fp
        if self.board is not None:
            self.board = board
        if self.crudo is not None:
            self.crudo["terminales"] = "sin_conexion"
        for queue in list(self.subscribers):
            self._offer(queue, board)

    def mark_pregunta_vista(self, session_id: str) -> None:
        if self.replies is None:
            return
        self.replies.mark_pregunta_vista(session_id)
        if self.board is None:
            return
        if self.crudo is None:
            board = self.replies.annotated_copy(self.board)
            self.board = board
            self._fp = fingerprint(board)
            for queue in list(self.subscribers):
                self._offer(queue, board)
            return
        self.reaplicar()

    def mark_seen(self, session_id: str) -> None:
        if self.replies is not None:
            self.replies.mark_seen(session_id)
        if self.board is None:
            return
        if self.estados is None:
            board = self.replies.annotated_copy(self.board)
            self.board = board
            self._fp = fingerprint(board)
            for queue in list(self.subscribers):
                self._offer(queue, board)
            return
        self.estados.marcar_visto(session_id)
        if self.crudo is None:
            if self.replies is not None:
                board = self.replies.annotated_copy(self.board)
            else:
                board = copy.deepcopy(self.board)
            self.board = board
            self._fp = fingerprint(board)
            for queue in list(self.subscribers):
                self._offer(queue, board)
            return
        self.reaplicar()

    @staticmethod
    def _offer(queue: asyncio.Queue, board: dict) -> None:
        while True:
            try:
                queue.put_nowait(board)
                return
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

    async def current(self) -> dict:
        if self.board is None:
            return await self.refresh()
        if self.board.get("terminales") == "sin_conexion":
            try:
                return await self.refresh()
            except TerminalesError:
                return self.board
        return self.board

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.subscribers.add(queue)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        return queue

    def set_keep_alive(self, value: bool) -> None:
        self.keep_alive = value
        if value and (self._task is None or self._task.done()):
            self._task = asyncio.create_task(self._run())
        elif not value and not self.subscribers and self._task and not self._task.done():
            self._task.cancel()
            self._task = None
            self.source = "idle"

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.discard(queue)
        if not self.subscribers and not self.keep_alive and self._task and not self._task.done():
            self._task.cancel()
            self._task = None
            self.source = "idle"

    async def _safe_refresh(self) -> None:
        try:
            await self.refresh()
        except Ilegible as exc:
            log.warning("snapshot falló: %s", exc)
        except TerminalesError as exc:
            log.warning("snapshot falló: %s", exc)
            self._offer_sin_conexion()
        except Exception as exc:
            log.warning("snapshot falló: %s", exc)

    async def _debounced_refresh(self) -> None:
        await asyncio.sleep(self.debounce)
        await self._safe_refresh()

    async def _run(self) -> None:
        await self._safe_refresh()
        pending: Optional[asyncio.Task] = None
        sub = None
        try:
            while True:
                try:
                    sub = self.enchufe.suscribir()
                    async for ev in sub:
                        via = ev.datos.get("via")
                        if via:
                            self.source = via
                        if ev.tipo == "caido":
                            if pending is not None and not pending.done():
                                pending.cancel()
                            self._offer_sin_conexion()
                        elif ev.tipo == "volvio" or (
                            ev.tipo == "tablero" and ev.datos.get("motivo") in ("poll", "seguridad")
                        ):
                            if pending is not None and not pending.done():
                                pending.cancel()
                            await self._safe_refresh()
                        else:
                            if pending is None or pending.done():
                                pending = asyncio.create_task(self._debounced_refresh())
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("suscripción del enchufe terminó: %s", exc)
                finally:
                    if sub is not None:
                        try:
                            await sub.aclose()
                        except Exception as exc:
                            log.warning("cierre de suscripción del enchufe falló: %s", exc)
                        sub = None
                await asyncio.sleep(max(self.debounce, 1.0))
        except asyncio.CancelledError:
            raise
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
            if sub is not None:
                try:
                    await sub.aclose()
                except Exception as exc:
                    log.warning("cierre de suscripción del enchufe falló: %s", exc)
