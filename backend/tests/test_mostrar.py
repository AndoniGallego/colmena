import base64
import struct
import zlib

import pytest

from orquestador import mostrar as m


def _png(ancho=3, alto=2):
    def trozo(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d))
    crudo = b"".join(b"\x00" + b"\x00\x00\x00" * ancho for _ in range(alto))
    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(crudo)) + trozo(b"IEND", b""))


def _raw(datos, tipo="png", ancho=3, alto=2):
    return {"tipo": tipo, "ancho": ancho, "alto": alto, "b64": base64.b64encode(datos).decode()}


def test_png_valido():
    img = m.decodificar_imagen(_raw(_png()))
    assert (img.tipo, img.ancho, img.alto, img.extension) == ("png", 3, 2, "png")
    assert img.datos == _png()


def test_jpeg_por_bytes_magicos():
    img = m.decodificar_imagen(_raw(b"\xff\xd8\xff\xe0" + b"x" * 20, tipo="jpeg", ancho=10, alto=10))
    assert img.extension == "jpg"


def test_tipo_no_coincide_con_bytes():
    with pytest.raises(ValueError):
        m.decodificar_imagen(_raw(_png(), tipo="jpeg"))


def test_b64_invalido():
    r = _raw(_png())
    r["b64"] = "no es base64!!"
    with pytest.raises(ValueError):
        m.decodificar_imagen(r)


def test_pasa_de_5mb():
    datos = b"\xff\xd8\xff" + b"0" * m.IMAGEN_MAX
    with pytest.raises(ValueError):
        m.decodificar_imagen(_raw(datos, tipo="jpeg", ancho=10, alto=10))


def test_ihdr_no_coincide():
    with pytest.raises(ValueError):
        m.decodificar_imagen(_raw(_png(3, 2), ancho=4, alto=2))


def test_lado_mayor_a_1568():
    with pytest.raises(ValueError):
        m.decodificar_imagen(_raw(_png(1569, 1), ancho=1569, alto=1))


def test_claves_de_mas():
    r = _raw(_png())
    r["extra"] = 1
    with pytest.raises(ValueError):
        m.decodificar_imagen(r)


def _foto(controles):
    return {"foto": 1, "ventana": {"titulo": "T", "proceso": "p"}, "controles": controles}


def test_foto_con_cero_controles_vale():
    assert m.validar_foto(_foto([]))["controles"] == []


def test_foto_con_151_controles_o_tipo_desconocido_falla():
    uno = {"n": 1, "tipo": "boton", "nombre": "a"}
    with pytest.raises(ValueError):
        m.validar_foto(_foto([uno] * 151))
    with pytest.raises(ValueError):
        m.validar_foto(_foto([{"n": 1, "tipo": "raro", "nombre": "a"}]))
