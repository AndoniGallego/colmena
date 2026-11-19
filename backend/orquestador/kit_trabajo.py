"""Integraciones opcionales con un kit de trabajo externo.

Los nombres propios de ese kit (prefijo de variables, script de flujo git, comando de tickets...) no viven en el
código: salen de la tabla `[kit_trabajo]` del config.toml de la carpeta de datos. Sin ella rigen los genéricos.
"""
import os
import tomllib
from pathlib import Path

GENERICOS = {
    "prefijo_vars": "COLMENA",
    "carpeta_titulos": ".kit-session-title",
    "script_flujo_git": "git-flow.sh",
    "comando_flujo": "/flujo-tickets",
    "agente_tickets": "analista de tickets",
    "apoyo_entornos": [],
    "units": [],
}

_cache: dict = {}


def _directorio() -> Path:
    env = os.environ.get("ORQ_DATA_DIR")
    if env:
        return Path(env).expanduser()
    from .config import REPO_ROOT
    return REPO_ROOT / "data"


def cargar() -> dict:
    path = _directorio() / "config.toml"
    try:
        marca = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    if _cache.get("marca") != marca:
        try:
            tabla = tomllib.loads(path.read_text(encoding="utf-8")).get("kit_trabajo")
        except (OSError, ValueError):
            tabla = None
        _cache["marca"] = marca
        _cache["tabla"] = tabla if isinstance(tabla, dict) else {}
    return _cache["tabla"]


def valor(clave: str):
    base = GENERICOS[clave]
    dado = cargar().get(clave)
    if isinstance(base, list):
        return [str(x) for x in dado] if isinstance(dado, list) else list(base)
    return dado if isinstance(dado, str) and dado.strip() else base


def variable(nombre: str, default=None):
    return os.environ.get(f"{valor('prefijo_vars')}_{nombre}", default)
