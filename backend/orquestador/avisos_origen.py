"""Le avisa a la sesión que pidió una pestaña que su pedido se descartó.

El texto es fijo por motivo (no repite nada del pedido) y se entrega cuando la
sesión queda quieta (idle o done) y no le está preguntando nada a Ando; si no lo queda en VENCE_S, el aviso se tira.
Un envío que falla no se reintenta.
"""
import logging
import time
import uuid
from typing import Awaitable, Callable, Optional

from .board import _agents
from .mensaje import MensajeBody

log = logging.getLogger(__name__)

ORIGEN = "pedido-pestana-aviso"
VENCE_S = 600.0
QUIETA = ("idle", "done")
TEXTOS = {
    "fila_llena": "Colmena: tu pedido de pestaña no se abrió porque ya tenías 3 pendientes. "
                  "Esperá a que Ando los responda.",
    "cooldown": "Colmena: tu pedido de pestaña no se abrió porque llegó muy seguido del anterior. "
                "Probá de nuevo en un rato.",
    "tope": "Colmena: tu pedido de pestaña no se abrió porque hay demasiados pedidos pendientes.",
    "vencido": "Colmena: tu pedido de pestaña venció sin respuesta de Ando y no se abrió.",
    "terminal_no_encontrada": "Colmena: tu pedido para cerrar una terminal no le llegó a Ando porque no hay una "
                              "sola terminal común con ese id o nombre. Usá el id del panel (por ejemplo w2:p1); "
                              "para una sesión de Claude usá \"sesion\".",
    "cierre_no_encontrado": "Colmena: tu pedido para cerrar no le llegó a Ando porque no encontré nada con ese id o nombre.",
    "cierre_ambiguo": "Colmena: tu pedido para cerrar no le llegó a Ando porque hay más de una coincidencia con ese "
                      "nombre. Usá el id (por ejemplo w2:p1, w2:t1 o w2).",
    "cierre_protegido": "Colmena: no se puede cerrar Colmena ni un espacio protegido; el pedido no le llegó a Ando.",
    "sesion_compartida": "Colmena: esa sesión comparte la pestaña con otras terminales, así que no la cierro sola. "
                         "Si hace falta, pedí cerrar la pestaña.",
    "cierre_no_posible": "Colmena: eso no se puede cerrar desde un pedido (por ejemplo, es el único espacio abierto). "
                         "Ando lo puede cerrar desde el tablero.",
    "cierre_cambio": "Colmena: no cerré lo que pediste porque cambió desde que lo pediste.",
    "cierre_no_hecho": "Colmena: no se cerró lo que pediste (falló o no terminó de guardar a tiempo). Si hace falta, "
                       "Ando lo cierra desde el tablero.",
    "carpeta_colmena": "Colmena no abre pedidos en su propio repo: si hace falta, Ando lo abre a mano desde el tablero.",
}


