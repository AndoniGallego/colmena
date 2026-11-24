import copy

import pytest

from orquestador.internas import filtrar_snapshot, pane_interno, predicado_de_carpetas
from orquestador.terminales import Terminales
from orquestador.traspaso import TraspasoError

GUIA = "/data/orq/guia"
COPILOTO = "/data/orq/reunion-copiloto"


def _es_interna():
    return predicado_de_carpetas([GUIA, COPILOTO])


def _pane(pid, tab, ws, cwd, agente=False):
    d = {"pane_id": pid, "tab_id": tab, "workspace_id": ws, "cwd": cwd}
    if agente:
        d["agent"] = "claude"
    return d


def snapshot_sintetico():
    """w1 normal; w2 solo interno (guía); w3 mixto: t1 normal, t2 solo interno (Copiloto)."""
    panes = [
        _pane("w1:p1", "w1:t1", "w1", "/work/a", True),
        _pane("w2:p1", "w2:t1", "w2", GUIA, True),
        _pane("w3:p1", "w3:t1", "w3", "/work/b"),
        _pane("w3:p2", "w3:t2", "w3", COPILOTO, True),
    ]
    return {
        "workspaces": [
            {"workspace_id": "w1", "number": 1, "label": "Uno", "pane_count": 1},
            {"workspace_id": "w2", "number": 2, "label": "Guia", "pane_count": 1},
            {"workspace_id": "w3", "number": 3, "label": "Mixto", "pane_count": 2},
        ],
        "tabs": [
            {"tab_id": "w1:t1", "workspace_id": "w1", "pane_count": 1},
            {"tab_id": "w2:t1", "workspace_id": "w2", "pane_count": 1},
            {"tab_id": "w3:t1", "workspace_id": "w3", "pane_count": 1},
            {"tab_id": "w3:t2", "workspace_id": "w3", "pane_count": 1},
        ],
        "panes": copy.deepcopy(panes),
        "agents": [p for p in copy.deepcopy(panes) if p.get("agent")],
    }


def test_predicado_compara_rutas_reales_y_no_prefijos():
    es = _es_interna()
    assert es(GUIA) and es(COPILOTO + "/")
    assert not es(GUIA + "/sub") and not es("/data/orq/guia-otra") and not es("")


def test_pane_interno_mira_cwd_y_cwd_en_primer_plano():
    es = _es_interna()
    assert pane_interno({"cwd": GUIA}, es)
    assert pane_interno({"cwd": "/x", "foreground_cwd": COPILOTO}, es)
    assert not pane_interno({"cwd": "/x"}, es)


def test_filtrar_snapshot_saca_panes_tabs_y_espacios_internos():
    snap = filtrar_snapshot(snapshot_sintetico(), _es_interna())
    assert [w["workspace_id"] for w in snap["workspaces"]] == ["w1", "w3"]
    assert [t["tab_id"] for t in snap["tabs"]] == ["w1:t1", "w3:t1"]
    assert sorted(p["pane_id"] for p in snap["panes"]) == ["w1:p1", "w3:p1"]
    assert [a["pane_id"] for a in snap["agents"]] == ["w1:p1"]
    mixto = next(w for w in snap["workspaces"] if w["workspace_id"] == "w3")
    assert mixto["pane_count"] == 1


def test_filtrar_snapshot_no_muta_el_original_ni_toca_lo_vacio_preexistente():
    original = snapshot_sintetico()
    original["workspaces"].append({"workspace_id": "w9", "number": 9, "label": "nuevo"})
    antes = copy.deepcopy(original)
    snap = filtrar_snapshot(original, _es_interna())
    assert original == antes
    assert "w9" in [w["workspace_id"] for w in snap["workspaces"]]


def test_filtrar_sin_predicado_devuelve_igual():
    original = snapshot_sintetico()
    assert filtrar_snapshot(original, None) == original


def test_terminales_locate_no_encuentra_panes_internos():
    t = Terminales(None, None, lambda: set())
    t.interna = _es_interna()
    snap = snapshot_sintetico()
    with pytest.raises(TraspasoError) as exc:
        t.locate(snap, "w3:p2")
    assert exc.value.status == 404
    assert t.locate(snap, "w3:p1")["pane_id"] == "w3:p1"


def test_terminales_locate_sin_predicado_sigue_igual():
    t = Terminales(None, None, lambda: set())
    with pytest.raises(TraspasoError) as exc:
        t.locate(snapshot_sintetico(), "w3:p2")
    assert exc.value.status == 403


def test_filtrar_snapshot_saca_espacio_vacio_que_dejo_un_ayudante():
    """Al cerrarse el pane de la guía, su espacio queda sin pestañas ni panes: no se muestra."""
    original = snapshot_sintetico()
    original["workspaces"] += [
        {"workspace_id": "g1", "number": 11, "label": "Guía", "pane_count": 0},
        {"workspace_id": "g2", "number": 12, "label": "Copiloto", "pane_count": 0},
        {"workspace_id": "w9", "number": 9, "label": "nuevo"},
    ]
    snap = filtrar_snapshot(original, _es_interna())
    assert [w["workspace_id"] for w in snap["workspaces"]] == ["w1", "w3", "w9"]


def test_espacio_guia_con_sesiones_de_ando_sigue_visible():
    original = snapshot_sintetico()
    original["workspaces"].append({"workspace_id": "w5", "number": 5, "label": "Guía", "pane_count": 1})
    original["tabs"].append({"tab_id": "w5:t1", "workspace_id": "w5", "pane_count": 1})
    original["panes"].append(_pane("w5:p1", "w5:t1", "w5", "/work/c"))
    snap = filtrar_snapshot(original, _es_interna())
    assert "w5" in [w["workspace_id"] for w in snap["workspaces"]]
