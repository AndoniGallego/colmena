from __future__ import annotations

import asyncio
import codecs
import logging
import os
import re
import signal
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orquestador.enchufe.base import TECLAS
from orquestador.enchufe.ids import es_guardian, tipo_de_id
from orquestador.guardian.lanzador import (
    MODOS_POR_LANZAMIENTO,
    AjustesGuardian,
    argv_claude,
    argv_shell,
    entorno_hijo,
)
from orquestador.guardian.pantalla import Pantalla
from orquestador.guardian.proceso import ProcesoPty
from orquestador.guardian.protocolo import INVALIDO, NO_DISPONIBLE, NO_EXISTE, ErrorProtocolo
from orquestador.guardian.registro import Registro, SesionRegistrada

log = logging.getLogger(__name__)

_TOPE_TEXTO = 256 * 1024
_NOMBRE_MAX = 80
_CTRL = re.compile(r"[\x00-\x1f\x7f]")

_TECLA_BYTES: dict[str, bytes] = {
    "esc": b"\x1b",
    "enter": b"\r",
    "arriba": b"\x1b[A",
    "derecha": b"\x1b[C",
    "ctrl-c": b"\x03",
    "ctrl-e": b"\x05",
    "ctrl-u": b"\x15",
    **{str(d): str(d).encode() for d in range(1, 10)},
}


@dataclass
class Escucha:
    _cb: Callable[[dict], None] = field(repr=False)
    salida: set[str] = field(default_factory=set)
    _cerrada: bool = field(default=False, repr=False)

    def cerrar(self) -> None:
        self._cerrada = True


@dataclass
class _RuntimeSesion:
    registro: SesionRegistrada
    pantalla: Pantalla
    proceso: ProcesoPty | None = None
    estado: str = "idle"
    codigo: int | None = None
    arranque: float = 0.0
    confianza_hecha: bool = False
    confianza_detectada: float | None = None
    listo: asyncio.Event = field(default_factory=asyncio.Event)
    tareas: list[asyncio.Task[Any]] = field(default_factory=list)
    decoder_salida: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")(errors="replace")
    )
    pgid_anterior: int | None = None
    con_resume: bool = False
    titulo_anterior: str = ""


