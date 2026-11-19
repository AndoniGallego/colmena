import asyncio
import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator
from typing import Any, Awaitable, Callable, Optional, Union

from .entornos import NOMBRE_RE

log = logging.getLogger("orquestador.entornos_vigia")
BACKOFF_INICIAL = 5
BACKOFF_TOPE = 300
VENTANA_STOP = 30.0
COOLDOWN_AVISO = 600.0
TITULO = "Entornos"
_FUERA_DE_TAG = re.compile(r"[^A-Za-z0-9_.-]")


def ref_aviso(proyecto: str, servicio: str) -> str:
    return f"{proyecto}:{_FUERA_DE_TAG.sub('-', servicio)}"[:100]


class VigiaEntornos:
    def __init__(
        self,
        docker_bin: Optional[str],
        avisar: Callable[[str, str, str], Awaitable[Any]],
        *,
        abrir: Optional[Callable[[], Union[AsyncIterator[str], Awaitable[AsyncIterator[str]]]]] = None,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        now: Callable[[], float] = time.monotonic,
    ):
        self.docker_bin = docker_bin
        self.avisar = avisar
        self._abrir = abrir
        self._sleep = sleep
        self._now = now
        self.parado: dict[str, float] = {}
        self._ultimo_aviso: dict[tuple[str, str], float] = {}
        self._backoff = BACKOFF_INICIAL
        self.ultimo_ts: int | None = None

    def argv_events(self) -> list[str]:
        args = [self.docker_bin, "events", "--format", "{{json .}}", "--filter", "type=container"]
        if self.ultimo_ts is not None:
            args.extend(["--since", str(self.ultimo_ts)])
        return args

    async def _iter_default(self) -> AsyncIterator[str]:
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        proc = await asyncio.create_subprocess_exec(
            *self.argv_events(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
        try:
            if proc.stdout is None:
                return
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                yield raw.decode(errors="replace").rstrip("\n")
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()

    async def _fuente(self) -> AsyncIterator[str]:
        abrir = self._abrir or (lambda: self._iter_default())
        fuente = abrir()
        if asyncio.iscoroutine(fuente):
            fuente = await fuente
        return fuente

    async def run(self) -> None:
        if not self.docker_bin:
            return
        while True:
            fuente: AsyncIterator[str] | None = None
            hubo_linea = False
            try:
                fuente = await self._fuente()
                async for linea in fuente:
                    hubo_linea = True
                    await self.procesar(linea)
                log.warning("docker events terminó, reintento en %ss", self._backoff)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("docker events falló, reintento en %ss", self._backoff)
            finally:
                if fuente is not None:
                    aclose = getattr(fuente, "aclose", None)
                    if aclose is not None:
                        await aclose()
            if hubo_linea:
                self._backoff = BACKOFF_INICIAL
            await self._sleep(self._backoff)
            if not hubo_linea:
                self._backoff = min(self._backoff * 2, BACKOFF_TOPE)

    def _limpiar_parado(self) -> None:
        ahora = self._now()
        for cid, cuando in list(self.parado.items()):
            if ahora - cuando > VENTANA_STOP:
                del self.parado[cid]

    async def _avisar_si_puede(self, cuerpo: str, proyecto: str, servicio: str, tipo: str) -> None:
        ref = ref_aviso(proyecto, servicio)
        clave = (ref, tipo)
        ahora = self._now()
        if ahora - self._ultimo_aviso.get(clave, -COOLDOWN_AVISO) < COOLDOWN_AVISO:
            return
        try:
            await self.avisar(TITULO, cuerpo, ref)
        except Exception:
            log.exception("avisar falló para %s", ref)
            return
        self._ultimo_aviso[clave] = ahora

    async def procesar(self, linea: str) -> None:
        self._limpiar_parado()
        try:
            evento = json.loads(linea)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(evento, dict):
            return
        t = evento.get("time")
        if isinstance(t, int):
            self.ultimo_ts = t
        accion = evento.get("Action") or evento.get("status")
        if not isinstance(accion, str):
            return
        actor = evento.get("Actor")
        attrs = actor.get("Attributes") if isinstance(actor, dict) else None
        if not isinstance(attrs, dict):
            attrs = {}
        cid = evento.get("id")
        if not isinstance(cid, str) and isinstance(actor, dict):
            cid = actor.get("ID")
        if not isinstance(cid, str):
            cid = ""
        proyecto = attrs.get("com.docker.compose.project")
        if not isinstance(proyecto, str) or not NOMBRE_RE.match(proyecto):
            return
        servicio = attrs.get("com.docker.compose.service") or attrs.get("name") or ""
        if not isinstance(servicio, str):
            servicio = str(servicio)

        if accion in ("stop", "kill"):
            if cid:
                self.parado[cid] = self._now()
            return
        if accion == "die":
            parado = self.parado.get(cid)
            if parado is not None and self._now() - parado < VENTANA_STOP:
                return
            exit_code = attrs.get("exitCode")
            if exit_code is not None and str(exit_code) == "0":
                return
            cuerpo = f"Se cayó {servicio} ({proyecto})"
            if exit_code is not None:
                cuerpo += f", código {exit_code}"
            await self._avisar_si_puede(cuerpo, proyecto, servicio, "die")
            return
        if accion == "health_status: unhealthy":
            await self._avisar_si_puede(
                f"{servicio} está enfermo ({proyecto})",
                proyecto,
                servicio,
                "unhealthy",
            )
