import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .cierre import MAX_PANES
from .config import private_write
from .enchufe import como_snapshot
from .statusline import parse_timestamp

DIAS_MIN, DIAS_MAX = 1, 90
GIT_TIMEOUT = 2.0
GIT_PARALLEL = 4
MAX_REPOS = 20
CACHE_TTL = 60.0
SEEN_KEEP_DAYS = 90
ACTIVE_STATUSES = {"idle", "done"}
# Solo lectura: nunca fetch, pull, push, gc ni nada que escriba o salga a red.
GIT_READ_ONLY = {"rev-parse", "rev-list", "symbolic-ref", "branch", "for-each-ref"}
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# El cwd sale de Herdr y puede ser un repo ajeno: nada de su config que ejecute programas.
GIT_SAFE_CONFIG = (("core.fsmonitor", "false"), ("core.hooksPath", "/dev/null"), ("core.pager", "cat"),
                   ("core.untrackedCache", "false"))


def _git_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="1", LC_ALL="C",
               GIT_CONFIG_COUNT=str(len(GIT_SAFE_CONFIG)))
    for i, (key, value) in enumerate(GIT_SAFE_CONFIG):
        env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = key, value
    return env


class GitNoData(Exception):
    pass


async def run_git(argv: list, cwd: str, timeout: float = GIT_TIMEOUT) -> str:
    sub = next((a for a in argv[1:] if not a.startswith("-") and a != cwd), "")
    if argv[0] != "git" or sub not in GIT_READ_ONLY:
        raise GitNoData("comando de git no permitido")
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, env=_git_env(), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
    except OSError as exc:
        raise GitNoData(str(exc))
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise GitNoData("timeout")
    if proc.returncode != 0:
        raise GitNoData("git falló")
    return out.decode("utf-8", "replace")


def _valid_cwd(cwd: str) -> bool:
    return bool(cwd) and cwd.startswith("/") and not CONTROL.search(cwd) and os.path.isdir(cwd)


