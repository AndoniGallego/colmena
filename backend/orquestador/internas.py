"""Sesiones internas (guía, Copiloto): no se muestran en ninguna vista de usuario.

Un pane es interno si su carpeta es la de un ayudante. `filtrar_snapshot` es para las vistas; lo que maneja
a los ayudantes (cerrar la pestaña del Copiloto, huérfanos de la guía) sigue usando el snapshot completo.
"""
import os
from typing import Callable, Iterable, Optional

EsInterna = Callable[[str], bool]

# Nombres con que la guía y el Copiloto crean su espacio; al cerrarse su pane, el espacio queda vacío.
NOMBRES_AYUDANTES = frozenset({"Guía", "Copiloto"})


def predicado_de_carpetas(carpetas: Iterable) -> EsInterna:
    reales = {os.path.realpath(str(c)) for c in carpetas}
    return lambda cwd: bool(cwd) and os.path.realpath(cwd) in reales


def pane_interno(pane: dict, es_interna: Optional[EsInterna]) -> bool:
    if es_interna is None:
        return False
    return any(es_interna(pane.get(k) or "") for k in ("cwd", "foreground_cwd"))


def filtrar_snapshot(snap: dict, es_interna: Optional[EsInterna]) -> dict:
    """Copia del snapshot sin panes internos, ni las pestañas y espacios que quedan vacíos por eso."""
    if es_interna is None:
        return snap
    snap = _sin_espacios_vacios_de_ayudantes(snap)
    todos = [p for k in ("panes", "agents") for p in snap.get(k, [])]
    internos = {p.get("pane_id") for p in todos if p.get("pane_id") and pane_interno(p, es_interna)}
    if not internos:
        return snap
    quedan = [p for p in todos if p.get("pane_id") not in internos]
    tabs_con_panes = {p.get("tab_id") for p in quedan}
    ws_con_panes = {p.get("workspace_id") for p in quedan}
    quitados_por_tab: dict = {}
    for p in todos:
        if p.get("pane_id") in internos and p.get("pane_id") not in quitados_por_tab:
            quitados_por_tab[p["pane_id"]] = (p.get("tab_id"), p.get("workspace_id"))
    tabs_tocadas = {t for t, _ in quitados_por_tab.values()}
    ws_tocados = {w for _, w in quitados_por_tab.values()}
    tabs_fuera = {t for t in tabs_tocadas if t not in tabs_con_panes}

    out = {k: v for k, v in snap.items() if k not in ("panes", "agents", "tabs", "workspaces")}
    out["panes"] = [p for p in snap.get("panes", []) if p.get("pane_id") not in internos]
    out["agents"] = [p for p in snap.get("agents", []) if p.get("pane_id") not in internos]
    por_tab = {t: sum(1 for pid, (tt, _) in quitados_por_tab.items() if tt == t) for t in tabs_tocadas}
    out["tabs"] = []
    for tab in snap.get("tabs", []):
        tid = tab.get("tab_id")
        if tid in tabs_fuera:
            continue
        if tid in por_tab and isinstance(tab.get("pane_count"), int):
            tab = {**tab, "pane_count": max(0, tab["pane_count"] - por_tab[tid])}
        out["tabs"].append(tab)
    tabs_vivas_por_ws = {t.get("workspace_id") for t in out["tabs"]}
    por_ws: dict = {}
    for tt, ww in quitados_por_tab.values():
        por_ws[ww] = por_ws.get(ww, 0) + 1
    out["workspaces"] = []
    for ws in snap.get("workspaces", []):
        wid = ws.get("workspace_id")
        if wid in ws_tocados and wid not in ws_con_panes and wid not in tabs_vivas_por_ws:
            continue
        if wid in por_ws and isinstance(ws.get("pane_count"), int):
            ws = {**ws, "pane_count": max(0, ws["pane_count"] - por_ws[wid])}
        out["workspaces"].append(ws)
    return out


def _sin_espacios_vacios_de_ayudantes(snap: dict) -> dict:
    con_algo = {x.get("workspace_id") for k in ("tabs", "panes", "agents") for x in snap.get(k, [])}
    vacios = {
        w.get("workspace_id") for w in snap.get("workspaces", [])
        if w.get("label") in NOMBRES_AYUDANTES and w.get("workspace_id") not in con_algo
    }
    if not vacios:
        return snap
    return {**snap, "workspaces": [w for w in snap["workspaces"] if w.get("workspace_id") not in vacios]}
