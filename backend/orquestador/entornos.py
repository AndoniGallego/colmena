from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.requests import Request

from orquestador import kit_trabajo
from orquestador.config import Config

DOCKER_TIMEOUT = 5.0
Runner = Callable[[list], Awaitable[tuple]]

APOYO = ("db", "cache", "mailhog", "mock", "payfake", "floci")
PUERTOS_BLOQUEADOS = frozenset({8770, 8771, 2375, 2376, 2377, 7437})
NOMBRE_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


def _spec_a_enteros(spec: str) -> list[int] | None:
    spec = spec.strip()
    if "-" in spec:
        a, b = spec.split("-", 1)
        try:
            ia, ib = int(a), int(b)
        except ValueError:
            return None
        if ia > ib:
            return None
        return list(range(ia, ib + 1))
    try:
        return [int(spec)]
    except ValueError:
        return None


def _puertos_host_desde_izquierda(izq: str) -> str | None:
    izq = izq.strip()
    if izq.startswith("["):
        fin = izq.find("]:")
        if fin == -1:
            return None
        return izq[fin + 2 :]
    if ":" not in izq:
        return None
    return izq.rsplit(":", 1)[1]


def parsear_puertos(ports: str) -> list[tuple[int, int]]:
    if not ports or not ports.strip():
        return []
    vistos: set[int] = set()
    salida: list[tuple[int, int]] = []
    for trozo in ports.split(","):
        trozo = trozo.strip()
        if not trozo or "->" not in trozo or "/tcp" not in trozo:
            continue
        if "/udp" in trozo:
            continue
        try:
            izq, der = trozo.rsplit("->", 1)
        except ValueError:
            continue
        der = der.strip()
        if not der.endswith("/tcp"):
            continue
        spec_cont = der[: -len("/tcp")].strip()
        spec_host = _puertos_host_desde_izquierda(izq)
        if spec_host is None:
            continue
        hosts = _spec_a_enteros(spec_host)
        conts = _spec_a_enteros(spec_cont)
        if not hosts or not conts or len(hosts) != len(conts):
            continue
        for h, c in zip(hosts, conts, strict=True):
            if h in vistos:
                continue
            vistos.add(h)
            salida.append((h, c))
    return salida


def parsear_labels(labels: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not labels:
        return out
    for pedazo in labels.split(","):
        if "=" not in pedazo:
            continue
        clave, valor = pedazo.split("=", 1)
        clave = clave.strip()
        if clave:
            out[clave] = valor.strip()
    return out


def carpeta_corta(path: str, home: str) -> str:
    if path == home:
        return "~"
    pref = home + "/"
    if path.startswith(pref):
        return "~" + path[len(home) :]
    return path


def _servicio_tiene_apoyo(servicio: str) -> bool:
    s = servicio.lower()
    return any(p in s for p in (*APOYO, *(a.lower() for a in kit_trabajo.valor("apoyo_entornos"))))


def elegir_principal(puertos: list[dict]) -> Optional[int]:
    abribles = [x for x in puertos if x.get("abrible")]
    if not abribles:
        return None
    candidatos = [x for x in abribles if not _servicio_tiene_apoyo(x.get("servicio") or "")]
    usar = candidatos if candidatos else abribles
    for pref in (80, 3000):
        for x in usar:
            if x.get("puerto_contenedor") == pref:
                return x["puerto"]
    return usar[0]["puerto"]


def _es_abrible(puerto: int, bloqueados: frozenset[int] | set[int]) -> bool:
    return puerto >= 1024 and puerto not in bloqueados


_CODIGO_SERVICIO_RE = re.compile(r"(?:Exited|Restarting)\s*\((\d+)\)", re.IGNORECASE)
_HACE_RELATIVO_RE = re.compile(
    r"(?:(\d+)\s+(second|minute|hour|day|week|month|year)s?|About an? (?:minute|hour)|Less than a second)\s+ago\s*$",
    re.IGNORECASE,
)
_HACE_UNIDAD = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2592000,
    "year": 31536000,
}
_ESTADOS_ACTIVOS = frozenset({"corriendo", "arrancando", "enfermo", "reiniciando", "pausado"})
_CODIGOS_APAGADO = frozenset({0, 137, 143})


def _hace_s_desde_status(status: str) -> int | None:
    if not status or " ago" not in status:
        return None
    m = _HACE_RELATIVO_RE.search(status)
    if not m:
        return None
    trozo = status[m.start() : m.end()].lower()
    if trozo.startswith("less than a second"):
        return 0
    if trozo.startswith("about a minute"):
        return 60
    if trozo.startswith("about an hour"):
        return 3600
    cant = m.group(1)
    unidad = m.group(2)
    if cant is None or unidad is None:
        return None
    mult = _HACE_UNIDAD.get(unidad.lower())
    if mult is None:
        return None
    return int(cant) * mult


