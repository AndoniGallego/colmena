"""Almacén de pedidos del nudo: una sesión de Claude pide a la PC de Ando que lea o señale controles."""
from __future__ import annotations

import asyncio
import errno
import hmac
import json
import logging
import os
import re
import secrets
import socket
import stat
import time
import unicodedata
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Optional

from .ganchos.canal import mismo_uid, preparar_directorio

log = logging.getLogger(__name__)

TIPOS = frozenset({"boton", "enlace", "menu", "item_menu", "pestana", "casilla", "radio", "campo", "combo",
                   "lista", "item_lista", "item_arbol", "deslizador"})
ERRORES_PC = frozenset({"apagado", "sin_ventana", "sin_controles", "foto_vieja", "sin_control", "invalido",
                        "fallo_pc"})
RESULTADOS = frozenset({"ok", "listo", "usado", "salir", "vencido"})
OPERACIONES = frozenset({"controles", "senalar", "marcar", "limpiar", "estado", "senalar_zona", "marcar_zonas"})
OPS_ZONA = frozenset({"senalar_zona", "marcar_zonas"})
OPS_DIBUJO = frozenset({"senalar", "marcar", "senalar_zona", "marcar_zonas"})
TEXTO_MAX = 120
ETIQUETA_MAX = 40
MARCAS_MAX = 8
CONTROLES_MAX = 150
NOMBRE_CONTROL_MAX = 200
NOMBRE_SESION_MAX = 60
ESPERA_DEFAULT_S = 120
ESPERA_MAX_S = 600
INACTIVIDAD_DUENO_S = 120.0
FOTO_VIDA_S = 300.0
VENCE_LECTURA_S = 15.0
VENCE_S = 10.0
MARGEN_ESPERA_S = 15.0
SESION_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")

MENSAJES = {
    "apagado": "El nudo está apagado en la PC.",
    "sin_pc": "La app de Colmena en la PC no está conectada.",
    "sin_ventana": "No hay una ventana para leer.",
    "sin_controles": "No encontré controles en la ventana.",
    "foto_vieja": "La lectura quedó vieja: pedí los controles de nuevo.",
    "sin_control": "Ese control ya no está.",
    "ocupado": "Ocupado.",
    "en_curso": "Hay otro pedido en curso.",
    "vencido": "La PC no contestó a tiempo.",
    "invalido": "Pedido inválido.",
    "fallo_pc": "Falló algo en la PC.",
}


class NudoError(Exception):
    def __init__(self, codigo: str, mensaje: Optional[str] = None):
        self.codigo = codigo
        self.mensaje = mensaje or MENSAJES.get(codigo, codigo)
        super().__init__(self.mensaje)


def _con_control(t: str) -> bool:
    return any(unicodedata.category(c) in ("Cc", "Cf", "Cs", "Zl", "Zp") for c in t)


def validar_texto(t: object, maximo: int) -> str:
    if not isinstance(t, str):
        raise ValueError("el texto tiene que ser una cadena")
    if _con_control(t):
        raise ValueError("el texto tiene que ser de una sola línea y sin caracteres de control")
    t = t.strip()
    if not t:
        raise ValueError("el texto no puede estar vacío")
    if len(t) > maximo:
        raise ValueError(f"el texto no puede pasar de {maximo} caracteres")
    return t


