import re
import pytest
from orquestador.enchufe import ids
from orquestador import avisos, push, traspaso

VIEJO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:.-]*$")
VIEJO_PANE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:.-]{0,63}$")
MUESTRA = ["w1", "w1:p1", "wC:tF", "w5:pH", "g3", "g3:p2", "a.b-c_d", "-x", "", "w1 p1", "w1:p1\n", "x" * 64, "x" * 65]

@pytest.mark.parametrize("v", ["g3", "g3:t2", "g3:p2", "g10:p0"])
def test_guardian_acepta(v):
    assert ids.es_guardian(v)

@pytest.mark.parametrize("v", ["g3\n", "g3:p2x", "", " g3", "g3 ", "gx", "g3:x1", "g", "wC:p1", "G3", None, 3])
def test_guardian_casos_limite(v):
    assert not ids.es_guardian(v)

@pytest.mark.parametrize("v", MUESTRA)
def test_id_re_igual_que_antes(v):
    assert bool(ids.ID_RE.match(v)) == bool(VIEJO_ID.match(v))
    assert bool(ids.PANE_RE.match(v)) == bool(VIEJO_PANE.match(v))

def test_un_solo_validador():
    assert traspaso.ID_RE is ids.ID_RE
    assert avisos.PANE_RE is ids.PANE_RE and push.PANE_RE is ids.PANE_RE

@pytest.mark.parametrize("v,tipo", [("w5", "espacio"), ("w5:tF", "linea"), ("w5:pH", "sesion"),
                                    ("g3", "espacio"), ("g3:t2", "linea"), ("g3:p2", "sesion"), ("w5:xF", None), ("w1:p1\n", None)])
def test_tipo_de_id(v, tipo):
    assert ids.tipo_de_id(v) == tipo


def test_teclas_igual_al_literal():
    from typing import get_args
    from orquestador.enchufe.base import TECLAS, Tecla
    assert set(get_args(Tecla)) == TECLAS


@pytest.mark.parametrize("regex,valor", [(ids.PANE_RE, "w1:p1\n"), (ids.ID_RE, "w1\n"), (ids.GUARDIAN_RE, "g1:p1\n"), (ids.PANE_RE, 7)])
def test_salto_final_o_tipo_no_valida(regex, valor):
    assert ids.valido(regex, valor) is False


def test_validos():
    assert ids.valido(ids.PANE_RE, "wC:p1") and ids.valido(ids.GUARDIAN_RE, "g3:t2")
