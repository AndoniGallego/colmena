import json
import re
import threading
from pathlib import Path
from typing import Callable, Optional

from .biblioteca import captura_ids_for_block, extract_bloques, extract_pruebas, puede_tener_diagrama, puede_tener_pruebas
from . import kit_trabajo
from .comando_sesion import bloques_comando, cwd_de, puede_tener_comando
from .captura_rutas import local_paths_en_markdown, quitar_imagenes_locales
from .contexto import _boundary
from .digest import DigestService, _clip, is_system_text, queued_prompt
from .jsonl_incremental import JsonlReadState, read_new_lines
from .statusline import build, ctx_dir, parse_timestamp, read_snapshot, read_ticket, used_tokens

MAX_ITEM_CHARS = 20000
SUMMARY_CHARS = 160
DEFAULT_LIMIT = 60
TAIL_OVERLAP = 5  # mensajes que se repiten en una cola parcial para recoger lib_ids tardíos
MAX_LIMIT = 200
CACHE_SIZE = 16
SUMMARY_KEYS = ("file_path", "path", "notebook_path", "pattern", "command", "url", "query", "description", "prompt")
SPACES = re.compile(r"\s+")
MR_URL_RE = re.compile(r"https://[^/\s\"']+/([A-Za-z0-9][A-Za-z0-9._/-]{0,300})/-/merge_requests/(\d{1,9})\b")


COLMENA_KEYS = {"leer_sesion": ("pane_id",), "dialogo": ("pane_id",), "encargo_crear": ("titulo",),
                "encargo_actualizar": ("id",), "encargo_cerrar": ("id",), "mandar": ("pane_id", "texto")}


def _tool_summary(data, name: str = "") -> str:
    if not isinstance(data, dict):
        return ""
    keys = COLMENA_KEYS.get(name.removeprefix("mcp__colmena__")) if name.startswith("mcp__colmena__") else None
    if keys:
        parts = [SPACES.sub(" ", data[k]).strip() for k in keys if isinstance(data.get(k), str) and data[k].strip()]
        return ": ".join(parts)[:SUMMARY_CHARS]
    for key in SUMMARY_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return SPACES.sub(" ", value).strip()[:SUMMARY_CHARS]
    return ""


def _user_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_result":
            continue
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "image":
            parts.append("[imagen]")
    return "\n".join(parts)


def _session_id_from_path(path: Path) -> str:
    if path.parent.name == "subagents":
        return path.parent.parent.name
    return path.stem


def _flush_fotos(items: list, buf: list, ts: str) -> None:
    if not buf:
        return
    items.append({"kind": "imagenes", "ts": ts or "", "fotos": buf[:]})
    buf.clear()


def _note_meta(obj: dict, meta: dict) -> None:
    if obj.get("isSidechain") is True:
        return
    msg = obj.get("message") or {}
    model = msg.get("model")
    if not isinstance(model, str) or not model or model.startswith("<"):
        return
    meta["model"] = model
    ts = parse_timestamp(obj.get("timestamp"))
    if ts is not None:
        meta["ts"] = ts
    tokens = used_tokens(msg.get("usage"))
    if tokens is not None:
        meta["tokens"] = tokens


def _transcript_ctx(session_id: str, captura_ruta: Optional[Callable[[str], Optional[str]]]) -> dict:
    return {"items": [], "meta": {}, "boundary": None, "foto_buf": [], "session_id": session_id,
            "captura_ruta": captura_ruta}


