"""Validación de lo que manda la PC en "Mostrame": la captura y la lista de controles."""
from __future__ import annotations

import base64
import binascii
import struct
from dataclasses import dataclass

from .nudo import CONTROLES_MAX, NOMBRE_CONTROL_MAX, TIPOS, _entero, _texto_pc

IMAGEN_MAX = 5 * 1024 * 1024
CUERPO_MAX = 7 * 1024 * 1024
LADO_MAX = 1568
PREGUNTA_MOSTRAR_MAX = 300

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_EXT = {"png": "png", "jpeg": "jpg", "jpg": "jpg"}


@dataclass(frozen=True)
class Imagen:
    datos: bytes
    tipo: str
    ancho: int
    alto: int

    @property
    def extension(self) -> str:
        return _EXT[self.tipo]


def decodificar_imagen(raw: object) -> Imagen:
    if not isinstance(raw, dict) or set(raw) != {"tipo", "ancho", "alto", "b64"}:
        raise ValueError("imagen inválida")
    tipo, b64 = raw["tipo"], raw["b64"]
    if not isinstance(tipo, str) or tipo not in _EXT or not isinstance(b64, str):
        raise ValueError("tipo de imagen inválido")
    if len(b64) > IMAGEN_MAX * 4 // 3 + 8:
        raise ValueError("la imagen es demasiado grande")
    try:
        datos = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("imagen mal codificada") from None
    if len(datos) > IMAGEN_MAX:
        raise ValueError("la imagen es demasiado grande")
    ancho, alto = _entero(raw["ancho"], 1, "ancho"), _entero(raw["alto"], 1, "alto")
    if ancho > LADO_MAX or alto > LADO_MAX:
        raise ValueError(f"la imagen no puede pasar de {LADO_MAX} píxeles de lado")
    es_png = tipo == "png"
    if not datos.startswith(_PNG if es_png else _JPEG):
        raise ValueError("los bytes no coinciden con el tipo de imagen")
    if es_png:
        if len(datos) < 24 or struct.unpack(">II", datos[16:24]) != (ancho, alto):
            raise ValueError("el tamaño no coincide con el de la imagen")
    return Imagen(datos, "png" if es_png else "jpeg", ancho, alto)


def validar_foto(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("foto inválida")
    foto = _entero(raw.get("foto"), 0, "foto")
    ventana = raw.get("ventana")
    if not isinstance(ventana, dict) or set(ventana) != {"titulo", "proceso"}:
        raise ValueError("ventana inválida")
    controles = raw.get("controles")
    if not isinstance(controles, list) or len(controles) > CONTROLES_MAX:
        raise ValueError("lista de controles inválida")
    lista = []
    for c in controles:
        if not isinstance(c, dict) or set(c) != {"n", "tipo", "nombre"}:
            raise ValueError("control inválido")
        if c["tipo"] not in TIPOS:
            raise ValueError("tipo de control desconocido")
        lista.append({"n": _entero(c["n"], 1, "n"), "tipo": c["tipo"],
                      "nombre": _texto_pc(c["nombre"], NOMBRE_CONTROL_MAX, vacio=True)})
    return {"foto": foto,
            "ventana": {"titulo": _texto_pc(ventana["titulo"], 300, True),
                        "proceso": _texto_pc(ventana["proceso"], 300, True)},
            "controles": lista}
