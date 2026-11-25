"""Atajos de teclado que el usuario puede cambiar (se guardan en el servidor).

Combinación: `[mod+][alt+][shift+]tecla`, todo en minúsculas. `mod` es Ctrl en Windows y Linux, ⌘ en Mac.
Debe mantenerse igual a frontend/src/lib/teclas.ts.
"""
import re

from pydantic import BaseModel, field_validator

ORIGINALES: dict[str, str] = {
    "buscador": "mod+k",
    "dictar": "mod+shift+space",
    "minimizar-preguntas": "m",
    "crear-terminal": "mod+enter",
    "comentar": "mod+enter",
}
# Dos atajos chocan si tienen la misma combinación y alguno es global o comparten ámbito.
AMBITO: dict[str, str] = {
    "buscador": "global",
    "dictar": "global",
    "minimizar-preguntas": "preguntas",
    "crear-terminal": "terminal",
    "comentar": "cambios",
}
SIN_MODIFICADOR = {"minimizar-preguntas"}

_TECLA = r"(?:[a-z0-9]|enter|space|tab|f(?:[1-9]|1[0-2])|[\[\]/.,;'\\`=-])"
_COMBO = re.compile(rf"^(mod\+)?(alt\+)?(shift\+)?({_TECLA})$")


def _valida_forma(id_: str, combo: object) -> None:
    if not isinstance(combo, str) or len(combo) > 40:
        raise ValueError(f"combinación inválida para {id_}")
    m = _COMBO.match(combo)
    if not m:
        raise ValueError(f"combinación inválida para {id_}")
    mod, alt, shift, tecla = m.groups()
    if not (mod or alt or shift) and id_ in SIN_MODIFICADOR and (tecla in {"1", "2", "3", "4", "5", "6", "enter", "tab", "space"}):
        raise ValueError(f"{id_} no puede usar esa tecla")
    if not (mod or alt or shift) and id_ not in SIN_MODIFICADOR:
        raise ValueError(f"{id_} necesita un modificador")
    if shift and not (mod or alt) and len(tecla) == 1 and id_ not in SIN_MODIFICADOR:
        raise ValueError(f"{id_} necesita Ctrl o Alt además de Shift")


def _chocan(a: str, b: str) -> bool:
    return AMBITO[a] == "global" or AMBITO[b] == "global" or AMBITO[a] == AMBITO[b]


def validar_atajos(raw: object) -> dict[str, str]:
    """Devuelve el mapa a guardar (sin lo que es igual al original) o levanta ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("atajos debe ser un objeto")
    for id_, combo in raw.items():
        if id_ not in ORIGINALES:
            raise ValueError(f"atajo desconocido: {id_}")
        _valida_forma(id_, combo)
    efectivos = {id_: raw.get(id_, orig) for id_, orig in ORIGINALES.items()}
    ids = list(efectivos)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if efectivos[a] == efectivos[b] and _chocan(a, b):
                raise ValueError(f"{a} y {b} usan la misma combinación")
    return {id_: c for id_, c in raw.items() if c != ORIGINALES[id_]}


class AtajosBody(BaseModel):
    atajos: dict

    @field_validator("atajos")
    @classmethod
    def validar(cls, v: dict) -> dict[str, str]:
        return validar_atajos(v)
