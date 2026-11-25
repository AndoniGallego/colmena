"""Comando que una sesión pide con un bloque ```comando: Colmena lo corre en modo bash de esa sesión con un toque.

El cliente solo dice qué bloque (id del mensaje + índice): el texto que corre se relee del transcript."""
import asyncio
import json
import logging
import posixpath
import re
import unicodedata
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from .cierre_dia import nombres
from .digest import LOCAL_PREFIX, is_system_text, queued_prompt
from .enchufe import TerminalesError
from .jsonl_incremental import read_new_lines
from .legado import LEGACY_FENCE
from .opciones import lenient_json
from .terminales import clean, redactar
from .telemetria import proyecto_de
from .terminales_acciones import COMANDO_LIMITS, MAX_COMMAND, validar_comando
from .traspaso import TraspasoError

log = logging.getLogger("orquestador.terminales")

MAX_BLOQUES = 20
MAX_USADOS = 500
PAUSA_BANG = 0.3
PAUSA_ENTER = 0.5
CARPETA_DISTINTA = "La carpeta pedida no es donde corre la sesión"
TRABAJANDO = "La sesión está trabajando; probá cuando termine"
YA_CORRIDO = "Ese comando ya se corrió"
NO_PREPARADO = "No pude preparar el comando en la sesión"
_REGLA = re.compile(r"^[\s│]*[─━]{10,}[\s│]*$")
_BORDE = "│┃ \t"

# Los mismos tipos de bloque que reconoce el front (segments.ts): un ```comando dentro de otro bloque no cuenta.
_ABRE = re.compile(r"(^|\n)[ \t]*(`{3,}|~{3,})[ \t]*(opciones|diagrama|pregunta|aviso|estado|pruebas|comando|%s)\b[^\n]*\n"
                   % LEGACY_FENCE, re.I)
_TIPOS = re.compile(r"(opciones|diagrama|pregunta|aviso|estado|pruebas|comando|%s)\b" % LEGACY_FENCE, re.I)
_FENCE_ABRE = re.compile(r"^( {0,3})(`{3,}|~{3,})[ \t]*(.*)$")
_FENCE_CIERRA = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*$")
_BASH_INPUT = re.compile(r"<bash-input>(.*?)</bash-input>", re.S)


class ComandoSesionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mid: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,80}$")
    indice: int = Field(..., ge=0, lt=MAX_BLOQUES)
    comando: str = Field(..., max_length=MAX_COMMAND + 100)


def puede_tener_comando(text: str) -> bool:
    return "comando" in text


def zonas_codigo(text: str) -> list:
    """Tramos [inicio, fin) de los bloques de código comunes (```, ````, ~~~ sin un tipo de tarjeta): lo que
    está adentro es un ejemplo citado. Los bloques de tarjeta se saltean enteros."""
    zonas, abierto, pos = [], None, 0
    for linea in text.split("\n"):
        inicio, pos = pos, pos + len(linea) + 1
        if abierto is None:
            m = _FENCE_ABRE.match(linea)
            if m and not (m.group(2)[0] == "`" and "`" in m.group(3)):
                abierto = (m.group(2)[0], len(m.group(2)), inicio, not _TIPOS.match(m.group(3)))
            continue
        m = _FENCE_CIERRA.match(linea)
        if m and m.group(1)[0] == abierto[0] and len(m.group(1)) >= abierto[1]:
            if abierto[3]:
                zonas.append((abierto[2], pos))
            abierto = None
    if abierto is not None and abierto[3]:
        zonas.append((abierto[2], len(text)))
    return zonas


def _sangria(linea: str) -> int:
    return len(linea.expandtabs(4)) - len(linea.expandtabs(4).lstrip(" "))


