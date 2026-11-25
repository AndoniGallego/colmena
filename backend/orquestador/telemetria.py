"""Registro propio de eventos de Colmena: JSONL por mes, esquema cerrado, sin contenido."""
import json
import logging
import os
import re
import threading
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from .redaccion import redactar

VERSION = 1
TOKEN_RE = re.compile(r"^[a-z0-9_]{1,40}$")
PROYECTO_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)?$")
ARCHIVO_RE = re.compile(r"^(\d{4})-(\d{2})\.jsonl$")
TOPE_BYTES = 20 * 1024 * 1024
RETENCION_DIAS = 90
_LOG = logging.getLogger("orquestador.telemetria")

_S, _I, _B = (str,), (int,), (bool,)
_NULL = type(None)
_TOKEN = "token"
_NOMBRE = re.compile(r"^[A-Za-z0-9_.]{1,60}$")
_PLANTILLA = re.compile(r"^[^/\x00-\x1f]{1,120}$")
_SEMANA = re.compile(r"^\d{4}-W\d{2}$")
_VERSION = re.compile(r"^[0-9A-Za-z._-]{1,32}$")
_FECHA = TS_RE
_PROYECTO = "proyecto"


def _c(tipos: tuple, marca=None) -> tuple:
    return (tipos, marca)


# marcador también puede ser una regex compilada: si el valor no cumple, va "otro".
# campo -> (tipos permitidos, marcador): None, "token", "proyecto" o la tupla de valores de un enum cerrado.
ESQUEMA: dict[str, dict[str, tuple]] = {
    "pedido": {
        "tipo": _c((str, _NULL), ("pestana", "tarjeta", "cerrar", "cursor", "mensaje", "programada", "tarea")),
        "origen": _c(_S, ("mcp", "marca")),
        "creado": _c(_B),
        "estado": _c(_S, ("abierto", "rechazado", "vencido", "descartado", "cortado")),
        "motivo": _c((str, _NULL), _TOKEN),
        "segundos": _c((int, _NULL)),
        "leyo_otra_sesion": _c(_B),
        "proyecto": _c((str, _NULL), _PROYECTO),
    },
    "respuesta": {
        "aviso": _c(_S, ("asks", "blocked")),
        "resultado": _c(_S, ("respondio", "sin_respuesta")),
        "segundos": _c((int, _NULL)),
        "via": _c((str, _NULL), ("prompt", "permiso")),
        "en_app": _c(_B),
    },
    "comando_sesion": {
        "resultado": _c(_S, ("corrido", "fallo", "no")),
        "codigo": _c((str, _NULL), _TOKEN),
        "proyecto": _c((str, _NULL), _PROYECTO),
    },
    "traba": {
        "fase": _c(_S, ("inicio", "fin")),
        "tipo": _c(_S, ("repetida", "fallando", "colgada", "quieta")),
        "avisada": _c(_B),
        "segundos": _c((int, _NULL)),
        "fin": _c((str, _NULL), ("prompt", "dejo_de_trabajar", "se_destrabo", "sesion_cerrada")),
    },
    "cierre_frenado": {
        "motivo": _c(_S, ("estado", "otro")),
        "resuelto": _c(_B),
    },
    "error_back": {
        "nivel": _c(_S, ("WARNING", "ERROR", "CRITICAL")),
        "logger": _c(_S, _NOMBRE),
        "plantilla": _c(_S, _PLANTILLA),
        "tipo_exc": _c((str, _NULL), _NOMBRE),
        "n": _c(_I),
        "primera": _c(_S, _FECHA),
        "ultima": _c(_S, _FECHA),
    },
    "app": {
        "origen": _c(_S, ("app", "nudo", "atajos", "guia", "mostrar", "reunion", "tuneles", "notch")),
        "evento": _c(_S, _TOKEN),
        "ok": _c(_B),
        "codigo": _c((str, _NULL), _TOKEN),
        "ms": _c((int, _NULL)),
        "version": _c((str, _NULL), _VERSION),
    },
    "resumen": {
        "semana": _c(_S, _SEMANA),
        "propuestas": _c(_I),
    },
    "propuesta": {
        "regla": _c(_S, _TOKEN),
        "decision": _c(_S, ("hacer", "ignorar", "mas_adelante")),
    },
}


