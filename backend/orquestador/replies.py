import copy
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from .digest import fin_de_turno
from .state import StateStore

KEEP_DAYS = 7
TOUCH_EVERY = timedelta(hours=1)
FINISHED = ("idle", "done")
# Margen para deshacer un "respondió" cuando el transcript confirma tarde que fue un comando local.
LATE_LOCAL = timedelta(seconds=30)


def _agents(board: Optional[dict]):
    for ws in (board or {}).get("workspaces", []):
        for tab in ws.get("tabs", []):
            yield from tab.get("agents", [])


def _parse(value) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class ReplyTracker:
    """Marca por sesión cuándo terminó un turno y cuándo lo vio el usuario, compartido entre dispositivos."""

    def __init__(self, state: StateStore, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.state = state
        self.clock = clock

    @property
    def entries(self) -> dict:
        return self.state.data.setdefault("replies", {})

    def is_unread(self, session_id: str) -> bool:
        entry = self.entries.get(session_id) or {}
        replied = _parse(entry.get("replied_at"))
        if replied is None:
            return False
        seen = _parse(entry.get("seen_at"))
        return seen is None or replied > seen

    def observe(self, prev: Optional[dict], board: dict) -> None:
        now = self.clock()
        entries = self.entries
        before = {a.get("session_id"): a for a in _agents(prev) if a.get("session_id")}
        dirty = False
        present = set()
        for agent in _agents(board):
            sid = agent.get("session_id")
            if not sid:
                continue
            present.add(sid)
            old = before.get(sid)
            entry = entries.get(sid)
            if agent.get("status") == "working" and entry is not None and "antes" in entry:
                del entry["antes"]
                dirty = True
            if fin_de_turno(old, agent):
                entry = entries.setdefault(sid, {})
                entry["antes"] = entry.get("replied_at") or ""
                entry["replied_at"] = now.isoformat()
                dirty = True
            elif agent.get("status") in FINISHED and agent.get("turno_local") and entry and "antes" in entry:
                antes = entry.pop("antes")
                if now - (_parse(entry.get("replied_at")) or now - LATE_LOCAL * 2) <= LATE_LOCAL:
                    if antes:
                        entry["replied_at"] = antes
                    else:
                        entry.pop("replied_at", None)
                dirty = True
            entry = entries.get(sid)
            if entry is not None:
                touched = _parse(entry.get("in_board"))
                if touched is None or now - touched >= TOUCH_EVERY:
                    entry["in_board"] = now.isoformat()
                    dirty = True
        if board.get("workspaces") is not None and present:
            limit = now - timedelta(days=KEEP_DAYS)
            for sid in [s for s, e in entries.items() if s not in present and (_parse(e.get("in_board")) or now) < limit]:
                del entries[sid]
                dirty = True
        if dirty:
            self.state.save()

    def mark_seen(self, session_id: str) -> None:
        entry = self.entries.setdefault(session_id, {})
        entry["seen_at"] = self.clock().isoformat()
        entry.setdefault("in_board", entry["seen_at"])
        self.state.save()

    def mark_pregunta_vista(self, session_id: str) -> None:
        """El usuario dio por leída la pregunta del turno actual: pasa a pendiente hasta que haya un turno nuevo."""
        entry = self.entries.setdefault(session_id, {})
        now = self.clock().isoformat()
        entry["pregunta_vista_at"] = now
        entry["seen_at"] = now
        entry.setdefault("in_board", now)
        self.state.save()

    def pregunta_vista(self, session_id: str) -> bool:
        entry = self.entries.get(session_id) or {}
        vista = _parse(entry.get("pregunta_vista_at"))
        if vista is None:
            return False
        replied = _parse(entry.get("replied_at"))
        return replied is None or vista >= replied

    def annotate(self, board: dict) -> dict:
        for agent in _agents(board):
            sid = agent.get("session_id")
            agent["unread"] = bool(sid) and self.is_unread(sid)
            marcada = bool(sid) and self.pregunta_vista(sid)
            agent["pendiente"] = marcada and bool(agent.get("asks_user") or agent.get("pendiente"))
            if agent["pendiente"]:
                agent["asks_user"] = False
                agent["pregunta_real"] = False
                agent["preguntas"] = 0
        return board

    def annotated_copy(self, board: dict) -> dict:
        return self.annotate(copy.deepcopy(board))
