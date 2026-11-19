import asyncio
import hmac
import hashlib
import ipaddress
import time
from typing import Callable, Optional

from fastapi import HTTPException, Request
from starlette.responses import PlainTextResponse

COOKIE_NAME = "__Host-orq_session"
COOKIE_TTL = 7 * 24 * 3600
MAX_FAILURES = 5
LOCK_SECONDS = 600
GLOBAL_MAX_FAILURES = 20
GLOBAL_WINDOW = 3600
GLOBAL_LOCK_SECONDS = 3600


def parse_networks(cidrs):
    return [ipaddress.ip_network(c, strict=False) for c in cidrs]


def valores_header(scope, nombre: str) -> list[str]:
    clave = nombre.lower().encode("latin-1")
    return [v.decode("latin-1") for k, v in scope.get("headers", []) if k.lower() == clave]


async def rechazar(scope, receive, send, status: int, texto: str) -> None:
    if scope["type"] == "http":
        await PlainTextResponse(texto, status_code=status)(scope, receive, send)
    elif scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})


def ip_allowed(host: Optional[str], networks) -> bool:
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return any(addr in n for n in networks if n.version == addr.version)


class CidrMiddleware:
    def __init__(self, app, networks):
        self.app = app
        self.networks = networks

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            client = scope.get("client")
            if not ip_allowed(client[0] if client else None, self.networks):
                await rechazar(scope, receive, send, 403, "forbidden")
                return
        await self.app(scope, receive, send)


class IpRealMiddleware:
    def __init__(self, app, cabecera: str):
        self.app = app
        self.cabecera = cabecera

    async def __call__(self, scope, receive, send):
        if self.cabecera and scope["type"] in ("http", "websocket"):
            client = scope.get("client")
            if client and client[0] == "127.0.0.1":
                cadena = ",".join(valores_header(scope, self.cabecera))
                ultimo = cadena.split(",")[-1].strip() if cadena else ""
                usable = False
                if ultimo:
                    try:
                        ip = ipaddress.ip_address(ultimo)
                        if not getattr(ip, "scope_id", None):
                            ip = getattr(ip, "ipv4_mapped", None) or ip
                            scope = {**scope, "client": (str(ip), client[1])}
                            usable = True
                    except ValueError:
                        pass
                if not usable:
                    await rechazar(scope, receive, send, 403, "forbidden")
                    return
        await self.app(scope, receive, send)


def _sig(secret: bytes, epoch: int, expires: str) -> str:
    return hmac.new(secret, f"{epoch}.{expires}".encode(), hashlib.sha256).hexdigest()


def sign_session(secret: bytes, now: Optional[float] = None, epoch: int = 0) -> str:
    expires = int((now if now is not None else time.time()) + COOKIE_TTL)
    return f"{expires}.{_sig(secret, epoch, str(expires))}"


def valid_session(secret: bytes, token: Optional[str], now: Optional[float] = None, epoch: int = 0) -> bool:
    if not token or "." not in token:
        return False
    expires, _, sig = token.partition(".")
    if not expires.isdigit():
        return False
    if not hmac.compare_digest(sig, _sig(secret, epoch, expires)):
        return False
    return int(expires) > (now if now is not None else time.time())


class LoginLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.failures: dict = {}
        self.locked_until: dict = {}
        self.global_failures: list = []
        self.global_locked_until = 0.0
        # Un PIN a la vez (login, diálogos y escritura): si no, N intentos en paralelo pasan el chequeo antes del primer fallo.
        self.gate = asyncio.Lock()

    def retry_after(self, ip: str) -> int:
        now = self.clock()
        remaining = self.global_locked_until - now
        if remaining > 0:
            return int(remaining) + 1
        until = self.locked_until.get(ip)
        if until is None:
            return 0
        remaining = until - now
        if remaining <= 0:
            self.locked_until.pop(ip, None)
            self.failures.pop(ip, None)
            return 0
        return int(remaining) + 1

    def fail(self, ip: str) -> None:
        now = self.clock()
        self.failures[ip] = self.failures.get(ip, 0) + 1
        if self.failures[ip] >= MAX_FAILURES:
            self.locked_until[ip] = now + LOCK_SECONDS
        self.global_failures = [t for t in self.global_failures if now - t < GLOBAL_WINDOW] + [now]
        if len(self.global_failures) > GLOBAL_MAX_FAILURES:
            self.global_locked_until = now + GLOBAL_LOCK_SECONDS
            self.global_failures = []

    def ok(self, ip: str) -> None:
        self.failures.pop(ip, None)
        self.locked_until.pop(ip, None)


class TailscaleUserMiddleware:
    def __init__(self, app, user: str, estricto: bool = True):
        self.app = app
        self.user = user
        self.estricto = estricto

    async def __call__(self, scope, receive, send):
        if self.user and scope["type"] in ("http", "websocket"):
            valores = valores_header(scope, "Tailscale-User-Login")
            if self.estricto:
                if not valores or len(set(valores)) > 1 or valores[0] != self.user:
                    await rechazar(scope, receive, send, 403, "forbidden")
                    return
            else:
                for v in valores:
                    if v != self.user:
                        await rechazar(scope, receive, send, 403, "forbidden")
                        return
        await self.app(scope, receive, send)


def require_session(request: Request) -> None:
    secret = request.app.state.secret
    if not valid_session(secret, request.cookies.get(COOKIE_NAME), epoch=request.app.state.epoch()):
        raise HTTPException(status_code=401, detail="no autenticado")
