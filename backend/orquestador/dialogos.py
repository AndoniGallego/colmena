import asyncio
import logging
import time
from collections import deque
from typing import Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .dialogo import ALLOWED_KEYS, MAX_OPCIONES, TESTED_VERSION, Dialogo, campo_abierto, estado_pregunta, huella, norm, parse_dialog, screen_tail, visibles
from .digest import SESSION_ID
from .enchufe import TerminalesError, como_snapshot
from .locks import PaneLocks
from .mensaje import TEXT_CONTROL_RE
from .traspaso import CONTROL_RE, FALLO_TERMINAL, ID_RE, TraspasoError, _need_id, _now

MAX_OTRO = 500
RATE_LIMIT = 20
RATE_WINDOW = 60.0
STEP_DELAYS = (0.15, 0.25, 0.6)
FINAL_WAIT = 3.0
log = logging.getLogger(__name__)

PUSH_TEXTS = {"Bash": "Quiere correr un comando", "Write": "Quiere editar un archivo",
              "Edit": "Quiere editar un archivo", "AskUserQuestion": "Te hace una pregunta"}
PIN_CHOICES = frozenset({"si_siempre", "si_auto", "si_ediciones"})
HALF_DONE = "Quedó a medio responder: terminá en la terminal"


class RespuestaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opciones: list[StrictInt] = Field(default_factory=list, max_length=20)
    otro: Optional[str] = Field(None, max_length=2000)


class RespuestaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    session_id: str = Field(..., max_length=100)
    pane_id: str = Field(..., max_length=64)
    huella: str = Field(..., max_length=128)
    tipo: Literal["permiso", "pregunta"]
    permiso: Optional[Literal["si", "si_siempre", "si_auto", "si_ediciones", "no"]] = None
    pin: Optional[str] = Field(None, max_length=128)
    respuestas: Optional[list[RespuestaItem]] = Field(None, max_length=10)


def _is(state: Optional[dict], kind: str, **fields) -> bool:
    return bool(state) and state["kind"] == kind and all(state.get(k) == v for k, v in fields.items())


def _session_of(agent: dict) -> Optional[str]:
    session = agent.get("agent_session") or {}
    return session.get("value") if session.get("kind") == "id" else None


def prepare_otro(raw: str) -> str:
    text = raw.replace("\r\n", "\n").strip()
    if not 1 <= len(text) <= MAX_OTRO:
        raise TraspasoError(400, f"La respuesta debe tener entre 1 y {MAX_OTRO} caracteres")
    if "\n" in text or "\t" in text or TEXT_CONTROL_RE.search(text):
        raise TraspasoError(400, "La respuesta tiene caracteres no permitidos")
    return f" {text}" if text.startswith("-") else text


def _visibles_pregunta(pregunta: dict) -> dict:
    return {"preguntas": [{**q, "header": visibles(q["header"]), "texto": visibles(q["texto"]),
                           "opciones": [{"label": visibles(o["label"]), "descripcion": visibles(o["descripcion"])}
                                        for o in q["opciones"]]} for q in pregunta["preguntas"]]}


