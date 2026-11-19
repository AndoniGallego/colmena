"""Abrir en la pantalla de la notebook una terminal enganchada a una sesión viva (`orquestador ver <sesión>`)."""
import asyncio
import logging
import os
import re
import shutil
import sys
import time
import unicodedata
from collections.abc import Awaitable, Callable

log = logging.getLogger("orquestador.ir_a_pc")

TITULO_MAX = 80
ESPERA_ENTRE_LANZAMIENTOS = 3.0
TOPE_GLOBAL = 5
VENTANA_TOPE = 60.0
TIMEOUT_SYSTEMCTL = 2.0
SELECTOR = re.compile(r"g\d+:p\d+")
ENTORNO_PERMITIDO = (
    "PATH", "HOME", "LANG", "USER", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS", "XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP",
)
MODULO_CLI = "orquestador.cli"

Lanzador = Callable[..., Awaitable[None]]
LectorSystemd = Callable[[], Awaitable[str]]


class IrAPcError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def selector_valido(sel: object) -> bool:
    return isinstance(sel, str) and SELECTOR.fullmatch(sel) is not None


def sanear_titulo(texto: str, respaldo: str) -> str:
    limpio = "".join(c for c in str(texto or "") if unicodedata.category(c) not in ("Cc", "Cf", "Cs"))
    limpio = " ".join(limpio.split())[:TITULO_MAX].strip()
    return limpio or respaldo


def argv_de(titulo: str, selector: str) -> list[str]:
    return ["gnome-terminal", f"--title={titulo}", "--", sys.executable, "-m", MODULO_CLI, "ver", selector]


def entorno_permitido(environ: dict) -> dict:
    return {k: v for k, v in environ.items() if v and (k in ENTORNO_PERMITIDO or k.startswith("LC_"))}


def parsear_entorno(salida: str) -> dict:
    out = {}
    for linea in salida.splitlines():
        clave, sep, valor = linea.partition("=")
        if sep and clave:
            out[clave] = valor
    return out


async def leer_systemctl() -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "--user", "show-environment",
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
    except (OSError, ValueError):
        return ""
    try:
        salida, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT_SYSTEMCTL)
    except (asyncio.TimeoutError, OSError):
        try:
            proc.kill()
            await proc.wait()
        except (ProcessLookupError, OSError):
            pass
        return ""
    return salida.decode("utf-8", "replace")


async def lanzar_desacoplado(argv: list[str], env: dict | None = None) -> None:
    await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )


class IrAPc:
    def __init__(
        self,
        lanzador: Lanzador = lanzar_desacoplado,
        reloj: Callable[[], float] = time.monotonic,
        systemctl: LectorSystemd = leer_systemctl,
    ):
        self.lanzador = lanzador
        self.reloj = reloj
        self.systemctl = systemctl
        self._ultimo: dict[str, float] = {}
        self._lanzados: list[float] = []

    async def _entorno(self) -> dict:
        env = entorno_permitido(dict(os.environ))
        if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
            sistema = parsear_entorno(await self.systemctl())
            for clave in ("WAYLAND_DISPLAY", "DISPLAY"):
                if sistema.get(clave):
                    env[clave] = sistema[clave]
        if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
            raise IrAPcError(503, "La notebook no tiene la pantalla activa")
        if not env.get("DBUS_SESSION_BUS_ADDRESS"):
            runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
            bus = os.path.join(runtime, "bus")
            if not os.path.exists(bus):
                raise IrAPcError(503, "La notebook no tiene la sesión gráfica disponible")
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"
        return env

    def _reservar(self, sid: str) -> float:
        ahora = self.reloj()
        self._ultimo = {k: t for k, t in self._ultimo.items() if ahora - t < ESPERA_ENTRE_LANZAMIENTOS}
        self._lanzados = [t for t in self._lanzados if ahora - t < VENTANA_TOPE]
        if sid in self._ultimo:
            raise IrAPcError(429, "Ya la abriste hace un momento")
        if len(self._lanzados) >= TOPE_GLOBAL:
            raise IrAPcError(429, "Abriste muchas ventanas seguidas, esperá un momento")
        self._ultimo[sid] = ahora
        self._lanzados.append(ahora)
        return ahora

    def _devolver(self, sid: str, marca: float) -> None:
        if self._ultimo.get(sid) == marca:
            del self._ultimo[sid]
        if marca in self._lanzados:
            self._lanzados.remove(marca)

    async def abrir(self, sid: str, pane_id: object, nombre: str) -> None:
        if not selector_valido(pane_id):
            raise IrAPcError(409, "Esta sesión no corre en una terminal de Colmena")
        if not shutil.which("gnome-terminal"):
            raise IrAPcError(503, "No encontré una terminal en la notebook")
        env = await self._entorno()
        marca = self._reservar(sid)
        try:
            await self.lanzador(argv_de(sanear_titulo(nombre, str(pane_id)), str(pane_id)), env)
        except Exception as exc:
            self._devolver(sid, marca)
            log.warning("ir a la notebook: no pude abrir la terminal (%s)", type(exc).__name__)
            raise IrAPcError(503, "No pude abrir la terminal en la notebook")
