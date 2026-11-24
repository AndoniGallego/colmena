from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from orquestador.enchufe.ids import es_guardian

log = logging.getLogger(__name__)

VERSION = 1
# Modo endurecido por conversación de Claude: sobrevive a retomarla o mudarla a otra sesión.
MAX_MODOS_CLAUDE = 500


@dataclass
class EspacioRegistrado:
    id: str
    nombre: str
    cwd: str
    numero: int


@dataclass
class LineaRegistrada:
    id: str
    espacio_id: str
    nombre: str


@dataclass
class SesionRegistrada:
    id: str
    linea_id: str
    espacio_id: str
    nombre: str
    cwd: str
    programa: str
    claude_session_id: str | None
    creada: float
    ultima_vez_viva: float | None
    modo_permisos: str | None = None
    dirs_extra: list[str] = field(default_factory=list)


def _modo_permisos(valor: object) -> str | None:
    """Modo por lanzamiento guardado; uno desconocido cae al más estricto, nunca al global."""
    from .lanzador import MODOS_INTERNOS, MODOS_POR_LANZAMIENTO

    if valor is None:
        return None
    # `copiloto` se conserva solo acá: la reanudación; el núcleo lo revalida contra su carpeta.
    return valor if valor in MODOS_POR_LANZAMIENTO | MODOS_INTERNOS else "default"


def _numero_espacio(espacio_id: str) -> int:
    return int(espacio_id[1:])


def _prefijo_espacio(espacio_id: str) -> str:
    return espacio_id.split(":", 1)[0]


