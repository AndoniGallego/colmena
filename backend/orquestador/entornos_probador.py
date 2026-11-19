from __future__ import annotations

import asyncio
import contextvars
import logging
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx

from .entornos import NOMBRE_RE

log = logging.getLogger(__name__)

_EN_PRUEBA: contextvars.ContextVar[bool] = contextvars.ContextVar("_EN_PRUEBA", default=False)


class _FiltroPrueba(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _EN_PRUEBA.get()


def _agregar_filtro_prueba(nombre: str) -> None:
    lg = logging.getLogger(nombre)
    for f in lg.filters:
        if isinstance(f, _FiltroPrueba):
            return
    lg.addFilter(_FiltroPrueba())


_agregar_filtro_prueba("httpx")
_agregar_filtro_prueba("httpcore")

TOPE_S = 10.0
MAX_PEDIDO_BYTES = 262144

OPCIONES_CLIENTE = {
    "follow_redirects": False,
    "trust_env": False,
    "timeout": httpx.Timeout(10.0),
}

METODOS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})
METODOS_CUERPO = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_ENCABEZADO_NOMBRE_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_ENCABEZADOS_PROHIBIDOS = frozenset({
    "host", "content-length", "transfer-encoding", "connection", "upgrade",
    "keep-alive", "te", "trailer", "expect", "accept-encoding",
})
_VENTANA_RL_S = 60.0
_TOPE_RL = 30
_MAX_CUERPO_PEDIDO = 65536
_MAX_LECTURA = 262144

MSG_PEDIDO_INVALIDO = "Pedido inválido"
MSG_PUERTO = "Ese puerto no es de un entorno prendido"
MSG_EN_CURSO = "Ya hay una prueba en curso"
MSG_RATELIMIT = "Demasiadas pruebas seguidas; esperá un minuto"
MSG_NO_RESPONDE = "El servicio no responde"
MSG_TARDE = "El servicio tardó más de 10 s"
MSG_DOCKER_TARDE = "Docker no responde"


class PedidoInvalido(Exception):
    def __init__(self, mensaje: str = MSG_PEDIDO_INVALIDO) -> None:
        self.mensaje = mensaje
        super().__init__(mensaje)


@dataclass(frozen=True)
class Pedido:
    nombre: str
    puerto: int
    metodo: str
    ruta: str
    encabezados: list[tuple[str, str]]
    cuerpo: bytes | None
    confirmado: bool


def _tipo_textual(content_type: str) -> bool:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if not ct:
        return True
    if ct.startswith("text/"):
        return True
    return any(x in ct for x in ("json", "xml", "javascript"))


def armar_url(puerto: int, ruta: str) -> str:
    url = f"http://127.0.0.1:{puerto}{ruta}"
    parsed = httpx.URL(url)
    if parsed.host != "127.0.0.1" or parsed.port != puerto or parsed.scheme != "http":
        raise PedidoInvalido()
    return url


def _validar_ruta(ruta: Any) -> str:
    if not isinstance(ruta, str):
        raise PedidoInvalido()
    if not ruta.startswith("/") or ruta.startswith("//"):
        raise PedidoInvalido()
    if len(ruta) > 2048:
        raise PedidoInvalido()
    for ch in ruta:
        if ch in " \\\r\n#":
            raise PedidoInvalido()
        if ord(ch) < 32 or ord(ch) == 127:
            raise PedidoInvalido()
    return ruta


def _encabezado_prohibido(nombre: str) -> bool:
    n = nombre.lower()
    if n in _ENCABEZADOS_PROHIBIDOS:
        return True
    return n.startswith("proxy-")


