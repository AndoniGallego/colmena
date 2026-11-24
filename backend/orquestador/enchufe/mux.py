import asyncio
import logging
import os
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from orquestador.config import Config

from .base import (
    Evento,
    Formato,
    Fuente,
    NoDisponible,
    NoExiste,
    Tecla,
    Terminales,
    TerminalesError,
    _CONFIRMAR_PROMPT,
    _LANZAMIENTO_SHELL,
)
from .herdr import AdaptadorHerdr, HerdrClient, herdr_instalado
from .ids import es_guardian, tipo_de_id
from .modelo import Creado, Espacio, EstadoSesion, InfoProceso, Lanzamiento, Linea, Sesion, Tablero, TomaPrompt

log = logging.getLogger(__name__)


def _home_normalizado(home: str) -> str:
    return os.path.normpath(os.path.realpath(home))


def _cwd_en_home(cwd: str, cwd_primer_plano: str | None, home: str) -> bool:
    ref = _home_normalizado(home)
    if _home_normalizado(cwd) != ref:
        return False
    if cwd_primer_plano is not None and _home_normalizado(cwd_primer_plano) != ref:
        return False
    return True


def _sesion_es_shell_vacia(s: Sesion) -> bool:
    if s.programa == "claude" or s.es_agente:
        return False
    if s.claude_session_id is not None:
        return False
    if s.agente or s.nombre_agente:
        return False
    return True


def _espacio_herdr_vacio_por_defecto(
    esp: Espacio,
    lineas_por_id: dict[str, Linea],
    sesiones_por_id: dict[str, Sesion],
    home: str,
) -> bool:
    if len(esp.lineas) != 1:
        return False
    linea = lineas_por_id.get(esp.lineas[0])
    if linea is None:
        return False
    if len(linea.sesiones) != 1:
        return False
    ses = sesiones_por_id.get(linea.sesiones[0])
    if ses is None:
        return False
    if ses.backend != "herdr" or ses.espacio_id != esp.id:
        return False
    if not _sesion_es_shell_vacia(ses):
        return False
    return _cwd_en_home(ses.cwd, ses.cwd_primer_plano, home)


def _sin_espacio_herdr_vacio(tablero: Tablero, home: str) -> Tablero:
    lineas_por_id = {l.id: l for l in tablero.lineas}
    sesiones_por_id = {s.id: s for s in tablero.sesiones}
    espacios_ocultar: set[str] = set()
    for esp in tablero.espacios:
        sesiones_esp = [sesiones_por_id[sid] for l in esp.lineas if (ln := lineas_por_id.get(l)) for sid in ln.sesiones if sid in sesiones_por_id]
        if sesiones_esp and not all(s.backend == "herdr" for s in sesiones_esp):
            continue
        if _espacio_herdr_vacio_por_defecto(esp, lineas_por_id, sesiones_por_id, home):
            espacios_ocultar.add(esp.id)
    if not espacios_ocultar:
        return tablero
    lineas_quitar = {l.id for l in tablero.lineas if l.espacio_id in espacios_ocultar}
    sesiones_quitar = {
        sid for l in tablero.lineas if l.id in lineas_quitar for sid in l.sesiones
    }
    linea_enfocada = tablero.linea_enfocada
    if linea_enfocada in lineas_quitar:
        linea_enfocada = None
    return Tablero(
        tuple(e for e in tablero.espacios if e.id not in espacios_ocultar),
        tuple(l for l in tablero.lineas if l.id not in lineas_quitar),
        tuple(s for s in tablero.sesiones if s.id not in sesiones_quitar),
        tablero.revision,
        linea_enfocada,
        tablero.conflictos,
        tablero.caidos,
    )


