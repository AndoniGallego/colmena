"""Canal unix del MCP de Colmena: identidad por SO_PEERCRED y ancestros, y una lista cerrada de ops.

La identidad sale solo del kernel: el pid del par y su cadena de ppid hasta el `pid_claude` de una sesión del
tablero del guardián. Nada de lo que mande el cliente (sesion, pane_id, COLMENA_SESION...) cuenta. El socket no
tiene ninguna operación de aprobar: eso solo existe en la web.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from .ganchos.canal import abrir_servidor_unix, credenciales_par

log = logging.getLogger(__name__)

OPS = frozenset({"sesiones", "leer_sesion", "pedidos", "buscar_memoria", "abrir", "mensaje", "cerrar", "cursor",
                 "programar", "tarea_ticket", "estado_pedido"})
OPS_ACCION = frozenset({"abrir", "mensaje", "cerrar", "cursor", "programar", "tarea_ticket"})
MODOS_NO_PERMITIDOS = frozenset({"copiloto", "guia"})

MAX_PETICION = 16 * 1024
MAX_ID = 64
MAX_SALTOS = 32
MAX_CONEXIONES_SESION = 4
MAX_CONEXIONES = 64
TIMEOUT_LINEA = 10.0

# Topes de creación de pedidos (se suman a los del store y a los de ejecución, que siguen al aprobar).
TOPE_ACCIONES_SESION = 30
TOPE_ACCIONES_GLOBAL = 90
TOPE_MENSAJES_SESION = 10
TOPE_LECTURAS_MINUTO = 4

Identidad = dict
Op = Callable[[Identidad, dict], Awaitable[dict]]


class ErrorCanal(Exception):
    def __init__(self, codigo: str, mensaje: str = "", **extra) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.mensaje = mensaje or codigo
        self.extra = extra

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "mensaje": self.mensaje, **self.extra}


# --- Identidad ---

def _ppid(pid: int, proc: Path, uid: int) -> int | None:
    """ppid de /proc/<pid>/stat, verificando que el proceso sea del mismo uid. Cualquier error: None."""
    try:
        if os.stat(proc / str(pid)).st_uid != uid:
            return None
        datos = (proc / str(pid) / "stat").read_bytes().decode("utf-8", "replace")
    except (OSError, ValueError):
        return None
    # El comm va entre paréntesis y puede traer espacios y paréntesis: se parsea desde el último ")".
    cierre = datos.rfind(")")
    if cierre < 0:
        return None
    campos = datos[cierre + 1:].split()
    if len(campos) < 2:
        return None
    try:
        return int(campos[1])
    except ValueError:
        return None


def resolver_identidad(pid: int, sesiones: list[dict], *, proc: Path = Path("/proc"),
                       uid: int | None = None) -> tuple[Identidad | None, str | None]:
    """Primer ancestro (incluido el par) que sea el `pid_claude` de una sesión viva del tablero."""
    uid = os.getuid() if uid is None else uid
    por_pid: dict[int, dict] = {}
    for s in sesiones:
        pc = s.get("pid_claude")
        if isinstance(pc, int) and not isinstance(pc, bool) and pc > 1 and s.get("estado") != "terminada":
            por_pid.setdefault(pc, s)
    vistos: set[int] = set()
    actual = pid
    for _ in range(MAX_SALTOS + 1):
        if not isinstance(actual, int) or actual <= 1 or actual in vistos:
            return None, "sesion_no_identificada"
        vistos.add(actual)
        if (ses := por_pid.get(actual)) is not None:
            # El par tiene que seguir siendo nuestro aunque coincida de entrada.
            if _ppid(actual, proc, uid) is None:
                return None, "sesion_no_identificada"
            if ses.get("modo") in MODOS_NO_PERMITIDOS:
                return None, "sesion_no_permitida"
            sid = str(ses.get("id") or "")
            return {"sesion_id": sid, "pane_id": sid, "nombre": str(ses.get("nombre") or ""),
                    "claude_session_id": ses.get("claude_session_id"), "modo": ses.get("modo")}, None
        siguiente = _ppid(actual, proc, uid)
        if siguiente is None:
            return None, "sesion_no_identificada"
        actual = siguiente
    return None, "sesion_no_identificada"


# --- Topes ---

class TopeVentana:
    """Cuántas veces en los últimos `ventana` segundos, por clave."""

    def __init__(self, maximo: int, ventana: float, reloj: Callable[[], float] = time.monotonic) -> None:
        self.maximo = maximo
        self.ventana = ventana
        self.reloj = reloj
        self._marcas: dict[str, deque] = {}

    def consumir(self, clave: str) -> float | None:
        """None si hay cupo (y lo consume); si no, segundos hasta que haya."""
        ahora = self.reloj()
        marcas = self._marcas.setdefault(clave, deque())
        while marcas and ahora - marcas[0] >= self.ventana:
            marcas.popleft()
        if len(marcas) >= self.maximo:
            return max(1.0, self.ventana - (ahora - marcas[0]))
        marcas.append(ahora)
        return None


class Topes:
    def __init__(self, reloj: Callable[[], float] = time.monotonic) -> None:
        self.acciones_sesion = TopeVentana(TOPE_ACCIONES_SESION, 3600, reloj)
        self.acciones_global = TopeVentana(TOPE_ACCIONES_GLOBAL, 3600, reloj)
        self.mensajes_sesion = TopeVentana(TOPE_MENSAJES_SESION, 3600, reloj)
        self.lecturas_sesion = TopeVentana(TOPE_LECTURAS_MINUTO, 60, reloj)

    def cobrar(self, op: str, sesion: str) -> None:
        espera = None
        if op == "leer_sesion":
            espera = self.lecturas_sesion.consumir(sesion)
        elif op in OPS_ACCION:
            if op == "mensaje":
                espera = self.mensajes_sesion.consumir(sesion)
            espera = espera or self.acciones_sesion.consumir(sesion) or self.acciones_global.consumir("*")
        if espera is not None:
            raise ErrorCanal("tope_alcanzado", "Demasiados pedidos seguidos: probá más tarde.",
                             retry_after=int(espera + 0.999))


# --- Servidor ---

def _error(pid_: str, codigo: str, mensaje: str = "", **extra) -> dict:
    return {"id": pid_, "ok": False, "error": ErrorCanal(codigo, mensaje, **extra).como_dict()}


def _validar(linea: bytes) -> tuple[str, str, dict] | dict:
    try:
        req = json.loads(linea.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _error("", "argumentos_invalidos", "JSON inválido")
    if not isinstance(req, dict):
        return _error("", "argumentos_invalidos", "La petición tiene que ser un objeto")
    rid = req.get("id")
    if not isinstance(rid, str) or len(rid) > MAX_ID:
        return _error("", "argumentos_invalidos", "id inválido")
    op = req.get("op")
    args = req.get("args", {})
    if not isinstance(op, str) or op not in OPS:
        return _error(rid, "op_desconocida", "Operación desconocida")
    if not isinstance(args, dict):
        return _error(rid, "argumentos_invalidos", "args tiene que ser un objeto")
    return rid, op, args


class ServidorMcp:
    def __init__(
        self,
        tablero: Callable[[], Awaitable[list[dict]] | list[dict]],
        ops: Mapping[str, Op],
        *,
        proc: Path = Path("/proc"),
        uid: int | None = None,
        credenciales: Callable[[object], tuple[int, int, int] | None] = credenciales_par,
        timeout_linea: float = TIMEOUT_LINEA,
        topes: Topes | None = None,
    ) -> None:
        self._tablero = tablero
        self._ops = {k: v for k, v in ops.items() if k in OPS}
        self._proc = proc
        self._uid = os.getuid() if uid is None else uid
        self._credenciales = credenciales
        self._timeout = timeout_linea
        self.topes = topes or Topes()
        self._server: asyncio.Server | None = None
        self._por_sesion: dict[str, int] = {}
        self._vivas: set[asyncio.Task] = set()
        self.leidas = 0

    async def _sesiones(self) -> list[dict]:
        res = self._tablero()
        if inspect.isawaitable(res):
            res = await res
        return list(res or [])

    async def identidad(self, pid: int) -> tuple[Identidad | None, str | None]:
        """Por llamada y con el tablero vigente: un pid reutilizado no hereda una identidad vieja."""
        try:
            sesiones = await self._sesiones()
        except Exception:
            log.warning("mcp: no pude leer el tablero")
            return None, "sesion_no_identificada"
        return resolver_identidad(pid, sesiones, proc=self._proc, uid=self._uid)

    async def _responder(self, writer: asyncio.StreamWriter, respuesta: dict) -> None:
        writer.write(json.dumps(respuesta, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
        await writer.drain()

    async def _ejecutar(self, pid: int, linea: bytes) -> dict:
        validado = _validar(linea)
        if isinstance(validado, dict):
            return validado
        rid, op, args = validado
        ident, codigo = await self.identidad(pid)
        if ident is None:
            log.info("mcp: %s rechazada (%s)", op, codigo)
            return _error(rid, codigo or "sesion_no_identificada")
        manejador = self._ops.get(op)
        if manejador is None:
            return _error(rid, "colmena_no_disponible", "Esa herramienta no está disponible")
        try:
            self.topes.cobrar(op, ident["sesion_id"])
            resultado = await manejador(ident, args)
        except ErrorCanal as exc:
            log.info("mcp: %s de %s → %s", op, ident["sesion_id"], exc.codigo)
            return {"id": rid, "ok": False, "error": exc.como_dict()}
        except Exception:
            log.exception("mcp: falló %s", op)
            return _error(rid, "error_interno", "Falló en Colmena")
        return {"id": rid, "ok": True, "resultado": resultado}

    async def _leer_linea(self, reader: asyncio.StreamReader, buf: bytearray) -> tuple[bytes | None, bool]:
        """(línea, demasiado_grande). None al cerrar o vencer el tiempo."""
        demasiado = False
        while True:
            idx = buf.find(b"\n")
            if idx >= 0:
                linea = bytes(buf[:idx])
                del buf[:idx + 1]
                return (b"" if demasiado else linea), demasiado or len(linea) > MAX_PETICION
            if len(buf) > MAX_PETICION:
                demasiado = True
                buf.clear()
            try:
                bloque = await asyncio.wait_for(reader.read(65536), self._timeout)
            except (asyncio.TimeoutError, OSError, ConnectionError):
                return None, False
            if not bloque:
                return None, False
            buf.extend(bloque)

    async def atender(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tarea = asyncio.current_task()
        if tarea is not None:
            self._vivas.add(tarea)
        sesion_contada = ""
        try:
            cred = None
            try:
                cred = self._credenciales(writer)
            except Exception:
                cred = None
            if cred is None or cred[1] != self._uid or len(self._vivas) > MAX_CONEXIONES:
                return
            pid = cred[0]
            ident, _ = await self.identidad(pid)
            if ident is not None:
                sesion_contada = ident["sesion_id"]
                if self._por_sesion.get(sesion_contada, 0) >= MAX_CONEXIONES_SESION:
                    sesion_contada = ""
                    await self._responder(writer, _error("", "tope_alcanzado", "Demasiadas conexiones",
                                                         retry_after=1))
                    return
                self._por_sesion[sesion_contada] = self._por_sesion.get(sesion_contada, 0) + 1
            buf = bytearray()
            while True:
                linea, grande = await self._leer_linea(reader, buf)
                if linea is None:
                    return
                self.leidas += 1
                if grande:
                    await self._responder(writer, _error("", "demasiado_grande", "Petición de más de 16 KiB"))
                    continue
                await self._responder(writer, await self._ejecutar(pid, linea))
        except (ConnectionError, OSError):
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("mcp: error atendiendo una conexión")
        finally:
            if sesion_contada:
                n = self._por_sesion.get(sesion_contada, 1) - 1
                if n <= 0:
                    self._por_sesion.pop(sesion_contada, None)
                else:
                    self._por_sesion[sesion_contada] = n
            if not writer.is_closing():
                writer.close()
            if tarea is not None:
                self._vivas.discard(tarea)

    async def abrir(self, ruta: Path) -> None:
        self._server = await abrir_servidor_unix(ruta, self.atender, MAX_PETICION + 1)

    async def cerrar(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
        actual = asyncio.current_task()
        tareas = [t for t in list(self._vivas) if t is not actual]
        for t in tareas:
            t.cancel()
        if tareas:
            await asyncio.gather(*tareas, return_exceptions=True)
        if server is not None:
            try:
                await asyncio.wait_for(server.wait_closed(), 2)
            except asyncio.TimeoutError:
                log.warning("timeout esperando el cierre del canal MCP")


def ruta_socket(entorno: Mapping[str, str] | None = None) -> Path | None:
    """`$XDG_RUNTIME_DIR/colmena/mcp.sock`; sin XDG_RUNTIME_DIR no hay canal."""
    base = (entorno if entorno is not None else os.environ).get("XDG_RUNTIME_DIR")
    if not base or not os.path.isabs(base):
        return None
    return Path(base) / "colmena" / "mcp.sock"