def estado_servicio(state: str, status: str) -> tuple[str, int | None, int | None]:
    state_l = (state or "").strip().lower()
    status_s = status or ""
    codigo: int | None = None
    cm = _CODIGO_SERVICIO_RE.search(status_s)
    if cm:
        codigo = int(cm.group(1))
    if state_l == "running":
        if "(unhealthy)" in status_s:
            estado = "enfermo"
        elif "(health: starting)" in status_s:
            estado = "arrancando"
        elif "(Paused)" in status_s:
            estado = "pausado"
        else:
            estado = "corriendo"
    elif state_l == "restarting":
        estado = "reiniciando"
    elif state_l == "paused":
        estado = "pausado"
    elif state_l == "exited" and codigo == 0:
        estado = "terminado"
    else:
        estado = "caido"
    hace_s: int | None = None
    if estado in ("caido", "reiniciando", "terminado"):
        hace_s = _hace_s_desde_status(status_s)
    return (estado, codigo, hace_s)


def _grupo_servicio(estado: str) -> int:
    if estado == "corriendo":
        return 1
    if estado == "terminado":
        return 2
    return 0


def _ordenar_servicios(servicios: list[dict]) -> list[dict]:
    return sorted(servicios, key=lambda s: (_grupo_servicio(s["estado"]), s["servicio"]))


def _salud_entorno(servicios: list[dict]) -> str:
    activos = [s for s in servicios if s["estado"] != "terminado"]
    if not activos:
        return "rojo"
    estados = [s["estado"] for s in activos]
    if all(e == "corriendo" for e in estados):
        return "verde"
    if not any(e in _ESTADOS_ACTIVOS for e in estados):
        return "rojo"
    return "amarillo"


def _entorno_apagado(servicios: list[dict]) -> bool:
    if not servicios or not all(s["estado"] in ("caido", "terminado") for s in servicios):
        return False
    if all(s.get("codigo") in _CODIGOS_APAGADO for s in servicios):
        return True
    conocidos = [s["hace_s"] for s in servicios if s.get("hace_s") is not None]
    if conocidos and min(conocidos) > 86400:
        return True
    return False


def armar_entornos(salida: str, cfg: Config, home: str) -> list[dict]:
    bloqueados_extra = PUERTOS_BLOQUEADOS | {cfg.port, cfg.viewer_port}
    por_nombre: dict[str, dict] = {}
    puertos_docker: set[int] = set()

    for linea in salida.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            obj = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        labels_txt = obj.get("Labels")
        if not isinstance(labels_txt, str):
            labels_txt = ""
        labels = parsear_labels(labels_txt)
        proyecto = labels.get("com.docker.compose.project")
        if not proyecto or not NOMBRE_RE.match(proyecto):
            continue
        wd = str(labels.get("com.docker.compose.project.working_dir") or "")
        servicio = labels.get("com.docker.compose.service")
        if not servicio:
            names = obj.get("Names")
            servicio = (names.split("/")[-1] if isinstance(names, str) and names else "") or "unknown"
        ports_txt = obj.get("Ports")
        if not isinstance(ports_txt, str):
            ports_txt = ""
        pares = parsear_puertos(ports_txt)
        for h, _ in pares:
            puertos_docker.add(h)
        state_txt = obj.get("State")
        status_txt = obj.get("Status")
        est, cod, hace = estado_servicio(
            state_txt if isinstance(state_txt, str) else "",
            status_txt if isinstance(status_txt, str) else "",
        )
        if proyecto not in por_nombre:
            por_nombre[proyecto] = {
                "nombre": proyecto,
                "carpeta": carpeta_corta(wd, home),
                "_vistos": set(),
                "_filas": [],
                "_servicios": [],
            }
        ent = por_nombre[proyecto]
        ent["_servicios"].append({
            "servicio": servicio,
            "estado": est,
            "codigo": cod,
            "hace_s": hace,
        })
        vistos: set[int] = ent["_vistos"]
        for h, c in pares:
            if h in vistos:
                continue
            vistos.add(h)
            ent["_filas"].append((h, servicio, c))

    nombres_usados = set(por_nombre.keys())
    resultado: list[dict] = []

    for nombre in sorted(por_nombre.keys()):
        ent = por_nombre[nombre]
        filas = sorted(ent["_filas"], key=lambda t: t[0])
        puertos_list: list[dict] = []
        for h, servicio, c in filas:
            puertos_list.append({
                "puerto": h,
                "servicio": servicio,
                "puerto_contenedor": c,
                "abrible": _es_abrible(h, bloqueados_extra),
            })
        override = cfg.entornos_principal.get(nombre) if isinstance(cfg.entornos_principal, dict) else None
        if override is not None and any(x["puerto"] == override and x["abrible"] for x in puertos_list):
            principal = override
        else:
            principal = elegir_principal(puertos_list)
        servicios = _ordenar_servicios(ent["_servicios"])
        resultado.append({
            "nombre": nombre,
            "carpeta": ent["carpeta"],
            "principal": principal,
            "puertos": puertos_list,
            "servicios": servicios,
            "salud": _salud_entorno(servicios),
            "apagado": _entorno_apagado(servicios),
        })

    extra_cfg = cfg.entornos_extra if isinstance(cfg.entornos_extra, list) else []
    for item in extra_cfg:
        if not isinstance(item, dict):
            continue
        nom = item.get("nombre")
        if not isinstance(nom, str) or not NOMBRE_RE.match(nom) or nom in nombres_usados:
            continue
        raw_ports = item.get("puertos")
        if not isinstance(raw_ports, list):
            continue
        filtrados: list[int] = []
        for x in raw_ports:
            if not isinstance(x, int) or isinstance(x, bool) or not (1 <= x <= 65535):
                continue
            if x in puertos_docker:
                continue
            filtrados.append(x)
        if not filtrados:
            continue
        puertos_ex: list[dict] = []
        for pu in sorted(set(filtrados)):
            puertos_ex.append({
                "puerto": pu,
                "servicio": nom,
                "puerto_contenedor": None,
                "abrible": _es_abrible(pu, bloqueados_extra),
            })
        decl = item.get("principal")
        if isinstance(decl, int) and any(
            d["puerto"] == decl and d["abrible"] for d in puertos_ex
        ):
            pr = decl
        else:
            pr = elegir_principal(puertos_ex)
        resultado.append({
            "nombre": nom,
            "carpeta": "",
            "principal": pr,
            "puertos": puertos_ex,
            "servicios": [],
            "salud": None,
            "apagado": False,
        })
        nombres_usados.add(nom)

    resultado.sort(key=lambda e: (e["apagado"], e["nombre"]))
    return resultado


