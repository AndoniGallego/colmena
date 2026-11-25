from dataclasses import dataclass
from typing import Literal

EstadoSesion = Literal["idle", "working", "blocked", "done", "terminada", "perdida"]
Programa = Literal["claude", "shell", "otro"]

ESTADOS_HERDR = ("working", "blocked", "idle", "done")


@dataclass(frozen=True)
class Sesion:
    id: str
    linea_id: str
    espacio_id: str
    programa: Programa
    estado: EstadoSesion
    estado_fuente: Literal["herdr", "ganchos", "guardian"]
    claude_session_id: str | None
    cwd: str
    cwd_primer_plano: str | None
    titulo: str
    revision: int | None
    backend: Literal["herdr", "guardian"]
    agente: str | None = None
    es_agente: bool = False
    nombre_agente: str | None = None
    estado_crudo: str | None = None
    claude_session_tipo: str | None = None
    seq: int | None = None
    terminal_id: str | None = None
    titulo_crudo: str | None = None
    listo: bool | None = None
    # Solo guardián: pid del Claude lanzado (identidad del canal MCP) y modo interno (copiloto o guía).
    pid_claude: int | None = None
    modo: str | None = None


@dataclass(frozen=True)
class Linea:
    id: str
    espacio_id: str
    nombre: str
    sesiones: tuple[str, ...]
    declaradas: int | None = None


@dataclass(frozen=True)
class Espacio:
    id: str
    nombre: str
    lineas: tuple[str, ...]
    numero: int | None = None
    estado_crudo: str | None = None
    declaradas: int | None = None


@dataclass(frozen=True)
class Tablero:
    espacios: tuple[Espacio, ...]
    lineas: tuple[Linea, ...]
    sesiones: tuple[Sesion, ...]
    revision: int
    linea_enfocada: str | None = None
    conflictos: tuple[str, ...] = ()
    caidos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Lanzamiento:
    programa: Literal["claude", "shell"]
    resume: str | None = None


@dataclass(frozen=True)
class Creado:
    espacio_id: str | None
    linea_id: str | None
    sesion_id: str


@dataclass(frozen=True)
class TomaPrompt:
    tomado: bool
    estado: EstadoSesion
    via: Literal["herdr", "gancho", "pantalla"]


@dataclass(frozen=True)
class ProcesoPrimerPlano:
    pid: int | None
    nombre: str
    argv: tuple
    cwd: str | None


@dataclass(frozen=True)
class InfoProceso:
    pid: int | None
    comando: str | None
    cwd: str | None
    es_claude: bool
    procesos: tuple[ProcesoPrimerPlano, ...] = ()
    grupo: int | None = None
    shell_pid: int | None = None