def token(valor: object) -> str:
    return valor if isinstance(valor, str) and TOKEN_RE.match(valor) else "otro"


def _nombre_proyecto(valor: object) -> str | None:
    if not isinstance(valor, str):
        return None
    limpio = redactar(valor)
    return limpio if PROYECTO_RE.match(limpio) else None


def proyecto_de(cwd: object) -> str | None:
    if not isinstance(cwd, str) or not cwd:
        return None
    return _nombre_proyecto(Path(cwd).name)


def _tipo_ok(valor: object, tipos: tuple) -> bool:
    if valor is None:
        return _NULL in tipos
    if isinstance(valor, bool):
        return bool in tipos
    return isinstance(valor, tipos)


def _normalizar(valor: object, marca):
    if valor is None:
        return None
    if marca == _TOKEN:
        return token(valor)
    if marca == _PROYECTO:
        return _nombre_proyecto(valor)
    if isinstance(marca, re.Pattern):
        return valor if marca.match(valor) else "otro"
    if isinstance(marca, tuple):
        return valor if valor in marca else "otro"
    return valor


class Telemetria:
    def __init__(self, directorio: Path, wall: Callable[[], datetime] = lambda: datetime.now().astimezone(),
                 activa: Callable[[], bool] = lambda: True, estricto: bool = False,
                 tope_bytes: int = TOPE_BYTES):
        self.directorio = Path(directorio)
        self._wall = wall
        self._activa = activa
        self._estricto = estricto
        self._tope = tope_bytes
        self._lock = threading.Lock()
        self._errores = Counter()
        self._tope_avisado: str | None = None
        self._ultimo_warning: datetime | None = None

    def archivo_mes(self, cuando: datetime) -> Path:
        return self.directorio / f"{cuando:%Y-%m}.jsonl"

    def anotar_error_interno(self, codigo: str) -> None:
        with self._lock:
            self._errores[codigo] += 1

    def tomar_errores_internos(self) -> dict[str, int]:
        with self._lock:
            tomados, self._errores = dict(self._errores), Counter()
        return tomados

    def anotar(self, ev: str, *, fuente: str = "back", ts: str | None = None, **campos) -> bool:
        try:
            return self._anotar(ev, fuente, ts, campos)
        except Exception as exc:
            if self._estricto and isinstance(exc, AssertionError):
                raise
            self._avisar_fallo(type(exc).__name__)
            return False

    def _anotar(self, ev: str, fuente: str, ts: str | None, campos: dict) -> bool:
        if not self._activa():
            return False
        esquema = ESQUEMA.get(ev)
        if esquema is None:
            return False
        ahora = self._wall()
        if fuente not in ("back", "windows"):
            fuente = "back"
        if not (fuente == "windows" and isinstance(ts, str) and TS_RE.match(ts)):
            ts = ahora.isoformat(timespec="seconds")
        linea = {"v": VERSION, "ts": ts, "ev": ev, "fuente": fuente}
        for nombre, valor in campos.items():
            regla = esquema.get(nombre)
            if regla is None or not _tipo_ok(valor, regla[0]):
                self.anotar_error_interno("telemetria_campo_invalido")
                if self._estricto:
                    raise AssertionError(nombre)
                continue
            linea[nombre] = _normalizar(valor, regla[1])
        datos = (json.dumps(linea, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            ok, fallo = self._escribir(ahora, datos)
        if fallo:
            self._avisar_fallo(fallo, ahora)
        return ok

    def _escribir(self, ahora: datetime, datos: bytes) -> tuple[bool, str | None]:
        try:
            self.directorio.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.archivo_mes(ahora), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                if os.fstat(fd).st_size >= self._tope:
                    mes = f"{ahora:%Y-%m}"
                    if self._tope_avisado != mes:
                        self._tope_avisado = mes
                        self._errores["telemetria_tope"] += 1
                    return False, None
                os.write(fd, datos)
            finally:
                os.close(fd)
            return True, None
        except OSError as exc:
            return False, type(exc).__name__

    def _avisar_fallo(self, tipo: str, ahora: datetime | None = None) -> None:
        try:
            ahora = ahora or self._wall()
            if self._ultimo_warning is None or ahora - self._ultimo_warning >= timedelta(hours=1):
                self._ultimo_warning = ahora
                _LOG.warning("telemetria: no se pudo escribir (%s)", tipo)
        except Exception:
            pass

    def borrar_viejos(self, hoy: date | None = None) -> list[str]:
        hoy = hoy or self._wall().date()
        limite = hoy - timedelta(days=RETENCION_DIAS)
        borrados: list[str] = []
        try:
            archivos = sorted(self.directorio.iterdir())
        except OSError:
            return borrados
        for ruta in archivos:
            m = ARCHIVO_RE.match(ruta.name)
            if not m:
                continue
            anio, mes = int(m.group(1)), int(m.group(2))
            if not 1 <= mes <= 12:
                continue
            ultimo = (date(anio + (mes == 12), mes % 12 + 1, 1)) - timedelta(days=1)
            if ultimo < limite:
                try:
                    ruta.unlink()
                    borrados.append(ruta.name)
                except OSError:
                    pass
        return borrados


_RUTA = re.compile(r"(?<![\w])/[^\s'\"]+")
_TEXTO = re.compile(r"'[^']*'|\"[^\"]*\"")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_HEX = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_NUMERO = re.compile(r"\d+")
_SUELTO = re.compile(r"[/\x00-\x1f\x7f]")
_ESPACIOS = re.compile(r"\s+")
_LARGO_PLANTILLA = 120


def normalizar_plantilla(msg: str) -> str:
    """Deja solo la forma del mensaje: sin rutas, textos entre comillas, ids ni números."""
    msg = _RUTA.sub("<ruta>", msg)
    msg = _TEXTO.sub("<txt>", msg)
    msg = _UUID.sub("<id>", msg)
    msg = _HEX.sub("<id>", msg)
    msg = _NUMERO.sub("0", msg)
    msg = redactar(msg)
    msg = _SUELTO.sub(" ", msg)
    return _ESPACIOS.sub(" ", msg).strip()[:_LARGO_PLANTILLA]


class TelemetriaHandler(logging.Handler):
    """Cuenta warnings y errores del back por hora y escribe una línea por clave al cerrar el tramo."""

    def __init__(self, telemetria: Telemetria):
        super().__init__(level=logging.WARNING)
        self._tel = telemetria
        self._tramo: dict[tuple, list] = {}
        self._hora: datetime | None = None
        self._cerrojo = threading.RLock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith("orquestador.telemetria"):
                return
            exc = record.exc_info[1] if record.exc_info else None
            clave = (record.levelname, record.name, normalizar_plantilla(str(record.msg)),
                     type(exc).__name__ if exc is not None else None)
            cuando = datetime.fromtimestamp(record.created).astimezone()
            hora = cuando.replace(minute=0, second=0, microsecond=0)
            ts = cuando.isoformat(timespec="seconds")
            with self._cerrojo:
                if self._hora is not None and hora != self._hora:
                    self._volcar()
                self._hora = hora
                dato = self._tramo.get(clave)
                if dato is None:
                    self._tramo[clave] = [1, ts, ts]
                else:
                    dato[0] += 1
                    dato[2] = ts
        except Exception:
            pass

    def flush(self) -> None:
        try:
            with self._cerrojo:
                self._volcar()
        except Exception:
            pass

    def _volcar(self) -> None:
        tramo, self._tramo, self._hora = self._tramo, {}, None
        for (nivel, logger, plantilla, tipo_exc), (n, primera, ultima) in tramo.items():
            self._tel.anotar("error_back", nivel=nivel, logger=logger, plantilla=plantilla,
                             tipo_exc=tipo_exc, n=n, primera=primera, ultima=ultima)
        ahora = self._tel._wall().isoformat(timespec="seconds")
        for codigo, n in self._tel.tomar_errores_internos().items():
            self._tel.anotar("error_back", nivel="WARNING", logger="orquestador.telemetria",
                             plantilla=codigo, tipo_exc=None, n=n, primera=ahora, ultima=ahora)