class Mux:
    nombre = "mux"

    def __init__(self, backends: Sequence[Terminales], nuevas_en: str = "herdr"):
        self.backends = tuple(backends)
        self.nuevas_en = nuevas_en
        caps: set[str] = set()
        for b in self.backends:
            caps.update(b.capacidades)
        self.capacidades = frozenset(caps)
        self._guardian_caido_logeado = False
        self._ultimo_guardian: Tablero | None = None

    def _backend(self, id: str) -> Terminales:
        destino = "guardian" if es_guardian(id) else "herdr"
        for b in self.backends:
            if b.nombre == destino:
                return b
        raise NoDisponible("no hay terminales para ese id")

    def _backend_nombre(self, nombre: str) -> Terminales:
        for b in self.backends:
            if b.nombre == nombre:
                return b
        raise NoDisponible("no hay terminales para ese backend")

    async def tablero(self) -> Tablero:
        tableros: list[Tablero] = []
        caidos: list[str] = []
        for b in self.backends:
            if b.nombre == "guardian":
                try:
                    t = await b.tablero()
                    self._ultimo_guardian = t
                    self._guardian_caido_logeado = False
                    tableros.append(t)
                except (TerminalesError, OSError) as exc:
                    ultimo = getattr(b, "ultimo_tablero", None) or self._ultimo_guardian
                    tableros.append(ultimo or Tablero((), (), (), 0))
                    caidos.append("guardian")
                    if not self._guardian_caido_logeado:
                        log.warning("tablero del guardián no disponible: %s", exc)
                        self._guardian_caido_logeado = True
            else:
                tableros.append(await b.tablero())
        espacios = tuple(e for t in tableros for e in t.espacios)
        lineas = tuple(l for t in tableros for l in t.lineas)
        sesiones = tuple(s for t in tableros for s in t.sesiones)
        revision = sum(t.revision for t in tableros)
        linea_enfocada = next((t.linea_enfocada for t in tableros if t.linea_enfocada is not None), None)
        conflictos = tuple(c for t in tableros for c in t.conflictos)
        return _sin_espacio_herdr_vacio(
            Tablero(
                espacios, lineas, sesiones, revision, linea_enfocada, conflictos, tuple(caidos),
            ),
            os.path.expanduser("~"),
        )

    async def proceso(self, sesion_id: str) -> InfoProceso:
        return await self._backend(sesion_id).proceso(sesion_id)

    async def leer(
        self,
        sesion_id: str,
        *,
        fuente: Fuente = "visible",
        formato: Formato = "texto",
        lineas: int | None = None,
    ) -> str:
        return await self._backend(sesion_id).leer(
            sesion_id, fuente=fuente, formato=formato, lineas=lineas
        )

    async def abrir_vivo(self, sesion_id: str, *, tamano: tuple[int, int] = (120, 40)):
        if not es_guardian(sesion_id) or tipo_de_id(sesion_id) != "sesion":
            raise NoExiste(sesion_id)
        for b in self.backends:
            if b.nombre == "guardian":
                fn = getattr(b, "abrir_vivo", None)
                if fn is None:
                    raise NoDisponible("el guardián no está configurado")
                return await fn(sesion_id, tamano=tamano)
        raise NoDisponible("el guardián no está configurado")

    async def crear_espacio(self, nombre: str, cwd: str) -> Creado:
        destino = self.nuevas_en
        try:
            return await self._backend_nombre(destino).crear_espacio(nombre, cwd)
        except NoDisponible:
            if destino != "guardian":
                raise
            if not any(b.nombre == "herdr" for b in self.backends):
                raise
            log.warning("guardián no disponible al crear espacio, uso Herdr")
            return await self._backend_nombre("herdr").crear_espacio(nombre, cwd)

    async def crear_linea(
        self,
        espacio_id: str,
        nombre: str,
        cwd: str,
        programa: Lanzamiento = _LANZAMIENTO_SHELL,
    ) -> Creado:
        return await self._backend(espacio_id).crear_linea(espacio_id, nombre, cwd, programa)

    async def arrancar_claude(
        self,
        sesion_id: str,
        nombre: str,
        resume: str | None = None,
        *,
        modo: str | None = None,
        dirs_extra: list[str] | None = None,
    ) -> None:
        backend = self._backend(sesion_id)
        if modo is None:
            await backend.arrancar_claude(sesion_id, nombre, resume)
        elif not dirs_extra:
            await backend.arrancar_claude(sesion_id, nombre, resume, modo=modo)
        else:
            await backend.arrancar_claude(sesion_id, nombre, resume, modo=modo, dirs_extra=dirs_extra)

    async def renombrar(self, objetivo_id: str, nombre: str) -> None:
        backend = self._backend(objetivo_id)
        if "renombrar" not in backend.capacidades:
            raise NoDisponible("renombrar no disponible en este backend")
        await backend.renombrar(objetivo_id, nombre)

    async def cerrar(self, objetivo_id: str) -> None:
        await self._backend(objetivo_id).cerrar(objetivo_id)

    async def enfocar(self, objetivo_id: str) -> None:
        backend = self._backend(objetivo_id)
        if "foco" not in backend.capacidades:
            return
        await backend.enfocar(objetivo_id)

    async def mandar_prompt(
        self,
        sesion_id: str,
        texto: str,
        *,
        confirmar: frozenset[EstadoSesion] = _CONFIRMAR_PROMPT,
        timeout: float = 30.0,
    ) -> TomaPrompt:
        return await self._backend(sesion_id).mandar_prompt(
            sesion_id, texto, confirmar=confirmar, timeout=timeout
        )

    async def interrumpir(self, sesion_id: str) -> None:
        await self._backend(sesion_id).interrumpir(sesion_id)

    async def esperar(
        self, sesion_id: str, hasta: frozenset[EstadoSesion], timeout: float
    ) -> EstadoSesion:
        return await self._backend(sesion_id).esperar(sesion_id, hasta, timeout)

    async def esperar_listo(self, sesion_id: str, timeout: float) -> str:
        return await self._backend(sesion_id).esperar_listo(sesion_id, timeout)

    async def teclas(self, sesion_id: str, teclas: Sequence[Tecla]) -> None:
        await self._backend(sesion_id).teclas(sesion_id, teclas)

    async def escribir(self, sesion_id: str, texto: str) -> None:
        await self._backend(sesion_id).escribir(sesion_id, texto)

    async def ejecutar(self, sesion_id: str, comando: str) -> None:
        await self._backend(sesion_id).ejecutar(sesion_id, comando)

    def conectar_estados(self, estados) -> None:
        for b in self.backends:
            fn = getattr(b, "conectar_estados", None)
            if fn is not None:
                fn(estados)

    def suscribir(self) -> AsyncIterator[Evento]:
        subs = []
        for b in self.backends:
            sub = b.suscribir()
            if b.nombre == "guardian":
                sub = _SuscripcionGuardianMux(sub)
            subs.append(sub)
        return _SuscripcionMux(subs)


