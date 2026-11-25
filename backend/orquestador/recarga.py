"""Recarga `/reload-plugins --force` en sesiones Claude del guardián (actualizador del kit de trabajo)."""
from __future__ import annotations

import asyncio
import errno
import json
import logging
import os
import socket
import stat
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .enchufe.base import NoTomado
from .enchufe.ids import es_guardian
from .ganchos.canal import mismo_uid, preparar_directorio

log = logging.getLogger(__name__)

TEXTO_RECARGA = "/reload-plugins --force"
ESPERA_MAX_S = 4 * 3600
TIMEOUT_CLIENTE = 5.0
_JSON_KW = {"ensure_ascii": False, "separators": (",", ":")}


@dataclass(frozen=True)
class SesionInfo:
    pane_id: str
    kind: str
    estado: str
    asks_user: bool = False


def ruta_socket(environ: dict | None = None) -> Path | None:
    base = (environ if environ is not None else os.environ).get("XDG_RUNTIME_DIR")
    if not base:
        return None
    return Path(base) / "colmena" / "recarga.sock"


def estado_efectivo(s: SesionInfo) -> str:
    if s.estado in ("terminada", "perdida"):
        return s.estado
    if s.asks_user and s.estado != "blocked":
        return "asks"
    return s.estado


def _listo(efectivo: str) -> bool:
    return efectivo in ("idle", "done")


def _esperar(efectivo: str) -> bool:
    return efectivo in ("working", "blocked", "asks")


class RecargaService:
    def __init__(
        self,
        *,
        sesiones: Callable[[], list[SesionInfo]],
        mandar: Callable[[str, str], Awaitable[None]],
        marcar_silencio: Callable[[], None],
        clock: Callable[[], float] = time.time,
        self_pane: Callable[[], str | None] = lambda: None,
        protected_panes: Callable[[], set[str]] = lambda: set(),
        al_escribir: Callable[[str], None] = lambda pane: None,
    ) -> None:
        self._al_escribir = al_escribir
        self._sesiones = sesiones
        self._mandar = mandar
        self._marcar_silencio = marcar_silencio
        self._clock = clock
        self._self_pane = self_pane
        self._protected_panes = protected_panes
        self._pendientes: dict[str, float] = {}
        self._enviando: set[str] = set()
        self._tareas_envio: set[asyncio.Task[None]] = set()

    @property
    def pendientes(self) -> dict[str, float]:
        return dict(self._pendientes)

    def _registrar_tarea(self, tarea: asyncio.Task[None]) -> None:
        self._tareas_envio.add(tarea)
        tarea.add_done_callback(self._tareas_envio.discard)

    async def esperar_envios(self) -> None:
        tareas = list(self._tareas_envio)
        if tareas:
            await asyncio.gather(*tareas, return_exceptions=True)

    def _descartar_vencidas(self) -> None:
        ahora = self._clock()
        for pane, vence in list(self._pendientes.items()):
            if ahora > vence:
                log.info("recarga pendiente vencida para %s", pane)
                del self._pendientes[pane]

    def _info_por_pane(self) -> dict[str, SesionInfo]:
        out: dict[str, SesionInfo] = {}
        for s in self._sesiones():
            if not es_guardian(s.pane_id):
                continue
            if s.kind != "claude":
                continue
            if s.estado in ("terminada", "perdida"):
                continue
            out[s.pane_id] = s
        return out

    def _excluida(self, pane_id: str) -> bool:
        propio = self._self_pane()
        if propio and pane_id == propio:
            return True
        return pane_id in self._protected_panes()

    def _avisar_escritura(self, pane_id: str) -> None:
        try:
            self._al_escribir(pane_id)
        except Exception:
            log.warning("al_escribir falló", exc_info=True)

    async def _mandar_recarga(self, pane_id: str) -> bool:
        self._marcar_silencio()
        try:
            self._avisar_escritura(pane_id)
            await self._mandar(pane_id, TEXTO_RECARGA)
        except NoTomado:
            log.info("recarga enviada a %s sin confirmación de toma", pane_id)
            return True
        except Exception:
            log.exception("no se pudo recargar sesión %s", pane_id)
            return False
        return True

    async def _recargar(self, pane_id: str, *, solo_si_pendiente: bool = False) -> bool:
        if self._excluida(pane_id):
            return False
        if pane_id in self._enviando:
            return False
        vence = self._pendientes.pop(pane_id, None)
        if solo_si_pendiente and vence is None:
            return False
        self._enviando.add(pane_id)
        try:
            return await self._mandar_recarga(pane_id)
        finally:
            self._enviando.discard(pane_id)

    async def _enviar_lote(self, panes: list[str]) -> None:
        async def uno(pane_id: str) -> None:
            try:
                await self._mandar_recarga(pane_id)
            finally:
                self._enviando.discard(pane_id)

        await asyncio.gather(*(uno(p) for p in panes))

    async def pedir(self) -> tuple[int, int]:
        self._descartar_vencidas()
        por_pane = self._info_por_pane()
        recargadas = 0
        esperando = 0
        ahora = self._clock()
        a_recargar: list[str] = []
        for pane_id, s in por_pane.items():
            efectivo = estado_efectivo(s)
            if _listo(efectivo):
                if self._excluida(pane_id):
                    continue
                if pane_id in self._enviando:
                    continue
                self._pendientes.pop(pane_id, None)
                self._enviando.add(pane_id)
                a_recargar.append(pane_id)
                recargadas += 1
            elif _esperar(efectivo):
                if pane_id not in self._pendientes:
                    self._pendientes[pane_id] = ahora + ESPERA_MAX_S
                esperando += 1
        self._marcar_silencio()
        if a_recargar:
            tarea = asyncio.create_task(self._enviar_lote(a_recargar))
            self._registrar_tarea(tarea)
        return recargadas, esperando

    async def al_cambio(self, pane_id: str | None = None) -> None:
        self._descartar_vencidas()
        por_pane = self._info_por_pane()
        candidatos = (
            [pane_id]
            if pane_id is not None and pane_id in self._pendientes
            else list(self._pendientes)
        )
        for pid in candidatos:
            if pid not in self._pendientes:
                continue
            s = por_pane.get(pid)
            if s is None:
                continue
            efectivo = estado_efectivo(s)
            if _listo(efectivo):
                await self._recargar(pid, solo_si_pendiente=True)


