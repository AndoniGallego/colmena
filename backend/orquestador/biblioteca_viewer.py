import asyncio
import os
import re
from typing import Optional

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

from . import auth
from .biblioteca import ITEM_ID, SERVED_KINDS, Library, Served, token_valid

CHUNK = 256 * 1024
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), usb=(), payment=(), clipboard-read=(), "
                          "display-capture=()",
    "Cache-Control": "private, max-age=300",
}


def html_csp(app_origin: str, cdns: list) -> str:
    c = " ".join(cdns)
    ancestors = app_origin or "'self'"
    return ("sandbox allow-scripts; default-src 'none'; "
            f"script-src 'unsafe-inline' {c}; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com {c}; "
            f"font-src 'self' data: https://fonts.gstatic.com {c}; "
            f"img-src 'self' data: blob: {c}; media-src 'self' data: blob:; connect-src 'self' {c}; "
            "worker-src blob:; frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'; "
            f"frame-ancestors {ancestors}")


def quiet_csp(app_origin: str) -> str:
    return ("sandbox; default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; "
            f"frame-ancestors {app_origin or chr(39) + 'self' + chr(39)}")


def pdf_csp() -> str:
    return "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"


class NoCookieMiddleware:
    """La cabecera Cookie se descarta antes de que nadie la lea; el visor solo acepta GET/HEAD."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "headers": [(k, v) for k, v in scope["headers"] if k.lower() != b"cookie"]}
            if scope["method"] not in ("GET", "HEAD"):
                await PlainTextResponse("method not allowed", status_code=405,
                                        headers={"Allow": "GET, HEAD"})(scope, receive, send)
                return

            async def clean(message):
                if message["type"] == "http.response.start":
                    message = {**message, "headers": [(k, v) for k, v in message["headers"]
                                                      if k.lower() != b"set-cookie"]}
                await send(message)

            await self.app(scope, receive, clean)
            return
        await self.app(scope, receive, send)


async def _chunks(fd: int, start: int, end: int):
    try:
        os.lseek(fd, start, os.SEEK_SET)
        left = end - start + 1
        while left > 0:
            data = await asyncio.to_thread(os.read, fd, min(CHUNK, left))
            if not data:
                break
            left -= len(data)
            yield data
    finally:
        os.close(fd)


def create_viewer_app(library: Library, secret: bytes, epoch, cfg) -> Starlette:
    app_origin = cfg.app_origin
    cdns = list(cfg.biblioteca_cdns)

    def not_found() -> Response:
        return PlainTextResponse("not found", status_code=404)

    def respond(request, served: Served, asset: bool) -> Response:
        headers = dict(BASE_HEADERS)
        headers["Cross-Origin-Resource-Policy"] = "cross-origin" if asset else "same-site"
        if asset:
            headers["Access-Control-Allow-Origin"] = "*"
        if served.mime in ("text/html", "image/svg+xml"):
            headers["Content-Security-Policy"] = html_csp(app_origin, cdns)
        elif served.mime == "application/pdf" and not asset:
            headers["Content-Security-Policy"] = pdf_csp()
            headers["Content-Disposition"] = "inline"
        else:
            headers["Content-Security-Policy"] = quiet_csp(app_origin)
        ctype = served.mime + ("; charset=utf-8" if served.mime.startswith("text/") or served.mime ==
                               "image/svg+xml" else "")
        headers["Content-Type"] = ctype
        start, end, status = 0, max(served.size - 1, 0), 200
        if served.kind == "video" or served.mime.startswith("audio/"):
            headers["Accept-Ranges"] = "bytes"
            m = RANGE_RE.match(request.headers.get("range", ""))
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = min(int(m.group(2)), served.size - 1) if m.group(2) else served.size - 1
                else:
                    start = max(served.size - int(m.group(2)), 0)
                if start >= served.size or start > end:
                    os.close(served.fd)
                    return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{served.size}"})
                status = 206
                headers["Content-Range"] = f"bytes {start}-{end}/{served.size}"
        length = 0 if served.size == 0 else end - start + 1
        headers["Content-Length"] = str(length)
        if request.method == "HEAD":
            os.close(served.fd)
            return Response(status_code=status, headers=headers)
        return StreamingResponse(_chunks(served.fd, start, end), status_code=status, headers=headers)

    async def view(request):
        p = request.path_params
        ident, exp, sig = p["item_id"], p["exp"], p["sig"]
        rel = p.get("rest", "")
        if not token_valid(secret, ident, exp, sig, epoch()):
            return not_found()
        item = library.items.get(ident)
        if item is None or not ITEM_ID.match(ident) or item["kind"] not in SERVED_KINDS:
            return not_found()
        if rel:
            if not library.count_asset(ident, exp, sig):
                return PlainTextResponse("too many requests", status_code=429)
            served = await asyncio.to_thread(library.open_asset, item, rel)
        else:
            served = await asyncio.to_thread(library.open_main, item)
        if served is None:
            return not_found()
        return respond(request, served, asset=bool(rel))

    routes = [Route("/v/{item_id}/{exp}/{sig}/", view, methods=["GET", "HEAD"]),
              Route("/v/{item_id}/{exp}/{sig}/{rest:path}", view, methods=["GET", "HEAD"])]
    viewer = Starlette(routes=routes)
    viewer.add_middleware(auth.TailscaleUserMiddleware, user=cfg.tailscale_user)
    viewer.add_middleware(auth.CidrMiddleware, networks=auth.parse_networks(cfg.allowed_cidrs))
    viewer.add_middleware(NoCookieMiddleware)
    return viewer