class Guardian:
    def __init__(
        self,
        registro: Registro,
        ajustes: AjustesGuardian,
        settings: Path,
        *,
        entorno: Mapping[str, str],
        cwd_confiable: Callable[[str], bool],
        espera_listo: float = 30.0,
        ventana_confianza: float = 15.0,
        demora_confianza: float = 2.0,
        vida_minima: float = 5.0,
        historial: int = 5000,
        reloj: Callable[[], float] | None = None,
    ) -> None:
        self._registro = registro
        self._ajustes = ajustes
        self._settings = settings
        self._entorno = dict(entorno)
        self._cwd_confiable = cwd_confiable
        self._espera_listo = espera_listo
        self._ventana_confianza = ventana_confianza
        self._demora_confianza = demora_confianza
        self._vida_minima = vida_minima
        self._historial = historial
        self._reloj = reloj or time.monotonic
        self._sesiones: dict[str, _RuntimeSesion] = {}
        self._escuchas: list[Escucha] = []
        self._seq = 0
        self._revision = 0

    @property
    def seq(self) -> int:
        return self._seq

    def escuchar(
        self, cb: Callable[[dict], None], salida: Iterable[str] = ()
    ) -> Escucha:
        esc = Escucha(_cb=cb, salida=set(salida))
        self._escuchas.append(esc)
        return esc

    def _emitir(self, evento: dict, *, es_salida: bool = False) -> None:
        self._seq += 1
        evento = {**evento, "seq": self._seq}
        if not es_salida:
            self._revision += 1
        self._escuchas = [e for e in self._escuchas if not e._cerrada]
        for esc in list(self._escuchas):
            if es_salida:
                sid = evento.get("sesion")
                if sid not in esc.salida:
                    continue
            try:
                esc._cb(evento)
            except Exception:
                log.exception("callback de escucha falló")

    def _emitir_tablero(self) -> None:
        self._emitir({"evento": "tablero"})

    def _validar_id(self, objetivo_id: str, tipo: str | None = None) -> None:
        if not es_guardian(objetivo_id):
            raise ErrorProtocolo(NO_EXISTE, objetivo_id)
        if tipo is not None and tipo_de_id(objetivo_id) != tipo:
            raise ErrorProtocolo(NO_EXISTE, objetivo_id)

    def _runtime(self, sesion_id: str) -> _RuntimeSesion:
        self._validar_id(sesion_id, "sesion")
        rt = self._sesiones.get(sesion_id)
        if rt is None:
            raise ErrorProtocolo(NO_EXISTE, sesion_id)
        return rt

    @staticmethod
    def _normalizar_nombre(nombre: str) -> str:
        limpio = _CTRL.sub(" ", nombre).strip()
        if not limpio:
            raise ErrorProtocolo(INVALIDO, "nombre vacío")
        return limpio[:_NOMBRE_MAX]

    @staticmethod
    def _validar_cwd(cwd: str) -> str:
        if not cwd or not os.path.isabs(cwd) or _CTRL.search(cwd):
            raise ErrorProtocolo(INVALIDO, "cwd inválido")
        if not os.path.isdir(cwd):
            raise ErrorProtocolo(INVALIDO, "cwd inexistente")
        return cwd

    def _nueva_runtime(self, ses: SesionRegistrada, *, estado: str = "idle") -> _RuntimeSesion:
        rt = _RuntimeSesion(
            registro=ses,
            pantalla=Pantalla(self._ajustes.columnas, self._ajustes.filas, self._historial),
            estado=estado,
        )
        self._sesiones[ses.id] = rt
        return rt

    def _cancelar_tareas(self, rt: _RuntimeSesion) -> None:
        for t in rt.tareas:
            t.cancel()
        rt.tareas.clear()

    async def retomar(self) -> None:
        self._registro.cargar()
        self._sesiones.clear()
        for ses in self._registro.sesiones.values():
            if not os.path.isdir(ses.cwd):
                self._nueva_runtime(ses, estado="perdida")
                continue
            rt = self._nueva_runtime(ses)
            try:
                if ses.programa == "claude" and ses.claude_session_id:
                    await self._lanzar_claude(rt, resume=ses.claude_session_id)
                elif ses.programa == "shell":
                    await self._lanzar_shell(rt)
                else:
                    rt.estado = "perdida"
            except ErrorProtocolo:
                rt.estado = "perdida"
        self._emitir_tablero()

    def tablero(self) -> dict:
        espacios = []
        for esp in sorted(self._registro.espacios.values(), key=lambda e: e.numero):
            lineas_ids = [l.id for l in self._registro.lineas.values() if l.espacio_id == esp.id]
            espacios.append(
                {
                    "id": esp.id,
                    "nombre": esp.nombre,
                    "numero": esp.numero,
                    "cwd": esp.cwd,
                    "lineas": lineas_ids,
                }
            )
        lineas = []
        for lin in self._registro.lineas.values():
            sids = [s.id for s in self._registro.sesiones.values() if s.linea_id == lin.id]
            lineas.append(
                {
                    "id": lin.id,
                    "espacio_id": lin.espacio_id,
                    "nombre": lin.nombre,
                    "sesiones": sids,
                }
            )
        sesiones = []
        for ses in self._registro.sesiones.values():
            rt = self._sesiones.get(ses.id)
            estado = rt.estado if rt else "terminada"
            codigo = rt.codigo if rt else None
            titulo = rt.pantalla.titulo if rt else ""
            pid = None
            cwd_fp = None
            if rt and rt.proceso and rt.proceso.vivo:
                pid = rt.proceso.pid
                fp = rt.proceso.primer_plano()
                if fp.get("pid"):
                    pid = fp["pid"]
                cwd_fp = fp.get("cwd")
            sesiones.append(
                {
                    "id": ses.id,
                    "linea_id": ses.linea_id,
                    "espacio_id": ses.espacio_id,
                    "nombre": ses.nombre,
                    "programa": ses.programa,
                    "estado": estado,
                    "claude_session_id": ses.claude_session_id,
                    "cwd": ses.cwd,
                    "cwd_primer_plano": cwd_fp,
                    "titulo": titulo,
                    "pid": pid,
                    "codigo": codigo,
                    "listo": rt.listo.is_set() if rt else False,
                }
            )
        return {"revision": self._revision, "espacios": espacios, "lineas": lineas, "sesiones": sesiones}

    async def crear_espacio(self, nombre: str, cwd: str) -> dict:
        nombre = self._normalizar_nombre(nombre)
        cwd = self._validar_cwd(cwd)
        esp = self._registro.nuevo_espacio(nombre, cwd)
        lin = self._registro.nueva_linea(esp.id, nombre)
        ses = self._registro.nueva_sesion(lin.id, nombre, cwd, "shell", None)
        rt = self._nueva_runtime(ses)
        await self._lanzar_shell(rt)
        self._emitir_tablero()
        return {"espacio_id": esp.id, "linea_id": lin.id, "sesion_id": ses.id}

    async def crear_linea(
        self,
        espacio_id: str,
        nombre: str,
        cwd: str,
        programa: str = "shell",
        resume: str | None = None,
    ) -> dict:
        self._validar_id(espacio_id, "espacio")
        if espacio_id not in self._registro.espacios:
            raise ErrorProtocolo(NO_EXISTE, espacio_id)
        nombre = self._normalizar_nombre(nombre)
        cwd = self._validar_cwd(cwd)
        if programa not in ("shell", "claude"):
            raise ErrorProtocolo(INVALIDO, "programa inválido")
        lin = self._registro.nueva_linea(espacio_id, nombre)
        if programa == "shell":
            ses = self._registro.nueva_sesion(lin.id, nombre, cwd, "shell", None)
            rt = self._nueva_runtime(ses)
            await self._lanzar_shell(rt)
            sid = ses.id
        else:
            uid = resume or str(uuid.uuid4())
            if resume:
                try:
                    uuid.UUID(resume)
                except ValueError as exc:
                    raise ErrorProtocolo(INVALIDO, "resume inválido") from exc
            ses = self._registro.nueva_sesion(lin.id, nombre, cwd, "claude", uid)
            rt = self._nueva_runtime(ses)
            await self._lanzar_claude(rt, session_id=uid if not resume else None, resume=resume)
            sid = ses.id
        self._emitir_tablero()
        return {"linea_id": lin.id, "sesion_id": sid}

    async def _lanzar_shell(self, rt: _RuntimeSesion) -> None:
        await self._lanzar(rt, argv_shell(self._ajustes, self._entorno), con_resume=False)

    async def _lanzar_claude(
        self,
        rt: _RuntimeSesion,
        *,
        session_id: str | None = None,
        resume: str | None = None,
    ) -> None:
        csid = session_id or resume
        # Una conversación que nació endurecida sigue así aunque se retome o se mude a otra sesión.
        modo = rt.registro.modo_permisos
        if modo is None and resume:
            modo = self._registro.modo_de_claude(resume)
        self._registro.actualizar_sesion(
            rt.registro.id, programa="claude", claude_session_id=csid, modo_permisos=modo
        )
        self._registro.recordar_modo_claude(csid, modo)
        rt.registro = self._registro.sesiones[rt.registro.id]
        argv = argv_claude(
            self._ajustes,
            self._settings,
            session_id=session_id,
            resume=resume,
            modo=rt.registro.modo_permisos,
        )
        rt.pantalla = Pantalla(self._ajustes.columnas, self._ajustes.filas, self._historial)
        await self._lanzar(rt, argv, con_resume=resume is not None)

    async def _lanzar(self, rt: _RuntimeSesion, argv: list[str], *, con_resume: bool) -> None:
        ses = rt.registro
        self._cancelar_tareas(rt)
        rt.estado = "idle"
        rt.codigo = None
        rt.con_resume = con_resume
        rt.confianza_hecha = False
        rt.confianza_detectada = None
        rt.listo = asyncio.Event()
        rt.decoder_salida.reset()
        rt.pgid_anterior = None
        rt.titulo_anterior = ""
        rt.arranque = self._reloj()
        try:
            rt.proceso = await ProcesoPty.lanzar(
                argv,
                ses.cwd,
                entorno_hijo(self._entorno, ses.id, self._ajustes),
                self._ajustes.columnas,
                self._ajustes.filas,
                lambda d, r=rt: self._al_leer(r, d),
                lambda c, r=rt: self._al_salir(r, c),
            )
        except OSError as exc:
            rt.proceso = None
            rt.estado = "perdida" if con_resume else "terminada"
            log.warning("no se pudo lanzar la sesión %s: %s", ses.id, type(exc).__name__)
            raise ErrorProtocolo(NO_DISPONIBLE, "no se pudo lanzar el programa") from exc

    async def arrancar_claude(
        self, sesion_id: str, nombre: str, resume: str | None = None, modo: str | None = None
    ) -> dict:
        if modo is not None and modo not in MODOS_POR_LANZAMIENTO:
            raise ErrorProtocolo(INVALIDO, "modo inválido")
        rt = self._runtime(sesion_id)
        ses = rt.registro
        if (
            rt.proceso
            and rt.proceso.vivo
            and ses.programa == "claude"
            and rt.estado not in ("terminada", "perdida")
        ):
            raise ErrorProtocolo(INVALIDO, "claude ya corre")
        nombre = self._normalizar_nombre(nombre)
        uid = resume or str(uuid.uuid4())
        if rt.proceso and rt.proceso.vivo:
            await rt.proceso.terminar(((signal.SIGHUP, 1.0), (signal.SIGTERM, 1.0)))
        # Un modo endurecido no se pierde: arrancar sin modo conserva el que la sesión ya tenía.
        modo_efectivo = modo if modo is not None else ses.modo_permisos
        self._registro.actualizar_sesion(
            ses.id,
            nombre=nombre,
            programa="claude",
            claude_session_id=uid,
            modo_permisos=modo_efectivo,
        )
        rt.registro = self._registro.sesiones[ses.id]
        if resume:
            await self._lanzar_claude(rt, resume=resume)
        else:
            await self._lanzar_claude(rt, session_id=uid)
        try:
            await asyncio.wait_for(rt.listo.wait(), self._espera_listo)
        except asyncio.TimeoutError:
            pass
        return {"estado": rt.estado, "listo": rt.listo.is_set(), "modo": rt.registro.modo_permisos}

    def renombrar(self, objetivo_id: str, nombre: str) -> None:
        if not es_guardian(objetivo_id):
            raise ErrorProtocolo(NO_EXISTE, objetivo_id)
        nombre = self._normalizar_nombre(nombre)
        try:
            self._registro.renombrar(objetivo_id, nombre)
        except KeyError as exc:
            raise ErrorProtocolo(NO_EXISTE, objetivo_id) from exc
        self._emitir_tablero()

    async def cerrar(self, objetivo_id: str) -> None:
        if not es_guardian(objetivo_id):
            raise ErrorProtocolo(NO_EXISTE, objetivo_id)
        tipo = tipo_de_id(objetivo_id)
        if tipo == "sesion":
            if objetivo_id not in self._registro.sesiones:
                raise ErrorProtocolo(NO_EXISTE, objetivo_id)
            ses = self._registro.sesiones[objetivo_id]
            await self._cerrar_linea(ses.linea_id)
            return
        if tipo == "linea":
            if objetivo_id not in self._registro.lineas:
                raise ErrorProtocolo(NO_EXISTE, objetivo_id)
            await self._cerrar_linea(objetivo_id)
            return
        if tipo == "espacio":
            if objetivo_id not in self._registro.espacios:
                raise ErrorProtocolo(NO_EXISTE, objetivo_id)
            for lid in [
                l.id for l in self._registro.lineas.values() if l.espacio_id == objetivo_id
            ]:
                await self._cerrar_linea(lid)
            self._registro.quitar_espacio(objetivo_id)
            self._emitir_tablero()
            return
        raise ErrorProtocolo(NO_EXISTE, objetivo_id)

    async def _cerrar_linea(self, linea_id: str) -> None:
        sids = [s.id for s in self._registro.sesiones.values() if s.linea_id == linea_id]
        for sid in sids:
            rt = self._sesiones.get(sid)
            if rt:
                self._cancelar_tareas(rt)
                if rt.proceso and rt.proceso.vivo:
                    await rt.proceso.terminar()
                del self._sesiones[sid]
        self._registro.quitar_linea(linea_id)
        self._emitir_tablero()

    def leer(
        self,
        sesion_id: str,
        fuente: str = "visible",
        formato: str = "texto",
        lineas: int | None = None,
    ) -> str:
        rt = self._runtime(sesion_id)
        if fuente == "visible":
            if formato == "ansi":
                return rt.pantalla.ansi()
            if formato != "texto":
                raise ErrorProtocolo(INVALIDO, "formato inválido")
            return "\n".join(rt.pantalla.visible())
        if fuente == "reciente":
            if formato == "ansi":
                hist = rt.pantalla.reciente(lineas)
                vis = rt.pantalla.ansi()
                unido = f"{hist}\n{vis}" if hist else vis
                if lineas is not None:
                    partes = unido.split("\n")
                    unido = "\n".join(partes[-lineas:])
                return unido
            if formato != "texto":
                raise ErrorProtocolo(INVALIDO, "formato inválido")
            return rt.pantalla.reciente(lineas)
        if fuente == "deteccion":
            if formato != "texto":
                raise ErrorProtocolo(INVALIDO, "formato inválido")
            return rt.pantalla.deteccion()
        raise ErrorProtocolo(INVALIDO, "fuente inválida")

    def foto(self, sesion_id: str) -> dict:
        rt = self._runtime(sesion_id)
        return rt.pantalla.foto()

    def _exigir_vivo(self, rt: _RuntimeSesion) -> ProcesoPty:
        if not rt.proceso or not rt.proceso.vivo:
            raise ErrorProtocolo(NO_DISPONIBLE, "sesión no disponible")
        return rt.proceso

    def _exigir_texto(self, texto: str) -> None:
        if len(texto.encode("utf-8")) > _TOPE_TEXTO:
            raise ErrorProtocolo(INVALIDO, "texto demasiado grande")

    def escribir(self, sesion_id: str, texto: str) -> None:
        self._exigir_texto(texto)
        proc = self._exigir_vivo(self._runtime(sesion_id))
        proc.escribir(texto.encode("utf-8"))

    def teclas(self, sesion_id: str, teclas: Sequence[str]) -> None:
        if not teclas:
            raise ErrorProtocolo(INVALIDO, "sin teclas")
        for t in teclas:
            if t not in TECLAS:
                raise ErrorProtocolo(INVALIDO, f"tecla inválida: {t}")
        proc = self._exigir_vivo(self._runtime(sesion_id))
        datos = b"".join(_TECLA_BYTES[t] for t in teclas)
        proc.escribir(datos)

    async def mandar_prompt(self, sesion_id: str, texto: str) -> None:
        self._exigir_texto(texto)
        proc = self._exigir_vivo(self._runtime(sesion_id))
        proc.escribir(texto.encode("utf-8"))
        await asyncio.sleep(0.5)
        proc.escribir(b"\r")

    def interrumpir(self, sesion_id: str) -> None:
        proc = self._exigir_vivo(self._runtime(sesion_id))
        proc.escribir(b"\x1b")

    def ejecutar(self, sesion_id: str, comando: str) -> None:
        self._exigir_texto(comando)
        proc = self._exigir_vivo(self._runtime(sesion_id))
        proc.escribir(comando.encode("utf-8") + b"\r")

    def proceso(self, sesion_id: str) -> dict:
        rt = self._runtime(sesion_id)
        fp = rt.proceso.primer_plano() if rt.proceso else {}
        shell_pid = rt.proceso.pid if rt.proceso else None
        grupo = rt.proceso.grupo if rt.proceso else None
        vivo = bool(rt.proceso and rt.proceso.vivo)
        es_claude = rt.registro.programa == "claude" and vivo
        return {
            "pid": fp.get("pid"),
            "comando": fp.get("comando"),
            "cwd": fp.get("cwd"),
            "es_claude": es_claude,
            "grupo": grupo,
            "shell_pid": shell_pid,
            "argv": fp.get("argv"),
        }

    def redimensionar(self, sesion_id: str, columnas: int, filas: int) -> None:
        if not (20 <= columnas <= 500 and 5 <= filas <= 200):
            raise ErrorProtocolo(INVALIDO, "tamaño inválido")
        rt = self._runtime(sesion_id)
        if rt.proceso and rt.proceso.vivo:
            rt.proceso.redimensionar(columnas, filas)
        rt.pantalla.redimensionar(columnas, filas)

    def _al_leer(self, rt: _RuntimeSesion, datos: bytes) -> None:
        rt.pantalla.alimentar(datos)
        self._chequear_titulo(rt)
        self._chequear_proceso(rt)
        self._manejar_confianza(rt)
        self._chequear_listo(rt)
        if any(not e._cerrada and rt.registro.id in e.salida for e in self._escuchas):
            texto = rt.decoder_salida.decode(datos)
            if texto:
                self._emitir(
                    {"evento": "salida", "sesion": rt.registro.id, "texto": texto},
                    es_salida=True,
                )

    def _chequear_titulo(self, rt: _RuntimeSesion) -> None:
        titulo = rt.pantalla.titulo
        if titulo != rt.titulo_anterior:
            rt.titulo_anterior = titulo
            self._emitir({"evento": "titulo", "sesion": rt.registro.id, "titulo": titulo})

    def _chequear_proceso(self, rt: _RuntimeSesion) -> None:
        if not rt.proceso or not rt.proceso.vivo:
            return
        pgid = rt.proceso.grupo_primer_plano()
        if pgid is None:
            return
        if pgid != rt.pgid_anterior:
            rt.pgid_anterior = pgid
            fp = rt.proceso.primer_plano()
            self._emitir(
                {
                    "evento": "proceso",
                    "sesion": rt.registro.id,
                    "pid": pgid,
                    "comando": fp.get("comando"),
                }
            )

    def _chequear_listo(self, rt: _RuntimeSesion) -> None:
        if rt.pantalla.tiene_prompt() and not rt.pantalla.dialogo_confianza():
            avisar = not rt.listo.is_set()
            rt.listo.set()
            if rt.estado == "blocked" and rt.confianza_hecha:
                rt.estado = "idle"
                avisar = True
            if avisar:
                self._emitir(
                    {"evento": "estado", "sesion": rt.registro.id, "estado": rt.estado}
                )

    def _manejar_confianza(self, rt: _RuntimeSesion) -> None:
        if rt.registro.programa != "claude":
            return
        if rt.confianza_hecha:
            return
        if self._reloj() - rt.arranque > self._ventana_confianza:
            return
        if not rt.pantalla.dialogo_confianza():
            return
        if rt.confianza_detectada is None:
            rt.confianza_detectada = self._reloj()
        if self._cwd_confiable(rt.registro.cwd):
            if not any(t.get_name() == "confianza" for t in rt.tareas if not t.done()):
                rt.tareas.append(asyncio.create_task(self._auto_confianza(rt), name="confianza"))
        else:
            rt.confianza_hecha = True
            if rt.estado != "blocked":
                rt.estado = "blocked"
                self._emitir(
                    {"evento": "estado", "sesion": rt.registro.id, "estado": "blocked"}
                )

    async def _auto_confianza(self, rt: _RuntimeSesion) -> None:
        detectada = rt.confianza_detectada or self._reloj()
        esperar = self._demora_confianza - (self._reloj() - detectada)
        if esperar > 0:
            await asyncio.sleep(esperar)
        proc = rt.proceso
        if not proc or not proc.vivo:
            return
        if not rt.pantalla.dialogo_confianza():
            return
        try:
            proc.escribir(b"\x1b[B")
            await asyncio.sleep(0.2)
            proc.escribir(b"\r")
        except ErrorProtocolo:
            return
        await asyncio.sleep(1.0)
        if rt.pantalla.dialogo_confianza():
            rt.confianza_hecha = True
            rt.estado = "blocked"
            log.warning("diálogo de confianza no se resolvió en sesión %s", rt.registro.id)
            self._emitir(
                {"evento": "estado", "sesion": rt.registro.id, "estado": "blocked"}
            )
        else:
            rt.confianza_hecha = True

    def _al_salir(self, rt: _RuntimeSesion, codigo: int) -> None:
        self._cancelar_tareas(rt)
        rt.codigo = codigo
        duracion = self._reloj() - rt.arranque
        if rt.con_resume and duracion < self._vida_minima and codigo != 0:
            rt.estado = "perdida"
        else:
            rt.estado = "terminada"
        self._registro.actualizar_sesion(
            rt.registro.id, ultima_vez_viva=time.time()
        )
        self._emitir(
            {"evento": "termino", "sesion": rt.registro.id, "codigo": codigo}
        )
        self._emitir(
            {"evento": "estado", "sesion": rt.registro.id, "estado": rt.estado}
        )

    async def apagar_ordenado(self, espera: float = 10.0) -> None:
        vivos = [rt for rt in self._sesiones.values() if rt.proceso and rt.proceso.vivo]
        for rt in vivos:
            rt.proceso.senal(signal.SIGTERM)
        if not vivos:
            self._registro.guardar()
            return
        plazo = self._reloj() + espera
        for rt in vivos:
            restante = plazo - self._reloj()
            if restante <= 0:
                break
            if rt.proceso and rt.proceso.vivo:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(rt.proceso.tarea_espera),
                        restante,
                    )
                except (asyncio.TimeoutError, AttributeError):
                    pass
        for rt in vivos:
            if rt.proceso and rt.proceso.vivo:
                rt.proceso.senal(signal.SIGKILL)
        fin = self._reloj() + 2.0
        for rt in vivos:
            if not rt.proceso:
                continue
            restante = fin - self._reloj()
            if restante <= 0:
                break
            if rt.proceso.vivo and rt.proceso.tarea_espera:
                try:
                    await asyncio.wait_for(asyncio.shield(rt.proceso.tarea_espera), restante)
                except asyncio.TimeoutError:
                    pass
        ahora = time.time()
        for rt in self._sesiones.values():
            if rt.registro.id in self._registro.sesiones:
                self._registro.actualizar_sesion(rt.registro.id, ultima_vez_viva=ahora)
        self._registro.guardar()
