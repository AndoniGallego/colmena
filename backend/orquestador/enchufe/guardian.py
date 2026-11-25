from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from orquestador.guardian.lanzador import MODOS_INTERNOS, MODOS_POR_LANZAMIENTO
from orquestador.guardian.protocolo import MAX_LINEA, VERSION, leer_mensaje

from .base import (
    TECLAS,
    Evento,
    Formato,
    Fuente,
    NoDisponible,
    NoExiste,
    NoTomado,
    Tecla,
    TerminalesError,
    Tiempo,
    _CONFIRMAR_PROMPT,
    _LANZAMIENTO_SHELL,
)
from .ids import es_guardian, tipo_de_id
if TYPE_CHECKING:
    from orquestador.estado_sesiones import EstadoSesiones

from .modelo import (
    Creado,
    ESTADOS_HERDR,
    Espacio,
    EstadoSesion,
    InfoProceso,
    Lanzamiento,
    Linea,
    ProcesoPrimerPlano,
    Sesion,
    Tablero,
    TomaPrompt,
)

log = logging.getLogger(__name__)

_ESTADOS_GUARDIAN = frozenset({"terminada", "perdida", "blocked"})
_ESTADOS_GANCHOS = frozenset({"idle", "working", "blocked", "done"})
_VALIDOS = _ESTADOS_GANCHOS | _ESTADOS_GUARDIAN
_VACIO = Tablero((), (), (), 0)
_TOPE_JUNTAR = 64 * 1024


@dataclass(frozen=True)
class FotoVivo:
    columnas: int
    filas: int
    historial: tuple[str, ...]
    pantalla: tuple[str, ...]
    cursor: tuple[int, int] | None
    cursor_visible: bool = True


def _foto_vivo_de(raw: object) -> FotoVivo | None:
    if not isinstance(raw, dict):
        return None
    col = raw.get("columnas")
    fil = raw.get("filas")
    if not isinstance(col, int) or not isinstance(fil, int):
        return None
    if not (1 <= col <= 1000 and 1 <= fil <= 1000):
        return None
    hist = raw.get("historial")
    pant = raw.get("pantalla")
    if not isinstance(hist, list) or not isinstance(pant, list):
        return None
    if not all(isinstance(x, str) for x in hist) or not all(isinstance(x, str) for x in pant):
        return None
    cur_raw = raw.get("cursor")
    cursor: tuple[int, int] | None
    if cur_raw is None:
        cursor = None
    elif isinstance(cur_raw, list) and len(cur_raw) == 2 and isinstance(cur_raw[0], int) and isinstance(cur_raw[1], int):
        cursor = (cur_raw[0], cur_raw[1])
    else:
        return None
    vis = raw.get("cursor_visible", True)
    if not isinstance(vis, bool):
        return None
    return FotoVivo(col, fil, tuple(hist), tuple(pant), cursor, vis)


def _error_de(codigo: str, mensaje: str) -> TerminalesError:
    if codigo == "no_existe":
        return NoExiste(mensaje)
    if codigo == "no_disponible":
        return NoDisponible(mensaje)
    if codigo == "invalido":
        return ValueError(mensaje)
    if codigo == "tiempo":
        return Tiempo(mensaje)
    if codigo == "no_tomado":
        return NoTomado(mensaje)
    return TerminalesError(mensaje)


# Claude Code antepone al título de la terminal su estado (✳ quieto; spinner braille o círculo ◐◓◑◒ trabajando).
_ESTADO_CLAUDE_RE = re.compile(r"^[\u2800-\u28ff\u2722-\u273d\u25d0-\u25d3·*]+\s*")


def _programa(raw: str) -> str:
    if raw == "claude":
        return "claude"
    if raw == "shell":
        return "shell"
    return "otro"


def _pid_o_none(valor: object) -> int | None:
    """Campo opcional y nuevo: un guardián viejo no lo manda."""
    return valor if isinstance(valor, int) and not isinstance(valor, bool) and valor > 1 else None


