import re
from typing import Literal

GUARDIAN_RE = re.compile(r"g\d+(:[pt]\d+)?")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:.-]*$")
PANE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:.-]{0,63}$")

_TipoId = Literal["espacio", "linea", "sesion"]


def valido(regex: re.Pattern, valor: object) -> bool:
    return isinstance(valor, str) and regex.fullmatch(valor) is not None


def _tipo_suffix(valor: str) -> _TipoId | None:
    if ":" not in valor:
        return "espacio"
    sufijo = valor.split(":", 1)[1]
    if sufijo.startswith("t"):
        return "linea"
    if sufijo.startswith("p"):
        return "sesion"
    return None


def es_guardian(valor: object) -> bool:
    if not isinstance(valor, str):
        return False
    return GUARDIAN_RE.fullmatch(valor) is not None


def tipo_de_id(valor: str) -> _TipoId | None:
    if es_guardian(valor):
        return _tipo_suffix(valor)
    if not ID_RE.fullmatch(valor):
        return None
    return _tipo_suffix(valor)
