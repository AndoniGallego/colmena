import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .subagentes import DONE_STATUSES, NOTIFICATION, PARENT_TAIL_BYTES, _read_tail

FONDO_MAX_S = 2 * 3600
AGENT_ASYNC = re.compile(r"async agent launched", re.I)
CURSOR = re.compile(r"cursor-agent")
TEXT_MAX = 60


def _clip(text: str, limit: int = TEXT_MAX) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _epoch(stamp) -> Optional[float]:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def _truthy(value) -> bool:
    return value is True or (isinstance(value, str) and value.casefold() in ("true", "1", "yes"))


def _texto(inp: dict) -> str:
    desc = inp.get("description")
    if isinstance(desc, str) and desc.strip():
        return _clip(desc.strip())
    return "En segundo plano"


def _tipo(name: str, inp: dict) -> str:
    if name == "Agent":
        return "agente"
    if name == "Workflow":
        return "workflow"
    cmd = inp.get("command")
    if name == "Bash" and isinstance(cmd, str) and CURSOR.search(cmd):
        return "cursor"
    return "comando"


def _blocks(obj: dict) -> list:
    content = (obj.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _line_text(obj: dict) -> str:
    if isinstance(obj.get("content"), str):
        return obj["content"]
    parts = []
    for b in _blocks(obj):
        if b.get("type") == "text" and isinstance(b.get("text"), str):
            parts.append(b["text"])
    msg = obj.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), str):
        parts.append(msg["content"])
    return "\n".join(parts)


def _result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
    return ""


def _launch(name: str, inp: dict) -> bool:
    if name in ("Workflow", "Agent"):
        return True
    if name == "Bash":
        return _truthy(inp.get("run_in_background"))
    return False


def _confirmed(name: str, inp: dict, result: str, is_error: bool) -> bool:
    if is_error:
        return False
    if name == "Agent":
        return _truthy(inp.get("run_in_background")) or bool(AGENT_ASYNC.search(result or ""))
    return True


def tareas_pendientes(lines: list, now: Optional[float] = None) -> list:
    """Tareas de segundo plano aún sin task-notification terminal."""
    if now is None:
        now = datetime.now().timestamp()
    done: dict = {}
    for line in lines:
        if not isinstance(line, str):
            continue
        for tid, status in NOTIFICATION.findall(line):
            if status in DONE_STATUSES:
                done[tid] = status
    pending: dict = {}
    for line in lines:
        try:
            obj = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        stamp = _epoch(obj.get("timestamp"))
        for block in _blocks(obj):
            if block.get("type") != "tool_use":
                continue
            name = block.get("name")
            tid = block.get("id")
            inp = block.get("input")
            if not isinstance(name, str) or not isinstance(tid, str) or not isinstance(inp, dict):
                continue
            if not _launch(name, inp):
                continue
            pending[tid] = {"tipo": _tipo(name, inp), "texto": _texto(inp), "desde": stamp or now, "name": name,
                            "inp": inp, "ok": False}
        for block in _blocks(obj):
            if block.get("type") != "tool_result":
                continue
            tid = block.get("tool_use_id")
            if not isinstance(tid, str) or tid not in pending:
                continue
            meta = pending[tid]
            if _confirmed(meta["name"], meta["inp"], _result_text(block), bool(block.get("is_error"))):
                meta["ok"] = True
            else:
                del pending[tid]
    out = []
    for tid, meta in pending.items():
        if not meta.get("ok") or tid in done:
            continue
        if now - (meta.get("desde") or now) > FONDO_MAX_S:
            continue
        out.append({"id": tid, "tipo": meta["tipo"], "texto": meta["texto"], "desde": meta["desde"]})
    out.sort(key=lambda t: t["desde"])
    return out


class FondoService:
    """Lee solo el final del transcript; cache por mtime/size como DigestService."""

    def __init__(self, find_transcript: Callable[[str], Optional[Path]], clock: Callable[[], float] = None):
        self._find = find_transcript
        self._clock = clock or (lambda: datetime.now().timestamp())
        self._cache: dict = {}

    def for_session(self, session_id: str) -> list:
        path = self._find(session_id)
        if path is None:
            return []
        try:
            st = path.stat()
        except OSError:
            return []
        key = (str(path), st.st_mtime_ns, st.st_size)
        cached = self._cache.get(session_id)
        if cached and cached[0] == key:
            return cached[1]
        try:
            lines = _read_tail(path, PARENT_TAIL_BYTES)
        except OSError:
            return []
        items = tareas_pendientes(lines, now=self._clock())
        self._cache[session_id] = (key, items)
        return items