class Registro:
    def __init__(self, ruta: Path, reloj: Callable[[], float] = time.time) -> None:
        self.ruta = ruta
        self._reloj = reloj
        self.contador = 0
        self.espacios: dict[str, EspacioRegistrado] = {}
        self.lineas: dict[str, LineaRegistrada] = {}
        self.sesiones: dict[str, SesionRegistrada] = {}
        self.modos_claude: dict[str, str] = {}

    def cargar(self) -> None:
        self.contador = 0
        self.espacios = {}
        self.lineas = {}
        self.sesiones = {}
        self.modos_claude = {}
        if not self.ruta.exists():
            return
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            log.warning("registro corrupto en %s", self.ruta)
            roto = self.ruta.with_name(f"{self.ruta.name}.roto-{int(self._reloj())}")
            try:
                self.ruta.rename(roto)
            except OSError:
                pass
            return
        if not isinstance(datos, dict):
            log.warning("registro corrupto en %s", self.ruta)
            return
        self.contador = int(datos.get("contador") or 0)
        modos = datos.get("modos_claude")
        if isinstance(modos, dict):
            for csid, valor in list(modos.items())[-MAX_MODOS_CLAUDE:]:
                if isinstance(csid, str) and 0 < len(csid) <= 200:
                    self.modos_claude[csid] = _modo_permisos(valor) or "default"
        for raw in datos.get("espacios") or []:
            if not isinstance(raw, dict):
                continue
            eid = raw.get("id")
            if not es_guardian(eid) or ":" in eid:
                continue
            try:
                esp = EspacioRegistrado(
                    id=eid,
                    nombre=str(raw.get("nombre") or ""),
                    cwd=str(raw.get("cwd") or ""),
                    numero=int(raw.get("numero", _numero_espacio(eid))),
                )
            except (TypeError, ValueError):
                continue
            self.espacios[esp.id] = esp
        for raw in datos.get("lineas") or []:
            if not isinstance(raw, dict):
                continue
            lid = raw.get("id")
            espacio_id = raw.get("espacio_id")
            if not es_guardian(lid) or not es_guardian(espacio_id):
                continue
            if espacio_id not in self.espacios:
                continue
            self.lineas[lid] = LineaRegistrada(
                id=lid,
                espacio_id=espacio_id,
                nombre=str(raw.get("nombre") or ""),
            )
        for raw in datos.get("sesiones") or []:
            if not isinstance(raw, dict):
                continue
            sid = raw.get("id")
            linea_id = raw.get("linea_id")
            espacio_id = raw.get("espacio_id")
            if not es_guardian(sid) or not es_guardian(linea_id):
                continue
            if linea_id not in self.lineas or espacio_id not in self.espacios:
                continue
            if self.lineas[linea_id].espacio_id != espacio_id:
                continue
            try:
                ses = SesionRegistrada(
                    id=sid,
                    linea_id=linea_id,
                    espacio_id=espacio_id,
                    nombre=str(raw.get("nombre") or ""),
                    cwd=str(raw.get("cwd") or ""),
                    programa=str(raw.get("programa") or ""),
                    claude_session_id=raw.get("claude_session_id"),
                    creada=float(raw.get("creada") or 0),
                    ultima_vez_viva=raw.get("ultima_vez_viva"),
                    modo_permisos=_modo_permisos(raw.get("modo_permisos")),
                    dirs_extra=[d for d in (raw.get("dirs_extra") or []) if isinstance(d, str)]
                    if isinstance(raw.get("dirs_extra") or [], list) else [],
                )
            except (TypeError, ValueError):
                continue
            if ses.ultima_vez_viva is not None:
                ses.ultima_vez_viva = float(ses.ultima_vez_viva)
            self.sesiones[sid] = ses
        ids = [*self.espacios, *self.lineas, *self.sesiones]
        self.contador = max([self.contador, *(int(i.rsplit(":", 1)[-1].lstrip("gpt")) for i in ids)])

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        cuerpo = json.dumps(
            {
                "version": VERSION,
                "contador": self.contador,
                "espacios": [asdict(e) for e in self.espacios.values()],
                "lineas": [asdict(l) for l in self.lineas.values()],
                "sesiones": [asdict(s) for s in self.sesiones.values()],
                "modos_claude": self.modos_claude,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        tmp = self.ruta.with_name(f"{self.ruta.name}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600)
            os.write(fd, cuerpo)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, self.ruta)

    def _siguiente_id(self) -> int:
        self.contador += 1
        return self.contador

    def nuevo_espacio(self, nombre: str, cwd: str) -> EspacioRegistrado:
        n = self._siguiente_id()
        esp = EspacioRegistrado(id=f"g{n}", nombre=nombre, cwd=cwd, numero=n)
        self.espacios[esp.id] = esp
        self.guardar()
        return esp

    def nueva_linea(self, espacio_id: str, nombre: str) -> LineaRegistrada:
        if espacio_id not in self.espacios:
            raise KeyError(espacio_id)
        n = self._siguiente_id()
        prefijo = _prefijo_espacio(espacio_id)
        linea = LineaRegistrada(id=f"{prefijo}:t{n}", espacio_id=espacio_id, nombre=nombre)
        self.lineas[linea.id] = linea
        self.guardar()
        return linea

    def nueva_sesion(
        self,
        linea_id: str,
        nombre: str,
        cwd: str,
        programa: str,
        claude_session_id: str | None,
    ) -> SesionRegistrada:
        if linea_id not in self.lineas:
            raise KeyError(linea_id)
        linea = self.lineas[linea_id]
        n = self._siguiente_id()
        prefijo = _prefijo_espacio(linea.espacio_id)
        ahora = self._reloj()
        ses = SesionRegistrada(
            id=f"{prefijo}:p{n}",
            linea_id=linea_id,
            espacio_id=linea.espacio_id,
            nombre=nombre,
            cwd=cwd,
            programa=programa,
            claude_session_id=claude_session_id,
            creada=ahora,
            ultima_vez_viva=None,
        )
        self.sesiones[ses.id] = ses
        self.guardar()
        return ses

    def modo_de_claude(self, claude_session_id: str | None) -> str | None:
        return self.modos_claude.get(claude_session_id) if claude_session_id else None

    def recordar_modo_claude(self, claude_session_id: str | None, modo: str | None) -> None:
        if not claude_session_id or modo is None:
            return
        modo = _modo_permisos(modo)
        if self.modos_claude.get(claude_session_id) == modo:
            return
        self.modos_claude.pop(claude_session_id, None)
        self.modos_claude[claude_session_id] = modo
        while len(self.modos_claude) > MAX_MODOS_CLAUDE:
            del self.modos_claude[next(iter(self.modos_claude))]
        self.guardar()

    def actualizar_sesion(self, id: str, **campos) -> None:
        if id not in self.sesiones:
            raise KeyError(id)
        ses = self.sesiones[id]
        for clave, valor in campos.items():
            if not hasattr(ses, clave):
                raise AttributeError(clave)
            setattr(ses, clave, valor)
        self.guardar()

    def quitar_sesion(self, id: str) -> None:
        if id in self.sesiones:
            del self.sesiones[id]
            self.guardar()

    def quitar_linea(self, id: str) -> None:
        if id not in self.lineas:
            return
        for sid in [s for s, ses in self.sesiones.items() if ses.linea_id == id]:
            del self.sesiones[sid]
        del self.lineas[id]
        self.guardar()

    def quitar_espacio(self, id: str) -> None:
        if id not in self.espacios:
            return
        for lid in [l for l, lin in self.lineas.items() if lin.espacio_id == id]:
            for sid in [s for s, ses in self.sesiones.items() if ses.linea_id == lid]:
                del self.sesiones[sid]
            del self.lineas[lid]
        del self.espacios[id]
        self.guardar()

    def renombrar(self, objetivo_id: str, nombre: str) -> None:
        if objetivo_id in self.espacios:
            self.espacios[objetivo_id].nombre = nombre
            self.guardar()
            return
        if objetivo_id in self.lineas:
            self.lineas[objetivo_id].nombre = nombre
            self.guardar()
            return
        raise KeyError(objetivo_id)