def _apply_transcript_line(ctx: dict, obj: dict) -> None:
    if not isinstance(obj, dict):
        return
    items, meta = ctx["items"], ctx["meta"]
    boundary, foto_buf = ctx["boundary"], ctx["foto_buf"]
    session_id, captura_ruta = ctx["session_id"], ctx["captura_ruta"]
    if obj.get("type") == "attachment":
        text = queued_prompt(obj)
        if text.strip():
            ts = obj.get("timestamp") if isinstance(obj.get("timestamp"), str) else ""
            items.append({"kind": "user", "text": _clip(text, MAX_ITEM_CHARS), "ts": ts})
        return
    if obj.get("type") == "system":
        ctx["boundary"] = _boundary(obj) or boundary
        return
    if obj.get("type") not in ("user", "assistant"):
        return
    if obj["type"] == "assistant":
        _note_meta(obj, meta)
    ts = obj.get("timestamp") if isinstance(obj.get("timestamp"), str) else ""
    content = (obj.get("message") or {}).get("content")
    if obj["type"] == "user":
        text = _user_text(content)
        if obj.get("isCompactSummary"):
            if text.strip():
                _flush_fotos(items, foto_buf, ts)
                entry = {"kind": "compact", "text": _clip(text, MAX_ITEM_CHARS), "ts": ts}
                if ctx["boundary"]:
                    entry["compact"] = {k: ctx["boundary"][k] for k in ("trigger", "pre", "post")}
                    ctx["boundary"] = None
                items.append(entry)
            return
        if text.strip() and not is_system_text(obj, text):
            _flush_fotos(items, foto_buf, ts)
            items.append({"kind": "user", "text": _clip(text, MAX_ITEM_CHARS), "ts": ts})
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result" \
                        and block.get("is_error") is not True:
                    foto_buf.extend(captura_ids_for_block(session_id, block))
        return
    if not isinstance(content, list):
        return
    mid = str(obj.get("uuid") or (obj.get("message") or {}).get("id") or ts)
    diagramas = 0
    comandos = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and (block.get("text") or "").strip():
            raw_text = block["text"]
            rutas_fotos: list = []
            text_out = raw_text
            if captura_ruta is not None:
                resueltas: set = set()
                for ruta, _alt in local_paths_en_markdown(raw_text):
                    iid = captura_ruta(ruta)
                    if iid:
                        resueltas.add(ruta)
                        rutas_fotos.append({"id": iid})
                text_out = quitar_imagenes_locales(raw_text, resueltas)
                if rutas_fotos:
                    ids = {f["id"] for f in rutas_fotos}
                    foto_buf[:] = [f for f in foto_buf if f.get("id") not in ids]
            _flush_fotos(items, foto_buf, ts)
            entry = {"kind": "claude", "text": _clip(text_out, MAX_ITEM_CHARS), "ts": ts}
            if captura_ruta is not None:
                evidencias = _pruebas_evidencias(raw_text, captura_ruta)
                if evidencias:
                    entry["evidencias"] = evidencias
            if puede_tener_diagrama(raw_text):
                count = len(extract_bloques(raw_text))
                if count:
                    entry.update(mid=mid, dstart=diagramas, dcount=count)
                    diagramas += count
            if puede_tener_comando(raw_text):
                count = len(bloques_comando(raw_text))
                if count:
                    entry.update(cmid=mid, cstart=comandos)
                    if cwd_de(obj):
                        entry["ccwd"] = cwd_de(obj)
                    comandos += count
            items.append(entry)
            if rutas_fotos:
                items.append({"kind": "imagenes", "ts": ts or "", "fotos": rutas_fotos})
        elif block.get("type") == "tool_use":
            entry = {"kind": "tool", "name": str(block.get("name") or "")[:40],
                     "summary": _tool_summary(block.get("input"), str(block.get("name") or "")), "ts": ts}
            if block.get("name") in ("Artifact", "SendUserFile") and isinstance(block.get("id"), str):
                entry["tid"] = block["id"]
            items.append(entry)


def _pruebas_evidencias(text: str, captura_ruta) -> dict:
    if not puede_tener_pruebas(text):
        return {}
    out: dict = {}
    for _raw, _titulo, data in extract_pruebas(text):
        for caso in data["casos"]:
            ruta = caso.get("evidencia")
            iid = captura_ruta(ruta) if ruta and ruta not in out else None
            if iid:
                out[ruta] = iid
    return out


def _parse_transcript_raw_lines(ctx: dict, raw_lines: list[bytes]) -> None:
    for raw in raw_lines:
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        _apply_transcript_line(ctx, obj)


def _transcript_return(items: list, meta: dict, foto_buf: list, *, at_eof: bool) -> tuple[list, dict]:
    out = list(items)
    if at_eof and foto_buf:
        out.append({"kind": "imagenes", "ts": "", "fotos": list(foto_buf)})
    return out, dict(meta)


def parse_file(path: Path, captura_ruta: Optional[Callable[[str], Optional[str]]] = None) -> tuple:
    session_id = _session_id_from_path(path)
    ctx = _transcript_ctx(session_id, captura_ruta)
    raw_lines, _, _ = read_new_lines(path, None, final=True)
    if raw_lines:
        _parse_transcript_raw_lines(ctx, raw_lines)
    _flush_fotos(ctx["items"], ctx["foto_buf"], "")
    return ctx["items"], ctx["meta"]


def parse_items(path: Path) -> list:
    return parse_file(path)[0]


def _tool_result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(parts)
    return ""


_GLAB_MR_CREATE_RE = re.compile(r"(?:^|[\s;&|(])(?:[\w~.-]*/)*glab\s+mr\s+create(?![\w-])")