def validar_pedido(datos: Any) -> Pedido:
    if not isinstance(datos, dict):
        raise PedidoInvalido()
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not NOMBRE_RE.match(nombre):
        raise PedidoInvalido()
    puerto = datos.get("puerto")
    if not isinstance(puerto, int) or isinstance(puerto, bool) or not (1 <= puerto <= 65535):
        raise PedidoInvalido()
    metodo = datos.get("metodo")
    if not isinstance(metodo, str) or metodo not in METODOS:
        raise PedidoInvalido()
    ruta = _validar_ruta(datos.get("ruta"))
    confirmado = datos.get("confirmado")
    if not isinstance(confirmado, bool):
        raise PedidoInvalido()

    raw_cuerpo = datos.get("cuerpo")
    cuerpo: bytes | None = None
    if raw_cuerpo is not None:
        if metodo not in METODOS_CUERPO:
            raise PedidoInvalido()
        if not isinstance(raw_cuerpo, str):
            raise PedidoInvalido()
        cuerpo = raw_cuerpo.encode("utf-8")
        if len(cuerpo) > _MAX_CUERPO_PEDIDO:
            raise PedidoInvalido()
    if metodo in METODOS_CUERPO and not confirmado:
        raise PedidoInvalido()

    raw_enc = datos.get("encabezados")
    encabezados: list[tuple[str, str]] = []
    if raw_enc is not None:
        if not isinstance(raw_enc, list) or len(raw_enc) > 20:
            raise PedidoInvalido()
        for item in raw_enc:
            if not isinstance(item, dict):
                raise PedidoInvalido()
            nom = item.get("nombre")
            val = item.get("valor")
            if not isinstance(nom, str) or not _ENCABEZADO_NOMBRE_RE.match(nom):
                raise PedidoInvalido()
            if _encabezado_prohibido(nom):
                raise PedidoInvalido()
            if not isinstance(val, str) or len(val) > 4096:
                raise PedidoInvalido()
            if not val.isascii():
                raise PedidoInvalido()
            if "\r" in val or "\n" in val or "\x00" in val:
                raise PedidoInvalido()
            encabezados.append((nom, val))

    armar_url(puerto, ruta)
    return Pedido(
        nombre=nombre,
        puerto=puerto,
        metodo=metodo,
        ruta=ruta,
        encabezados=encabezados,
        cuerpo=cuerpo,
        confirmado=confirmado,
    )


def _respuesta_encabezados(headers: httpx.Headers) -> list[list[str]]:
    out: list[list[str]] = []
    for nombre, valor in headers.multi_items():
        if nombre.lower() == "set-cookie":
            out.append([nombre, "(oculto)"])
        else:
            out.append([nombre, valor])
    return out


