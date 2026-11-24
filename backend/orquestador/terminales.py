"""Terminales que no son de un agente: listado para el tablero y lectura de su salida (solo lectura)."""
import asyncio
import hashlib
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

from .dialogo import visibles
from .enchufe import TerminalesError, como_snapshot
from .enchufe.modelo import InfoProceso
from .redaccion import OCULTO, redactar_basico as redactar
from .enchufe.ids import valido
from .internas import pane_interno
from .traspaso import CONTROL_RE, ID_RE, TraspasoError

TECLAS = {
    "ctrl_c": "ctrl-c",
    "arriba": "arriba",
    "enter": "enter",
    "fin_linea": "ctrl-e",
    "borrar_linea": "ctrl-u",
}

SHELLS = frozenset({"bash", "zsh", "fish", "sh", "dash"})
# Procesos de agente: aunque Herdr todavía no lo marque como agente, en ese pane no se actúa.
AGENT_PROCS = frozenset({"claude"})
# Claude lanzado vía node/npx o con el binario versionado (`~/.local/share/claude/versions/X`) no se llama `claude`.
_CLAUDE_ARG = re.compile(r"(?:^|/)claude(?:\.js|\.exe)?$|@anthropic-ai/claude-code|/claude/versions/")
TITLE_CHARS = 120
CWD_CHARS = 200
PROCESS_CHARS = 40
INFO_TTL = 10.0
INFO_PARALLEL = 4
READ_LINES = 500
READ_BYTES = 256 * 1024
READ_CACHE_TTL = 1.0
READ_IN_FLIGHT = 3
READS_PER_MINUTE = 120
FRESH_INFO_TTL = 3.0


