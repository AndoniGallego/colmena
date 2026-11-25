from __future__ import annotations

import asyncio
import logging

import pytest

from orquestador.avisos_origen import ORIGEN, TEXTOS, VENCE_S, AvisosOrigen
from orquestador.enchufe import NoTomado
from orquestador.mensaje import ORIGENES_PUBLICOS, MensajeBody
from orquestador.traspaso import TraspasoError

SID = "11111111-2222-3333-4444-555555555555"
ORIGEN_SESION = {"pane_id": "w1:p1", "nombre": "Uno", "session_id": SID}


def _board(status: str, pane: str = "w1:p1", sid: str = SID, **extra) -> dict:
    agente = {"pane_id": pane, "session_id": sid, "status": status, **extra}
    return {"workspaces": [{"tabs": [{"agents": [agente]}]}]}


class Reloj:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class Armado:
    def __init__(self, status: str = "working", error: Exception | None = None):
        self.board = _board(status)
        self.enviados: list[MensajeBody] = []
        self.error = error
        self.tareas: list = []
        self.reloj = Reloj()
        self.avisos = AvisosOrigen(self.mandar, lambda: self.board, self.tareas.append, reloj=self.reloj)

    async def mandar(self, body: MensajeBody) -> dict:
        if self.error:
            raise self.error
        self.enviados.append(body)
        return {"ok": True}

    def correr(self) -> None:
        tareas, self.tareas[:] = list(self.tareas), []

        async def todas():
            await asyncio.gather(*tareas)

        asyncio.run(todas())

    def tablero(self, status: str, **extra) -> None:
        prev, self.board = self.board, _board(status, **extra)
        self.avisos.al_tablero(prev, self.board)


def test_textos_fijos_por_motivo():
    assert TEXTOS == {
        "fila_llena": "Colmena: tu pedido de pestaña no se abrió porque ya tenías 3 pendientes. "
                      "Esperá a que Ando los responda.",
        "cooldown": "Colmena: tu pedido de pestaña no se abrió porque llegó muy seguido del anterior. "
                    "Probá de nuevo en un rato.",
        "tope": "Colmena: tu pedido de pestaña no se abrió porque hay demasiados pedidos pendientes.",
        "vencido": "Colmena: tu pedido de pestaña venció sin respuesta de Ando y no se abrió.",
        "terminal_no_encontrada": "Colmena: tu pedido para cerrar una terminal no le llegó a Ando porque no hay "
                                  "una sola terminal común con ese id o nombre. Usá el id del panel (por ejemplo "
                                  "w2:p1); para una sesión de Claude usá \"sesion\".",
        "cierre_no_encontrado": "Colmena: tu pedido para cerrar no le llegó a Ando porque no encontré nada con "
                                "ese id o nombre.",
        "cierre_ambiguo": "Colmena: tu pedido para cerrar no le llegó a Ando porque hay más de una coincidencia "
                          "con ese nombre. Usá el id (por ejemplo w2:p1, w2:t1 o w2).",
        "cierre_protegido": "Colmena: no se puede cerrar Colmena ni un espacio protegido; el pedido no le llegó "
                            "a Ando.",
        "sesion_compartida": "Colmena: esa sesión comparte la pestaña con otras terminales, así que no la cierro "
                             "sola. Si hace falta, pedí cerrar la pestaña.",
        "cierre_no_posible": "Colmena: eso no se puede cerrar desde un pedido (por ejemplo, es el único espacio "
                             "abierto). Ando lo puede cerrar desde el tablero.",
        "cierre_cambio": "Colmena: no cerré lo que pediste porque cambió desde que lo pediste.",
        "cierre_no_hecho": "Colmena: no se cerró lo que pediste (falló o no terminó de guardar a tiempo). Si hace "
                           "falta, Ando lo cierra desde el tablero.",
        "carpeta_colmena": "Colmena: es el repo de Colmena y no abre pedidos ahí. Pedile a Ando que la abra "
                           "desde el tablero, o hacé el trabajo con ayudantes (subagentes).",
        "carpeta_no_permitida": "Colmena: esa carpeta no está entre las que permite. No pruebes otra por tu "
                                "cuenta: decile a Ando cuál querías o que la abra a mano desde el tablero.",
    }


@pytest.mark.parametrize("status", ["idle", "done"])
def test_entrega_inmediata_si_esta_quieta(status):
    a = Armado(status)
    a.avisos.al_descarte(ORIGEN_SESION, "fila_llena")
    a.correr()
    assert len(a.enviados) == 1
    body = a.enviados[0]
    assert body.pane_id == "w1:p1"
    assert body.texto == TEXTOS["fila_llena"]
    assert body.origen == ORIGEN


