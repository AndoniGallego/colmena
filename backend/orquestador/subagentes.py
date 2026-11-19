import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .digest import SESSION_ID

MAX_AGENTS = 30
TAIL_BYTES = 64 * 1024
HEAD_BYTES = 16 * 1024
PARENT_TAIL_BYTES = 2 * 1024 * 1024
USAGE_MAX_BYTES = 4 * 1024 * 1024
ACTIVE_SECS = 10 * 60
AGENT_FILE = re.compile(r"^agent-([A-Za-z0-9_-]+)\.meta\.json$")
NOTIFICATION = re.compile(r"<tool-use-id>([A-Za-z0-9_-]+)</tool-use-id>.{0,600}?<status>(\w+)</status>", re.S)
FAMILY = re.compile(r"(opus|sonnet|haiku|fable)", re.I)
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
DONE_STATUSES = {"completed", "failed", "killed", "stopped"}


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _base(value) -> str:
    return _clip(Path(value).name, 60) if isinstance(value, str) and value else ""


def _step(name: str, inp: dict) -> str:
    if name == "Read":
        f = _base(inp.get("file_path"))
        return f"Leyendo {f}" if f else "Leyendo un archivo"
    if name in EDIT_TOOLS:
        f = _base(inp.get("file_path") or inp.get("notebook_path"))
        return f"Editando {f}" if f else "Editando un archivo"
    if name == "Bash":
        d = inp.get("description")
        return f"Corriendo: {_clip(d, 80)}" if isinstance(d, str) and d.strip() else "Corriendo un comando"
    if name in ("Grep", "Glob"):
        return "Buscando en el código"
    if name in ("Agent", "Task"):
        return "Lanzando un agente"
    if name in ("WebSearch", "WebFetch"):
        return "Buscando en internet"
    if name == "SubagentHandback":
        return "Entregando el resultado"
    return f"Usando {_clip(name, 40)}"


def _read_tail(path: Path, size: int) -> list:
    with path.open("rb") as fh:
        total = fh.seek(0, 2)
        fh.seek(max(0, total - size))
        data = fh.read()
        cut = total > size
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if cut else lines


def _read_head(path: Path) -> list:
    with path.open("rb") as fh:
        data = fh.read(HEAD_BYTES + 1)
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[:-1] if len(data) > HEAD_BYTES else lines


def _parse(lines: list):
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            yield obj


def _blocks(obj: dict) -> list:
    content = (obj.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _epoch(stamp) -> Optional[float]:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def _model_chip(raw) -> str:
    if not isinstance(raw, str) or not raw:
        return ""
    found = FAMILY.search(raw)
    return found.group(1).lower() if found else _clip(raw, 24)


def _tokens(path: Path, size: int) -> Optional[int]:
    if size > USAGE_MAX_BYTES:
        return None
    seen: dict = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for obj in _parse(fh):
            msg = obj.get("message") or {}
            usage = msg.get("usage")
            if obj.get("type") == "assistant" and isinstance(usage, dict):
                n = sum(usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "output_tokens")
                        if isinstance(usage.get(k), int))
                seen[msg.get("id") or id(obj)] = n
    return sum(seen.values()) or None


_PARENT_CACHE_MAX = 256


