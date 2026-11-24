import asyncio
import contextlib
import json
import logging
import os
import shutil
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Optional

from .base import (
    TECLAS,
    Evento,
    Formato,
    Fuente,
    GrupoRequerido,
    Ilegible,
    NoDisponible,
    NoExiste,
    NoTomado,
    Tecla,
    TerminalesError,
    Tiempo,
    _CONFIRMAR_PROMPT,
    _LANZAMIENTO_SHELL,
)
from .ids import ID_RE, es_guardian, tipo_de_id, valido
from .modelo import (
    Creado,
    Espacio,
    ESTADOS_HERDR,
    EstadoSesion,
    InfoProceso,
    Lanzamiento,
    Linea,
    ProcesoPrimerPlano,
    Sesion,
    Tablero,
    TomaPrompt,
)

STRUCTURAL_EVENTS = [
    "workspace.created", "workspace.updated", "workspace.renamed", "workspace.closed",
    "workspace.focused", "tab.created", "tab.closed", "tab.focused", "tab.renamed",
    "pane.created", "pane.closed", "pane.updated", "pane.focused", "pane.exited",
    "pane.agent_detected",
]
READ_LIMIT = 16 * 1024 * 1024
RUN_TIMEOUT = 10.0

log = logging.getLogger("orquestador.enchufe.herdr")

VARIABLES_PROPIAS = ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID")


def herdr_instalado(cfg) -> str | None:
    candidato = (cfg.herdr_bin or "").strip() or "herdr"
    if os.sep not in candidato:
        candidato = shutil.which(candidato)
    if candidato and os.path.isfile(candidato) and os.access(candidato, os.X_OK):
        return candidato
    return None


_SENTINEL_CIERRE = object()


def sesion_propia() -> str | None:
    return os.environ.get("HERDR_PANE_ID")

A_HERDR = {"arriba": "up", "derecha": "right", "ctrl-c": "ctrl+c", "ctrl-e": "ctrl+e", "ctrl-u": "ctrl+u"}
FUENTES = {"visible": "visible", "reciente": "recent-unwrapped", "deteccion": "detection"}
_FORMATO_HERDR = {"texto": "text", "ansi": "ansi"}


class HerdrError(RuntimeError):
    pass


class HerdrClient:
    def __init__(self, herdr_bin: str = ""):
        self.bin = herdr_bin or shutil.which("herdr") or "herdr"

    @property
    def socket_path(self) -> Path:
        env = os.environ.get("HERDR_SOCKET_PATH")
        return Path(env) if env else Path.home() / ".config" / "herdr" / "herdr.sock"

    @property
    def supports_socket(self) -> bool:
        return hasattr(asyncio, "open_unix_connection") and self.socket_path.exists()

    @staticmethod
    def _budget(args: tuple) -> float:
        """Tiempo máximo del comando: el base más lo que el propio comando pide con `--timeout` (ms)."""
        extra = 0.0
        if "--timeout" in args:
            try:
                extra = int(args[args.index("--timeout") + 1]) / 1000
            except (IndexError, ValueError):
                pass
        return RUN_TIMEOUT + extra

    async def run(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            self.bin, *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), self._budget(args))
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise HerdrError("herdr no respondió a tiempo")
        if proc.returncode != 0:
            raise HerdrError(err.decode(errors="replace").strip() or f"herdr salió con {proc.returncode}")
        return out.decode(errors="replace")

    async def snapshot(self) -> dict:
        data = json.loads(await self.run("api", "snapshot"))
        return data["result"]["snapshot"]

    async def focus_workspace(self, workspace_id: str) -> None:
        await self.run("workspace", "focus", workspace_id)

    async def focus_tab(self, tab_id: str) -> None:
        await self.run("tab", "focus", tab_id)

    async def events(self, pane_ids: list, idle_timeout: float) -> AsyncIterator[Optional[dict]]:
        """Yields event dicts; None when idle_timeout passes without events."""
        subs = [{"type": t} for t in STRUCTURAL_EVENTS]
        subs += [{"type": "pane.agent_status_changed", "pane_id": p} for p in pane_ids]
        reader, writer = await asyncio.open_unix_connection(str(self.socket_path), limit=READ_LIMIT)
        try:
            request = {"id": "orq", "method": "events.subscribe", "params": {"subscriptions": subs}}
            writer.write((json.dumps(request) + "\n").encode())
            await writer.drain()
            ack = json.loads(await asyncio.wait_for(reader.readline(), 10) or "{}")
            if "error" in ack or not ack:
                raise HerdrError(f"suscripción rechazada: {ack}")
            while True:
                try:
                    line = await asyncio.wait_for(reader.readline(), idle_timeout)
                except asyncio.TimeoutError:
                    yield None
                    continue
                if not line:
                    raise HerdrError("socket cerrado")
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
        finally:
            writer.close()