def _tablero_de_res(res: dict, estados: EstadoSesiones | None) -> Tablero:
    espacios: list[Espacio] = []
    for e in res.get("espacios") or []:
        if not isinstance(e, dict):
            continue
        eid = e.get("id")
        if not isinstance(eid, str):
            continue
        lineas_ids = tuple(x for x in (e.get("lineas") or []) if isinstance(x, str))
        num = e.get("numero")
        espacios.append(
            Espacio(
                id=eid,
                nombre=str(e.get("nombre") or ""),
                lineas=lineas_ids,
                numero=1000 + int(num) if isinstance(num, int) else None,
            )
        )
    lineas: list[Linea] = []
    for lin in res.get("lineas") or []:
        if not isinstance(lin, dict):
            continue
        lid = lin.get("id")
        eid = lin.get("espacio_id")
        if not isinstance(lid, str) or not isinstance(eid, str):
            continue
        sids = tuple(x for x in (lin.get("sesiones") or []) if isinstance(x, str))
        lineas.append(Linea(id=lid, espacio_id=eid, nombre=str(lin.get("nombre") or ""), sesiones=sids))
    sesiones: list[Sesion] = []
    for s in res.get("sesiones") or []:
        if not isinstance(s, dict):
            continue
        sid = s.get("id")
        if not isinstance(sid, str):
            continue
        crudo_g = s.get("estado")
        estado, fuente = _estado_actual(sid, crudo_g, estados)
        prog = _programa(str(s.get("programa") or "shell"))
        claude_id = s.get("claude_session_id")
        claude_id = claude_id if isinstance(claude_id, str) else None
        titulo_crudo = str(s.get("titulo") or "")
        titulo = _ESTADO_CLAUDE_RE.sub("", titulo_crudo).strip()
        es_agente = prog == "claude" and estado not in ("terminada", "perdida")
        sesiones.append(
            Sesion(
                id=sid,
                linea_id=str(s.get("linea_id") or ""),
                espacio_id=str(s.get("espacio_id") or ""),
                programa=prog,  # type: ignore[arg-type]
                estado=estado,  # type: ignore[arg-type]
                estado_fuente=fuente,  # type: ignore[arg-type]
                claude_session_id=claude_id,
                cwd=str(s.get("cwd") or ""),
                cwd_primer_plano=s.get("cwd_primer_plano") if isinstance(s.get("cwd_primer_plano"), str) else None,
                titulo=titulo,
                revision=None,
                backend="guardian",
                agente="claude" if es_agente else None,
                es_agente=es_agente,
                estado_crudo=estado,
                claude_session_tipo="id" if claude_id else None,
                titulo_crudo=titulo_crudo,
                listo=s.get("listo") if isinstance(s.get("listo"), bool) else None,
                pid_claude=_pid_o_none(s.get("pid_claude")),
                modo=s.get("modo") if isinstance(s.get("modo"), str) else None,
            )
        )
    return Tablero(tuple(espacios), tuple(lineas), tuple(sesiones), 0)


def _estado_actual(
    sid: str,
    crudo_g: object,
    estados: EstadoSesiones | None,
) -> tuple[EstadoSesion, str]:
    if isinstance(crudo_g, str) and crudo_g in _ESTADOS_GUARDIAN:
        return crudo_g, "guardian"  # type: ignore[return-value]
    if estados is not None:
        reg = estados.estado_de(sid)
        if reg is not None and reg.estado in _ESTADOS_GANCHOS:
            return reg.estado, "ganchos"  # type: ignore[return-value]
    return "idle", "guardian"


