"""La pregunta con tarjetas ```opciones de una sesión, para contestarla desde el notch; todo se recalcula contra el board."""
import time
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, Field, field_validator

from .cierre_dia import nombres
from .digest import quitar_estado
from .mensaje import MensajeBody
from .opciones import preguntas_de, signature
from .redaccion import redactar
from .enchufe import TerminalesError
from .traspaso import TraspasoError

SIN_PREGUNTA = "SIN_PREGUNTA"
YA_CONTESTADA = "YA_CONTESTADA"
CONTESTADAS_TTL = 600.0
CONTESTADAS_MAX = 200


class PreguntaBody(BaseModel):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    sig: str = Field(..., max_length=200)
    texto: str = Field(..., max_length=20000)

    @field_validator("texto")
    @classmethod
    def _no_vacio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("texto vacío")
        return v


def _ubicar(board: Optional[dict], sid: str) -> tuple:
    nombre, _donde, agent, ws = nombres(board).get(sid, ("", "", None, None))
    return agent, ws, nombre


def _redactada(preguntas: list) -> list:
    return [{"pregunta": redactar(q["pregunta"]),
             "opciones": [{"label": redactar(o["label"]), "detalle": redactar(o["detalle"]),
                           "recomendada": o["recomendada"]} for o in q["opciones"]]} for q in preguntas]


class PreguntaSesionService:
    def __init__(self, board: Callable[[], Awaitable[Optional[dict]]], digests, mensajes,
                 protected_workspaces: Optional[list] = None, protected_panes: Callable[[], set] = lambda: set(),
                 refrescar: Optional[Callable[[], Awaitable[Optional[dict]]]] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.board = board
        self.refrescar = refrescar
        self.clock = clock
        self._contestadas: dict = {}
        self.digests = digests
        self.mensajes = mensajes
        self.protected = {w.strip().casefold() for w in (protected_workspaces or [])}
        self.protected_panes = protected_panes

    def _vigente(self, board: Optional[dict], sid: str) -> Optional[dict]:
        agent, ws, nombre = _ubicar(board, sid)
        if agent is None or agent.get("kind") != "claude" or not (agent.get("asks_user") or agent.get("pendiente")):
            return None
        if agent.get("status") not in ("idle", "done") or self._excluida(agent, ws):
            return None
        digest = self.digests.get(sid)
        preguntas = preguntas_de(quitar_estado(digest.last_claude_text().strip())) if digest else []
        if not preguntas:
            return None
        sig = signature(sid, preguntas)
        if self._contestada(sid, sig):
            return None
        return {"sig": sig, "session_id": sid, "pane_id": agent.get("pane_id"),
                "nombre": nombre, "preguntas": preguntas}

    def _contestada(self, sid: str, sig: str) -> bool:
        ts = self._contestadas.get((sid, sig))
        return ts is not None and self.clock() - ts < CONTESTADAS_TTL

    def _recordar(self, sid: str, sig: str) -> None:
        now = self.clock()
        self._contestadas = {k: t for k, t in self._contestadas.items() if now - t < CONTESTADAS_TTL}
        while len(self._contestadas) >= CONTESTADAS_MAX:
            del self._contestadas[next(iter(self._contestadas))]
        self._contestadas[(sid, sig)] = now

    async def _board_fresco(self) -> Optional[dict]:
        if self.refrescar is not None:
            try:
                return await self.refrescar()
            except TerminalesError:
                pass
        return await self.board()

    def _excluida(self, agent: dict, ws: dict) -> bool:
        return agent.get("pane_id") in self.protected_panes() or (ws.get("label") or "").strip().casefold() in self.protected

    async def leer(self, sid: str) -> dict:
        pregunta = self._vigente(await self.board(), sid)
        if pregunta is None:
            raise TraspasoError(404, SIN_PREGUNTA)
        return {**pregunta, "preguntas": _redactada(pregunta["preguntas"])}

    async def responder(self, sid: str, body: PreguntaBody) -> dict:
        board = await self._board_fresco()
        agent, ws, nombre = _ubicar(board, sid)
        if agent is not None:
            if self._excluida(agent, ws):
                raise TraspasoError(400, "Esa sesión no admite respuestas desde acá")
            if agent.get("status") in ("working", "blocked"):
                raise TraspasoError(409, "La sesión está ocupada: contestale cuando termine")
        pregunta = self._vigente(board, sid)
        if pregunta is None or pregunta["sig"] != body.sig:
            raise TraspasoError(409, YA_CONTESTADA)
        self._recordar(sid, pregunta["sig"])
        try:
            return await self.mensajes.execute(MensajeBody(
                id=body.id, pane_id=pregunta["pane_id"], texto=body.texto, origen="manual", destino=nombre))
        except BaseException:
            self._contestadas.pop((sid, pregunta["sig"]), None)
            raise
