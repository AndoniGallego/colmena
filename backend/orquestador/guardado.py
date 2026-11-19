"""Guardar en Engram antes de cerrar (spec 16 y 20): pide a las sesiones Claude del target que guarden y esperan su turno real."""
import asyncio
import logging
from typing import Callable, Optional

from . import silencio
from .cierre import CierreBody, CierreService, PreviewBody
from .enchufe import TerminalesError
from .traspaso import FALLO_TERMINAL, TraspasoError

log = logging.getLogger("orquestador.guardado")

# Constante del servidor: nunca lleva contenido del usuario ni de transcripts.
MENSAJE = ("Antes de cerrar esta sesión: guardá en Engram lo que haga falta (mem_save y mem_session_summary) "
           "y terminá tu turno.")
TIMEOUT = 300.0
MAX_LOTES = 20


class _Pane:
    def __init__(self, pane_id: str, titulo: str, pedido: bool, estado: str):
        self.pane_id = pane_id
        self.titulo = titulo
        self.pedido = pedido
        self.estado = estado

    def public(self) -> dict:
        return {"pane_id": self.pane_id, "titulo": self.titulo, "estado": self.estado}


class _Target:
    def __init__(self, key: str, body: CierreBody, preview: dict):
        self.key = key
        self.body = body
        self.tipo = body.tipo
        self.target_id = body.target_id
        self.label = preview.get("label") or body.target_id
        self.estructura = CierreService.estructura(preview)
        self.panes: dict = {}
        self.estado = "guardando"
        self.error = ""
        self.guardado = ""
        self.resultado: Optional[dict] = None

    def public(self) -> dict:
        return {"key": self.key, "tipo": self.tipo, "target_id": self.target_id, "label": self.label,
                "estado": self.estado, "error": self.error, "guardado": self.guardado,
                "panes": [p.public() for p in self.panes.values()], "resultado": self.resultado}


class Lote:
    def __init__(self, ident: str, origen: str, plan_id: str, listener: Optional[Callable]):
        self.id = ident
        self.origen = origen
        self.plan_id = plan_id
        self.listener = listener
        self.targets: dict = {}
        self.vencido = False
        self.handle = None
        self.hecho = asyncio.Event()
        self.cancelado = False

    @property
    def terminado(self) -> bool:
        return bool(self.targets) and all(t.estado in ("cerrado", "error", "cancelado") for t in self.targets.values())

    def trabado(self, target) -> bool:
        """Cerrar igual solo vale para lo que no avanza: todo si venció la espera; si no, el target cuyas sesiones
        pendientes están todas esperando al usuario o fallaron (una que sigue guardando se espera)."""
        if target.estado != "guardando":
            return False
        if self.vencido:
            return True
        pendientes = [p for p in target.panes.values() if not p.pedido or p.estado != "listo"]
        return bool(pendientes) and all(p.estado in ("bloqueado", "fallo") for p in pendientes)

    @property
    def puede_cerrar_igual(self) -> bool:
        return any(self.trabado(t) for t in self.targets.values())

    def public(self) -> dict:
        return {"id": self.id, "origen": self.origen, "plan_id": self.plan_id, "vencido": self.vencido,
                "puede_cerrar_igual": self.puede_cerrar_igual, "terminado": self.terminado,
                "targets": [t.public() for t in self.targets.values()]}


def _agentes(board: Optional[dict]) -> dict:
    out = {}
    for ws in (board or {}).get("workspaces", []):
        for tab in ws.get("tabs", []):
            for agent in tab.get("agents", []):
                if agent.get("pane_id"):
                    out[agent["pane_id"]] = agent
    return out


def _termino(before: Optional[dict], agent: dict) -> bool:
    """Turno real terminado: venía trabajando (o esperando un diálogo) y volvió a idle/done con respuesta del modelo."""
    return (bool(before) and before.get("status") in ("working", "blocked") and agent.get("status") in ("idle", "done")
            and not agent.get("turno_local") and not silencio.vigente())


