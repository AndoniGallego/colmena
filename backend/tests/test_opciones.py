import json
from pathlib import Path

import pytest

from orquestador.opciones import analizar, signature, to_opciones

CASOS = json.loads((Path(__file__).resolve().parents[2] / "frontend/src/lib/opciones.casos.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("caso", CASOS["to_opciones"], ids=lambda c: c["nombre"])
def test_to_opciones_igual_que_el_front(caso):
    assert to_opciones(caso["entrada"]) == caso["salida"]


@pytest.mark.parametrize("caso", CASOS["texto"], ids=lambda c: c["nombre"])
def test_tarjetas_de_un_mensaje(caso):
    assert analizar(caso["texto"]) == (caso["preguntas"], caso["termina"])


@pytest.mark.parametrize("caso", CASOS["firma"], ids=lambda c: c["id"])
def test_firma_igual_que_el_stepper(caso):
    assert signature(caso["id"], caso["preguntas"]) == caso["sig"]
