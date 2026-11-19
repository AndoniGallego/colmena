import pytest
from orquestador.config import Config
from orquestador.ganchos import ajustes as a


def test_defaults_seguros():
    c = Config()
    assert a.fuente_estado(c) == "herdr" and a.permisos_desde_app(c) is False and a.permisos_espera(c) == 120


@pytest.mark.parametrize("valor,esperado", [("ganchos", "ganchos"), ("ganchos_con_respaldo", "ganchos_con_respaldo"),
                                            ("GANCHOS", "herdr"), (3, "herdr"), (None, "herdr")])
def test_fuente(valor, esperado):
    assert a.fuente_estado(Config(estado={"fuente": valor})) == esperado


@pytest.mark.parametrize("valor,esperado", [(True, True), ("true", False), (1, False)])
def test_desde_app_solo_true(valor, esperado):
    assert a.permisos_desde_app(Config(permisos={"desde_app": valor})) is esperado


@pytest.mark.parametrize(
    "valor,esperado",
    [
        (5, 10),
        (500, 280),
        ("x", 120),
        (150, 150),
        (True, 120),
        (False, 120),
    ],
)
def test_espera_acotada(valor, esperado):
    assert a.permisos_espera(Config(permisos={"espera": valor})) == esperado


@pytest.mark.parametrize(
    "estado,esperado",
    [("x", "herdr"), (3, "herdr")],
)
def test_fuente_estado_no_dict(estado, esperado):
    c = Config()
    c.estado = estado  # type: ignore[assignment]
    assert a.fuente_estado(c) == esperado


def test_permisos_desde_app_no_dict():
    c = Config()
    c.permisos = 3  # type: ignore[assignment]
    assert a.permisos_desde_app(c) is False


def test_permisos_espera_no_dict():
    c = Config()
    c.permisos = 3  # type: ignore[assignment]
    assert a.permisos_espera(c) == 120
