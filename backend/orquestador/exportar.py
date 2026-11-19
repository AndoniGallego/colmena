"""Arma una copia limpia del repo para compartir (solo HEAD, sin data/ local)."""
from __future__ import annotations

import inspect
import io
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .config import data_dir, load_config

GIT_NAME = "Colmena"
GIT_EMAIL = "colmena@example.com"
COMMIT_MSG = "Colmena"
MAX_COINCIDENCIAS = 50
_BIN_MUESTRA = 8192
MIN_TERMINO = 3
ERROR_CONFIG = "No pude leer la config: no puedo garantizar que la copia esté limpia"
CARPETAS_GENERICAS = frozenset(
    "src app api web docs test tests backend frontend lib tmp data home proyectos development".split()
)
DOCS_EXCLUIDOS = ("docs/specs", "docs/plans", "docs/research")


@dataclass(frozen=True)
class DatosRevision:
    nombre: str
    terminos: list[str]
    error: str = ""


class ExportarCtx(ABC):
    repo_root: Path

    @abstractmethod
    def imprimir(self, linea: str) -> None: ...

    @abstractmethod
    def correr(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]: ...

    @abstractmethod
    def home_path(self) -> Path: ...

    @abstractmethod
    def datos_revision(self) -> DatosRevision: ...


def _host_de_origin(origin: str) -> str | None:
    raw = (origin or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").strip()
    if not host or host.lower() in ("localhost", "127.0.0.1"):
        return None
    return host


def terminos_revision(
    *,
    nombre: str = "",
    app_origin: str = "",
    viewer_origin: str = "",
    home: Path | str = "",
    git_user_email: str = "",
    extra: list[str] | None = None,
) -> DatosRevision:
    out: list[str] = []
    n = (nombre or "").strip()
    nombre_busqueda = n if len(n) >= 3 else ""
    if nombre_busqueda:
        out.append(nombre_busqueda)
    for origin in (app_origin, viewer_origin):
        h = _host_de_origin(origin)
        if h:
            out.append(h)
    home_p = Path(home).expanduser() if home else Path()
    if len(home_p.parts) >= 2:
        out.append(str(home_p))
    email = (git_user_email or "").strip()
    if email:
        out.append(email)
    for t in extra or []:
        if isinstance(t, str) and len(t.strip()) >= MIN_TERMINO:
            out.append(t.strip())
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        key = t.casefold()
        if key not in seen:
            seen.add(key)
            uniq.append(t)
    return DatosRevision(nombre=nombre_busqueda, terminos=uniq)


def _texto(valor: object) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _id_texto(valor: object) -> str:
    if isinstance(valor, bool):
        return ""
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, str) and valor.strip().isdigit():
        return valor.strip()
    return ""


