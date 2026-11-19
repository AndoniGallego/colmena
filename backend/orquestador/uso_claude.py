import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from .config import private_write
from .statusline import SESSION_ID, model_name
from .uso import CAMPOS, RETENCION_DIAS, total_of

log = logging.getLogger("orquestador.uso_claude")

CACHE_VERSION = 1
TAIL_IDS = 64
TOP_FILAS = 14
RESCAN_THROTTLE = 10.0
RANGOS = {"hoy": 1, "7d": 7, "30d": 30}
_ASSISTANT = (b'"type":"assistant"', b'"type": "assistant"')
_TITLE = (b'"ai-title"',)
_KEYS = {"input": "input_tokens", "cache_write": "cache_creation_input_tokens",
         "cache_read": "cache_read_input_tokens", "output": "output_tokens"}


def project_key(path: Path) -> str:
    """Nombre de carpeta que Claude Code le da a un cwd dentro de ~/.claude/projects."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _count(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _usage(raw) -> Optional[list]:
    if not isinstance(raw, dict):
        return None
    out = [_count(raw.get(_KEYS[name])) for name in CAMPOS]
    return out if any(out) else None


def _empty() -> dict:
    return {**{name: 0 for name in CAMPOS}, "mensajes": 0}


def _add(bucket: dict, vals, mensajes: int = 0) -> None:
    for i, name in enumerate(CAMPOS):
        bucket[name] += vals[i]
    bucket["mensajes"] += mensajes


def _close(bucket: dict) -> dict:
    return {**bucket, "total": total_of(bucket)}


def _ts_seconds(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000 if value > 1e11 else float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _normalizar_limites(rate_limits: dict, ts, now: float) -> Optional[dict]:
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return None
    out = {}
    for key in ("five_hour", "seven_day"):
        raw = rate_limits.get(key)
        if not isinstance(raw, dict):
            continue
        pct = raw.get("used_percentage")
        if isinstance(pct, bool) or not isinstance(pct, (int, float)) or pct < 0:
            continue
        resets = _ts_seconds(raw.get("resets_at"))
        out[key] = {"pct": round(min(float(pct), 100.0), 1),
                    "resets_at": datetime.fromtimestamp(resets).astimezone().isoformat() if resets else None,
                    "vencido": bool(resets and resets <= now)}
    if not out:
        return None
    return {**out, "actualizado": datetime.fromtimestamp(ts).astimezone().isoformat(),
            "edad_s": max(0, int(now - ts))}


def _leer_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_limits(directory: Optional[Path], now: float) -> Optional[dict]:
    """Límites del plan: primero `plan-limites.json` (en el padre del dir de snapshots), si no el snapshot más nuevo que los traiga."""
    if directory is None:
        return None
    unico = _leer_json(directory.parent / "plan-limites.json")
    if unico and isinstance(unico.get("rate_limits"), dict):
        found = _normalizar_limites(unico["rate_limits"], unico.get("ts"), now)
        if found:
            return found
    if not directory.is_dir():
        return None
    best = None
    for path in directory.glob("*.json"):
        data = _leer_json(path)
        if not data or not isinstance(data.get("rate_limits"), dict):
            continue
        ts = data.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            continue
        if best is None or ts > best[0]:
            best = (ts, data["rate_limits"])
    if best is None:
        return None
    return _normalizar_limites(best[1], best[0], now)


class ClaudeUso:
    """Uso de tokens de todas las sesiones de Claude, leído de los transcripts locales (sin llamar a la API).

    Lee cada archivo desde donde quedó la última vez y guarda lo sumado por día y modelo, así que
    pedirlo de nuevo solo procesa lo que se agregó.
    """

    def __init__(self, projects_dir: Path, directory: Path,
                 excluir: tuple = (), limits_dir: Optional[Path] = None,
                 now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
                 clock: Callable[[], float] = time.monotonic):
        self.projects_dir = projects_dir
        self.path = directory / "uso-claude.json"
        self.excluir = frozenset(excluir)
        self.limits_dir = limits_dir
        self._now = now
        self._clock = clock
        self._lock = threading.Lock()
        self._last_scan: Optional[float] = None
        self.files: dict = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded.get("v") == CACHE_VERSION and isinstance(loaded.get("files"), dict):
                    self.files = loaded["files"]
            except ValueError:
                pass

    # --- lectura incremental ---
    def _limit(self) -> str:
        return (self._now().astimezone().date() - timedelta(days=RETENCION_DIAS - 1)).isoformat()

    def _discover(self) -> list:
        out = []
        if not self.projects_dir.is_dir():
            return out
        for p in self.projects_dir.glob("*/*.jsonl"):
            if p.parent.name not in self.excluir and SESSION_ID.match(p.stem):
                out.append((p, None if p.stem.startswith("agent-") else p.stem, False))
        for p in self.projects_dir.glob("*/*/subagents/*.jsonl"):
            if p.parents[2].name not in self.excluir and SESSION_ID.match(p.parent.parent.name):
                out.append((p, p.parent.parent.name, True))
        return out

    def scan(self, force: bool = False) -> bool:
        """Procesa lo nuevo de cada transcript; devuelve True si algo cambió."""
        with self._lock:
            if not force and self._last_scan is not None and self._clock() - self._last_scan < RESCAN_THROTTLE:
                return False
            self._last_scan = self._clock()
            cutoff = (self._now() - timedelta(days=RETENCION_DIAS + 1)).timestamp()
            changed = False
            seen = set()
            for path, session, sub in self._discover():
                key = str(path)
                seen.add(key)
                try:
                    st = path.stat()
                    if st.st_mtime < cutoff:
                        if key in self.files:
                            del self.files[key]
                            changed = True
                        continue
                    changed = self._process(path, key, st, session, sub) or changed
                except OSError as exc:
                    log.warning("no pude leer %s: %s", path, exc)
            for key in [k for k in self.files if k not in seen]:
                del self.files[key]
                changed = True
            if self._prune():
                changed = True
            if changed:
                private_write(self.path, json.dumps({"v": CACHE_VERSION, "files": self.files}, ensure_ascii=False))
            return changed

    def _prune(self) -> bool:
        limit = self._limit()
        changed = False
        for state in self.files.values():
            for day in [d for d in state["days"] if d < limit]:
                del state["days"][day]
                changed = True
        return changed

    def _process(self, path: Path, key: str, st, session: Optional[str], sub: bool) -> bool:
        state = self.files.get(key)
        if state and (state.get("inode") != st.st_ino or st.st_size < state.get("offset", 0)):
            state = None
        if state and state["size"] == st.st_size and state["mtime_ns"] == st.st_mtime_ns:
            return False
        state = state or {"inode": st.st_ino, "size": 0, "mtime_ns": 0, "offset": 0, "session": session or "",
                          "sub": sub, "cwd": "", "title": "", "days": {}, "tail": {}}
        offset = state["offset"]
        with path.open("rb") as fh:
            fh.seek(offset)
            for raw in fh:
                if not raw.endswith(b"\n"):
                    break
                offset += len(raw)
                self._line(raw, state, sub)
        state.update(offset=offset, size=st.st_size, mtime_ns=st.st_mtime_ns)
        self.files[key] = state
        return True

    def _line(self, raw: bytes, state: dict, sub: bool) -> None:
        is_title = not sub and any(m in raw for m in _TITLE)
        if not is_title and not any(m in raw for m in _ASSISTANT):
            return
        try:
            obj = json.loads(raw)
        except ValueError:
            return
        if not isinstance(obj, dict):
            return
        if is_title and obj.get("type") == "ai-title":
            if isinstance(obj.get("aiTitle"), str) and obj["aiTitle"].strip():
                state["title"] = obj["aiTitle"].strip()[:120]
            return
        if obj.get("type") != "assistant":
            return
        if not state["session"] and isinstance(obj.get("sessionId"), str) and SESSION_ID.match(obj["sessionId"]):
            state["session"] = obj["sessionId"]
        if isinstance(obj.get("cwd"), str) and obj["cwd"]:
            state["cwd"] = obj["cwd"]
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        vals = _usage(message.get("usage"))
        if vals is None:
            return
        try:
            day = datetime.fromisoformat(str(obj.get("timestamp")).replace("Z", "+00:00")).astimezone().date().isoformat()
        except ValueError:
            return
        if day < self._limit():
            return
        model = message.get("model") if isinstance(message.get("model"), str) and message.get("model") else "?"
        mid = message.get("id") if isinstance(message.get("id"), str) else obj.get("requestId")
        tail = state["tail"]
        prev = tail.get(mid) if isinstance(mid, str) else None
        if prev is not None:
            day, model = prev[0], prev[1]
            delta = [max(0, v - p) for v, p in zip(vals, prev[2:])]
            prev[2:] = [max(v, p) for v, p in zip(vals, prev[2:])]
            mensajes = 0
        else:
            delta, mensajes = vals, 1
            if isinstance(mid, str):
                tail[mid] = [day, model, *vals]
                while len(tail) > TAIL_IDS:
                    tail.pop(next(iter(tail)))
        if not any(delta) and not mensajes:
            return
        row = state["days"].setdefault(day, {}).setdefault(model, [0, 0, 0, 0, 0])
        for i, v in enumerate(delta):
            row[i] += v
        row[4] += mensajes

    # --- resumen ---
    def tokens_de_hoy(self, session_id: str) -> int:
        if not session_id:
            return 0
        self.scan()
        hoy = self._now().astimezone().date().isoformat()
        total = 0
        with self._lock:
            for state in self.files.values():
                if state.get("session") != session_id:
                    continue
                for row in state.get("days", {}).get(hoy, {}).values():
                    total += sum(row[:4])
        return total

    def summary(self, nombres: Optional[dict] = None) -> dict:
        self.scan()
        nombres = nombres or {}
        hoy = self._now().astimezone().date()
        fechas = [(hoy - timedelta(days=back)).isoformat() for back in range(RETENCION_DIAS - 1, -1, -1)]
        por_dia = {f: _empty() for f in fechas}
        rangos = {name: {f for f in fechas[-n:]} for name, n in RANGOS.items()}
        grupos = {name: {"sesiones": {}, "proyectos": {}, "modelos": {}} for name in RANGOS}
        meta: dict = {}

        with self._lock:
            files = [(dict(s), {d: {m: list(v) for m, v in ms.items()} for d, ms in s["days"].items()}) for s in self.files.values()]
        for state, days in files:
            sid = state.get("session") or "?"
            info = meta.setdefault(sid, {"title": "", "cwd": ""})
            if not state.get("sub"):
                info["title"] = state.get("title") or info["title"]
                info["cwd"] = state.get("cwd") or info["cwd"]
            elif not info["cwd"]:
                info["cwd"] = state.get("cwd") or ""
            for day, models in days.items():
                if day not in por_dia:
                    continue
                for model, row in models.items():
                    _add(por_dia[day], row[:4], row[4])
                    for name, dset in rangos.items():
                        if day in dset:
                            g = grupos[name]
                            _add(g["sesiones"].setdefault(sid, _empty()), row[:4], row[4])
                            _add(g["modelos"].setdefault(model, _empty()), row[:4], row[4])

        def proyecto(sid: str) -> str:
            cwd = meta.get(sid, {}).get("cwd") or ""
            return cwd.rstrip("/").rsplit("/", 1)[-1] or cwd or "Sin proyecto"

        desglose = {}
        for name, g in grupos.items():
            proyectos: dict = {}
            for sid, bucket in g["sesiones"].items():
                _add(proyectos.setdefault(proyecto(sid), _empty()), [bucket[n] for n in CAMPOS], bucket["mensajes"])
            sesiones = [self._fila(sid, b, self._nombre_sesion(sid, meta, nombres), proyecto(sid)) for sid, b in g["sesiones"].items()]
            filas_proy = [self._fila(p, b, p, "") for p, b in proyectos.items()]
            filas_mod = [self._fila(m, b, model_name(m) if m != "?" else "Sin modelo", m if m != "?" else "") for m, b in g["modelos"].items()]
            desglose[name] = {"sesiones": _top(sesiones), "proyectos": _top(filas_proy), "modelos": _top(filas_mod)}

        historial = [{"fecha": f, **_close(por_dia[f])} for f in fechas]
        totales = {name: _close(_sum(por_dia[f] for f in fechas[-n:])) for name, n in RANGOS.items()}
        return {"generado": self._now().isoformat(), "totales": totales, "historial": historial,
                "desglose": desglose, "limites": read_limits(self.limits_dir, self._now().timestamp())}

    @staticmethod
    def _nombre_sesion(sid: str, meta: dict, nombres: dict) -> str:
        if sid in nombres and nombres[sid]:
            return nombres[sid]
        info = meta.get(sid) or {}
        if info.get("title"):
            return info["title"]
        cwd = (info.get("cwd") or "").rstrip("/")
        return cwd.rsplit("/", 1)[-1] if cwd else f"Sesión {sid[:8]}"

    @staticmethod
    def _fila(fid: str, bucket: dict, nombre: str, detalle: str, tipo: str = "") -> dict:
        return {"id": fid, "nombre": nombre, "detalle": detalle, "tipo": tipo, **_close(bucket)}


def _sum(buckets) -> dict:
    out = _empty()
    for b in buckets:
        _add(out, [b[n] for n in CAMPOS], b["mensajes"])
    return out


def _top(filas: list) -> list:
    filas = sorted((f for f in filas if f["total"] > 0 or f["mensajes"] > 0), key=lambda f: (-f["total"], f["nombre"]))
    if len(filas) <= TOP_FILAS:
        return filas
    keep = filas[:TOP_FILAS - 1]
    rest = [f for f in filas if f not in keep]
    otras = _sum(rest)
    return keep + [{"id": "_otras", "nombre": f"Otras {len(rest)}", "detalle": "", "tipo": "otras", **_close(otras)}]


def nombres_herdr(board: Optional[dict]) -> dict:
    """session_id → «tab · workspace» de las sesiones abiertas en Herdr."""
    out = {}
    for ws in (board or {}).get("workspaces", []):
        for tab in ws.get("tabs", []):
            for agent in tab.get("agents", []):
                sid = agent.get("session_id")
                if not sid:
                    continue
                parts = [p for p in ((tab.get("label") or "").strip(), (ws.get("label") or "").strip()) if p]
                if parts:
                    out[sid] = " · ".join(dict.fromkeys(parts))
    return out
