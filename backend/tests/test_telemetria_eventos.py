import json

from conftest import SID
from test_pedidos_pestana import _json_cmd, _msg_bash, apagada_app, enchufe, sender, wall  # noqa: F401

import pytest

from orquestador.comando_sesion import CARPETA_DISTINTA, NO_PREPARADO, TRABAJANDO, YA_CORRIDO
from orquestador.telemetria_eventos import campos_pedido, codigo_traspaso


def lineas(d):
    return [json.loads(l) for f in sorted(d.glob("*.jsonl")) for l in f.read_text().splitlines()]


def test_campos_pedido_abierto_mcp():
    item = {"id": "p", "ts": 100, "carpeta": "/home/x/Proyectos/orquestador", "mensaje": "CANARIO",
            "origen": {"via": "mcp"}, "accion": "mensaje", "leyo_otra_sesion": {"nombre": "a", "ts": 1}}
    assert campos_pedido(item, item["origen"], "abierto", None, 142.9) == {
        "tipo": "mensaje", "origen": "mcp", "creado": True, "estado": "abierto", "motivo": None,
        "segundos": 42, "leyo_otra_sesion": True, "proyecto": "orquestador"}


def test_campos_pedido_tarjeta_y_sin_item():
    assert campos_pedido({"ts": 0, "carpeta": "/a/b", "pestanas": [{}], "origen": {}}, {}, "rechazado", "x y", 5)["tipo"] == "tarjeta"
    c = campos_pedido(None, {"via": None}, "descartado", "cooldown", 5)
    assert c == {"tipo": None, "origen": "marca", "creado": False, "estado": "descartado", "motivo": "cooldown",
                 "segundos": None, "leyo_otra_sesion": False, "proyecto": None}


def test_tipo_pestana_por_defecto():
    assert campos_pedido({"ts": 0, "carpeta": "/a/b", "origen": {}}, {}, "vencido", None, 5)["tipo"] == "pestana"


def test_motivo_raro_es_otro():
    assert campos_pedido(None, {}, "descartado", "Carpeta Rara!", 0)["motivo"] == "otro"


def test_abierto_no_lleva_motivo():
    item = {"ts": 0, "carpeta": "/a/b", "origen": {}}
    assert campos_pedido(item, {}, "abierto", "aviso_tardio", 5)["motivo"] is None


def test_rechazar_pedido_escribe_una_linea(apagada_app, tmp_path):  # noqa: F811
    c, app, _, _, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="CANARIO")), "w1:p1")
    pid = c.get("/api/pedidos-pestana").json()[0]["id"]
    assert c.post(f"/api/pedidos-pestana/{pid}/rechazar").status_code == 200
    (l,) = [x for x in lineas(tmp_path / "telemetria") if x["ev"] == "pedido"]
    assert l["estado"] == "rechazado" and l["creado"] is True and l["origen"] == "marca"
    crudo = json.dumps(l)
    assert "mensaje" not in l and "CANARIO" not in crudo and SID not in crudo and "w1:p1" not in crudo


def test_cortar_al_apagar_escribe_cortado(apagada_app, tmp_path):  # noqa: F811
    c, app, _, _, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(carpeta="/tmp", mensaje="x")), "w1:p1")
    app.state.pedidos_pestana.cortar()
    (l,) = [x for x in lineas(tmp_path / "telemetria") if x["ev"] == "pedido"]
    assert l["estado"] == "cortado"


@pytest.mark.parametrize("detail,codigo", [
    (YA_CORRIDO, "ya_corrido"), (TRABAJANDO, "trabajando"), (NO_PREPARADO, "no_preparado"),
    (CARPETA_DISTINTA, "carpeta_distinta"), ("Esa sesión ya no está abierta", "sesion_cerrada"),
    ("Esa sesión no admite comandos desde acá", "protegida"),
    ("Las terminales no responden: x", "terminales_caidas"),
    ("Las terminales no respondieron: x", "terminales_caidas"),
    ("escritura apagada", "escritura_apagada"), ("demasiadas acciones seguidas", "limite"),
    ("No encontré la conversación de esa sesión", "sin_conversacion"),
    ("No encontré ese pedido en la conversación", "sin_conversacion"),
    ("Ese pedido quedó viejo: la conversación siguió", "sin_conversacion"),
    ("El comando cambió: recargá la conversación", "comando_cambio"),
    ("La sesión espera una aprobación tuya en la terminal", "esperando_aprobacion"),
    ("La sesión no está lista para recibir un comando", "no_lista"),
    ("La sesión cambió de lugar: probá de nuevo", "cambio_lugar"),
    ("algo nuevo", "otro")])
def test_codigo_traspaso(detail, codigo):
    assert codigo_traspaso(detail) == codigo