class ClienteGuardian:
    nombre = "guardian"
    capacidades = frozenset({"renombrar", "retoma"})

    def __init__(
        self,
        ruta: Path,
        *,
        conectar: Callable[[], Any] | None = None,
        timeout: float = 10.0,
        reintento: float = 1.0,
        reintento_max: float = 30.0,
        espera_toma: float = 5.0,
    ) -> None:
        self._ruta = ruta
        self._conectar_fn = conectar
        self._timeout = timeout
        self._reintento = reintento
        self._reintento_max = reintento_max
        self._espera_toma = espera_toma
        self._estados: EstadoSesiones | None = None
        self._ultimo_tablero = _VACIO
        self._revision = 0
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lector: asyncio.Task | None = None
        self._siguiente_id = 1
        self._pendientes: dict[int, asyncio.Future] = {}
        self._esperas: dict[str, asyncio.Event] = {}
        self._esperas_estado: dict[str, asyncio.Event] = {}
        self._subs_abiertas: set[_SuscripcionGuardian] = set()

    @property
    def ultimo_tablero(self) -> Tablero:
        return self._ultimo_tablero

    def conectar_estados(self, estados: EstadoSesiones) -> None:
        self._estados = estados
        if self.al_gancho not in estados.observadores:
            estados.observadores.append(self.al_gancho)

    def _despertar_esperas(self, sesion_id: str) -> None:
        ev = self._esperas.get(sesion_id)
        if ev is not None:
            ev.set()
        ev2 = self._esperas_estado.get(sesion_id)
        if ev2 is not None:
            ev2.set()

    def al_gancho(self, sesion_id: str, evento: str) -> None:
        if not es_guardian(sesion_id):
            return
        self._despertar_esperas(sesion_id)
        for sub in list(self._subs_abiertas):
            sub._empujar(Evento("estado", "guardian", sesion_id=sesion_id))

    async def cerrar_enchufe(self) -> None:
        await self._cerrar_pedidos()

    async def _conectar_default(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        try:
            return await asyncio.open_unix_connection(str(self._ruta), limit=MAX_LINEA + 1)
        except (FileNotFoundError, ConnectionRefusedError, PermissionError, OSError) as exc:
            raise NoDisponible("guardián no disponible") from exc

    async def _abrir_pedidos(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            return
        conectar = self._conectar_fn or self._conectar_default
        reader, writer = await conectar()
        self._reader = reader
        self._writer = writer
        self._lector = asyncio.create_task(self._loop_lector())
        res = await self._pedir_interno("hola", {}, timeout=self._timeout)
        if res.get("protocolo") != VERSION:
            await self._cerrar_pedidos()
            log.error("versión del guardián incompatible")
            raise NoDisponible("versión del guardián incompatible")

    async def _cerrar_pedidos(self) -> None:
        writer = self._writer
        lector = self._lector
        self._writer = None
        self._reader = None
        self._lector = None
        if writer is not None:
            with contextlib.suppress(OSError):
                writer.close()
                await writer.wait_closed()
        if lector is not None:
            lector.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await lector
        for fut in self._pendientes.values():
            if not fut.done():
                fut.set_exception(NoDisponible("guardián no disponible"))
        self._pendientes.clear()

    def _timeout_de(self, op: str) -> float:
        if op == "arrancar_claude":
            return 45.0
        if op == "cerrar":
            return 15.0
        return self._timeout

    async def _pedir(self, op: str, args: dict) -> dict:
        async with self._lock:
            try:
                await self._abrir_pedidos()
            except Exception:
                await self._cerrar_pedidos()
                raise
            try:
                return await self._pedir_interno(op, args, timeout=self._timeout_de(op))
            except NoDisponible:
                await self._cerrar_pedidos()
                raise

    async def _pedir_interno(self, op: str, args: dict, *, timeout: float) -> dict:
        assert self._writer is not None
        pid = self._siguiente_id
        self._siguiente_id += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pendientes[pid] = fut
        linea = json.dumps({"id": pid, "op": op, "args": args}, ensure_ascii=False, separators=(",", ":")) + "\n"
        self._writer.write(linea.encode())
        await self._writer.drain()
        try:
            msg = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError as exc:
            self._pendientes.pop(pid, None)
            raise Tiempo("tiempo") from exc
        if not msg.get("ok"):
            err = msg.get("error") or {}
            codigo = err.get("codigo") if isinstance(err, dict) else "interno"
            mensaje = err.get("mensaje") if isinstance(err, dict) else str(err)
            raise _error_de(str(codigo), str(mensaje))
        res = msg.get("res")
        return res if isinstance(res, dict) else {}

    async def _loop_lector(self) -> None:
        assert self._reader is not None
        try:
            while True:
                linea = await self._reader.readuntil(b"\n")
                try:
                    msg = leer_mensaje(linea)
                except Exception:
                    continue
                if "id" in msg:
                    pid = msg.get("id")
                    if isinstance(pid, int):
                        fut = self._pendientes.pop(pid, None)
                        if fut is not None and not fut.done():
                            fut.set_result(msg)
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            self._reader = None
            if self._writer is not None:
                with contextlib.suppress(OSError):
                    self._writer.close()
                self._writer = None
            for fut in self._pendientes.values():
                if not fut.done():
                    fut.set_exception(NoDisponible("guardián no disponible"))
            self._pendientes.clear()

    async def tablero(self) -> Tablero:
        res = await self._pedir("tablero", {})
        base = _tablero_de_res(res, self._estados)
        clave = (base.espacios, base.lineas, base.sesiones)
        if clave != (self._ultimo_tablero.espacios, self._ultimo_tablero.lineas, self._ultimo_tablero.sesiones):
            self._revision += 1
        tablero = replace(base, revision=self._revision)
        self._ultimo_tablero = tablero
        return tablero

    async def proceso(self, sesion_id: str) -> InfoProceso:
        res = await self._pedir("proceso", {"sesion_id": sesion_id})
        argv = res.get("argv")
        argv_t = tuple(argv) if isinstance(argv, list) else ()
        comando = res.get("comando")
        comando = str(comando) if comando is not None else None
        cwd = res.get("cwd")
        cwd = str(cwd) if cwd is not None else None
        pid = res.get("pid")
        pid = int(pid) if isinstance(pid, int) else None
        es_claude = bool(res.get("es_claude"))
        grupo = res.get("grupo")
        grupo = int(grupo) if isinstance(grupo, int) else None
        shell_pid = res.get("shell_pid")
        shell_pid = int(shell_pid) if isinstance(shell_pid, int) else None
        proc = ProcesoPrimerPlano(pid, comando or "", argv_t, cwd)
        return InfoProceso(pid, comando, cwd, es_claude, (proc,), grupo, shell_pid)

    async def leer(
        self,
        sesion_id: str,
        *,
        fuente: Fuente = "visible",
        formato: Formato = "texto",
        lineas: int | None = None,
    ) -> str:
        args: dict[str, Any] = {"sesion_id": sesion_id, "fuente": fuente, "formato": formato}
        if lineas is not None:
            args["lineas"] = lineas
        res = await self._pedir("leer", args)
        texto = res.get("texto")
        return str(texto) if texto is not None else ""

    async def crear_espacio(self, nombre: str, cwd: str) -> Creado:
        res = await self._pedir("crear_espacio", {"nombre": nombre, "cwd": cwd})
        return Creado(res.get("espacio_id"), res.get("linea_id"), str(res.get("sesion_id")))

    async def crear_linea(
        self,
        espacio_id: str,
        nombre: str,
        cwd: str,
        programa: Lanzamiento = _LANZAMIENTO_SHELL,
    ) -> Creado:
        args: dict[str, Any] = {
            "espacio_id": espacio_id,
            "nombre": nombre,
            "cwd": cwd,
            "programa": programa.programa,
        }
        if programa.resume:
            args["resume"] = programa.resume
        res = await self._pedir("crear_linea", args)
        return Creado(None, res.get("linea_id"), str(res.get("sesion_id")))

    async def arrancar_claude(
        self,
        sesion_id: str,
        nombre: str,
        resume: str | None = None,
        *,
        modo: str | None = None,
        dirs_extra: list[str] | None = None,
    ) -> None:
        if modo is not None and modo not in MODOS_POR_LANZAMIENTO | MODOS_INTERNOS:
            raise ValueError("modo de permisos por lanzamiento inválido")
        if dirs_extra and modo != "copiloto":
            raise ValueError("dirs_extra solo vale en modo copiloto")
        args: dict[str, Any] = {"sesion_id": sesion_id, "nombre": nombre}
        if resume:
            args["resume"] = resume
        if modo is not None:
            args["modo"] = modo
        if dirs_extra:
            args["dirs_extra"] = list(dirs_extra)
        res = await self._pedir("arrancar_claude", args)
        if modo is None:
            return
        if not isinstance(res, dict) or res.get("modo") != modo:
            # Guardián viejo: ignoró el modo y Claude quedó con el global. No se deja corriendo.
            try:
                await self._pedir("cerrar", {"objetivo_id": sesion_id})
            except TerminalesError as exc:
                log.warning("no pude cerrar %s tras un arranque sin modo: %s", sesion_id, type(exc).__name__)
            raise NoDisponible("Actualizá el guardián: no pude arrancar Claude en modo seguro")

    async def renombrar(self, objetivo_id: str, nombre: str) -> None:
        await self._pedir("renombrar", {"objetivo_id": objetivo_id, "nombre": nombre})

    async def cerrar(self, objetivo_id: str) -> None:
        await self._pedir("cerrar", {"objetivo_id": objetivo_id})

    async def enfocar(self, objetivo_id: str) -> None:
        return None

    async def mandar_prompt(
        self,
        sesion_id: str,
        texto: str,
        *,
        confirmar: frozenset[EstadoSesion] = _CONFIRMAR_PROMPT,
        timeout: float = 30.0,
    ) -> TomaPrompt:
        espera = asyncio.Event()
        self._esperas[sesion_id] = espera
        try:
            await self._pedir("mandar_prompt", {"sesion_id": sesion_id, "texto": texto})
        except Exception:
            self._esperas.pop(sesion_id, None)
            raise
        plazo = min(timeout, self._espera_toma)
        try:
            await asyncio.wait_for(espera.wait(), plazo)
            reg = self._estados.estado_de(sesion_id) if self._estados else None
            estado: EstadoSesion = "working"
            if reg is not None and reg.estado in confirmar:
                estado = reg.estado  # type: ignore[assignment]
            elif reg is not None and reg.estado in _ESTADOS_GANCHOS:
                estado = reg.estado  # type: ignore[assignment]
            return TomaPrompt(True, estado, "gancho")
        except asyncio.TimeoutError:
            pass
        finally:
            self._esperas.pop(sesion_id, None)

        pantalla = await self.leer(sesion_id, fuente="visible")
        if "❯" not in pantalla:
            raise NoTomado("sin prompt visible")
        primera = (texto.splitlines()[0] if texto else "").strip()
        prefijo = primera[:40] if primera else ""
        if prefijo and prefijo in pantalla:
            raise NoTomado("el prompt quedó en la entrada")
        return TomaPrompt(True, "working", "pantalla")

    async def esperar(
        self, sesion_id: str, hasta: frozenset[EstadoSesion], timeout: float
    ) -> EstadoSesion:
        loop = asyncio.get_running_loop()
        limite = loop.time() + timeout

        def _actual() -> EstadoSesion | None:
            for s in self._ultimo_tablero.sesiones:
                if s.id == sesion_id:
                    return s.estado
            return None

        while True:
            try:
                await self.tablero()
            except TerminalesError:
                pass
            actual = _actual()
            if actual is None:
                raise NoExiste(sesion_id)
            if actual in hasta:
                return actual
            restante = limite - loop.time()
            if restante <= 0:
                raise Tiempo("tiempo")
            ev = asyncio.Event()
            self._esperas_estado[sesion_id] = ev
            try:
                await asyncio.wait_for(ev.wait(), restante)
            except asyncio.TimeoutError as exc:
                raise Tiempo("tiempo") from exc
            finally:
                self._esperas_estado.pop(sesion_id, None)

    async def esperar_listo(self, sesion_id: str, timeout: float) -> str:
        loop = asyncio.get_running_loop()
        limite = loop.time() + timeout
        while True:
            try:
                await self.tablero()
            except TerminalesError:
                pass
            ses = next((s for s in self._ultimo_tablero.sesiones if s.id == sesion_id), None)
            if ses is None:
                raise NoExiste(sesion_id)
            if ses.estado in ("terminada", "perdida"):
                raise NoDisponible(f"sesión {ses.estado}")
            if ses.listo is True:
                return "guardian"
            if ses.listo is None and self._estados is not None and self._estados.estado_de(sesion_id) is not None:
                return "ganchos"
            restante = limite - loop.time()
            if restante <= 0:
                raise Tiempo("tiempo", listo_conocido=ses.listo is not None)
            ev = asyncio.Event()
            self._esperas_estado[sesion_id] = ev
            try:
                await asyncio.wait_for(ev.wait(), min(restante, 1.0))
            except asyncio.TimeoutError:
                pass
            finally:
                self._esperas_estado.pop(sesion_id, None)

    async def interrumpir(self, sesion_id: str) -> None:
        await self._pedir("interrumpir", {"sesion_id": sesion_id})

    async def teclas(self, sesion_id: str, teclas: Sequence[Tecla]) -> None:
        if not teclas:
            raise ValueError("tecla no permitida")
        for t in teclas:
            if t not in TECLAS:
                raise ValueError("tecla no permitida")
        await self._pedir("teclas", {"sesion_id": sesion_id, "teclas": list(teclas)})

    async def escribir(self, sesion_id: str, texto: str) -> None:
        await self._pedir("escribir", {"sesion_id": sesion_id, "texto": texto})

    async def ejecutar(self, sesion_id: str, comando: str) -> None:
        await self._pedir("ejecutar", {"sesion_id": sesion_id, "comando": comando})

    async def abrir_vivo(self, sesion_id: str, *, tamano: tuple[int, int] = (120, 40)) -> "CanalVivo":
        if not es_guardian(sesion_id) or tipo_de_id(sesion_id) != "sesion":
            raise NoExiste(sesion_id)
        conectar = self._conectar_fn or self._conectar_default
        reader: asyncio.StreamReader | None = None
        writer: asyncio.StreamWriter | None = None
        pendientes: list[dict] = []
        try:
            reader, writer = await conectar()
            pid = 1
            linea = json.dumps({"id": pid, "op": "hola", "args": {}}, ensure_ascii=False, separators=(",", ":")) + "\n"
            writer.write(linea.encode())
            await writer.drain()
            ack = await _leer_hasta_id(reader, pid, self._timeout, pendientes)
            if not ack.get("ok") or (ack.get("res") or {}).get("protocolo") != VERSION:
                raise NoDisponible("versión del guardián incompatible")
            pid = 2
            args = {"salida": [sesion_id], "foto": True}
            linea = json.dumps({"id": pid, "op": "suscribir", "args": args}, ensure_ascii=False, separators=(",", ":")) + "\n"
            writer.write(linea.encode())
            await writer.drain()
            sub = await _leer_hasta_id(reader, pid, self._timeout, pendientes)
            if not sub.get("ok"):
                err = sub.get("error") or {}
                codigo = err.get("codigo") if isinstance(err, dict) else "interno"
                mensaje = err.get("mensaje") if isinstance(err, dict) else str(err)
                raise _error_de(str(codigo), str(mensaje))
            res = sub.get("res")
            res = res if isinstance(res, dict) else {}
            fotos = res.get("fotos")
            foto_raw = fotos.get(sesion_id) if isinstance(fotos, dict) else None
            foto = _foto_vivo_de(foto_raw)
            siguiente_id = 3
            if foto is None:
                pid = 3
                args_leer = {"sesion_id": sesion_id, "fuente": "visible", "formato": "ansi"}
                linea = json.dumps({"id": pid, "op": "leer", "args": args_leer}, ensure_ascii=False, separators=(",", ":")) + "\n"
                writer.write(linea.encode())
                await writer.drain()
                leer_ack = await _leer_hasta_id(reader, pid, self._timeout, pendientes)
                if not leer_ack.get("ok"):
                    err = leer_ack.get("error") or {}
                    codigo = err.get("codigo") if isinstance(err, dict) else "interno"
                    mensaje = err.get("mensaje") if isinstance(err, dict) else str(err)
                    raise _error_de(str(codigo), str(mensaje))
                leer_res = leer_ack.get("res")
                leer_res = leer_res if isinstance(leer_res, dict) else {}
                texto = leer_res.get("texto")
                texto = str(texto) if texto is not None else ""
                foto = FotoVivo(
                    tamano[0],
                    tamano[1],
                    (),
                    tuple(texto.split("\n")),
                    None,
                )
                siguiente_id = 4
            return CanalVivo(reader, writer, sesion_id, foto, pendientes=pendientes, siguiente_id=siguiente_id)
        except Exception:
            if writer is not None:
                with contextlib.suppress(OSError):
                    writer.close()
                    await writer.wait_closed()
            raise

    def suscribir(self) -> AsyncIterator[Evento]:
        return _SuscripcionGuardian(self)


async def _leer_hasta_id(
    reader: asyncio.StreamReader,
    pid: int,
    timeout: float,
    buffer: list[dict],
) -> dict:
    while True:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout)
        except asyncio.TimeoutError as exc:
            raise Tiempo("tiempo") from exc
        if not raw:
            raise NoDisponible("guardián no disponible")
        try:
            msg = leer_mensaje(raw)
        except Exception:
            continue
        if msg.get("id") == pid:
            return msg
        if "id" not in msg:
            buffer.append(msg)


class CanalVivo:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        sesion_id: str,
        foto: FotoVivo,
        *,
        pendientes: list[dict] | None = None,
        siguiente_id: int = 3,
    ) -> None:
        self.foto = foto
        self._reader = reader
        self._writer = writer
        self._sesion_id = sesion_id
        self._pendientes = list(pendientes or [])
        self._siguiente_id = siguiente_id
        self._tablero_pendiente: int | None = None
        self._cerrado = False
        self._caido_emitido = False
        self._writer_cerrado = False

    def __aiter__(self) -> AsyncIterator[dict]:
        return self

    async def _leer_mensaje(self) -> dict | None:
        while True:
            if self._pendientes:
                return self._pendientes.pop(0)
            try:
                raw = await self._reader.readline()
            except (ConnectionError, OSError):
                return None
            if not raw:
                return None
            try:
                return leer_mensaje(raw)
            except Exception:
                continue

    async def _pedir_tablero(self) -> dict | None:
        if self._tablero_pendiente is not None:
            return None
        pid = self._siguiente_id
        self._siguiente_id += 1
        self._tablero_pendiente = pid
        linea = json.dumps({"id": pid, "op": "tablero", "args": {}}, ensure_ascii=False, separators=(",", ":")) + "\n"
        self._writer.write(linea.encode())
        await self._writer.drain()
        return None

    def _sesiones_en_tablero(self, res: dict) -> set[str]:
        ids: set[str] = set()
        for s in res.get("sesiones") or []:
            if isinstance(s, dict):
                sid = s.get("id")
                if isinstance(sid, str):
                    ids.add(sid)
        return ids

    async def _procesar_tablero_respuesta(self, msg: dict) -> dict | None:
        pid = msg.get("id")
        if self._tablero_pendiente is None or pid != self._tablero_pendiente:
            return None
        self._tablero_pendiente = None
        if not msg.get("ok"):
            return None
        res = msg.get("res")
        res = res if isinstance(res, dict) else {}
        if self._sesion_id not in self._sesiones_en_tablero(res):
            return {"tipo": "cerrada"}
        return None

    def _traducir(self, ev: dict) -> dict | None:
        if "id" in ev:
            return None
        tipo = ev.get("evento")
        sid = ev.get("sesion")
        if tipo == "salida":
            if sid != self._sesion_id:
                return None
            texto = ev.get("texto")
            return {"tipo": "salida", "texto": str(texto) if texto is not None else ""}
        if tipo == "termino":
            if sid != self._sesion_id:
                return None
            codigo = ev.get("codigo")
            return {"tipo": "termino", "codigo": int(codigo) if isinstance(codigo, int) else None}
        if tipo == "vivo_cortado":
            if sid != self._sesion_id:
                return None
            return {"tipo": "desfasado"}
        if tipo == "tablero":
            return {"tipo": "__tablero__"}
        return None

    async def _concat_salidas(self, primero: dict) -> dict:
        textos = [primero["texto"]]
        total = len(textos[0])
        while total < _TOPE_JUNTAR:
            try:
                raw = await asyncio.wait_for(self._reader.readline(), 0)
            except asyncio.TimeoutError:
                break
            except (ConnectionError, OSError):
                break
            if not raw:
                break
            try:
                ev = leer_mensaje(raw)
            except Exception:
                break
            if "id" in ev:
                self._pendientes.insert(0, ev)
                break
            trad = self._traducir(ev)
            if trad is None:
                continue
            if trad.get("tipo") == "__tablero__":
                self._pendientes.insert(0, ev)
                break
            if trad.get("tipo") != "salida":
                self._pendientes.insert(0, ev)
                break
            textos.append(trad["texto"])
            total += len(trad["texto"])
        return {"tipo": "salida", "texto": "".join(textos)}

    async def __anext__(self) -> dict:
        if self._cerrado:
            raise StopAsyncIteration
        while True:
            msg = await self._leer_mensaje()
            if msg is None:
                self._cerrado = True
                if self._caido_emitido:
                    raise StopAsyncIteration
                self._caido_emitido = True
                return {"tipo": "caido"}
            if "id" in msg:
                cerrada = await self._procesar_tablero_respuesta(msg)
                if cerrada is not None:
                    self._cerrado = True
                    return cerrada
                continue
            trad = self._traducir(msg)
            if trad is None:
                continue
            if trad.get("tipo") == "__tablero__":
                await self._pedir_tablero()
                continue
            if trad.get("tipo") == "salida":
                return await self._concat_salidas(trad)
            return trad

    async def cerrar(self) -> None:
        if self._writer_cerrado:
            return
        self._writer_cerrado = True
        self._cerrado = True
        with contextlib.suppress(OSError):
            self._writer.close()
            await self._writer.wait_closed()


