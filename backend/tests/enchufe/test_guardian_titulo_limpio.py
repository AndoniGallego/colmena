import pytest

from orquestador.enchufe.guardian import _tablero_de_res


def _res(titulo: str) -> dict:
    return {
        "espacios": [{"id": "g1", "nombre": "G", "numero": 1, "lineas": ["g1:t1"]}],
        "lineas": [{"id": "g1:t1", "espacio_id": "g1", "nombre": "L", "sesiones": ["g1:p2"]}],
        "sesiones": [
            {"id": "g1:p2", "linea_id": "g1:t1", "espacio_id": "g1", "programa": "claude",
             "estado": "idle", "cwd": "/tmp", "titulo": titulo}
        ],
    }


@pytest.mark.parametrize(
    "crudo, limpio",
    [
        ("✳ Arreglar el login", "Arreglar el login"),
        ("⠂ Arreglar el login", "Arreglar el login"),
        ("⠐  Arreglar el login", "Arreglar el login"),
        ("✻ Revisar MR", "Revisar MR"),
        ("◐ Orquestador de sesiones", "Orquestador de sesiones"),
        ("◓ Orquestador de sesiones", "Orquestador de sesiones"),
        ("◑ Orquestador", "Orquestador"),
        ("◒ Orquestador", "Orquestador"),
        ("Arreglar el login", "Arreglar el login"),
        ("✳", ""),
        ("Login ✳ nuevo", "Login ✳ nuevo"),
    ],
)
def test_titulo_sin_el_simbolo_de_estado_de_claude(crudo: str, limpio: str) -> None:
    s = _tablero_de_res(_res(crudo), None).sesiones[0]
    assert s.titulo == limpio
    assert s.titulo_crudo == crudo