class SlidingLimit:
    """Ventana deslizante en memoria: `hit` devuelve 0 si pasa o los segundos de espera."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._hits: dict = {}

    def hit(self, key: str, *limits: tuple) -> int:
        now = self.clock()
        queue = self._hits.setdefault(key, deque())
        horizon = max(w for _, w in limits)
        while queue and now - queue[0] >= horizon:
            queue.popleft()
        wait = 0.0
        for count, window in limits:
            recent = [t for t in queue if now - t < window]
            if len(recent) >= count:
                wait = max(wait, window - (now - recent[0]))
        if wait > 0:
            return int(wait) + 1
        queue.append(now)
        return 0

    def restantes(self, key: str, limit: tuple[int, float]) -> int:
        count, window = limit
        now = self.clock()
        queue = self._hits.get(key, deque())
        recent = [t for t in queue if now - t < window]
        return max(0, count - len(recent))

    def consumir(self, key: str, n: int, limit: tuple[int, float]) -> int:
        if n <= 0:
            return 0
        if self.restantes(key, limit) < n:
            now = self.clock()
            queue = self._hits.get(key, deque())
            count, window = limit
            recent = [t for t in queue if now - t < window]
            if recent:
                wait = window - (now - recent[0])
                return int(wait) + 1
            return 1
        for _ in range(n):
            self.hit(key, limit)
        return 0


def clean(text: str, limit: int) -> str:
    return visibles(CONTROL_RE.sub(" ", text or ""))[:limit]


def short_cwd(cwd: str, limit: int = CWD_CHARS) -> str:
    cwd = CONTROL_RE.sub(" ", cwd or "")
    home = str(Path.home())
    if home and (cwd == home or cwd.startswith(home + "/")):
        cwd = "~" + cwd[len(home):]
    return cwd if len(cwd) <= limit else "…" + cwd[-(limit - 1):]


def pane_cwd(pane: dict) -> str:
    return pane.get("foreground_cwd") or pane.get("cwd") or ""


def parse_process(info: InfoProceso | None) -> dict:
    """(proceso, estado) a partir de `pane process-info`. Nunca devuelve argumentos: pueden traer tokens."""
    if info is None or not info.procesos:
        return {"proceso": None, "estado": "desconocido"}
    procs = list(info.procesos)
    if any(isinstance(a, str) and _CLAUDE_ARG.search(a) for p in procs for a in p.argv[:3]):
        return {"proceso": "claude", "estado": "corriendo"}
    group = info.grupo
    proc = next((p for p in procs if group is not None and p.pid == group), procs[0])
    argv = proc.argv
    first = argv[0] if argv and isinstance(argv[0], str) else str(proc.nombre or "")
    name = os.path.basename(first.lstrip("-") if first.startswith("-") else first)
    if not name:
        return {"proceso": None, "estado": "desconocido"}
    return {"proceso": clean(name, PROCESS_CHARS), "estado": "prompt" if name in SHELLS else "corriendo"}


class ProcessInfoCache:
    def __init__(self, enchufe, clock: Callable[[], float] = time.monotonic, ttl: float = INFO_TTL,
                 parallel: int = INFO_PARALLEL):
        self.enchufe = enchufe
        self.clock = clock
        self.ttl = ttl
        self._cache: dict = {}
        self._sem = asyncio.Semaphore(parallel)

    async def _fetch(self, pane_id: str) -> dict:
        async with self._sem:
            try:
                info = await self.enchufe.proceso(pane_id)
            except (TerminalesError, OSError):
                return {"proceso": None, "estado": "desconocido"}
        return parse_process(info)

    async def get(self, pane_id: str, revision=None, ttl: Optional[float] = None) -> dict:
        """`ttl=0` fuerza lectura fresca (las acciones nunca confían en la caché del tablero)."""
        key = (pane_id, revision)
        limit = self.ttl if ttl is None else ttl
        hit = self._cache.get(key)
        now = self.clock()
        if hit and limit > 0 and now - hit[0] < limit:
            return hit[1]
        value = await self._fetch(pane_id)
        self._cache[key] = (self.clock(), value)
        return value

    async def many(self, panes: list) -> dict:
        now = self.clock()
        live = {(p["pane_id"], p.get("revision")) for p in panes}
        self._cache = {k: v for k, v in self._cache.items() if k in live and now - v[0] < self.ttl}
        found = await asyncio.gather(*[self.get(p["pane_id"], p.get("revision")) for p in panes])
        return {p["pane_id"]: info for p, info in zip(panes, found)}


def merged_panes(snapshot: dict) -> dict:
    merged: dict = {}
    for source in ("panes", "agents"):
        for pane in snapshot.get(source, []):
            if pane.get("pane_id"):
                merged[pane["pane_id"]] = {**merged.get(pane["pane_id"], {}), **pane}
    return merged


def is_agent(pane: dict, agent_ids: set) -> bool:
    return bool(pane.get("agent")) or pane.get("pane_id") in agent_ids


def terminal_panes(snapshot: dict, hidden: set = frozenset()) -> list:
    agent_ids = {a.get("pane_id") for a in snapshot.get("agents", [])}
    panes = [p for p in merged_panes(snapshot).values() if not is_agent(p, agent_ids) and p["pane_id"] not in hidden]
    return sorted(panes, key=lambda p: p["pane_id"])


def terminals_by_tab(snapshot: dict, info: dict, hidden: set) -> dict:
    out: dict = {}
    for pane in terminal_panes(snapshot, hidden):
        data = info.get(pane["pane_id"]) or {"proceso": None, "estado": "desconocido"}
        out.setdefault(pane.get("tab_id"), []).append({
            "pane_id": pane["pane_id"],
            "terminal_id": pane.get("terminal_id") or "",
            "titulo": titulo_de(pane),
            "cwd": short_cwd(pane_cwd(pane)),
            "proceso": data["proceso"] or "",
            "estado": data["estado"],
            "protegida": False,
        })
    return out


def titulo_de(pane: dict) -> str:
    """El título lo pone la shell y puede traer el comando en curso con sus argumentos: se redacta."""
    return clean(redactar(pane.get("terminal_title_stripped") or pane.get("terminal_title") or ""), TITLE_CHARS)


def huella_de(pane: dict, proceso: str = "") -> str:
    """Pane, terminal, workspace, cwd y proceso en primer plano: si algo cambia entre ver y confirmar, 409."""
    raw = "|".join([pane.get("pane_id") or "", pane.get("terminal_id") or "", pane.get("workspace_id") or "",
                    pane_cwd(pane), proceso or ""])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def cortar(text: str, lines: int = READ_LINES, size: int = READ_BYTES) -> tuple:
    """Se quedan las últimas líneas y bytes; devuelve (texto, truncado)."""
    parts = text.split("\n")
    truncated = len(parts) > lines
    parts = parts[-lines:]
    total = sum(len(p.encode()) + 1 for p in parts)
    while total > size and len(parts) > 1:
        total -= len(parts.pop(0).encode()) + 1
        truncated = True
    out = "\n".join(parts)
    if len(out.encode()) > size:
        out = out.encode()[-size:].decode(errors="ignore")
        truncated = True
    return out, truncated


class Terminales:
    """Ubica terminales en el snapshot y lee su salida. No escribe nunca."""

    def __init__(self, enchufe, info: ProcessInfoCache, hidden: Callable[[], set],
                 clock: Callable[[], float] = time.monotonic, writes: Callable[[], bool] = lambda: False):
        self.writes = writes
        self.enchufe = enchufe
        self.info = info
        self.hidden = hidden
        self.clock = clock
        self.interna: Optional[Callable[[str], bool]] = None
        self._snap: Optional[tuple] = None
        self._reads: dict = {}
        self._locks: dict = {}
        self._sem = asyncio.Semaphore(READ_IN_FLIGHT)
        self.limit = SlidingLimit(clock)

    async def snapshot(self, fresh: bool = False) -> dict:
        if not fresh and self._snap and self.clock() - self._snap[0] < READ_CACHE_TTL:
            return self._snap[1]
        try:
            snap = como_snapshot(await self.enchufe.tablero())
        except (TerminalesError, OSError, ValueError) as exc:
            raise TraspasoError(502, f"Las terminales no respondieron: {exc}")
        self._snap = (self.clock(), snap)
        return snap

    def workspace_label(self, snapshot: dict, workspace_id: str) -> str:
        return next((w.get("label") or "" for w in snapshot.get("workspaces", [])
                     if w.get("workspace_id") == workspace_id), "")

    def tab_label(self, snapshot: dict, tab_id: str) -> str:
        return next((t.get("label") or "" for t in snapshot.get("tabs", []) if t.get("tab_id") == tab_id), "")

    def escritura(self, estado: str) -> dict:
        """Si se puede escribir y, si no, el motivo (palabra fija: la UI la traduce; nunca argv ni salida)."""
        if not self.writes():
            motivo = "apagada"
        elif estado == "corriendo":
            motivo = "ocupada"
        elif estado != "prompt":
            motivo = "desconocido"
        else:
            motivo = None
        return {"puede_escribir": motivo is None, "motivo": motivo}

    def locate(self, snapshot: dict, pane_id: str) -> dict:
        if not valido(ID_RE, pane_id or ""):
            raise TraspasoError(400, "pane_id inválido")
        pane = merged_panes(snapshot).get(pane_id)
        if pane is None or pane_interno(pane, self.interna):
            raise TraspasoError(404, "la terminal ya no está")
        agent_ids = {a.get("pane_id") for a in snapshot.get("agents", [])}
        if is_agent(pane, agent_ids):
            raise TraspasoError(403, "es una sesión de agente")
        if pane_id in self.hidden():
            raise TraspasoError(403, "es el panel del orquestador")
        return pane

    @staticmethod
    def check_proceso(info: dict) -> None:
        """Herdr puede tardar en marcar un Claude como agente: el proceso en primer plano manda."""
        if (info.get("proceso") or "") in AGENT_PROCS:
            raise TraspasoError(403, "es una sesión de agente")

    async def salida(self, pane_id: str, rev: str = "") -> dict:
        pane = self.locate(await self.snapshot(), pane_id)
        wait = self.limit.hit("salida", (READS_PER_MINUTE, 60.0))
        if wait:
            raise TraspasoError(429, "demasiadas lecturas", {"retry_after": wait})
        proc = await self.info.get(pane_id, ttl=FRESH_INFO_TTL)
        text = await self._read(pane_id)
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        base = {"proceso": proc["proceso"] or "", "estado": proc["estado"],
                **self.escritura(proc["estado"])}
        if rev and rev == digest:
            return {"sin_cambios": True, "revision": digest, **base}
        ansi, truncated = cortar(text)
        return {"pane_id": pane_id, "revision": digest, "ansi": ansi, "truncado": truncated,
                "cwd": short_cwd(pane_cwd(pane)), **base}

    async def _read(self, pane_id: str) -> str:
        lock = self._locks.setdefault(pane_id, asyncio.Lock())
        async with lock:
            hit = self._reads.get(pane_id)
            if hit and self.clock() - hit[0] < READ_CACHE_TTL:
                return hit[1]
            if self._sem.locked():
                raise TraspasoError(429, "demasiadas lecturas en curso", {"retry_after": 1})
            async with self._sem:
                try:
                    text = await self.enchufe.leer(pane_id, fuente="reciente", lineas=READ_LINES, formato="ansi")
                except (TerminalesError, OSError) as exc:
                    raise TraspasoError(502, f"Las terminales no respondieron: {exc}")
            self._reads[pane_id] = (self.clock(), text)
            if len(self._reads) > 32:
                oldest = min(self._reads, key=lambda k: self._reads[k][0])
                self._reads.pop(oldest, None)
            return text
