import zlib
from typing import AsyncIterator


def acepta_gzip(accept_encoding: str) -> bool:
    for parte in (accept_encoding or "").split(","):
        token, _, params = parte.strip().partition(";")
        if token.strip().lower() != "gzip":
            continue
        q = params.replace(" ", "").lower()
        return not (q.startswith("q=") and _q_cero(q[2:]))
    return False


def _q_cero(valor: str) -> bool:
    try:
        return float(valor) == 0.0
    except ValueError:
        return False


async def comprimir(stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
    """Un evento por chunk: Z_SYNC_FLUSH deja cada evento descomprimible sin esperar al siguiente."""
    comp = zlib.compressobj(6, zlib.DEFLATED, 31)
    try:
        async for texto in stream:
            yield comp.compress(texto.encode("utf-8")) + comp.flush(zlib.Z_SYNC_FLUSH)
    finally:
        await stream.aclose()
