import base64
import binascii
import hashlib
import hmac
import html as htmllib
import json
import logging
import os
import re
import shutil
import stat as statmod
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import uploads as uploads_mod
from .captura_rutas import EVIDENCIA_ID_RE, id_desde_tool_result, ruta_desde_tool_result
from .legado import LEGACY_FENCE, diagrama_legado, migrar_items
from .config import private_write
from .digest import SESSION_ID

log = logging.getLogger("orquestador.biblioteca")

KINDS = ("html", "image", "svg", "gif", "pdf", "video", "text", "diagrama", "pruebas", "remoto", "reunion", "otro")
MB = 1024 * 1024
MAX_BY_KIND = {"html": 5 * MB, "image": 25 * MB, "gif": 25 * MB, "svg": 2 * MB, "pdf": 50 * MB,
               "video": 200 * MB, "text": 1 * MB}
MAX_ASSET = 20 * MB
MAX_DIAGRAMA_BYTES = 64 * 1024
MAX_REUNION_RAW_BYTES = 64 * 1024
REUNION_TITULO_CHARS = 200
REUNION_TEMA_CHARS = 200  # igual que reunion.TEMA_MAX
REUNION_ITEM_CHARS = 400
MAX_PRUEBAS_CASOS = 60
PRUEBAS_RESULTADOS = ("ok", "falla", "omitida")
PRUEBAS_IMG_EXT = {"png": ("image", "png", "image/png"), "jpg": ("image", "jpeg", "image/jpeg"),
                   "jpeg": ("image", "jpeg", "image/jpeg"), "webp": ("image", "webp", "image/webp"),
                   "gif": ("gif", "gif", "image/gif")}
MAX_DIAGRAMA_NODOS = 200
MAX_DIAGRAMA_CONEXIONES = 400
MAX_ASSETS_PER_TOKEN = 300
MAX_COPY_ITEM = 100 * MB
MAX_COPY_FILES = 300
COPY_TOTAL_CAP = 2 * 1024 * MB
CAPTURA_MAX = 8 * MB
CAPTURAS_BACKFILL_V = 2
CAPTURA_MEDIA = {"image/png": ("image", "png"), "image/jpeg": ("image", "jpeg"),
                 "image/webp": ("image", "webp"), "image/gif": ("gif", "gif")}
CHROME_TOOL_RE = re.compile(r"^mcp__claude-in-chrome__")
COPY_DAYS = 90
TOKEN_TTL = 30 * 60
STAT_TTL = 30.0
RESCAN_THROTTLE = 60.0
PASS_BYTES = 32 * MB
PURGE_GC_INTERVAL = 600.0
MAX_WALK = 5000
MAX_PENDING = 50
MAX_VERSIONS = 50
TITLE_CHARS = 120
TEXT_CHARS = 400
EXT_KIND = {"html": "html", "htm": "html", "png": "image", "jpg": "image", "jpeg": "image", "webp": "image",
            "avif": "image", "gif": "gif", "svg": "svg", "pdf": "pdf", "webm": "video", "mp4": "video",
            "md": "text"}
ASSET_EXT = set(EXT_KIND) | {"css", "js", "mjs", "json", "woff", "woff2", "ttf", "otf", "wav", "mp3", "ogg"}
MIME = {"html": "text/html", "htm": "text/html", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "webp": "image/webp", "avif": "image/avif", "gif": "image/gif", "svg": "image/svg+xml",
        "pdf": "application/pdf", "webm": "video/webm", "mp4": "video/mp4", "md": "text/markdown",
        "css": "text/css", "js": "text/javascript", "mjs": "text/javascript", "json": "application/json",
        "woff": "font/woff", "woff2": "font/woff2", "ttf": "font/ttf", "otf": "font/otf",
        "wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg"}
BLACKLIST = ("*.pem", "*.key", "*.p12", "*.pfx", "id_*", "*credential*", "*secret*", "*password*", "*token*",
             "*.kdbx", "*.sqlite", "*.db")
CLAUDE_URL = re.compile(r"^https://claude\.ai/(artifact|code/artifact)/([A-Za-z0-9-]{8,64})$")
PUBLISHED_RE = re.compile(r"Published (.+?) at (https://claude\.ai/\S+) \(Version (\d+)")
SCRATCH_RE = re.compile(r"^[^/]+/[^/]+/scratchpad(/|$)")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
CTRL = re.compile(r"[\x00-\x1f\x7f]")
ITEM_ID = re.compile(r"^[0-9a-f]{32}$")
EXP_RE = re.compile(r"^\d{9,12}$")
SIG_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
NO_TREE_EXT = frozenset({"md", "json"})
PENDING_ID = re.compile(rb'"tool_use_id"\s*:\s*"(toolu_[A-Za-z0-9_]+)"')
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SERVED_KINDS = ("html", "svg", "image", "gif", "pdf", "video")


