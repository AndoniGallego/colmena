"""Port de `toOpciones` y `signature` de frontend/src/lib: los casos de opciones.casos.json valen para los dos."""
import json
import re
from typing import Optional

from .digest import _BLOQUE

MAX_OPCIONES = 6
MAX_LABEL = 80
MAX_DETALLE = 200
MAX_PREGUNTA = 300

# El mismo conjunto que String.prototype.trim de JS (Python strip() también come \x1c-\x1f).
_JS_WS = " \t\n\v\f\r             " \
         "    　﻿"


def _units(text: str) -> list:
    raw = text.encode("utf-16-le", "surrogatepass")
    return [int.from_bytes(raw[i:i + 2], "little") for i in range(0, len(raw), 2)]


def _from_units(units: list) -> str:
    return b"".join(u.to_bytes(2, "little") for u in units).decode("utf-16-le", "surrogatepass")


def _clip(value, limit: int) -> str:
    text = value.strip(_JS_WS) if isinstance(value, str) else ""
    units = _units(text)
    if len(units) <= limit:
        return text
    return _from_units(units[:limit - 1]).rstrip(_JS_WS) + "…"


def to_opciones(value) -> Optional[dict]:
    if not isinstance(value, dict) or not isinstance(value.get("opciones"), list):
        return None
    opciones = []
    for raw in value["opciones"]:
        if not isinstance(raw, dict):
            continue
        label = _clip(raw.get("label"), MAX_LABEL)
        if not label:
            continue
        opciones.append({"label": label, "detalle": _clip(raw.get("detalle"), MAX_DETALLE),
                         "recomendada": raw.get("recomendada") is True})
        if len(opciones) == MAX_OPCIONES:
            break
    return {"pregunta": _clip(value.get("pregunta"), MAX_PREGUNTA), "opciones": opciones} if opciones else None


def lenient_json(src: str):
    body = src.strip()
    try:
        return json.loads(body)
    except ValueError:
        pass
    repaired = re.sub(r",\s*([}\]])", r"\1", body.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'"))
    try:
        return json.loads(repaired)
    except ValueError:
        return None


def analizar(text: str) -> tuple:
    """(tarjetas ```opciones válidas en orden, si el mensaje termina con una de ellas); las inválidas no cuentan."""
    text = text or ""
    out = []
    termina = False
    pos = 0
    while True:
        m = _BLOQUE.search(text, pos)
        if not m:
            return out, termina and not text[pos:].strip()
        fence, kind = m.group(2), m.group(3).lower()
        close = re.compile(r"\n[ \t]*" + ("`" if fence[0] == "`" else "~") + "{%d,}[ \t]*(?=\n|$)" % len(fence))
        c = close.search(text, m.end() - 1)
        value = None
        if kind == "opciones":
            value = to_opciones(lenient_json(text[m.end():c.start() if c else len(text)]))
            if value:
                out.append(value)
        termina = value is not None
        pos = c.end() if c else len(text)


def preguntas_de(text: str) -> list:
    return analizar(text)[0]


def _hash(text: str) -> str:
    h = 5381
    for unit in _units(text):
        h = ((h << 5) + h + unit) & 0xFFFFFFFF
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        h, r = divmod(h, 36)
        out = digits[r] + out
        if not h:
            return out


def signature(ident: str, preguntas: list) -> str:
    joined = "\u0003".join(f"{q['pregunta']}\u0001" + "\u0002".join(o["label"] for o in q["opciones"])
                           for q in preguntas)
    return f"{ident}:{_hash(joined)}"