class DialogService:
    def __init__(self, enchufe, state, locks: PaneLocks, transcripts, protected_panes: Callable[[], set],
                 limiter, pin_hash: str, verify: Callable[[str, str], bool], refresh: Optional[Callable] = None,
                 sleep: Callable = asyncio.sleep, clock: Callable[[], float] = time.monotonic):
        self.enchufe = enchufe
        self.state = state
        self.locks = locks
        self.transcripts = transcripts
        self.protected_panes = protected_panes
        self.limiter = limiter
        self.pin_hash = pin_hash
        self.verify = verify
        self.refresh = refresh
        self.sleep = sleep
        self.clock = clock
        self._inflight: set = set()
        self._recent: deque = deque()
        self.permisos = None

    async def verificar_pin(self, pin: str | None, ip: str) -> None:
        async with self.limiter.gate:
            wait = self.limiter.retry_after(ip)
            if wait:
                raise TraspasoError(429, "Demasiados intentos", {"retry_after": wait})
            if not await asyncio.to_thread(self.verify, pin or "", self.pin_hash):
                self.limiter.fail(ip)
                log.warning("PIN incorrecto al confirmar un permiso duradero desde %s", ip)
                raise TraspasoError(401, "PIN incorrecto")
            self.limiter.ok(ip)

    async def _snapshot(self) -> dict:
        try:
            return como_snapshot(await self.enchufe.tablero())
        except TerminalesError as exc:
            raise TraspasoError(502, f"Las terminales no responden: {exc}")

    async def _agent_by(self, *, session_id: Optional[str] = None, pane_id: Optional[str] = None) -> Optional[dict]:
        for agent in (await self._snapshot()).get("agents", []):
            if pane_id is not None and agent.get("pane_id") != pane_id:
                continue
            if session_id is not None and _session_of(agent) != session_id:
                continue
            return agent
        return None

    async def _read(self, pane: str) -> str:
        try:
            return await self.enchufe.leer(pane, fuente="deteccion", lineas=60, formato="texto")
        except TerminalesError as exc:
            raise TraspasoError(502, f"{FALLO_TERMINAL}: {exc}")

    async def _inspect(self, agent: dict) -> tuple:
        """(diálogo, huella o None, pantalla). Nunca falla por un formato raro: eso es `desconocido`."""
        pane, session = agent["pane_id"], _session_of(agent)
        screen = await self._read(pane)
        if not session:
            return Dialogo(razon="sin session_id"), None, screen
        info = await asyncio.to_thread(self.transcripts.pending, session)
        if not info:
            return Dialogo(razon="transcript ilegible"), None, screen
        version = info.get("version")
        if version and version != TESTED_VERSION:
            log.warning("Claude Code %s: las fixtures son de %s", version, TESTED_VERSION)
        dialogo = parse_dialog(screen, info["pendientes"], agent.get("cwd") or "")
        if dialogo.tipo == "desconocido":
            log.info("diálogo no reconocido en %s: %s (Claude Code %s)", pane, dialogo.razon, version)
            return dialogo, None, screen
        return dialogo, huella(pane, session, agent.get("state_change_seq"), dialogo), screen

    @staticmethod
    def _payload(dialogo: Dialogo, hu: str, pane: str) -> dict:
        if dialogo.tipo == "pregunta":
            return {"tipo": "pregunta", "huella": hu, "pane_id": pane, "pregunta": _visibles_pregunta(dialogo.pregunta)}
        permiso = {"herramienta": dialogo.herramienta, "detalle": visibles(dialogo.detalle), "descripcion": visibles(dialogo.descripcion),
                   "completo": dialogo.completo, "opciones": dialogo.opciones,
                   "regla": visibles(dialogo.regla) if dialogo.regla else dialogo.regla,
                   "mas_en_terminal": dialogo.mas_en_terminal}
        if dialogo.herramienta != "Bash":
            permiso["archivo"] = visibles(dialogo.archivo)
        if dialogo.herramienta == "Edit":
            permiso["replace_all"] = dialogo.replace_all
        return {"tipo": "permiso", "huella": hu, "pane_id": pane, "permiso": permiso}

    async def read(self, session_id: str) -> dict:
        agent = await self._agent_by(session_id=session_id)
        if agent is None or agent.get("pane_id") in self.protected_panes():
            raise TraspasoError(404, "Esa sesión ya no está abierta")
        if self.permisos is not None:
            pedido = self.permisos.abierto_para(session_id)
            if pedido is not None:
                return {"tipo": "pedido", "pedido": pedido.publico()}
        if agent.get("agent_status") != "blocked":
            return {"tipo": "ninguno"}
        dialogo, hu, screen = await self._inspect(agent)
        if hu is None:
            return {"tipo": "desconocido", "pane_id": agent["pane_id"], "pantalla": screen_tail(screen)}
        return self._payload(dialogo, hu, agent["pane_id"])

    async def push_text(self, session_id: str) -> Optional[str]:
        """Cuerpo genérico para el aviso de push, sin el comando ni la ruta; None si no se reconoce."""
        try:
            agent = await self._agent_by(session_id=session_id) if session_id else None
            if agent is None or agent.get("agent_status") != "blocked" or agent.get("pane_id") in self.protected_panes():
                return None
            dialogo, hu, _ = await self._inspect(agent)
            return PUSH_TEXTS.get(dialogo.herramienta) if hu else None
        except Exception as exc:
            log.warning("no pude clasificar el diálogo para el aviso: %s", type(exc).__name__)
            return None

    def _already_done(self, ident: str) -> bool:
        return any(r.get("id") == ident and r.get("ok") for r in self.state.respuestas())

    def _shape(self, body: RespuestaBody) -> Optional[str]:
        if body.tipo == "permiso":
            if body.permiso is None or body.respuestas is not None:
                raise TraspasoError(400, "cuerpo inválido")
            if body.permiso in PIN_CHOICES:
                if not body.pin:
                    raise TraspasoError(400, "Falta el PIN")
            elif body.pin is not None:
                raise TraspasoError(400, "Ese permiso no lleva PIN")
            return None
        if body.permiso is not None or body.pin is not None or not body.respuestas:
            raise TraspasoError(400, "cuerpo inválido")
        if len(body.respuestas) > 4:
            raise TraspasoError(400, "cuerpo inválido")
        otro = None
        for item in body.respuestas:
            if item.otro is not None:
                if len(body.respuestas) != 1 or item.opciones:
                    raise TraspasoError(400, "cuerpo inválido")
                otro = prepare_otro(item.otro)
        return otro

    async def _check_pin(self, body: RespuestaBody, ip: str) -> None:
        await self.verificar_pin(body.pin, ip)

    def _rate_limit(self) -> None:
        now = self.clock()
        while self._recent and now - self._recent[0] > RATE_WINDOW:
            self._recent.popleft()
        if len(self._recent) >= RATE_LIMIT:
            raise TraspasoError(429, "Demasiadas respuestas seguidas: esperá un minuto")
        self._recent.append(now)

    async def answer(self, body: RespuestaBody, ip: str) -> dict:
        if body.id in self._inflight or self._already_done(body.id):
            raise TraspasoError(409, "Ya se respondió")
        pane = _need_id(body.pane_id, "pane_id")
        if pane in self.protected_panes():
            raise TraspasoError(400, "No se le puede responder al orquestador")
        if not SESSION_ID.match(body.session_id):
            raise TraspasoError(400, "session_id inválido")
        self._inflight.add(body.id)
        try:
            otro = self._shape(body)
            if body.permiso in PIN_CHOICES:
                await self._check_pin(body, ip)
            self._rate_limit()
            async with self.locks.get(pane):
                if self.permisos is not None and self.permisos.abierto_para(body.session_id) is not None:
                    raise TraspasoError(409, "lo está contestando la app")
                return await self._answer_locked(body, pane, otro)
        finally:
            self._inflight.discard(body.id)

    async def _answer_locked(self, body: RespuestaBody, pane: str, otro: Optional[str]) -> dict:
        agent = await self._agent_by(pane_id=pane)
        if agent is None or _session_of(agent) != body.session_id:
            raise TraspasoError(404, "Esa sesión ya no está abierta")
        if agent.get("agent_status") != "blocked":
            raise TraspasoError(409, "La sesión ya no espera respuesta")
        seq = agent.get("state_change_seq")
        dialogo, hu, _ = await self._inspect(agent)
        if hu is None:
            raise TraspasoError(409, "No reconozco este diálogo: respondé en la terminal")
        if hu != body.huella or dialogo.tipo != body.tipo:
            raise TraspasoError(409, "El diálogo cambió")
        if self.state.teclas_enviadas(pane, dialogo.tool_use_id):
            raise TraspasoError(409, "Ya se mandó una respuesta: mirá la terminal")
        if dialogo.tipo == "permiso":
            return await self._answer_permiso(body, pane, seq, dialogo)
        return await self._answer_pregunta(body, pane, seq, dialogo, otro)

    @staticmethod
    def _digit(number) -> str:
        key = str(number)
        if key not in ALLOWED_KEYS or key in ("derecha", "enter"):
            raise TraspasoError(409, "Esa opción no está disponible: respondé en la terminal")
        return key

    async def _answer_permiso(self, body: RespuestaBody, pane: str, seq, dialogo: Dialogo) -> dict:
        choice = body.permiso
        if choice not in dialogo.opciones:
            raise TraspasoError(409, "Esa opción no está disponible: respondé en la terminal")
        if choice != "no" and not dialogo.completo:
            raise TraspasoError(409, "Revisalo en la terminal")
        kind = {"si": "yes", "si_siempre": "yes_dont_ask", "si_auto": "mode_auto", "si_ediciones": "mode_edits",
                "no": "no"}[choice]
        digit = self._digit(dialogo.digitos[kind])
        label = {"si": "Sí", "si_siempre": "Sí, y no volver a preguntar", "si_auto": "Sí y modo automático",
                 "si_ediciones": "Sí y aceptar ediciones", "no": "No"}[choice]
        resumen = f"Permiso {dialogo.herramienta}: {label} ({self._brief(dialogo)})"
        await self._run_steps(body, pane, seq, dialogo, resumen, [("keys", [digit], None)])
        return await self._done(body, pane, resumen, interrumpida=choice == "no")

    async def _answer_pregunta(self, body: RespuestaBody, pane: str, seq, dialogo: Dialogo, otro: Optional[str]) -> dict:
        preguntas = dialogo.pregunta["preguntas"]
        if len(body.respuestas) != len(preguntas):
            raise TraspasoError(400, "Tiene que haber una respuesta por pregunta")
        if otro is not None:
            if len(preguntas) != 1 or preguntas[0]["multi"]:
                raise TraspasoError(400, "Esta pregunta no admite otra respuesta desde la app")
            resumen = f"Pregunta: otra respuesta ({otro.strip()[:80]})"
            steps = [("keys", [self._digit(dialogo.digitos["type_something"])],
                      lambda s: campo_abierto(s, dialogo) == "Type something."),
                     ("text", otro, lambda s: campo_abierto(s, dialogo) == norm(otro)),
                     ("keys", ["enter"], None)]
        else:
            chosen = [self._chosen(q, item) for q, item in zip(preguntas, body.respuestas)]
            resumen, steps = self._plan(dialogo, chosen)
        await self._run_steps(body, pane, seq, dialogo, resumen, steps)
        return await self._done(body, pane, resumen, interrumpida=False)

    @staticmethod
    def _chosen(question: dict, item: RespuestaItem) -> list:
        picks, total = item.opciones, len(question["opciones"])
        if item.otro is not None or not picks or len(set(picks)) != len(picks) or len(picks) > MAX_OPCIONES \
                or not all(0 <= p < total for p in picks):
            raise TraspasoError(400, "Opción fuera de rango")
        if not question["multi"] and len(picks) != 1:
            raise TraspasoError(400, "Esa pregunta admite una sola opción")
        return sorted(picks)

    def _plan(self, dialogo: Dialogo, chosen: list) -> tuple:
        """Pasos de teclas de todo el cuestionario; cada uno trae lo que la pantalla tiene que mostrar después."""
        preguntas = dialogo.pregunta["preguntas"]
        labels = [[o["label"] for o in q["opciones"]] for q in preguntas]
        texts = [[labels[i][k] for k in picks] for i, picks in enumerate(chosen)]
        resumen = "Pregunta: " + " | ".join(", ".join(t) for t in texts)
        if len(preguntas) == 1 and not preguntas[0]["multi"]:
            return resumen, [("keys", [self._digit(chosen[0][0] + 1)], None)]
        pares = [(norm(q["texto"]), norm(", ".join(t))) for q, t in zip(preguntas, texts)]
        last = len(preguntas) - 1

        def after(i):
            if i < last:
                return lambda s: _is(estado_pregunta(s, dialogo), "pestania", i=i + 1, casillas=frozenset())
            return lambda s: _is(estado_pregunta(s, dialogo), "revision", pares=pares)

        steps: list = []
        for i, picks in enumerate(chosen):
            digits = [self._digit(k + 1) for k in picks]
            if preguntas[i]["multi"]:
                steps.append(("keys", digits, lambda s, i=i, c=frozenset(picks): _is(
                    estado_pregunta(s, dialogo), "pestania", i=i, casillas=c)))
                steps.append(("keys", ["derecha"], after(i)))
            else:
                steps.append(("keys", digits, after(i)))
        steps.append(("keys", ["1"], None))
        return resumen, steps

    @staticmethod
    def _brief(dialogo: Dialogo) -> str:
        head = dialogo.detalle if dialogo.herramienta == "Bash" else dialogo.archivo
        return CONTROL_RE.sub(" ", head)[:60]

    async def _send_keys(self, pane: str, keys: list) -> None:
        if not keys or any(k not in ALLOWED_KEYS for k in keys):
            raise TraspasoError(409, "Tecla no permitida")
        await self.enchufe.teclas(pane, keys)

    async def _run_steps(self, body: RespuestaBody, pane: str, seq, dialogo: Dialogo, resumen: str, steps: list) -> None:
        try:
            self.state.add_tecla(pane, dialogo.tool_use_id)
            for index, (kind, value, expected) in enumerate(steps):
                last = index == len(steps) - 1
                if index:
                    await self._same_state(pane, body.session_id, seq)
                if kind == "keys":
                    await self._send_keys(pane, value)
                else:
                    await self.enchufe.escribir(pane, value)
                if last:
                    await self._confirm_final(pane, body.session_id, dialogo.tool_use_id)
                else:
                    await self._expect(pane, expected)
        except TerminalesError as exc:
            self._record(body, pane, resumen, ok=False, error=str(exc)[:300])
            raise TraspasoError(502, f"{FALLO_TERMINAL}: {exc}")
        except TraspasoError as exc:
            if exc.status >= 500:
                self._record(body, pane, resumen, ok=False, error=exc.detail)
            raise

    async def _same_state(self, pane: str, session_id: str, seq) -> None:
        agent = await self._agent_by(pane_id=pane)
        if agent is None or _session_of(agent) != session_id or agent.get("agent_status") != "blocked" \
                or agent.get("state_change_seq") != seq:
            raise TraspasoError(502, HALF_DONE)

    async def _expect(self, pane: str, predicate: Callable[[str], bool]) -> None:
        for delay in STEP_DELAYS:
            await self.sleep(delay)
            if predicate(await self._read(pane)):
                return
        raise TraspasoError(502, HALF_DONE)

    async def _confirm_final(self, pane: str, session_id: str, tool_use_id: str) -> None:
        try:
            await self.enchufe.esperar(pane, frozenset({"working", "idle", "done"}), FINAL_WAIT)
        except TerminalesError:
            pass
        agent = await self._agent_by(pane_id=pane)
        failure = TraspasoError(502, "No se confirmó la respuesta: mirá la terminal")
        if agent is None or _session_of(agent) != session_id:
            raise failure
        if agent.get("agent_status") != "blocked":
            return
        dialogo, hu, _ = await self._inspect(agent)
        if hu is not None and dialogo.tool_use_id != tool_use_id:
            return
        raise failure

    def _record(self, body: RespuestaBody, pane: str, resumen: str, ok: bool, error: str = "",
                interrumpida: bool = False) -> None:
        entry = {"id": body.id, "pane_id": pane, "session_id": body.session_id, "tipo": body.tipo,
                 "resumen": CONTROL_RE.sub(" ", resumen)[:200], "ts": _now(), "ok": ok, "interrumpida": interrumpida}
        if error:
            entry["error"] = error
        self.state.add_respuesta(entry)

    async def _done(self, body: RespuestaBody, pane: str, resumen: str, interrumpida: bool) -> dict:
        self._record(body, pane, resumen, ok=True, interrumpida=interrumpida)
        log.info("respondido %s: %s", pane, CONTROL_RE.sub(" ", resumen)[:200])
        if self.refresh:
            await self._refresh()
        return {"ok": True, "interrumpida": interrumpida}

    async def _refresh(self) -> None:
        try:
            await self.refresh()
        except Exception as exc:
            log.warning("refresh tras responder falló: %s", type(exc).__name__)