class _SuscripcionMux:
    def __init__(self, subs: list[AsyncIterator[Evento]]) -> None:
        self._subs = subs
        self._cola: asyncio.Queue[Evento | None] = asyncio.Queue()
        self._cerrada = False
        self._error: Exception | None = None
        self._tareas = [asyncio.create_task(self._bomba(s)) for s in subs]
        self._cierres_hijos: set[asyncio.Task] = set()

    def _cancelar_bombas(self) -> None:
        for t in self._tareas:
            if not t.done():
                t.cancel()

    def _programar_cierre_hijos(self) -> None:
        for sub in self._subs:
            aclose = getattr(sub, "aclose", None)
            if aclose is None:
                continue

            async def _cerrar(aclose=aclose) -> None:
                try:
                    await aclose()
                except Exception:
                    log.exception("error al cerrar suscripción hijo del mux")

            t = asyncio.ensure_future(_cerrar())
            self._cierres_hijos.add(t)
            t.add_done_callback(self._cierres_hijos.discard)

    def _liberar(self) -> None:
        if self._cerrada:
            return
        self._cerrada = True
        self._cancelar_bombas()
        self._programar_cierre_hijos()

    async def _bomba(self, sub: AsyncIterator[Evento]) -> None:
        try:
            async for ev in sub:
                if self._cerrada:
                    break
                await self._cola.put(ev)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("error en suscripción de backend del mux")
            if self._error is None:
                self._error = exc
            await self._cola.put(None)
        else:
            await self._cola.put(None)

    def __aiter__(self) -> AsyncIterator[Evento]:
        return self

    async def __anext__(self) -> Evento:
        if self._cerrada:
            if self._error is not None:
                exc = self._error
                self._error = None
                raise exc
            raise StopAsyncIteration
        try:
            while True:
                item = await self._cola.get()
                if self._error is not None:
                    exc = self._error
                    self._error = None
                    self._liberar()
                    await asyncio.gather(*self._tareas, return_exceptions=True)
                    if self._cierres_hijos:
                        await asyncio.gather(*self._cierres_hijos, return_exceptions=True)
                    raise exc
                if item is not None:
                    return item
                if self._cerrada:
                    raise StopAsyncIteration
                if all(t.done() for t in self._tareas):
                    raise StopAsyncIteration
        except asyncio.CancelledError:
            self._liberar()
            raise

    async def aclose(self) -> None:
        if self._cerrada:
            return
        self._cerrada = True
        self._cancelar_bombas()
        err: BaseException | None = None
        try:
            for sub in self._subs:
                aclose = getattr(sub, "aclose", None)
                if aclose is not None:
                    await aclose()
        except BaseException as exc:
            err = exc
        finally:
            await asyncio.gather(*self._tareas, return_exceptions=True)
            while not self._cola.empty():
                self._cola.get_nowait()
            try:
                self._cola.put_nowait(None)
            except asyncio.QueueFull:
                pass
        if err is not None:
            raise err