def bloques_comando(text: str) -> list:
    """Cada bloque ```comando cuyo JSON trae un `comando` de texto no vacío, válido o no: así los índices
    coinciden con las tarjetas del front aunque alguna sea inválida."""
    text = text or ""
    out = []
    pos = 0
    zonas = None
    while True:
        m = _ABRE.search(text, pos)
        if not m:
            return out
        fence, kind = m.group(2), m.group(3).lower()
        if kind == "comando":
            # Citado dentro de otro bloque de código o con sangría de código (4+ espacios): no es un pedido.
            inicio = m.start() + len(m.group(1))
            zonas = zonas_codigo(text) if zonas is None else zonas
            if _sangria(text[inicio:m.start(2)]) >= 4 or any(a <= inicio < b for a, b in zonas):
                pos = m.end() - 1
                continue
        close = re.compile(r"\n[ \t]*" + ("`" if fence[0] == "`" else "~") + "{%d,}[ \t]*(?=\n|$)" % len(fence))
        c = close.search(text, m.end() - 1)
        if kind == "comando":
            value = lenient_json(text[m.end():c.start() if c else len(text)])
            if isinstance(value, dict) and isinstance(value.get("comando"), str) and value["comando"]:
                out.append(value)
        if not c:
            return out
        pos = c.end()


def entrada_en_modo_bash(pantalla: str, comando: str) -> bool:
    """La entrada de Claude Code (entre las dos últimas reglas ─) tiene que ser `! <comando>`: el `!` como
    marca del modo bash y el comando completo, aunque se haya partido en varias líneas."""
    lineas = (pantalla or "").splitlines()
    reglas = [i for i, linea in enumerate(lineas) if _REGLA.match(linea)]
    if len(reglas) < 2:
        return False
    cuerpo = [linea.strip(_BORDE) for linea in lineas[reglas[-2] + 1:reglas[-1]]]
    cuerpo = [linea for linea in cuerpo if linea]
    if not cuerpo or not cuerpo[0].startswith("!"):
        return False
    tipeado = re.sub(r"\s+", "", cuerpo[0][1:] + "".join(cuerpo[1:]))
    return tipeado == re.sub(r"\s+", "", comando)


def cwd_de(obj: dict) -> str:
    """El cwd que Claude Code anotó en esa entrada: donde corre un `!` en ese momento."""
    cwd = obj.get("cwd")
    return cwd if isinstance(cwd, str) and cwd.startswith("/") and len(cwd) <= 500 else ""


def misma_carpeta(a: str, b: str) -> bool:
    return bool(a and b) and posixpath.normpath(a) == posixpath.normpath(b)


def mid_de(obj: dict) -> str:
    """El mismo id que transcript.py le da a cada mensaje del asistente."""
    return str(obj.get("uuid") or (obj.get("message") or {}).get("id") or obj.get("timestamp") or "")