def docker_bin(cfg: Config) -> str:
    return cfg.docker_bin or shutil.which("docker") or ""


async def correr_docker(args: list) -> tuple:
    env = {**os.environ, "LC_ALL": "C"}
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=DOCKER_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    except BaseException:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        raise
    return (proc.returncode or 0, stdout, stderr)


async def listar(cfg: Config, runner: Runner, home: str) -> dict:
    bin_path = docker_bin(cfg)
    if not bin_path:
        return {"entornos": [], "error": "No encuentro docker en la notebook"}
    try:
        rc, out, _err = await runner([bin_path, "ps", "-a", "--format", "{{json .}}"])
    except Exception:
        return {"entornos": [], "error": "Docker no responde"}
    if rc != 0:
        return {"entornos": [], "error": "Docker no responde"}
    return {"entornos": armar_entornos(out.decode(errors="replace"), cfg, home), "error": None}


def build_router(
    cfg: Config,
    runner: Optional[Runner] = None,
    probador=None,
) -> APIRouter:
    router = APIRouter()
    ejecutar: Runner = runner or correr_docker

    @router.get("/entornos")
    async def listar_entornos() -> JSONResponse:
        cuerpo = await listar(cfg, ejecutar, str(Path.home()))
        return JSONResponse(content=cuerpo, headers={"Cache-Control": "no-store"})

    if probador is None:
        from .entornos_probador import Probador

        probador = Probador(lambda: listar(cfg, ejecutar, str(Path.home())))

    def _err(codigo: int, msg: str) -> JSONResponse:
        return JSONResponse(
            status_code=codigo,
            content={"error": msg},
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/entornos/probar")
    async def entornos_probar(request: Request) -> JSONResponse:
        from .entornos_probador import MAX_PEDIDO_BYTES, MSG_PEDIDO_INVALIDO

        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                tam = int(cl)
            except ValueError:
                return _err(400, MSG_PEDIDO_INVALIDO)
            if tam > MAX_PEDIDO_BYTES:
                return _err(413, "Pedido demasiado grande")
        trozos: list[bytes] = []
        leido = 0
        async for bloque in request.stream():
            leido += len(bloque)
            if leido > MAX_PEDIDO_BYTES:
                return _err(413, "Pedido demasiado grande")
            trozos.append(bloque)
        try:
            datos = json.loads(b"".join(trozos) if trozos else b"null")
        except Exception:
            return _err(400, MSG_PEDIDO_INVALIDO)
        if not isinstance(datos, dict):
            return _err(400, MSG_PEDIDO_INVALIDO)
        codigo, cuerpo = await probador.probar(datos)
        return JSONResponse(
            status_code=codigo,
            content=cuerpo,
            headers={"Cache-Control": "no-store"},
        )

    return router
