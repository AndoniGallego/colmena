import json
import threading
from pathlib import Path
from typing import Optional

from .digest import DigestService
from .statusline import context_window, ctx_dir, parse_timestamp, read_snapshot, used_tokens

TAIL_BYTES = 4 * 1024 * 1024
MAX_BACK_BYTES = 32 * 1024 * 1024
CHUNK = 4 * 1024 * 1024
CACHE_SIZE = 64
MARK = b"compact_boundary"


def _int(value) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _read_tail(path: Path, size: int, nbytes: int) -> list:
    with path.open("rb") as fh:
        start = max(0, size - nbytes)
        fh.seek(start)
        data = fh.read(size - start)
    lines = data.split(b"\n")
    if start > 0:
        lines = lines[1:]
    return lines


def _boundary(obj: dict) -> Optional[dict]:
    if obj.get("type") != "system" or obj.get("subtype") != "compact_boundary":
        return None
    meta = obj.get("compactMetadata")
    meta = meta if isinstance(meta, dict) else {}
    trigger = meta.get("trigger")
    return {"ts": obj.get("timestamp") if isinstance(obj.get("timestamp"), str) else "",
            "trigger": trigger if trigger in ("auto", "manual") else "auto",
            "pre": _int(meta.get("preTokens")) or 0, "post": _int(meta.get("postTokens")) or 0}


def _scan(lines: list) -> tuple:
    """(último assistant de la cadena principal con usage, último compact_boundary, posición de cada uno)."""
    assistant = None
    boundary = None
    for idx, raw in enumerate(lines):
        if not raw.strip():
            continue
        is_boundary = MARK in raw
        if not is_boundary and b'"assistant"' not in raw:
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        found = _boundary(obj) if is_boundary else None
        if found:
            boundary = (idx, found)
            continue
        if obj.get("type") != "assistant" or obj.get("isSidechain") is True:
            continue
        msg = obj.get("message") or {}
        model = msg.get("model")
        if not isinstance(model, str) or not model or model.startswith("<"):
            continue
        tokens = used_tokens(msg.get("usage"))
        if tokens is None:
            continue
        assistant = (idx, {"tokens": tokens, "model": model, "ts": parse_timestamp(obj.get("timestamp"))})
    return assistant, boundary


def _count_boundaries(path: Path, start: int, end: int) -> tuple:
    """Cuenta compact_boundary entre dos offsets; devuelve (cantidad, última, offset hasta donde leyó)."""
    count = 0
    last = None
    pos = start
    carry = b""
    with path.open("rb") as fh:
        fh.seek(start)
        while pos < end:
            block = fh.read(min(CHUNK, end - pos))
            if not block:
                break
            pos += len(block)
            data = carry + block
            lines = data.split(b"\n")
            carry = lines.pop()
            for raw in lines:
                if MARK not in raw:
                    continue
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                found = _boundary(obj) if isinstance(obj, dict) else None
                if found:
                    count += 1
                    last = found
    return count, last, pos - len(carry)


class ContextoService:
    """Contexto por sesión: el mismo número que la statusline de la terminal, sin niveles de alarma."""

    def __init__(self, digests: DigestService, snapshot_dir: Optional[Path] = None):
        self.digests = digests
        self._snapshot_dir = snapshot_dir
        self._cache: dict = {}
        self._counts: dict = {}
        self._lock = threading.Lock()

    def for_session(self, session_id: str) -> Optional[dict]:
        path = self.digests.find(session_id)
        if path is None:
            return None
        try:
            stat = path.stat()
        except OSError:
            return None
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            hit = self._cache.get(session_id)
        if hit and hit[0] == key:
            base = hit[1]
        else:
            try:
                base = self._read(path, stat.st_size)
            except OSError:
                return None
            with self._lock:
                self._cache.pop(session_id, None)
                self._cache[session_id] = (key, base)
                while len(self._cache) > CACHE_SIZE:
                    self._cache.pop(next(iter(self._cache)))
        return self._finish(session_id, base)

    def _compactions(self, path: Path, size: int) -> tuple:
        key = str(path)
        with self._lock:
            prev = self._counts.get(key)
        if prev is None or prev["pos"] > size:
            prev = {"pos": 0, "count": 0, "last": None}
        count, last, pos = _count_boundaries(path, prev["pos"], size)
        state = {"pos": pos, "count": prev["count"] + count, "last": last or prev["last"]}
        with self._lock:
            self._counts.pop(key, None)
            self._counts[key] = state
            while len(self._counts) > CACHE_SIZE:
                self._counts.pop(next(iter(self._counts)))
        return state["count"], state["last"]

    def _read(self, path: Path, size: int) -> dict:
        window_bytes = TAIL_BYTES
        assistant = boundary = None
        while True:
            assistant, boundary = _scan(_read_tail(path, size, window_bytes))
            if (assistant or boundary) or window_bytes >= min(size, MAX_BACK_BYTES):
                break
            window_bytes = min(window_bytes * 2, MAX_BACK_BYTES)
        count, last = self._compactions(path, size)
        if boundary and not last:
            count, last = max(count, 1), boundary[1]
        use_post = bool(boundary) and (assistant is None or boundary[0] > assistant[0])
        info = assistant[1] if assistant else {}
        tokens = info.get("tokens")
        if use_post:
            post = boundary[1]["post"]
            tokens = post if post else tokens
        return {"tokens": tokens if tokens else None, "model": info.get("model", ""), "ts": info.get("ts"),
                "compactaciones": count, "ultima": last}

    def _finish(self, session_id: str, base: dict) -> Optional[dict]:
        snap = read_snapshot(self._snapshot_dir or ctx_dir(), session_id, base["ts"])
        if snap:
            tokens, window, source = snap["tokens"], snap["window"], "statusline"
        elif base["tokens"]:
            tokens, window, source = base["tokens"], context_window(base["model"]), "transcript"
        else:
            return None
        last = base["ultima"]
        return {"pct": round(tokens * 100 / window), "tokens": tokens, "window": window, "fuente": source,
                "compactaciones": base["compactaciones"],
                "ultima_compactacion": dict(last) if last else None}
