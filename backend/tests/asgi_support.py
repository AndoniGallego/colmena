import asyncio
from dataclasses import dataclass
from typing import Optional


@dataclass
class Resultado:
    status: Optional[int]
    cierre: Optional[int]
    aceptado: bool
    llamada: bool
    scope: Optional[dict]


async def _correr_app(app, scope):
    status: Optional[int] = None
    cierre: Optional[int] = None
    aceptado = False
    mensajes: list = []

    async def send(message):
        nonlocal status, cierre, aceptado
        mensajes.append(message)
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "websocket.close":
            cierre = message.get("code")
        elif message["type"] == "websocket.accept":
            aceptado = True

    async def receive():
        if scope["type"] == "websocket":
            return {"type": "websocket.connect"}
        return {"type": "http.request", "body": b"", "more_body": False}

    await app(scope, receive, send)
    return status, cierre, aceptado


def correr(envolver, tipo="http", headers=(), client=("127.0.0.1", 1), path="/api/x", method="GET") -> Resultado:
    scope_recibido: dict = {}
    llamada = False

    async def inner(scope, receive, send):
        nonlocal llamada
        llamada = True
        scope_recibido.clear()
        scope_recibido.update(scope)
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok", "more_body": False})
        else:
            await send({"type": "websocket.accept"})

    app = envolver(inner)
    hdrs = [(n.lower().encode("latin-1"), v.encode("latin-1")) for n, v in headers]
    scope = {
        "type": tipo,
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "headers": hdrs,
        "client": client,
        "server": ("127.0.0.1", 8770),
    }
    if tipo == "websocket":
        scope["subprotocols"] = []
    status, cierre, aceptado = asyncio.run(_correr_app(app, scope))
    return Resultado(status=status, cierre=cierre, aceptado=aceptado, llamada=llamada,
                     scope=scope_recibido or None)
