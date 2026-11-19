import asyncio, json
from pathlib import Path
import pytest
from conftest import FakeHerdr, make_snapshot
from terminales_support import snapshot_con_terminales
from orquestador.enchufe.herdr import tablero_de_snapshot
from orquestador.enchufe.vista import como_snapshot

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "herdr-snapshot-sample.json"
CAMPOS = ("pane_id", "tab_id", "workspace_id", "cwd", "foreground_cwd", "terminal_title_stripped", "terminal_title",
          "revision", "terminal_id", "agent", "agent_status", "agent_session", "state_change_seq", "name")

def _merged(snap):
    out = {}
    for src in ("panes", "agents"):
        for p in snap.get(src, []):
            out[p["pane_id"]] = {**out.get(p["pane_id"], {}), **p}
    return {k: {c: v.get(c) for c in CAMPOS} | ({"agent_session": {"kind": v["agent_session"].get("kind"), "value": v["agent_session"].get("value")}} if v.get("agent_session") else {}) for k, v in out.items()}

def _fuentes():
    sample = json.loads(SAMPLE.read_text())["result"]["snapshot"] if SAMPLE.exists() else None
    return {"make_snapshot": asyncio.run(FakeHerdr().snapshot()),
            "terminales": asyncio.run(FakeHerdr(snapshot_con_terminales()).snapshot()), "sample": sample}

@pytest.mark.parametrize("nombre", ["make_snapshot", "terminales", "sample"])
def test_ida_y_vuelta_conserva_lo_que_leen_los_consumidores(nombre):
    if nombre == "sample" and not SAMPLE.exists():
        pytest.skip("el repo publicado no trae la muestra de herdr")
    snap = _fuentes()[nombre]
    vista = como_snapshot(tablero_de_snapshot(snap))
    assert _merged(vista) == _merged(snap)
    assert [a["pane_id"] for a in vista["agents"]] == [a["pane_id"] for a in snap["agents"]]
    assert [(w["workspace_id"], w.get("label"), w.get("number"), w.get("agent_status"), w.get("pane_count"))
            for w in vista["workspaces"]] == [(w["workspace_id"], w.get("label"), w.get("number"), w.get("agent_status"),
                                               w.get("pane_count")) for w in snap["workspaces"]]
    assert [(t["tab_id"], t["workspace_id"], t.get("label"), t.get("pane_count")) for t in vista["tabs"]] == \
           [(t["tab_id"], t["workspace_id"], t.get("label"), t.get("pane_count")) for t in snap["tabs"]]
    assert vista.get("focused_tab_id") == snap.get("focused_tab_id")

def test_ids_pasan_intactos():
    if not SAMPLE.exists():
        pytest.skip("el repo publicado no trae la muestra de herdr")
    t = tablero_de_snapshot(_fuentes()["sample"])
    assert "w5:pH" in {s.id for s in t.sesiones} and "w6:t1" in {l.id for l in t.lineas}

def test_pane_sin_tab_o_workspace_se_omite_sin_romper():
    snap = make_snapshot()
    snap["panes"].append({"pane_id": "w1:p99", "workspace_id": "w1"})
    t = tablero_de_snapshot(snap)
    assert "w1:p99" not in {s.id for s in t.sesiones}


def test_id_con_forma_de_guardian_no_se_expone_y_queda_como_conflicto():
    snap = make_snapshot()
    snap["tabs"].append({"tab_id": "g7:t1", "workspace_id": "w1", "label": "raro"})
    snap["panes"].append({"pane_id": "g7:p1", "tab_id": "g7:t1", "workspace_id": "w1"})
    t = tablero_de_snapshot(snap)
    assert "g7:p1" not in {s.id for s in t.sesiones} and "g7:t1" not in {l.id for l in t.lineas}
    assert t.conflictos == ("g7:p1", "g7:t1")
    assert como_snapshot(t)["conflictos"] == ["g7:p1", "g7:t1"]