def _entero(v: object, minimo: int, que: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < minimo:
        raise ValueError(f"{que} inválido")
    return v


def _zona(z: object) -> dict:
    if not isinstance(z, dict):
        raise ValueError("zona inválida")
    return {"x": _entero(z.get("x"), 0, "x"), "y": _entero(z.get("y"), 0, "y"),
            "ancho": _entero(z.get("ancho"), 1, "ancho"), "alto": _entero(z.get("alto"), 1, "alto")}


def validar_args(op: str, args: dict) -> dict:
    if op not in OPERACIONES:
        raise ValueError("operación desconocida")
    if not isinstance(args, dict):
        raise ValueError("argumentos inválidos")
    if op == "senalar":
        esperar = args.get("esperar")
        if esperar is not None:
            esperar = _entero(esperar, 0, "esperar")
            if esperar == 0:
                esperar = ESPERA_DEFAULT_S
            if esperar > ESPERA_MAX_S:
                raise ValueError(f"esperar no puede pasar de {ESPERA_MAX_S} s")
        return {"n": _entero(args.get("n"), 1, "n"), "texto": validar_texto(args.get("texto"), TEXTO_MAX),
                "esperar": esperar}
    if op == "marcar":
        marcas = args.get("marcas")
        if not isinstance(marcas, list) or not 1 <= len(marcas) <= MARCAS_MAX:
            raise ValueError(f"hay que marcar entre 1 y {MARCAS_MAX} controles")
        out, vistos = [], set()
        for m in marcas:
            if not isinstance(m, dict):
                raise ValueError("marca inválida")
            n = _entero(m.get("n"), 1, "n")
            if n in vistos:
                raise ValueError("marca repetida")
            vistos.add(n)
            out.append({"n": n, "etiqueta": validar_texto(m.get("etiqueta"), ETIQUETA_MAX)})
        return {"marcas": out}
    if op == "senalar_zona":
        return {"zona": _zona(args.get("zona")), "texto": validar_texto(args.get("texto"), TEXTO_MAX)}
    if op == "marcar_zonas":
        zonas = args.get("zonas")
        if not isinstance(zonas, list) or not 1 <= len(zonas) <= MARCAS_MAX:
            raise ValueError(f"hay que marcar entre 1 y {MARCAS_MAX} zonas")
        return {"zonas": [dict(_zona(z), etiqueta=validar_texto(z.get("etiqueta"), ETIQUETA_MAX)) for z in zonas]}
    return {}


def _texto_pc(v: object, maximo: int, vacio: bool = False) -> str:
    if not isinstance(v, str):
        raise ValueError("texto inválido en la respuesta de la PC")
    t = " ".join("".join(" " if _con_control(c) else c for c in v).split())[:maximo].strip()
    if not t and not vacio:
        raise ValueError("texto vacío en la respuesta de la PC")
    return t


def _validar_controles(r: object) -> dict:
    if not isinstance(r, dict):
        raise ValueError("respuesta inválida")
    foto = _entero(r.get("foto"), 0, "foto")
    ventana = r.get("ventana")
    if not isinstance(ventana, dict) or set(ventana) != {"titulo", "proceso"}:
        raise ValueError("ventana inválida")
    controles = r.get("controles")
    if not isinstance(controles, list) or not 1 <= len(controles) <= CONTROLES_MAX:
        raise ValueError("lista de controles inválida")
    lista = []
    for c in controles:
        if not isinstance(c, dict) or set(c) != {"n", "tipo", "nombre"}:
            raise ValueError("control inválido")
        if c["tipo"] not in TIPOS:
            raise ValueError("tipo de control desconocido")
        lista.append({"n": _entero(c["n"], 1, "n"), "tipo": c["tipo"],
                      "nombre": _texto_pc(c["nombre"], NOMBRE_CONTROL_MAX, vacio=True)})
    return {"foto": foto,
            "ventana": {"titulo": _texto_pc(ventana["titulo"], 300, True),
                        "proceso": _texto_pc(ventana["proceso"], 300, True)},
            "monitor": _texto_pc(r.get("monitor"), 60), "controles": lista}


def validar_respuesta(op: str, resultado: object) -> dict:
    if isinstance(resultado, dict) and "error" in resultado:
        if set(resultado) != {"error"} or resultado["error"] not in ERRORES_PC:
            raise ValueError("error desconocido")
        return {"error": resultado["error"]}
    if op == "controles":
        return _validar_controles(resultado)
    if op == "estado":
        if (not isinstance(resultado, dict) or set(resultado) != {"prendido", "se_ve_al_compartir"}
                or not all(isinstance(v, bool) for v in resultado.values())):
            raise ValueError("estado inválido")
        return dict(resultado)
    if op in ("senalar", "marcar", "limpiar", "senalar_zona", "marcar_zonas"):
        if isinstance(resultado, dict):
            if set(resultado) != {"resultado"}:
                raise ValueError("resultado inválido")
            resultado = resultado["resultado"]
        permitidos = RESULTADOS if op == "senalar" else {"ok"}
        if not isinstance(resultado, str) or resultado not in permitidos:
            raise ValueError("resultado desconocido")
        return {"resultado": resultado}
    raise ValueError("operación desconocida")


def _limpio(t: object) -> str:
    texto = "".join(" " if _con_control(c) else c for c in str(t or ""))
    return " ".join(texto.split())[:NOMBRE_SESION_MAX].strip()


def _respaldo(sesion: str) -> str:
    return sesion[:NOMBRE_SESION_MAX]


def nombre_sesion(board: Optional[dict], sesion: str) -> str:
    for ws in (board or {}).get("workspaces", []):
        for tab in ws.get("tabs", []):
            for agent in tab.get("agents", []):
                if agent.get("pane_id") == sesion:
                    return _limpio(agent.get("title")) or _respaldo(sesion)
    return _respaldo(sesion)


class _Pedido:
    def __init__(self, pid: str, token: str, device: str, sesion: str, op: str, fut: asyncio.Future,
                 nombre: str = ""):
        self.pid, self.token, self.device, self.sesion, self.op, self.fut = pid, token, device, sesion, op, fut
        self.nombre = nombre
        self.usado = False


class NudoStore:
    def __init__(self, ofrecer: Callable[[object, tuple], None], clock: Callable[[], float] = time.monotonic,
                 token: Callable[[], str] = lambda: secrets.token_urlsafe(24), vence_s: float = VENCE_S,
                 vence_lectura_s: float = VENCE_LECTURA_S,
                 es_guia: Callable[[str], bool] | None = None):
        self.es_guia: Callable[[str], bool] = es_guia or (lambda sesion: False)
        self._ofrecer = ofrecer
        self._clock = clock
        self._token = token
        self._vence_s = vence_s
        self._vence_lectura_s = vence_lectura_s
        self._pcs: list[tuple[str, object]] = []
        self._pend: Optional[_Pedido] = None
        self._pend_estado: Optional[_Pedido] = None
        self._pend_interno: Optional[_Pedido] = None
        self._dueno: Optional[list] = None  # [sesion, nombre, ultima_actividad]
        self._fotos: dict[str, tuple[int, float]] = {}
        self._imagenes: dict[str, tuple[int, int]] = {}
        self._timer: Optional[asyncio.TimerHandle] = None

    def pc_conectada(self, device: str, cola: object) -> None:
        if (device, cola) not in self._pcs:
            self._pcs.append((device, cola))
        if self._dueno is None and self._pend is None:
            self._limpiar_interno(device, cola)

    def _limpiar_interno(self, device: str, cola: object) -> None:
        """Limpia la pantalla de la PC recién conectada. Va registrado aparte (`_pend_interno`) para que la
        respuesta de la PC se acepte; no bloquea a las sesiones: sus operaciones de dibujo piden antes una lectura."""
        ev = {"id": secrets.token_urlsafe(12), "token": self._token(), "op": "limpiar", "args": {}, "sesion": ""}
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._ofrecer(cola, ("nudo", ev))
            return
        p = _Pedido(ev["id"], ev["token"], device, "", "limpiar", loop.create_future(), "")
        if self._pend_interno and not self._pend_interno.fut.done():
            self._pend_interno.fut.cancel()
        self._pend_interno = p
        timer = loop.call_later(self._vence_s, self._cancelar_interno, p)

        def terminado(f: asyncio.Future) -> None:
            timer.cancel()
            if not f.cancelled():
                f.exception()
            self._soltar(p)

        p.fut.add_done_callback(terminado)
        self._ofrecer(cola, ("nudo", ev))

    def _cancelar_interno(self, p: _Pedido) -> None:
        if not p.fut.done():
            p.fut.cancel()

    def pc_desconectada(self, device: str, cola: object) -> None:
        self._pcs = [p for p in self._pcs if p != (device, cola)]
        if not self._pcs:
            self._liberar(limpiar=False)
            self._fotos.clear()
            self._imagenes.clear()
        for p in (self._pend, self._pend_estado, self._pend_interno):
            if p and p.device == device and not any(d == device for d, _ in self._pcs) and not p.fut.done():
                p.fut.set_exception(NudoError("sin_pc"))

    def _buscar(self, pid: str) -> Optional[_Pedido]:
        for p in (self._pend, self._pend_estado, self._pend_interno):
            if p and p.pid == pid:
                return p
        return None

    def op_de(self, pid: str) -> Optional[str]:
        p = self._buscar(pid)
        return p.op if p and not p.usado else None

    def pc_objetivo(self) -> Optional[str]:
        return self._pcs[-1][0] if self._pcs else None

    def dueno(self) -> Optional[tuple[str, str]]:
        self.expirar()
        return (self._dueno[0], self._dueno[1]) if self._dueno else None

    def expirar(self) -> None:
        d = self._dueno
        if d is None:
            return
        if self._pend and self._pend.sesion == d[0]:
            d[2] = self._clock()
        elif self.es_guia(d[0]):
            d[2] = self._clock()  # la guía se libera con su propio apagado, no por inactividad del nudo
        elif self._clock() - d[2] > INACTIVIDAD_DUENO_S:
            self._liberar(limpiar=True)

    def salir(self, device: str) -> None:
        self._liberar(limpiar=False)

    def soltar(self, limpiar: bool = True) -> None:
        self._liberar(limpiar=limpiar)

    def cancelar(self, pid: str) -> None:
        p = self._buscar(pid)
        if p:
            if not p.fut.done():
                p.fut.set_exception(NudoError("vencido", "Pedido cancelado."))
            self._soltar(p)

    def _soltar(self, p: _Pedido) -> None:
        if self._pend is p:
            self._pend = None
        if self._pend_estado is p:
            self._pend_estado = None
        if self._pend_interno is p:
            self._pend_interno = None

    def _vence_de(self, op: str, args: dict) -> float:
        if op == "controles":
            return self._vence_lectura_s
        if op == "senalar" and args.get("esperar"):
            return args["esperar"] + MARGEN_ESPERA_S
        return self._vence_s

    def _liberar(self, limpiar: bool) -> None:
        if self._dueno:
            self._fotos.pop(self._dueno[0], None)
            self._imagenes.pop(self._dueno[0], None)
        self._dueno = None
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if limpiar and self._pcs:
            self._limpiar_interno(*self._pcs[-1])

    def _armar(self, espera: float) -> None:
        if self._timer:
            self._timer.cancel()
        try:
            self._timer = asyncio.get_running_loop().call_later(max(espera, 1.0), self._tick)
        except RuntimeError:
            self._timer = None

    def _tick(self) -> None:
        self._timer = None
        self.expirar()
        if self._dueno:
            self._armar(INACTIVIDAD_DUENO_S - (self._clock() - self._dueno[2]))

    def _poner_dueno(self, sesion: str, nombre: str) -> None:
        if not self._pcs:
            return
        self._dueno = [sesion, nombre, self._clock()]
        self._armar(INACTIVIDAD_DUENO_S)

    def _podar_fotos(self) -> None:
        ahora = self._clock()
        self._fotos = {k: v for k, v in self._fotos.items() if ahora - v[1] <= FOTO_VIDA_S}
        self._imagenes = {k: v for k, v in self._imagenes.items() if k in self._fotos}

    def registrar_foto(self, sesion: str, foto: int, ancho: int, alto: int) -> None:
        if not isinstance(sesion, str) or not SESION_RE.fullmatch(sesion):
            raise ValueError("sesión inválida")
        _entero(foto, 0, "foto")
        _entero(ancho, 1, "ancho")
        _entero(alto, 1, "alto")
        self._podar_fotos()
        self._fotos[sesion] = (foto, self._clock())
        self._imagenes[sesion] = (ancho, alto)

    def _exito(self, p: _Pedido, nombre: str, datos: dict) -> dict:
        if p.op == "controles":
            self._podar_fotos()
            self._fotos[p.sesion] = (datos["foto"], self._clock())
            self._imagenes.pop(p.sesion, None)
            if self._dueno and self._dueno[0] == p.sesion:
                self._dueno[2] = self._clock()
            return {k: v for k, v in datos.items() if k != "foto"}
        if p.op == "limpiar":
            self._liberar(limpiar=False)
            return {"resultado": "ok"}
        if p.op in OPS_DIBUJO:
            if datos["resultado"] == "salir":
                self._liberar(limpiar=False)
            else:
                self._poner_dueno(p.sesion, nombre)
        return datos

    def resolver(self, pid: str, device: str, token: str, resultado: object) -> bool:
        p = self._buscar(pid)
        if (p is None or p.usado or p.fut.done() or p.device != device
                or not isinstance(token, str)
                or not hmac.compare_digest(p.token.encode(), token.encode())):
            return False
        p.usado = True
        try:
            datos = validar_respuesta(p.op, resultado)
        except ValueError:
            p.fut.set_exception(NudoError("fallo_pc"))
            return True
        if "error" in datos:
            p.fut.set_exception(NudoError(datos["error"]))
        else:
            p.fut.set_result(datos)
        return True

    async def pedir(self, sesion: str, nombre: str, op: str, args: dict) -> dict:
        if op not in OPERACIONES or not isinstance(sesion, str) or not SESION_RE.fullmatch(sesion):
            raise NudoError("invalido")
        nombre = _limpio(nombre) or _respaldo(sesion)
        self.expirar()
        dueno = self._dueno
        if op == "limpiar" and (dueno is None or dueno[0] != sesion):
            return {"resultado": "ok", "nada": True}
        device = self.pc_objetivo()
        if device is None:
            raise NudoError("sin_pc")
        if op == "estado":
            if self._pend_estado is not None:
                raise NudoError("en_curso")
        elif self._pend is not None:
            if self._pend.sesion != sesion:
                raise NudoError("ocupado", f"Ocupado por {self._pend.nombre}.")
            raise NudoError("en_curso")
        if (op == "controles" or op in OPS_DIBUJO) and dueno and dueno[0] != sesion:
            raise NudoError("ocupado", f"Ocupado por {dueno[1]}.")
        args = dict(args)
        if op in OPS_DIBUJO:
            foto = self._fotos.get(sesion)
            imagen = self._imagenes.get(sesion)
            if foto is None or self._clock() - foto[1] > FOTO_VIDA_S or (op in OPS_ZONA and imagen is None):
                self._fotos.pop(sesion, None)
                self._imagenes.pop(sesion, None)
                raise NudoError("foto_vieja")
            if op in OPS_ZONA:
                zonas = [args["zona"]] if op == "senalar_zona" else args["zonas"]
                if any(z["x"] + z["ancho"] > imagen[0] or z["y"] + z["alto"] > imagen[1] for z in zonas):
                    raise NudoError("invalido", f"La zona cae fuera de la captura ({imagen[0]}x{imagen[1]}).")
            args["foto"] = foto[0]
        pid = secrets.token_urlsafe(12)
        token = self._token()
        fut = asyncio.get_running_loop().create_future()
        p = _Pedido(pid, token, device, sesion, op, fut, nombre)
        if op == "estado":
            self._pend_estado = p
        else:
            self._pend = p
        evento = {"id": pid, "token": token, "op": op, "args": args, "sesion": nombre}
        if op in OPS_DIBUJO and self.es_guia(sesion):
            evento["guia"] = True
        self._ofrecer(self._pcs[-1][1], ("nudo", evento))
        try:
            datos = await asyncio.wait_for(fut, self._vence_de(op, args))
        except asyncio.TimeoutError:
            raise NudoError("vencido") from None
        except asyncio.CancelledError:
            if op in OPS_DIBUJO:
                self._poner_dueno(sesion, nombre)
            raise
        finally:
            self._soltar(p)
        return self._exito(p, nombre, datos)


def ruta_socket(environ: Optional[dict] = None) -> Optional[Path]:
    base = (environ if environ is not None else os.environ).get("XDG_RUNTIME_DIR")
    if not base:
        return None
    return Path(base) / "colmena" / "nudo.sock"


MAX_LINEA_CLI = 8 * 1024
MENSAJE_SIN_PC = "PC no conectada: la app de Windows no está abierta."
_JSON_KW = {"ensure_ascii": False, "separators": (",", ":")}


def _error(codigo: str, mensaje: Optional[str] = None) -> dict:
    return {"ok": False, "error": codigo, "mensaje": mensaje or MENSAJES.get(codigo, codigo)}


def crear_manejador(store: NudoStore, tablero: Callable[[], Optional[dict]]):
    async def manejar(msg: dict) -> dict:
        op, sesion, args = msg.get("op"), msg.get("sesion"), msg.get("args", {})
        try:
            if not isinstance(op, str) or op not in OPERACIONES:
                raise ValueError("operación desconocida")
            if not isinstance(sesion, str) or not SESION_RE.fullmatch(sesion):
                raise ValueError("sesión inválida")
            args = validar_args(op, args)
            datos = await store.pedir(sesion, nombre_sesion(tablero(), sesion), op, args)
        except NudoError as e:
            return _error(e.codigo, MENSAJE_SIN_PC if e.codigo == "sin_pc" else e.mensaje)
        except ValueError as e:
            return _error("invalido", str(e) or None)
        return {"ok": True, "datos": datos}

    return manejar


class ServidorNudo:
    def __init__(self, manejar: Callable[[dict], Awaitable[dict]], verificar=mismo_uid) -> None:
        self._manejar = manejar
        self._verificar = verificar
        self._server: Optional[asyncio.Server] = None
        self._tareas: set[asyncio.Task] = set()

    async def _cerrar_writer(self, writer: asyncio.StreamWriter) -> None:
        if not writer.is_closing():
            writer.close()
        try:
            await writer.wait_closed()
        except (OSError, asyncio.CancelledError):
            pass

    async def atender(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tarea = asyncio.current_task()
        if tarea is not None:
            self._tareas.add(tarea)
        try:
            try:
                ok = self._verificar(writer)
            except Exception:
                ok = False
            if not ok:
                return
            resp = await self._leer_y_manejar(reader, writer)
            if resp is not None:
                try:
                    writer.write((json.dumps(resp, **_JSON_KW) + "\n").encode())
                    await writer.drain()
                except (OSError, ConnectionError):
                    pass
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("error en el socket del nudo")
        finally:
            await self._cerrar_writer(writer)
            if tarea is not None:
                self._tareas.discard(tarea)

    async def _leer_y_manejar(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> Optional[dict]:
        try:
            linea = await reader.readline()
        except (asyncio.LimitOverrunError, ValueError):
            return _error("invalido", "Pedido demasiado largo.")
        if not linea:
            return None
        if len(linea) > MAX_LINEA_CLI or not linea.endswith(b"\n"):
            return _error("invalido", "Pedido demasiado largo o cortado.")
        try:
            msg = json.loads(linea)
        except ValueError:
            return _error("invalido", "El pedido no es JSON.")
        if not isinstance(msg, dict):
            return _error("invalido", "El pedido tiene que ser un objeto.")
        trabajo = asyncio.ensure_future(self._manejar(msg))
        eof = asyncio.ensure_future(self._hasta_eof(reader))
        try:
            await asyncio.wait({trabajo, eof}, return_when=asyncio.FIRST_COMPLETED)
            if not trabajo.done():
                trabajo.cancel()
                await asyncio.gather(trabajo, return_exceptions=True)
                return None
            try:
                return trabajo.result()
            except Exception:
                log.exception("error manejando un pedido del nudo")
                return _error("fallo_pc")
        finally:
            eof.cancel()
            if not trabajo.done():
                trabajo.cancel()

    async def _hasta_eof(self, reader: asyncio.StreamReader) -> None:
        try:
            while await reader.read(65536):
                pass
        except (OSError, ConnectionError):
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
            self._server = await asyncio.start_unix_server(self.atender, sock=sock, limit=MAX_LINEA_CLI + 1)
        except Exception:
            sock.close()
            try:
                ruta.unlink()
            except OSError:
                pass
            raise

    async def cerrar(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
        actual = asyncio.current_task()
        tareas = [t for t in self._tareas if t is not actual]
        for t in tareas:
            t.cancel()
        if tareas:
            await asyncio.gather(*tareas, return_exceptions=True)
        if server is not None:
            try:
                await asyncio.wait_for(server.wait_closed(), 2)
            except asyncio.TimeoutError:
                log.warning("timeout esperando el cierre del socket del nudo")
