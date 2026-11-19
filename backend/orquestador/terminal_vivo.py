from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from orquestador import auth
from orquestador.enchufe.base import NoDisponible, NoExiste, TerminalesError, Tiempo
from orquestador.enchufe.guardian import FotoVivo
from orquestador.enchufe.ids import es_guardian, tipo_de_id
from orquestador.hardening import MARCA_ORIGEN

MAX_POR_SESION = 3
MAX_TOTAL = 8
MAX_ENTRADA = 8192
MAX_TEXTO_ENTRADA = 4096
# Con el teclado en vivo cada tecla es un mensaje (el cliente agrupa en tandas de ~30 ms).
MAX_MENSAJES_VENTANA = 400
VENTANA_S = 10.0
REVALIDAR_S = 30.0
AUDITORIA_S = 30.0

TECLAS_VIVO: frozenset[str] = frozenset(
    {
        "esc",
        "tab",
        "enter",
        "arriba",
        "abajo",
        "izquierda",
        "derecha",
        "ctrl-c",
        "1",
        "2",
        "3",
    }
)

_MAPEO_TECLAS: dict[str, tuple[str, tuple[str, ...] | str]] = {
    "esc": ("teclas", ("esc",)),
    "enter": ("teclas", ("enter",)),
    "arriba": ("teclas", ("arriba",)),
    "derecha": ("teclas", ("derecha",)),
    "ctrl-c": ("teclas", ("ctrl-c",)),
    "1": ("teclas", ("1",)),
    "2": ("teclas", ("2",)),
    "3": ("teclas", ("3",)),
    "tab": ("escribir", "\t"),
    "abajo": ("escribir", "\x1b[B"),
    "izquierda": ("escribir", "\x1b[D"),
}


def mapear_tecla_vivo(nombre: str) -> tuple[str, tuple[str, ...] | str] | None:
    if nombre not in TECLAS_VIVO:
        return None
    return _MAPEO_TECLAS[nombre]


class AcumuladorAuditoriaVivo:
    def __init__(self, audit, sesion_id: str, reloj: Callable[[], float] = time.monotonic):
        self._audit = audit
        self._sesion_id = sesion_id
        self._reloj = reloj
        self._caracteres = 0
        self._teclas: list[str] = []
        self._ultimo = reloj()

    def sumar_texto(self, n: int) -> None:
        if n > 0:
            self._caracteres += n

    def sumar_tecla(self, nombre: str) -> None:
        self._teclas.append(nombre)

    def volcar_si_toca(self, *, forzar: bool = False) -> None:
        if self._caracteres <= 0 and not self._teclas:
            return
        ahora = self._reloj()
        if not forzar and ahora - self._ultimo < AUDITORIA_S:
            return
        self._volcar()

    def cerrar(self) -> None:
        self._volcar()

    def _volcar(self) -> None:
        if self._caracteres <= 0 and not self._teclas:
            return
        from datetime import datetime, timezone

        self._audit.write(
            {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "accion": "vivo_escritura",
                "sesion_id": self._sesion_id,
                "caracteres": self._caracteres,
                "teclas": list(self._teclas),
            }
        )
        self._caracteres = 0
        self._teclas = []
        self._ultimo = self._reloj()

_CTRL_C0 = re.compile(r"[\x00-\x1f\x7f]")


class Cupos:
    def __init__(self) -> None:
        self._por_sesion: dict[str, int] = {}
        self._total = 0

    def tomar(self, sid: str) -> bool:
        n = self._por_sesion.get(sid, 0)
        if n >= MAX_POR_SESION or self._total >= MAX_TOTAL:
            return False
        self._por_sesion[sid] = n + 1
        self._total += 1
        return True

    def soltar(self, sid: str) -> None:
        n = self._por_sesion.get(sid, 0)
        if n <= 0:
            return
        if n == 1:
            del self._por_sesion[sid]
        else:
            self._por_sesion[sid] = n - 1
        self._total = max(0, self._total - 1)


def armar_foto(foto: FotoVivo) -> str:
    pantalla = list(foto.pantalla[: foto.filas])
    while len(pantalla) < foto.filas:
        pantalla.append("")
    historial = tuple(_CTRL_C0.sub("", ln) for ln in foto.historial)
    texto = "\r\n".join(historial + tuple(pantalla)) + "\x1b[0m"
    if foto.cursor is not None:
        x, y = foto.cursor
        texto += f"\x1b[{y + 1};{x + 1}H"
    if not foto.cursor_visible:
        texto += "\x1b[?25l"
    return texto