def clip(value, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(CTRL.sub(" ", value).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def item_id(session_id: str, key: str, index: int) -> str:
    return hashlib.sha256(f"v1|{session_id}|{key}|{index}".encode()).hexdigest()[:32]


def parse_ts(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# ---------- tokens del visor ----------

def view_key(secret: bytes) -> bytes:
    return hmac.new(secret, b"biblioteca-visor-v1", hashlib.sha256).digest()


def _sig(key: bytes, ident: str, exp: int, epoch: int) -> str:
    digest = hmac.new(key, f"v1|{ident}|{exp}|{epoch}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:43]


def make_token(secret: bytes, ident: str, epoch: int, now: Optional[float] = None) -> tuple:
    exp = int((now if now is not None else time.time()) + TOKEN_TTL)
    return exp, _sig(view_key(secret), ident, exp, epoch)


def token_valid(secret: bytes, ident: str, exp: str, sig: str, epoch: int, now: Optional[float] = None) -> bool:
    if not (ITEM_ID.match(ident) and EXP_RE.match(exp) and SIG_RE.match(sig)):
        return False
    now = now if now is not None else time.time()
    if not (now < int(exp) <= now + TOKEN_TTL + 5):
        return False
    return hmac.compare_digest(sig, _sig(view_key(secret), ident, int(exp), epoch))


# ---------- diagramas ----------

_BLOQUE_OPEN = re.compile(r"(^|\n)[ \t]*(`{3,}|~{3,})[ \t]*(diagrama|%s)\b[^\n]*\n" % LEGACY_FENCE, re.I)


def _lenient(body: str):
    body = body.strip()
    try:
        return json.loads(body)
    except ValueError:
        pass
    fixed = re.sub(r",\s*([}\]])", r"\1", body.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'"))
    try:
        return json.loads(fixed)
    except ValueError:
        return None


def _tiene_pasos(data) -> bool:
    return isinstance(data, dict) and isinstance(data.get("pasos"), list) and bool(data["pasos"])


def _es_diagrama(data) -> bool:
    """Forma mínima según "tipo": pasos para secuencia/proceso; si no, al menos un nodo con id y nombre de texto.
    Los topes los recorta el front."""
    if not isinstance(data, dict):
        return False
    tipo = data.get("tipo", "estructura")
    if tipo in ("secuencia", "proceso"):
        return _tiene_pasos(data)
    if tipo != "estructura" or not isinstance(data.get("nodos"), list):
        return False
    nodos, conexiones = data["nodos"], data.get("conexiones", [])
    if not nodos or len(nodos) > MAX_DIAGRAMA_NODOS:
        return False
    if conexiones is not None and (not isinstance(conexiones, list) or len(conexiones) > MAX_DIAGRAMA_CONEXIONES):
        return False
    return any(isinstance(n, dict) and isinstance(n.get("id"), (str, int)) and str(n["id"]).strip()
               and isinstance(n.get("nombre", n.get("id")), (str, int)) for n in nodos)


_LEGACY = LEGACY_FENCE.encode()


def puede_tener_diagrama(text: str) -> bool:
    """Filtro barato antes de buscar bloques."""
    return "diagrama" in text or LEGACY_FENCE in text


def _fences(text: str, open_re) -> list:
    """(match de apertura, cuerpo) de cada bloque cercado por `open_re`, con el cierre de `lib/fence.ts`."""
    out = []
    pos = 0
    while True:
        m = open_re.search(text, pos)
        if not m:
            return out
        fence = m.group(2)
        body_start = m.end()
        close = re.compile(r"\n[ \t]*" + ("`" if fence[0] == "`" else "~") + "{%d,}[ \t]*(?=\n|$)" % len(fence))
        c = close.search(text, body_start - 1)
        out.append((m, text[body_start:c.start()] if c else text[body_start:]))
        pos = c.end() if c else len(text)


def extract_bloques(text: str) -> list:
    """(cuerpo, título) de cada bloque ```diagrama``` válido, en orden (misma apertura/cierre que `lib/fence.ts`)."""
    out = []
    for m, body in _fences(text, _BLOQUE_OPEN):
        if len(body.encode()) > MAX_DIAGRAMA_BYTES:
            continue
        data = _lenient(body)
        if m.group(3).lower() == LEGACY_FENCE:
            nuevo = diagrama_legado(data)
            if nuevo is not None and nuevo is not data:
                data, body = nuevo, json.dumps(nuevo, ensure_ascii=False)
        if _es_diagrama(data):
            out.append((body.strip(), clip(data.get("titulo") or data.get("title"), TITLE_CHARS)))
    return out


# ---------- pruebas ----------

_PRUEBAS_OPEN = re.compile(r"(^|\n)[ \t]*(`{3,}|~{3,})[ \t]*(pruebas)\b[^\n]*\n", re.I)


def puede_tener_pruebas(text: str) -> bool:
    return "pruebas" in text


def _pruebas_normalizadas(data) -> Optional[dict]:
    if not isinstance(data, dict):
        return None
    titulo = clip(data.get("titulo"), 100)
    casos = data.get("casos")
    if not titulo.strip() or not isinstance(casos, list):
        return None
    out = []
    for c in casos[:MAX_PRUEBAS_CASOS]:
        if not isinstance(c, dict):
            continue
        nombre = clip(c.get("nombre"), 120)
        res = c.get("resultado")
        res = res.strip().lower() if isinstance(res, str) else ""
        if not nombre.strip() or res not in PRUEBAS_RESULTADOS:
            continue
        caso = {"nombre": nombre, "resultado": res}
        detalle = clip(c.get("detalle"), 400)
        if detalle:
            caso["detalle"] = detalle
        ev = c.get("evidencia")
        ev = ev.strip() if isinstance(ev, str) else ev
        if isinstance(ev, str) and ((ev.startswith("/") and len(ev) <= 500) or EVIDENCIA_ID_RE.fullmatch(ev)):
            caso["evidencia"] = ev
        out.append(caso)
    if not out:
        return None
    res = {"titulo": titulo, "casos": out}
    resumen = clip(data.get("resumen"), 300)
    if resumen:
        res["resumen"] = resumen
    return res


def extract_pruebas(text: str) -> list:
    """(json normalizado, título, datos) de cada bloque ```pruebas``` válido, en orden."""
    out = []
    for _m, body in _fences(text, _PRUEBAS_OPEN):
        if len(body.encode()) > MAX_DIAGRAMA_BYTES:
            continue
        data = _pruebas_normalizadas(_lenient(body))
        if data is not None:
            out.append((json.dumps(data, ensure_ascii=False), data["titulo"], data))
    return out


def pruebas_conteo(data: dict) -> str:
    n = {r: 0 for r in PRUEBAS_RESULTADOS}
    for c in data["casos"]:
        n[c["resultado"]] += 1
    return " · ".join(f"{n[r]} {r}" for r in PRUEBAS_RESULTADOS if n[r])


# ---------- política de rutas ----------

class PathPolicy:
    def __init__(self, roots: list = (), scratch_base: Optional[Path] = None, home: Optional[Path] = None):
        self.uid = os.getuid()
        self.scratch_base = scratch_base
        self.home = home
        self.custom = [Path(r).expanduser() for r in roots]

    def _bases(self) -> list:
        if self.custom:
            return [self._real(r) for r in self.custom]
        out = []
        base = self.scratch_base if self.scratch_base is not None else Path(f"/tmp/claude-{os.getuid()}")
        try:
            st = os.stat(base)
            if statmod.S_ISDIR(st.st_mode) and st.st_uid == self.uid and (self.scratch_base is not None
                                                                         or statmod.S_IMODE(st.st_mode) == 0o700):
                out.append(self._real(base))
        except OSError:
            pass
        out.append(self._real(self.home if self.home is not None else Path.home()))
        return out

    @staticmethod
    def _real(p: Path) -> Path:
        return Path(os.path.realpath(p))

    def _scratch_root(self) -> Optional[Path]:
        base = self.scratch_base if self.scratch_base is not None else Path(f"/tmp/claude-{os.getuid()}")
        return self._real(base)

    def check(self, path) -> Optional[Path]:
        checked = self.check_id(path)
        return checked[0] if checked else None

    def check_id(self, path) -> Optional[tuple]:
        """BL2 puntos 1 a 3: raíz, componentes ocultos y lista negra. Devuelve (realpath, (dev, ino) o None)."""
        if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
            return None
        real = Path(os.path.realpath(path))
        for base in self._bases():
            try:
                rel = real.relative_to(base)
            except ValueError:
                continue
            parts = rel.parts
            if not parts or any(p.startswith(".") for p in parts):
                return None
            name = real.name.casefold()
            if any(_fn(name, pat) for pat in BLACKLIST):
                return None
            try:
                st = os.stat(real)
                return real, (st.st_dev, st.st_ino)
            except OSError:
                return real, None
        return None

    def scratchpad_of(self, real: Path) -> Optional[Path]:
        try:
            rel = real.relative_to(self._scratch_root())
        except ValueError:
            return None
        m = SCRATCH_RE.match(rel.as_posix())
        if not m:
            return None
        return self._scratch_root() / Path(*rel.parts[:3])


def _fn(name: str, pattern: str) -> bool:
    import fnmatch
    return fnmatch.fnmatchcase(name, pattern)


def decode_embedded_image(block: dict) -> Optional[tuple]:
    """(bytes, kind, ext, mime) de un bloque image embebido, o None si no aplica."""
    if not isinstance(block, dict) or block.get("type") != "image":
        return None
    src = block.get("source")
    if not isinstance(src, dict) or src.get("type") != "base64":
        return None
    media = src.get("media_type")
    if media not in CAPTURA_MEDIA:
        return None
    raw = src.get("data")
    if not isinstance(raw, str):
        return None
    try:
        data = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error):
        return None
    if not data or len(data) > CAPTURA_MAX:
        return None
    kind, ext = CAPTURA_MEDIA[media]
    if not uploads_mod._image_ok(ext, data[:16]):
        return None
    return data, kind, ext, media


def _pending_input(name: str, inp: dict) -> dict:
    # El estado se persiste: de las demás herramientas solo hace falta lo que usa la captura.
    if name in ("Artifact", "SendUserFile"):
        return inp
    if name == "Read" and isinstance(inp.get("file_path"), str):
        return {"file_path": inp["file_path"]}
    return {}


def captura_title(name: str, inp: dict) -> str:
    if CHROME_TOOL_RE.match(name or ""):
        return "Captura del navegador"
    if name == "Read":
        path = inp.get("file_path") if isinstance(inp.get("file_path"), str) else ""
        base = os.path.basename(path.replace("\\", "/"))
        return clip(base, TITLE_CHARS) if base else "Captura"
    return "Captura"


def captura_ids_for_block(session_id: str, block: dict) -> list:
    """Ids de biblioteca para las imágenes embebidas de un tool_result (sin persistir)."""
    out = []
    content = block.get("content")
    if not isinstance(content, list):
        return out
    for piece in content:
        if not isinstance(piece, dict):
            continue
        parsed = decode_embedded_image(piece)
        if parsed is None:
            continue
        data = parsed[0]
        sha = hashlib.sha256(data).hexdigest()
        out.append({"id": item_id(session_id, f"c:{sha}", 0)})
    return out


def magic_ok(path: Path, kind: str, ext: str) -> bool:
    try:
        with path.open("rb") as fh:
            head = fh.read(16)
            if kind in ("html", "svg", "text"):
                fh.seek(0)
                data = fh.read(MAX_BY_KIND[kind] + 1)
    except OSError:
        return False
    if kind in ("html", "svg", "text"):
        if len(data) > MAX_BY_KIND[kind] or b"\x00" in data:
            return False
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return "<svg" in text[:4096].lower() if kind == "svg" else True
    if kind == "pdf":
        return head.startswith(b"%PDF-")
    if kind == "video":
        return head.startswith(b"\x1a\x45\xdf\xa3") if ext == "webm" else head[4:8] == b"ftyp"
    if ext == "avif":
        return head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis")
    return uploads_mod._image_ok(ext, head)


def open_checked(real: Path, ident: Optional[tuple] = None) -> Optional[tuple]:
    """Abre sin seguir symlinks y compara el fd contra la identidad de check() (anti-TOCTOU). Devuelve (fd, stat)."""
    try:
        fd = os.open(real, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if ident is None:
            again = os.stat(real)
            ident = (again.st_dev, again.st_ino)
        if not statmod.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != tuple(ident):
            os.close(fd)
            return None
    except OSError:
        os.close(fd)
        return None
    return fd, st


@dataclass
class Served:
    fd: int
    size: int
    mime: str
    kind: str
    ext: str


REL_BAD = re.compile(r"[\\\x00-\x1f\x7f]")


def clean_rel(rel: str) -> Optional[list]:
    if not rel or len(rel) > 512 or REL_BAD.search(rel) or rel.startswith("/"):
        return None
    parts = rel.split("/")
    if len(parts) > 12 or any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        return None
    return parts


# ---------- índice ----------

class Library:
    PURGE_GC_INTERVAL = PURGE_GC_INTERVAL
    SAVE_DELAY = 3.0

    def __init__(self, cfg, data_directory: Path, secret: bytes = b"", epoch=lambda: 0,
                 scratch_base: Optional[Path] = None, home: Optional[Path] = None, clock=time.monotonic,
                 uploads_dir: Optional[Path] = None):
        self.cfg = cfg
        self.projects_dir = cfg.projects_dir()
        self.dir = data_directory
        self.path = data_directory / "biblioteca.json"
        self.copies = data_directory / "biblioteca"
        self.secret = secret
        self.epoch = epoch
        self.clock = clock
        self.policy = PathPolicy(cfg.biblioteca_roots, scratch_base, home)
        self.home = home
        self.uploads_dir = uploads_dir.resolve() if uploads_dir is not None else None
        self._lock = threading.RLock()
        self._index_lock = threading.Lock()
        self.items: dict = {}
        self.files: dict = {}
        self.sessions: dict = {}
        self.quitados: set = set()
        self.keymap: dict = {}
        self.by_tool: dict = {}
        self.indexando = False
        self.listeners: list = []
        self._stat: dict = {}
        self._last_scan = 0.0
        self._counters: dict = {}
        self._fresh: set = set()
        self._copy_bytes = 0
        self._copy_bytes_stale = True
        self._last_saved: Optional[str] = None
        self._save_timer: Optional[threading.Timer] = None
        self._save_guard = threading.Lock()
        self._last_purge_gc = 0.0
        self._capturas_backfill: dict = {"done": False, "files": {}, "v": CAPTURAS_BACKFILL_V}
        self.rutas_gen = 0
        self._load()
        self._migrate_copies()

    # --- persistencia ---
    def _load(self) -> None:
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._last_saved = raw
        except (OSError, ValueError):
            return
        self.items = data.get("items", {})
        self.files = data.get("files", {})
        self.sessions = data.get("sessions", {})
        raw = data.get("quitados", [])
        self.quitados = {q for q in raw if isinstance(q, str) and ITEM_ID.match(q)} if isinstance(raw, list) else set()
        for ident in [i for i in self.items if i in self.quitados]:
            del self.items[ident]
        for item in self.items.values():
            self._register(item)
        raw_bf = data.get("capturas_backfill")
        if isinstance(raw_bf, dict):
            if raw_bf.get("v") == CAPTURAS_BACKFILL_V:
                self._capturas_backfill = {"done": raw_bf.get("done") is True, "v": CAPTURAS_BACKFILL_V,
                                           "files": raw_bf.get("files") if isinstance(raw_bf.get("files"), dict) else {}}
        if migrar_items(self.items):
            self.save()

    def _migrate_copies(self) -> None:
        """Las copias por ítem (formato anterior) se descartan; las de contenido direccionado viven en blobs/."""
        if not self.copies.is_dir():
            return
        os.chmod(self.copies, 0o700)
        for d in self.copies.iterdir():
            if d.name != "blobs" and d.is_dir() and not d.is_symlink():
                shutil.rmtree(d, ignore_errors=True)
        for item in self.items.values():
            if item.get("copia") and not item.get("blobs"):
                item["copia"] = False

    def _register(self, item: dict) -> None:
        for k in item.get("keys", []):
            self.keymap[(item["session_id"], k)] = item["id"]
        ruta = item.get("ruta")
        if isinstance(ruta, str) and ruta:
            self.keymap[(item["session_id"], f"r:{ruta}")] = item["id"]
        shot = item.get("shot_id")
        if isinstance(shot, str) and shot:
            self.keymap.setdefault((item["session_id"], f"r:{shot}"), item["id"])
        if item.get("tool_use_id"):
            self.by_tool.setdefault(item["tool_use_id"], [])
            if item["id"] not in self.by_tool[item["tool_use_id"]]:
                self.by_tool[item["tool_use_id"]].append(item["id"])

    def save_later(self) -> None:
        with self._save_guard:
            if self._save_timer is not None:
                return
            timer = threading.Timer(self.SAVE_DELAY, self._timer_save)
            timer.daemon = True
            self._save_timer = timer
            timer.start()

    def _timer_save(self) -> None:
        with self._save_guard:
            self._save_timer = None
        try:
            with self._index_lock:
                self.save()
        except Exception:
            log.exception("no pude guardar biblioteca.json")

    def flush(self) -> None:
        with self._save_guard:
            timer, self._save_timer = self._save_timer, None
        if timer is not None:
            timer.cancel()
        with self._index_lock:
            self.save()

    def save(self) -> None:
        with self._lock:
            text = json.dumps({"v": 2, "files": self.files, "items": self.items, "sessions": self.sessions,
                               "quitados": sorted(self.quitados), "capturas_backfill": self._capturas_backfill},
                              ensure_ascii=False)
        if text == self._last_saved:
            return
        private_write(self.path, text)
        self._last_saved = text

    def _ensure_copy_bytes(self) -> None:
        if self._copy_bytes_stale:
            self._copy_bytes = self._blob_bytes()
            self._copy_bytes_stale = False

    def _mark_copy_bytes_dirty(self) -> None:
        self._copy_bytes_stale = True

    def _periodic_purge_gc(self) -> None:
        now = self.clock()
        if now - self._last_purge_gc < self.PURGE_GC_INTERVAL:
            return
        self._last_purge_gc = now
        self.purge()

    # --- descubrimiento ---
    def _discover(self) -> list:
        out = []
        if not self.projects_dir.is_dir():
            return out
        for p in self.projects_dir.glob("*/*.jsonl"):
            if SESSION_ID.match(p.stem):
                out.append((p, p.stem, False))
        for p in self.projects_dir.glob("*/*/subagents/agent-*.jsonl"):
            if SESSION_ID.match(p.parent.parent.name):
                out.append((p, p.parent.parent.name, True))
        return out

    def session_files(self, session_id: str) -> list:
        if not SESSION_ID.match(session_id):
            return []
        return [t for t in self._discover_for(session_id)]

    def _discover_for(self, session_id: str) -> list:
        out = []
        if not self.projects_dir.is_dir():
            return out
        for p in self.projects_dir.glob(f"*/{session_id}.jsonl"):
            out.append((p, session_id, False))
        for p in self.projects_dir.glob(f"*/{session_id}/subagents/agent-*.jsonl"):
            out.append((p, session_id, True))
        return out

    def index_all(self) -> list:
        self.indexando = True
        try:
            return self._index(self._discover())
        finally:
            self.indexando = False
            self._last_scan = self.clock()

    def index_sessions(self, session_ids) -> list:
        files = []
        for sid in session_ids:
            if isinstance(sid, str) and SESSION_ID.match(sid):
                files += self._discover_for(sid)
        files = [f for f in files if self._file_changed(f[0])]
        return self._index(files) if files else []

    def _file_changed(self, path: Path) -> bool:
        state = self.files.get(str(path))
        if not state:
            return True
        try:
            st = path.stat()
        except OSError:
            return False
        return not (state["inode"] == st.st_ino and state["size"] == st.st_size and state["mtime_ns"] == st.st_mtime_ns)

    def foto_disponible(self, ident: str) -> bool:
        with self._lock:
            item = self.items.get(ident)
            return item is not None and ident not in self.quitados and item.get("source") == "captura"

    def captura_id_for_ruta(self, session_id: str, ruta: str) -> Optional[str]:
        with self._lock:
            return self.keymap.get((session_id, f"r:{ruta}"))

    def captura_ruta_lookup(self, session_id: str):
        def lookup(ruta: str) -> Optional[str]:
            iid = self.captura_id_for_ruta(session_id, ruta)
            return iid if iid and self.foto_disponible(iid) else None
        return lookup

    def run_capturas_backfill(self) -> list:
        if self._capturas_backfill.get("done"):
            return []
        new_ids: list = []
        with self._index_lock:
            self._ensure_copy_bytes()
            files = self._discover()
            bf_files = self._capturas_backfill.setdefault("files", {})
            for path, sid, sub in files:
                key = str(path)
                state = self.files.get(key)
                stop = int(state["offset"]) if state and isinstance(state.get("offset"), int) else 0
                if stop <= 0:
                    bf_files[key] = stop
                    continue
                pos = int(bf_files.get(key, 0))
                if pos >= stop:
                    continue
                try:
                    new_ids += self._backfill_capturas_file(path, sid, sub, pos, stop, bf_files, key)
                except OSError as exc:
                    log.warning("backfill de capturas falló en %s: %s", path, exc)
            if self._capturas_backfill_complete(files):
                self._capturas_backfill["done"] = True
            self._periodic_purge_gc()
            self.save_later()
        if new_ids:
            for fn in list(self.listeners):
                try:
                    fn(new_ids)
                except Exception as exc:
                    log.warning("listener de la biblioteca falló: %s", exc)
        return new_ids

    def rescan_on_demand(self) -> bool:
        """Al abrir la Biblioteca: un rescan completo como mucho cada RESCAN_THROTTLE, sin esperar a otro índice."""
        if self.clock() - self._last_scan < RESCAN_THROTTLE or self._index_lock.locked():
            return False
        self._last_scan = self.clock()
        self._index(self._discover())
        return True

    def _index(self, files: list) -> list:
        new_ids: list = []
        with self._index_lock:
            self._ensure_copy_bytes()
            for path, sid, sub in files:
                try:
                    new_ids += self._process_file(path, sid, sub)
                except OSError as exc:
                    log.warning("no pude indexar %s: %s", path, exc)
                    continue
            self._periodic_purge_gc()
            self.save_later()
        if new_ids:
            for fn in list(self.listeners):
                try:
                    fn(new_ids)
                except Exception as exc:
                    log.warning("listener de la biblioteca falló: %s", exc)
        return new_ids

    def _process_file(self, path: Path, session_id: str, subagent: bool) -> list:
        st = path.stat()
        key = str(path)
        state = self.files.get(key)
        if state and (state["inode"] != st.st_ino or st.st_size < state["offset"]):
            state = None
        if state and state["size"] == st.st_size and state["mtime_ns"] == st.st_mtime_ns:
            return []
        state = state or {"inode": st.st_ino, "size": 0, "offset": 0, "mtime_ns": 0, "pending": {}, "cwd": ""}
        project = path.parents[2].name if subagent else path.parent.name
        with path.open("rb") as fh:
            fh.seek(state["offset"])
            data = fh.read(PASS_BYTES)
        full = len(data) >= PASS_BYTES
        head = 0
        if state.get("skipline"):
            nl = data.find(b"\n")
            head = len(data) if nl < 0 else nl + 1
            state["skipline"] = nl < 0
        lines: list = []
        consumed = len(data)
        if head < len(data):
            body = data[head:]
            end = body.rfind(b"\n") + 1
            if end == 0 and full:
                state["skipline"] = True
            else:
                lines = body[:end].split(b"\n")
                consumed = head + end
                tail = body[end:]
                if not full and tail.strip():
                    try:
                        json.loads(tail)
                        lines.append(tail)
                        consumed = len(data)
                    except ValueError:
                        pass
        ctx = {"session_id": session_id, "project": project, "subagent": subagent, "state": state, "new": []}
        for raw in lines:
            if raw.strip():
                self._line(raw, ctx)
        state.update(size=-1 if full else st.st_size, mtime_ns=st.st_mtime_ns, offset=state["offset"] + consumed)
        with self._lock:
            self.files[key] = state
        return ctx["new"]

    def _capturas_backfill_complete(self, files: list) -> bool:
        bf_files = self._capturas_backfill.get("files") or {}
        for path, _, _ in files:
            key = str(path)
            state = self.files.get(key)
            stop = int(state.get("offset", 0)) if state else 0
            if stop <= 0:
                continue
            if int(bf_files.get(key, 0)) < stop:
                return False
        return True

    def _backfill_capturas_file(self, path: Path, session_id: str, subagent: bool, start: int, stop: int,
                                bf_files: dict, key: str) -> list:
        project = path.parents[2].name if subagent else path.parent.name
        pos = start
        ctx = {"session_id": session_id, "project": project, "subagent": subagent, "state": {"pending": {}, "cwd": ""},
               "new": []}
        while pos < stop:
            chunk_end = min(pos + PASS_BYTES, stop)
            with path.open("rb") as fh:
                fh.seek(pos)
                data = fh.read(chunk_end - pos)
            if not data:
                break
            full = chunk_end < stop or chunk_end - pos >= PASS_BYTES
            lines, consumed = self._chunk_lines(data, full)
            for raw in lines:
                if raw.strip():
                    self._capturas_line(raw, ctx)
            if consumed <= 0:
                consumed = len(data)
            pos += consumed
            bf_files[key] = pos
        return ctx["new"]

    def _chunk_lines(self, data: bytes, full: bool) -> tuple:
        head = 0
        lines: list = []
        consumed = len(data)
        if not data:
            return lines, 0
        body = data
        end = body.rfind(b"\n") + 1
        if end == 0 and full:
            return lines, 0
        if end == 0:
            return lines, 0
        lines = body[:end].split(b"\n")
        consumed = end
        tail = body[end:]
        if not full and tail.strip():
            try:
                json.loads(tail)
                lines.append(tail)
                consumed = len(data)
            except ValueError:
                pass
        return lines, consumed

    def _capturas_line(self, raw: bytes, ctx: dict) -> None:
        pending = ctx["state"]["pending"]
        if b'"tool_use"' not in raw and b'"tool_result"' not in raw and b'"cwd"' not in raw \
                and not (bool(pending) and any(m.decode() in pending for m in PENDING_ID.findall(raw))):
            return
        try:
            obj = json.loads(raw)
        except ValueError:
            return
        if not isinstance(obj, dict):
            return
        if isinstance(obj.get("cwd"), str):
            ctx["state"]["cwd"] = obj["cwd"]
        kind = obj.get("type")
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        content = message.get("content")
        if not isinstance(content, list):
            return
        ts = obj.get("timestamp") if isinstance(obj.get("timestamp"), str) else ""
        if kind == "assistant":
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and isinstance(block.get("id"), str) \
                        and isinstance(block.get("input"), dict):
                    name = str(block.get("name") or "")
                    pending[block["id"]] = {"name": name, "input": _pending_input(name, block["input"]), "ts": ts}
                    while len(pending) > MAX_PENDING:
                        pending.pop(next(iter(pending)))
        elif kind == "user":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_id = block.get("tool_use_id")
                use = pending.pop(tool_id, None) if isinstance(tool_id, str) else None
                if block.get("is_error") is True:
                    continue
                self._capturas_from_result(ctx, tool_id if isinstance(tool_id, str) else "", use, block, ts)

    def _line(self, raw: bytes, ctx: dict) -> None:
        pending = ctx["state"]["pending"]
        interesting = (b'"Artifact"' in raw or b'"SendUserFile"' in raw or b"diagrama" in raw or b"pruebas" in raw or _LEGACY in raw
                       or b'"ai-title"' in raw or b'"type":"image"' in raw or b'"type": "image"' in raw
                       or b'"tool_use"' in raw or b'"type": "tool_use"' in raw
                       or (bool(pending) and any(m.decode() in pending for m in PENDING_ID.findall(raw))))
        if not interesting:
            return
        try:
            obj = json.loads(raw)
        except ValueError:
            return
        if not isinstance(obj, dict):
            return
        if isinstance(obj.get("cwd"), str):
            ctx["state"]["cwd"] = obj["cwd"]
        kind = obj.get("type")
        sid = ctx["session_id"]
        if kind == "ai-title" and not ctx["subagent"]:
            title = clip(obj.get("aiTitle"), TITLE_CHARS)
            if title:
                with self._lock:
                    self.sessions.setdefault(sid, {})["titulo"] = title
            return
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        content = message.get("content")
        if not isinstance(content, list):
            return
        ts = obj.get("timestamp") if isinstance(obj.get("timestamp"), str) else ""
        if kind == "assistant":
            index = 0
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and isinstance(block.get("id"), str) \
                        and isinstance(block.get("input"), dict):
                    name = str(block.get("name") or "")
                    pending[block["id"]] = {"name": name, "input": _pending_input(name, block["input"]), "ts": ts}
                    while len(pending) > MAX_PENDING:
                        pending.pop(next(iter(pending)))
                elif block.get("type") == "text" and isinstance(block.get("text"), str) \
                        and (puede_tener_diagrama(block["text"]) or puede_tener_pruebas(block["text"])):
                    mid = obj.get("uuid") or message.get("id") or ts
                    for body, title in extract_bloques(block["text"]) if puede_tener_diagrama(block["text"]) else []:
                        self._add_diagrama(ctx, str(mid), index, body, title, ts)
                        index += 1
                    for pindex, (raw_json, title, data) in enumerate(extract_pruebas(block["text"])
                                                                     if puede_tener_pruebas(block["text"]) else []):
                        self._add_pruebas(ctx, str(mid), 2000 + pindex, raw_json, title, data, ts)
        elif kind == "user":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_id = block.get("tool_use_id")
                use = pending.pop(tool_id, None) if isinstance(tool_id, str) else None
                if block.get("is_error") is True:
                    continue
                if use:
                    self._finalize(ctx, tool_id, use, block, obj, ts)
                self._capturas_from_result(ctx, tool_id if isinstance(tool_id, str) else "", use, block, ts)

    # --- construcción de ítems ---
    def _base(self, ctx: dict, kind: str, source: str, tool_use_id: str, ts: str) -> dict:
        return {"kind": kind, "source": source, "session_id": ctx["session_id"], "project": ctx["project"],
                "subagent": ctx["subagent"], "tool_use_id": tool_use_id, "ts": ts, "title": "", "description": "",
                "caption": "", "path": "", "exists": False, "size": 0, "mime": "", "url": "", "version": 0,
                "versions": [], "assets": {}, "diagrama_raw": None, "pruebas_raw": None, "reunion_raw": None, "allowed": True, "motivo": "", "copia": False,
                "keys": []}

    def _put(self, ctx: dict, item: dict, is_new: bool) -> None:
        with self._lock:
            if item["id"] in self.quitados:
                return
            self.items[item["id"]] = item
            self._register(item)
        if is_new:
            ctx["new"].append(item["id"])

    def _add_diagrama(self, ctx, mid: str, index: int, body: str, title: str, ts: str) -> None:
        iid = item_id(ctx["session_id"], mid, 1000 + index)
        if iid in self.items or iid in self.quitados:
            return
        item = self._base(ctx, "diagrama", "diagrama", mid, ts)
        item.update(id=iid, title=title or "Diagrama", diagrama_raw=body, size=len(body), exists=True, mime="application/json")
        self._put(ctx, item, True)

    def _add_pruebas(self, ctx, mid: str, offset: int, raw_json: str, title: str, data: dict, ts: str) -> None:
        iid = item_id(ctx["session_id"], mid, offset)
        if iid in self.items or iid in self.quitados:
            return
        evidencias = {}
        for caso in data["casos"]:
            ruta = caso.get("evidencia")
            cid = self._evidencia_captura(ctx, ruta, ts) if ruta and ruta not in evidencias else None
            if cid:
                evidencias[ruta] = cid
        item = self._base(ctx, "pruebas", "pruebas", mid, ts)
        item.update(id=iid, title=clip(title, TITLE_CHARS), pruebas_raw=raw_json, size=len(raw_json), exists=True,
                    mime="application/json", description=pruebas_conteo(data), evidencias=evidencias)
        self._put(ctx, item, True)

    def _evidencia_captura(self, ctx: dict, ruta: str, ts: str) -> Optional[str]:
        sid = ctx["session_id"]
        iid = self.captura_ruta_lookup(sid)(ruta)
        if iid or EVIDENCIA_ID_RE.fullmatch(ruta):
            return iid
        spec = PRUEBAS_IMG_EXT.get(ext_of(ruta))
        real = self.policy.check(ruta) if spec else None
        if real is None:
            return None
        kind, ext, mime = spec
        try:
            st = os.stat(real)
            if not statmod.S_ISREG(st.st_mode) or st.st_uid != self.policy.uid or st.st_size > CAPTURA_MAX \
                    or not magic_ok(real, kind, ext_of(ruta)):
                return None
            data = real.read_bytes()
        except OSError:
            return None
        self._add_captura(ctx, "", {"name": "", "input": {}}, data, kind, ext, mime, ts, ruta=ruta)
        cid = item_id(sid, f"c:{hashlib.sha256(data).hexdigest()}", 0)
        return cid if cid in self.items and cid not in self.quitados else None

    def _resolve_local(self, ctx: dict, value) -> str:
        if not isinstance(value, str) or not value:
            return ""
        if value.startswith("/"):
            return value
        return os.path.join(ctx["state"].get("cwd") or "", value) if ctx["state"].get("cwd") else ""

    def _finalize(self, ctx: dict, tool_id: str, use: dict, block: dict, obj: dict, ts: str) -> None:
        tur = obj.get("toolUseResult") if isinstance(obj.get("toolUseResult"), dict) else {}
        if use["name"] == "Artifact":
            self._finalize_artifact(ctx, tool_id, use, block, tur, ts or use["ts"])
        elif use["name"] == "SendUserFile":
            self._finalize_send(ctx, tool_id, use, tur, ts or use["ts"])

    def _path_in_uploads(self, ctx: dict, use: dict) -> bool:
        if use.get("name") != "Read" or self.uploads_dir is None:
            return False
        inp = use.get("input") if isinstance(use.get("input"), dict) else {}
        path = self._resolve_local(ctx, inp.get("file_path") if isinstance(inp.get("file_path"), str) else "")
        if not path:
            return False
        try:
            return Path(os.path.realpath(path)).is_relative_to(self.uploads_dir)
        except (ValueError, OSError):
            return False

    def _capturas_from_result(self, ctx: dict, tool_id: str, use: Optional[dict], block: dict, ts: str) -> None:
        use = use or {"name": "", "input": {}}
        if self._path_in_uploads(ctx, use):
            return
        content = block.get("content")
        if not isinstance(content, list):
            return
        shot = id_desde_tool_result(block)
        for piece in content:
            parsed = decode_embedded_image(piece)
            if parsed is None:
                continue
            data, kind, ext, mime = parsed
            self._add_captura(ctx, tool_id, use, data, kind, ext, mime, ts, block, shot_id=shot)
            shot = None

    def _add_captura(self, ctx: dict, tool_id: str, use: dict, data: bytes, kind: str, ext: str, mime: str, ts: str,
                     block: Optional[dict] = None, ruta: Optional[str] = None, shot_id: Optional[str] = None) -> None:
        sha = hashlib.sha256(data).hexdigest()
        key = f"c:{sha}"
        sid = ctx["session_id"]
        existing = self.keymap.get((sid, key))
        is_new = existing is None or existing not in self.items
        iid = existing if not is_new else item_id(sid, key, 0)
        if iid in self.quitados:
            return
        ruta = ruta or (ruta_desde_tool_result(block) if isinstance(block, dict) else None)
        if not is_new:
            with self._lock:
                self.items[iid]["ts"] = max(self.items[iid]["ts"], ts)
                if ruta and not self.items[iid].get("ruta"):
                    self.items[iid]["ruta"] = ruta
                    self.keymap[(sid, f"r:{ruta}")] = iid
                    self.rutas_gen += 1
                if shot_id and not self.items[iid].get("shot_id"):
                    self.items[iid]["shot_id"] = shot_id
                    self.keymap.setdefault((sid, f"r:{shot_id}"), iid)
                    self.rutas_gen += 1
            return
        item = self._base(ctx, kind, "captura", tool_id, ts)
        item["id"] = iid
        item["title"] = captura_title(use.get("name", ""), use.get("input") or {})
        item["mime"] = mime
        item["keys"] = [key]
        item["path"] = f"captura/{sha[:12]}.{ext}"
        if ruta:
            item["ruta"] = ruta
        if shot_id:
            item["shot_id"] = shot_id
        try:
            sha_stored, size = self._store_bytes(data, iid)
        except OSError:
            return
        item.update(copia=True, blobs={"main": sha_stored, "files": {}}, size=size, exists=True, allowed=True,
                    copied_at=time.time())
        self._put(ctx, item, True)
        if ruta or shot_id:
            with self._lock:
                if ruta:
                    self.keymap[(sid, f"r:{ruta}")] = iid
                if shot_id:
                    self.keymap.setdefault((sid, f"r:{shot_id}"), iid)
                self.rutas_gen += 1

    def _result_text(self, block: dict) -> str:
        c = block.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return "\n".join(b.get("text", "") for b in c if isinstance(b, dict))
        return ""

    def _finalize_artifact(self, ctx, tool_id, use, block, tur, ts) -> None:
        inp = use["input"]
        action = inp.get("action")
        if (action not in (None, "publish")) or inp.get("asset"):
            return
        file_path = inp.get("file_path") if isinstance(inp.get("file_path"), str) else ""
        files = inp.get("files") if isinstance(inp.get("files"), dict) else {}
        if not file_path and not inp.get("type_url") and not files and not inp.get("url"):
            return
        text = self._result_text(block)
        url = tur.get("url") if isinstance(tur.get("url"), str) else ""
        version = tur.get("version") if isinstance(tur.get("version"), int) else 0
        title = clip(tur.get("title"), TITLE_CHARS)
        m = PUBLISHED_RE.search(text)
        if m:
            url = url or m.group(2).rstrip(".,)")
            version = version or int(m.group(3))
        um = CLAUDE_URL.match(url)
        if not um:
            url = ""
        artifact_id = tur.get("artifact_id") if isinstance(tur.get("artifact_id"), str) else (um.group(2) if um else "")
        in_url = CLAUDE_URL.match(inp.get("url", "")) if isinstance(inp.get("url"), str) else None
        if in_url:
            artifact_id = artifact_id or in_url.group(2)
        local = self._resolve_local(ctx, file_path)
        assets: dict = {}
        root = inp.get("root") if isinstance(inp.get("root"), str) else ""
        for published, src in files.items():
            if not isinstance(published, str):
                continue
            source = src if isinstance(src, str) else src.get("from") if isinstance(src, dict) else None
            if not isinstance(source, str) or (isinstance(src, dict) and "artifact" in src):
                continue
            if not source.startswith("/"):
                base = root if root.startswith("/") else self._resolve_local(ctx, root) if root else ctx["state"].get("cwd", "")
                source = os.path.join(base, source) if base else ""
            if source:
                assets[published] = source
        if not local and "index.html" in assets:
            local = assets["index.html"]
        keys = []
        if artifact_id:
            keys.append(f"a:{artifact_id}")
        if local:
            keys.append(f"f:{local}")
        existing = next((self.keymap.get((ctx["session_id"], k)) for k in keys
                         if self.keymap.get((ctx["session_id"], k))), None)
        is_new = existing is None
        if is_new:
            iid = item_id(ctx["session_id"], artifact_id or tool_id, 0)
            item = self._base(ctx, "remoto", "artifact", tool_id, ts)
            item["id"] = iid
            if iid in self.quitados:
                return
            if iid in self.items and tool_id in (self.items[iid].get("tool_use_id"),):
                return
        else:
            item = self.items[existing]
            if any(v.get("tool_id") == tool_id for v in item["versions"]):
                self._fill_missing(item, url, artifact_id, title)
                return
        label = clip(inp.get("title") or inp.get("label"), TITLE_CHARS)
        item["title"] = title or label or item["title"]
        item["description"] = clip(inp.get("description"), TEXT_CHARS) or item["description"]
        item["url"] = url or item["url"]
        for k in keys:
            if k not in item["keys"]:
                item["keys"].append(k)
        if local:
            item["path"] = local
            item["assets"] = assets
        elif assets:
            item["assets"] = assets
        item["ts"] = max(item["ts"], ts)
        item["version"] = version or item["version"] + 1 if not is_new else (version or 1)
        item["versions"] = (item["versions"] + [{"version": item["version"], "ts": ts, "tool_id": tool_id}])[-MAX_VERSIONS:]
        item["tool_use_id"] = tool_id
        self._inspect(ctx, item, copy=True)
        self._put(ctx, item, is_new)

    def _fill_missing(self, item, url, artifact_id, title) -> None:
        with self._lock:
            if url and not item["url"]:
                item["url"] = url
            if title and not item["title"]:
                item["title"] = title

    def _finalize_send(self, ctx, tool_id, use, tur, ts) -> None:
        inp = use["input"]
        paths = []
        atts = tur.get("attachments")
        if isinstance(atts, list):
            for a in atts:
                if isinstance(a, dict) and isinstance(a.get("path"), str):
                    paths.append(a["path"])
        if not paths and isinstance(inp.get("files"), list):
            paths = [f for f in inp["files"] if isinstance(f, str)]
        caption = clip(inp.get("caption"), TEXT_CHARS)
        for index, p in enumerate(paths[:50]):
            iid = item_id(ctx["session_id"], tool_id, index)
            if iid in self.items or iid in self.quitados:
                continue
            item = self._base(ctx, "otro", "send_user_file", tool_id, ts)
            item.update(id=iid, path=self._resolve_local(ctx, p), caption=caption)
            self._inspect(ctx, item, copy=True)
            self._put(ctx, item, True)

    # --- inspección de archivos ---
    def _inspect(self, ctx, item: dict, copy: bool) -> None:
        path = item["path"]
        if not path:
            item.update(kind="remoto" if item["source"] == "artifact" else "otro", exists=False, allowed=True, motivo="")
            return
        ext = ext_of(path)
        kind = EXT_KIND.get(ext)
        item["mime"] = MIME.get(ext, "")
        if kind is None:
            item.update(kind="otro", allowed=False, motivo="Tipo no soportado")
            item["exists"] = os.path.exists(path)
            return
        item["kind"] = kind
        checked = self.policy.check_id(path)
        if checked is None:
            item.update(allowed=False, motivo="Ruta no permitida", exists=os.path.exists(path))
            return
        real, ident = checked
        try:
            st = os.stat(real)
        except OSError:
            item.update(exists=False, allowed=True, motivo="")
            return
        item["exists"] = True
        item["size"] = st.st_size
        ok, motivo = self._file_ok(real, st, kind, ext)
        item.update(allowed=ok, motivo=motivo)
        if not ok:
            return
        if kind == "html" and not item["title"]:
            item["title"] = self._html_title(real)
        if not item["title"]:
            item["title"] = clip(os.path.basename(path), TITLE_CHARS)
        if copy and self.cfg.biblioteca_copias:
            self._copy(item, real, ident)

    def _file_ok(self, real: Path, st, kind: str, ext: str) -> tuple:
        if not statmod.S_ISREG(st.st_mode) or st.st_uid != self.policy.uid:
            return False, "Ruta no permitida"
        if st.st_size > MAX_BY_KIND[kind]:
            return False, "Demasiado grande para verlo acá"
        if not magic_ok(real, kind, ext):
            return False, "El contenido no coincide con el tipo"
        return True, ""

    @staticmethod
    def _html_title(real: Path) -> str:
        try:
            with real.open("rb") as fh:
                head = fh.read(64 * 1024).decode("utf-8", "replace")
        except OSError:
            return ""
        m = TITLE_RE.search(head)
        return clip(htmllib.unescape(m.group(1)), TITLE_CHARS) if m else ""

    # --- copias locales (direccionadas por contenido: sha256 -> un blob; los ítems lo referencian) ---
    def _blob(self, sha: str) -> Path:
        return self.copies / "blobs" / sha

    def _ensure_dirs(self) -> None:
        for d in (self.copies, self.copies / "blobs"):
            d.mkdir(parents=True, exist_ok=True)
            os.chmod(d, 0o700)

    def _blob_bytes(self) -> int:
        total = 0
        try:
            with os.scandir(self.copies / "blobs") as it:
                for e in it:
                    if e.is_file(follow_symlinks=False):
                        total += e.stat(follow_symlinks=False).st_size
        except OSError:
            pass
        return total

    @staticmethod
    def _shas(item: dict) -> list:
        blobs = item.get("blobs") or {}
        return [blobs.get("main"), *(blobs.get("files") or {}).values()]

    @staticmethod
    def _drop_copy(item: dict) -> None:
        item["copia"] = False
        item.pop("blobs", None)

    def _gc(self) -> None:
        with self._lock:
            live = {sha for i in self.items.values() if i.get("copia") for sha in self._shas(i)} | self._fresh
        total = 0
        try:
            with os.scandir(self.copies / "blobs") as it:
                for e in it:
                    if not e.is_file(follow_symlinks=False):
                        continue
                    if e.name in live:
                        total += e.stat(follow_symlinks=False).st_size
                    else:
                        try:
                            os.unlink(e.path)
                        except OSError:
                            pass
        except OSError:
            pass
        self._copy_bytes = total
        self._copy_bytes_stale = False

    def _make_room(self, size: int, keep: str) -> bool:
        if size > COPY_TOTAL_CAP:
            return False
        if self._copy_bytes + size <= COPY_TOTAL_CAP:
            return True
        with self._lock:
            old = sorted((i for i in self.items.values() if i.get("copia") and i["id"] != keep),
                         key=lambda i: i.get("copied_at", 0))
        for victim in old:
            self._drop_copy(victim)
            self._gc()
            if self._copy_bytes + size <= COPY_TOTAL_CAP:
                return True
        return False

    def _store_bytes(self, data: bytes, keep: str) -> tuple:
        size = len(data)
        if size > CAPTURA_MAX or not self._make_room(size, keep):
            raise OSError("sin presupuesto de copias")
        self._ensure_dirs()
        digest = hashlib.sha256(data)
        sha = digest.hexdigest()
        dest = self._blob(sha)
        if dest.exists():
            return sha, size
        tmp = self._blob(f".tmp-{os.getpid()}-{threading.get_ident()}")
        try:
            with open(tmp, "wb") as fout:
                os.fchmod(fout.fileno(), 0o600)
                fout.write(data)
            os.replace(tmp, dest)
            self._copy_bytes += size
            self._copy_bytes_stale = False
        finally:
            if tmp.exists():
                tmp.unlink()
        self._fresh.add(sha)
        return sha, size

    def _store(self, src: Path, ident, allow: int, keep: str) -> tuple:
        opened = open_checked(src, ident)
        if opened is None:
            raise OSError("archivo no seguro")
        fd, st = opened
        with os.fdopen(fd, "rb") as fin:
            if st.st_size > allow or not self._make_room(st.st_size, keep):
                raise OSError("sin presupuesto de copias")
            self._ensure_dirs()
            tmp = self._blob(f".tmp-{os.getpid()}-{threading.get_ident()}")
            digest = hashlib.sha256()
            left = st.st_size
            try:
                with open(tmp, "wb") as fout:
                    os.fchmod(fout.fileno(), 0o600)
                    while left > 0:
                        chunk = fin.read(min(MB, left))
                        if not chunk:
                            break
                        digest.update(chunk)
                        fout.write(chunk)
                        left -= len(chunk)
                size = st.st_size - left
                sha = digest.hexdigest()
                dest = self._blob(sha)
                if dest.exists():
                    os.unlink(tmp)
                else:
                    os.replace(tmp, dest)
                    self._copy_bytes += size
                    self._copy_bytes_stale = False
            finally:
                if tmp.exists():
                    tmp.unlink()
        self._fresh.add(sha)
        return sha, size

    def _copy(self, item: dict, real: Path, ident) -> bool:
        self._fresh = set()
        try:
            main, total = self._store(real, ident, MAX_COPY_ITEM, item["id"])
            blobs = {"main": main, "files": {}}
            if item["kind"] == "html":
                self._copy_assets(item, real, blobs, MAX_COPY_ITEM - total, item["id"])
        except OSError as exc:
            log.warning("no pude copiar %s: %s", item["id"], exc)
            with self._lock:
                self._drop_copy(item)
            self._fresh = set()
            return False
        with self._lock:
            item.update(copia=True, blobs=blobs, copied_at=time.time())
        self._fresh = set()
        return True

    def _asset_ok(self, real: Path) -> bool:
        ext = ext_of(real.name)
        if ext not in ASSET_EXT or self.policy.scratchpad_of(real) is None:
            return False
        try:
            st = os.stat(real)
        except OSError:
            return False
        return statmod.S_ISREG(st.st_mode) and st.st_uid == self.policy.uid and st.st_size <= MAX_ASSET

    def _copy_assets(self, item: dict, main_real: Path, blobs: dict, budget: int, keep: str) -> None:
        files = blobs["files"]
        used = 0

        def add(key: str, real: Path, ident) -> None:
            nonlocal used
            if key in files or len(files) >= MAX_COPY_FILES:
                return
            try:
                sha, size = self._store(real, ident, budget - used, keep)
            except OSError:
                return
            files[key] = sha
            used += size

        for published, source in item["assets"].items():
            parts = clean_rel(published)
            checked = self.policy.check_id(source)
            if parts is None or checked is None or not self._asset_ok(checked[0]):
                continue
            add("assets/" + "/".join(parts), *checked)
        scratch = self.policy.scratchpad_of(main_real)
        if scratch is None:
            return
        base = main_real.parent
        seen = 0
        for dirpath, dirs, names in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            for name in names:
                seen += 1
                if seen > MAX_WALK or len(files) >= MAX_COPY_FILES:
                    return
                real = Path(dirpath, name)
                checked = self.policy.check_id(str(real))
                if name.startswith(".") or ext_of(name) in NO_TREE_EXT or real == main_real or checked is None \
                        or not self._asset_ok(checked[0]):
                    continue
                add("tree/" + "/".join(real.relative_to(base).parts), *checked)

    def quitar(self, ids) -> int:
        """Saca ítems del índice y libera sus copias propias; nunca toca los archivos originales."""
        wanted = {i for i in ids if isinstance(i, str) and ITEM_ID.match(i)}
        with self._index_lock:
            with self._lock:
                self.quitados |= wanted
                gone = [i for i in wanted if i in self.items]
                for ident in gone:
                    del self.items[ident]
                for key in [k for k, v in self.keymap.items() if v in wanted]:
                    del self.keymap[key]
                for tool, lst in list(self.by_tool.items()):
                    kept = [i for i in lst if i not in wanted]
                    if kept:
                        self.by_tool[tool] = kept
                    else:
                        del self.by_tool[tool]
            self._gc()
            self.save()
        return len(gone)

    @staticmethod
    def _reunion_raw(datos: dict) -> str:
        def textos(v):
            return [clip(x, REUNION_ITEM_CHARS) for x in (v if isinstance(v, list) else []) if isinstance(x, str)][:8]

        def tocada(t):
            if not isinstance(t, dict):
                return None
            return {k: (clip(v, REUNION_ITEM_CHARS) if isinstance(v, str) else v) for k, v in t.items()
                    if k in ("texto", "tipo", "respuesta", "archivos")}

        out = dict(datos)
        out["titulo"] = clip(datos.get("titulo"), REUNION_TITULO_CHARS)
        out["resumen"] = textos(datos.get("resumen"))
        out["pendientes"] = textos(datos.get("pendientes"))
        out["tema"] = clip(datos.get("tema") if isinstance(datos.get("tema"), str) else "", REUNION_TEMA_CHARS)
        out["repos"] = [clip(x, REUNION_TITULO_CHARS) for x in (datos.get("repos") or []) if isinstance(x, str)][:20]
        tocadas = [t for t in map(tocada, datos.get("tocadas") or []) if t is not None]
        for t in tocadas:
            if isinstance(t.get("archivos"), list):
                t["archivos"] = [clip(a, REUNION_ITEM_CHARS) for a in t["archivos"] if isinstance(a, str)][:20]
        while True:
            out["tocadas"] = tocadas
            raw = json.dumps(out, ensure_ascii=False)
            if len(raw.encode()) <= MAX_REUNION_RAW_BYTES or not tocadas:
                break
            tocadas = tocadas[1:]
        if len(raw.encode()) > MAX_REUNION_RAW_BYTES:
            raw = json.dumps({k: out[k] for k in ("v", "reunion", "inicio", "fin", "titulo") if k in out},
                             ensure_ascii=False)
        return raw

    def agregar_reunion(self, datos: dict, charla: str) -> str:
        rid = str(datos.get("reunion") or "")
        if not rid:
            raise ValueError("la reunión no trae id")
        ident = item_id(f"reunion-{rid}", rid, 0)
        fin = datos.get("fin") if isinstance(datos.get("fin"), (int, float)) else time.time()
        inicio = datos.get("inicio") if isinstance(datos.get("inicio"), (int, float)) else fin
        resumen = [p for p in (datos.get("resumen") or []) if isinstance(p, str)]
        raw = self._reunion_raw(datos)
        stamp = datetime.fromtimestamp(inicio).strftime("%d/%m %H:%M")
        item = {"kind": "reunion", "source": "reunion", "session_id": f"reunion-{rid}", "project": "Reunión",
                "subagent": False, "tool_use_id": "", "ts": datetime.fromtimestamp(fin, timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "title": clip(f"Reunión {stamp} · {datos.get('titulo') or ''}".rstrip(" ·"), TITLE_CHARS),
                "description": clip(resumen[0] if resumen else "", TEXT_CHARS), "caption": "", "path": "",
                "exists": True, "size": len(raw.encode()), "mime": "text/plain", "url": "", "version": 0, "versions": [],
                "assets": {}, "diagrama_raw": None, "pruebas_raw": None, "reunion_raw": raw, "allowed": True,
                "motivo": "", "copia": False, "keys": [], "id": ident}
        with self._index_lock:
            self._fresh = set()
            try:
                sha, _ = self._store_bytes(charla.encode(), ident)
                item.update(copia=True, blobs={"main": sha, "files": {}}, copied_at=time.time())
            except OSError as exc:
                log.warning("no pude guardar la charla de la reunión %s: %s", rid, exc)
            with self._lock:
                self.quitados.discard(ident)
                self.items[ident] = item
                self._register(item)
            self._fresh = set()
            self.save()
        for fn in list(self.listeners):
            try:
                fn([ident])
            except Exception as exc:
                log.warning("listener de la biblioteca falló: %s", exc)
        return ident

    def charla_de(self, ident: str) -> Optional[str]:
        item = self.items.get(ident)
        if not item or item.get("kind") != "reunion":
            return None
        path = self._blob_file(item)
        if path is None:
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def purge(self) -> None:
        cutoff = time.time() - COPY_DAYS * 86400
        with self._lock:
            for item in self.items.values():
                if item.get("copia") and item.get("copied_at", 0) < cutoff:
                    self._drop_copy(item)
        self._gc()

    # --- consultas ---
    def _stat_of(self, path: str) -> tuple:
        now = self.clock()
        hit = self._stat.get(path)
        if hit and now - hit[0] < STAT_TTL:
            return hit[1], hit[2]
        try:
            st = os.stat(path)
            res = (True, st.st_size)
        except OSError:
            res = (False, 0)
        self._stat[path] = (now, *res)
        if len(self._stat) > 5000:
            self._stat.clear()
        return res

    def view_of(self, item: dict, with_src: bool = True) -> dict:
        exists, size = (self._stat_of(item["path"]) if item["path"] else (item["kind"] in ("diagrama", "pruebas", "reunion"), item["size"]))
        copia = bool(item.get("copia")) and self._blob_file(item) is not None
        kind = item["kind"]
        servible = (kind in SERVED_KINDS or kind == "text") and item["allowed"] and (exists or copia)
        if exists:
            size = size or item["size"]
        else:
            size = item["size"]
        motivo = item["motivo"]
        if not motivo and kind in SERVED_KINDS + ("text",) and not (exists or copia):
            motivo = "Ya no está en disco"
        if kind in MAX_BY_KIND and size > MAX_BY_KIND[kind]:
            servible, motivo = False, "Demasiado grande para verlo acá"
        path = item["path"]
        nombre = os.path.basename(path)
        donde = ""
        if path:
            home = str(self.home if self.home is not None else Path.home())
            donde = "scratchpad" if self.policy.scratchpad_of(Path(path)) is not None or "/scratchpad/" in path \
                else ("~/" + os.path.relpath(path, home) if path.startswith(home + "/") else "")
        sess = self.sessions.get(item["session_id"], {})
        out = {"id": item["id"], "kind": kind, "source": item["source"], "session_id": item["session_id"],
               "session_titulo": sess.get("titulo") or item["session_id"][:8], "project": item["project"],
               "subagent": item["subagent"], "ts": item["ts"], "title": item["title"],
               "description": item["description"], "caption": item["caption"], "nombre": nombre, "donde": donde,
               "exists": exists, "copia": copia, "servible": servible, "motivo": motivo, "size": size,
               "mime": item["mime"], "url": item["url"], "version": item["version"],
               "versions": [{"version": v["version"], "ts": v["ts"]} for v in item["versions"]],
               "diagrama_raw": item.get("diagrama_raw"), "pruebas_raw": item.get("pruebas_raw"),
               "reunion_raw": item.get("reunion_raw"), "tiene_charla": kind == "reunion" and copia,
               "evidencias": dict(item.get("evidencias") or {}), "src": ""}
        if with_src and servible and kind in SERVED_KINDS:
            out["src"] = self.src_for(item["id"])
        return out

    def _blob_file(self, item: dict, key: Optional[str] = None) -> Optional[Path]:
        blobs = item.get("blobs") or {}
        sha = blobs.get("main") if key is None else (blobs.get("files") or {}).get(key)
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            return None
        path = self._blob(sha)
        return path if path.is_file() and not path.is_symlink() else None

    def src_for(self, ident: str) -> str:
        origin = self.cfg.viewer_origin
        if not origin or not self.secret:
            return ""
        exp, sig = make_token(self.secret, ident, self.epoch())
        return f"{origin}/v/{ident}/{exp}/{sig}/"

    def _match(self, item: dict, tipos, session, desde, hasta, q: str) -> bool:
        if tipos and item["kind"] not in tipos:
            return False
        if session and item["session_id"] != session:
            return False
        day = item["ts"][:10]
        if desde and day < desde:
            return False
        if hasta and day > hasta:
            return False
        if q:
            sess = self.sessions.get(item["session_id"], {}).get("titulo", "")
            hay = fold(" ".join([item["title"], item["description"], item["caption"],
                                 os.path.basename(item["path"]), sess]))
            if q not in hay:
                return False
        return True

    def filtered(self, tipo: str = "", session: str = "", desde: str = "", hasta: str = "", q: str = "") -> list:
        tipos = {t for t in tipo.split(",") if t in KINDS} if tipo else set()
        needle = fold(q.strip())[:100]
        with self._lock:
            rows = [i for i in self.items.values() if self._match(i, tipos, session, desde, hasta, needle)]
        rows.sort(key=lambda i: (i["ts"], i["id"]), reverse=True)
        return rows

    def listing(self, cursor: Optional[str] = None, limit: int = 60, **filters) -> dict:
        rows = self.filtered(**filters)
        total = len(rows)
        if cursor:
            after = _decode_cursor(cursor)
            if after:
                rows = [r for r in rows if (r["ts"], r["id"]) < after]
        limit = min(max(limit, 1), 200)
        page = rows[:limit]
        nxt = _encode_cursor(page[-1]) if len(rows) > limit and page else None
        return {"items": [self.view_of(i) for i in page], "cursor": nxt, "indexando": self.indexando, "total": total}

    def detail(self, ident: str, **filters) -> Optional[dict]:
        if not ITEM_ID.match(ident):
            return None
        item = self.items.get(ident)
        if item is None:
            return None
        rows = self.filtered(**filters)
        ids = [r["id"] for r in rows]
        pos = ids.index(ident) if ident in ids else -1
        vecinos = {"anterior": ids[pos - 1] if pos > 0 else None,
                   "siguiente": ids[pos + 1] if 0 <= pos < len(ids) - 1 else None}
        return {**self.view_of(item), "vecinos": vecinos}

    def session_list(self) -> list:
        acc: dict = {}
        with self._lock:
            for i in self.items.values():
                a = acc.setdefault(i["session_id"], {"n": 0, "ultimo_ts": "", "proyecto": i["project"]})
                a["n"] += 1
                a["ultimo_ts"] = max(a["ultimo_ts"], i["ts"])
        out = [{"session_id": sid, "titulo": self.sessions.get(sid, {}).get("titulo") or sid[:8],
                "proyecto": a["proyecto"], "n": a["n"], "ultimo_ts": a["ultimo_ts"]} for sid, a in acc.items()]
        return sorted(out, key=lambda s: s["ultimo_ts"], reverse=True)

    def text_of(self, ident: str) -> Optional[str]:
        item = self.items.get(ident) if ITEM_ID.match(ident or "") else None
        if item is None or item["kind"] != "text" or not item["allowed"]:
            return None
        served = self._open_item(item, ("text",))
        if served is None:
            return None
        with os.fdopen(served.fd, "rb") as fh:
            data = fh.read(MAX_BY_KIND["text"] + 1)
        if len(data) > MAX_BY_KIND["text"]:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    # --- transcript ---
    def lib_ids_for_tool(self, tool_use_id: str) -> list:
        return [i for i in self.by_tool.get(tool_use_id, []) if i in self.items]

    def lib_ids_for_diagramas(self, session_id: str, message_id: str, start: int, count: int) -> list:
        ids = [item_id(session_id, message_id, 1000 + start + n) for n in range(count)]
        return [i for i in ids if i in self.items]

    # --- servir ---
    def open_main(self, item: dict) -> Optional[Served]:
        return self._open_item(item, SERVED_KINDS)

    def _open_item(self, item: dict, kinds: tuple) -> Optional[Served]:
        kind = item["kind"]
        if not item["allowed"] or kind not in kinds:
            return None
        ext = ext_of(item["path"])
        limit = MAX_BY_KIND[kind]
        checked = self.policy.check_id(item["path"]) if item["path"] else None
        if checked is not None:
            real, ident = checked
            opened = open_checked(real, ident)
            if opened is not None:
                fd, st = opened
                if st.st_uid == self.policy.uid and st.st_size <= limit and self._fd_magic(fd, kind, ext, st.st_size):
                    return Served(fd, st.st_size, MIME.get(ext, "application/octet-stream"), kind, ext)
                os.close(fd)
        cpath = self._blob_file(item) if item.get("copia") else None
        if cpath is not None:
            opened = open_checked(cpath)
            if opened is not None:
                fd, st = opened
                if st.st_size <= limit and self._fd_magic(fd, kind, ext, st.st_size):
                    return Served(fd, st.st_size, MIME.get(ext, "application/octet-stream"), kind, ext)
                os.close(fd)
        return None

    @staticmethod
    def _fd_magic(fd: int, kind: str, ext: str, size: int) -> bool:
        return magic_ok(Path(f"/proc/self/fd/{fd}"), kind, ext) if os.path.isdir("/proc/self/fd") else True

    def open_asset(self, item: dict, rel: str) -> Optional[Served]:
        parts = clean_rel(rel)
        if parts is None or item["kind"] != "html":
            return None
        ext = ext_of(parts[-1])
        if ext not in ASSET_EXT:
            return None
        declared = item["assets"].get(rel)
        main = item["path"]
        if declared is None and ext in NO_TREE_EXT:
            return None
        if declared is None and not (main and self.policy.scratchpad_of(Path(os.path.realpath(main))) is not None):
            return None
        checked = None
        if declared is not None:
            checked = self.policy.check_id(declared)
            copy_key = "assets/" + "/".join(parts)
        else:
            base = Path(os.path.realpath(os.path.dirname(main)))
            cand = Path(os.path.realpath(base.joinpath(*parts)))
            if base in cand.parents:
                checked = self.policy.check_id(str(cand))
            copy_key = "tree/" + "/".join(parts)
        mime, kind = MIME[ext], EXT_KIND.get(ext)
        if checked is not None and self._asset_ok(checked[0]):
            opened = open_checked(*checked)
            if opened is not None:
                fd, st = opened
                if kind and kind != "text" and not self._fd_magic(fd, kind, ext, st.st_size):
                    os.close(fd)
                else:
                    return Served(fd, st.st_size, mime, kind or "asset", ext)
        cpath = self._blob_file(item, copy_key) if item.get("copia") else None
        if cpath is not None:
            opened = open_checked(cpath)
            if opened is not None:
                return Served(opened[0], opened[1].st_size, mime, kind or "asset", ext)
        return None

    def count_asset(self, ident: str, exp: str, sig: str) -> bool:
        now = time.time()
        if len(self._counters) > 2000:
            self._counters = {k: v for k, v in self._counters.items() if int(k[1]) > now}
        key = (ident, exp, sig)
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key] <= MAX_ASSETS_PER_TOKEN

    # --- app hooks ---
    def on_board(self, previous: Optional[dict], board: dict) -> list:
        from .board import session_activity
        before = session_activity(previous) if previous else {}
        now = session_activity(board)
        return [sid for sid, mtime in now.items() if before.get(sid) != mtime]


def _encode_cursor(item: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps([item["ts"], item["id"]]).encode()).decode()


def _decode_cursor(value: str) -> Optional[tuple]:
    try:
        ts, ident = json.loads(base64.urlsafe_b64decode(value.encode()))
        return (str(ts), str(ident))
    except (ValueError, TypeError):
        return None
