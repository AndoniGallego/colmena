from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from .modelo import (
    Creado,
    EstadoSesion,
    InfoProceso,
    Lanzamiento,
    Tablero,
    TomaPrompt,
)

Tecla = Literal[
    "esc",
    "enter",
    "arriba",
    "derecha",
    "ctrl-c",
    "ctrl-e",
    "ctrl-u",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
]
TECLAS: frozenset[str] = frozenset(
    {
        "esc",
        "enter",
        "arriba",
        "derecha",
        "ctrl-c",
        "ctrl-e",
        "ctrl-u",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
    }
)

Fuente = Literal["visible", "reciente", "deteccion"]
Formato = Literal["texto", "ansi"]

_CONFIRMAR_PROMPT = frozenset({"working", "blocked", "done"})
_LANZAMIENTO_SHELL = Lanzamiento("shell")


@dataclass(frozen=True)
class Evento:
    tipo: Literal["tablero", "estado", "proceso", "termino", "titulo", "salida", "caido", "volvio"]
    backend: str
    sesion_id: str | None = None
    estado: EstadoSesion | None = None
    datos: Mapping[str, Any] = field(default_factory=dict)


class TerminalesError(RuntimeError):
    pass


class NoExiste(TerminalesError):
    pass


class NoDisponible(TerminalesError):
    pass


class NoTomado(TerminalesError):
    pass


class Tiempo(TerminalesError):
    def __init__(self, *args, listo_conocido: bool = False):
        super().__init__(*args)
        # True si el guardián publica `listo` y venció igual: hay otra cosa en pantalla.
        self.listo_conocido = listo_conocido


class GrupoRequerido(TerminalesError):
    pass


class Ilegible(TerminalesError):
    pass


class Terminales(Protocol):
    nombre: str
    capacidades: frozenset[str]

    async def tablero(self) -> Tablero: ...

    async def proceso(self, sesion_id: str) -> InfoProceso: ...

    async def leer(
        self,
        sesion_id: str,
        *,
        fuente: Fuente = "visible",
        formato: Formato = "texto",
        lineas: int | None = None,
    ) -> str: ...

    async def crear_espacio(self, nombre: str, cwd: str) -> Creado: ...

    async def crear_linea(
        self,
        espacio_id: str,
        nombre: str,
        cwd: str,
        programa: Lanzamiento = _LANZAMIENTO_SHELL,
    ) -> Creado: ...

    async def arrancar_claude(
        self, sesion_id: str, nombre: str, resume: str | None = None, *, modo: str | None = None
    ) -> None: ...

    async def renombrar(self, objetivo_id: str, nombre: str) -> None: ...

    async def cerrar(self, objetivo_id: str) -> None: ...

    async def enfocar(self, objetivo_id: str) -> None: ...

    async def mandar_prompt(
        self,
        sesion_id: str,
        texto: str,
        *,
        confirmar: frozenset[EstadoSesion] = _CONFIRMAR_PROMPT,
        timeout: float = 30.0,
    ) -> TomaPrompt: ...

    async def interrumpir(self, sesion_id: str) -> None: ...

    async def esperar(
        self, sesion_id: str, hasta: frozenset[EstadoSesion], timeout: float
    ) -> EstadoSesion: ...

    async def esperar_listo(self, sesion_id: str, timeout: float) -> str: ...

    async def teclas(self, sesion_id: str, teclas: Sequence[Tecla]) -> None: ...

    async def escribir(self, sesion_id: str, texto: str) -> None: ...

    async def ejecutar(self, sesion_id: str, comando: str) -> None: ...

    def suscribir(self) -> AsyncIterator[Evento]: ...
