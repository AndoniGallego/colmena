"""Resuelve y resume el objetivo de un pedido de cierre (sesión, pestaña o tarjeta) sin cerrar nada."""
from typing import Literal, Optional

from .cierre import CierreService

Objetivo = Literal["sesion", "pestana", "tarjeta"]


def _norm(texto) -> str:
    return (texto or "").strip().casefold()


def _coincide(sel: str, clave: str, ident, *nombres) -> bool:
    return bool(ident) and ident == sel or clave in {_norm(n) for n in nombres} - {""}


def resolver_objetivo(board: Optional[dict], objetivo: Objetivo, sel: str) -> tuple[Optional[dict], Optional[str]]:
    sel = (sel or "").strip()
    clave = sel.casefold()
    if not sel:
        return None, "cierre_no_encontrado"
    halladas: dict = {}
    compartidas: set = set()
    for ws in (board or {}).get("workspaces") or []:
        for tab in ws.get("tabs") or []:
            if objetivo == "tarjeta":
                if _coincide(sel, clave, ws.get("id"), ws.get("label")):
                    halladas[ws["id"]] = ("workspace", ws)
                continue
            if objetivo == "pestana":
                if _coincide(sel, clave, tab.get("id"), tab.get("label")):
                    halladas[tab["id"]] = ("tab", ws)
                continue
            for ag in tab.get("agents") or []:
                if _coincide(sel, clave, ag.get("pane_id"), ag.get("title"), tab.get("label")):
                    halladas[tab["id"]] = ("tab", ws)
                    if len(tab.get("agents") or []) + len(tab.get("terminales") or []) != 1:
                        compartidas.add(tab["id"])
        if objetivo == "tarjeta" and ws.get("id") in halladas:
            continue
    if not halladas:
        return None, "cierre_no_encontrado"
    if len(halladas) > 1:
        return None, "cierre_ambiguo"
    target_id, (tipo, ws) = next(iter(halladas.items()))
    if ws.get("pinned"):
        return None, "cierre_protegido"
    if target_id in compartidas:
        return None, "sesion_compartida"
    return {"objetivo": objetivo, "tipo": tipo, "target_id": target_id}, None


def resumen_cierre(objetivo: Objetivo, preview: dict) -> dict:
    panes = preview.get("panes") or []
    claude = [p for p in panes if p.get("kind") == "claude"]
    label = preview.get("label") or ""
    if objetivo == "sesion" and claude and claude[0].get("titulo"):
        label = claude[0]["titulo"]
    primero = (claude or panes or [{}])[0]
    return {
        "objetivo": objetivo, "tipo": preview.get("tipo"), "target_id": preview.get("target_id"), "label": label,
        "workspace_label": preview.get("workspace_label") or "", "carpeta": primero.get("cwd") or "",
        "sesiones": len(claude), "terminales": len(panes) - len(claude),
        "estructura": CierreService.estructura(preview),
    }


def vista_cierre(preview: dict) -> dict:
    bloqueantes = preview.get("bloqueantes") or []
    return {"trabajando": bool(bloqueantes), "estados": sorted({b["status"] for b in bloqueantes}),
            "huella": preview["huella"]}


def motivo_fin_lote(lote: dict) -> Optional[str]:
    if lote.get("vencido") or any(t.get("estado") == "error" for t in lote.get("targets") or []):
        return "cierre_no_hecho"
    return None
