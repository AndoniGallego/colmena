"""Normalización de texto y suficiencia de citas literales del usuario."""
import re
import unicodedata

_PALABRA = re.compile(r"[a-z0-9]+")


def normalizar(text: str) -> str:
    """Minúsculas, sin tildes y con los espacios colapsados."""
    plano = unicodedata.normalize("NFKD", text or "")
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return " ".join(plano.casefold().split())


def palabras(text: str) -> list:
    return _PALABRA.findall(normalizar(text))


def cita_suficiente(cita: str) -> bool:
    texto = normalizar(cita)
    return sum(c.isalnum() for c in texto) >= 12 and len(_PALABRA.findall(texto)) >= 3
