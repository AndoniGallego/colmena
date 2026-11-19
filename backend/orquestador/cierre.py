import asyncio
import hashlib
import json
import logging
import os
import uuid
from contextlib import AsyncExitStack
from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field

from .enchufe import GrupoRequerido, Ilegible, InfoProceso, TerminalesError, como_snapshot
from .locks import PaneLocks
from .nueva_tarea import estado_copia
from .terminales import AGENT_PROCS, parse_process
from .traspaso import CONTROL_RE, FALLO_TERMINAL, ID_RE, TraspasoError, _need_id, _now

MAX_PANES = 12
BLOCKING = {"working", "blocked", "unknown", "fondo"}
SHELLS = {"bash", "zsh", "sh", "fish", "dash", "ksh", "nu"}
log = logging.getLogger(__name__)


class PreviewBody(BaseModel):
    tipo: Literal["tab", "workspace"]
    target_id: str = Field(..., max_length=64)


class CierreBody(PreviewBody):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    huella: str = Field(..., max_length=128)
    origen: Literal["manual", "jefe", "limpieza", "plan", "pedido-pestana"]
    destino: str = Field("", max_length=200)
    por_que: str = Field("", max_length=2000)
    lote_id: str = Field("", pattern=r"^([A-Za-z0-9_-]{8,64})?$")
    sin_guardar: bool = False
    forzar: bool = False
    confirmado_por: Literal["", "aprobar_todo", "usuario"] = ""


def _foreground_name(info: InfoProceso | None) -> Optional[str]:
    if info is None:
        return None
    shell_pid = info.shell_pid
    for proc in info.procesos:
        name = str(proc.nombre or "")
        if name and proc.pid != shell_pid and name not in SHELLS:
            return CONTROL_RE.sub(" ", name)[:80]
    return None


def _runs_claude(info: InfoProceso | None, parsed: dict) -> bool:
    """Cualquier proceso en primer plano que sea Claude, no solo el líder del grupo (falla hacia "es Claude")."""
    if (parsed.get("proceso") or "") in AGENT_PROCS:
        return True
    if info is None:
        return False
    return any(str(p.nombre or "").rsplit("/", 1)[-1].casefold() in AGENT_PROCS for p in info.procesos)


