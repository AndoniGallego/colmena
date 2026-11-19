import json

import pytest

from orquestador.guardian import protocolo as p


def test_codificar_ok():
    assert p.codificar({"id": 1, "op": "hola"}) == b'{"id":1,"op":"hola"}\n'


def test_codificar_demasiado_grande():
    obj = {"x": "a" * p.MAX_LINEA}
    with pytest.raises(p.ErrorProtocolo) as exc:
        p.codificar(obj)
    assert exc.value.codigo == p.INVALIDO


def test_leer_pedido_ok():
    linea = b'{"id":0,"op":"tablero","args":{}}\n'
    assert p.leer_pedido(linea) == (0, "tablero", {})


def test_leer_pedido_sin_newline():
    with pytest.raises(p.ErrorProtocolo):
        p.leer_pedido(b'{}')


def test_leer_pedido_op_desconocida():
    with pytest.raises(p.ErrorProtocolo) as exc:
        p.leer_pedido(b'{"id":3,"op":"foo"}\n')
    assert exc.value.id == 3


def test_leer_pedido_id_invalido():
    with pytest.raises(p.ErrorProtocolo) as exc:
        p.leer_pedido(b'{"id":true,"op":"hola"}\n')
    assert exc.value.id is None


def test_respuestas():
    assert p.respuesta_ok(1, {"a": 1})["ok"] is True
    err = p.respuesta_error(2, p.NO_EXISTE, "nada")
    assert err["ok"] is False and err["error"]["codigo"] == p.NO_EXISTE


def test_leer_mensaje():
    assert p.leer_mensaje(b'{"ok":true}\n') == {"ok": True}
