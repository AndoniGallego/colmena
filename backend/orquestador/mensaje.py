import logging
import re
import uuid
from typing import Callable, Literal, Optional

from pathlib import Path

from pydantic import BaseModel, Field

from .enchufe import TerminalesError, como_snapshot
from .locks import PaneLocks
from .traspaso import CONTROL_RE, FALLO_TERMINAL, ID_RE, TraspasoError, _need_id, _now
from .uploads import con_adjuntos, resolve_adjuntos

MAX_TEXT = 4000
MAX_ATTACHMENTS = 5
TEXT_CONTROL_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f  ]")
LINE_BREAK_RE = re.compile(r"\s*\n\s*")
ORIGENES_PUBLICOS = ("manual", "jefe")
UNCERTAIN = "Puede que ese mensaje ya haya llegado: mirá la sesión. Si no llegó, volvé a mandarlo."
log = logging.getLogger(__name__)


class StopBody(BaseModel):
    pane_id: str = Field(..., max_length=64)


class MensajeBody(BaseModel):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    pane_id: str = Field(..., max_length=64)
    texto: str = Field("", max_length=20000)
    adjuntos: list[str] = Field(default_factory=list, max_length=MAX_ATTACHMENTS)
    origen: Literal["manual", "jefe", "usuario", "pedido-pestana", "pedido-pestana-aviso", "pedido-mr",
                    "comentario-diff", "mr-job", "mr-hilo", "cursor-aviso", "programada", "copiloto", "guia"]
    destino: str = Field("", max_length=200)
    por_que: str = Field("", max_length=2000)


def prepare_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").strip()
    if not 1 <= len(text) <= MAX_TEXT:
        raise TraspasoError(400, f"el mensaje debe tener entre 1 y {MAX_TEXT} caracteres")
    if TEXT_CONTROL_RE.search(text):
        raise TraspasoError(400, "el mensaje tiene caracteres de control")
    flat = LINE_BREAK_RE.sub(" ", text)
    return f" {flat}" if flat.startswith("-") else flat


class MensajeService:
    def __init__(self, enchufe, state, self_pane: Callable[[], Optional[str]] = lambda: None,
                 uploads_dir: Optional[Path] = None, locks: Optional[PaneLocks] = None,
                 protected_workspaces: Optional[list] = None, protected_panes: Callable[[], set] = lambda: set()):
        self.enchufe = enchufe
        self.protected = {w.strip().casefold() for w in (protected_workspaces or [])}
        self.protected_panes = protected_panes
        self.state = state
        self.self_pane = self_pane
        self.uploads_dir = uploads_dir
        self._inflight: set = set()
        self.locks = locks or PaneLocks()

    def _already_done(self, ident: str) -> bool:
        return any(m.get("id") == ident and m.get("ok") for m in self.state.mensajes())

    def _uncertain(self, ident: str) -> bool:
        return any(m.get("id") == ident and not m.get("ok") and m.get("incierto") for m in self.state.mensajes())

    async def execute(self, body: MensajeBody, auditoria: Optional[dict] = None) -> dict:
        if body.id in self._inflight or self._already_done(body.id):
            raise TraspasoError(409, "Ya se mandó ese mensaje")
        if self._uncertain(body.id):
            raise TraspasoError(409, UNCERTAIN)
        pane = _need_id(body.pane_id, "pane_id")
        if pane == self.self_pane():
            raise TraspasoError(400, "no se le puede mandar un mensaje al orquestador")
        text = self._compose(body)
        self._inflight.add(body.id)
        try:
            async with self.locks.get(pane):
                await self._send(body, pane, text, auditoria)
            return self._finish(body, text, auditoria)
        finally:
            self._inflight.discard(body.id)

    async def _lookup(self, pane: str) -> tuple:
        try:
            snapshot = como_snapshot(await self.enchufe.tablero())
        except TerminalesError as exc:
            raise TraspasoError(502, f"Las terminales no responden: {exc}")
        agent = next((a for a in snapshot.get("agents", []) if a.get("pane_id") == pane), None)
        if agent is None:
            raise TraspasoError(404, "Esa sesión ya no está abierta")
        return snapshot, agent

    async def _agent(self, pane: str) -> dict:
        return (await self._lookup(pane))[1]

    def _ws_protected(self, snapshot: dict, agent: dict) -> bool:
        ws = next((w for w in snapshot.get("workspaces", []) if w.get("workspace_id") == agent.get("workspace_id")), None)
        return bool(ws) and (ws.get("label") or "").strip().casefold() in self.protected

    async def _send(self, body: MensajeBody, pane: str, text: str, auditoria: Optional[dict] = None) -> None:
        # Lo que vos mandás o confirmás llega a cualquier sesión; lo automático no toca la protegida.
        confirmado = body.origen in ORIGENES_PUBLICOS
        if not confirmado and pane in self.protected_panes():
            raise TraspasoError(400, "no se le puede mandar un mensaje al orquestador")
        snapshot, agent = await self._lookup(pane)
        if not confirmado and self._ws_protected(snapshot, agent):
            raise TraspasoError(400, "esa sesión está en el workspace protegido")
        if agent.get("agent_status") == "blocked":
            raise TraspasoError(409, "la sesión espera una aprobación tuya en la terminal")
        try:
            await self.enchufe.mandar_prompt(pane, text)
        except TerminalesError as exc:
            self._record(body, text, ok=False, error=str(exc)[:300], incierto=True, auditoria=auditoria)
            raise TraspasoError(502, f"{FALLO_TERMINAL}: {exc}")

    async def stop(self, body: StopBody) -> dict:
        pane = _need_id(body.pane_id, "pane_id")
        if pane == self.self_pane():
            raise TraspasoError(400, "no se puede frenar al orquestador")
        agent = await self._agent(pane)
        if agent.get("agent_status") != "working":
            raise TraspasoError(409, "La sesión no está trabajando")
        try:
            await self.enchufe.interrumpir(pane)
        except TerminalesError as exc:
            raise TraspasoError(502, f"{FALLO_TERMINAL}: {exc}")
        log.info("freno enviado a %s", pane)
        return {"ok": True, "pane_id": pane}

    def _compose(self, body: MensajeBody) -> str:
        paths = resolve_adjuntos(self.uploads_dir, body.adjuntos)
        if paths and not body.texto.strip():
            return con_adjuntos("", paths)
        return con_adjuntos(prepare_text(body.texto), paths)

    def _record(self, body: MensajeBody, text: str, ok: bool, error: str = "", incierto: bool = False,
                auditoria: Optional[dict] = None) -> None:
        entry = {"id": body.id, "pane_id": body.pane_id, "destino": CONTROL_RE.sub(" ", body.destino)[:200],
                 "origen": body.origen, "ts": _now(), "ok": ok, "texto": text[:200]}
        if error:
            entry["error"] = error
        if incierto:
            entry["incierto"] = True
        entry.update({k: v for k, v in (auditoria or {}).items() if k not in entry})
        self.state.add_mensaje(entry)

    def _finish(self, body: MensajeBody, text: str, auditoria: Optional[dict] = None) -> dict:
        self._record(body, text, ok=True, auditoria=auditoria)
        result = {"ok": True, "pane_id": body.pane_id}
        if body.origen == "jefe":
            destino = CONTROL_RE.sub(" ", body.destino or body.pane_id)[:200]
            event = {"id": uuid.uuid4().hex, "role": "event", "text": f"Mensaje enviado a {destino}", "ts": _now()}
            result["event"] = event
        return result