def test_origen_correcto_y_no_publico():
    assert ORIGEN == "pedido-pestana-aviso"
    assert ORIGEN not in ORIGENES_PUBLICOS
    MensajeBody(id="aviso-12345678", pane_id="w1:p1", texto="x", origen=ORIGEN)


def test_diferida_hasta_que_queda_quieta():
    a = Armado("working")
    a.avisos.al_descarte(ORIGEN_SESION, "cooldown")
    a.correr()
    assert a.enviados == []
    a.tablero("blocked")
    a.correr()
    assert a.enviados == []
    a.tablero("done")
    a.correr()
    assert [b.texto for b in a.enviados] == [TEXTOS["cooldown"]]
    a.tablero("working")
    a.tablero("idle")
    a.correr()
    assert len(a.enviados) == 1


def test_un_pendiente_por_sesion_y_motivo():
    a = Armado("working")
    a.avisos.al_descarte(ORIGEN_SESION, "cooldown")
    a.avisos.al_descarte(ORIGEN_SESION, "cooldown")
    a.avisos.al_descarte(ORIGEN_SESION, "vencido")
    a.tablero("idle")
    a.correr()
    assert sorted(b.texto for b in a.enviados) == sorted([TEXTOS["cooldown"], TEXTOS["vencido"]])


def test_pendiente_vence_a_los_10_min():
    a = Armado("working")
    a.avisos.al_descarte(ORIGEN_SESION, "tope")
    a.reloj.t += VENCE_S
    a.tablero("idle")
    a.correr()
    assert a.enviados == []
    assert VENCE_S == 600


@pytest.mark.parametrize("error", [TraspasoError(502, "no"), NoTomado("sin prompt")])
def test_error_de_envio_se_descarta(caplog, error):
    caplog.set_level(logging.INFO, logger="orquestador.avisos_origen")
    a = Armado("idle", error=error)
    a.avisos.al_descarte(ORIGEN_SESION, "vencido")
    a.correr()
    assert a.enviados == []
    assert "no se pudo avisar" in caplog.text
    a.error = None
    a.tablero("working")
    a.tablero("idle")
    a.correr()
    assert a.enviados == []


def test_sesion_ausente_del_tablero_queda_pendiente():
    a = Armado("idle")
    a.board = {"workspaces": []}
    a.avisos.al_descarte(ORIGEN_SESION, "vencido")
    a.correr()
    assert a.enviados == []
    a.tablero("idle")
    a.correr()
    assert len(a.enviados) == 1


def test_sin_sesion_ni_pane_no_hace_nada():
    a = Armado("idle")
    a.avisos.al_descarte({"pane_id": "", "nombre": "", "session_id": ""}, "vencido")
    a.correr()
    assert a.enviados == [] and a.tareas == []


PREGUNTA = {"asks_user": True, "pregunta_real": True, "preguntas": 1}


@pytest.mark.parametrize("status", ["idle", "done"])
def test_sesion_que_pregunta_a_ando_no_recibe_el_aviso(status):
    a = Armado(status)
    a.board = _board(status, **PREGUNTA)
    a.avisos.al_descarte(ORIGEN_SESION, "vencido")
    a.correr()
    assert a.enviados == []
    a.tablero(status, asks_user=True)
    a.correr()
    assert a.enviados == []


def test_aviso_retenido_por_pregunta_se_entrega_al_resolverse():
    a = Armado("done")
    a.board = _board("done", **PREGUNTA)
    a.avisos.al_descarte(ORIGEN_SESION, "cooldown")
    a.tablero("working")
    a.correr()
    assert a.enviados == []
    a.tablero("idle")
    a.correr()
    assert [b.texto for b in a.enviados] == [TEXTOS["cooldown"]]


def test_aviso_retenido_por_pregunta_vence_a_los_10_min():
    a = Armado("done")
    a.board = _board("done", **PREGUNTA)
    a.avisos.al_descarte(ORIGEN_SESION, "fila_llena")
    a.reloj.t += VENCE_S
    a.tablero("idle")
    a.correr()
    assert a.enviados == []


# --- AvisoLibre: texto ya armado (fin del trabajador Cursor) ---


