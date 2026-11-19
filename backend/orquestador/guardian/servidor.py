from __future__ import annotations

import asyncio
import errno
import logging
import os
import socket
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from orquestador.ganchos.canal import mismo_uid, preparar_directorio
from orquestador.guardian.lanzador import MODOS_POR_LANZAMIENTO
from orquestador.guardian.nucleo import Escucha, Guardian
from orquestador.guardian.protocolo import (
    INTERNO,
    INVALIDO,
    MAX_LINEA,
    VERSION,
    ErrorProtocolo,
    codificar,
    leer_pedido,
    respuesta_error,
    respuesta_ok,
)

log = logging.getLogger(__name__)

_MAX_PENDIENTE = 8 << 20
_FIN_ESCRITOR = object()


@dataclass
class _Conexion:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    servidor: ServidorGuardian
    escucha: Escucha | None = None
    cola: asyncio.Queue = field(default_factory=asyncio.Queue)
    pendiente: int = 0
    tarea_escritor: asyncio.Task | None = None
    tareas_pedidos: set[asyncio.Task] = field(default_factory=set)
    cerrada: bool = False


class ServidorGuardian:
    def __init__(
        self,
        guardian: Guardian,
        version_guardian: str,
        al_pedir_apagado: Callable[[], None],
    ) -> None:
        self._guardian = guardian
        self._version = version_guardian
        self._al_pedir_apagado = al_pedir_apagado
        self._server: asyncio.Server | None = None
        self._ruta: Path | None = None
        self._conexiones: list[_Conexion] = []
        self._cierres: set[asyncio.Task] = set()

    async def _aceptar(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if not mismo_uid(writer):
            if not writer.is_closing():
                writer.close()
            return
        await self.atender(reader, writer)

    async def atender(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        conn = _Conexion(reader=reader, writer=writer, servidor=self)
        self._conexiones.append(conn)
        conn.tarea_escritor = asyncio.create_task(self._escritor(conn))
        try:
            while not conn.cerrada:
                try:
                    linea = await reader.readuntil(b"\n")
                except asyncio.IncompleteReadError:
                    break
                except asyncio.LimitOverrunError:
                    break
                tarea = asyncio.create_task(self._procesar_pedido(conn, linea))
                conn.tareas_pedidos.add(tarea)
                tarea.add_done_callback(conn.tareas_pedidos.discard)
        finally:
            if conn.tareas_pedidos:
                await asyncio.gather(*list(conn.tareas_pedidos), return_exceptions=True)
            await self._cerrar_conexion(conn)

    async def _escritor(self, conn: _Conexion) -> None:
        try:
            while True:
                item = await conn.cola.get()
                if item is _FIN_ESCRITOR:
                    break
                try:
                    conn.writer.write(item)
                    await conn.writer.drain()
                except (ConnectionError, OSError):
                    break
                finally:
                    conn.pendiente -= len(item)
        except asyncio.CancelledError:
            pass

    def _encolar(self, conn: _Conexion, mensaje: dict, *, salida_vivo: bool = False) -> None:
        if conn.cerrada:
            return
        try:
            payload = codificar(mensaje)
        except ErrorProtocolo:
            return
        n = len(payload)
        if salida_vivo and conn.pendiente + n > MAX_LINEA:
            self._cortar_vivo(conn, mensaje.get("seq", 0))
            return
        if conn.pendiente + n > _MAX_PENDIENTE:
            log.warning("cola de escritura del guardián superó el tope; cierro conexión")
            tarea = asyncio.create_task(self._cerrar_conexion(conn))
            self._cierres.add(tarea)
            tarea.add_done_callback(self._cierres.discard)
            return
        conn.pendiente += n
        conn.cola.put_nowait(payload)

    def _cortar_vivo(self, conn: _Conexion, seq: int) -> None:
        if conn.escucha is None:
            return
        cortadas = set(conn.escucha.salida)
        conn.escucha.salida.clear()
        for sid in cortadas:
            self._encolar(
                conn,
                {"evento": "vivo_cortado", "seq": seq, "sesion": sid},
            )

    async def _responder(self, conn: _Conexion, id: int, res: dict) -> None:
        self._encolar(conn, respuesta_ok(id, res))

    async def _responder_error(
        self, conn: _Conexion, id: int, codigo: str, mensaje: str
    ) -> None:
        self._encolar(conn, respuesta_error(id, codigo, mensaje))

    async def _procesar_pedido(self, conn: _Conexion, linea: bytes) -> None:
        pedido_id: int | None = None
        try:
            pedido_id, op, args = leer_pedido(linea)
            res = await self._ejecutar(conn, pedido_id, op, args)
            await self._responder(conn, pedido_id, res)
        except ErrorProtocolo as exc:
            id_resp = pedido_id if pedido_id is not None else exc.id
            if id_resp is not None:
                await self._responder_error(conn, id_resp, exc.codigo, exc.mensaje)
            else:
                await self._cerrar_conexion(conn)
        except Exception:
            log.exception("error interno en pedido del guardián")
            if pedido_id is not None:
                await self._responder_error(conn, pedido_id, INTERNO, "error interno")

    async def _ejecutar(
        self, conn: _Conexion, pedido_id: int, op: str, args: dict
    ) -> dict:
        g = self._guardian
        if op == "hola":
            return {
                "protocolo": VERSION,
                "guardian": self._version,
                "pid": os.getpid(),
            }
        if op == "tablero":
            return g.tablero()
        if op == "crear_espacio":
            nombre = _exigir_str(args, "nombre", pedido_id)
            cwd = _exigir_str(args, "cwd", pedido_id)
            return await g.crear_espacio(nombre, cwd)
        if op == "crear_linea":
            espacio_id = _exigir_str(args, "espacio_id", pedido_id)
            nombre = _exigir_str(args, "nombre", pedido_id)
            cwd = _exigir_str(args, "cwd", pedido_id)
            programa = args.get("programa", "shell")
            if programa is not None and not isinstance(programa, str):
                raise ErrorProtocolo(INVALIDO, "programa inválido", pedido_id)
            resume = args.get("resume")
            if resume is not None and not isinstance(resume, str):
                raise ErrorProtocolo(INVALIDO, "resume inválido", pedido_id)
            return await g.crear_linea(
                espacio_id,
                nombre,
                cwd,
                programa=programa or "shell",
                resume=resume,
            )
        if op == "arrancar_claude":
            sesion_id = _exigir_str(args, "sesion_id", pedido_id)
            nombre = _exigir_str(args, "nombre", pedido_id)
            resume = args.get("resume")
            if resume is not None and not isinstance(resume, str):
                raise ErrorProtocolo(INVALIDO, "resume inválido", pedido_id)
            modo = args.get("modo")
            if modo is not None and (not isinstance(modo, str) or modo not in MODOS_POR_LANZAMIENTO):
                raise ErrorProtocolo(INVALIDO, "modo inválido", pedido_id)
            if modo is None:
                return await g.arrancar_claude(sesion_id, nombre, resume=resume)
            return await g.arrancar_claude(sesion_id, nombre, resume=resume, modo=modo)
        if op == "renombrar":
            objetivo_id = _exigir_str(args, "objetivo_id", pedido_id)
            nombre = _exigir_str(args, "nombre", pedido_id)
            g.renombrar(objetivo_id, nombre)
            return {}
        if op == "cerrar":
            objetivo_id = _exigir_str(args, "objetivo_id", pedido_id)
            await g.cerrar(objetivo_id)
            return {}
        if op == "leer":
            sesion_id = _exigir_str(args, "sesion_id", pedido_id)
            fuente = args.get("fuente", "visible")
            formato = args.get("formato", "texto")
            lineas = args.get("lineas")
            if fuente is not None and not isinstance(fuente, str):
                raise ErrorProtocolo(INVALIDO, "fuente inválida", pedido_id)
            if formato is not None and not isinstance(formato, str):
                raise ErrorProtocolo(INVALIDO, "formato inválido", pedido_id)
            if lineas is not None and (isinstance(lineas, bool) or not isinstance(lineas, int)):
                raise ErrorProtocolo(INVALIDO, "lineas inválido", pedido_id)
            texto = g.leer(
                sesion_id,
                fuente=fuente or "visible",
                formato=formato or "texto",
                lineas=lineas,
            )
            return {"texto": texto}
        if op == "escribir":
            sesion_id = _exigir_str(args, "sesion_id", pedido_id)
            texto = _exigir_str(args, "texto", pedido_id)
            g.escribir(sesion_id, texto)
            return {}
        if op == "teclas":
            sesion_id = _exigir_str(args, "sesion_id", pedido_id)
            teclas = args.get("teclas")
            if not isinstance(teclas, list) or not all(isinstance(t, str) for t in teclas):
                raise ErrorProtocolo(INVALIDO, "teclas inválido", pedido_id)
            g.teclas(sesion_id, teclas)
            return {}
        if op == "mandar_prompt":
            sesion_id = _exigir_str(args, "sesion_id", pedido_id)
            texto = _exigir_str(args, "texto", pedido_id)
            await g.mandar_prompt(sesion_id, texto)
            return {}
        if op == "interrumpir":
            sesion_id = _exigir_str(args, "sesion_id", pedido_id)
            g.interrumpir(sesion_id)
            return {}
        if op == "ejecutar":
            sesion_id = _exigir_str(args, "sesion_id", pedido_id)
            comando = _exigir_str(args, "comando", pedido_id)
            g.ejecutar(sesion_id, comando)
            return {}
        if op == "proceso":
            sesion_id = _exigir_str(args, "sesion_id", pedido_id)
            return g.proceso(sesion_id)
        if op == "redimensionar":
            sesion_id = _exigir_str(args, "sesion_id", pedido_id)
            columnas = _exigir_int(args, "columnas", pedido_id)
            filas = _exigir_int(args, "filas", pedido_id)
            g.redimensionar(sesion_id, columnas, filas)
            return {}
        if op == "suscribir":
            ids = (
                _exigir_ids_sesion(args, "salida", pedido_id)
                if "salida" in args
                else []
            )
            foto = args.get("foto")
            if foto is not None and not isinstance(foto, bool):
                raise ErrorProtocolo(INVALIDO, "foto inválido", pedido_id)
            return self._suscribir(conn, ids, con_foto=foto is True)
        if op == "desuscribir":
            if "salida" not in args:
                self._desuscribir(conn, None)
            else:
                ids = _exigir_ids_sesion(args, "salida", pedido_id)
                self._desuscribir(conn, ids)
            return {}
        if op == "apagar_ordenado":
            loop = asyncio.get_running_loop()
            loop.call_soon(self._al_pedir_apagado)
            return {}
        raise ErrorProtocolo(INVALIDO, "operación inválida", pedido_id)

    def _suscribir(self, conn: _Conexion, ids: list[str], *, con_foto: bool = False) -> dict:
        salida = set(ids)
        fotos: dict[str, dict] | None = None
        if con_foto:
            # Síncrono: la foto y el alta de escucha deben ser atómicos respecto de la salida del PTY.
            fotos = {sid: self._guardian.foto(sid) for sid in ids}

        def _cb(evento: dict) -> None:
            es_salida = evento.get("evento") == "salida"
            self._encolar(conn, evento, salida_vivo=es_salida)

        if conn.escucha is None:
            conn.escucha = self._guardian.escuchar(_cb, salida)
        else:
            conn.escucha.salida.clear()
            conn.escucha.salida.update(salida)
        res: dict = {"seq": self._guardian.seq}
        if fotos is not None:
            res["fotos"] = fotos
        return res

    def _desuscribir(self, conn: _Conexion, ids: list[str] | None) -> None:
        if conn.escucha is None:
            return
        if ids is None:
            conn.escucha.cerrar()
            conn.escucha = None
            return
        for sid in ids:
            conn.escucha.salida.discard(sid)

    async def _cerrar_conexion(self, conn: _Conexion) -> None:
        if conn.cerrada:
            return
        conn.cerrada = True
        if conn in self._conexiones:
            self._conexiones.remove(conn)
        if conn.escucha is not None:
            conn.escucha.cerrar()
            conn.escucha = None
        actual = asyncio.current_task()
        otras = [t for t in list(conn.tareas_pedidos) if t is not actual]
        for t in otras:
            t.cancel()
        if otras:
            await asyncio.gather(*otras, return_exceptions=True)
        if conn.tarea_escritor is not None:
            conn.cola.put_nowait(_FIN_ESCRITOR)
            await asyncio.gather(conn.tarea_escritor, return_exceptions=True)
        if not conn.writer.is_closing():
            conn.writer.close()
            try:
                await conn.writer.wait_closed()
            except OSError:
                pass

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
                raise OSError(
                    errno.EEXIST, "La ruta del socket no es un socket unix", str(ruta)
                )
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
                self._aceptar, sock=sock, limit=MAX_LINEA + 1
            )
            self._ruta = ruta
        except Exception:
            sock.close()
            try:
                ruta.unlink()
            except OSError:
                pass
            raise

    async def cerrar(self) -> None:
        for conn in list(self._conexiones):
            await self._cerrar_conexion(conn)
        server = self._server
        if server is not None:
            server.close()
            try:
                await asyncio.wait_for(server.wait_closed(), 2)
            except asyncio.TimeoutError:
                log.warning("timeout cerrando servidor del guardián")
            self._server = None
        ruta = self._ruta
        self._ruta = None
        if ruta is not None:
            try:
                st = os.lstat(ruta)
                if stat.S_ISSOCK(st.st_mode):
                    ruta.unlink()
            except OSError:
                pass


def _exigir_str(args: dict, clave: str, pedido_id: int) -> str:
    if clave not in args:
        raise ErrorProtocolo(INVALIDO, f"falta {clave}", pedido_id)
    valor = args[clave]
    if not isinstance(valor, str):
        raise ErrorProtocolo(INVALIDO, f"{clave} inválido", pedido_id)
    return valor


def _exigir_int(args: dict, clave: str, pedido_id: int) -> int:
    if clave not in args:
        raise ErrorProtocolo(INVALIDO, f"falta {clave}", pedido_id)
    valor = args[clave]
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErrorProtocolo(INVALIDO, f"{clave} inválido", pedido_id)
    return valor


def _exigir_ids_sesion(args: dict, clave: str, pedido_id: int) -> list[str]:
    if clave not in args:
        raise ErrorProtocolo(INVALIDO, f"falta {clave}", pedido_id)
    valor = args[clave]
    if not isinstance(valor, list) or not all(isinstance(x, str) for x in valor):
        raise ErrorProtocolo(INVALIDO, f"{clave} inválido", pedido_id)
    return valor
