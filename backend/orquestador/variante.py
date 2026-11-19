import json
import re
import unicodedata
import uuid
from pathlib import Path

from .traspaso import CONTROL_RE, NAME_RE, TraspasoBody, TraspasoError, _now, resolve_brief

ORIGIN_PANE = re.compile(r"\(([^()]+)\)\s*$")
NAME_SPLIT = re.compile(r"^(.*?)\s*\([^()]+\)\s*$")


def _clean(text: str, limit: int) -> str:
    return CONTROL_RE.sub(" ", text or "").strip().lstrip("-").strip()[:limit]


def _slug(label: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9_-]+", "-", ascii_text).strip("-_")
    slug = re.sub(r"^[^a-z]+", "", slug)[:32].rstrip("-_")
    return slug if NAME_RE.match(slug) else "traspaso"


def _find(board: dict, pane: str):
    for ws in board.get("workspaces", []):
        for tab in ws.get("tabs", []):
            for agent in tab.get("agents", []):
                if agent.get("pane_id") == pane:
                    return ws, tab, agent
    return None


def proponer(body: TraspasoBody, board: dict, handoffs: Path) -> dict:
    """Arma, sin llamar a Claude, la propuesta de traspaso con otro tipo de destino; devuelve el mensaje de la propuesta."""
    kind = body.destino_tipo
    if kind == "existente":
        raise TraspasoError(422, "el traspaso a una sesión existente no se puede armar desde acá")
    brief = str(resolve_brief(handoffs, body.brief_path))
    match = ORIGIN_PANE.search(body.origen or "")
    origin = _find(board, match.group(1)) if match else None
    dest_pane = _find(board, body.pane_id) if body.pane_id else None
    named = NAME_SPLIT.match(body.destino or "")
    dest_name = named.group(1) if named else (body.destino or "")

    cwd = body.cwd or (origin[2].get("cwd") if origin else "")
    if not cwd:
        raise TraspasoError(422, "no pude determinar el directorio del traspaso")
    plan = {"origen": body.origen, "por_que": body.por_que, "resumen_brief": body.resumen_brief,
            "destino_tipo": kind, "cwd": cwd, "brief_path": brief}
    if kind == "tab_nuevo":
        ws = dest_pane[0] if dest_pane else (origin[0] if origin else None)
        wid = body.workspace_id or (ws or {}).get("id")
        if not wid:
            raise TraspasoError(422, "no pude determinar el workspace del tab nuevo")
        ws = ws if ws and ws.get("id") == wid else next((w for w in board.get("workspaces", []) if w.get("id") == wid), None)
        label = _clean(body.label or dest_name or (origin[1].get("label") if origin else ""), 60)
        plan["workspace_id"] = wid
        where = f"Tab nuevo en {(ws or {}).get('label') or wid}"
    else:
        label = _clean(body.label or dest_name or (origin[0].get("label") if origin else ""), 60)
        where = "Workspace nuevo"
    if not label:
        raise TraspasoError(422, "no pude armar un nombre para el destino")
    agent = body.agent_name if body.agent_name and NAME_RE.match(body.agent_name) else _slug(label)
    plan.update({"label": label, "agent_name": agent, "destino": f"{where} · {label}"[:200]})
    block = json.dumps(plan, ensure_ascii=False, indent=1)
    text = f"Listo, lo preparé como {where.lower()}. Revisalo y tocá Mandar.\n\n```traspaso\n{block}\n```"
    return {"id": uuid.uuid4().hex, "role": "assistant", "text": text, "ts": _now()}