def _programa(agente: str | None) -> str:
    if not agente:
        return "shell"
    if agente == "claude":
        return "claude"
    return "otro"


def _estado(crudo: str | None) -> str:
    if crudo in ESTADOS_HERDR:
        return crudo
    return "idle"


def _sesion_de_pane(pane: dict, agent_ids: set[str]) -> Sesion:
    agente = pane.get("agent")
    es_agente = bool(agente) or pane["pane_id"] in agent_ids
    session = pane.get("agent_session") or {}
    crudo = pane.get("agent_status")
    titulo = pane.get("terminal_title_stripped") or pane.get("terminal_title") or ""
    return Sesion(
        id=pane["pane_id"],
        linea_id=pane["tab_id"],
        espacio_id=pane["workspace_id"],
        programa=_programa(agente),
        estado=_estado(crudo),
        estado_fuente="herdr",
        claude_session_id=session.get("value") if session.get("kind") == "id" else None,
        cwd=pane.get("cwd") or "",
        cwd_primer_plano=pane.get("foreground_cwd"),
        titulo=titulo,
        revision=pane.get("revision"),
        backend="herdr",
        agente=agente,
        es_agente=es_agente,
        nombre_agente=pane.get("name"),
        estado_crudo=crudo,
        claude_session_tipo=session.get("kind"),
        seq=pane.get("state_change_seq"),
        terminal_id=pane.get("terminal_id"),
        titulo_crudo=pane.get("terminal_title"),
    )


def _fusionar_panes(snap: dict) -> tuple[list[dict], set[str]]:
    merged: dict[str, dict] = {}
    orden: list[str] = []
    for src in ("panes", "agents"):
        for pane in snap.get(src, []):
            pid = pane.get("pane_id")
            if not pid:
                continue
            if pid not in merged:
                orden.append(pid)
            merged[pid] = {**merged.get(pid, {}), **pane}
    agent_ids = {a.get("pane_id") for a in snap.get("agents", []) if a.get("pane_id")}
    return [merged[p] for p in orden], agent_ids


def tablero_de_snapshot(snap: dict, revision: int = 0, *, log_conflictos: bool = True) -> Tablero:
    conflictos: list[str] = []

    def conflicto(valor: str | None) -> bool:
        if valor and es_guardian(valor):
            conflictos.append(valor)
            if log_conflictos:
                log.warning("id con forma de guardián en snapshot de Herdr: %s", valor)
            return True
        return False

    panes, agent_ids = _fusionar_panes(snap)
    sesiones: list[Sesion] = []
    por_tab: dict[str, list[str]] = {}
    for pane in panes:
        if not pane.get("tab_id") or not pane.get("workspace_id"):
            log.warning("pane sin tab_id o workspace_id en snapshot de Herdr: %s", pane.get("pane_id"))
            continue
        if conflicto(pane.get("pane_id")) or conflicto(pane.get("tab_id")) or conflicto(pane.get("workspace_id")):
            continue
        ses = _sesion_de_pane(pane, agent_ids)
        sesiones.append(ses)
        por_tab.setdefault(ses.linea_id, []).append(ses.id)

    lineas: list[Linea] = []
    for tab in snap.get("tabs", []):
        tid = tab.get("tab_id")
        if not tid or conflicto(tid) or conflicto(tab.get("workspace_id")):
            continue
        lineas.append(Linea(
            id=tid,
            espacio_id=tab["workspace_id"],
            nombre=tab.get("label") or "",
            sesiones=tuple(por_tab.get(tid, ())),
            declaradas=tab.get("pane_count"),
        ))

    por_ws: dict[str, list[str]] = {}
    for lin in lineas:
        por_ws.setdefault(lin.espacio_id, []).append(lin.id)

    espacios: list[Espacio] = []
    for ws in snap.get("workspaces", []):
        wid = ws.get("workspace_id")
        if not wid or conflicto(wid):
            continue
        espacios.append(Espacio(
            id=wid,
            nombre=ws.get("label") or "",
            lineas=tuple(por_ws.get(wid, ())),
            numero=ws.get("number"),
            estado_crudo=ws.get("agent_status"),
            declaradas=ws.get("pane_count"),
        ))

    foco = snap.get("focused_tab_id")
    if foco and es_guardian(foco):
        foco = None

    return Tablero(
        espacios=tuple(espacios),
        lineas=tuple(lineas),
        sesiones=tuple(sesiones),
        revision=revision,
        linea_enfocada=foco,
        conflictos=tuple(sorted(set(conflictos))),
    )


