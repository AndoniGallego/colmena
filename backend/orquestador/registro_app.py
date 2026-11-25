"""Registro de errores de la app de Windows: guarda las líneas que manda en la notebook. Sin lectura por la API."""
import logging
import os
import re
import threading
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Callable, Mapping, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, conint, constr, model_validator

from .telemetria import Telemetria

log = logging.getLogger(__name__)

LINEA_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3} (info|aviso|error) (app|nudo|atajos|guia|reunion|tuneles|notch) \S.*$")
LINEA_MAX = 600
DIAS_GUARDADO = 7
_ARCHIVO_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.log$")
SH = {"Cache-Control": "no-store"}


def carpeta_registro_app(env: Mapping[str, str]) -> Path:
    base = env.get("XDG_DATA_HOME") or str(Path(env["HOME"]) / ".local/share")
    return Path(base) / "orquestador" / "registro-app"


def limpiar_linea(s: str) -> Optional[str]:
    s = "".join(" " if unicodedata.category(c) == "Cc" or c in "  " else c for c in s)
    s = s.strip()[:LINEA_MAX]
    return s if LINEA_RE.match(s) else None


class RegistroApp:
    def __init__(self, carpeta: Path, hoy: Callable[[], date] = date.today):
        self.carpeta = carpeta
        self._hoy = hoy
        self._lock = threading.Lock()
        self._limpiado: Optional[date] = None

    def agregar(self, lineas: list) -> tuple:
        validas = [l for l in (limpiar_linea(x) for x in lineas) if l]
        if validas:
            with self._lock:
                self._escribir(validas)
        return len(validas), len(lineas) - len(validas)

    def _escribir(self, validas: list) -> None:
        self.carpeta.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.carpeta, 0o700)
        self._limpiar_si_cambio_el_dia()
        ruta = self.carpeta / f"{self._hoy().isoformat()}.log"
        fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, ("\n".join(validas) + "\n").encode("utf-8"))
        finally:
            os.close(fd)

    def limpiar_viejos(self) -> None:
        hoy = self._hoy()
        limite = hoy - timedelta(days=DIAS_GUARDADO)
        try:
            archivos = list(self.carpeta.iterdir())
        except OSError:
            return
        for p in archivos:
            m = _ARCHIVO_RE.match(p.name)
            if not m:
                continue
            try:
                if date.fromisoformat(m.group(1)) < limite:
                    p.unlink()
            except (ValueError, OSError):
                log.warning("No se pudo borrar el registro viejo %s", p.name)
        self._limpiado = hoy

    def _limpiar_si_cambio_el_dia(self) -> None:
        if self._limpiado != self._hoy():
            self.limpiar_viejos()


class EventoAppBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ts: constr(max_length=40)
    origen: str = Field(max_length=40)
    evento: constr(max_length=40)
    ok: bool
    codigo: Optional[constr(max_length=40)] = None
    ms: Optional[conint(ge=0, le=86_400_000)] = None
    version: Optional[constr(max_length=20)] = None


class RegistroBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lineas: Optional[list[Annotated[str, Field(max_length=2000)]]] = None
    eventos: Optional[list[EventoAppBody]] = None

    @model_validator(mode="after")
    def _total(self):
        total = len(self.lineas or []) + len(self.eventos or [])
        if not 1 <= total <= 200:
            raise ValueError("entre 1 y 200 ítems entre lineas y eventos")
        return self


def build_router(registro: RegistroApp, telemetria: Optional[Telemetria] = None) -> APIRouter:
    router = APIRouter()

    @router.post("/registro/app")
    def post_registro(body: RegistroBody):
        guardadas, descartadas = registro.agregar(body.lineas or [])
        respuesta = {"ok": True, "guardadas": guardadas, "descartadas": descartadas}
        if body.eventos is not None:
            escritos = 0
            for ev in body.eventos:
                if telemetria is not None and telemetria.anotar(
                        "app", fuente="windows", ts=ev.ts, origen=ev.origen, evento=ev.evento, ok=ev.ok,
                        codigo=ev.codigo, ms=ev.ms, version=ev.version):
                    escritos += 1
            respuesta["eventos"] = escritos
        return respuesta

    return router
