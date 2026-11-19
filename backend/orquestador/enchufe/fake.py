import asyncio
import re
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import replace

from .base import (
    TECLAS,
    Evento,
    Formato,
    Fuente,
    NoDisponible,
    NoExiste,
    NoTomado,
    Tecla,
    _CONFIRMAR_PROMPT,
    _LANZAMIENTO_SHELL,
)
from .herdr import tablero_de_snapshot
from .ids import tipo_de_id
from .modelo import (
    Creado,
    Espacio,
    EstadoSesion,
    InfoProceso,
    Lanzamiento,
    Linea,
    ProcesoPrimerPlano,
    Sesion,
    Tablero,
    TomaPrompt,
)

_VACIO_PROCESO = InfoProceso(None, None, None, False, ())


class FakeTerminales:
    nombre = "fake"
    capacidades = frozenset({"foco", "renombrar", "estado_propio", "retoma"})

    def __init__(
        self,
        tablero: Tablero | None = None,
        *,
        nombre: str = "fake",
        poll: float | None = None,
    ):
        self.nombre = nombre
        self.poll = poll
        self.tablero_actual = tablero or Tablero((), (), (), 0)
        self.calls: list[tuple] = []
        self.fallas: dict[str, Exception] = {}
        self.procesos: dict[str, InfoProceso | Exception] = {}
        self.pantallas: dict[str, str | Callable[[tuple], str]] = {}
        self.estados_tras_prompt: dict[str, EstadoSesion] = {}
        self.proximos_ids: list[tuple[str | None, str | None, str]] = []
        self.aplicar_cierres = True
        self._caido = False
        self._caido_notificado = False
        self._colas: set[asyncio.Queue[Evento]] = set()

    @classmethod
    def desde_snapshot(cls, snap: dict, **kw) -> "FakeTerminales":
        return cls(tablero_de_snapshot(snap, 0), **kw)

    def calls_of(self, op: str) -> list[tuple]:
        return [c for c in self.calls if c and c[0] == op]

    def caer(self) -> None:
        # Solo tablero() queda indisponible; el resto de operaciones sigue respondiendo.
        self._caido = True

    def volver(self) -> None:
        self._caido = False

    def emitir(self, ev: Evento) -> None:
        self._empujar(ev)

    def cambiar(self, **reemplazos) -> None:
        self.tablero_actual = replace(self.tablero_actual, **reemplazos)
        self._emitir_tablero()

    async def tablero(self) -> Tablero:
        if self._caido:
            self._notificar_caido()
            raise NoDisponible("herdr no responde")
        self._notificar_volvio()
        return self.tablero_actual

    async def proceso(self, sesion_id: str) -> InfoProceso:
        self._registrar("proceso", sesion_id)
        self._exigir_sesion(sesion_id)
        val = self.procesos.get(sesion_id, _VACIO_PROCESO)
        if isinstance(val, Exception):
            raise val
        return val

    async def leer(
        self,
        sesion_id: str,
        *,
        fuente: Fuente = "visible",
        formato: Formato = "texto",
        lineas: int | None = None,
    ) -> str:
        self._registrar("leer", sesion_id, fuente, formato, lineas)
        self._exigir_sesion(sesion_id)
        val = self.pantallas.get(sesion_id, "")
        if callable(val):
            return val(("leer", sesion_id, fuente, formato, lineas))
        return val

    async def crear_espacio(self, nombre: str, cwd: str) -> Creado:
        if self._caido:
            raise NoDisponible("guardián no disponible")
        self._registrar("crear_espacio", nombre, cwd)
        eid, lid, sid = self._siguiente_ids(None)
        esp = Espacio(eid, nombre, (lid,))
        lin = Linea(lid, eid, nombre, (sid,))
        ses = self._sesion_shell(sid, lid, eid, cwd)
        self._anexar(esp, lin, ses)
        return Creado(eid, lid, sid)

    async def crear_linea(
        self,
        espacio_id: str,
        nombre: str,
        cwd: str,
        programa: Lanzamiento = _LANZAMIENTO_SHELL,
    ) -> Creado:
        self._registrar("crear_linea", espacio_id, nombre, cwd)
        self._exigir_espacio(espacio_id)
        _, lid, sid = self._siguiente_ids(espacio_id)
        lin = Linea(lid, espacio_id, nombre, (sid,))
        ses = self._sesion_shell(sid, lid, espacio_id, cwd)
        self._anexar_linea(lin, ses)
        return Creado(espacio_id, lid, sid)

    async def arrancar_claude(
        self, sesion_id: str, nombre: str, resume: str | None = None, *, modo: str | None = None
    ) -> None:
        if modo is None:
            self._registrar("arrancar_claude", sesion_id, nombre, resume)
        else:
            self._registrar("arrancar_claude", sesion_id, nombre, resume, modo)
        if resume:
            raise NoDisponible("retoma con resume no disponible en adaptador herdr")
        self._exigir_sesion(sesion_id)

    async def renombrar(self, objetivo_id: str, nombre: str) -> None:
        self._registrar("renombrar", objetivo_id, nombre)
        tipo = tipo_de_id(objetivo_id)
        if tipo == "linea":
            self._exigir_linea(objetivo_id)
            lineas = tuple(
                replace(l, nombre=nombre) if l.id == objetivo_id else l for l in self.tablero_actual.lineas
            )
            self._poner_tablero(replace(self.tablero_actual, lineas=lineas))
            return
        if tipo == "espacio":
            self._exigir_espacio(objetivo_id)
            espacios = tuple(
                replace(e, nombre=nombre) if e.id == objetivo_id else e for e in self.tablero_actual.espacios
            )
            self._poner_tablero(replace(self.tablero_actual, espacios=espacios))
            return
        raise NoExiste(objetivo_id)

    async def cerrar(self, objetivo_id: str) -> None:
        self._registrar("cerrar", objetivo_id)
        tipo = tipo_de_id(objetivo_id)
        if tipo == "linea":
            self._exigir_linea(objetivo_id)
            if self.aplicar_cierres:
                self._cerrar_linea(objetivo_id)
            return
        if tipo == "espacio":
            self._exigir_espacio(objetivo_id)
            if self.aplicar_cierres:
                self._cerrar_espacio(objetivo_id)
            return
        if tipo == "sesion":
            ses = self._exigir_sesion(objetivo_id)
            if self.aplicar_cierres:
                self._cerrar_sesion(ses)
            return
        raise NoExiste(objetivo_id)

    async def enfocar(self, objetivo_id: str) -> None:
        self._registrar("enfocar", objetivo_id)
        tipo = tipo_de_id(objetivo_id)
        if tipo == "linea":
            self._exigir_linea(objetivo_id)
            self._poner_tablero(replace(self.tablero_actual, linea_enfocada=objetivo_id))
            return
        if tipo == "espacio":
            self._exigir_espacio(objetivo_id)
            return
        raise NoExiste(objetivo_id)

    async def mandar_prompt(
        self,
        sesion_id: str,
        texto: str,
        *,
        confirmar: frozenset[EstadoSesion] = _CONFIRMAR_PROMPT,
        timeout: float = 30.0,
    ) -> TomaPrompt:
        self._registrar("mandar_prompt", sesion_id, texto)
        self._exigir_sesion(sesion_id)
        nuevo = self.estados_tras_prompt.get(sesion_id, "working")
        if nuevo in ("idle", "done"):
            raise NoTomado("no se tomó")
        sesiones = tuple(
            replace(s, estado=nuevo) if s.id == sesion_id else s for s in self.tablero_actual.sesiones
        )
        self._poner_tablero(replace(self.tablero_actual, sesiones=sesiones))
        return TomaPrompt(True, nuevo, "herdr")

    async def interrumpir(self, sesion_id: str) -> None:
        self._registrar("interrumpir", sesion_id)
        self._exigir_sesion(sesion_id)

    async def esperar(
        self, sesion_id: str, hasta: frozenset[EstadoSesion], timeout: float
    ) -> EstadoSesion:
        # No espera de verdad: devuelve al instante según el estado actual o el primer `hasta`.
        self._registrar("esperar", sesion_id, tuple(sorted(hasta)), timeout)
        self._exigir_sesion(sesion_id)
        ses = next(s for s in self.tablero_actual.sesiones if s.id == sesion_id)
        if ses.estado in hasta:
            return ses.estado
        for e in ("working", "blocked", "idle", "done", "terminada", "perdida"):
            if e in hasta:
                return e  # type: ignore[return-value]
        return next(iter(hasta))

    async def esperar_listo(self, sesion_id: str, timeout: float) -> str:
        self._registrar("esperar_listo", sesion_id, timeout)
        self._exigir_sesion(sesion_id)
        return "guardian"

    async def teclas(self, sesion_id: str, teclas: Sequence[Tecla]) -> None:
        if not teclas:
            raise ValueError("tecla no permitida")
        for t in teclas:
            if t not in TECLAS:
                raise ValueError("tecla no permitida")
        self._registrar("teclas", sesion_id, tuple(teclas))
        self._exigir_sesion(sesion_id)

    async def escribir(self, sesion_id: str, texto: str) -> None:
        self._registrar("escribir", sesion_id, texto)
        self._exigir_sesion(sesion_id)

    async def ejecutar(self, sesion_id: str, comando: str) -> None:
        self._registrar("ejecutar", sesion_id, comando)
        self._exigir_sesion(sesion_id)

    def suscribir(self) -> AsyncIterator[Evento]:
        return _SuscripcionFake(self)

    def _registrar(self, op: str, *args) -> None:
        self.calls.append((op, *args))
        exc = self.fallas.get(op)
        if exc is not None:
            raise exc

    def _notificar_caido(self) -> None:
        if self._caido_notificado:
            return
        self._caido_notificado = True
        self._empujar(Evento("caido", self.nombre))

    def _notificar_volvio(self) -> None:
        if not self._caido_notificado:
            return
        self._caido_notificado = False
        self._empujar(Evento("volvio", self.nombre))

    def _empujar(self, ev: Evento) -> None:
        for cola in self._colas:
            cola.put_nowait(ev)

    def _emitir_tablero(self) -> None:
        self._empujar(Evento("tablero", self.nombre))

    def _poner_tablero(self, tablero: Tablero) -> None:
        self.tablero_actual = replace(tablero, revision=self.tablero_actual.revision + 1)
        self._emitir_tablero()

    def _exigir_sesion(self, sesion_id: str) -> Sesion:
        for s in self.tablero_actual.sesiones:
            if s.id == sesion_id:
                return s
        raise NoExiste(sesion_id)

    def _exigir_linea(self, linea_id: str) -> Linea:
        for l in self.tablero_actual.lineas:
            if l.id == linea_id:
                return l
        raise NoExiste(linea_id)

    def _exigir_espacio(self, espacio_id: str) -> Espacio:
        for e in self.tablero_actual.espacios:
            if e.id == espacio_id:
                return e
        raise NoExiste(espacio_id)

    @staticmethod
    def _sesion_shell(sid: str, lid: str, eid: str, cwd: str) -> Sesion:
        return Sesion(
            id=sid,
            linea_id=lid,
            espacio_id=eid,
            programa="shell",
            estado="idle",
            estado_fuente="herdr",
            claude_session_id=None,
            cwd=cwd,
            cwd_primer_plano=None,
            titulo="",
            revision=None,
            backend="herdr",
        )

    def _siguiente_ids(self, espacio_id: str | None) -> tuple[str, str, str]:
        if self.proximos_ids:
            e, l, s = self.proximos_ids.pop(0)
            if espacio_id is not None:
                e = espacio_id
                if l is None:
                    l = self._nueva_linea(espacio_id)
                if s is None:
                    s = self._nueva_sesion(espacio_id, l)
            else:
                if e is None:
                    e = self._nuevo_espacio()
                if l is None:
                    l = f"{e}:t1"
                if s is None:
                    s = f"{e}:p1"
            return e, l, s
        if espacio_id is not None:
            lid = self._nueva_linea(espacio_id)
            return espacio_id, lid, self._nueva_sesion(espacio_id, lid)
        e = self._nuevo_espacio()
        return e, f"{e}:t1", f"{e}:p1"

    def _nuevo_espacio(self) -> str:
        nums = []
        for e in self.tablero_actual.espacios:
            m = re.fullmatch(r"w(\d+)", e.id)
            if m:
                nums.append(int(m.group(1)))
        n = max(nums, default=0) + 1
        return f"w{n}"

    def _nueva_linea(self, espacio_id: str) -> str:
        nums = []
        for l in self.tablero_actual.lineas:
            if l.espacio_id != espacio_id:
                continue
            m = re.fullmatch(re.escape(espacio_id) + r":t(\d+)", l.id)
            if m:
                nums.append(int(m.group(1)))
        n = max(nums, default=0) + 1
        return f"{espacio_id}:t{n}"

    def _nueva_sesion(self, espacio_id: str, linea_id: str) -> str:
        nums = []
        for s in self.tablero_actual.sesiones:
            if s.espacio_id != espacio_id:
                continue
            m = re.fullmatch(re.escape(espacio_id) + r":p(\d+)", s.id)
            if m:
                nums.append(int(m.group(1)))
        n = max(nums, default=0) + 1
        return f"{espacio_id}:p{n}"

    def _anexar(self, esp: Espacio, lin: Linea, ses: Sesion) -> None:
        espacios = self.tablero_actual.espacios + (esp,)
        lineas = self.tablero_actual.lineas + (lin,)
        sesiones = self.tablero_actual.sesiones + (ses,)
        self._poner_tablero(
            replace(self.tablero_actual, espacios=espacios, lineas=lineas, sesiones=sesiones)
        )

    def _anexar_linea(self, lin: Linea, ses: Sesion) -> None:
        espacios = tuple(
            replace(e, lineas=e.lineas + (lin.id,)) if e.id == lin.espacio_id else e
            for e in self.tablero_actual.espacios
        )
        lineas = self.tablero_actual.lineas + (lin,)
        sesiones = self.tablero_actual.sesiones + (ses,)
        self._poner_tablero(
            replace(self.tablero_actual, espacios=espacios, lineas=lineas, sesiones=sesiones)
        )

    def _cerrar_linea(self, linea_id: str) -> None:
        lin = self._exigir_linea(linea_id)
        sesiones = tuple(s for s in self.tablero_actual.sesiones if s.linea_id != linea_id)
        lineas = tuple(l for l in self.tablero_actual.lineas if l.id != linea_id)
        espacios = tuple(
            replace(e, lineas=tuple(x for x in e.lineas if x != linea_id)) if e.id == lin.espacio_id else e
            for e in self.tablero_actual.espacios
        )
        foco = self.tablero_actual.linea_enfocada
        if foco == linea_id:
            foco = None
        self._poner_tablero(replace(self.tablero_actual, espacios=espacios, lineas=lineas, sesiones=sesiones, linea_enfocada=foco))

    def _cerrar_sesion(self, ses: Sesion) -> None:
        """Como herdr: el último panel de una pestaña se la lleva."""
        quedan = [s for s in self.tablero_actual.sesiones if s.linea_id == ses.linea_id and s.id != ses.id]
        if not quedan:
            self._cerrar_linea(ses.linea_id)
            return
        sesiones = tuple(s for s in self.tablero_actual.sesiones if s.id != ses.id)
        lineas = tuple(
            replace(l, sesiones=tuple(x for x in l.sesiones if x != ses.id),
                    declaradas=None if l.declaradas is None else l.declaradas - 1)
            if l.id == ses.linea_id else l
            for l in self.tablero_actual.lineas
        )
        self._poner_tablero(replace(self.tablero_actual, lineas=lineas, sesiones=sesiones))

    def _cerrar_espacio(self, espacio_id: str) -> None:
        lineas_ids = {l.id for l in self.tablero_actual.lineas if l.espacio_id == espacio_id}
        sesiones = tuple(s for s in self.tablero_actual.sesiones if s.espacio_id != espacio_id)
        lineas = tuple(l for l in self.tablero_actual.lineas if l.espacio_id != espacio_id)
        espacios = tuple(e for e in self.tablero_actual.espacios if e.id != espacio_id)
        foco = self.tablero_actual.linea_enfocada
        if foco in lineas_ids:
            foco = None
        self._poner_tablero(
            replace(self.tablero_actual, espacios=espacios, lineas=lineas, sesiones=sesiones, linea_enfocada=foco)
        )


class _SuscripcionFake:
    def __init__(self, fake: FakeTerminales) -> None:
        self._fake = fake
        self._cola: asyncio.Queue[Evento] = asyncio.Queue()
        fake._colas.add(self._cola)
        self._tarea: asyncio.Task | None = None
        if fake.poll is not None:
            self._tarea = asyncio.create_task(self._poll())
        self._cerrada = False

    async def _poll(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._fake.poll)  # type: ignore[arg-type]
                await self._cola.put(
                    Evento("tablero", self._fake.nombre, datos={"motivo": "poll", "via": "polling"})
                )
        except asyncio.CancelledError:
            raise

    def __aiter__(self) -> AsyncIterator[Evento]:
        return self

    async def __anext__(self) -> Evento:
        if self._cerrada:
            raise StopAsyncIteration
        return await self._cola.get()

    async def aclose(self) -> None:
        if self._cerrada:
            return
        self._cerrada = True
        self._fake._colas.discard(self._cola)
        if self._tarea is not None:
            self._tarea.cancel()
            try:
                await self._tarea
            except asyncio.CancelledError:
                pass
