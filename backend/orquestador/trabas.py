"""Detección pura de sesiones trabadas o en loop a partir del transcript del turno actual."""
import json
import re
from dataclasses import dataclass, fields
from datetime import datetime

from .subagentes import EDIT_TOOLS

EXCLUIDAS_REPETICION = frozenset({"BashOutput", "TaskOutput", "TaskList", "Monitor", "ScheduleWakeup"})
ESPERA_USUARIO = frozenset({"AskUserQuestion", "ExitPlanMode"})
_CD = re.compile(r"^\s*cd\s+\S+\s*&&\s*")
_EXIT = re.compile(r"^\s*Exit code\s+(\d+)", re.I)


@dataclass(frozen=True)
class Umbrales:
    repetidas: int = 4
    ventana: int = 12
    fallas: int = 4
    bash_timeout_default: float = 120.0
    bash_timeout_tope: float = 600.0
    bash_margen: float = 90.0
    herramienta: float = 600.0
    quieta: float = 600.0

    @classmethod
    def de_dict(cls, raw) -> "Umbrales":
        base = cls()
        if not isinstance(raw, dict):
            return base
        out = {}
        for f in fields(cls):
            v = raw.get(f.name)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                out[f.name] = type(getattr(base, f.name))(v)
        return cls(**out)


@dataclass(frozen=True)
class Traba:
    tipo: str
    firma: str
    desde: float
    detalle: str


def _epoch(stamp):
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def _bloques(obj: dict) -> list:
    content = (obj.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _texto(block: dict) -> str:
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in c)
    return ""


def _es_prompt(obj: dict) -> bool:
    if obj.get("type") != "user" or obj.get("isMeta"):
        return False
    content = (obj.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    return isinstance(content, list) and not any(b.get("type") == "tool_result" for b in _bloques(obj)) and bool(
        _bloques(obj))


def _llamadas_del_turno(lineas) -> list:
    """[{id, name, inp, ts, resultado: None | {error, texto}}] desde el último prompt real."""
    llamadas: list = []
    por_id: dict = {}
    for linea in lineas:
        try:
            obj = json.loads(linea)
        except (TypeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        if _es_prompt(obj):
            llamadas, por_id = [], {}
            continue
        for b in _bloques(obj):
            if b.get("type") == "tool_use" and isinstance(b.get("id"), str) and isinstance(b.get("name"), str):
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                item = {"id": b["id"], "name": b["name"], "inp": inp, "ts": _epoch(obj.get("timestamp")),
                        "resultado": None}
                llamadas.append(item)
                por_id[b["id"]] = item
            elif b.get("type") == "tool_result":
                item = por_id.get(b.get("tool_use_id"))
                if item is not None:
                    texto = _texto(b)
                    item["resultado"] = {"error": bool(b.get("is_error")) or bool(_EXIT.match(texto)
                                                                                  and _EXIT.match(texto).group(1) != "0"),
                                         "texto": texto}
    return llamadas


def _firma(item: dict) -> str:
    inp = {k: v for k, v in item["inp"].items() if k != "description"}
    return item["name"] + ":" + json.dumps(inp, sort_keys=True, ensure_ascii=False, default=str)


def _comando(item: dict) -> str:
    cmd = item["inp"].get("command")
    cmd = cmd if isinstance(cmd, str) else ""
    return " ".join(_CD.sub("", cmd).split())


def _repetidas(llamadas: list, u: Umbrales):
    ventana = llamadas[-u.ventana:]
    ultimo_edit = max((i for i, c in enumerate(ventana) if c["name"] in EDIT_TOOLS), default=-1)
    cuenta: dict = {}
    for i, c in enumerate(ventana):
        if c["name"] in EXCLUIDAS_REPETICION:
            continue
        if c["name"] == "Read" and i < ultimo_edit:
            continue
        cuenta.setdefault(_firma(c), []).append(c)
    for firma, items in cuenta.items():
        if len(items) >= u.repetidas:
            primero = items[0]
            return Traba("repetida", firma, primero["ts"] or 0.0,
                         f"{primero['name']} repetido {len(items)} veces con lo mismo")
    return None


def _fallando(llamadas: list, u: Umbrales):
    rachas: dict = {}
    for c in llamadas:
        if c["name"] != "Bash" or c["resultado"] is None:
            continue
        cmd = _comando(c)
        if not cmd:
            continue
        if c["resultado"]["error"]:
            rachas.setdefault(cmd, []).append(c)
        else:
            rachas.pop(cmd, None)
    for cmd, items in rachas.items():
        if len(items) >= u.fallas:
            return Traba("fallando", cmd, items[0]["ts"] or 0.0, f"{cmd[:80]} falló {len(items)} veces")
    return None


def _limite_pendiente(c: dict, u: Umbrales, subagentes_activos: bool):
    name, inp = c["name"], c["inp"]
    if name in ESPERA_USUARIO:
        return None
    if name == "Agent":
        return None if subagentes_activos else u.herramienta
    if name == "Bash":
        t = inp.get("timeout")
        seg = t / 1000 if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0 else u.bash_timeout_default
        return min(seg, u.bash_timeout_tope) + u.bash_margen
    if name == "Monitor":
        t = inp.get("timeout_ms") or inp.get("timeout")
        if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0:
            return t / 1000 + u.bash_margen
    return u.herramienta


def _colgada(llamadas: list, ahora: float, subagentes_activos: bool, u: Umbrales):
    pendientes = [c for c in llamadas if c["resultado"] is None and c["ts"] is not None]
    for c in pendientes:
        limite = _limite_pendiente(c, u, subagentes_activos)
        if limite is not None and ahora - c["ts"] > limite:
            return Traba("colgada", c["id"], c["ts"], f"{c['name']} sin respuesta hace {int((ahora - c['ts']) // 60)} min")
    return None


def detectar(lineas, ahora, *, fondo=(), subagentes_activos=False, mtime=None, umbrales=None) -> list:
    """Trabas del turno en curso de una sesión en `working`. No toca nada, solo mira."""
    u = umbrales or Umbrales()
    llamadas = _llamadas_del_turno(lineas)
    out = []
    for traba in (_repetidas(llamadas, u), _fallando(llamadas, u),
                  _colgada(llamadas, ahora, subagentes_activos, u)):
        if traba is not None:
            out.append(traba)
    hay_pendiente = any(c["resultado"] is None for c in llamadas)
    if (mtime is not None and not hay_pendiente and not fondo and not subagentes_activos
            and ahora - mtime >= u.quieta):
        out.append(Traba("quieta", "quieta", mtime, f"Sin actividad hace {int((ahora - mtime) // 60)} min"))
    return out
