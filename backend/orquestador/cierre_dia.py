import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .config import private_write
from .agenda import parse_dias, parse_hora, seconds_until_next
from .limpieza import GitNoData, run_git
from .redaccion import redactar

log = logging.getLogger("orquestador.cierre_dia")
STATE_FILE = "cierre-dia.json"
_PANE_ID = re.compile(r"^[gw]\d+:p\d+$", re.I)
_GIT_PARALLEL = 4


def nombres(board: Optional[dict]) -> dict:
    """session_id -> (nombre, donde, agente, workspace); el nombre suma el tab si el workspace tiene varios Claude."""
    out = {}
    for ws in (board or {}).get("workspaces", []):
        claudes = [a for t in ws.get("tabs", []) for a in t.get("agents", []) if a.get("kind") == "claude"]
        for tab in ws.get("tabs", []):
            for agent in tab.get("agents", []):
                sid = agent.get("session_id")
                if not sid:
                    continue
                wl, tl = (ws.get("label") or "").strip(), (tab.get("label") or "").strip()
                if wl and tl and len(claudes) > 1:
                    nombre = f"{wl} · {tl}"
                else:
                    nombre = wl or tl or (agent.get("title") or "").strip() or "Sesión"
                donde = " / ".join(p for p in (wl, tl) if p)
                out[sid] = (redactar(nombre)[:80], redactar(donde)[:120], agent, ws)
    return out

def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _mismo_dia(ts: Optional[datetime], now: datetime) -> bool:
    if ts is None:
        return False
    local = now.astimezone()
    t = ts.astimezone(local.tzinfo)
    return t.date() == local.date()


def _nombre_legible(nombre: str, sid: str, board: Optional[dict]) -> str:
    raw = (nombre or "").strip()
    info = nombres(board).get(sid)
    if info and (_PANE_ID.match(raw) or not raw):
        return info[0]
    return raw or (info[0] if info else "Sesión")


def terminado_hoy(messages: list, now: datetime) -> list:
    vistos: set = set()
    out: list = []
    for msg in messages:
        if msg.get("role") != "reporte":
            continue
        for item in msg.get("items") or []:
            sid = item.get("session_id")
            if not sid or sid in vistos:
                continue
            fin = _parse_ts(item.get("fin"))
            if not _mismo_dia(fin, now):
                continue
            vistos.add(sid)
            out.append({
                "session_id": sid,
                "nombre": _nombre_legible(str(item.get("nombre") or ""), sid, None),
                "quedo": str(item.get("quedo") or "").strip() or "Terminó sin dejar texto",
            })
    return out


def _agentes_board(board: Optional[dict]) -> list:
    out = []
    for ws in (board or {}).get("workspaces", []):
        for tab in ws.get("tabs", []):
            for agent in tab.get("agents", []):
                if agent.get("kind") == "claude" and agent.get("session_id"):
                    out.append(agent)
    return out


def te_esperan(board: Optional[dict]) -> list:
    nmap = nombres(board)
    out = []
    for agent in _agentes_board(board):
        sid = agent.get("session_id")
        if not sid:
            continue
        motivo = None
        if agent.get("status") == "blocked":
            motivo = "blocked"
        elif agent.get("asks_user"):
            motivo = "asks"
        elif agent.get("unread"):
            motivo = "unread"
        if motivo is None:
            continue
        info = nmap.get(sid)
        nombre = info[0] if info else _nombre_legible(agent.get("title") or "", sid, board)
        out.append({"session_id": sid, "nombre": nombre, "motivo": motivo})
    return out


def _sesiones_actividad_hoy(board: Optional[dict], messages: list, now: datetime) -> set:
    sids = {x["session_id"] for x in terminado_hoy(messages, now)}
    for agent in _agentes_board(board):
        sid = agent.get("session_id")
        if sid and _mismo_dia(_parse_ts(agent.get("last_activity")), now):
            sids.add(sid)
    return sids


