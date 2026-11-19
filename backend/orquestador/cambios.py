"""Qué cambió una sesión: rama, commits sobre la base y diff por archivo (solo lectura, sin fetch)."""
import asyncio
import time
from pathlib import Path
from typing import Callable, Optional

from .mrs import git_env

GIT_TIMEOUT = 10.0
MAX_COMMITS = 50
MAX_ARCHIVOS_DIFF = 200
MAX_ARCHIVO = 60_000
MAX_TOTAL = 600_000
MAX_LECTURA = 1_000_000
CACHE_TTL = 5.0
CACHE_MAX = 50
BASES_FALLBACK = ("main", "master")


async def _git(cwd: str, *args: str) -> Optional[bytes]:
    cmd = ["git", "--no-pager", "-c", "core.quotepath=off", "--literal-pathspecs", *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd, env=git_env(), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    except OSError:
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), GIT_TIMEOUT)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        return None
    return out if proc.returncode == 0 else None


def _txt(raw: Optional[bytes]) -> str:
    return (raw or b"").decode(errors="replace").strip()


def _pares(raw: Optional[bytes]) -> list:
    return [p for p in (raw or b"").decode(errors="replace").split("\0")]


def _recortar(diff: str, restante: int, tope: int) -> tuple:
    limite = max(0, min(tope, restante))
    if len(diff) <= limite:
        return diff, False
    return diff[:limite], True


class CambiosService:
    def __init__(self, ttl: float = CACHE_TTL, clock: Callable[[], float] = time.monotonic,
                 max_archivo: int = MAX_ARCHIVO, max_total: int = MAX_TOTAL):
        self.ttl = ttl
        self.clock = clock
        self.max_archivo = max_archivo
        self.max_total = max_total
        self._cache: dict = {}

    async def cambios(self, cwd: str, refrescar: bool = False) -> dict:
        now = self.clock()
        hit = self._cache.get(cwd)
        if hit and not refrescar and now - hit[0] < self.ttl:
            return hit[1]
        out = await self._armar(cwd)
        self._cache[cwd] = (now, out)
        while len(self._cache) > CACHE_MAX:
            self._cache.pop(next(iter(self._cache)))
        return out

    async def _base(self, top: str) -> tuple:
        """(nombre para mostrar, ref para git) de la rama por defecto; vacío si no hay."""
        cand = []
        head = _txt(await _git(top, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"))
        if head:
            cand.append(head)
        for nombre in BASES_FALLBACK:
            cand += [nombre, f"origin/{nombre}"]
        for ref in cand:
            if await _git(top, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is not None:
                return (ref[len("origin/"):] if ref.startswith("origin/") else ref), ref
        return "", ""

    async def _armar(self, cwd: str) -> dict:
        vacio = {"repo": False, "rama": "", "base": "", "commits": [], "commits_total": 0,
                 "sin_guardar": 0, "archivos": [], "truncado": False}
        if not cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
            return vacio
        top = _txt(await _git(cwd, "rev-parse", "--show-toplevel"))
        if not top:
            return vacio
        rama = _txt(await _git(top, "branch", "--show-current"))
        base, base_ref = await self._base(top)
        tiene_head = await _git(top, "rev-parse", "--verify", "--quiet", "HEAD^{commit}") is not None
        mb = ""
        commits: list = []
        total = 0
        if tiene_head and base_ref:
            mb = _txt(await _git(top, "merge-base", base_ref, "HEAD"))
            rango = f"{base_ref}..HEAD"
            total = int(_txt(await _git(top, "rev-list", "--count", rango)) or 0)
            log = _txt(await _git(top, "log", f"-n{MAX_COMMITS}", "--format=%h%x09%s", rango))
            for linea in log.splitlines():
                sha, _, titulo = linea.partition("\t")
                commits.append({"sha": sha, "titulo": titulo})
        elif tiene_head:
            mb = "HEAD"

        archivos: dict = {}
        if mb:
            estados = _pares(await _git(top, "diff", mb, "--name-status", "--no-renames", "-z"))
            for i in range(0, len(estados) - 1, 2):
                archivos[estados[i + 1]] = {"estado": estados[i][:1] or "M"}
            nums = _pares(await _git(top, "diff", mb, "--numstat", "--no-renames", "-z"))
            for tok in nums:
                partes = tok.split("\t", 2)
                if len(partes) == 3 and partes[2] in archivos:
                    a = archivos[partes[2]]
                    a["binario"] = partes[0] == "-"
                    a["adds"], a["dels"] = (0, 0) if a["binario"] else (int(partes[0]), int(partes[1]))

        sin_guardar = 0
        untracked: list = []
        estado = _pares(await _git(top, "status", "--porcelain", "-z", "-uall"))
        i = 0
        while i < len(estado):
            ent = estado[i]
            i += 1
            if len(ent) < 4:
                continue
            sin_guardar += 1
            if ent[0] in "RC":
                i += 1
            if ent[:2] == "??":
                untracked.append(ent[3:])
        for path in untracked:
            archivos.setdefault(path, {"estado": "A", "nuevo": True})

        lista = []
        restante = self.max_total
        truncado = False
        for n, path in enumerate(sorted(archivos)):
            a = archivos[path]
            item = {"path": path, "estado": a["estado"], "adds": a.get("adds", 0), "dels": a.get("dels", 0),
                    "binario": a.get("binario", False), "diff": "", "truncado": False}
            if a.get("nuevo"):
                self._leer_nuevo(top, path, item)
                diff = item.pop("_diff", "")
            elif item["binario"] or n >= MAX_ARCHIVOS_DIFF:
                diff = ""
                item["truncado"] = not item["binario"]
            else:
                crudo = _txt_sin_strip(await _git(top, "diff", mb, "--no-color", "--no-ext-diff", "--no-renames",
                                                    "-U3", "--", path))
                diff = crudo[crudo.find("@@"):] if "@@" in crudo else ""
            if diff:
                diff, cortado = _recortar(diff, restante, self.max_archivo)
                item["truncado"] = item["truncado"] or cortado
            elif restante <= 0 and not item["binario"] and (a.get("adds", 0) or a.get("dels", 0) or a.get("nuevo")):
                item["truncado"] = True
            item.pop("_diff", None)
            item["diff"] = diff
            restante -= len(diff)
            truncado = truncado or item["truncado"]
            lista.append(item)
        return {"repo": True, "rama": rama, "base": base, "commits": commits, "commits_total": total,
                "sin_guardar": sin_guardar, "archivos": lista, "truncado": truncado}

    @staticmethod
    def _leer_nuevo(top: str, path: str, item: dict) -> None:
        archivo = Path(top) / path
        try:
            if archivo.is_symlink() or not archivo.is_file():
                return
            with archivo.open("rb") as fh:
                crudo = fh.read(MAX_LECTURA)
        except OSError:
            return
        if b"\0" in crudo[:8000]:
            item["binario"] = True
            return
        lineas = crudo.decode(errors="replace").splitlines()
        item["adds"] = len(lineas)
        item["_diff"] = f"@@ -0,0 +1,{len(lineas)} @@\n" + "\n".join("+" + ln for ln in lineas)


def _txt_sin_strip(raw: Optional[bytes]) -> str:
    return (raw or b"").decode(errors="replace")
