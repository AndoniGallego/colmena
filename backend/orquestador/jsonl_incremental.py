"""Lectura JSONL por offset (líneas completas; la última sin \\n queda pendiente)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class JsonlReadState:
    inode: int
    offset: int = 0
    size: int = 0
    skipline: bool = field(default=False)
    mtime_ns: int = 0


def _valid_json_object(raw: bytes) -> bool:
    if not raw.strip():
        return False
    try:
        json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return False
    return True


def read_new_lines(
    path: Path,
    state: Optional[JsonlReadState],
    *,
    final: bool = False,
    consume_valid_tail: bool = False,
) -> tuple[list[bytes], JsonlReadState, bool]:
    """Devuelve líneas completas nuevas (bytes), estado actualizado y si hubo reset."""
    st = path.stat()
    reset = False
    if state is None or state.inode != st.st_ino or st.st_size < state.offset:
        state = JsonlReadState(inode=st.st_ino, offset=0, size=0, mtime_ns=st.st_mtime_ns)
        reset = True
    elif state.size == st.st_size and state.mtime_ns != st.st_mtime_ns:
        state = JsonlReadState(inode=st.st_ino, offset=0, size=0, mtime_ns=st.st_mtime_ns)
        reset = True
    if (
        state.offset >= st.st_size
        and state.mtime_ns == st.st_mtime_ns
        and not reset
        and not state.skipline
    ):
        with path.open("rb") as fh:
            fh.seek(state.offset)
            if not fh.read(1):
                state.size = max(st.st_size, state.offset)
                return [], state, reset
    base_offset = state.offset
    if consume_valid_tail:
        path.stat()
        path.stat()
    with path.open("rb") as fh:
        fh.seek(state.offset)
        data = fh.read()
    if not data:
        state.size = max(st.st_size, state.offset)
        state.mtime_ns = st.st_mtime_ns
        return [], state, reset
    lines: list[bytes] = []
    head = 0
    if state.skipline:
        nl = data.find(b"\n")
        if nl < 0:
            if final:
                if data.strip():
                    lines.append(data.rstrip(b"\r"))
                head = len(data)
                state.skipline = False
            elif consume_valid_tail and _valid_json_object(data):
                lines.append(data.rstrip(b"\r"))
                head = len(data)
                state.skipline = False
            else:
                state.skipline = True
            state.offset = base_offset + head
            state.size = max(st.st_size, state.offset)
            state.mtime_ns = st.st_mtime_ns
            return lines, state, reset
        if data[:nl].strip():
            lines.append(data[:nl])
        head = nl + 1
        state.skipline = False
    consumed = head
    if head < len(data):
        body = data[head:]
        end = body.rfind(b"\n") + 1
        if end == 0:
            if final:
                if body.strip():
                    lines.append(body.rstrip(b"\r"))
                consumed = head + len(body)
                state.skipline = False
            elif consume_valid_tail and _valid_json_object(body):
                lines.append(body.rstrip(b"\r"))
                consumed = head + len(body)
                state.skipline = False
            else:
                state.skipline = bool(body.strip())
        else:
            extra = body[:end].split(b"\n")
            if extra and extra[-1] == b"":
                extra.pop()
            lines.extend(extra)
            consumed = head + end
            tail = body[end:]
            if tail.strip():
                if final:
                    lines.append(tail.rstrip(b"\r"))
                    consumed = head + len(body)
                    state.skipline = False
                elif consume_valid_tail and _valid_json_object(tail):
                    lines.append(tail.rstrip(b"\r"))
                    consumed = head + len(body)
                    state.skipline = False
                else:
                    state.skipline = True
    state.offset = base_offset + consumed
    state.size = max(st.st_size, state.offset)
    state.mtime_ns = st.st_mtime_ns
    return lines, state, reset
