import asyncio
import errno
import json
import logging
import os
import socket
import stat
import struct
from collections.abc import Awaitable, Callable
from pathlib import Path

from .colmena_gancho import MAX_MENSAJE
from .mensaje import MensajeGancho, parsear

logger = logging.getLogger(__name__)

MAX_LINEA = MAX_MENSAJE
_JSON_KW = {"ensure_ascii": False, "separators": (",", ":")}


def preparar_directorio(directorio: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    try:
        fd = os.open(directorio, flags)
    except FileNotFoundError:
        directorio.mkdir(mode=0o700, parents=True, exist_ok=True)
        return
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise PermissionError(f"directorio de ganchos es symlink: {directorio}") from exc
        if exc.errno == errno.ENOTDIR:
            try:
                st = os.lstat(directorio)
                if stat.S_ISLNK(st.st_mode):
                    raise PermissionError(
                        f"directorio de ganchos es symlink: {directorio}"
                    ) from exc
            except FileNotFoundError:
                pass
            raise OSError(errno.ENOTDIR, "No es un directorio", str(directorio)) from exc
        raise
    try:
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode):
            raise OSError(errno.ENOTDIR, "No es un directorio", str(directorio))
        if st.st_uid != os.getuid():
            raise PermissionError(f"directorio de ganchos de otro usuario: {directorio}")
        if stat.S_IMODE(st.st_mode) != 0o700:
            os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


def mismo_uid(writer) -> bool:
    try:
        sock = writer.get_extra_info("socket")
        if sock is None:
            return False
        raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _, uid, _ = struct.unpack("3i", raw)
        return uid == os.getuid()
    except Exception:
        return False


class Conexion:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer
        self.cerrada = asyncio.Event()
        self._respondido = False
        self._cerrada = False
        self._leer = asyncio.create_task(self._hasta_eof())

    async def _hasta_eof(self) -> None:
        try:
            while True:
                bloque = await self._reader.read(65536)
                if not bloque:
                    break
        except (OSError, ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self.cerrada.set()

    async def responder(self, respuesta: dict) -> bool:
        if self._respondido or self._cerrada or self.cerrada.is_set():
            return False
        self._respondido = True
        try:
            linea = json.dumps(respuesta, **_JSON_KW) + "\n"
            self._writer.write(linea.encode())
            await self._writer.drain()
            self.cerrar()
            return True
        except (ConnectionError, OSError, ValueError, TypeError):
            self.cerrar()
            return False

    def cerrar(self) -> None:
        if self._cerrada:
            return
        self._cerrada = True
        self.cerrada.set()
        if not self._leer.done():
            self._leer.cancel()
        if not self._writer.is_closing():
            self._writer.close()


class ServidorGanchos:
    """Canal Unix de ganchos. `manejar` debe esperar hasta responder o hasta `conexion.cerrada`, porque al volver se cierra la conexión."""

    def __init__(
        self,
        manejar: Callable[[MensajeGancho, Conexion], Awaitable[None]],
        verificar: Callable[[object], bool] = mismo_uid,
    ) -> None:
        self._manejar = manejar
        self._verificar = verificar
        self.descartados = 0
        self._server: asyncio.Server | None = None
        self._vivas: set[Conexion] = set()
        self._tareas_atender: set[asyncio.Task] = set()

    async def _cerrar_writer(self, writer: asyncio.StreamWriter) -> None:
        if not writer.is_closing():
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def atender(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tarea = asyncio.current_task()
        if tarea is not None:
            self._tareas_atender.add(tarea)
        conexion: Conexion | None = None
        try:
            try:
                ok = self._verificar(writer)
            except Exception:
                ok = False
            if not ok:
                self.descartados += 1
                await self._cerrar_writer(writer)
                return

            try:
                linea = await reader.readline()
            except (asyncio.LimitOverrunError, ValueError):
                self.descartados += 1
                await self._cerrar_writer(writer)
                return

            if not linea.endswith(b"\n"):
                self.descartados += 1
                await self._cerrar_writer(writer)
                return

            msg = parsear(linea)
            if msg is None:
                self.descartados += 1
                logger.debug("mensaje de gancho descartado")
                await self._cerrar_writer(writer)
                return

            conexion = Conexion(reader, writer)
            self._vivas.add(conexion)
            try:
                await self._manejar(msg, conexion)
            except Exception:
                logger.exception("error en manejar gancho")
            finally:
                conexion.cerrar()
                self._vivas.discard(conexion)
                await self._cerrar_writer(writer)
        except Exception:
            logger.exception("error en atender gancho")
            if conexion is not None:
                conexion.cerrar()
                self._vivas.discard(conexion)
            await self._cerrar_writer(writer)
        finally:
            if not writer.is_closing():
                await self._cerrar_writer(writer)
            if tarea is not None:
                self._tareas_atender.discard(tarea)

    async def abrir(self, ruta: Path) -> None:
        preparar_directorio(ruta.parent)
        try:
            st = os.lstat(ruta)
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISSOCK(st.st_mode):
                ruta.unlink()
            else:
                raise OSError(errno.EEXIST, "La ruta del socket no es un socket unix", str(ruta))
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        umask_prev = os.umask(0o177)
        try:
            sock.bind(str(ruta))
        except Exception:
            sock.close()
            raise
        finally:
            os.umask(umask_prev)
        try:
            os.chmod(ruta, 0o600)
            sock.listen()
            self._server = await asyncio.start_unix_server(
                self.atender, sock=sock, limit=MAX_LINEA + 1
            )
        except Exception:
            sock.close()
            try:
                ruta.unlink()
            except OSError:
                pass
            raise

    async def cerrar(self) -> None:
        server = self._server
        actual = asyncio.current_task()
        if server is not None:
            server.close()
        for conexion in list(self._vivas):
            conexion.cerrar()
        self._vivas.clear()
        tareas = [t for t in list(self._tareas_atender) if t is not actual]
        for tarea in tareas:
            tarea.cancel()
        if tareas:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tareas, return_exceptions=True),
                    2,
                )
            except asyncio.TimeoutError:
                logger.warning("timeout esperando tareas atender de ganchos")
        if server is not None:
            try:
                await asyncio.wait_for(server.wait_closed(), 2)
            except asyncio.TimeoutError:
                logger.warning("timeout esperando cierre del servidor de ganchos")
            self._server = None
