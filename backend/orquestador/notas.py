import json
import logging
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import private_write
from .state import _quarantine_state_file

log = logging.getLogger(__name__)

TIPOS = ("apunte", "recordatorio")
MAX_TEXTO = 4000
_LIMITES_ORIGEN = {"sid": 200, "nombre": 200, "ts": 64}


class NotasNoDisponibles(RuntimeError):
    pass


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validar_tipo(tipo) -> str:
    if tipo not in TIPOS:
        raise ValueError("tipo invalido")
    return tipo


def _validar_texto(texto) -> str:
    if not isinstance(texto, str):
        raise ValueError("texto invalido")
    texto = texto.strip()
    if not texto or len(texto) > MAX_TEXTO:
        raise ValueError("texto invalido")
    return texto


def _limpiar_origen(origen) -> Optional[dict]:
    if not isinstance(origen, dict):
        return None
    limpio = {k: v[:n] for k, n in _LIMITES_ORIGEN.items() if isinstance(v := origen.get(k), str)}
    return limpio or None


class NotasStore:
    def __init__(self, directory: Path, save_delay: float = 0.2):
        self.path = directory / "notas.json"
        self._save_delay = save_delay
        self._data_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._dirty = False
        self._timer: Optional[threading.Timer] = None
        self.version = 0
        self._notas: list = []
        self._disponible = True
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except OSError:
                self._disponible = False
                log.exception("no pude leer notas.json; arranco sin notas")
            except ValueError as exc:
                _quarantine_state_file(self.path, f"notas.json no parseable: {exc}")
            else:
                if isinstance(loaded, dict) and isinstance(loaded.get("notas"), list):
                    self._notas = [n for n in loaded["notas"] if isinstance(n, dict)]
                    for n in self._notas:
                        n.setdefault("editada_at", n.get("creada_at"))
                else:
                    _quarantine_state_file(self.path, "notas.json con forma inesperada")

    def _schedule(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self._save_delay, self._write)
        self._timer.daemon = True
        self._timer.start()

    def _write(self) -> None:
        with self._write_lock:
            with self._data_lock:
                if not self._dirty or not self._disponible:
                    return
                try:
                    payload = json.dumps({"notas": self._notas}, ensure_ascii=False)
                except Exception:
                    log.exception("no pude guardar notas.json")
                    return
                self._dirty = False
            try:
                private_write(self.path, payload)
            except Exception:
                with self._data_lock:
                    self._dirty = True
                log.exception("no pude guardar notas.json")

    def _changed(self) -> None:
        self.version += 1
        self._dirty = True
        self._schedule()

    def flush(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._write()

    def _exigir_disponible(self) -> None:
        if not self._disponible:
            raise NotasNoDisponibles("notas.json no se pudo leer")

    def _buscar(self, nota_id: str) -> Optional[dict]:
        return next((n for n in self._notas if n.get("id") == nota_id), None)

    def listar(self) -> list:
        with self._data_lock:
            if not self._disponible:
                return []
            return [dict(n) for n in reversed(self._notas)]

    def crear(self, tipo: str, texto: str, origen: Optional[dict] = None) -> dict:
        self._exigir_disponible()
        _validar_tipo(tipo)
        texto = _validar_texto(texto)
        ahora = _ahora()
        nota = {"id": "n_" + secrets.token_urlsafe(8), "tipo": tipo, "texto": texto,
                "creada_at": ahora, "editada_at": ahora, "hecha_at": None, "origen": _limpiar_origen(origen)}
        with self._data_lock:
            self._notas.append(nota)
            self._changed()
            return dict(nota)

    def editar(self, nota_id: str, texto: Optional[str] = None, tipo: Optional[str] = None) -> Optional[dict]:
        self._exigir_disponible()
        if texto is not None:
            texto = _validar_texto(texto)
        if tipo is not None:
            _validar_tipo(tipo)
        with self._data_lock:
            nota = self._buscar(nota_id)
            if nota is None:
                return None
            cambio = False
            if texto is not None and texto != nota.get("texto"):
                nota["texto"] = texto
                cambio = True
            if tipo is not None and tipo != nota.get("tipo"):
                nota["tipo"] = tipo
                cambio = True
                if tipo != "recordatorio":
                    nota["hecha_at"] = None
            if cambio:
                nota["editada_at"] = _ahora()
                self._changed()
            return dict(nota)

    def marcar(self, nota_id: str, hecha: bool) -> Optional[dict]:
        self._exigir_disponible()
        with self._data_lock:
            nota = self._buscar(nota_id)
            if nota is None:
                return None
            if nota.get("tipo") != "recordatorio":
                raise ValueError("solo los recordatorios se marcan")
            if hecha and not nota.get("hecha_at"):
                nota["hecha_at"] = _ahora()
                self._changed()
            elif not hecha and nota.get("hecha_at"):
                nota["hecha_at"] = None
                self._changed()
            return dict(nota)

    def borrar(self, nota_id: str) -> bool:
        self._exigir_disponible()
        with self._data_lock:
            nota = self._buscar(nota_id)
            if nota is None:
                return False
            self._notas.remove(nota)
            self._changed()
            return True

    def pendientes(self) -> int:
        with self._data_lock:
            if not self._disponible:
                return 0
            return sum(1 for n in self._notas if n.get("tipo") == "recordatorio" and not n.get("hecha_at"))
