"""Vista del kit para la app: estado en lenguaje simple y catálogo de reglas, skills y hooks."""

import re
import subprocess
import threading
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import kit_instalador as ki

MAX_PROPOSITO = 160
_ID_REGLA = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_MARCA_PROPOSITO = re.compile(r"<!--\s*propósito:\s*(.*?)\s*-->", re.S)
_FIN_ORACION = re.compile(r"(?<=[.!?])\s")


def _primera_oracion(texto: str, maximo: int = MAX_PROPOSITO) -> str:
    texto = " ".join(texto.split())
    corte = _FIN_ORACION.search(texto)
    if corte:
        texto = texto[: corte.start()]
    if len(texto) > maximo:
        texto = texto[: maximo - 1].rstrip() + "…"
    return texto


def _titulo_de(md: str) -> str:
    for linea in md.splitlines():
        if linea.startswith("# "):
            return linea[2:].strip()
    return ""


def proposito_de(md: str) -> str:
    """Marca `<!-- propósito: ... -->` si está; si no, primera oración del primer párrafo real
    (sin título, sin citas (>), sin comentarios HTML ni bloques de código)."""
    marca = _MARCA_PROPOSITO.search(md)
    if marca:
        return _primera_oracion(marca.group(1))
    parrafo: list[str] = []
    en_codigo = False
    for linea in md.splitlines():
        t = linea.strip()
        if t.startswith(("```", "~~~")):
            if parrafo:
                break
            en_codigo = not en_codigo
            continue
        if en_codigo:
            continue
        if not t:
            if parrafo:
                break
            continue
        if t.startswith(("#", ">", "<!--")):
            if parrafo:
                break
            continue
        parrafo.append(re.sub(r"^[-*]\s+", "", t))
    return _primera_oracion(" ".join(parrafo))