async def _branch_info(cwd: str, repos: dict, sem: asyncio.Semaphore, git=run_git) -> Optional[dict]:
    if not cwd or not cwd.startswith("/"):
        return None
    try:
        async with sem:
            head = (await git(["git", "-C", cwd, "--no-optional-locks", "rev-parse", "--show-toplevel",
                               "--abbrev-ref", "HEAD"], cwd)).split("\n")
    except GitNoData:
        return None
    if len(head) < 2 or not head[0].startswith("/") or not head[1] or head[1] == "HEAD":
        return None
    top, branch = head[0], head[1]
    if top not in repos:
        repos[top] = asyncio.ensure_future(_repo(top, sem, git))
    repo = await repos[top]
    if repo is None:
        return None
    merged = await _merged(top, branch, repo, sem)
    base = merged.get("base")
    if not base or branch == (base.split("/", 1)[-1] if base else ""):
        return None
    if merged.get("mergeada"):
        return None
    commits = await _commits_ahead(top, branch, base, sem, repo)
    if not commits:
        return None
    return {"repo": Path(top).name, "rama": branch, "commits": commits, "base": base}


async def _repo(top: str, sem: asyncio.Semaphore, git=run_git):
    async def g(*args):
        async with sem:
            return await git(["git", "-C", top, "--no-optional-locks", *args], top)

    try:
        base = None
        try:
            ref = (await g("symbolic-ref", "refs/remotes/origin/HEAD")).strip()
            if ref.startswith("refs/remotes/") and not ref[len("refs/remotes/"):].startswith("-"):
                base = ref[len("refs/remotes/"):]
        except GitNoData:
            pass
        base_ref = f"refs/remotes/{base}" if base else None
        if base is None:
            # Repos sin remoto (apps personales): la base es la rama principal local.
            for ref in ("refs/remotes/origin/main", "refs/remotes/origin/develop", "refs/heads/main",
                        "refs/heads/master", "refs/heads/develop"):
                try:
                    await g("rev-parse", "--verify", "--quiet", ref)
                    base_ref = ref
                    base = ref.split("/", 2)[2]
                    break
                except GitNoData:
                    continue
        if base is None:
            return None
        remote = set((await g("branch", "-r", f"--merged={base_ref}", "--format=%(refname:short)")).split("\n"))
        local = set((await g("branch", f"--merged={base_ref}", "--format=%(refname:short)")).split("\n"))
        return {"base": base, "base_ref": base_ref, "remote": remote, "local": local, "g": g}
    except GitNoData:
        return None


async def _merged(top: str, branch: str, repo: dict, sem: asyncio.Semaphore) -> dict:
    base = repo.get("base")
    if not base or branch == base.split("/", 1)[-1]:
        return {"base": base, "mergeada": False}
    g = repo["g"]
    try:
        tip = (await g("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")).strip()
        base_tip = (await g("rev-parse", "--verify", "--quiet", repo["base_ref"])).strip()
        gone = "[gone]" in await g("for-each-ref", "--format=%(upstream:track)", f"refs/heads/{branch}")
    except GitNoData:
        return {"base": base, "mergeada": False}
    if not tip or tip == base_tip:
        return {"base": base, "mergeada": False}
    merged = f"origin/{branch}" in repo["remote"] or branch in repo["local"] or gone
    return {"base": base, "mergeada": merged}


async def _commits_ahead(top: str, branch: str, base: str, sem: asyncio.Semaphore, repo: dict) -> int:
    g = repo["g"]
    try:
        raw = (await g("rev-list", "--count", f"{repo['base_ref']}..refs/heads/{branch}")).strip()
        return max(0, int(raw))
    except (GitNoData, ValueError):
        return 0