class SubagentService:
    def __init__(self, projects_dir: Path, find_transcript):
        self.projects_dir = projects_dir
        self._find = find_transcript
        self._cache: dict = {}
        self._parent_cache: dict = {}

    def _safe_dir(self, session_id: str) -> Optional[tuple]:
        if not SESSION_ID.match(session_id):
            return None
        transcript = self._find(session_id)
        if transcript is None:
            return None
        try:
            root = self.projects_dir.resolve()
            folder = (transcript.parent / session_id / "subagents")
            if folder.is_symlink() or not folder.is_dir():
                return None
            real = folder.resolve()
            if root not in real.parents:
                return None
            return transcript, real
        except OSError:
            return None

    def _parent_status(self, transcript: Path) -> dict:
        out: dict = {}
        try:
            st = transcript.stat()
        except OSError:
            return out
        key = (st.st_mtime_ns, st.st_size)
        ck = str(transcript)
        hit = self._parent_cache.get(ck)
        if hit and hit[0] == key:
            return dict(hit[1])
        try:
            text = "\n".join(_read_tail(transcript, PARENT_TAIL_BYTES))
        except OSError:
            return out
        for tid, status in NOTIFICATION.findall(text):
            if status in DONE_STATUSES:
                out[tid] = status
        self._parent_cache[ck] = (key, dict(out))
        if len(self._parent_cache) > _PARENT_CACHE_MAX:
            self._parent_cache.pop(next(iter(self._parent_cache)))
        return dict(out)

    def _one(self, folder: Path, agent_id: str, meta_path: Path, done: dict, now: float) -> Optional[dict]:
        log = folder / f"agent-{agent_id}.jsonl"
        try:
            if meta_path.is_symlink() or log.is_symlink() or not log.is_file():
                return None
            real_log = log.resolve()
            if folder not in real_log.parents:
                return None
            st = log.stat()
            key = (st.st_mtime_ns, st.st_size)
            cached = self._cache.get(str(log))
            if cached and cached[0] == key:
                base = cached[1]
            else:
                base = self._read_log(log, meta_path, st.st_size)
                self._cache[str(log)] = (key, base)
                if len(self._cache) > 400:
                    self._cache.pop(next(iter(self._cache)))
        except OSError:
            return None
        finished = base["handback"] or base["tool_use_id"] in done
        idle = now - st.st_mtime
        estado = "termino" if finished else ("trabajando" if idle <= ACTIVE_SECS else "sin_actividad")
        start = base["start"] or st.st_mtime
        end = st.st_mtime if estado != "trabajando" else now
        return {
            "id": agent_id[:8],
            "descripcion": base["descripcion"],
            "tipo": base["tipo"],
            "modelo": base["modelo"],
            "estado": estado,
            "inicio": datetime.fromtimestamp(start).astimezone().isoformat(),
            "segundos": max(0, int(end - start)),
            "paso": "Terminó" if estado == "termino" else ("" if estado == "sin_actividad" else base["paso"]),
            "tokens": base["tokens"],
            "_mtime": st.st_mtime,
        }

    def _read_log(self, log: Path, meta_path: Path, size: int) -> dict:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")[:8192])
        except (OSError, ValueError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        tail = list(_parse(_read_tail(log, TAIL_BYTES)))
        head = list(_parse(_read_head(log)))
        paso, model, handback = "Pensando", None, False
        step_found = False
        for obj in reversed(tail):
            if obj.get("type") != "assistant":
                continue
            model = model or (obj.get("message") or {}).get("model")
            for b in reversed(_blocks(obj)):
                if b.get("type") == "tool_use" and isinstance(b.get("name"), str):
                    if not step_found:
                        inp = b.get("input")
                        paso = _step(b["name"], inp if isinstance(inp, dict) else {})
                        step_found = True
                        handback = b["name"] == "SubagentHandback"
            if step_found and model:
                break
        stamps = [_epoch(o.get("timestamp")) for o in head if o.get("timestamp")]
        stamps = [s for s in stamps if s]
        desc = meta.get("description")
        return {
            "descripcion": _clip(desc, 120) if isinstance(desc, str) and desc else "Subagente",
            "tipo": _clip(meta["agentType"], 40) if isinstance(meta.get("agentType"), str) else "",
            "modelo": _model_chip(meta.get("model") if isinstance(meta.get("model"), str) else model),
            "tool_use_id": meta.get("toolUseId") if isinstance(meta.get("toolUseId"), str) else "",
            "start": stamps[0] if stamps else None,
            "paso": paso,
            "handback": handback,
            "tokens": _tokens(log, size),
        }

    def listar(self, session_id: str) -> Optional[list]:
        found = self._safe_dir(session_id)
        if found is None:
            return []
        transcript, folder = found
        try:
            metas = []
            for p in folder.iterdir():
                m = AGENT_FILE.match(p.name)
                if m and p.is_file() and not p.is_symlink():
                    metas.append((p.stat().st_mtime, m.group(1), p))
        except OSError:
            return []
        metas.sort(reverse=True)
        done = self._parent_status(transcript)
        now = time.time()
        items = [self._one(folder, aid, p, done, now) for _, aid, p in metas[:MAX_AGENTS]]
        items = [i for i in items if i]
        order = {"trabajando": 0, "sin_actividad": 1, "termino": 2}
        items.sort(key=lambda i: (order[i["estado"]], -i["_mtime"]))
        for i in items:
            del i["_mtime"]
        return items