class _SuscripcionGuardian:
    def __init__(self, cliente: ClienteGuardian) -> None:
        self._cliente = cliente
        self._cola: asyncio.Queue[Evento | None] = asyncio.Queue()
        self._cerrada = False
        self._tarea: asyncio.Task | None = None
        cliente._subs_abiertas.add(self)

    def _arrancar(self) -> None:
        if self._tarea is None and not self._cerrada:
            self._tarea = asyncio.create_task(self._correr())

    def _empujar(self, ev: Evento) -> None:
        if not self._cerrada:
            self._cola.put_nowait(ev)

    def __aiter__(self) -> AsyncIterator[Evento]:
        self._arrancar()
        return self

    async def _correr(self) -> None:
        espera = self._cliente._reintento
        while not self._cerrada:
            try:
                conectar = self._cliente._conectar_fn or self._cliente._conectar_default
                reader, writer = await conectar()
            except (NoDisponible, OSError):
                self._empujar(Evento("caido", "guardian"))
                await asyncio.sleep(espera)
                espera = min(espera * 2, self._cliente._reintento_max)
                continue
            try:
                pid = 1
                linea = json.dumps({"id": pid, "op": "hola", "args": {}}) + "\n"
                writer.write(linea.encode())
                await writer.drain()
                ack = json.loads((await asyncio.wait_for(reader.readline(), self._cliente._timeout)).decode())
                if not ack.get("ok") or (ack.get("res") or {}).get("protocolo") != VERSION:
                    raise NoDisponible("versión del guardián incompatible")
                pid = 2
                linea = json.dumps({"id": pid, "op": "suscribir", "args": {}}) + "\n"
                writer.write(linea.encode())
                await writer.drain()
                sub_ack = json.loads((await asyncio.wait_for(reader.readline(), self._cliente._timeout)).decode())
                if not sub_ack.get("ok"):
                    raise NoDisponible("suscripción rechazada")
                self._empujar(Evento("volvio", "guardian"))
                espera = self._cliente._reintento
                while not self._cerrada:
                    raw = await reader.readline()
                    if not raw:
                        break
                    try:
                        ev = leer_mensaje(raw)
                    except Exception:
                        continue
                    trad = _evento_de_guardian(ev)
                    if trad is not None:
                        if trad.sesion_id and trad.tipo in ("estado", "termino"):
                            self._cliente._despertar_esperas(trad.sesion_id)
                        self._empujar(trad)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            finally:
                with contextlib.suppress(OSError):
                    writer.close()
                    await writer.wait_closed()
            if self._cerrada:
                break
            self._empujar(Evento("caido", "guardian"))
            await asyncio.sleep(espera)
            espera = min(espera * 2, self._cliente._reintento_max)

    async def __anext__(self) -> Evento:
        if self._cerrada and self._cola.empty():
            raise StopAsyncIteration
        self._arrancar()
        item = await self._cola.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def aclose(self) -> None:
        if self._cerrada:
            return
        self._cerrada = True
        self._cliente._subs_abiertas.discard(self)
        if self._tarea is not None:
            self._tarea.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tarea
            self._tarea = None
        self._cola.put_nowait(None)