class ServidorRecarga:
    def __init__(
        self,
        pedir: Callable[[], Awaitable[tuple[int, int]]],
        verificar: Callable[[object], bool] = mismo_uid,
    ) -> None:
        self._pedir = pedir
        self._verificar = verificar
        self._server: asyncio.Server | None = None

    async def _cerrar_writer(self, writer: asyncio.StreamWriter) -> None:
        if not writer.is_closing():
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _responder(self, writer: asyncio.StreamWriter, respuesta: dict) -> None:
        try:
            linea = json.dumps(respuesta, **_JSON_KW) + "\n"
            writer.write(linea.encode())
            await writer.drain()
        except (ConnectionError, OSError, ValueError, TypeError):
            pass
        await self._cerrar_writer(writer)

    async def atender(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            if not self._verificar(writer):
                await self._cerrar_writer(writer)
                return
            try:
                linea = await reader.readline()
            except (asyncio.LimitOverrunError, ValueError):
                await self._responder(writer, {"ok": False, "error": "pedido inválido"})
                return
            if not linea.endswith(b"\n"):
                await self._responder(writer, {"ok": False, "error": "pedido inválido"})
                return
            try:
                data = json.loads(linea.decode())
            except (UnicodeDecodeError, json.JSONDecodeError):
                await self._responder(writer, {"ok": False, "error": "JSON inválido"})
                return
            if not isinstance(data, dict) or data.get("op") != "recargar":
                await self._responder(writer, {"ok": False, "error": "operación desconocida"})
                return
            recargadas, esperando = await self._pedir()
            await self._responder(
                writer,
                {"ok": True, "recargadas": recargadas, "esperando": esperando},
            )
        except Exception:
            log.exception("error atendiendo recarga")
            await self._cerrar_writer(writer)

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
            self._server = await asyncio.start_unix_server(self.atender, sock=sock, limit=4096)
        except Exception:
            sock.close()
            try:
                ruta.unlink()
            except OSError:
                pass
            raise

    async def cerrar(self) -> None:
        server = self._server
        if server is not None:
            server.close()
            try:
                await asyncio.wait_for(server.wait_closed(), 2)
            except asyncio.TimeoutError:
                log.warning("timeout cerrando servidor de recarga")
            self._server = None


def cliente_recargar(ruta: Path, timeout: float = TIMEOUT_CLIENTE) -> tuple[bool, dict[str, Any]]:
    """Devuelve (ok, payload). offline=True si Colmena no escucha."""
    if not ruta.exists():
        return False, {"offline": True}
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(str(ruta))
        sock.sendall(b'{"op":"recargar"}\n')
        buf = b""
        while b"\n" not in buf and len(buf) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        if not buf:
            return False, {"offline": True}
        linea = buf.split(b"\n", 1)[0]
        return True, json.loads(linea.decode())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False, {"offline": True}
    finally:
        sock.close()


def sesiones_desde_board(board: dict | None) -> list[SesionInfo]:
    if not board:
        return []
    out: list[SesionInfo] = []
    for ws in board.get("workspaces", []):
        for tab in ws.get("tabs", []):
            for agent in tab.get("agents", []):
                pane = agent.get("pane_id")
                if not isinstance(pane, str):
                    continue
                out.append(
                    SesionInfo(
                        pane,
                        str(agent.get("kind") or "unknown"),
                        str(agent.get("status") or "unknown"),
                        bool(agent.get("asks_user")),
                    )
                )
    return out