class _SuscripcionGuardianMux:
    def __init__(self, hijo: AsyncIterator[Evento]) -> None:
        self._hijo = hijo

    def __aiter__(self) -> AsyncIterator[Evento]:
        self._hijo = self._hijo.__aiter__()
        return self

    async def __anext__(self) -> Evento:
        ev = await self._hijo.__anext__()
        if ev.tipo in ("caido", "volvio") and ev.backend == "guardian":
            return Evento("tablero", "guardian", datos={"motivo": "seguridad"})
        return ev

    async def aclose(self) -> None:
        aclose = getattr(self._hijo, "aclose", None)
        if aclose is not None:
            await aclose()


def crear_terminales(
    cfg: Config,
    cliente=None,
    *,
    poll: float = 5.0,
    guardian=None,
) -> Mux:
    term_cfg = cfg.terminales if isinstance(cfg.terminales, dict) else {}
    nuevas_en = term_cfg.get("nuevas_en", "herdr")
    backends_cfg = term_cfg.get("backends", ["herdr"])
    if nuevas_en not in ("herdr", "guardian"):
        log.warning("terminales.nuevas_en inválido (%s), uso herdr", nuevas_en)
        nuevas_en = "herdr"
    if not isinstance(backends_cfg, list):
        backends_cfg = ["herdr"]
    filtrado: list[str] = []
    for b in backends_cfg:
        if b in ("herdr", "guardian"):
            filtrado.append(b)
        else:
            log.warning("backend desconocido en terminales.backends: %s", b)
    backends_cfg = filtrado

    usar_herdr = "herdr" in backends_cfg
    if usar_herdr and cliente is None:
        ruta = herdr_instalado(cfg)
        if ruta is None:
            usar_herdr = False
            log.warning("Herdr no está instalado: las terminales van solo por el guardián")
        else:
            cliente = HerdrClient(ruta)

    if not usar_herdr:
        if nuevas_en != "guardian":
            log.info("sin Herdr: nuevas terminales en el guardián")
        nuevas_en = "guardian"

    backends: list[Terminales] = []
    if usar_herdr:
        backends.append(AdaptadorHerdr(cliente, poll=poll))

    incluir_guardian = nuevas_en == "guardian" or "guardian" in backends_cfg
    if incluir_guardian:
        if guardian is not None:
            backends.append(guardian)
        else:
            from .guardian import ClienteGuardian

            gcfg = cfg.guardian if isinstance(cfg.guardian, dict) else {}
            ruta_raw = gcfg.get("socket")
            if ruta_raw:
                ruta = Path(str(ruta_raw))
            else:
                runtime = os.environ.get("XDG_RUNTIME_DIR")
                ruta = (
                    Path(runtime) / "colmena-guardian" / "guardian.sock"
                    if runtime
                    else None
                )
            if ruta is not None:
                backends.append(ClienteGuardian(ruta))
            else:
                if usar_herdr:
                    log.warning("sin socket del guardián ni XDG_RUNTIME_DIR; no incluyo guardián")
                    if nuevas_en == "guardian":
                        nuevas_en = "herdr"
                else:
                    log.error(
                        "sin Herdr y sin socket del guardián (XDG_RUNTIME_DIR o guardian.socket): "
                        "no hay terminales",
                    )
                    nuevas_en = "guardian"

    return Mux(backends, nuevas_en=nuevas_en)