class Probador:
    def __init__(
        self,
        listar: Callable[[], Awaitable[dict]],
        *,
        cliente_factory: Callable[[], httpx.AsyncClient] | None = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._listar = listar
        self._cliente_factory = cliente_factory or (
            lambda: httpx.AsyncClient(**OPCIONES_CLIENTE)
        )
        self._now = now
        self._mutex = asyncio.Lock()
        self._ventana: deque[float] = deque()

    def _podar_rate_limit(self, ahora: float) -> None:
        while self._ventana and ahora - self._ventana[0] > _VENTANA_RL_S:
            self._ventana.popleft()

    async def _autorizado(self, pedido: Pedido) -> bool | str:
        data = await self._listar()
        err = data.get("error")
        if isinstance(err, str) and err:
            return err
        for ent in data.get("entornos") or []:
            if not isinstance(ent, dict):
                continue
            if ent.get("nombre") != pedido.nombre:
                continue
            if ent.get("apagado"):
                return False
            for p in ent.get("puertos") or []:
                if not isinstance(p, dict):
                    continue
                if p.get("puerto") == pedido.puerto and p.get("abrible"):
                    return True
        return False

    async def _leer_respuesta(
        self, cliente: httpx.AsyncClient, pedido: Pedido, url: str,
    ) -> tuple[int, str, list[list[str]], int, bool, bytes, bool]:
        headers = {k: v for k, v in pedido.encabezados}
        headers["Accept-Encoding"] = "identity"
        kwargs: dict = {"headers": headers}
        if pedido.cuerpo is not None:
            kwargs["content"] = pedido.cuerpo
        async with cliente.stream(pedido.metodo, url, **kwargs) as resp:
            codigo_http = resp.status_code
            tipo = resp.headers.get("content-type", "").split(";", 1)[0].strip()
            encabezados = _respuesta_encabezados(resp.headers)
            enc = (resp.headers.get("content-encoding") or "").strip().lower()
            comprimido = bool(enc) and enc != "identity"
            leido = 0
            trozos: list[bytes] = []
            truncado = False
            iter_bloques = resp.aiter_raw() if comprimido else resp.aiter_bytes()
            async for bloque in iter_bloques:
                if not bloque:
                    continue
                restante = _MAX_LECTURA - leido
                if restante <= 0:
                    truncado = True
                    break
                if len(bloque) > restante:
                    trozos.append(bloque[:restante])
                    leido += restante
                    truncado = True
                    break
                trozos.append(bloque)
                leido += len(bloque)
            return codigo_http, tipo, encabezados, leido, truncado, b"".join(trozos), comprimido

    async def _consultar(self, pedido: Pedido) -> tuple[int, dict]:
        url = armar_url(pedido.puerto, pedido.ruta)
        inicio = self._now()
        token = _EN_PRUEBA.set(True)

        async def _correr() -> tuple[int, dict]:
            async with self._cliente_factory() as cliente:
                (
                    codigo_http,
                    tipo,
                    encabezados,
                    leido,
                    truncado,
                    cuerpo_bin,
                    comprimido,
                ) = await self._leer_respuesta(cliente, pedido, url)
                cuerpo_texto: str | None
                if pedido.metodo == "HEAD" or comprimido or not _tipo_textual(tipo):
                    cuerpo_texto = None
                else:
                    cuerpo_texto = cuerpo_bin.decode("utf-8", errors="replace")
                ms = int((self._now() - inicio) * 1000)
                log.info(
                    "prueba entorno=%s puerto=%d metodo=%s codigo=%s ms=%d",
                    pedido.nombre,
                    pedido.puerto,
                    pedido.metodo,
                    codigo_http,
                    ms,
                )
                return 200, {
                    "codigo": codigo_http,
                    "ms": ms,
                    "tipo": tipo,
                    "encabezados": encabezados,
                    "cuerpo": cuerpo_texto,
                    "bytes": leido,
                    "truncado": truncado,
                }

        try:
            return await asyncio.wait_for(_correr(), TOPE_S)
        except asyncio.TimeoutError:
            return 504, {"error": MSG_TARDE}
        except httpx.TimeoutException:
            return 504, {"error": MSG_TARDE}
        except httpx.HTTPError:
            return 502, {"error": MSG_NO_RESPONDE}
        except Exception as exc:
            log.warning(
                "prueba falló entorno=%s puerto=%d error=%s",
                pedido.nombre,
                pedido.puerto,
                type(exc).__name__,
            )
            return 502, {"error": MSG_NO_RESPONDE}
        finally:
            _EN_PRUEBA.reset(token)

    async def probar(self, datos: Any) -> tuple[int, dict]:
        if self._mutex.locked():
            return 429, {"error": MSG_EN_CURSO}
        ahora = self._now()
        self._podar_rate_limit(ahora)
        if len(self._ventana) >= _TOPE_RL:
            return 429, {"error": MSG_RATELIMIT}
        try:
            pedido = validar_pedido(datos)
        except (PedidoInvalido, ValueError, UnicodeError, httpx.InvalidURL):
            return 400, {"error": MSG_PEDIDO_INVALIDO}
        self._ventana.append(ahora)
        async with self._mutex:
            try:
                auth = await asyncio.wait_for(self._autorizado(pedido), TOPE_S)
            except asyncio.TimeoutError:
                return 504, {"error": MSG_DOCKER_TARDE}
            except Exception as exc:
                log.warning(
                    "prueba falló al listar entorno=%s puerto=%d error=%s",
                    pedido.nombre,
                    pedido.puerto,
                    type(exc).__name__,
                )
                return 503, {"error": MSG_DOCKER_TARDE}
            if isinstance(auth, str):
                return 503, {"error": auth}
            if not auth:
                return 404, {"error": MSG_PUERTO}
            return await self._consultar(pedido)
