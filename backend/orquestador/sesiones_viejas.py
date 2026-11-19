"""Listar y retomar sesiones Claude cerradas (transcripts locales)."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from .digest import SESSION_ID, _user_text, is_system_text, queued_prompt
from .enchufe import NoDisponible, TerminalesError
from .enchufe.modelo import Lanzamiento
from .memoria_indice import DIR_EXCLUIDO
from .nueva_terminal import (
    NUEVA_LIMIT,
    agente_unico,
    enumerar_carpetas,
    grupos_desde_tablero,
    normalizar_nombre,
    slug_agente,
    validar_carpeta,
)
from .nueva_terminal import _display_path
from .traspaso import CONTROL_RE, TraspasoError

DIAS = 30
MAX_RESULTADOS = 200
MAX_TITULO = 120
MAX_FRASE = 200
HEAD_BYTES = 96 * 1024
TAIL_BYTES = 96 * 1024
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _una_linea(text: str, limite: int) -> str:
    t = CONTROL_RE.sub(" ", " ".join((text or "").split())).strip()
    if len(t) <= limite:
        return t
    return t[: limite - 1] + "…"


def _ts_iso(stamp: str, mtime: float) -> str:
    if isinstance(stamp, str) and stamp.strip():
        return stamp
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _titulo_de(obj: dict, primer_usuario: str) -> Optional[str]:
    kind = obj.get("type")
    if kind == "summary" and isinstance(obj.get("summary"), str) and obj["summary"].strip():
        return obj["summary"].strip()
    if kind in ("custom-title", "ai-title"):
        for key in ("customTitle", "aiTitle", "title"):
            if isinstance(obj.get(key), str) and obj[key].strip():
                return obj[key].strip()
    if kind == "user" and not primer_usuario:
        if obj.get("isMeta") or obj.get("isCompactSummary"):
            return None
        text = _user_text((obj.get("message") or {}).get("content"))
        if text.strip() and not is_system_text(obj, text):
            return text.strip()
    return None


def _frase_de(obj: dict) -> Optional[tuple[str, str]]:
    """(rol, texto, ts) simplificado a (ts, texto)."""
    ts = obj.get("timestamp") if isinstance(obj.get("timestamp"), str) else ""
    kind = obj.get("type")
    if kind == "attachment":
        text = queued_prompt(obj)
        if text.strip():
            return ts, text
        return None
    if kind == "user":
        if obj.get("isMeta") or obj.get("isCompactSummary"):
            return None
        text = _user_text((obj.get("message") or {}).get("content"))
        if text.strip() and not is_system_text(obj, text):
            return ts, text
        return None
    if kind == "assistant":
        content = (obj.get("message") or {}).get("content")
        if not isinstance(content, list):
            return None
        text = "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
        if text.strip():
            return ts, text
    return None


@dataclass
class _Meta:
    titulo: str = ""
    cwd: str = ""
    ultimo_ts: str = ""
    ultima_frase: str = ""


class _Lector:
    def __init__(self):
        self._cache: dict = {}
        self._lock = threading.Lock()

    def leer(self, path: Path) -> Optional[_Meta]:
        try:
            st = path.stat()
        except OSError:
            return None
        key = (str(path), st.st_mtime_ns, st.st_size)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        meta = self._parse(path, st.st_mtime, st.st_size)
        if meta is None:
            return None
        with self._lock:
            self._cache[key] = meta
            while len(self._cache) > 400:
                self._cache.pop(next(iter(self._cache)))
        return meta

    def _parse(self, path: Path, mtime: float, size: int) -> Optional[_Meta]:
        titulo = ""
        cwd = ""
        ultimo_ts = ""
        ultima_frase = ""
        head_left = HEAD_BYTES
        try:
            with path.open("rb") as fh:
                while head_left > 0:
                    raw = fh.readline()
                    if not raw:
                        break
                    head_left -= len(raw)
                    if not raw.endswith(b"\n"):
                        break
                    try:
                        obj = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if isinstance(obj.get("cwd"), str) and obj["cwd"] and not cwd:
                        cwd = obj["cwd"]
                    t = _titulo_de(obj, titulo)
                    if t and not titulo:
                        titulo = t
                    fr = _frase_de(obj)
                    if fr:
                        ultimo_ts = max(ultimo_ts, fr[0])
                        ultima_frase = fr[1]
        except OSError:
            return None
        if size > TAIL_BYTES:
            try:
                with path.open("rb") as fh:
                    fh.seek(max(0, size - TAIL_BYTES))
                    chunk = fh.read(TAIL_BYTES)
            except OSError:
                chunk = b""
            for raw in reversed(chunk.splitlines()):
                if not raw.strip():
                    continue
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(obj, dict):
                    continue
                fr = _frase_de(obj)
                if fr:
                    ultimo_ts = max(ultimo_ts, fr[0])
                    ultima_frase = fr[1]
                    break
        if not cwd:
            return None
        return _Meta(
            titulo=_una_linea(titulo or path.stem[:12], MAX_TITULO),
            cwd=cwd,
            ultimo_ts=_ts_iso(ultimo_ts, mtime),
            ultima_frase=_una_linea(ultima_frase, MAX_FRASE),
        )


class SesionesViejas:
    def __init__(
        self,
        projects_dir: Path,
        *,
        plan_cwds: Callable[[], list],
        excluir_carpetas: tuple[str, ...] = (),
        sesiones_excluir: Callable[[], set[str]] = lambda: set(),
        abiertas: Callable[[], set[str]] = lambda: set(),
        clock: Callable[[], float] = time.time,
    ):
        self.projects_dir = projects_dir
        self.plan_cwds = plan_cwds
        self.excluir_carpetas = frozenset(excluir_carpetas)
        self.sesiones_excluir = sesiones_excluir
        self.abiertas = abiertas
        self.clock = clock
        self._lector = _Lector()

    def listar(self, q: str = "") -> list[dict]:
        if not self.projects_dir.is_dir():
            return []
        cutoff = self.clock() - DIAS * 86400
        needle = (q or "").casefold().strip()
        out: list[dict] = []
        vistos: set[str] = set()
        for path in self.projects_dir.glob("*/*.jsonl"):
            if not SESSION_ID.match(path.stem) or path.stem in vistos:
                continue
            if path.parent.name in self.excluir_carpetas or DIR_EXCLUIDO.search(path.parent.name):
                continue
            if path.stem in self.sesiones_excluir() or path.stem in self.abiertas():
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff:
                continue
            meta = self._lector.leer(path)
            if meta is None:
                continue
            try:
                validar_carpeta(meta.cwd, self.plan_cwds())
            except TraspasoError:
                continue
            item = {
                "session_id": path.stem,
                "titulo": meta.titulo,
                "carpeta": _display_path(meta.cwd),
                "ultimo_ts": meta.ultimo_ts,
                "ultima_frase": meta.ultima_frase,
                "_mtime": st.st_mtime,
            }
            if needle:
                blob = f"{item['titulo']}\n{item['carpeta']}\n{item['ultima_frase']}".casefold()
                if needle not in blob:
                    continue
            vistos.add(path.stem)
            out.append(item)
        out.sort(key=lambda r: r["_mtime"], reverse=True)
        for row in out:
            row.pop("_mtime", None)
        return out[:MAX_RESULTADOS]

    def encontrar(self, session_id: str) -> Optional[tuple[Path, _Meta]]:
        if not SESSION_ID.match(session_id or ""):
            return None
        matches = list(self.projects_dir.glob(f"*/{session_id}.jsonl"))
        if not matches:
            return None
        path = matches[0]
        if path.parent.name in self.excluir_carpetas or DIR_EXCLUIDO.search(path.parent.name):
            return None
        meta = self._lector.leer(path)
        if meta is None:
            return None
        return path, meta


def validar_uuid(session_id: str) -> str:
    try:
        return str(uuid.UUID(session_id))
    except (ValueError, AttributeError, TypeError):
        raise TraspasoError(422, "session_id inválido")