def traducir(exc: BaseException) -> TerminalesError:
    if isinstance(exc, TerminalesError):
        return exc
    texto = str(exc)
    bajo = texto.casefold()
    if "a tiempo" in bajo:
        return Tiempo(texto)
    if "workspace_group_close_required" in texto:
        return GrupoRequerido(texto)
    if "not_found" in bajo or "not found" in bajo:
        return NoExiste(texto)
    return NoDisponible(texto)


def _estado_agente(raw: str) -> str | None:
    try:
        result = json.loads(raw).get("result") or {}
    except (ValueError, AttributeError, TypeError):
        return None
    estado = result.get("agent_status")
    if isinstance(estado, str):
        return estado
    agent = result.get("agent")
    if isinstance(agent, dict) and isinstance(agent.get("agent_status"), str):
        return agent["agent_status"]
    return None


def _until_de(estados: frozenset[str]) -> tuple[str, ...]:
    return tuple(s for s in ESTADOS_HERDR if s in estados)


def _timeout_ms(segundos: float) -> str:
    return str(round(segundos * 1000))


def _es_claude(nombre: str) -> bool:
    return os.path.basename(nombre).casefold() == "claude"


def info_de_process_json(raw: str) -> InfoProceso:
    vacio = InfoProceso(None, None, None, False, ())
    try:
        info = json.loads(raw)["result"]["process_info"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return vacio
    if not isinstance(info, dict):
        return vacio
    crudos = info.get("foreground_processes") or []
    if not isinstance(crudos, list) or not crudos:
        return InfoProceso(None, None, None, False, (), info.get("foreground_process_group_id"), info.get("shell_pid"))
    procesos: list[ProcesoPrimerPlano] = []
    es_claude = False
    for proc in crudos:
        if not isinstance(proc, dict):
            continue
        argv = proc.get("argv")
        argv_t = tuple(argv) if isinstance(argv, list) else ()
        nombre = str(proc.get("name") or "")
        if _es_claude(nombre) or any(_es_claude(str(a)) for a in argv_t[:3]):
            es_claude = True
        procesos.append(ProcesoPrimerPlano(proc.get("pid"), nombre, argv_t, proc.get("cwd")))
    if not procesos:
        return InfoProceso(None, None, None, False, (), info.get("foreground_process_group_id"), info.get("shell_pid"))
    grupo = info.get("foreground_process_group_id")
    lider = next((p for p in procesos if grupo is not None and p.pid == grupo), procesos[0])
    comando = os.path.basename(lider.nombre) if lider.nombre else None
    if not comando and lider.argv:
        comando = os.path.basename(str(lider.argv[0]).lstrip("-"))
    return InfoProceso(
        lider.pid, comando, lider.cwd, es_claude, tuple(procesos), grupo, info.get("shell_pid"),
    )


def _creado_de(raw: str, espacio_fallback: str | None) -> Creado:
    try:
        result = json.loads(raw).get("result") or {}
    except (ValueError, AttributeError, TypeError):
        raise Ilegible("respuesta de herdr ilegible")
    pane_id = (result.get("root_pane") or {}).get("pane_id")
    if not valido(ID_RE, pane_id):
        raise Ilegible("herdr no devolvió root_pane.pane_id")
    ws = (result.get("workspace") or {}).get("workspace_id") or espacio_fallback
    tab = (result.get("tab") or {}).get("tab_id")
    return Creado(ws, tab, pane_id)


def _estado_esperado(hasta: frozenset[EstadoSesion], crudo: str | None) -> EstadoSesion:
    if crudo in hasta:
        return crudo  # type: ignore[return-value]
    for s in ESTADOS_HERDR:
        if s in hasta:
            return s  # type: ignore[return-value]
    return next(iter(hasta))


class AdaptadorHerdr:
    nombre = "herdr"
    capacidades = frozenset({"foco", "renombrar", "estado_propio", "retoma"})

    def __init__(self, cliente, *, poll: float = 5.0, seguridad: float = 30.0):
        self.cliente = cliente
        self.poll = poll
        self.seguridad = seguridad
        self._revision = 0
        self._clave_tablero = None
        self._colas: set[asyncio.Queue] = set()
        self._ids_agente: list[str] = []
        self._caido_notificado = False
        self._conflictos_logeados: frozenset[str] = frozenset()
        self._tarea_fuente: Optional[asyncio.Task] = None

    async def _llamar(self, *args: str) -> str:
        try:
            return await self.cliente.run(*args)
        except Exception as exc:
            raise traducir(exc) from exc

    async def _llamar_prompt(self, *args: str) -> str:
        try:
            return await self.cliente.run(*args)
        except Exception as exc:
            err = traducir(exc)
            if isinstance(err, (Tiempo, NoExiste)):
                raise err
            raise NoTomado(str(exc)) from exc

    async def _snapshot(self) -> dict:
        try:
            return await self.cliente.snapshot()
        except Exception as exc:
            if isinstance(exc, (ValueError, KeyError, json.JSONDecodeError)):
                raise Ilegible(str(exc)) from exc
            raise traducir(exc) from exc

    async def _focus_workspace(self, workspace_id: str) -> None:
        try:
            await self.cliente.focus_workspace(workspace_id)
        except Exception as exc:
            raise traducir(exc) from exc

    async def _focus_tab(self, tab_id: str) -> None:
        try:
            await self.cliente.focus_tab(tab_id)
        except Exception as exc:
            raise traducir(exc) from exc

    def _tablero_de_snapshot(self, snap: dict, revision: int, *, log_conflictos: bool = True) -> Tablero:
        if not isinstance(snap, dict):
            raise Ilegible("snapshot no es un objeto")
        try:
            return tablero_de_snapshot(snap, revision, log_conflictos=log_conflictos)
        except Exception as exc:
            raise Ilegible(str(exc)) from exc

    def _log_conflictos_si_cambian(self, conflictos: tuple[str, ...]) -> None:
        nuevos = frozenset(conflictos)
        for cid in sorted(nuevos - self._conflictos_logeados):
            log.warning("id con forma de guardián en snapshot de Herdr: %s", cid)
        self._conflictos_logeados = nuevos

    def _comando_estructural(self, objetivo_id: str) -> tuple[str, str]:
        tipo = tipo_de_id(objetivo_id)
        if tipo == "linea":
            return "tab", objetivo_id
        if tipo == "espacio":
            return "workspace", objetivo_id
        raise NoExiste(objetivo_id)

    def _ids_de_agente(self, tablero: Tablero) -> list[str]:
        return sorted(s.id for s in tablero.sesiones if s.es_agente)

    def _empujar_a_colas(self, evento: Evento) -> None:
        for cola in self._colas:
            cola.put_nowait(evento)

    def _notificar_caido(self) -> None:
        if self._caido_notificado:
            return
        self._caido_notificado = True
        self._empujar_a_colas(Evento("caido", self.nombre))

    def _notificar_volvio(self) -> None:
        if not self._caido_notificado:
            return
        self._caido_notificado = False
        self._empujar_a_colas(Evento("volvio", self.nombre))

    async def tablero(self) -> Tablero:
        try:
            snap = await self._snapshot()
        except Ilegible:
            raise
        except TerminalesError:
            self._notificar_caido()
            raise
        try:
            base = self._tablero_de_snapshot(snap, 0, log_conflictos=False)
        except Ilegible:
            raise
        self._log_conflictos_si_cambian(base.conflictos)
        clave = (base.espacios, base.lineas, base.sesiones, base.linea_enfocada, base.conflictos)
        if clave != self._clave_tablero:
            self._revision += 1
            self._clave_tablero = clave
        tablero = replace(base, revision=self._revision)
        self._ids_agente = self._ids_de_agente(tablero)
        self._notificar_volvio()
        return tablero

    async def proceso(self, sesion_id: str) -> InfoProceso:
        raw = await self._llamar("pane", "process-info", "--pane", sesion_id)
        return info_de_process_json(raw)

    async def leer(
        self,
        sesion_id: str,
        *,
        fuente: Fuente = "visible",
        formato: Formato = "texto",
        lineas: int | None = None,
    ) -> str:
        args: list[str] = ["pane", "read", sesion_id, "--source", FUENTES[fuente]]
        if lineas is not None:
            args.extend(["--lines", str(lineas)])
        args.extend(["--format", _FORMATO_HERDR[formato]])
        return await self._llamar(*args)

    async def crear_espacio(self, nombre: str, cwd: str) -> Creado:
        raw = await self._llamar("workspace", "create", "--cwd", cwd, "--label", nombre, "--no-focus")
        return _creado_de(raw, None)

    async def crear_linea(
        self,
        espacio_id: str,
        nombre: str,
        cwd: str,
        programa: Lanzamiento = _LANZAMIENTO_SHELL,
    ) -> Creado:
        raw = await self._llamar(
            "tab", "create", "--workspace", espacio_id, "--cwd", cwd, "--label", nombre, "--no-focus",
        )
        return _creado_de(raw, espacio_id)

    async def arrancar_claude(
        self,
        sesion_id: str,
        nombre: str,
        resume: str | None = None,
        *,
        modo: str | None = None,
        dirs_extra: list[str] | None = None,
    ) -> None:
        if modo is not None:
            raise NoDisponible("herdr no permite elegir el modo de permisos")
        if resume:
            raise NoDisponible("retoma con resume no disponible en adaptador herdr")
        await self._llamar("agent", "start", nombre, "--kind", "claude", "--pane", sesion_id)

    async def renombrar(self, objetivo_id: str, nombre: str) -> None:
        kind, oid = self._comando_estructural(objetivo_id)
        await self._llamar(kind, "rename", oid, nombre)

    async def cerrar(self, objetivo_id: str) -> None:
        if tipo_de_id(objetivo_id) == "sesion":
            await self._llamar("pane", "close", objetivo_id)
            return
        kind, oid = self._comando_estructural(objetivo_id)
        await self._llamar(kind, "close", oid)

    async def enfocar(self, objetivo_id: str) -> None:
        tipo = tipo_de_id(objetivo_id)
        if tipo == "linea":
            tablero = await self.tablero()
            espacio = next((l.espacio_id for l in tablero.lineas if l.id == objetivo_id), None)
            if espacio is None:
                raise NoExiste(objetivo_id)
            await self._focus_workspace(espacio)
            await self._focus_tab(objetivo_id)
            return
        if tipo == "espacio":
            await self._focus_workspace(objetivo_id)
            return
        raise NoExiste(objetivo_id)

    async def mandar_prompt(
        self,
        sesion_id: str,
        texto: str,
        *,
        confirmar: frozenset[EstadoSesion] = _CONFIRMAR_PROMPT,
        timeout: float = 30.0,
    ) -> TomaPrompt:
        until = _until_de(confirmar)
        args = (
            "agent", "prompt", sesion_id, texto, "--wait",
            *sum((("--until", s) for s in until), ()),
            "--timeout", _timeout_ms(timeout),
        )
        raw = await self._llamar_prompt(*args)
        estado = _estado_agente(raw) or "working"
        if estado not in ESTADOS_HERDR:
            estado = "working"
        return TomaPrompt(True, estado, "herdr")  # type: ignore[arg-type]

    async def interrumpir(self, sesion_id: str) -> None:
        await self._llamar("pane", "send-keys", sesion_id, "esc")

    async def esperar(
        self, sesion_id: str, hasta: frozenset[EstadoSesion], timeout: float,
    ) -> EstadoSesion:
        until = _until_de(hasta)
        args = (
            "agent", "wait", sesion_id,
            *sum((("--until", s) for s in until), ()),
            "--timeout", _timeout_ms(timeout),
        )
        raw = await self._llamar(*args)
        return _estado_esperado(hasta, _estado_agente(raw))

    async def esperar_listo(self, sesion_id: str, timeout: float) -> str:
        await self.esperar(sesion_id, frozenset({"idle", "done"}), timeout)
        return "herdr"

    async def teclas(self, sesion_id: str, teclas: Sequence[Tecla]) -> None:
        if not teclas:
            raise ValueError("tecla no permitida")
        for t in teclas:
            if t not in TECLAS:
                raise ValueError("tecla no permitida")
        await self._llamar("pane", "send-keys", sesion_id, *[A_HERDR.get(t, t) for t in teclas])

    async def escribir(self, sesion_id: str, texto: str) -> None:
        await self._llamar("pane", "send-text", sesion_id, texto)

    async def ejecutar(self, sesion_id: str, comando: str) -> None:
        await self._llamar("pane", "run", sesion_id, comando)

    @staticmethod
    def _evento_de_socket(raw: Optional[dict]) -> Evento:
        if raw is None:
            return Evento("tablero", "herdr", datos={"motivo": "seguridad", "via": "socket"})
        inner = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        tipo = raw.get("type") or raw.get("event") or inner.get("type") or inner.get("event")
        pane_id = raw.get("pane_id") or inner.get("pane_id")
        agent_status = raw.get("agent_status") or inner.get("agent_status")
        if tipo == "pane.agent_status_changed":
            estado = agent_status if agent_status in ESTADOS_HERDR else None
            return Evento("estado", "herdr", sesion_id=pane_id, estado=estado, datos={"via": "socket"})
        if tipo == "pane.exited":
            return Evento("termino", "herdr", sesion_id=pane_id, datos={"via": "socket"})
        return Evento("tablero", "herdr", datos={"via": "socket"})

    def _arrancar_fuente(self) -> None:
        if self._tarea_fuente is not None and not self._tarea_fuente.done():
            return
        self._tarea_fuente = asyncio.create_task(self._fuente_eventos())

    def _detener_fuente_si_vacia(self) -> None:
        if self._colas:
            return
        if self._tarea_fuente is not None:
            self._tarea_fuente.cancel()
            self._tarea_fuente = None

    async def _fuente_eventos(self) -> None:
        while True:
            try:
                resuscribir_rapido = False
                if self.cliente.supports_socket:
                    ids = list(self._ids_agente)
                    try:
                        async with contextlib.aclosing(
                            self.cliente.events(ids, self.seguridad),
                        ) as eventos:
                            async for raw in eventos:
                                self._empujar_a_colas(self._evento_de_socket(raw))
                                if list(self._ids_agente) != ids:
                                    resuscribir_rapido = True
                                    break
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        log.warning("socket de Herdr no disponible (%s), uso polling", exc)
                    if resuscribir_rapido:
                        continue
                await asyncio.sleep(self.poll)
                self._empujar_a_colas(
                    Evento("tablero", "herdr", datos={"motivo": "poll", "via": "polling"}),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("fuente de eventos de Herdr murió: %s", exc)
                for cola in list(self._colas):
                    cola.put_nowait(_SENTINEL_CIERRE)
                self._colas.clear()
                return

    def suscribir(self) -> AsyncIterator[Evento]:
        return _SuscripcionEventos(self)


class _SuscripcionEventos:
    def __init__(self, adaptador: AdaptadorHerdr) -> None:
        self._adaptador = adaptador
        self._cola: asyncio.Queue[Evento] = asyncio.Queue()
        adaptador._colas.add(self._cola)
        adaptador._arrancar_fuente()
        self._cerrada = False

    def __aiter__(self) -> AsyncIterator[Evento]:
        return self

    def _liberar(self) -> None:
        if self._cerrada:
            return
        self._cerrada = True
        self._adaptador._colas.discard(self._cola)
        self._adaptador._detener_fuente_si_vacia()

    async def __anext__(self) -> Evento:
        if self._cerrada:
            raise StopAsyncIteration
        try:
            item = await self._cola.get()
        except asyncio.CancelledError:
            self._liberar()
            raise
        if item is _SENTINEL_CIERRE:
            raise StopAsyncIteration
        return item

    async def aclose(self) -> None:
        if self._cerrada:
            return
        self._cerrada = True
        self._cola.put_nowait(_SENTINEL_CIERRE)
        self._adaptador._colas.discard(self._cola)
        self._adaptador._detener_fuente_si_vacia()