class AvisosOrigen:
    def __init__(self, mandar: Callable[[MensajeBody], Awaitable], tablero: Callable[[], Optional[dict]],
                 spawn: Callable, reloj: Callable[[], float] = time.monotonic):
        self.mandar = mandar
        self.tablero = tablero
        self.spawn = spawn
        self.reloj = reloj
        # (sesión, motivo) -> {"origen": ..., "desde": t}
        self._pendientes: dict[tuple[str, str], dict] = {}

    @staticmethod
    def _agente(board: Optional[dict], origen: dict) -> Optional[dict]:
        agentes = list(_agents(board or {}))
        sid = origen.get("session_id")
        if sid:
            hallado = next((a for a in agentes if a.get("session_id") == sid), None)
            if hallado:
                return hallado
        pane = origen.get("pane_id")
        return next((a for a in agentes if pane and a.get("pane_id") == pane), None)

    def al_descarte(self, origen: dict, motivo: str) -> None:
        if motivo not in TEXTOS:
            return
        clave = (origen.get("session_id") or origen.get("pane_id") or "", motivo)
        if not clave[0] or clave in self._pendientes:
            return
        self._pendientes[clave] = {"origen": dict(origen), "desde": self.reloj()}
        self._entregar_si_quieta(clave, self.tablero())

    def al_tablero(self, _prev, board: Optional[dict]) -> None:
        ahora = self.reloj()
        for clave, pend in list(self._pendientes.items()):
            if ahora - pend["desde"] >= VENCE_S:
                del self._pendientes[clave]
                log.info("aviso de pedido de pestaña vencido sin entregar (%s)", clave[1])
                continue
            self._entregar_si_quieta(clave, board)

    def _entregar_si_quieta(self, clave: tuple[str, str], board: Optional[dict]) -> None:
        agente = self._agente(board, self._pendientes[clave]["origen"])
        if not agente or agente.get("status") not in QUIETA or not agente.get("pane_id"):
            return
        # Si espera una respuesta de Ando, el aviso le llegaría como respuesta y le borraría la tarjeta.
        if agente.get("asks_user") or agente.get("pregunta_real") or agente.get("preguntas"):
            return
        pend = self._pendientes.pop(clave)
        self.spawn(self._enviar(agente["pane_id"], pend["origen"].get("nombre") or "", clave[1]))

    async def _enviar(self, pane: str, nombre: str, motivo: str) -> None:
        body = MensajeBody(id=f"aviso-{uuid.uuid4().hex}", pane_id=pane, texto=TEXTOS[motivo],
                           origen=ORIGEN, destino=nombre[:200])
        try:
            await self.mandar(body)
        except Exception as exc:
            log.info("no se pudo avisar a %s del pedido de pestaña (%s): %s", pane, motivo, type(exc).__name__)


VENCE_LIBRE_S = 1800.0
ORIGEN_LIBRE = "cursor-aviso"


class AvisoLibre:
    """Como AvisosOrigen, pero con un texto ya armado (el fin de un trabajador Cursor): se entrega cuando la
    sesión queda quieta y sin pregunta pendiente; si no pasa en VENCE_LIBRE_S, se tira. No se reintenta."""

    def __init__(self, mandar: Callable[[MensajeBody], Awaitable], tablero: Callable[[], Optional[dict]],
                 spawn: Callable, reloj: Callable[[], float] = time.monotonic, origen: str = ORIGEN_LIBRE):
        self.mandar = mandar
        self.tablero = tablero
        self.spawn = spawn
        self.reloj = reloj
        self.origen = origen
        self._pendientes: dict[str, dict] = {}

    def encolar(self, origen: dict, texto: str) -> None:
        from .mensaje import MAX_TEXT

        destino = {k: origen.get(k) for k in ("session_id", "pane_id", "nombre") if isinstance(origen.get(k), str)}
        if not (destino.get("session_id") or destino.get("pane_id")) or not texto or len(texto) > MAX_TEXT:
            log.info("aviso libre descartado: sin destino o texto inválido")
            return
        clave = uuid.uuid4().hex
        self._pendientes[clave] = {"origen": destino, "texto": texto, "desde": self.reloj()}
        self._entregar_si_quieta(clave, self.tablero())

    def al_tablero(self, _prev, board: Optional[dict]) -> None:
        ahora = self.reloj()
        for clave, pend in list(self._pendientes.items()):
            if ahora - pend["desde"] >= VENCE_LIBRE_S:
                del self._pendientes[clave]
                log.info("aviso libre vencido sin entregar")
                continue
            self._entregar_si_quieta(clave, board)

    def _entregar_si_quieta(self, clave: str, board: Optional[dict]) -> None:
        agente = AvisosOrigen._agente(board, self._pendientes[clave]["origen"])
        if not agente or agente.get("status") not in QUIETA or not agente.get("pane_id"):
            return
        if agente.get("asks_user") or agente.get("pregunta_real") or agente.get("preguntas"):
            return
        pend = self._pendientes.pop(clave)
        self.spawn(self._enviar(agente["pane_id"], pend))

    async def _enviar(self, pane: str, pend: dict) -> None:
        body = MensajeBody(id=f"aviso-{uuid.uuid4().hex}", pane_id=pane, texto=pend["texto"], origen=self.origen,
                           destino=(pend["origen"].get("nombre") or "")[:200])
        try:
            await self.mandar(body)
        except Exception as exc:
            log.info("no se pudo mandar el aviso a %s: %s", pane, type(exc).__name__)