async def ramas_sin_integrar(board: Optional[dict], messages: list, now: datetime, git=run_git) -> list:
    sids = _sesiones_actividad_hoy(board, messages, now)
    cwd_por_sid = {a.get("session_id"): a.get("cwd") or "" for a in _agentes_board(board)}
    repos: dict = {}
    sem = asyncio.Semaphore(_GIT_PARALLEL)
    vistos: set = set()
    out: list = []
    for sid in sids:
        cwd = cwd_por_sid.get(sid) or ""
        info = await _branch_info(cwd, repos, sem, git=git)
        if info is None:
            continue
        key = (info["repo"], info["rama"])
        if key in vistos:
            continue
        vistos.add(key)
        out.append(info)
    out.sort(key=lambda x: (x["repo"], x["rama"]))
    return out


def contenido_cierre_dia(board: Optional[dict], messages: list, now: datetime, *,
                         esperan: Optional[list] = None, ramas: Optional[list] = None) -> Optional[dict]:
    termino = terminado_hoy(messages, now)
    for row in termino:
        row["nombre"] = _nombre_legible(row["nombre"], row["session_id"], board)
    esperan = esperan if esperan is not None else te_esperan(board)
    ramas = ramas if ramas is not None else []
    if not termino and not esperan and not ramas:
        return None
    return {
        "fecha": now.astimezone().date().isoformat(),
        "termino": termino,
        "esperan": esperan,
        "ramas": ramas,
    }


def frase_resumen_cierre(contenido: dict) -> str:
    n_t = len(contenido.get("termino") or [])
    n_e = len(contenido.get("esperan") or [])
    n_r = len(contenido.get("ramas") or [])
    parts = []
    if n_t:
        parts.append(f"{'Terminó' if n_t == 1 else 'Terminaron'} {n_t}")
    if n_e:
        parts.append(f"{'te espera' if n_e == 1 else 'te esperan'} {n_e}")
    if n_r:
        parts.append(f"{n_r} {'rama sin integrar' if n_r == 1 else 'ramas sin integrar'}")
    return " · ".join(parts)


class CierreDiaAviso:
    def __init__(self, directory: Path, hora: Callable[[], str], dias: Callable[[], list],
                 ejecutar: Callable[[], asyncio.Future], now: Optional[Callable[[], datetime]] = None,
                 sleep=asyncio.sleep):
        self.path = directory / STATE_FILE
        self.hora = hora
        self.dias = dias
        self.ejecutar = ejecutar
        self._now = now or (lambda: datetime.now().astimezone())
        self._sleep = sleep

    def _ultimo(self) -> str:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8")).get("ultimo")
        except (OSError, ValueError, AttributeError):
            return ""
        return value if isinstance(value, str) else ""

    def _marcar(self, day) -> None:
        try:
            private_write(self.path, json.dumps({"ultimo": day.isoformat()}))
        except OSError as exc:
            log.warning("no pude guardar el cierre del día: %s", type(exc).__name__)

    async def run(self) -> None:
        while True:
            tick_fallo = False
            try:
                hora = parse_hora(self.hora())
            except Exception:
                log.exception("el aviso de cierre del día falló al leer la hora")
                await self._sleep(600)
                continue
            if hora is None:
                return
            try:
                await self.tick()
            except Exception:
                log.exception("el aviso de cierre del día falló")
                tick_fallo = True
            try:
                espera = seconds_until_next(hora, parse_dias(self.dias()), self._now())
            except Exception:
                log.exception("el aviso de cierre del día falló al calcular la espera")
                await self._sleep(600)
                continue
            if tick_fallo:
                espera = min(600, espera)
            await self._sleep(espera)

    async def tick(self) -> bool:
        hora = parse_hora(self.hora())
        now = self._now()
        today = now.date()
        if hora is None or today.weekday() not in parse_dias(self.dias()):
            return False
        if (now.hour, now.minute) < hora or self._ultimo() == today.isoformat():
            return False
        self._marcar(today)
        try:
            await self.ejecutar()
        except Exception as exc:
            log.warning("cierre del día falló: %s", type(exc).__name__)
        return True
