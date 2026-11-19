import asyncio
import json
import zlib

import pytest
from conftest import make_snapshot
from terminales_support import aplicar_snapshot

from orquestador import app as app_mod


def _parse(text: str) -> list:
    out = []
    for block in text.split("\n\n"):
        if not block:
            continue
        lines = block.split("\n")
        assert lines[0].startswith("event: ")
        out.append((lines[0][7:], json.loads(lines[1][6:])))
    return out


async def drive(app, cookie, accept=None, quiere=3, antes=None):
    """Corre /api/events directo por ASGI y devuelve (headers, chunks) tras `quiere` chunks de cuerpo."""
    headers = [(b"host", b"testserver"), (b"origin", b"http://testserver"), (b"cookie", cookie.encode())]
    if accept is not None:
        headers.append((b"accept-encoding", accept.encode()))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "https",
             "path": "/api/events", "raw_path": b"/api/events", "query_string": b"", "headers": headers,
             "client": ("127.0.0.1", 5000), "server": ("testserver", 443)}
    chunks: list = []
    start: dict = {}
    llego = asyncio.Event()
    desconectar = asyncio.Event()

    async def receive():
        await desconectar.wait()
        return {"type": "http.disconnect"}

    async def send(msg):
        if msg["type"] == "http.response.start":
            start["status"] = msg["status"]
            start["headers"] = {k.decode().lower(): v.decode() for k, v in msg["headers"]}
        elif msg["type"] == "http.response.body" and msg.get("body"):
            chunks.append(msg["body"])
            if antes is not None:
                await antes(len(chunks))
            if len(chunks) >= quiere:
                llego.set()

    task = asyncio.create_task(app(scope, receive, send))
    try:
        await asyncio.wait_for(llego.wait(), 5)
    finally:
        desconectar.set()
        task.cancel()
        try:
            await task
        except BaseException:
            pass
    return start, chunks


@pytest.fixture
def cookie(authed):
    return "; ".join(f"{k}={v}" for k, v in authed.cookies.items())


@pytest.fixture(autouse=True)
def rapido(monkeypatch):
    monkeypatch.setattr(app_mod, "KEEPALIVE", 0.05)


def test_con_gzip_cada_chunk_es_un_evento_completo(app, cookie):
    start, chunks = asyncio.run(drive(app, cookie, accept="gzip, deflate", quiere=3))
    assert start["status"] == 200
    assert start["headers"]["content-encoding"] == "gzip"
    assert "accept-encoding" in start["headers"]["vary"].lower()
    d = zlib.decompressobj(31)
    eventos = []
    for chunk in chunks:
        texto = d.decompress(chunk).decode()
        assert texto.endswith("\n\n") and texto.count("\n\n") == 1
        eventos.append(_parse(texto)[0])
    assert eventos[0][0] == "build" and eventos[1][0] == "board"


def test_sin_accept_encoding_sale_en_texto_plano(app, cookie):
    start, chunks = asyncio.run(drive(app, cookie, quiere=2))
    assert "content-encoding" not in start["headers"]
    assert [e[0] for e in _parse("".join(c.decode() for c in chunks))] == ["build", "board"]


def test_los_ping_tambien_llegan_con_gzip(app, cookie):
    start, chunks = asyncio.run(drive(app, cookie, accept="gzip", quiere=4))
    d = zlib.decompressobj(31)
    nombres = [_parse(d.decompress(c).decode())[0][0] for c in chunks]
    assert "ping" in nombres


def test_sse_gzip_apagado_sale_en_texto_plano(app, cookie, cfg):
    cfg.sse_gzip = False
    start, chunks = asyncio.run(drive(app, cookie, accept="gzip", quiere=2))
    assert "content-encoding" not in start["headers"]
    assert chunks[0].decode().startswith("event: build")


def test_el_stream_no_recalcula_el_fingerprint(app, cookie, enchufe, monkeypatch):
    llamadas = []
    original = app_mod.fingerprint

    def espia(board):
        llamadas.append(1)
        return original(board)

    monkeypatch.setattr(app_mod, "fingerprint", espia)
    hub = app.state.hub

    async def antes(n):
        if n == 2:
            aplicar_snapshot(enchufe, make_snapshot("blocked"))
            await hub.refresh()

    start, chunks = asyncio.run(drive(app, cookie, quiere=6, antes=antes))
    nombres = [e[0] for e in _parse("".join(c.decode() for c in chunks))]
    assert nombres.count("board") == 2
    assert llamadas == []
