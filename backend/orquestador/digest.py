import json
import re
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import silencio
from .jsonl_incremental import JsonlReadState, read_new_lines
from .legado import LEGACY_FENCE

# Comandos que Claude Code resuelve solo (/reload-plugins, /model, /compact, `!ls`...): el modelo no responde.
LOCAL_PREFIX = re.compile(r"^\s*<(command-name|command-message|command-args|local-command-|bash-input|bash-stdout|bash-stderr)")
SKIP_PREFIX = re.compile(r"^(<(command-|local-command|system-reminder|task-notification)|Another Claude session sent a message)")


def is_system_text(obj: dict, text: str) -> bool:
    """Avisos que el harness inyecta como turno de usuario (subagentes, tareas en segundo plano)."""
    return bool(obj.get("isMeta") or obj.get("promptSource") == "system" or SKIP_PREFIX.match(text))


def queued_prompt(obj: dict) -> str:
    """Mensaje humano que Claude Code absorbió a mitad de turno (no queda como entrada `user`)."""
    att = obj.get("attachment")
    if obj.get("type") != "attachment" or not isinstance(att, dict) or att.get("type") != "queued_command":
        return ""
    origin = att.get("origin")
    human = att.get("humanTurn") is True or (isinstance(origin, dict) and origin.get("kind") == "human")
    prompt = att.get("prompt")
    if att.get("commandMode") != "prompt" or not human or not isinstance(prompt, str):
        return ""
    return "" if is_system_text(obj, prompt) else prompt


SESSION_ID = re.compile(r"^[A-Za-z0-9_-]+$")
CACHE_SIZE = 256
# Lo máximo que pide la pantalla (app.py acota summary a 50): el resto de la conversación no se guarda.
MAX_TURNS = 50
MAX_TURN_CHARS = 12000
OLD_TURN_CHARS = 1200
PENDING_CHARS = 180

_BLOQUE = re.compile(r"(^|\n)[ \t]*(`{3,}|~{3,})[ \t]*(diagrama|opciones|%s)\b[^\n]*\n" % LEGACY_FENCE, re.I)
_TITULO = re.compile(r'"(?:titulo|pregunta)"\s*:\s*"((?:[^"\\]|\\.){1,160})"')
_NOMBRE = {"diagrama": "Diagrama", "opciones": "Opciones", LEGACY_FENCE: "Diagrama"}


ESTADO_CHARS = 120
_FENCE_ABRE = re.compile(r"(^|\n)[ \t]*(`{3,}|~{3,})[ \t]*([^\n]*)\n")
_ESTADO_INFO = re.compile(r"estado\b", re.I)
_ESTADO_CAMPOS = ("hizo", "falta", "pide")


def _bloques_estado(text: str) -> list:
    """[(inicio, fin, cuerpo)] de cada bloque ```estado``` de primer nivel (uno dentro de otro fence no cuenta);
    uno sin cerrar llega hasta el final."""
    out = []
    pos = 0
    while True:
        m = _FENCE_ABRE.search(text, pos)
        if not m:
            return out
        fence = m.group(2)
        close = re.compile(r"\n[ \t]*" + ("`" if fence[0] == "`" else "~") + "{%d,}[ \t]*(?=\n|$)" % len(fence))
        c = close.search(text, m.end() - 1)
        fin = c.end() if c else len(text)
        if _ESTADO_INFO.match(m.group(3)):
            out.append((m.start() + len(m.group(1)), fin, text[m.end():c.start() if c else len(text)]))
        pos = fin


def quitar_estado(text: str) -> str:
    """El texto sin los bloques ```estado```: son para la tarjeta, no para leer."""
    spans = _bloques_estado(text)
    if not spans:
        return text
    out = []
    pos = 0
    for inicio, fin, _ in spans:
        out.append(text[pos:inicio])
        pos = fin
    out.append(text[pos:])
    return re.sub(r"[ \t]*\n{3,}", "\n\n", "".join(out)).strip()


def parse_estado(text: str) -> Optional[dict]:
    """{"hizo"?, "falta"?, "pide"?} del último bloque ```estado```; JSON roto o sin campos de texto = None."""
    spans = _bloques_estado(text or "")
    if not spans:
        return None
    from .opciones import lenient_json
    obj = lenient_json(spans[-1][2])
    if not isinstance(obj, dict):
        return None
    out = {}
    for campo in _ESTADO_CAMPOS:
        valor = obj.get(campo)
        if isinstance(valor, str) and valor.strip():
            out[campo] = clip_words(" ".join(valor.split()), ESTADO_CHARS)
    return out or None