def _evento_de_guardian(ev: dict) -> Evento | None:
    tipo = ev.get("evento")
    if tipo == "tablero":
        return Evento("tablero", "guardian")
    if tipo == "estado":
        sid = ev.get("sesion")
        est = ev.get("estado")
        estado = est if isinstance(est, str) and est in _VALIDOS else None
        return Evento("estado", "guardian", sesion_id=sid if isinstance(sid, str) else None, estado=estado)  # type: ignore[arg-type]
    if tipo == "termino":
        sid = ev.get("sesion")
        codigo = ev.get("codigo")
        return Evento(
            "termino",
            "guardian",
            sesion_id=sid if isinstance(sid, str) else None,
            datos={"codigo": codigo},
        )
    if tipo == "titulo":
        sid = ev.get("sesion")
        return Evento("titulo", "guardian", sesion_id=sid if isinstance(sid, str) else None, datos=dict(ev))
    if tipo == "proceso":
        sid = ev.get("sesion")
        return Evento("proceso", "guardian", sesion_id=sid if isinstance(sid, str) else None, datos=dict(ev))
    if tipo == "salida":
        sid = ev.get("sesion")
        texto = ev.get("texto")
        return Evento(
            "salida",
            "guardian",
            sesion_id=sid if isinstance(sid, str) else None,
            datos={"texto": texto},
        )
    if tipo == "vivo_cortado":
        return None
    return None
