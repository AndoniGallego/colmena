from .modelo import Sesion, Tablero


def _sin_nones(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _sesion_a_pane(s: Sesion) -> dict:
    out = {
        "pane_id": s.id,
        "tab_id": s.linea_id,
        "workspace_id": s.espacio_id,
        "cwd": s.cwd or None,
        "foreground_cwd": s.cwd_primer_plano,
        "terminal_title_stripped": s.titulo or None,
        "terminal_title": s.titulo_crudo,
        "revision": s.revision,
        "terminal_id": s.terminal_id,
        "agent": s.agente,
        "agent_status": s.estado_crudo,
        "state_change_seq": s.seq,
        "name": s.nombre_agente,
    }
    if s.claude_session_tipo or s.claude_session_id:
        out["agent_session"] = _sin_nones({"kind": s.claude_session_tipo, "value": s.claude_session_id})
    return _sin_nones(out)


def como_snapshot(t: Tablero) -> dict:
    por_tab: dict[str, list] = {l.id: list(l.sesiones) for l in t.lineas}
    for s in t.sesiones:
        por_tab.setdefault(s.linea_id, [])
        if s.id not in por_tab[s.linea_id]:
            por_tab[s.linea_id].append(s.id)

    def pane_count_linea(lid: str, declaradas: int | None) -> int:
        if declaradas is not None:
            return declaradas
        return len(por_tab.get(lid, ()))

    panes = [_sesion_a_pane(s) for s in t.sesiones]
    agents = [_sesion_a_pane(s) for s in t.sesiones if s.es_agente]

    workspaces = [
        _sin_nones({
            "workspace_id": e.id,
            "label": e.nombre or None,
            "number": e.numero,
            "agent_status": e.estado_crudo,
            "pane_count": e.declaradas if e.declaradas is not None else sum(
                1 for s in t.sesiones if s.espacio_id == e.id
            ),
        })
        for e in t.espacios
    ]

    tabs = [
        _sin_nones({
            "tab_id": l.id,
            "workspace_id": l.espacio_id,
            "label": l.nombre or None,
            "pane_count": pane_count_linea(l.id, l.declaradas),
        })
        for l in t.lineas
    ]

    out = {
        "workspaces": workspaces,
        "tabs": tabs,
        "panes": panes,
        "agents": agents,
    }
    if t.linea_enfocada:
        out["focused_tab_id"] = t.linea_enfocada
    if t.conflictos:
        out["conflictos"] = list(t.conflictos)
    if t.caidos:
        out["caidos"] = list(t.caidos)
    return out