def estados_todos_validos(text: str) -> bool:
    """Como el hook de andokit: al menos un bloque ```estado``` y todos válidos."""
    spans = _bloques_estado(text or "")
    if not spans:
        return False
    from .opciones import lenient_json
    for _, _, cuerpo in spans:
        obj = lenient_json(cuerpo)
        if not isinstance(obj, dict):
            return False
        if not any(isinstance(obj.get(c), str) and obj[c].strip() for c in _ESTADO_CAMPOS):
            return False
    return True


def sin_bloques(text: str) -> str:
    """Cambia los bloques ```diagrama/opciones``` por una frase legible: los avisos nunca muestran JSON."""
    text = quitar_estado(text)
    out = []
    pos = 0
    while True:
        m = _BLOQUE.search(text, pos)
        if not m:
            out.append(text[pos:])
            return re.sub(r"[ \t]*\n{3,}", "\n\n", "".join(out)).strip()
        fence, kind = m.group(2), m.group(3).lower()
        close = re.compile(r"\n[ \t]*" + ("`" if fence[0] == "`" else "~") + "{%d,}[ \t]*(?=\n|$)" % len(fence))
        c = close.search(text, m.end() - 1)
        body = text[m.end():c.start()] if c else text[m.end():]
        t = _TITULO.search(body)
        titulo = ""
        if t:
            try:
                titulo = json.loads('"' + t.group(1) + '"').strip()
            except ValueError:
                titulo = t.group(1).strip()
        frase = titulo if kind == "opciones" and titulo else (f"{_NOMBRE[kind]}: {titulo}" if titulo else _NOMBRE[kind])
        out.append(text[pos:m.start()] + m.group(1) + frase + ("" if frase.endswith(("?", ".", "!")) else ".") + "\n")
        pos = c.end() if c else len(text)


@dataclass
class Digest:
    path: Path
    mtime: float
    title: str = ""
    last_prompt: str = ""
    last_message: str = ""
    turns: list = field(default_factory=list)
    # Desde la última entrada del modelo solo hubo comandos locales: ese fin de turno no trae respuesta nueva.
    local_tail: bool = False
    # Lo último que cuenta para el modelo: "claude_text", "claude_other" o "user" (comandos locales no cuentan).
    tail: str = ""

    @property
    def last_activity(self) -> str:
        return datetime.fromtimestamp(self.mtime, tz=timezone.utc).isoformat()

    def last_claude_text(self) -> str:
        for turn in reversed(self.turns):
            if turn["role"] == "claude":
                return turn["text"]
        return ""


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + " …[recortado]"


def _recent_turns(all_turns: list, count: int) -> list:
    # El último turno va entero: suele ser la respuesta que hay que leer.
    recent = all_turns[-max(1, count):]
    return [{**t, "text": _clip(t["text"], OLD_TURN_CHARS)} for t in recent[:-1]] + recent[-1:]


def clip_words(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.6 else cut).rstrip(" ,.;:") + "…"


_FIN_FRASE = re.compile(r"[.?!…]+[\"')\]]*(?=\s)")


def clip_frase(text: str, limit: int) -> str:
    """Recorta en el final de la última frase completa que entra; sin ninguna razonable, por palabra."""
    if len(text) <= limit:
        return text
    fin = 0
    for m in _FIN_FRASE.finditer(text, 0, limit + 1):
        if m.end() <= limit:
            fin = m.end()
    if fin >= limit * 0.3:
        return text[:fin].rstrip()
    return clip_words(text, limit)


def _user_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _apply_digest_line(digest: Digest, obj: dict, max_chars: int = MAX_TURN_CHARS) -> None:
    if not isinstance(obj, dict):
        return
    kind = obj.get("type")
    if kind == "system":
        if obj.get("subtype") in ("local_command", "compact_boundary"):
            digest.local_tail = True
        return
    if kind == "ai-title":
        digest.title = obj.get("aiTitle") or digest.title
    elif kind == "last-prompt":
        digest.last_prompt = obj.get("lastPrompt") or digest.last_prompt
    elif kind == "attachment":
        text = queued_prompt(obj)
        if text.strip():
            digest.local_tail, digest.tail = False, "user"
            stamp = obj.get("timestamp")
            if isinstance(stamp, str):
                digest.last_message = max(digest.last_message, stamp)
            digest.turns.append({"role": "user", "text": _clip(text, max_chars)})
    elif kind in ("user", "assistant"):
        stamp = obj.get("timestamp")
        if isinstance(stamp, str) and not (obj.get("isMeta") or obj.get("promptSource") == "system"):
            digest.last_message = max(digest.last_message, stamp)
        message = obj.get("message") or {}
        content = message.get("content")
        if kind == "user":
            if obj.get("isCompactSummary"):
                digest.local_tail = True
                return
            if obj.get("isMeta"):
                return
            text = _user_text(content)
            if text and LOCAL_PREFIX.match(text):
                digest.local_tail = True
                return
            digest.local_tail, digest.tail = False, "user"
            if not text or is_system_text(obj, text):
                return
            digest.turns.append({"role": "user", "text": _clip(text, max_chars)})
        else:
            digest.local_tail = False
            if not isinstance(content, list):
                return
            text = "\n".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
            digest.tail = "claude_text" if text else "claude_other"
            if text:
                digest.turns.append({"role": "claude", "text": _clip(text, max_chars)})


