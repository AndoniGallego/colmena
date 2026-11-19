from orquestador.citas import cita_suficiente, normalizar


def test_normalizar_tildes_mayusculas_espacios():
    assert normalizar("  DecíLE   á   PS9  ") == "decile a ps9"


def test_cita_suficiente_corta():
    assert cita_suficiente("ok") is False


def test_cita_suficiente_larga():
    assert cita_suficiente("que siga con los tests") is True
