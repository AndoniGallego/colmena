import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import private_write

log = logging.getLogger(__name__)

MAX_CIERRES = 100
MAX_RESPUESTAS = 200
MAX_TECLAS = 200
MAX_TRASPASOS = 200
MAX_MENSAJES = 500
MAX_SILENCIADAS = 500


def _quarantine_state_file(path: Path, reason: str) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.roto-{stamp}")
    suffix = 2
    while backup.exists():
        backup = path.with_name(f"{path.name}.roto-{stamp}-{suffix}")
        suffix += 1
    try:
        os.replace(path, backup)
    except OSError as exc:
        log.error("%s; no pude respaldar %s: %s", reason, path.name, exc)
        return
    log.error("%s; respaldo en %s", reason, backup.name)


class StateStore:
    def __init__(self, directory: Path, save_delay: float = 0.2):
        self.path = directory / "state.json"
        self._save_delay = save_delay
        self._data_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._dirty = False
        self._timer: Optional[threading.Timer] = None
        self.data = {"messages": [], "traspasos": [],
                     "mensajes": [], "cierres": [], "respuestas": [], "teclas": [], "replies": {},
                     "orden_tablero": [], "orden_pestanas": {}, "plegadas": [], "silenciadas": []}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except ValueError as exc:
                _quarantine_state_file(self.path, f"state.json no parseable: {exc}")
            else:
                if isinstance(loaded, dict):
                    self.data.update(loaded)
                else:
                    _quarantine_state_file(self.path, f"state.json no es un objeto ({type(loaded).__name__})")

    def _schedule(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self._save_delay, self._timer_write)
        self._timer.daemon = True
        self._timer.start()

    def _timer_write(self) -> None:
        self._write()

    def _write(self) -> None:
        with self._write_lock:
            with self._data_lock:
                if not self._dirty:
                    return
                try:
                    payload = json.dumps(self.data, ensure_ascii=False)
                except Exception:
                    log.exception("no pude guardar state.json")
                    return
                self._dirty = False
            try:
                private_write(self.path, payload)
            except Exception:
                with self._data_lock:
                    self._dirty = True
                log.exception("no pude guardar state.json")

    def save(self) -> None:
        self._dirty = True
        self._schedule()

    def flush(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._write()

    def messages(self) -> list:
        """Solo lectura: historial de mensajes viejos, que ya nadie escribe."""
        return self.data.get("messages") or []

    def traspasos(self) -> list:
        return self.data.setdefault("traspasos", [])

    def add_traspaso(self, entry: dict) -> None:
        items = self.traspasos()
        items.append(entry)
        del items[:-MAX_TRASPASOS]
        self.save()

    def mensajes(self) -> list:
        return self.data.setdefault("mensajes", [])

    def add_mensaje(self, entry: dict) -> None:
        items = self.mensajes()
        items.append(entry)
        del items[:-MAX_MENSAJES]
        self.save()

    def cierres(self) -> list:
        return self.data.setdefault("cierres", [])

    def add_cierre(self, entry: dict) -> None:
        cierres = self.cierres()
        cierres.append(entry)
        del cierres[:-MAX_CIERRES]
        self.save()

    def respuestas(self) -> list:
        return self.data.setdefault("respuestas", [])

    def add_respuesta(self, entry: dict) -> None:
        items = self.respuestas()
        items.append(entry)
        del items[:-MAX_RESPUESTAS]
        self.save()

    def teclas_enviadas(self, pane: str, tool_use_id: str) -> bool:
        return [pane, tool_use_id] in self.data.setdefault("teclas", [])

    def add_tecla(self, pane: str, tool_use_id: str) -> None:
        items = self.data.setdefault("teclas", [])
        if [pane, tool_use_id] not in items:
            items.append([pane, tool_use_id])
            del items[:-MAX_TECLAS]
            self.save()

    def orden_tablero(self) -> list:
        raw = self.data.get("orden_tablero")
        return list(raw) if isinstance(raw, list) else []

    def set_orden_tablero(self, orden: list) -> None:
        self.data["orden_tablero"] = list(orden)
        self.save()

    def orden_pestanas(self) -> dict:
        raw = self.data.get("orden_pestanas")
        if not isinstance(raw, dict):
            return {}
        out: dict = {}
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, list):
                out[k] = [x for x in v if isinstance(x, str)]
        return out

    def set_orden_pestanas_grupo(self, grupo: str, orden: list) -> None:
        raw = self.data.setdefault("orden_pestanas", {})
        if not isinstance(raw, dict):
            raw = {}
            self.data["orden_pestanas"] = raw
        if not orden:
            raw.pop(grupo, None)
        else:
            raw[grupo] = list(orden)
            while len(raw) > 200:
                del raw[next(iter(raw))]
        self.save()

    def clear_orden_pestanas(self) -> None:
        if self.orden_pestanas():
            self.data["orden_pestanas"] = {}
            self.save()

    def plegadas(self) -> list:
        raw = self.data.get("plegadas")
        return list(raw) if isinstance(raw, list) else []

    def set_plegadas(self, ids: list) -> None:
        self.data["plegadas"] = list(ids)
        self.save()

    def silenciadas(self) -> list:
        raw = self.data.get("silenciadas")
        return [x for x in raw if isinstance(x, str)] if isinstance(raw, list) else []

    def set_silenciada(self, sid: str, on: bool) -> None:
        items = self.silenciadas()
        if on == (sid in items):
            return
        if on:
            items.append(sid)
            del items[:-MAX_SILENCIADAS]
        else:
            items.remove(sid)
        self.data["silenciadas"] = items
        self.save()