def terminos_desde_config(raw: dict, excluir: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Términos del equipo y la empresa que salen de la config TOML (ya parseada)."""
    out: list[str] = [_texto(raw.get("tailscale_user"))]
    mrs = raw.get("mrs") if isinstance(raw.get("mrs"), dict) else {}
    out += [_texto(mrs.get("usuario")), _id_texto(mrs.get("usuario_id"))]
    for item in mrs.get("equipo") or []:
        if isinstance(item, dict):
            out += [_texto(item.get("usuario")), _texto(item.get("nombre"))]
            out.append(_id_texto(item.get("id")))
    omitir = CARPETAS_GENERICAS | {e.casefold() for e in excluir}
    carpetas = [*(raw.get("plan_cwds") or []), *(mrs.get("repos") or [])]
    for c in carpetas:
        if isinstance(c, str) and c.strip():
            nombre_c = Path(c.strip().rstrip("/")).name
            if nombre_c.casefold() not in omitir:
                out.append(nombre_c)
    exp = raw.get("exportar") if isinstance(raw.get("exportar"), dict) else {}
    terminos = exp.get("terminos")
    out += [_texto(t) for t in (terminos if isinstance(terminos, list) else [])]
    return [t for t in out if len(t) >= MIN_TERMINO]


def _terminos_config(directorio: Path, excluir: list[str]) -> tuple[list[str], str, str, str, str]:
    """Devuelve (términos, nombre, app_origin, viewer_origin, error)."""
    ruta = directorio / "config.toml"
    if not ruta.is_file():
        return [], "", "", "", ERROR_CONFIG
    try:
        raw = tomllib.loads(ruta.read_text(encoding="utf-8"))
        cfg = load_config(directorio)
    except Exception:
        return [], "", "", "", ERROR_CONFIG
    return (
        terminos_desde_config(raw, excluir),
        cfg.nombre or "",
        cfg.app_origin or "",
        getattr(cfg, "viewer_origin", "") or "",
        "",
    )


def _terminos_desde_maquina(repo_root: Path, home: Path) -> DatosRevision:
    try:
        extra, nombre, app_origin, viewer_origin, error = _terminos_config(data_dir(), [repo_root.name])
    except Exception:
        extra, nombre, app_origin, viewer_origin, error = [], "", "", "", ERROR_CONFIG
    proc = subprocess.run(
        ["git", "config", "user.email"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    git_email = (proc.stdout or "").strip() if proc.returncode == 0 else ""
    rev = terminos_revision(
        nombre=nombre,
        app_origin=app_origin,
        viewer_origin=viewer_origin,
        home=home,
        git_user_email=git_email,
        extra=extra,
    )
    return DatosRevision(nombre=rev.nombre, terminos=rev.terminos, error=error)


def validar_destino(dest: Path, repo_root: Path, *, existe: bool | None = None) -> str | None:
    if existe if existe is not None else dest.exists():
        return f"Ya existe {dest}; elegí otra carpeta o borrala vos"
    try:
        dest.relative_to(repo_root.resolve())
        return f"No podés exportar adentro del repo ({dest})"
    except ValueError:
        pass
    return None


def destino_resuelto(destino: str) -> Path:
    return Path(destino).expanduser().resolve()


def _es_binario(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            chunk = fh.read(_BIN_MUESTRA)
    except OSError:
        return True
    return b"\x00" in chunk


def _coincide_en_linea(linea: str, termino: str, *, palabra_completa: bool) -> bool:
    if palabra_completa:
        return re.search(rf"(?<!\w){re.escape(termino)}(?!\w)", linea, re.IGNORECASE) is not None
    return termino.casefold() in linea.casefold()


def _en_bytes(data: bytes, terminos: list[str]) -> list[str]:
    bajo = data.lower()
    out = []
    for term in terminos:
        t = term.casefold()
        if t.encode("utf-8") in bajo or t.encode("utf-16-le") in bajo:
            out.append(term)
    return out


def buscar_datos_personales(
    copia_root: Path,
    terminos: list[str],
    *,
    nombre: str | None = None,
) -> list[tuple[str, int, str]]:
    """Coincidencias (ruta, línea, término). Línea 0 = binario; -1 = nombre de la ruta."""
    if not terminos:
        return []
    copia_root = copia_root.resolve()
    nombre_key = (nombre or "").strip()
    if len(nombre_key) < 3:
        nombre_key = ""
    hits: list[tuple[str, int, str]] = []

    for path in sorted(copia_root.rglob("*")):
        rel = path.relative_to(copia_root)
        if rel.parts and rel.parts[0] == ".git":
            continue
        rel_s = rel.as_posix()
        for term in terminos:
            if term.casefold() in rel_s.casefold():
                hits.append((rel_s, -1, term))
        if path.is_symlink() or not path.is_file():
            continue
        if _es_binario(path):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            for term in _en_bytes(data, terminos):
                hits.append((rel_s, 0, term))
            continue
        try:
            texto = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for num, linea in enumerate(texto.splitlines(), start=1):
            for term in terminos:
                palabra = bool(nombre_key and term == nombre_key)
                if _coincide_en_linea(linea, term, palabra_completa=palabra):
                    hits.append((rel_s, num, term))
    return hits


def _extraer_tar(dest: Path, tar_bytes: bytes) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    dest_res = dest.resolve()
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
        if "filter" in inspect.signature(tarfile.TarFile.extractall).parameters:
            tar.extractall(dest, filter="data")
            return
        for member in tar.getmembers():
            target = (dest_res / member.name).resolve()
            if target != dest_res and dest_res not in target.parents:
                raise tarfile.TarError(f"ruta insegura en el archive: {member.name}")
        tar.extractall(dest)


def _git_archive_bytes(ctx: ExportarCtx) -> bytes | None:
    proc = ctx.correr(["git", "archive", "--format=tar", "HEAD"], cwd=ctx.repo_root)
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        ctx.imprimir(err or "git archive falló")
        return None
    return proc.stdout


def _init_repo_destino(ctx: ExportarCtx, dest: Path) -> bool:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = GIT_NAME
    env["GIT_AUTHOR_EMAIL"] = GIT_EMAIL
    env["GIT_COMMITTER_NAME"] = GIT_NAME
    env["GIT_COMMITTER_EMAIL"] = GIT_EMAIL
    pasos = [
        (["git", "init", "-b", "main"], env),
        (["git", "add", "-A"], env),
        (
            [
                "git",
                "-c",
                f"user.name={GIT_NAME}",
                "-c",
                f"user.email={GIT_EMAIL}",
                "commit",
                "-m",
                COMMIT_MSG,
            ],
            env,
        ),
        (
            [
                "git",
                "config",
                "user.name",
                GIT_NAME,
            ],
            env,
        ),
        (
            [
                "git",
                "config",
                "user.email",
                GIT_EMAIL,
            ],
            env,
        ),
    ]
    for cmd, e in pasos:
        proc = ctx.correr(cmd, cwd=dest, env=e)
        if proc.returncode != 0:
            msg = proc.stderr.decode(errors="replace").strip()
            ctx.imprimir(msg or f"falló: {' '.join(cmd)}")
            return False
    return True


def _etiqueta(num: int) -> str:
    return " (binario)" if num == 0 else " (ruta)" if num < 0 else ""


def _reportar_revision(
    ctx: ExportarCtx, dest: Path, revision: DatosRevision, permitir_hallazgos: bool = False
) -> int:
    hits = buscar_datos_personales(
        dest,
        revision.terminos,
        nombre=revision.nombre or None,
    )
    if revision.error:
        ctx.imprimir(revision.error)
    total = len(hits)
    if total == 0 and not revision.error:
        ctx.imprimir(f"Listo: copia en {dest}, sin datos tuyos a la vista.")
        return 0
    if total:
        ctx.imprimir(f"Ojo: encontré datos del equipo o de la empresa en {total} lugares; revisalos antes de compartir:")
        por_termino: dict[str, list[tuple[str, int]]] = {}
        for rel, num, term in hits:
            por_termino.setdefault(term, []).append((rel, num))
        for term, items in por_termino.items():
            archivos = len({r for r, _n in items})
            ctx.imprimir(f"{term}: {archivos} archivos")
        for rel, num, term in hits[:MAX_COINCIDENCIAS]:
            ctx.imprimir(f"{rel}:{num}: {term}" if num > 0 else f"{rel}: {term}{_etiqueta(num)}")
        if total > MAX_COINCIDENCIAS:
            ctx.imprimir(f"Total: {total}")
    if permitir_hallazgos:
        ctx.imprimir("Sigo igual porque pediste --permitir-hallazgos.")
        return 0
    ctx.imprimir("No compartas esta copia. Si los hallazgos son falsos positivos, repetí con --permitir-hallazgos.")
    return 1


def _quitar_docs_internos(dest: Path) -> list[str]:
    errores: list[str] = []
    for rel in DOCS_EXCLUIDOS:
        p = dest / rel
        try:
            if p.is_symlink():
                p.unlink()
            elif p.exists():
                shutil.rmtree(p)
        except OSError as exc:
            errores.append(f"No pude borrar {rel}: {exc.strerror or exc}")
            continue
        if p.exists() or p.is_symlink():
            errores.append(f"No pude borrar {rel}")
    return errores


def ejecutar_exportar(ctx: ExportarCtx, destino: str, permitir_hallazgos: bool = False) -> int:
    dest = destino_resuelto(destino)
    err = validar_destino(dest, ctx.repo_root.resolve())
    if err:
        ctx.imprimir(err)
        return 1
    tar_bytes = _git_archive_bytes(ctx)
    if tar_bytes is None:
        return 1
    try:
        _extraer_tar(dest, tar_bytes)
    except (tarfile.TarError, OSError) as exc:
        ctx.imprimir(str(exc))
        return 1
    errores_docs = _quitar_docs_internos(dest)
    if errores_docs:
        for e in errores_docs:
            ctx.imprimir(e)
        return 1
    if not _init_repo_destino(ctx, dest):
        return 1
    return _reportar_revision(ctx, dest, ctx.datos_revision(), permitir_hallazgos)


class RealExportarCtx(ExportarCtx):
    def __init__(self, repo_root: Path | None = None):
        if repo_root is not None:
            self.repo_root = repo_root
        else:
            pkg = Path(__file__).resolve().parent
            proc = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=pkg,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                self.repo_root = Path(__file__).resolve().parents[2]
            else:
                self.repo_root = Path(proc.stdout.strip()).resolve()
        self._home = Path.home()

    def home_path(self) -> Path:
        return self._home

    def datos_revision(self) -> DatosRevision:
        return _terminos_desde_maquina(self.repo_root, self._home)

    def imprimir(self, linea: str) -> None:
        print(linea)

    def correr(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            cmd,
            cwd=cwd or self.repo_root,
            env=merged,
            capture_output=True,
            input=input_bytes,
            check=False,
        )


def exportar(destino: str, permitir_hallazgos: bool = False) -> int:
    return ejecutar_exportar(RealExportarCtx(), destino, permitir_hallazgos)

