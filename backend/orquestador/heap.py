"""Devolverle al sistema la memoria que el proceso liberó y glibc retiene en sus arenas."""
import asyncio
import logging
from typing import Awaitable, Callable, Optional

log = logging.getLogger(__name__)

INTERVALO_S = 600


def trim_heap() -> None:
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


async def devolver_periodicamente(*, intervalo: float = INTERVALO_S, trim: Callable[[], None] = trim_heap,
                                  sleep: Callable[[float], Awaitable] = asyncio.sleep,
                                  vueltas: Optional[int] = None) -> None:
    hechas = 0
    while vueltas is None or hechas < vueltas:
        await sleep(intervalo)
        try:
            await asyncio.to_thread(trim)
        except Exception:
            log.exception("no pude devolver memoria al sistema")
        hechas += 1
