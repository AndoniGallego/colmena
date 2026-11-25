import asyncio
import collections
import copy
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field

from .enchufe.ids import es_guardian
from .ganchos.ajustes import FUENTES
from .ganchos.mensaje import Ids, MensajeGancho
from .digest import estados_todos_validos, quitar_estado
from .opciones import analizar
from .redaccion import redactar

log = logging.getLogger(__name__)

_PRIORIDAD_ESTADO = {"blocked": 4, "working": 3, "done": 2, "idle": 1, "unknown": 0}

_MAX_ULTIMO_MENSAJE = 500
_MAX_IGNORADOS = 200
_MAX_SIN_DUENO = 200
# Un Stop sin bloque ```estado``` en una terminal de Colmena puede ser el que frena el hook de andokit
# (Claude sigue escribiendo el estado): se espera este tiempo antes de dar por terminado el turno.
ESPERA_RESUMEN_S = 20
_ACTIVIDAD = frozenset({"SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest"})


@dataclass
class RegistroSesion:
    pane_id: str
    session_id: str | None
    estado: str
    usando: str | None
    ultimo_mensaje: str | None
    ultimo_evento: float
    pre_desde: float
    pr_desde: float | None
    stop_en: float | None
    herramientas_en_turno: bool = False
    herramientas_previas_stop: set[str] = field(default_factory=set)


def _agentes(board: dict):
    for ws in board.get("workspaces", []):
        for tab in ws.get("tabs", []):
            yield from tab.get("agents", [])


def _pane_ids(board: dict) -> set[str]:
    return {a["pane_id"] for a in _agentes(board) if a.get("pane_id")}


def dueno_de(ids: Ids, board: dict | None) -> str | None:
    if ids.colmena and es_guardian(ids.colmena):
        return ids.colmena
    if board is None:
        return None
    panes = _pane_ids(board)
    if ids.colmena and ids.colmena in panes:
        return ids.colmena
    if ids.herdr_pane and ids.herdr_pane in panes:
        return ids.herdr_pane
    if ids.claude:
        for agent in _agentes(board):
            if agent.get("session_id") == ids.claude:
                return agent.get("pane_id")
    return None