class ArmadoLibre:
    def __init__(self, status: str = "working"):
        from orquestador.avisos_origen import AvisoLibre

        self.board = _board(status)
        self.enviados: list[MensajeBody] = []
        self.tareas: list = []
        self.reloj = Reloj()
        self.aviso = AvisoLibre(self.mandar, lambda: self.board, self.tareas.append, reloj=self.reloj)

    async def mandar(self, body: MensajeBody) -> dict:
        self.enviados.append(body)
        return {"ok": True}

    def correr(self) -> None:
        tareas, self.tareas[:] = list(self.tareas), []

        async def todas():
            await asyncio.gather(*tareas)

        asyncio.run(todas())

    def tablero(self, status: str, **extra) -> None:
        prev, self.board = self.board, _board(status, **extra)
        self.aviso.al_tablero(prev, self.board)


def test_aviso_libre_espera_sesion_quieta_y_sin_pregunta():
    a = ArmadoLibre("working")
    a.aviso.encolar({"tipo": "claude", "session_id": SID, "pane_id": "w1:p1", "nombre": "Uno"}, "Colmena: terminó")
    assert a.tareas == []
    a.tablero("idle", asks_user=True)
    assert a.tareas == []
    a.tablero("idle")
    a.correr()
    assert len(a.enviados) == 1
    body = a.enviados[0]
    assert body.texto == "Colmena: terminó" and body.origen == "cursor-aviso" and body.pane_id == "w1:p1"
    a.tablero("idle")
    assert a.tareas == []


def test_aviso_libre_entrega_ya_si_esta_quieta_y_dos_avisos_no_se_pisan():
    a = ArmadoLibre("idle")
    a.aviso.encolar({"session_id": SID}, "uno")
    a.aviso.encolar({"session_id": SID}, "dos")
    a.correr()
    assert [b.texto for b in a.enviados] == ["uno", "dos"]


def test_aviso_libre_vence():
    from orquestador.avisos_origen import VENCE_LIBRE_S

    assert VENCE_LIBRE_S == 1800
    a = ArmadoLibre("working")
    a.aviso.encolar({"session_id": SID}, "Colmena: terminó")
    a.reloj.t += VENCE_LIBRE_S
    a.tablero("idle")
    assert a.tareas == [] and a.enviados == []


def test_aviso_libre_descarta_sin_destino_o_texto_largo():
    from orquestador.mensaje import MAX_TEXT

    a = ArmadoLibre("idle")
    a.aviso.encolar({"tipo": "claude"}, "sin sesión")
    a.aviso.encolar({"session_id": SID}, "x" * (MAX_TEXT + 1))
    a.aviso.encolar({"session_id": SID}, "")
    assert a.tareas == []


# --- MCP (CA14) ---

def test_descarte_de_un_pedido_por_mcp_no_avisa():
    a = Armado("idle")
    a.avisos.al_descarte({**ORIGEN_SESION, "via": "mcp"}, "fila_llena")
    a.correr()
    assert a.enviados == []


def test_descarte_de_la_marca_sigue_avisando_con_el_store():
    from orquestador.pedidos_pestana import PedidosPestanaStore

    a = Armado("idle")
    store = PedidosPestanaStore()
    store.on_descarte(a.avisos.al_descarte)
    store.descartar(ORIGEN_SESION, "carpeta_colmena")
    store.descartar({**ORIGEN_SESION, "via": "mcp"}, "carpeta_colmena")
    a.correr()
    assert len(a.enviados) == 1


from orquestador.avisos_origen import TEXTOS as _TEXTOS, texto_mcp


def test_carpeta_colmena_dice_que_hacer():
    t = texto_mcp("carpeta_colmena")
    assert "repo de Colmena" in t and "tablero" in t and "subagentes" in t


def test_carpeta_no_permitida_dice_que_hacer():
    t = texto_mcp("carpeta_no_permitida")
    assert "no está entre las que" in t and "decile a Ando" in t
    assert "carpeta_no_permitida" in _TEXTOS


def test_texto_mcp_sin_prefijo_colmena_ni_pestana():
    t = texto_mcp("cooldown")
    assert not t.startswith("Colmena:") and "pedido de pestaña" not in t and "Probá de nuevo" in t


def test_tope_agrega_que_hacer():
    assert "Esperá" in texto_mcp("tope")


def test_motivo_desconocido_usa_fallback_con_el_codigo():
    t = texto_mcp("algo_raro")
    assert "algo_raro" in t and "decile a Ando" in t and t != "Colmena descartó el pedido."


def test_todo_motivo_de_textos_tiene_texto_mcp_no_vacio():
    assert all(texto_mcp(m).strip() for m in _TEXTOS)