class GuardadoService:
    """Nunca cierra solo tras el timeout: la decisión de "Cerrar igual" es del usuario."""

    def __init__(self, cierres: CierreService, enchufe, locks, call_later: Optional[Callable] = None,
                 emit: Callable[[str, dict], None] = lambda event, data: None, spawn: Optional[Callable] = None,
                 timeout: float = TIMEOUT):
        self.cierres = cierres
        self.enchufe = enchufe
        self.locks = locks
        self.call_later = call_later or (lambda delay, fn: asyncio.get_running_loop().call_later(delay, fn))
        self.emit = emit
        self.spawn = spawn or (lambda coro: asyncio.get_running_loop().create_task(coro))
        self.timeout = timeout
        self._lotes: dict = {}

    # ---------- lectura ----------

    def listar(self) -> list:
        return [lote.public() for lote in self._lotes.values()]

    def lote(self, ident: str) -> Optional[Lote]:
        return self._lotes.get(ident)

    # ---------- entrada ----------

    async def iniciar_uno(self, body: CierreBody, sin_guardar: bool = False, origen: Optional[str] = None,
                          plan_id: str = "", key: str = "", listener: Optional[Callable] = None):
        """Un solo target. Devuelve el resultado del cierre si no había nada que esperar, o el `Lote` si quedó guardando."""
        origen = origen or body.origen
        if sin_guardar:
            return await self.cierres.execute(body, guardado="saltado", solo_unknown=body.forzar)
        existente = self._lotes.get(body.id)
        if existente is not None and not existente.terminado:
            return existente
        self._lotes.pop(body.id, None)
        if self.cierres._already_done(body.id):
            raise TraspasoError(409, "Ya se cerró")
        lote = Lote(body.id, origen, plan_id, listener)
        self._registrar(lote)  # reserva el id antes del primer await: dos dispositivos no arman dos lotes
        try:
            return await self._iniciar_uno(lote, body, key)
        except BaseException:
            self._descartar(lote)
            raise

    async def _iniciar_uno(self, lote: Lote, body: CierreBody, key: str):
        preview = await self.cierres.preview(PreviewBody(tipo=body.tipo, target_id=body.target_id))
        self._sin_bloqueantes_duros(preview, tolerar_unknown=body.forzar, body=body)
        self._huella_vigente(body, preview)
        if lote.cancelado:  # cancelaron mientras esperaba el preview: nada se pide ni se cierra
            target = lote.targets[key or "t1"] = self._armar(key or "t1", body, preview)
            target.estado = "cancelado"
            self._notificar(lote)
            return lote
        if not [p for p in preview["panes"] if p.get("kind") == "claude"]:
            self._descartar(lote)
            return await self.cierres.execute(body, guardado="saltado", solo_unknown=body.forzar)
        lote.targets[key or "t1"] = self._armar(key or "t1", body, preview)
        await self._pedir_todo(lote)
        if not lote.cancelado:
            self._avanzar(lote)
        self._notificar(lote)
        return lote

    async def iniciar_tanda(self, ident: str, entradas: list, origen: str = "plan", plan_id: str = "",
                            sin_guardar: bool = False, listener: Optional[Callable] = None) -> Lote:
        """Varios targets con un solo pedido, un solo timeout y un solo "Cerrar sin guardar".

        `entradas`: [(key, CierreBody, huella_vista_por_el_usuario o "")]. Un target que falla al prepararse queda en `error` y
        los demás siguen."""
        lote = Lote(ident, origen, plan_id, listener)
        self._registrar(lote)
        try:
            await self._tanda(lote, entradas, sin_guardar)
        except BaseException:
            self._descartar(lote)
            raise
        self._notificar(lote)
        return lote

    async def _tanda(self, lote: Lote, entradas: list, sin_guardar: bool) -> None:
        for key, body, vista in entradas:
            try:
                preview = await self.cierres.preview(PreviewBody(tipo=body.tipo, target_id=body.target_id))
                if vista:
                    self._huella_vigente(body.model_copy(update={"huella": vista}), preview)
                if not sin_guardar:
                    self._sin_bloqueantes_duros(preview, body=body)
                lote.targets[key] = self._armar(key, body, preview)
            except (TraspasoError, TerminalesError) as exc:
                target = _Target(key, body, {"label": body.destino or body.target_id})
                target.estado, target.error = "error", (exc.detail if isinstance(exc, TraspasoError) else f"{FALLO_TERMINAL}: {exc}")[:300]
                lote.targets[key] = target
        if lote.cancelado:
            for target in lote.targets.values():
                if target.estado == "guardando":
                    target.estado = "cancelado"
        elif sin_guardar:
            for target in lote.targets.values():
                if target.estado == "guardando":
                    await self._cerrar_target(lote, target, forzar=False, guardado="saltado")
        else:
            await self._pedir_todo(lote)
            if not lote.cancelado:
                self._avanzar(lote)

    # ---------- preparación ----------

    def _huella_vigente(self, body: CierreBody, preview: dict) -> None:
        if body.huella != preview["huella"]:
            what = "tab" if body.tipo == "tab" else "workspace"
            raise TraspasoError(409, f"El {what} cambió, revisalo de nuevo")

    @staticmethod
    def _sin_bloqueantes_duros(preview: dict, tolerar_unknown: bool = False, body: Optional[CierreBody] = None) -> None:
        """Trabajando o sin saber: eso se frena a mano; un diálogo abierto (`blocked`) se tolera y espera al usuario."""
        duros = [b for b in preview.get("bloqueantes", []) if b["status"] != "blocked" and not (tolerar_unknown and b["status"] == "unknown")]
        if duros:
            if body is not None:
                log.info("cierre rechazado %s %s: %s", body.tipo, body.target_id,
                         ", ".join(f"{b['pane_id']}={b['status']}" for b in duros))
            only_unknown = all(b["status"] == "unknown" for b in duros)
            detail = "No sé si está trabajando: revisala o cerrala en la terminal" if only_unknown else "Frenala primero"
            raise TraspasoError(409, detail, {"bloqueantes": preview.get("bloqueantes", [])})

    @staticmethod
    def _clasificar(preview: dict) -> tuple:
        ask, bloqueados = [], []
        for pane in preview.get("panes", []):
            if pane.get("kind") != "claude":
                continue
            (bloqueados if pane.get("status") == "blocked" else ask).append(pane)
        return ask, bloqueados

    def _armar(self, key: str, body: CierreBody, preview: dict) -> _Target:
        target = _Target(key, body, preview)
        ask, bloqueados = self._clasificar(preview)
        self._poblar(target, preview, ask, bloqueados)
        return target

    @staticmethod
    def _poblar(target: _Target, preview: dict, ask: list, bloqueados: list) -> None:
        target.panes = {}
        for pane in ask:
            target.panes[pane["pane_id"]] = _Pane(pane["pane_id"], pane.get("titulo") or "", True, "guardando")
        for pane in bloqueados:
            target.panes[pane["pane_id"]] = _Pane(pane["pane_id"], pane.get("titulo") or "", False, "bloqueado")

    def _descartar(self, lote: Lote) -> None:
        handle, lote.handle = lote.handle, None
        if handle is not None and hasattr(handle, "cancel"):
            handle.cancel()
        if self._lotes.get(lote.id) is lote:
            del self._lotes[lote.id]
            try:  # quien tenía el lote reservado (otro dispositivo) deja de esperar
                self.emit("guardado", {**lote.public(), "terminado": True})
            except Exception as exc:
                log.warning("emit del lote falló: %s", type(exc).__name__)

    def _registrar(self, lote: Lote) -> None:
        self._lotes[lote.id] = lote
        while len(self._lotes) > MAX_LOTES:
            viejo = next((k for k, v in self._lotes.items() if v.terminado), None)
            if viejo is None:
                break
            del self._lotes[viejo]
        lote.handle = self.call_later(self.timeout, lambda: self._vencer(lote.id))

    # ---------- pedido ----------

    async def _pedir_todo(self, lote: Lote) -> None:
        pedidos = [(t, p) for t in lote.targets.values() if t.estado == "guardando" for p in t.panes.values() if p.pedido]
        await asyncio.gather(*[self._pedir(p) for _, p in pedidos])

    async def _pedir(self, pane: _Pane) -> None:
        try:
            async with self.locks.get(pane.pane_id):
                await self.enchufe.mandar_prompt(pane.pane_id, MENSAJE)
        except TerminalesError as exc:
            log.warning("no pude confirmar el pedido de guardado a %s: %s", pane.pane_id, type(exc).__name__)
            pane.estado = "fallo"

    async def _pedir_tarde(self, lote: Lote, pane: _Pane) -> None:
        await self._pedir(pane)
        self._notificar(lote)

    # ---------- eventos del tablero ----------

    def on_board(self, previous: Optional[dict], board: dict) -> None:
        if not self._lotes:
            return
        antes, ahora = _agentes(previous), _agentes(board)
        for lote in list(self._lotes.values()):
            if lote.cancelado:
                continue
            cambio = False
            for target in lote.targets.values():
                if target.estado != "guardando":
                    continue
                for pane in target.panes.values():
                    if not pane.pedido and pane.estado == "bloqueado":
                        agent = ahora.get(pane.pane_id)
                        if agent is not None and agent.get("status") != "blocked":
                            # el usuario contestó el diálogo: se le pide guardar ahora y espera como las demás
                            pane.pedido, pane.estado, cambio = True, "guardando", True
                            self.spawn(self._pedir_tarde(lote, pane))
                        continue
                    if not pane.pedido or pane.estado == "listo":
                        continue
                    agent = ahora.get(pane.pane_id)
                    nuevo = pane.estado
                    if agent is None or _termino(antes.get(pane.pane_id), agent):
                        nuevo = "listo"
                    elif agent.get("status") == "blocked":
                        nuevo = "bloqueado"
                    elif agent.get("status") == "working" and pane.estado == "bloqueado":
                        nuevo = "guardando"
                    if nuevo != pane.estado:
                        pane.estado, cambio = nuevo, True
            if cambio:
                self._avanzar(lote)
                self._notificar(lote)

    def _avanzar(self, lote: Lote) -> None:
        if lote.cancelado:
            return
        for target in lote.targets.values():
            if target.estado == "guardando" and all(p.estado == "listo" for p in target.panes.values() if p.pedido) \
                    and not any(not p.pedido for p in target.panes.values()):
                target.estado = "cerrando"
                hubo = any(p.pedido for p in target.panes.values())
                self.spawn(self._cerrar_target(lote, target, forzar=False, guardado="ok" if hubo else "saltado", ya_marcado=True))

    # ---------- cierre ----------

    async def _cerrar_target(self, lote: Lote, target: _Target, forzar: bool, guardado: str, ya_marcado: bool = False) -> None:
        if target.estado == "cerrando" and not ya_marcado:
            return
        target.estado = "cerrando"
        self._notificar(lote)
        try:
            preview = await self.cierres.preview(PreviewBody(tipo=target.tipo, target_id=target.target_id))
            if forzar and not lote.vencido and any(p.get("kind") == "claude" and p.get("status") == "working" for p in preview["panes"]):
                target.estado = "guardando"  # retomó el trabajo por su cuenta: forzar solo vale para lo trabado
                self._notificar(lote)
                return
            if CierreService.estructura(preview) != target.estructura:
                what = "tab" if target.tipo == "tab" else "workspace"
                raise TraspasoError(409, f"El {what} cambió mientras guardaba: revisalo de nuevo")
            body = target.body.model_copy(update={"huella": preview["huella"]})
            if guardado == "ok" and any(p.estado != "listo" for p in target.panes.values()):
                guardado = "vencido"
            target.resultado = await self.cierres.execute(body, guardado=guardado, forzar=forzar, solo_unknown=target.body.forzar)
            target.guardado = guardado
            target.estado = "cerrado"
        except TraspasoError as exc:
            target.estado, target.error = "error", exc.detail[:300]
        except TerminalesError as exc:
            target.estado, target.error = "error", f"{FALLO_TERMINAL}: {exc}"[:300]
        except Exception as exc:
            log.warning("cierre guardado %s falló: %s", lote.id, type(exc).__name__)
            target.estado, target.error = "error", "Error inesperado en el servidor"
        self._notificar(lote)

    # ---------- acciones del usuario ----------

    def _vencer(self, ident: str) -> None:
        lote = self._lotes.get(ident)
        if lote is None or lote.terminado:
            return
        lote.vencido = True
        lote.handle = None
        self._notificar(lote)

    async def accion(self, ident: str, accion: str) -> dict:
        lote = self._lotes.get(ident)
        if lote is None or lote.terminado:
            raise TraspasoError(409, "Ese cierre ya terminó")
        if accion == "esperar_mas":
            if not lote.vencido:
                raise TraspasoError(409, "Todavía no venció la espera")
            lote.vencido = False
            lote.hecho.clear()
            lote.handle = self.call_later(self.timeout, lambda: self._vencer(lote.id))
            self._notificar(lote)
        elif accion == "cerrar_igual":
            if not lote.puede_cerrar_igual:
                raise TraspasoError(409, "Todavía están guardando: esperá o frená la espera")
            # Solo lo trabado: lo que sigue guardando se espera. "vencido" solo si de verdad venció la espera.
            # Sesión bloqueada o espera vencida: "vencido" (16.3); un pedido que no llegó (fallo) queda "saltado".
            trabados = [(t, "vencido" if lote.vencido or any(p.estado == "bloqueado" for p in t.panes.values()) else "saltado")
                        for t in lote.targets.values() if lote.trabado(t)]
            for target, _ in trabados:
                target.estado = "cerrando"
            for target, etiqueta in trabados:
                await self._cerrar_target(lote, target, forzar=True, guardado=etiqueta, ya_marcado=True)
        else:
            raise TraspasoError(400, "Acción inválida")
        return lote.public()

    def cancelar(self, ident: str) -> None:
        lote = self._lotes.get(ident)
        if lote is None or lote.terminado:
            return
        lote.cancelado = True
        if not lote.targets:  # reservado y todavía sin targets: nadie más lo va a cerrar
            self._descartar(lote)
            return
        for target in lote.targets.values():
            if target.estado == "guardando":
                target.estado = "cancelado"
        self._notificar(lote)

    async def esperar(self, lote: Lote) -> None:
        """Hasta que termine, venza o alguna sesión necesite al usuario (sin polling: se despierta por evento)."""
        await lote.hecho.wait()

    # ---------- aviso ----------

    def _notificar(self, lote: Lote) -> None:
        if lote.terminado or lote.vencido or lote.puede_cerrar_igual:
            lote.hecho.set()
        if lote.terminado:
            handle, lote.handle = lote.handle, None
            if handle is not None and hasattr(handle, "cancel"):
                handle.cancel()
        public = lote.public()
        if lote.listener is not None:
            try:
                lote.listener(lote)
            except Exception as exc:
                log.warning("listener del lote %s falló: %s", lote.id, type(exc).__name__)
        try:
            self.emit("guardado", public)
        except Exception as exc:
            log.warning("emit del lote falló: %s", type(exc).__name__)
