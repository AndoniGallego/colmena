"""Lectura validada de estado.fuente y permisos en config."""

from __future__ import annotations

from orquestador.config import Config

FUENTES = frozenset({"ganchos", "ganchos_con_respaldo", "herdr"})


def fuente_estado(cfg: Config) -> str:
    estado = cfg.estado if isinstance(cfg.estado, dict) else {}
    valor = estado.get("fuente")
    if valor in FUENTES:
        return valor
    return "herdr"


def permisos_desde_app(cfg: Config) -> bool:
    permisos = cfg.permisos if isinstance(cfg.permisos, dict) else {}
    return permisos.get("desde_app") is True


def permisos_espera(cfg: Config) -> int:
    permisos = cfg.permisos if isinstance(cfg.permisos, dict) else {}
    valor = permisos.get("espera", 120)
    if not isinstance(valor, int) or isinstance(valor, bool):
        return 120
    return max(10, min(280, valor))