def _frontmatter(md: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---", md, re.S)
    out: dict[str, str] = {}
    if not m:
        return out
    for linea in m.group(1).splitlines():
        k, sep, v = linea.partition(":")
        if sep and k.strip() and not linea.startswith(" "):
            out[k.strip()] = v.strip().strip("\"'")
    return out


def _cabecera_hook(texto: str) -> str:
    lineas = texto.splitlines()
    if lineas and lineas[0].startswith("#!"):
        lineas = lineas[1:]
    out: list[str] = []
    for linea in lineas:
        if linea.startswith("#"):
            out.append(linea.lstrip("#").strip())
        elif not linea.strip() and not out:
            continue
        else:
            break
    return " ".join(x for x in out if x)


def _leer(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _reglas(kit_dir: Path) -> dict[str, Path]:
    return {f.stem: f for f in sorted((kit_dir / "reglas").glob("*/*.md"))}


def catalogo(kit_dir: Path) -> dict[str, list[dict]]:
    reglas = []
    for rid, f in _reglas(kit_dir).items():
        md = _leer(f)
        reglas.append(
            {"id": rid, "titulo": _titulo_de(md) or rid, "proposito": proposito_de(md)}
        )
    skills = []
    for sd in sorted((kit_dir / "skills").glob("*")):
        if not sd.is_dir():
            continue
        fm = _frontmatter(_leer(sd / "SKILL.md"))
        skills.append(
            {
                "id": sd.name,
                "nombre": fm.get("name") or sd.name,
                "que_hace": _primera_oracion(fm.get("description", "")),
            }
        )
    hooks = []
    for h in sorted((kit_dir / "ganchos").glob("*.sh")):
        cab = _cabecera_hook(_leer(h))
        hooks.append({"id": h.name, "nombre": h.name, "que_hace": _primera_oracion(cab)})
    return {"reglas": reglas, "skills": skills, "hooks": hooks}


def texto_regla(kit_dir: Path, rid: str) -> str | None:
    if not _ID_REGLA.match(rid):
        return None
    f = _reglas(kit_dir).get(rid)
    return _leer(f) if f else None


_PROBLEMA = {
    ("regla", "falta"): "Falta instalar la regla «{n}».",
    ("regla", "ajeno"): "La regla «{n}» es otra cosa, no la del kit.",
    ("regla", "sobra"): "Sobra la regla «{n}»: quedó de una versión vieja.",
    ("skill", "falta"): "Falta instalar la skill «{n}».",
    ("skill", "ajeno"): "La skill «{n}» es otra cosa, no la del kit.",
    ("skill", "sobra"): "Sobra la skill «{n}»: quedó de una versión vieja.",
    ("hook", "falta"): "Falta instalar el hook «{n}».",
    ("hook", "ajeno"): "El hook «{n}» es otra cosa, no el del kit.",
    ("hook", "sobra"): "Sobra el hook «{n}»: quedó de una versión vieja.",
    ("bin", "falta"): "Falta el comando «{n}».",
    ("bin", "ajeno"): "El comando «{n}» es otra cosa, no el del kit.",
    ("bin", "sobra"): "Sobra el comando «{n}»: quedó de una versión vieja.",
    ("unit", "falta"): "Falta el servicio de actualización automática («{n}»).",
    ("unit", "distinta"): "El servicio de actualización («{n}») difiere del del kit.",
    ("settings", "falta"): "Los hooks del kit no están registrados en la configuración de Claude.",
    ("settings", "distinta"): "Los hooks registrados en Claude no coinciden con los del kit.",
}


def _problema(it: dict) -> str | None:
    est = it["estado"]
    if est in ("ok", "info"):
        return None
    if it["tipo"] == "settings" and it["nombre"] == "statusLine":
        return "Falta la barra de estado del kit en la configuración de Claude."
    if est == "error":
        return f"No pude revisar «{it['nombre']}»: {it['detalle']}"
    plantilla = _PROBLEMA.get((it["tipo"], est))
    return plantilla.format(n=it["nombre"]) if plantilla else f"«{it['nombre']}» no está como debería."


def estado(kit_dir: Path, deploy_dir: Path, d: ki.Destinos) -> dict:
    rep = ki.chequear_kit(kit_dir, deploy_dir, d)
    problemas = [p for p in map(_problema, rep.items) if p]
    return {
        "al_dia": not rep.drift and not rep.fallo and not problemas,
        "problemas": problemas,
    }


SYSTEMCTL_TIMEOUT = 30


class SystemctlNoResponde(Exception):
    pass


def _correr_systemctl(cmd: list[str]) -> int:
    try:
        return subprocess.run(cmd, check=False, capture_output=True, timeout=SYSTEMCTL_TIMEOUT).returncode
    except subprocess.TimeoutExpired as e:
        raise SystemctlNoResponde(cmd) from e


def arreglar(kit_dir: Path, deploy_dir: Path, d: ki.Destinos, correr: Callable[[list[str]], int]) -> tuple[bool, str]:
    lineas: list[str] = []
    try:
        rc = ki.instalar_kit(kit_dir, deploy_dir, d, "instalar", lineas.append, correr, datetime.now)
    except ki.KitInvalido as e:
        return False, str(e)
    except SystemctlNoResponde:
        return False, f"systemctl no respondió en {SYSTEMCTL_TIMEOUT} s: probá de nuevo."
    except OSError as e:
        return False, f"No pude instalar el kit: {e}"
    if rc == 0:
        return True, ""
    fallas = [ln.strip() for ln in lineas if ln.startswith(("FAILED", "ERROR", "  ERROR"))]
    return False, " ".join(fallas) or "No pude terminar la instalación del kit."


def build_router(
    kit_dir: Path | None = None,
    deploy_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    correr: Callable[[list[str]], int] | None = None,
) -> APIRouter:
    router = APIRouter()
    kdir = kit_dir or ki.KIT_DIR
    ddir = deploy_dir or ki.REPO_ROOT / "deploy"
    sh = {"Cache-Control": "no-store"}

    def _destinos() -> ki.Destinos:
        import os

        return ki.destinos(env if env is not None else os.environ, home or Path.home(), kdir)

    @router.get("/kit")
    def kit_estado() -> JSONResponse:
        cuerpo = {"estado": estado(kdir, ddir, _destinos()), **catalogo(kdir)}
        return JSONResponse(cuerpo, headers=sh)

    @router.get("/kit/regla/{rid}")
    def kit_regla(rid: str) -> JSONResponse:
        texto = texto_regla(kdir, rid)
        if texto is None:
            return JSONResponse({"error": "No encuentro esa regla"}, status_code=404, headers=sh)
        return JSONResponse({"id": rid, "texto": texto}, headers=sh)

    candado = threading.Lock()

    @router.post("/kit/arreglar")
    def kit_arreglar() -> JSONResponse:
        # Dos instalaciones a la vez se pisan los respaldos y los enlaces: la segunda espera su turno.
        if not candado.acquire(blocking=False):
            return JSONResponse({"error": "Ya se está arreglando el kit: esperá a que termine."},
                                status_code=409, headers=sh)
        try:
            d = _destinos()
            ok, error = arreglar(kdir, ddir, d, correr or _correr_systemctl)
        finally:
            candado.release()
        cuerpo: dict = {"ok": ok, "estado": estado(kdir, ddir, d)}
        if not ok:
            cuerpo["error"] = error
        return JSONResponse(cuerpo, headers=sh)

    return router
