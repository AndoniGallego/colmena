from starlette.responses import JSONResponse

from orquestador.auth import rechazar, valores_header

MARCA_ORIGEN = "colmena.origen_validado"

SAFE_METHODS = (b"GET", b"HEAD", b"OPTIONS")
FETCH_SITE_OK = (b"same-origin", b"none")
MULTIPART_PATHS = ("/api/uploads", "/api/voz/transcribir")


def build_csp(viewer_origin: str = "") -> str:
    viewer = f" {viewer_origin}" if viewer_origin else ""
    frame_src = viewer_origin or "'none'"
    return ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            f"font-src 'self'; img-src 'self' data: blob:{viewer}; connect-src 'self'; "
            f"media-src 'self'{viewer}; frame-src {frame_src}; "
            "manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def _same_origin(origin: str, app_origin: str, host: str) -> bool:
    origin = origin.strip().rstrip("/").lower()
    if not origin or origin == "null":
        return False
    if app_origin:
        return origin == app_origin.lower()
    # Sin app_origin (desarrollo): el esquema puede no coincidir detrás de un proxy, el host sí.
    return bool(host) and origin.split("://", 1)[-1] == host.lower()


class HardeningMiddleware:
    """El visor de la Biblioteca es el mismo sitio (otro puerto): la API no confía en cookies sin más."""

    def __init__(self, app, app_origin: str = ""):
        self.app = app
        self.app_origin = app_origin

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            if self._reject_ws(scope):
                await rechazar(scope, receive, send, 403, "origen no permitido")
                return
            await self.app({**scope, MARCA_ORIGEN: True}, receive, send)
            return
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        reject = self._reject(scope, headers)

        async def send_corp(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": list(message["headers"]) + [
                    (b"cross-origin-resource-policy", b"same-origin")]}
            await send(message)

        if reject:
            await reject(scope, receive, send_corp)
            return
        await self.app(scope, receive, send_corp)

    def _reject_ws(self, scope) -> bool:
        if not self.app_origin:
            return True
        origins = valores_header(scope, "origin")
        if len(origins) != 1:
            return True
        origin = origins[0].strip().rstrip("/").lower()
        if not origin or origin == "null" or origin != self.app_origin.lower():
            return True
        sites = valores_header(scope, "sec-fetch-site")
        if len(sites) > 1:
            return True
        if len(sites) == 1 and sites[0].lower() != "same-origin":
            return True
        return False

    def _reject(self, scope, headers):
        site = headers.get(b"sec-fetch-site")
        if site is not None and site.lower() not in FETCH_SITE_OK:
            return JSONResponse({"detail": "origen no permitido"}, status_code=403)
        method = scope["method"].encode()
        if method in SAFE_METHODS:
            return None
        origin = headers.get(b"origin", b"").decode("latin-1")
        host = headers.get(b"host", b"").decode("latin-1")
        if not _same_origin(origin, self.app_origin, host):
            return JSONResponse({"detail": "origen no permitido"}, status_code=403)
        length = headers.get(b"content-length", b"0")
        has_body = b"chunked" in headers.get(b"transfer-encoding", b"") or (length.isdigit() and int(length) > 0)
        if has_body:
            kind = headers.get(b"content-type", b"").split(b";")[0].strip().lower()
            wanted = b"multipart/form-data" if scope["path"] in MULTIPART_PATHS else b"application/json"
            if kind != wanted:
                return JSONResponse({"detail": f"Content-Type debe ser {wanted.decode()}"}, status_code=415)
        return None