def _sin_comillas(cmd: str) -> str:
    """El comando con lo que va entre comillas simples o dobles tapado con espacios."""
    out: list[str] = []
    quote = ""
    i = 0
    while i < len(cmd):
        c = cmd[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                out.append("  ")
                continue
            if c == quote:
                quote = ""
            out.append(" ")
        elif c == "\\":
            out.append(cmd[i:i + 2])
            i += 2
            continue
        elif c in "'\"":
            quote = c
            out.append(" ")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _ejecuta_glab_mr_create(cmd: str) -> bool:
    return bool(_GLAB_MR_CREATE_RE.search(_sin_comillas(cmd)))


def mr_creados_glab_en_transcript(path: Path) -> list[tuple[str, int]]:
    """Pares (proyecto GitLab, iid) de MRs creados con `glab mr create` según el transcript."""
    glab_pending: dict[str, bool] = {}
    found: list[tuple[str, int]] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(obj, dict) or obj.get("type") not in ("user", "assistant"):
                    continue
                content = (obj.get("message") or {}).get("content")
                blocks = content if isinstance(content, list) else []
                if obj["type"] == "assistant":
                    for block in blocks:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        if block.get("name") != "Bash" or not isinstance(block.get("id"), str):
                            continue
                        inp = block.get("input")
                        cmd = inp.get("command") if isinstance(inp, dict) else ""
                        if isinstance(cmd, str) and _ejecuta_glab_mr_create(cmd):
                            glab_pending[block["id"]] = True
                    continue
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    tid = block.get("tool_use_id")
                    if not isinstance(tid, str) or tid not in glab_pending:
                        continue
                    text = _tool_result_text(block.get("content"))
                    if "merge_requests" not in text:
                        continue
                    for m in MR_URL_RE.finditer(text):
                        found.append((m.group(1), int(m.group(2))))
                    glab_pending.pop(tid, None)
    except OSError:
        return []
    return found


PENDING_TAIL_BYTES = 1024 * 1024
PENDING_MAX = 8


def _tail_lines(path: Path) -> list:
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > PENDING_TAIL_BYTES:
            fh.seek(size - PENDING_TAIL_BYTES)
            fh.readline()
        data = fh.read()
    return data.decode("utf-8", errors="replace").splitlines()


def parse_pending(path: Path) -> dict:
    """`tool_use` del turno actual sin `tool_result` todavía, más la versión de Claude Code (de la cola del .jsonl)."""
    open_uses: dict = {}
    version = None
    for line in _tail_lines(path):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get("type") not in ("user", "assistant") or obj.get("isSidechain") is True:
            continue
        if isinstance(obj.get("version"), str):
            version = obj["version"][:40]
        content = (obj.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else []
        if obj["type"] == "assistant":
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                    open_uses[block["id"]] = {"id": block["id"], "name": str(block.get("name") or ""),
                                              "input": block.get("input") if isinstance(block.get("input"), dict) else {}}
            continue
        results = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
        for block in results:
            open_uses.pop(block.get("tool_use_id"), None)
        if not results and _user_text(content).strip():
            open_uses.clear()
    pending = list(open_uses.values())
    return {"pendientes": pending[-PENDING_MAX:], "version": version}


class TranscriptService:
    def __init__(self, digests: DigestService, title_dir: Optional[Path] = None, ctx_dir: Optional[Path] = None):
        self.digests = digests
        self._ctx_dir = ctx_dir
        self._parse: dict = {}
        self._last_parsed: dict[str, tuple] = {}
        self._parse_lock = threading.Lock()
        self._pending_cache: dict = {}
        self._pending_lock = threading.Lock()
        self._title_dir = title_dir
        self.library = None

    def _parsed(self, session_id: str) -> Optional[tuple]:
        path = self.digests.find(session_id)
        if path is None:
            return None
        try:
            st = path.stat()
        except OSError:
            return None
        rutas_gen = getattr(self.library, "rutas_gen", 0)
        lookup = self.library.captura_ruta_lookup(session_id) if self.library is not None else None
        path_key = str(path)
        with self._parse_lock:
            prev = self._parse.get(session_id)
            jstate = None
            sid = _session_id_from_path(path)
            if prev and prev[0] == path_key and prev[1] == st.st_ino and st.st_size >= prev[2].offset \
                    and prev[5] == rutas_gen:
                jstate = prev[2]
            need_reset = (
                prev is None or prev[0] != path_key or prev[1] != st.st_ino
                or st.st_size < (prev[2].offset if prev else 0) or (prev and prev[5] != rutas_gen)
            )
            jstate_in = None if need_reset else jstate
            consume_tail = jstate_in is None
            raw_lines, jstate, reset = read_new_lines(
                path, jstate_in, final=False, consume_valid_tail=consume_tail
            )
            if reset and prev is not None:
                raw_lines, jstate, reset = read_new_lines(
                    path, None, final=False, consume_valid_tail=True
                )
                need_reset = True
            if not raw_lines and not reset and not need_reset and prev is not None:
                cached = self._last_parsed.get(session_id)
                if cached is not None:
                    return cached
            if need_reset:
                ctx = _transcript_ctx(sid, lookup)
            else:
                ctx = {"items": list(prev[3]), "meta": dict(prev[4]), "boundary": prev[6],
                       "foto_buf": list(prev[7]), "session_id": sid, "captura_ruta": lookup}
            if raw_lines:
                _parse_transcript_raw_lines(ctx, raw_lines)
            at_eof = jstate.size >= st.st_size
            self._parse.pop(session_id, None)
            self._parse[session_id] = (
                path_key, st.st_ino, jstate, ctx["items"], ctx["meta"], rutas_gen, ctx["boundary"], ctx["foto_buf"]
            )
            while len(self._parse) > CACHE_SIZE:
                evicted = next(iter(self._parse))
                self._parse.pop(evicted)
                self._last_parsed.pop(evicted, None)
            out = _transcript_return(ctx["items"], ctx["meta"], ctx["foto_buf"], at_eof=at_eof)
            self._last_parsed[session_id] = out
            return out

    def pending(self, session_id: str) -> Optional[dict]:
        path = self.digests.find(session_id)
        if path is None:
            return None
        try:
            stat = path.stat()
            key = (str(path), stat.st_mtime_ns, stat.st_size)
            cached = self._pending_cache.get(session_id)
            if cached and cached[0] == key:
                return cached[1]
            result = parse_pending(path)
        except OSError:
            return None
        with self._pending_lock:
            self._pending_cache.pop(session_id, None)
            self._pending_cache[session_id] = (key, result)
            while len(self._pending_cache) > CACHE_SIZE:
                self._pending_cache.pop(next(iter(self._pending_cache)), None)
        return result

    @property
    def title_dir(self) -> Path:
        return self._title_dir or Path.home() / ".claude" / kit_trabajo.valor("carpeta_titulos")

    def _snapshot(self, session_id: str, meta: dict) -> Optional[dict]:
        return read_snapshot(self._ctx_dir or ctx_dir(), session_id, meta.get("ts"))

    def _items(self, session_id: str) -> Optional[list]:
        parsed = self._parsed(session_id)
        return parsed[0] if parsed else None

    def _decorate(self, session_id: str, item: dict) -> Optional[dict]:
        if item.get("kind") == "imagenes":
            if self.library is None:
                return item
            fotos = [f for f in item["fotos"] if self.library.foto_disponible(f["id"])]
            return {**item, "fotos": fotos} if fotos else None
        if "tid" not in item and "mid" not in item:
            return item
        out = {k: v for k, v in item.items() if k not in ("tid", "mid", "dstart", "dcount")}
        if self.library is not None:
            ids = (self.library.lib_ids_for_tool(item["tid"]) if "tid" in item else
                   self.library.lib_ids_for_diagramas(session_id, item["mid"], item["dstart"], item["dcount"]))
            if ids:
                out["lib_ids"] = ids
        return out

    def page(self, session_id: str, before: Optional[int], limit: int, desde: Optional[int] = None) -> Optional[dict]:
        if self.library is not None:
            self.library.index_sessions([session_id])
        parsed = self._parsed(session_id)
        if parsed is None:
            return None
        return self._pagina(session_id, parsed, before, limit, desde)

    def vacia(self, session_id: str) -> dict:
        """Una sesión que ya está en el tablero pero todavía no escribió su transcript."""
        return self._pagina(session_id, ([], {}), None, 1)

    def _pagina(self, session_id: str, parsed: tuple, before: Optional[int], limit: int,
                desde: Optional[int] = None) -> dict:
        items, meta = parsed
        end = len(items) if before is None else min(max(before, 0), len(items))
        start = max(0, end - min(max(limit, 1), MAX_LIMIT))
        if desde is not None and before is None and 0 <= desde < len(items):
            start = max(start, desde - TAIL_OVERLAP, 0)
        ticket = read_ticket(self.title_dir, session_id)
        shown = []
        for pos, it in enumerate(items[start:end], start):
            d = self._decorate(session_id, it)
            if d is not None:
                shown.append({**d, "idx": pos})
        return {"items": shown, "before": start if start > 0 else None,
                "status_line": build(meta, ticket, self._snapshot(session_id, meta))}
