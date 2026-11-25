"""Pedidos de una sesión: paridad entre la marca y el MCP (CA9) y acciones nuevas (CA18)."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from orquestador.colmena_pestana import PREFIJO_PEDIDO, pedido_desde_comando_bash, pedido_desde_dict
from orquestador.pedidos_pestana import PedidosPestanaStore
from orquestador.pedidos_sesion import PedidosSesion

PANE, SID, NOMBRE = "w1:p1", "s-uno", "Uno"
VOLATILES = ("id", "ts", "vence")


class _Push:
    def __init__(self):
        self.enviados = []

    async def dispatch_pestana(self, pedido_id, titulo, cuerpo, session_id="", pane_id=""):
        self.enviados.append((titulo, cuerpo))
        return 1


def _board(tmp_path: Path) -> dict:
    return {"workspaces": [{"id": "w2", "label": "Logs", "tabs": [{"id": "w2:t1", "label": "tail", "terminales": [
        {"pane_id": "w2:p1", "terminal_id": "t-1", "titulo": "tail", "cwd": str(tmp_path), "proceso": "tail",
         "estado": "idle"}]}]}]}


def _armar(tmp_path: Path):
    store = PedidosPestanaStore()
    push = _Push()
    tareas = []

    def spawn(coro):
        tareas.append(coro)

    ps = PedidosSesion(store, lambda: _board(tmp_path), SimpleNamespace(plan_cwds=[str(tmp_path)]), push, spawn,
                       cierres=None)
    return ps, store, push, tareas


def _correr_tareas(tareas):
    async def todas():
        await asyncio.gather(*tareas)

    asyncio.run(todas())
    tareas.clear()


def _sin_volatiles(item: dict) -> dict:
    out = {k: v for k, v in item.items() if k not in VOLATILES and k != "via"}
    out["origen"] = {k: v for k, v in item["origen"].items() if k != "via"}
    return out


def _marca(data: dict) -> dict:
    import json
    return pedido_desde_comando_bash(f"echo '[colmena-pestana] {json.dumps(data)}'")


CASOS = [
    lambda d: {"carpeta": d, "mensaje": "hacé tal cosa", "nombre": "API"},
    lambda d: {"carpeta": d, "tarjeta": "Trabajo", "pestanas": [
        {"nombre": "API", "tipo": "claude", "mensaje": "brief"}, {"nombre": "Logs", "tipo": "terminal"}]},
    lambda d: {"accion": "cursor", "carpeta": d, "nombre": "Renombrar", "pedido": "renombrá x por y"},
    lambda d: {"accion": "cerrar", "terminal": "tail"},
]


@pytest.mark.parametrize("caso", range(len(CASOS)))
def test_marca_y_mcp_crean_el_mismo_item(tmp_path, caso):
    data = CASOS[caso](str(tmp_path))
    ps_m, store_m, _, tareas_m = _armar(tmp_path)
    ps_m.desde_marca(_marca(data), PANE, SID, NOMBRE)
    _correr_tareas(tareas_m)
    ps_c, store_c, _, tareas_c = _armar(tmp_path)
    payload = pedido_desde_dict(data)
    item, motivo = asyncio.run(ps_c.desde_mcp(payload, PANE, SID, NOMBRE))
    _correr_tareas(tareas_c)
    assert motivo is None
    [desde_marca] = store_m._items.values()
    assert item["via"] == "mcp" and item["origen"]["via"] == "mcp"
    assert _sin_volatiles(desde_marca) == _sin_volatiles(item)


def test_pedido_desde_dict_es_lo_que_parsea_la_marca(tmp_path):
    for caso in CASOS:
        data = caso(str(tmp_path))
        assert pedido_desde_dict(data) == _marca(data)


def test_mcp_devuelve_el_motivo_del_descarte(tmp_path):
    ps, store, _, _ = _armar(tmp_path)
    item, motivo = asyncio.run(ps.desde_mcp({"carpeta": "/no/existe", "mensaje": "x"}, PANE, SID, NOMBRE))
    assert item is None and motivo == "carpeta_no_permitida"
    item, motivo = asyncio.run(ps.desde_mcp({"accion": "cerrar", "terminal": "nada"}, PANE, SID, NOMBRE))
    assert item is None and motivo == "terminal_no_encontrada"


# --- acciones nuevas (CA18) ---

def test_mensaje_crea_pedido_pendiente_con_prefijo(tmp_path):
    ps, store, push, tareas = _armar(tmp_path)
    destino = {"pane_id": "w3:p1", "nombre": "Tres"}
    item, motivo = ps.mensaje(destino, "  revisá\nel MR  ", PANE, SID, NOMBRE, via="mcp")
    _correr_tareas(tareas)
    assert motivo is None
    assert item["estado"] == "pendiente" and item["accion"] == "mensaje"
    assert item["envio"] == {"pane_id": "w3:p1", "nombre": "Tres", "texto": PREFIJO_PEDIDO + "revisá el MR"}
    assert item["mensaje"] == "revisá el MR"
    assert push.enviados and "Tres" in push.enviados[0][1]


def test_mensaje_a_una_sesion_abierta_por_la_misma_igual_pide_aprobacion(tmp_path):
    ps, store, _, tareas = _armar(tmp_path)
    abierta, _ = store.crear(str(tmp_path), "brief", None, {"pane_id": PANE, "nombre": NOMBRE, "session_id": SID})
    store.marcar(abierta["id"], "abierto")
    item, _ = ps.mensaje({"pane_id": "w9:p1", "nombre": "Hija"}, "seguí", PANE, "s-otro-ciclo", NOMBRE, via="mcp")
    _correr_tareas(tareas)
    assert item["estado"] == "pendiente"


def test_mensaje_vacio_o_largo_no_crea(tmp_path):
    ps, store, _, _ = _armar(tmp_path)
    assert ps.mensaje({"pane_id": "w3:p1", "nombre": "T"}, "   ", PANE, SID, NOMBRE)[1] == "mensaje_invalido"
    assert ps.mensaje({"pane_id": "w3:p1", "nombre": "T"}, "x" * 3901, PANE, SID, NOMBRE)[1] == "mensaje_invalido"
    assert store._items == {}


def test_programada_valida_la_hora_y_crea_pedido(tmp_path):
    ps, store, _, tareas = _armar(tmp_path)
    assert ps.programada("hola", "25:99", {"pane_id": PANE, "nombre": NOMBRE}, PANE, SID, NOMBRE)[1] == \
        "cuando_invalido"
    item, motivo = ps.programada("acordate del deploy", "09:30", {"pane_id": PANE, "nombre": NOMBRE},
                                 PANE, SID, NOMBRE, via="mcp")
    _correr_tareas(tareas)
    assert motivo is None and item["accion"] == "programada"
    assert item["programada"] == {"cuando": "09:30", "pane_id": PANE, "nombre": NOMBRE}
    assert item["mensaje"] == "acordate del deploy"


def test_tarea_valida_ticket_y_carpeta(tmp_path):
    ps, store, _, tareas = _armar(tmp_path)
    assert ps.tarea("no es ticket", str(tmp_path), "", PANE, SID, NOMBRE)[1] == "ticket_invalido"
    assert ps.tarea("SITE-12", "/no/existe", "", PANE, SID, NOMBRE)[1] == "carpeta_no_permitida"
    item, motivo = ps.tarea("SITE-12", str(tmp_path), "mirá el CA2", PANE, SID, NOMBRE, via="mcp")
    _correr_tareas(tareas)
    assert motivo is None and item["accion"] == "tarea"
    assert item["tarea"] == {"ticket": "SITE-12"} and item["carpeta"] == str(tmp_path.resolve())
    assert item["mensaje"] == "mirá el CA2"


def test_tarea_en_el_repo_de_colmena_se_descarta():
    from orquestador import config

    ps, store, _, _ = _armar(Path(config.REPO_ROOT))
    assert ps.tarea("SITE-1", str(config.REPO_ROOT), "", PANE, SID, NOMBRE)[1] == "carpeta_colmena"


def test_carpeta_no_permitida_en_pestana_tambien_se_descarta(tmp_path):
    ps, store, _, _ = _armar(tmp_path)
    ps.abrir({"carpeta": str(tmp_path), "pestanas": [{"nombre": "a", "tipo": "terminal", "carpeta": "/no/existe"}]},
             PANE, SID, NOMBRE)
    assert [d["motivo"] for d in store.descartes_de(SID)] == ["carpeta_no_permitida"]


def test_marca_carpeta_no_permitida_se_descarta_con_origen(tmp_path):
    ps, store, _, _ = _armar(tmp_path)
    visto = []
    store.on_descarte(lambda origen, motivo: visto.append((origen["session_id"], motivo)))
    ps.abrir({"carpeta": "/no/existe"}, PANE, SID, NOMBRE)
    assert visto == [(SID, "carpeta_no_permitida")]