async def atender(
    websocket: WebSocket,
    sesion_id: str,
    *,
    secret: bytes,
    epoch: Callable[[], int],
    habilitado: Callable[[], bool],
    abrir: Callable[[str], Awaitable[Any]],
    cupos: Cupos,
    reloj: Callable[[], float] = time.monotonic,
    escritura_habilitada: Callable[[], bool] | None = None,
    ventana: Any | None = None,
    escribir: Callable[[str, str], Awaitable[Any]] | None = None,
    teclas: Callable[[str, Sequence[Any]], Awaitable[Any]] | None = None,
    audit: Any | None = None,
    ip_cliente: str = "?",
    cookie_sesion: str = "",
) -> None:
    if websocket.scope.get(MARCA_ORIGEN) is not True:
        await websocket.close(code=1008)
        return
    if not auth.valid_session(secret, websocket.cookies.get(auth.COOKIE_NAME), epoch=epoch()):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    tomado = False
    canal = None
    auditoria: AcumuladorAuditoriaVivo | None = None

    async def _enviar(payload: dict) -> None:
        await websocket.send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    async def _error(codigo: str, mensaje: str, close: int) -> None:
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            await _enviar({"tipo": "error", "codigo": codigo, "mensaje": mensaje})
            await websocket.close(code=close)

    try:
        if not habilitado():
            await _error("apagado", "El visor en vivo está desactivado.", 4403)
            return
        if not es_guardian(sesion_id) or tipo_de_id(sesion_id) != "sesion":
            await _error("no_es_propia", "Esta sesión no es una terminal propia.", 4404)
            return
        if not cupos.tomar(sesion_id):
            await _error("cupo", "Hay demasiados visores abiertos.", 4429)
            return
        tomado = True
        try:
            canal = await abrir(sesion_id)
        except NoExiste:
            await _error("no_existe", "Esa sesión ya no existe.", 4404)
            return
        except (NoDisponible, Tiempo, TerminalesError, OSError):
            with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                await _enviar({"tipo": "caido"})
                await websocket.close(code=4503)
            return

        try:
            await _enviar(
                {
                    "tipo": "foto",
                    "columnas": canal.foto.columnas,
                    "filas": canal.foto.filas,
                    "texto": armar_foto(canal.foto),
                }
            )
        except (WebSocketDisconnect, RuntimeError):
            return

        ultima_revalidacion = reloj()

        async def _revalidar_si_toca() -> bool:
            nonlocal ultima_revalidacion
            if reloj() - ultima_revalidacion < REVALIDAR_S:
                return True
            ultima_revalidacion = reloj()
            if auth.valid_session(secret, websocket.cookies.get(auth.COOKIE_NAME), epoch=epoch()):
                return True
            with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                await _enviar({"tipo": "error", "codigo": "sesion", "mensaje": "Tu sesión expiró."})
                await websocket.close(code=4401)
            return False

        async def emisor() -> None:
            async for ev in canal:
                if not await _revalidar_si_toca():
                    return
                tipo = ev.get("tipo")
                if tipo == "salida":
                    await _enviar({"tipo": "salida", "texto": ev.get("texto", "")})
                elif tipo == "termino":
                    await _enviar({"tipo": "termino", "codigo": ev.get("codigo")})
                    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                        await websocket.close(code=1000)
                    return
                elif tipo == "cerrada":
                    await _enviar({"tipo": "cerrada"})
                    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                        await websocket.close(code=1000)
                    return
                elif tipo == "caido":
                    await _enviar({"tipo": "caido"})
                    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                        await websocket.close(code=4503)
                    return
                elif tipo == "desfasado":
                    await _enviar({"tipo": "desfasado"})
                    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                        await websocket.close(code=4409)
                    return

        if audit is not None:
            auditoria = AcumuladorAuditoriaVivo(audit, sesion_id, reloj)

        async def _error_escritura(codigo: str, mensaje: str) -> None:
            await _enviar({"tipo": "error_escritura", "codigo": codigo, "mensaje": mensaje})

        async def _aplicar_escritura(payload: dict) -> None:
            if escribir is None or teclas is None or ventana is None:
                return
            if not escritura_habilitada or not escritura_habilitada():
                await _error_escritura("apagado", "La escritura remota está apagada.")
                return
            token = payload.get("token")
            motivo = ventana.validar(token, cookie_sesion, ip_cliente) if isinstance(token, str) else "invalida"
            if motivo:
                await _error_escritura(
                    "ventana",
                    "La ventana de escritura venció." if motivo == "vencida" else "La ventana de escritura no es válida.",
                )
                return
            tipo = payload.get("tipo")
            try:
                if tipo == "entrada":
                    texto_in = payload.get("texto")
                    if not isinstance(texto_in, str) or len(texto_in) > MAX_TEXTO_ENTRADA:
                        return
                    await escribir(sesion_id, texto_in)
                    ventana.usar()
                    if auditoria:
                        auditoria.sumar_texto(len(texto_in))
                        auditoria.volcar_si_toca()
                elif tipo == "tecla":
                    nombre = payload.get("tecla")
                    if not isinstance(nombre, str):
                        return
                    mapeo = mapear_tecla_vivo(nombre)
                    if mapeo is None:
                        return
                    modo, valor = mapeo
                    if modo == "teclas":
                        await teclas(sesion_id, valor)
                    else:
                        await escribir(sesion_id, valor)
                    ventana.usar()
                    if auditoria:
                        auditoria.sumar_tecla(nombre)
                        auditoria.volcar_si_toca()
            except (NoDisponible, Tiempo, TerminalesError, OSError, ValueError):
                await _error_escritura("caido", "Las terminales propias no responden.")

        async def receptor() -> None:
            ventana_inicio = reloj()
            mensajes = 0
            while True:
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                datos = msg.get("bytes")
                if datos is not None:
                    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                        await websocket.close(code=1003)
                    return
                texto = msg.get("text")
                if texto is None:
                    continue
                ahora = reloj()
                if ahora - ventana_inicio > VENTANA_S:
                    ventana_inicio = ahora
                    mensajes = 0
                mensajes += 1
                if len(texto) > MAX_ENTRADA:
                    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                        await websocket.close(code=1009)
                    return
                if mensajes > MAX_MENSAJES_VENTANA:
                    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                        await websocket.close(code=1008)
                    return
                try:
                    payload = json.loads(texto)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get("tipo") in ("entrada", "tecla"):
                    await _aplicar_escritura(payload)
                if auditoria:
                    auditoria.volcar_si_toca()

        t_emisor = asyncio.create_task(emisor())
        t_receptor = asyncio.create_task(receptor())
        done, pending = await asyncio.wait({t_emisor, t_receptor}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in pending:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        for t in done:
            with contextlib.suppress(Exception):
                await t
    finally:
        if auditoria is not None:
            auditoria.cerrar()
        if canal is not None:
            with contextlib.suppress(Exception):
                await canal.cerrar()
        if tomado:
            cupos.soltar(sesion_id)