def _parse_digest_lines(digest: Digest, raw_lines: list[bytes], max_chars: int = MAX_TURN_CHARS) -> None:
    for raw in raw_lines:
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        _apply_digest_line(digest, obj, max_chars)
    if len(digest.turns) > MAX_TURNS:
        del digest.turns[:-MAX_TURNS]


def parse_transcript(path: Path, max_chars: int = MAX_TURN_CHARS) -> Digest:
    digest = Digest(path=path, mtime=path.stat().st_mtime)
    raw_lines, _, _ = read_new_lines(path, None, final=True)
    if raw_lines:
        _parse_digest_lines(digest, raw_lines, max_chars)
    return digest


def fin_de_turno(was: Optional[dict], agent: dict) -> bool:
    """Pasó de trabajando a terminado con respuesta del modelo; un comando local (/reload-plugins) no cuenta,
    ni nada mientras el actualizador del kit de trabajo tiene abierta su ventana de silencio."""
    return (bool(was) and was.get("status") == "working" and agent.get("status") in ("idle", "done")
            and not agent.get("turno_local") and not silencio.vigente())


class DigestService:
    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir
        self._path_cache: dict[str, Path] = {}
        self._parse: dict[str, tuple[str, int, JsonlReadState, Digest]] = {}
        self._last_digest: dict[str, Digest] = {}
        self._lock = threading.Lock()
        self._find_lock = threading.Lock()

    def find(self, session_id: str) -> Optional[Path]:
        if not SESSION_ID.match(session_id) or not self.projects_dir.is_dir():
            return None
        with self._find_lock:
            cached = self._path_cache.get(session_id)
            if cached is not None:
                if cached.exists():
                    self._path_cache.pop(session_id, None)
                    self._path_cache[session_id] = cached
                    return cached
                self._path_cache.pop(session_id, None)
            for candidate in self.projects_dir.glob(f"*/{session_id}.jsonl"):
                if candidate.is_file():
                    self._path_cache.pop(session_id, None)
                    self._path_cache[session_id] = candidate
                    while len(self._path_cache) > CACHE_SIZE:
                        self._path_cache.pop(next(iter(self._path_cache)), None)
                    return candidate
            return None

    def _load_digest(self, session_id: str, path: Path) -> Digest:
        st = path.stat()
        path_key = str(path)
        with self._lock:
            prev = self._parse.get(session_id)
            jstate, digest = None, None
            if prev and prev[0] == path_key and prev[1] == st.st_ino and st.st_size >= prev[2].offset:
                jstate, digest = prev[2], prev[3]
            consume_tail = jstate is None
            raw_lines, jstate, reset = read_new_lines(
                path, jstate, final=False, consume_valid_tail=consume_tail
            )
            if reset and prev is not None:
                raw_lines, jstate, reset = read_new_lines(
                    path, None, final=False, consume_valid_tail=True
                )
            if not raw_lines and not reset and digest is not None:
                digest.mtime = st.st_mtime
                cached = self._last_digest.get(session_id)
                if cached is not None:
                    return cached
            if digest is None or reset:
                digest = Digest(path=path, mtime=st.st_mtime)
            if raw_lines:
                digest.turns = list(digest.turns)
                _parse_digest_lines(digest, raw_lines)
            digest.mtime = st.st_mtime
            self._parse.pop(session_id, None)
            self._parse[session_id] = (path_key, st.st_ino, jstate, digest)
            while len(self._parse) > CACHE_SIZE:
                evicted = next(iter(self._parse))
                self._parse.pop(evicted)
                self._last_digest.pop(evicted, None)
            out = replace(digest, turns=list(digest.turns))
            self._last_digest[session_id] = out
            return out

    def get(self, session_id: str) -> Optional[Digest]:
        path = self.find(session_id)
        if path is None:
            return None
        try:
            return self._load_digest(session_id, path)
        except OSError:
            return None

    def summary(self, session_id: str, turns: int = 8) -> Optional[dict]:
        digest = self.get(session_id)
        if digest is None:
            return None
        return {
            "title": digest.title,
            "last_prompt": digest.last_prompt[:400],
            "turns": _recent_turns(digest.turns, turns),
        }