def _textos(content) -> list:
    if not isinstance(content, list):
        return []
    return [b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text"]


def _user_text(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(_textos(content))


def _prompt_humano(obj: dict) -> bool:
    if obj.get("type") == "attachment":
        return bool(queued_prompt(obj).strip())
    if obj.get("type") != "user" or obj.get("isMeta") or obj.get("isCompactSummary"):
        return False
    text = _user_text((obj.get("message") or {}).get("content"))
    return bool(text.strip()) and not LOCAL_PREFIX.match(text) and not is_system_text(obj, text)


def _bash_inputs(obj: dict) -> list:
    if obj.get("type") != "user":
        return []
    return [m.strip() for m in _BASH_INPUT.findall(_user_text((obj.get("message") or {}).get("content")))]


def leer_pedido(path: Path, mid: str, indice: int) -> dict:
    """El bloque `indice` del mensaje `mid` ({comando validado, carpeta, cwd del mensaje}); solo si sigue vigente
    (último turno) y sin correr."""
    raw_lines, _, _ = read_new_lines(path, None, final=True)
    objs = []
    for raw in raw_lines:
        try:
            obj = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(obj, dict):
            objs.append(obj)
    pos = next((i for i, o in enumerate(objs) if o.get("type") == "assistant" and not o.get("isSidechain")
                and mid_de(o) == mid), None)
    if pos is None:
        raise TraspasoError(404, "No encontré ese pedido en la conversación")
    bloques = [b for t in _textos((objs[pos].get("message") or {}).get("content")) for b in bloques_comando(t)]
    if indice >= len(bloques):
        raise TraspasoError(404, "No encontré ese pedido en la conversación")
    comando = validar_comando(bloques[indice]["comando"])
    for obj in objs[pos + 1:]:
        if _prompt_humano(obj):
            raise TraspasoError(409, "Ese pedido quedó viejo: la conversación siguió")
        if comando in _bash_inputs(obj):
            raise TraspasoError(409, YA_CORRIDO)
    carpeta = bloques[indice].get("carpeta")
    return {"comando": comando, "carpeta": carpeta if isinstance(carpeta, str) and carpeta.strip() else None,
            "cwd": cwd_de(objs[pos])}


class ComandoSesionService:
    def __init__(self, board: Callable[[], Awaitable[Optional[dict]]], digests, enchufe, locks, audit, limit,
                 enabled: Callable[[], bool], notify=None, protected_panes: Callable[[], set] = lambda: set(),
                 sleep: Callable[[float], Awaitable] = asyncio.sleep, protected_workspaces: Optional[list] = None,
                 anotar: Callable = lambda ev, **c: None):
        self.board = board
        self.digests = digests
        self.enchufe = enchufe
        self.locks = locks
        self.audit = audit
        self.limit = limit
        self.enabled = enabled
        self.notify = notify
        self.protected_panes = protected_panes
        self.sleep = sleep
        self.anotar = anotar
        self.protected = {w.strip().casefold() for w in (protected_workspaces or []) if isinstance(w, str)}
        self._usados: OrderedDict = OrderedDict()
        self._inflight: set = set()

    def _registrar(self, ctx, sid: str, pane: str, cwd: str, comando: str, ok: bool, error: str = "") -> None:
        self.audit.write({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "accion": "comando_sesion" if ok else "rechazo",
            "ip": ctx.ip, "tailscale_user": ctx.user, "dispositivo": ctx.device[:80],
            "session_id": sid, "pane_id": pane, "cwd": clean(cwd, 200),
            "comando": redactar(comando)[:MAX_COMMAND], "ok": ok, "error": redactar(error)[:200],
        })

    def _anotar(self, info: dict, resultado: str, detail: Optional[str] = None) -> None:
        try:
            codigo = None
            if detail is not None:
                from .telemetria_eventos import codigo_traspaso  # tardío: telemetria_eventos importa este módulo
                codigo = codigo_traspaso(detail)
            self.anotar("comando_sesion", resultado=resultado, codigo=codigo, proyecto=proyecto_de(info["cwd"]))
        except Exception as exc:
            log.warning("telemetría de comando de sesión falló: %s", type(exc).__name__)

    def _usado(self, key: str) -> None:
        self._usados[key] = True
        while len(self._usados) > MAX_USADOS:
            self._usados.popitem(last=False)

    async def _ubicar(self, sid: str) -> tuple:
        try:
            board = await self.board()
        except TerminalesError as exc:
            raise TraspasoError(502, f"Las terminales no responden: {str(exc)[:150]}")
        nombre, _donde, agent, ws = nombres(board).get(sid, ("", "", None, None))
        if agent is None or agent.get("kind") != "claude" or not agent.get("pane_id"):
            raise TraspasoError(404, "Esa sesión ya no está abierta")
        if ((ws or {}).get("label") or "").strip().casefold() in self.protected:
            raise TraspasoError(400, "Esa sesión no admite comandos desde acá")
        return nombre, agent

    async def correr(self, sid: str, body: ComandoSesionBody, ctx) -> dict:
        key = f"{sid}:{body.mid}:{body.indice}"
        info = {"pane": "", "cwd": "", "comando": "", "tocado": False, "nombre": ""}
        try:
            result = await self._correr(sid, body, key, info)
        except TraspasoError as exc:
            if info["tocado"]:
                self._usado(key)
            self._registrar(ctx, sid, info["pane"], info["cwd"], info["comando"], False, exc.detail)
            self._anotar(info, "fallo", exc.detail)
            raise
        self._registrar(ctx, sid, info["pane"], info["cwd"], info["comando"], True)
        self._anotar(info, "corrido")
        await self._avisar(info, ctx)
        return result

    async def _correr(self, sid: str, body: ComandoSesionBody, key: str, info: dict) -> dict:
        if not self.enabled():
            raise TraspasoError(403, "escritura apagada")
        wait = self.limit.hit("comando_sesion", *COMANDO_LIMITS)
        if wait:
            raise TraspasoError(429, "demasiadas acciones seguidas", {"retry_after": wait})
        if key in self._usados or key in self._inflight:
            raise TraspasoError(409, YA_CORRIDO)
        # Sincrónico, antes de cualquier await: un doble toque (PC y celu) no pasa los dos este chequeo.
        self._inflight.add(key)
        try:
            pane = (await self._verificar(sid, body, info))["pane_id"]
            async with self.locks.get(pane):
                # Lo que pudo cambiar mientras se esperaba: otro toque, un `!` ya corrido o la sesión ocupada.
                if key in self._usados:
                    raise TraspasoError(409, YA_CORRIDO)
                if (await self._verificar(sid, body, info))["pane_id"] != pane:
                    raise TraspasoError(409, "La sesión cambió de lugar: probá de nuevo")
                await self._escribir(pane, info["comando"], info)
            self._usado(key)
        finally:
            self._inflight.discard(key)
        return {"ok": True, "comando": info["comando"], "cwd": posixpath.normpath(info["cwd"]) if info["cwd"] else ""}

    async def _verificar(self, sid: str, body: ComandoSesionBody, info: dict) -> dict:
        path = self.digests.find(sid)
        if path is None:
            raise TraspasoError(404, "No encontré la conversación de esa sesión")
        pedido = await asyncio.to_thread(leer_pedido, path, body.mid, body.indice)
        comando = info["comando"] = pedido["comando"]
        if unicodedata.normalize("NFC", body.comando) != comando:
            raise TraspasoError(409, "El comando cambió: recargá la conversación")
        nombre, agent = await self._ubicar(sid)
        pane = agent["pane_id"]
        info.update(pane=pane, cwd=pedido["cwd"] or agent.get("cwd") or "", nombre=nombre)
        if pane in self.protected_panes():
            raise TraspasoError(400, "Esa sesión no admite comandos desde acá")
        if pedido["carpeta"] is not None and not misma_carpeta(pedido["carpeta"].strip(), info["cwd"]):
            raise TraspasoError(400, CARPETA_DISTINTA)
        estado = agent.get("status")
        if estado == "working":
            raise TraspasoError(409, TRABAJANDO)
        if estado == "blocked":
            raise TraspasoError(409, "La sesión espera una aprobación tuya en la terminal")
        if estado not in ("idle", "done"):
            raise TraspasoError(409, "La sesión no está lista para recibir un comando")
        return agent

    async def _escribir(self, pane: str, comando: str, info: dict) -> None:
        try:
            info["tocado"] = True
            await self.enchufe.teclas(pane, ("ctrl-e", "ctrl-u"))
            await self.enchufe.escribir(pane, "!")
            await self.sleep(PAUSA_BANG)
            await self.enchufe.escribir(pane, comando)
            await self.sleep(PAUSA_ENTER)
            # Una sola captura, sin reintentos: si la entrada no quedó en modo bash con el comando, se borra.
            try:
                pantalla = await self.enchufe.leer(pane, fuente="visible")
            except (TerminalesError, OSError):
                pantalla = ""
            if not entrada_en_modo_bash(pantalla, comando):
                await self.enchufe.teclas(pane, ("ctrl-u",))
                info["tocado"] = False
                raise TraspasoError(409, NO_PREPARADO)
            await self.enchufe.teclas(pane, ("enter",))
        except (TerminalesError, OSError) as exc:
            raise TraspasoError(502, f"Las terminales no respondieron: {str(exc)[:150]}")

    async def _avisar(self, info: dict, ctx) -> None:
        if self.notify is None:
            return
        try:
            await self.notify(f"Comando en {info['nombre'] or 'una sesión'}",
                              f"{redactar(info['comando'])[:80]} · {ctx.device}".strip(" ·"),
                              "terminal-comando-sesion", info["pane"])
        except Exception as exc:
            log.warning("aviso de comando de sesión falló: %s", type(exc).__name__)
