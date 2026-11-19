"""Piezas opcionales: cada subpaquete de este paquete que tenga `montar(ctx)` se monta al crear la app.

Una pieza que falta no cambia nada; una que falla al importar o al montarse se loguea y Colmena arranca igual.
El núcleo nunca importa una pieza por su nombre.
"""
import importlib
import logging
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Optional

from fastapi import APIRouter

log = logging.getLogger("orquestador.piezas")


@dataclass
class ContextoPieza:
    api: APIRouter
    cfg: Any
    data_directory: Path
    push: Any
    spawn: Callable
    opciones: dict = field(default_factory=dict)
    inicio: list = field(default_factory=list)
    cierre: list = field(default_factory=list)

    def al_iniciar(self, fn: Callable) -> None:
        self.inicio.append(fn)

    def al_cerrar(self, fn: Callable) -> None:
        self.cierre.append(fn)


def nombre(modulo: ModuleType) -> str:
    return modulo.__name__.rsplit(".", 1)[-1]


def descubrir(paquete: str = __name__) -> list:
    """Subpaquetes con `montar`, en orden alfabético; los que no importan quedan afuera con un aviso en el log."""
    try:
        raiz = importlib.import_module(paquete)
    except Exception:
        log.exception("no pude importar el paquete de piezas %s", paquete)
        return []
    encontrados = []
    for info in sorted(pkgutil.iter_modules(getattr(raiz, "__path__", [])), key=lambda i: i.name):
        if not info.ispkg or info.name.startswith("_"):
            continue
        try:
            modulo = importlib.import_module(f"{paquete}.{info.name}")
        except Exception:
            log.exception("la pieza %s no se pudo importar; sigo sin ella", info.name)
            continue
        if callable(getattr(modulo, "montar", None)):
            encontrados.append(modulo)
    return encontrados


def montar_todas(modulos: list, crear_ctx: Callable[[str], ContextoPieza],
                 nombres: Optional[list] = None) -> list:
    """Monta cada pieza (o solo las de `nombres`); devuelve los nombres que quedaron montados."""
    montadas = []
    for modulo in modulos:
        clave = nombre(modulo)
        if nombres is not None and clave not in nombres:
            continue
        ctx = crear_ctx(clave)
        api, inicio, cierre = ctx.api, ctx.inicio, ctx.cierre
        instantanea = ctx.push.instantanea_piezas()
        ctx.api, ctx.inicio, ctx.cierre = APIRouter(), [], []
        try:
            modulo.montar(ctx)
        except Exception:
            log.exception("la pieza %s falló al montarse; sigo sin ella", clave)
            ctx.push.restaurar_piezas(instantanea)
            continue
        finally:
            propio, ctx.api = ctx.api, api
        api.include_router(propio)
        inicio.extend(ctx.inicio)
        cierre.extend(ctx.cierre)
        ctx.inicio, ctx.cierre = inicio, cierre
        montadas.append(clave)
    return montadas