def _age_days(stamp, now: float) -> Optional[int]:
    parsed = parse_timestamp(stamp)
    return None if parsed is None else max(0, int((now - parsed) // 86400))


class LimpiezaService:
    def __init__(self, enchufe, hub, protected_panes: Callable[[], set], protected_workspaces: list, directory: Path,
                 default_dias: Callable[[], int] = lambda: 7, git=run_git, clock: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic):
        self.enchufe = enchufe
        self.hub = hub
        self.protected_panes = protected_panes
        self.protected_workspaces = {w.strip().casefold() for w in protected_workspaces}
        self.path = directory / "limpieza-visto.json"
        self.default_dias = default_dias
        self.git = git
        self.clock = clock
        self.monotonic = monotonic
        self._cache: Optional[tuple] = None
        self._baseline: dict = {}
        self._visto: Optional[dict] = None
        self.lote_activo = False

    def dias(self, value: Optional[int]) -> int:
        base = value if value is not None else self.default_dias()
        return max(DIAS_MIN, min(DIAS_MAX, int(base)))

    def _load(self) -> dict:
        if self._visto is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._visto = {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
            except (OSError, ValueError, AttributeError):
                self._visto = {}
        return self._visto

    def _save(self) -> None:
        try:
            private_write(self.path, json.dumps(self._visto or {}))
        except OSError:
            pass

    def _observe(self, snapshot: dict, tabs_without_claude: dict, now: float) -> dict:
        """Primera vez que se ve cada tab sin Claude; un cambio de estado desde el arranque reinicia la cuenta."""
        visto = self._load()
        stamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
        dirty = False
        for tab_id, seqs in tabs_without_claude.items():
            if tab_id not in self._baseline:
                self._baseline[tab_id] = seqs
            elif self._baseline[tab_id] != seqs:
                self._baseline[tab_id] = seqs
                visto[tab_id] = stamp
                dirty = True
            if tab_id not in visto:
                visto[tab_id] = stamp
                dirty = True
        present = {t.get("tab_id") for t in snapshot.get("tabs", [])}
        limit = now - SEEN_KEEP_DAYS * 86400
        for tab_id in [t for t in visto if t not in present and (parse_timestamp(visto[t]) or now) < limit]:
            del visto[tab_id]
            dirty = True
        if dirty:
            self._save()
        return visto

    async def _branch_info(self, cwd: str, repos: dict, sem: asyncio.Semaphore) -> Optional[dict]:
        """Rama del cwd y si está mergeada según refs locales. None = sin datos."""
        if not _valid_cwd(cwd):
            return None
        try:
            async with sem:
                head = (await self.git(["git", "-C", cwd, "--no-optional-locks", "rev-parse", "--show-toplevel",
                                        "--abbrev-ref", "HEAD"], cwd)).split("\n")
        except GitNoData:
            return None
        if len(head) < 2 or not head[0].startswith("/") or not head[1] or head[1] == "HEAD":
            return None
        top, branch = head[0], head[1]
        if top not in repos:
            if len(repos) >= MAX_REPOS:
                return None
            repos[top] = asyncio.ensure_future(self._repo(top, sem))
        repo = await repos[top]
        if repo is None:
            return None
        return {"branch": branch, **await self._merged(top, branch, repo, sem)}

    async def _repo(self, top: str, sem: asyncio.Semaphore) -> Optional[dict]:
        async def g(*args):
            async with sem:
                return await self.git(["git", "-C", top, "--no-optional-locks", *args], top)

        try:
            base = None
            try:
                ref = (await g("symbolic-ref", "refs/remotes/origin/HEAD")).strip()
                if ref.startswith("refs/remotes/") and not ref[len("refs/remotes/"):].startswith("-"):
                    base = ref[len("refs/remotes/"):]
            except GitNoData:
                pass
            if base is None:
                for candidate in ("origin/main", "origin/develop"):
                    try:
                        await g("rev-parse", "--verify", "--quiet", f"refs/remotes/{candidate}")
                        base = candidate
                        break
                    except GitNoData:
                        continue
            if base is None:
                return {"base": None}
            remote = set((await g("branch", "-r", f"--merged={base}", "--format=%(refname:short)")).split("\n"))
            local = set((await g("branch", f"--merged={base}", "--format=%(refname:short)")).split("\n"))
            return {"base": base, "remote": remote, "local": local, "g": g}
        except GitNoData:
            return None

    async def _merged(self, top: str, branch: str, repo: dict, sem: asyncio.Semaphore) -> dict:
        base = repo.get("base")
        if not base or branch == base.split("/", 1)[-1]:
            return {"base": base, "mergeada": False}
        g = repo["g"]
        try:
            tip = (await g("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")).strip()
            base_tip = (await g("rev-parse", "--verify", "--quiet", f"refs/remotes/{base}")).strip()
            gone = "[gone]" in await g("for-each-ref", "--format=%(upstream:track)", f"refs/heads/{branch}")
        except GitNoData:
            return {"base": base, "mergeada": False}
        # Una rama recién creada sobre la base figura como mergeada: no cuenta como trabajo terminado.
        if not tip or tip == base_tip:
            return {"base": base, "mergeada": False}
        merged = f"origin/{branch}" in repo["remote"] or branch in repo["local"] or gone
        return {"base": base, "mergeada": merged}

    @staticmethod
    def _terminal_state(tab: dict) -> Optional[str]:
        """None si todas están en el prompt, 'corriendo' si alguna corre algo, 'dudosa' si no se sabe."""
        states = [t.get("estado") for t in tab.get("terminales", [])]
        if "corriendo" in states:
            return "corriendo"
        if any(s != "prompt" for s in states):
            return "dudosa"
        return None

    async def candidatos(self, dias: Optional[int] = None, fresh: bool = False) -> dict:
        dias = self.dias(dias)
        board = await self.hub.refresh() if fresh else await self.hub.current()
        key = (json.dumps({k: v for k, v in board.items() if k != "updated_at"}, sort_keys=True), dias)
        if not fresh and self._cache and self._cache[0] == key and self.monotonic() - self._cache[1] < CACHE_TTL:
            return self._cache[2]
        result = await self._compute(board, dias)
        self._cache = (key, self.monotonic(), result)
        return result

    async def _compute(self, board: dict, dias: int) -> dict:
        snapshot = como_snapshot(await self.enchufe.tablero())
        now = self.clock()
        own = {p for p in self.protected_panes() if p}
        panes_by_tab: dict = {}
        for source in ("panes", "agents"):
            for pane in snapshot.get(source, []):
                if pane.get("pane_id"):
                    panes_by_tab.setdefault(pane.get("tab_id"), {}).setdefault(pane["pane_id"], {}).update(pane)
        tab_meta = {t.get("tab_id"): t for t in snapshot.get("tabs", [])}
        workspaces = board.get("workspaces", [])

        no_claude: dict = {}
        for ws in workspaces:
            for tab in ws.get("tabs", []):
                if not tab.get("agents"):
                    panes = panes_by_tab.get(tab["id"], {})
                    no_claude[tab["id"]] = tuple(sorted((p, v.get("state_change_seq", 0)) for p, v in panes.items()))
        visto = self._observe(snapshot, no_claude, now)

        repos: dict = {}
        sem = asyncio.Semaphore(GIT_PARALLEL)
        gaps = [False]

        async def evaluate(ws: dict, tab: dict) -> Optional[dict]:
            tab_id = tab["id"]
            panes = panes_by_tab.get(tab_id, {})
            meta = tab_meta.get(tab_id) or {}
            if not panes or set(panes) & own or len(panes) > MAX_PANES or meta.get("pane_count") != len(panes):
                return None
            agents, terms = tab.get("agents", []), tab.get("terminales", [])
            if len(agents) + len(terms) != len(panes):
                return None
            if any(a.get("status") not in ACTIVE_STATUSES or not a.get("session_id") for a in agents):
                return None
            term_state = self._terminal_state(tab)
            if term_state == "dudosa":
                return None
            razones = []
            if agents:
                ages = [_age_days(a.get("last_activity"), now) for a in agents]
                if all(a is not None and a >= dias for a in ages):
                    razones.append({"tipo": "quieto", "dias": min(ages)})
                infos = [await self._branch_info(a.get("cwd") or "", repos, sem) for a in agents]
                if any(i is None for i in infos):
                    gaps[0] = True
                elif all(i["mergeada"] for i in infos):
                    razones.append({"tipo": "mergeada", "rama": infos[0]["branch"], "base": infos[0]["base"]})
            else:
                first = parse_timestamp(visto.get(tab_id))
                age = None if first is None else int((now - first) // 86400)
                if age is not None and age >= dias:
                    razones.append({"tipo": "sin_claude", "dias": age})
            if not razones:
                return None
            unread = any(a.get("unread") for a in agents)
            bloqueado = "sin_leer" if unread else ("corriendo" if term_state == "corriendo" else None)
            return {
                "tipo": "tab", "target_id": tab_id, "workspace": ws.get("label") or "",
                "workspace_id": ws.get("id"), "label": tab.get("label") or "", "razones": razones,
                "sesiones": [{"session_id": a["session_id"], "titulo": (a.get("doing") or a.get("title") or "")[:200],
                              "ultima": a.get("last_activity"), "pendiente": (a.get("pending") or "")[:200]}
                             for a in agents],
                "terminales": len(terms), "marcado": bloqueado is None, "bloqueado": bloqueado,
            }

        tasks = [(ws, tab) for ws in workspaces if (ws.get("label") or "").strip().casefold()
                 not in self.protected_workspaces and not ws.get("pinned") for tab in ws.get("tabs", [])]
        evaluated = await asyncio.gather(*[evaluate(ws, tab) for ws, tab in tasks])
        by_ws: dict = {}
        for (ws, _), item in zip(tasks, evaluated):
            if item:
                by_ws.setdefault(ws["id"], []).append(item)

        items = []
        for ws in workspaces:
            found = by_ws.get(ws["id"], [])
            if not found:
                continue
            ready = [i for i in found if i["bloqueado"] is None]
            if len(found) == len(ws.get("tabs", [])) and len(ready) == len(found):
                if len(workspaces) <= 1:
                    continue
                items.append(self._workspace_item(ws, found))
            elif len(found) == len(ws.get("tabs", [])) and len(workspaces) <= 1:
                items.extend(i for i in found if i["bloqueado"])
            else:
                items.extend(found)
        items.sort(key=lambda i: (i["bloqueado"] is not None, i["workspace"].casefold(), i["label"].casefold()))
        git = "ok"
        if gaps[0] or len(repos) >= MAX_REPOS:
            git = "parcial"
        if repos and all(r.result() is None for r in repos.values() if r.done()):
            git = "sin_datos"
        return {"dias": dias, "items": items, "generado_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "git": git}

    @staticmethod
    def _workspace_item(ws: dict, found: list) -> dict:
        tipos = {}
        for item in found:
            for r in item["razones"]:
                tipos.setdefault(r["tipo"], r)
        razones = list(tipos.values())
        return {"tipo": "workspace", "target_id": ws["id"], "workspace": ws.get("label") or "",
                "workspace_id": ws["id"], "label": ws.get("label") or "", "razones": razones,
                "sesiones": [s for i in found for s in i["sesiones"]],
                "terminales": sum(i["terminales"] for i in found), "marcado": True, "bloqueado": None}

    async def sigue_siendo_candidato(self, tipo: str, target_id: str, dias: Optional[int]) -> bool:
        fresh = await self.candidatos(dias, fresh=True)
        return any(i["tipo"] == tipo and i["target_id"] == target_id and i["bloqueado"] is None
                   for i in fresh["items"])
