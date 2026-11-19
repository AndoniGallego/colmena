import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from .config import private_write

MODELOS = ("sonnet", "opus")
RETENCION_DIAS = 30
CAMPOS = ("input", "cache_write", "cache_read", "output")
FUENTES = ("mrs",)
MAX_TOPE = 1_000_000_000
_KEYS = {"input": "input_tokens", "cache_write": "cache_creation_input_tokens",
         "cache_read": "cache_read_input_tokens", "output": "output_tokens"}


def _count(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def usage_from(raw) -> Optional[dict]:
    """Normaliza el `usage` de un evento result de la CLI; None si no trae nada utilizable."""
    if not isinstance(raw, dict):
        return None
    out = {name: _count(raw.get(key)) for name, key in _KEYS.items()}
    return out if any(out.values()) else None


def context_from(raw) -> Optional[int]:
    """Tokens que ocupa el contexto en la última llamada a la API (entrada + caché)."""
    usage = usage_from(raw)
    if usage is None:
        return None
    return usage["input"] + usage["cache_write"] + usage["cache_read"]


def total_of(usage: dict) -> int:
    return sum(_count(usage.get(name)) for name in CAMPOS)


def valid_modelo(value) -> str:
    return value if isinstance(value, str) and value in MODELOS else "sonnet"


def valid_tope(value, default: int) -> int:
    ok = isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_TOPE
    return value if ok else default


def _empty() -> dict:
    return {**{name: 0 for name in CAMPOS}, "mensajes": 0}


class UsoStore:
    """Tokens por día y por fuente (hoy solo MR; lee sin error la fuente vieja `dios`), con retención de 30 días."""

    def __init__(self, directory: Path, now: Callable[[], datetime] = lambda: datetime.now().astimezone()):
        self.path = directory / "uso.json"
        self._now = now
        self._lock = threading.Lock()
        self.days: dict = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("days"), dict):
                    self.days = loaded["days"]
            except ValueError:
                pass

    def today(self) -> str:
        return self._now().date().isoformat()

    def add(self, source: str, usage: Optional[dict]) -> None:
        if source not in FUENTES or not usage:
            return
        with self._lock:
            day = self.days.setdefault(self.today(), {})
            bucket = day.setdefault(source, _empty())
            for name in CAMPOS:
                bucket[name] = _count(bucket.get(name)) + _count(usage.get(name))
            bucket["mensajes"] = _count(bucket.get("mensajes")) + 1
            self._prune()
            private_write(self.path, json.dumps({"days": self.days}, ensure_ascii=False))

    def _prune(self) -> None:
        limit = (self._now().date() - timedelta(days=RETENCION_DIAS)).isoformat()
        for key in [k for k in self.days if not isinstance(k, str) or k < limit]:
            del self.days[key]

    def day(self, key: Optional[str] = None) -> dict:
        data = self.days.get(key or self.today()) or {}
        out = {}
        for source in FUENTES:
            bucket = {**_empty(), **{k: _count(v) for k, v in (data.get(source) or {}).items() if k in _empty()}}
            bucket["total"] = total_of(bucket)
            out[source] = bucket
        total = {name: sum(out[s][name] for s in FUENTES) for name in (*CAMPOS, "mensajes")}
        total["total"] = total_of(total)
        out["total"] = total
        return out

    def historial(self, dias: int = RETENCION_DIAS) -> list:
        dias = max(1, min(RETENCION_DIAS, dias))
        hoy = self._now().date()
        out = []
        for back in range(dias - 1, -1, -1):
            key = (hoy - timedelta(days=back)).isoformat()
            total = self.day(key)["total"]
            out.append({"fecha": key, **{name: total[name] for name in CAMPOS}, "mensajes": total["mensajes"], "total": total["total"]})
        return out

    def total_today(self) -> int:
        return self.day()["total"]["total"]


def estado(total: int, tope: int) -> str:
    if tope <= 0:
        return "ok"
    if total >= tope:
        return "tope"
    return "aviso" if total * 100 >= tope * 80 else "ok"
