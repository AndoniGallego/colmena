from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty
import signal
import struct
import termios
from collections.abc import Callable, Sequence

from orquestador.guardian.protocolo import NO_DISPONIBLE, ErrorProtocolo

log = logging.getLogger(__name__)

_TOPE_PENDIENTE = 1 << 20


def _tomar_terminal() -> None:
    # Sin TIOCSCTTY el hijo no tiene tty de control y el job control del PTY no funciona.
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


def _winsize(columnas: int, filas: int) -> bytes:
    return struct.pack("HHHH", filas, columnas, 0, 0)


class ProcesoPty:
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        master: int,
        proc: asyncio.subprocess.Process,
        al_leer: Callable[[bytes], None],
        al_salir: Callable[[int], None],
    ) -> None:
        self._loop = loop
        self._master = master
        self._proc = proc
        self._al_leer = al_leer
        self._al_salir = al_salir
        self._codigo: int | None = None
        self._cerrado = False
        self._pendiente = bytearray()
        self._writer_registrado = False
        self._tarea_espera: asyncio.Task[None] | None = None
        self._registrar_lectura()
        self._tarea_espera = loop.create_task(self._esperar_salida())

    @classmethod
    async def lanzar(
        cls,
        argv: list[str],
        cwd: str,
        entorno: dict[str, str],
        columnas: int,
        filas: int,
        al_leer: Callable[[bytes], None],
        al_salir: Callable[[int], None],
    ) -> ProcesoPty:
        loop = asyncio.get_running_loop()
        master, slave = pty.openpty()
        try:
            fcntl.ioctl(master, termios.TIOCSWINSZ, _winsize(columnas, filas))
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=cwd,
                env=entorno,
                start_new_session=True,
                preexec_fn=_tomar_terminal,
            )
        except Exception:
            os.close(slave)
            os.close(master)
            raise
        os.close(slave)
        flags = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        return cls(
            loop=loop,
            master=master,
            proc=proc,
            al_leer=al_leer,
            al_salir=al_salir,
        )

    @property
    def pid(self) -> int:
        return self._proc.pid

    @property
    def grupo(self) -> int:
        return self._proc.pid

    @property
    def codigo(self) -> int | None:
        return self._codigo

    @property
    def vivo(self) -> bool:
        return not self._cerrado and self._codigo is None

    @property
    def tarea_espera(self) -> asyncio.Task[None] | None:
        return self._tarea_espera

    def _registrar_lectura(self) -> None:
        if self._cerrado:
            return
        self._loop.add_reader(self._master, self._leer_master)

    def _sacar_lectura(self) -> None:
        try:
            self._loop.remove_reader(self._master)
        except (ValueError, OSError):
            pass

    def _leer_master(self) -> None:
        if self._cerrado:
            return
        try:
            datos = os.read(self._master, 65536)
        except BlockingIOError:
            return
        except OSError:
            self._sacar_lectura()
            return
        if not datos:
            self._sacar_lectura()
            return
        self._al_leer(datos)

    async def _esperar_salida(self) -> None:
        codigo = await self._proc.wait()
        self._codigo = codigo
        self._vaciar_master_final()
        self._cerrar_master()
        self._al_salir(codigo)

    def _vaciar_master_final(self) -> None:
        self._sacar_lectura()
        while not self._cerrado:
            try:
                datos = os.read(self._master, 65536)
            except BlockingIOError:
                break
            except OSError:
                break
            if not datos:
                break
            self._al_leer(datos)

    def _cerrar_master(self) -> None:
        if self._cerrado:
            return
        self._cerrado = True
        self._sacar_lectura()
        self._sacar_escritura()
        try:
            os.close(self._master)
        except OSError:
            pass

    def _sacar_escritura(self) -> None:
        if not self._writer_registrado:
            return
        try:
            self._loop.remove_writer(self._master)
        except (ValueError, OSError):
            pass
        self._writer_registrado = False

    def _intentar_escribir_pendiente(self) -> None:
        if self._cerrado or not self._pendiente:
            self._sacar_escritura()
            return
        try:
            n = os.write(self._master, self._pendiente)
        except BlockingIOError:
            return
        except OSError:
            self._cerrar_master()
            return
        del self._pendiente[:n]
        if not self._pendiente:
            self._sacar_escritura()

    def escribir(self, datos: bytes) -> None:
        if self._cerrado:
            raise ErrorProtocolo(NO_DISPONIBLE, "la sesión terminó")
        if not datos:
            return
        try:
            n = os.write(self._master, datos)
            resto = datos[n:]
        except BlockingIOError:
            resto = datos
        except OSError as exc:
            self._cerrar_master()
            raise ErrorProtocolo(NO_DISPONIBLE, "la sesión terminó") from exc
        if resto:
            if len(self._pendiente) + len(resto) > _TOPE_PENDIENTE:
                raise ErrorProtocolo(NO_DISPONIBLE, "la terminal no está leyendo")
            self._pendiente.extend(resto)
            if not self._writer_registrado:
                self._writer_registrado = True
                self._loop.add_writer(self._master, self._intentar_escribir_pendiente)

    def redimensionar(self, columnas: int, filas: int) -> None:
        if self._cerrado:
            return
        try:
            fcntl.ioctl(self._master, termios.TIOCSWINSZ, _winsize(columnas, filas))
            os.killpg(self.grupo, signal.SIGWINCH)
        except OSError:
            pass

    def senal(self, sig: int) -> None:
        """Al grupo del shell y al que tiene la terminal en primer plano (un `claude` a mano vive en otro grupo)."""
        grupos = [self.grupo]
        primero = self.grupo_primer_plano()
        if primero is not None and primero > 1 and primero != self.grupo and primero != os.getpgrp():
            grupos.insert(0, primero)
        for pgid in grupos:
            try:
                os.killpg(pgid, sig)
            except (ProcessLookupError, PermissionError):
                pass

    async def terminar(
        self,
        escalones: Sequence[tuple[int, float]] = (
            (signal.SIGHUP, 3.0),
            (signal.SIGTERM, 3.0),
        ),
    ) -> int | None:
        if self._codigo is not None:
            return self._codigo
        if self._tarea_espera is None:
            return self._codigo
        for sig, tiempo in escalones:
            if self._codigo is not None:
                return self._codigo
            self.senal(sig)
            try:
                await asyncio.wait_for(asyncio.shield(self._tarea_espera), tiempo)
            except asyncio.TimeoutError:
                pass
        if self._codigo is None:
            self.senal(signal.SIGKILL)
            try:
                await asyncio.wait_for(asyncio.shield(self._tarea_espera), 5.0)
            except asyncio.TimeoutError:
                pass
        return self._codigo

    def grupo_primer_plano(self) -> int | None:
        if self._cerrado:
            return None
        try:
            return os.tcgetpgrp(self._master)
        except OSError:
            return None

    def primer_plano(self) -> dict:
        pgid = self.grupo_primer_plano()
        if pgid is None:
            return {}
        out: dict = {"pid": pgid, "comando": None, "argv": None, "cwd": None}
        cmdline_path = f"/proc/{pgid}/cmdline"
        try:
            with open(cmdline_path, "rb") as fh:
                raw = fh.read()
            argv = [p.decode("utf-8", errors="replace") for p in raw.split(b"\0") if p]
            out["argv"] = argv
            if argv:
                out["comando"] = os.path.basename(argv[0])
        except OSError:
            pass
        try:
            out["cwd"] = os.readlink(f"/proc/{pgid}/cwd")
        except OSError:
            pass
        return out