class EstadoSesiones:
    def __init__(
        self,
        clock=time.monotonic,
        wall_clock=time.time,
        ventana: float = 1.0,
        max_vistos: int = 4096,
        programar: Callable | None = None,
        espera_resumen: float = ESPERA_RESUMEN_S,
        hook_instalado: Callable[[], bool] | None = None,
    ):
        self._hook_instalado = hook_instalado
        self._clock = clock
        self._programar = programar
        self._espera_resumen = espera_resumen
        self.al_cierre_diferido: Callable[[], None] | None = None
        self._esperas: dict[str, tuple[object, MensajeGancho]] = {}
        self._wall_clock = wall_clock
        self._ventana = ventana
        self._max_vistos = max_vistos
        self._vistos: OrderedDict[tuple, float] = OrderedDict()
        self._registros: dict[str, RegistroSesion] = {}
        self._pre_pendientes: dict[str, set[str]] = {}
        self.sin_dueno: collections.deque[dict] = collections.deque(maxlen=_MAX_SIN_DUENO)
        self.ignorados: collections.deque[str] = collections.deque(maxlen=_MAX_IGNORADOS)
        self.observadores: list[Callable[[str, str], None]] = []
        self.al_stop: list[Callable[[str, str], None]] = []

    def vistos_count(self) -> int:
        return len(self._vistos)

    def estado_de(self, pane_id: str) -> RegistroSesion | None:
        return self._registros.get(pane_id)

    def _clave_dedup(self, msg: MensajeGancho, pane_id: str | None) -> tuple:
        sid = msg.ids.claude
        if sid:
            scope = sid
        else:
            scope = pane_id or msg.ids.herdr_pane or msg.ids.colmena or ""
        tid = msg.tool_use_id
        if tid is not None:
            return (scope, msg.evento, tid)
        extra = None
        if msg.evento == "Notification":
            nt = msg.datos.get("notification_type")
            if isinstance(nt, str):
                extra = nt
        return (scope, msg.evento, None, extra)

    def _registrar_visto(self, msg: MensajeGancho, pane_id: str | None) -> bool:
        key = self._clave_dedup(msg, pane_id)
        tid = msg.tool_use_id
        ahora = self._clock()
        if tid is not None:
            if key in self._vistos:
                return False
            self._vistos[key] = ahora
        else:
            prev = self._vistos.get(key)
            if prev is not None and (ahora - prev) < self._ventana:
                return False
            self._vistos[key] = ahora
        while len(self._vistos) > self._max_vistos:
            self._vistos.popitem(last=False)
        return True

    def _obtener_o_crear(self, pane_id: str, msg: MensajeGancho) -> RegistroSesion:
        reg = self._registros.get(pane_id)
        if reg is None:
            ahora = self._clock()
            reg = RegistroSesion(
                pane_id=pane_id,
                session_id=msg.ids.claude,
                estado="idle",
                usando=None,
                ultimo_mensaje=None,
                ultimo_evento=ahora,
                pre_desde=ahora,
                pr_desde=None,
                stop_en=None,
            )
            self._registros[pane_id] = reg
        elif msg.ids.claude:
            reg.session_id = msg.ids.claude
        return reg

    def recibir(self, msg: MensajeGancho, pane_id: str | None) -> bool:
        if not self._registrar_visto(msg, pane_id):
            return False

        ahora = self._clock()

        if pane_id is None:
            self.sin_dueno.append(
                {
                    "evento": msg.evento,
                    "claude": msg.ids.claude,
                    "hora": self._wall_clock(),
                }
            )
            return True

        notif = msg.datos.get("notification_type") if msg.evento == "Notification" else None
        if notif == "idle_prompt":
            self.ignorados.append("idle_prompt")
            if pane_id not in self._registros:
                return True
            reg = self._registros[pane_id]
            reg.ultimo_evento = ahora
            return True

        reg = self._obtener_o_crear(pane_id, msg)
        reg.ultimo_evento = ahora

        evento = msg.evento
        if evento in _ACTIVIDAD:
            self._cancelar_espera(pane_id)
        if evento == "SessionStart":
            reg.estado = "idle"
        elif evento == "UserPromptSubmit":
            reg.estado = "working"
            reg.herramientas_previas_stop.clear()
            reg.herramientas_en_turno = False
            self._pre_pendientes.pop(pane_id, None)
        elif evento == "PreToolUse":
            reg.estado = "working"
            reg.herramientas_en_turno = True
            reg.pre_desde = ahora
            reg.usando = msg.herramienta
            tid = msg.tool_use_id
            if tid:
                self._pre_pendientes.setdefault(pane_id, set()).add(tid)
        elif evento in ("PostToolUse", "PostToolUseFailure"):
            tid = msg.tool_use_id
            pend = self._pre_pendientes.get(pane_id)
            if pend and tid:
                pend.discard(tid)
            mantener_estado = (reg.estado == "done" and not tid) or (
                bool(tid) and tid in reg.herramientas_previas_stop
            )
            if not mantener_estado:
                reg.estado = "working"
        elif evento == "PermissionRequest":
            reg.estado = "blocked"
            reg.pr_desde = ahora
        elif evento == "Notification" and notif == "permission_prompt":
            if reg.estado != "done":
                pend = self._pre_pendientes.get(pane_id) or set()
                if pend and (reg.pr_desde is None or reg.pr_desde < reg.pre_desde):
                    reg.estado = "blocked"
        elif evento == "Stop":
            self._llamar_al_stop(pane_id, msg)
            previa = self._esperas.pop(pane_id, None)
            if previa is not None:
                previa[0].cancel()
            elif self._debe_esperar(reg, pane_id, msg):
                if self._esperar(pane_id, msg):
                    return True
            self._aplicar_stop(reg, pane_id, msg, ahora)

        self._avisar(pane_id, evento)
        return True

    def _llamar_al_stop(self, pane_id: str, msg: MensajeGancho) -> None:
        crudo = msg.datos.get("last_assistant_message")
        if not isinstance(crudo, str):
            return
        for cb in list(self.al_stop):
            try:
                cb(pane_id, crudo)
            except Exception:
                log.exception("al_stop falló")

    def _aplicar_stop(self, reg: RegistroSesion, pane_id: str, msg: MensajeGancho, ahora: float) -> None:
        reg.estado = "done"
        reg.stop_en = ahora
        crudo = msg.datos.get("last_assistant_message")
        if isinstance(crudo, str):
            reg.ultimo_mensaje = redactar(crudo)[:_MAX_ULTIMO_MENSAJE]
        else:
            reg.ultimo_mensaje = None
        reg.herramientas_previas_stop = set(self._pre_pendientes.get(pane_id, ()))
        self._pre_pendientes.pop(pane_id, None)

    def _debe_esperar(self, reg: RegistroSesion, pane_id: str, msg: MensajeGancho) -> bool:
        if not es_guardian(pane_id) or reg.estado != "working" or not reg.herramientas_en_turno:
            return False
        if self._hook_instalado is None or not self._hook_instalado():
            return False
        crudo = msg.datos.get("last_assistant_message")
        if not isinstance(crudo, str) or estados_todos_validos(crudo):
            return False
        # Una pregunta a Ando no se demora: el aviso tiene que salir ya.
        _, termina = analizar(quitar_estado(crudo))
        return not (quitar_estado(crudo).strip().endswith("?") or termina)

    def _esperar(self, pane_id: str, msg: MensajeGancho) -> bool:
        programar = self._programar
        if programar is None:
            try:
                programar = asyncio.get_running_loop().call_later
            except RuntimeError:
                return False
        handle = None

        def vencio() -> None:
            actual = self._esperas.get(pane_id)
            if actual is None or actual[0] is not handle:
                return
            del self._esperas[pane_id]
            try:
                reg = self._registros.get(pane_id)
                if reg is None:
                    return
                self._aplicar_stop(reg, pane_id, msg, self._clock())
                self._avisar(pane_id, "Stop")
                if self.al_cierre_diferido is not None:
                    self.al_cierre_diferido()
            except Exception:
                log.exception("fin de turno diferido falló")

        handle = programar(self._espera_resumen, vencio)
        self._esperas[pane_id] = (handle, msg)
        return True

    def _cancelar_espera(self, pane_id: str) -> None:
        previa = self._esperas.pop(pane_id, None)
        if previa is not None:
            previa[0].cancel()

    def _avisar(self, pane_id: str, evento: str) -> None:
        for obs in self.observadores:
            try:
                obs(pane_id, evento)
            except Exception:
                log.exception("observador de estado falló")

    def marcar_visto(self, session_id: str) -> bool:
        cambio = False
        for reg in self._registros.values():
            if reg.session_id == session_id and reg.estado == "done":
                reg.estado = "idle"
                cambio = True
        return cambio