class CierreService:
    def __init__(self, enchufe, state, locks: PaneLocks, protected_panes: Callable[[], set],
                 protected_workspaces: list, refresh: Callable = None, fondo=None, worktrees=None):
        self.enchufe = enchufe
        self.state = state
        self.locks = locks
        self.protected_panes = protected_panes
        self.protected_workspaces = {w.strip().casefold() for w in protected_workspaces}
        self.refresh = refresh
        self.fondo = fondo
        self.worktrees = worktrees
        self._inflight: set = set()

    async def _snapshot(self) -> dict:
        try:
            return como_snapshot(await self.enchufe.tablero())
        except Ilegible as exc:
            raise TraspasoError(409, f"Las terminales devolvieron un estado que no se puede interpretar: {exc}")
        except TerminalesError as exc:
            raise TraspasoError(502, f"Las terminales no responden: {exc}")

    @staticmethod
    def _target(snapshot: dict, tipo: str, target_id: str):
        items = snapshot.get("tabs" if tipo == "tab" else "workspaces", [])
        key = "tab_id" if tipo == "tab" else "workspace_id"
        return next((i for i in items if i.get(key) == target_id), None)

    @staticmethod
    def _panes(snapshot: dict, tipo: str, target_id: str) -> list:
        key = "tab_id" if tipo == "tab" else "workspace_id"
        merged: dict = {}
        for source in ("panes", "agents"):
            for pane in snapshot.get(source, []):
                if pane.get(key) == target_id and pane.get("pane_id"):
                    merged[pane["pane_id"]] = {**merged.get(pane["pane_id"], {}), **pane}
        return [merged[k] for k in sorted(merged)]

    def _is_protected(self, workspace: dict) -> bool:
        return (workspace.get("label") or "").strip().casefold() in self.protected_workspaces

    def _check_protected(self, snapshot: dict, panes: list, workspace: dict, tipo: str, closes_workspace: bool) -> None:
        if self.protected_panes() & {p["pane_id"] for p in panes}:
            raise TraspasoError(400, "No se puede cerrar el orquestador")
        if not self._is_protected(workspace):
            return
        # Del workspace protegido solo se cierran tabs sin Claude que no se lleven el workspace; el proceso se mira aparte.
        if tipo != "tab" or closes_workspace:
            raise TraspasoError(400, "Ese workspace está protegido")
        agent_ids = {a.get("pane_id") for a in snapshot.get("agents", [])}
        if any(p.get("agent") or p["pane_id"] in agent_ids for p in panes):
            raise TraspasoError(403, "Ese tab del workspace protegido tiene una sesión de Claude")

    def _view(self, snapshot: dict, body: PreviewBody) -> dict:
        target_id = _need_id(body.target_id, "target_id")
        target = self._target(snapshot, body.tipo, target_id)
        if target is None:
            raise TraspasoError(404, "Ya no está abierto")
        workspaces = snapshot.get("workspaces", [])
        workspace_id = target.get("workspace_id") if body.tipo == "tab" else target_id
        workspace = next((w for w in workspaces if workspace_id and w.get("workspace_id") == workspace_id), None)
        if workspace is None:
            raise TraspasoError(409, "No pude ubicar el workspace del tab: revisalo de nuevo")
        tabs_here = [t for t in snapshot.get("tabs", []) if t.get("workspace_id") == workspace_id]
        closes_workspace = body.tipo == "tab" and len(tabs_here) == 1
        panes = self._panes(snapshot, body.tipo, target_id)
        self._check_protected(snapshot, panes, workspace, body.tipo, closes_workspace)
        if target.get("pane_count") != len(panes):
            raise TraspasoError(409, "No pude ver todos sus paneles: cerralo en la terminal")
        if len(panes) > MAX_PANES:
            raise TraspasoError(409, "Demasiados panes: cerralo en la terminal")
        if (body.tipo == "workspace" or closes_workspace) and len(workspaces) <= 1:
            raise TraspasoError(409, "Es el único workspace abierto")
        labels = [target.get("label") or ""] if body.tipo == "tab" else sorted(t.get("label") or "" for t in tabs_here)
        return {"target": target, "workspace": workspace, "panes": panes, "closes_workspace": closes_workspace,
                "tab_count": 1 if body.tipo == "tab" else len(tabs_here), "labels": labels,
                "protected": self._is_protected(workspace)}

    @staticmethod
    def _guard_protected(view: dict, infos: dict) -> None:
        """Tab del workspace protegido: cada pane tiene que leerse y ninguno puede estar corriendo Claude."""
        if not view["protected"]:
            return
        if not view["panes"]:
            raise TraspasoError(403, "No pude ver qué corre en ese tab del workspace protegido: cerralo en la terminal")
        for pane in view["panes"]:
            info = infos.get(pane["pane_id"]) or {"proceso": None, "estado": "desconocido"}
            if info.get("claude"):
                raise TraspasoError(403, "Ese tab del workspace protegido tiene una sesión de Claude")
            if info.get("estado") not in {"prompt", "corriendo"}:
                raise TraspasoError(403, "No pude ver qué corre en ese tab del workspace protegido: cerralo en la terminal")

    @staticmethod
    def _huella(view: dict, body: PreviewBody, procs: dict) -> str:
        panes = sorted(
            [p["pane_id"], p.get("terminal_id") or "", (p.get("agent_status") or "") if p.get("agent") else "-",
             p.get("state_change_seq", 0), procs.get(p["pane_id"]) or ""] for p in view["panes"])
        raw = json.dumps([body.tipo, body.target_id, view["workspace"].get("label") or "", view["labels"], panes])
        return hashlib.sha256(raw.encode()).hexdigest()

    def _blockers(self, panes: list, procs: dict, infos: dict) -> list:
        out = []
        for p in panes:
            if not p.get("agent"):
                if ((procs.get(p["pane_id"]) or "").casefold() == "claude"
                        or (infos.get(p["pane_id"]) or {}).get("claude")):
                    out.append({"pane_id": p["pane_id"], "status": "unknown"})
                continue
            status = p.get("agent_status") or "unknown"
            if status not in {"idle", "done"}:
                out.append({"pane_id": p["pane_id"], "status": status if status in BLOCKING else "unknown"})
                continue
            session = p.get("agent_session") or {}
            sid = session.get("value") if session.get("kind") == "id" else None
            if sid and self.fondo is not None and self.fondo.for_session(sid):
                out.append({"pane_id": p["pane_id"], "status": "fondo"})
        return out

    async def _inspect(self, panes: list) -> tuple:
        """Lectura fresca de cada pane sin agente: (nombre para la lista y la huella, proceso/estado robusto)."""
        found = await asyncio.gather(*[self._process(p["pane_id"]) if not p.get("agent") else _none() for p in panes])
        procs, infos = {}, {}
        for pane, proc_info in zip(panes, found):
            if pane.get("agent"):
                continue
            parsed = parse_process(proc_info)
            infos[pane["pane_id"]] = {**parsed, "claude": proc_info is not None and _runs_claude(proc_info, parsed)}
            name = _foreground_name(proc_info)
            if name:
                procs[pane["pane_id"]] = name
        return procs, infos

    async def _process(self, pane_id: str) -> Optional[InfoProceso]:
        try:
            return await self.enchufe.proceso(pane_id)
        except TerminalesError:
            return None

    async def preview(self, body: PreviewBody) -> dict:
        view = self._view(await self._snapshot(), body)
        panes = view["panes"]
        procs, infos = await self._inspect(panes)
        self._guard_protected(view, infos)
        listed = []
        for pane in panes:
            proceso = procs.get(pane["pane_id"])
            session = pane.get("agent_session") or {}
            listed.append({
                "pane_id": pane["pane_id"],
                "kind": pane.get("agent") or None,
                "status": (pane.get("agent_status") or "unknown") if pane.get("agent") else None,
                "titulo": CONTROL_RE.sub(" ", pane.get("terminal_title_stripped") or pane.get("terminal_title") or "")[:200],
                "session_id": session.get("value") if session.get("kind") == "id" else None,
                "cwd": CONTROL_RE.sub(" ", pane.get("cwd") or ""),
                "proceso": proceso,
            })
        target = view["target"]
        return {
            "tipo": body.tipo, "target_id": body.target_id, "label": target.get("label") or "",
            "workspace_label": view["workspace"].get("label") or "",
            "cierra_workspace": view["closes_workspace"], "tab_count": view["tab_count"],
            "panes": listed, "bloqueantes": self._blockers(panes, procs, infos),
            "huella": self._huella(view, body, procs), "protegido": view["protected"],
        }

    def _already_done(self, ident: str) -> bool:
        return any(c.get("id") == ident and c.get("ok") for c in self.state.cierres())

    @staticmethod
    def estructura(preview: dict) -> str:
        """Qué hay en el target sin el estado de los agentes: sirve para saber si tras guardar cambió algo más."""
        raw = json.dumps([preview.get("tipo"), preview.get("target_id"), preview.get("label"), preview.get("workspace_label"),
                          preview.get("cierra_workspace"), preview.get("tab_count"),
                          sorted(p.get("pane_id") for p in preview.get("panes", []))])
        return hashlib.sha256(raw.encode()).hexdigest()

    async def execute(self, body: CierreBody, guardado: str = "saltado", forzar: bool = False, solo_unknown: bool = False) -> dict:
        if body.id in self._inflight or self._already_done(body.id):
            raise TraspasoError(409, "Ya se cerró")
        _need_id(body.target_id, "target_id")
        self._inflight.add(body.id)
        try:
            async with self.locks.structure:
                first = self._view(await self._snapshot(), body)
                locked = {p["pane_id"] for p in first["panes"]}
                async with AsyncExitStack() as stack:
                    for pane in sorted(locked):
                        await stack.enter_async_context(self.locks.get(pane))
                    return await self._close(body, locked, guardado, forzar, solo_unknown)
        finally:
            self._inflight.discard(body.id)

    def _changed(self, body: CierreBody) -> TraspasoError:
        what = "tab" if body.tipo == "tab" else "workspace"
        return TraspasoError(409, f"El {what} cambió, revisalo de nuevo")

    async def _close(self, body: CierreBody, locked: set, guardado: str = "saltado", forzar: bool = False,
                     solo_unknown: bool = False) -> dict:
        view = self._view(await self._snapshot(), body)
        panes = view["panes"]
        procs, infos = await self._inspect(panes)
        self._guard_protected(view, infos)
        blockers = self._blockers(panes, procs, infos)
        if forzar:
            # "Cerrar igual": el usuario ya decidió cerrar con la sesión trabajando o con un diálogo abierto.
            blockers = [b for b in blockers if b["status"] not in {"working", "blocked", "fondo", "unknown"}]
        elif solo_unknown:
            # Forzar público: solo el "no sé si está trabajando"; working/blocked/fondo siguen frenando.
            blockers = [b for b in blockers if b["status"] != "unknown"]
        if blockers:
            log.info("cierre rechazado %s %s (forzar=%s): %s", body.tipo, body.target_id,
                     "cerrar_igual" if forzar else "publico" if solo_unknown else "no",
                     ", ".join(f"{b['pane_id']}={b['status']}" for b in blockers))
            only_unknown = all(b["status"] == "unknown" for b in blockers)
            detail = "No sé si está trabajando: revisala o cerrala en la terminal" if only_unknown else "Frenala primero"
            raise TraspasoError(409, detail, {"bloqueantes": blockers})
        if {p["pane_id"] for p in panes} != locked or body.huella != self._huella(view, body, procs):
            raise self._changed(body)
        sesiones = [{"session_id": (p.get("agent_session") or {}).get("value"), "cwd": CONTROL_RE.sub(" ", p.get("cwd") or ""),
                     "titulo": CONTROL_RE.sub(" ", p.get("terminal_title_stripped") or "")[:200]}
                    for p in panes if p.get("agent") == "claude" and (p.get("agent_session") or {}).get("kind") == "id"]
        label = view["target"].get("label") or body.target_id
        workspace_id = view["target"].get("workspace_id") if body.tipo == "tab" else None
        try:
            await self.enchufe.cerrar(body.target_id)
        except GrupoRequerido:
            raise TraspasoError(409, "Tiene worktrees vinculados: cerralo en la terminal")
        except TerminalesError as exc:
            self._record(body, label, [], ok=False, error=str(exc)[:300], guardado=guardado)
            raise TraspasoError(502, f"{FALLO_TERMINAL}: {exc}")
        try:
            after = await self._snapshot()
        except TraspasoError:
            after = None
        if after is not None and self._target(after, body.tipo, body.target_id) is not None:
            self._record(body, label, [], ok=False, error="No se pudo cerrar", guardado=guardado)
            raise TraspasoError(502, "No se pudo cerrar")
        self._record(body, label, sesiones, ok=True, guardado=guardado)
        log.info("cerrado %s %s (%d panes)", body.tipo, body.target_id, len(panes))
        if self.refresh:
            try:
                await self.refresh()
            except Exception as exc:
                log.warning("refresh tras cerrar falló: %s", exc)
        result: dict = {"ok": True, "sesiones": sesiones}
        copias = await self._copias_ofrecibles(panes, after)
        if copias:
            result["copias"] = copias
        if after is None:
            result["aviso"] = "No pude confirmar que se cerró: revisá el tablero"
        if body.tipo == "tab":
            result["closed_tab_id"] = body.target_id
            if view["closes_workspace"] and workspace_id:
                result["closed_workspace_id"] = workspace_id
        else:
            result["closed_workspace_id"] = body.target_id
        if body.origen == "jefe":
            event = {"id": uuid.uuid4().hex, "role": "event", "ts": _now(),
                     "text": f"Cerré {body.tipo} {CONTROL_RE.sub(' ', label)[:200]}"}
            result["event"] = event
        return result

    async def _copias_ofrecibles(self, panes: list, after: Optional[dict]) -> list:
        """Copias del repo creadas por Colmena que usaban los panes cerrados, y si se pueden borrar sin perder nada."""
        if self.worktrees is None:
            return []
        registradas = {os.path.realpath(e["ruta"]): e for e in self.worktrees.todas()}
        en_uso = {os.path.realpath(a["cwd"]) for a in (after or {}).get("agents", []) if a.get("cwd")}
        usadas: dict = {}
        for p in panes:
            real = os.path.realpath(p["cwd"]) if p.get("cwd") else ""
            if real in registradas and real not in en_uso:
                usadas[real] = registradas[real]
        out = []
        for entrada in usadas.values():
            try:
                estado = await asyncio.to_thread(estado_copia, entrada)
            except TraspasoError:
                estado = {"borrable": False, "motivo": "No pude revisar la copia"}
            out.append({"ruta": entrada["ruta"], "rama": entrada["rama"], **estado})
        return out

    def _record(self, body: CierreBody, label: str, sesiones: list, ok: bool, error: str = "",
                guardado: str = "saltado") -> None:
        entry = {"id": body.id, "tipo": body.tipo, "target_id": body.target_id,
                 "label": CONTROL_RE.sub(" ", label)[:200], "origen": body.origen, "ts": _now(), "ok": ok,
                 "sesiones": sesiones, "guardado": guardado}
        if body.lote_id:
            entry["lote_id"] = body.lote_id
        if body.confirmado_por:
            entry["confirmado_por"] = body.confirmado_por
        if error:
            entry["error"] = error
        self.state.add_cierre(entry)


async def _none():
    return None
