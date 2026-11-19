import asyncio
import os
import re
import secrets
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional

from python_multipart.multipart import MultipartParser, parse_options_header

from .traspaso import TraspasoError

MAX_UPLOAD = 20 * 1024 * 1024
MAX_BODY_OVERHEAD = 64 * 1024
RETENTION_DAYS = 30
UPLOAD_ID_RE = re.compile(r"^\d{8}-\d{6}-[a-z0-9-]{1,70}\.[a-z0-9]{2,4}$")
IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif", "heic"}
TEXT_EXT = {"txt", "md", "log", "json", "csv", "yaml", "yml"}
HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
               "gif": "image/gif", "heic": "image/heic", "pdf": "application/pdf"}
SLUG_MAX = 60


def kind_of(ext: str) -> Optional[str]:
    if ext in IMAGE_EXT:
        return "image"
    if ext == "pdf":
        return "pdf"
    return "text" if ext in TEXT_EXT else None


def _image_ok(ext: str, head: bytes) -> bool:
    if ext == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in ("jpg", "jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == "gif":
        return head[:6] in (b"GIF87a", b"GIF89a")
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return head[4:8] == b"ftyp" and head[8:12] in HEIC_BRANDS


def content_ok(path: Path, ext: str) -> bool:
    kind = kind_of(ext)
    if kind == "text":
        with path.open("rb") as fh:
            data = fh.read()
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return b"\x00" not in data
    with path.open("rb") as fh:
        head = fh.read(16)
    return head.startswith(b"%PDF-") if kind == "pdf" else _image_ok(ext, head)


def clean_name(raw: str) -> str:
    name = unicodedata.normalize("NFC", raw.replace("\\", "/").rsplit("/", 1)[-1])
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", name).strip()[:120]


def make_id(name: str, now: Optional[datetime] = None) -> str:
    stem, _, ext = name.rpartition(".")
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_stem.lower()).strip("-")[:SLUG_MAX].strip("-") or "archivo"
    return f"{(now or datetime.now()).strftime('%Y%m%d-%H%M%S')}-{slug}.{ext.lower()}"


def upload_path(base: Path, ident: str) -> Optional[Path]:
    if not UPLOAD_ID_RE.match(ident):
        return None
    root = base.resolve()
    if (root / ident).is_symlink():
        return None
    path = (root / ident).resolve()
    return path if path.parent == root and path.is_file() else None


def resolve_adjuntos(base: Optional[Path], idents) -> list:
    paths = []
    for ident in idents:
        path = upload_path(base, ident) if base is not None and isinstance(ident, str) else None
        if path is None or path.stat().st_size > MAX_UPLOAD:
            raise TraspasoError(400, f"adjunto inexistente: {str(ident)[:80]}")
        paths.append(path)
    return paths


def con_adjuntos(text: str, paths: list) -> str:
    if not paths:
        return text
    if not text.strip():
        return "Te paso " + ", ".join(str(p) for p in paths)
    return text + "".join(f" (Adjunto: {p})" for p in paths)


def media_type(ident: str) -> str:
    return MEDIA_TYPES.get(ident.rsplit(".", 1)[-1], "text/plain; charset=utf-8")


def cleanup(base: Path, days: int = RETENTION_DAYS) -> None:
    if not base.is_dir():
        return
    limit = time.time() - days * 86400
    for entry in base.iterdir():
        try:
            if entry.is_file() and not entry.is_symlink() and entry.stat().st_mtime < limit:
                entry.unlink()
        except OSError:
            continue


class _Part:
    def __init__(self, base: Path, limit: Optional[int] = None, label: str = "el archivo supera los 20 MB"):
        self.base = base
        self.limit = limit
        self.label = label
        self.ctype = ""
        self.tmp: Optional[Path] = None
        self.fh = None
        self.size = 0
        self.name = ""
        self.files = 0
        self._field = b""
        self._value = b""
        self._headers: dict = {}
        self._current = ""

    def begin(self):
        self._headers = {}

    def header_field(self, data, start, end):
        self._field += data[start:end]

    def header_value(self, data, start, end):
        self._value += data[start:end]

    def header_end(self):
        self._headers[self._field.lower()] = self._value
        self._field = b""
        self._value = b""

    def headers_done(self):
        _, params = parse_options_header(self._headers.get(b"content-disposition", b""))
        filename = params.get(b"filename")
        if filename is None:
            self._current = ""
            return
        self.files += 1
        if self.files > 1:
            raise TraspasoError(400, "un archivo por pedido")
        self.name = clean_name(filename.decode("utf-8", "replace"))
        self.ctype = self._headers.get(b"content-type", b"").decode("latin-1").split(";")[0].strip().lower()
        self.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.base, 0o700)
        self.tmp = self.base / f".tmp-{secrets.token_hex(8)}"
        self.fh = os.fdopen(os.open(self.tmp, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600), "wb")
        self._current = "file"

    def data(self, data, start, end):
        if self._current != "file":
            return
        self.size += end - start
        if self.size > (self.limit if self.limit is not None else MAX_UPLOAD):
            raise TraspasoError(413, self.label)
        self.fh.write(data[start:end])

    def end(self):
        if self.fh:
            self.fh.close()
            self.fh = None

    def discard(self):
        if self.fh:
            self.fh.close()
        if self.tmp:
            self.tmp.unlink(missing_ok=True)


async def read_multipart(stream, content_type: str, part: _Part, max_total: int) -> None:
    kind_header, params = parse_options_header(content_type.encode("latin-1", "ignore"))
    boundary = params.get(b"boundary")
    if kind_header != b"multipart/form-data" or not boundary:
        raise TraspasoError(400, "se esperaba multipart/form-data")
    parser = MultipartParser(boundary, {
        "on_part_begin": part.begin, "on_header_field": part.header_field, "on_header_value": part.header_value,
        "on_header_end": part.header_end, "on_headers_finished": part.headers_done, "on_part_data": part.data,
        "on_part_end": part.end,
    })
    total = 0
    async for chunk in stream:
        total += len(chunk)
        if total > max_total:
            raise TraspasoError(413, part.label)
        parser.write(chunk)
    parser.finalize()


async def save_upload(stream, content_type: str, base: Path) -> dict:
    part = _Part(base)
    try:
        await read_multipart(stream, content_type, part, MAX_UPLOAD + MAX_BODY_OVERHEAD)
        if part.tmp is None or not part.name:
            raise TraspasoError(400, "falta el archivo")
        ext = part.name.rpartition(".")[2].lower() if "." in part.name else ""
        kind = kind_of(ext)
        if kind is None or part.size == 0:
            raise TraspasoError(415, "tipo de archivo no permitido")
        if not await asyncio.to_thread(content_ok, part.tmp, ext):
            raise TraspasoError(415, "el contenido no coincide con el tipo del archivo")
        ident = make_id(part.name)
        final = base / ident
        while final.exists():
            ident = make_id(part.name).replace(f".{ext}", f"-{secrets.token_hex(2)}.{ext}")
            final = base / ident
        os.replace(part.tmp, final)
        return {"id": ident, "name": part.name, "size": part.size, "kind": kind}
    except TraspasoError:
        part.discard()
        raise
    except Exception:
        part.discard()
        raise TraspasoError(400, "pedido multipart inválido")