def estados_por_pane(estados: EstadoSesiones) -> dict[str, RegistroSesion]:
    return dict(estados._registros)


def _estado_workspace(statuses: list[str]) -> str:
    if not statuses:
        return "unknown"
    return max(statuses, key=lambda s: _PRIORIDAD_ESTADO.get(s, 0))


def _aplicar_ganchos_guardian(out: dict, por_pane: dict[str, RegistroSesion]) -> None:
    tocado = False
    for agent in _agentes(out):
        pane_id = agent.get("pane_id")
        if not pane_id or not es_guardian(pane_id):
            continue
        reg = por_pane.get(pane_id)
        if reg is None:
            continue
        if agent.get("status") == "blocked" and reg.estado == "idle":
            continue
        agent["status"] = reg.estado
        if reg.usando is not None:
            agent["usando"] = reg.usando
        else:
            agent.pop("usando", None)
        tocado = True
    if not tocado:
        return
    for ws in out.get("workspaces", []):
        statuses = []
        for tab in ws.get("tabs", []):
            for agent in tab.get("agents", []):
                statuses.append(agent.get("status") or "unknown")
        if statuses:
            ws["status"] = _estado_workspace(statuses)


def aplicar_fuente(board: dict, estados: EstadoSesiones | None, fuente: str) -> dict:
    if fuente not in FUENTES:
        fuente = "herdr"
    out = copy.deepcopy(board)
    por_pane = estados_por_pane(estados) if estados else {}

    if fuente == "herdr":
        _aplicar_ganchos_guardian(out, por_pane)
        return out

    for agent in _agentes(out):
        herdr = agent.get("status")
        agent["status_herdr"] = herdr
        pane_id = agent.get("pane_id")
        reg = por_pane.get(pane_id) if pane_id else None
        if reg is not None:
            agent["status"] = reg.estado
            if reg.usando is not None:
                agent["usando"] = reg.usando

    for ws in out.get("workspaces", []):
        statuses = []
        for tab in ws.get("tabs", []):
            for agent in tab.get("agents", []):
                statuses.append(agent.get("status") or "unknown")
        if statuses:
            ws["status"] = _estado_workspace(statuses)

    return out
