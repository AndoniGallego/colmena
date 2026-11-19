import copy
import json

from conftest import make_snapshot
from orquestador.enchufe import como_snapshot
from orquestador.enchufe.fake import FakeTerminales
from orquestador.enchufe.herdr import info_de_process_json, tablero_de_snapshot
from orquestador.enchufe.modelo import InfoProceso

ANSI = "\x1b[32mlisto\x1b[0m\r\nsegunda\r\n"


def aplicar_snapshot(enchufe: FakeTerminales, snap: dict) -> None:
    rev = enchufe.tablero_actual.revision
    enchufe.tablero_actual = tablero_de_snapshot(copy.deepcopy(snap), rev)


def snap_de(enchufe: FakeTerminales) -> dict:
    return como_snapshot(enchufe.tablero_actual)


def process_info(argv, pid=100, group=None, name=None):
    return json.dumps({"id": "x", "result": {"process_info": {
        "foreground_process_group_id": pid if group is None else group,
        "foreground_processes": [{"argv": argv, "cmdline": " ".join(argv), "cwd": "/x", "name": name or argv[0], "pid": pid}],
        "pane_id": "p", "shell_pid": 1}}})


def info_proceso(argv, pid=100, group=None, name=None) -> InfoProceso:
    return info_de_process_json(process_info(argv, pid=pid, group=group, name=name))


def proceso_json(*procs, shell_pid=1):
    """JSON de process-info al estilo tests de cierre (nombres y pids)."""
    return json.dumps({"result": {"process_info": {"shell_pid": shell_pid, "foreground_processes": [
        {"name": n, "pid": pid, "cmdline": f"{n} --token=SECRETO"} for n, pid in procs]}}})


def proceso_argv_json(*procs, group=42):
    return json.dumps({"result": {"process_info": {"shell_pid": 1, "foreground_process_group_id": group,
                                                   "foreground_processes": [{"name": n, "pid": pid, "argv": argv}
                                                                            for n, pid, argv in procs]}}})


def set_proceso_todos(enchufe: FakeTerminales, raw) -> None:
    """Equivalente a herdr.responses['pane process-info'] para todos los pane_id del snapshot."""
    s = snap_de(enchufe)
    if isinstance(raw, Exception):
        val = raw
    elif isinstance(raw, str):
        val = info_de_process_json(raw)
    else:
        val = raw
    ids = {p["pane_id"] for p in s.get("panes", [])}
    ids |= {a["pane_id"] for a in s.get("agents", [])}
    for pid in ids:
        enchufe.procesos[pid] = val


def snapshot_con_terminales():
    snap = make_snapshot()
    snap["workspaces"].append({"workspace_id": "w3", "number": 3, "label": "Super orquestador", "agent_status": "idle"})
    snap["tabs"].append({"tab_id": "w3:t1", "workspace_id": "w3", "label": "super"})
    snap["panes"] += [
        {"pane_id": "w1:p5", "tab_id": "w1:t1", "workspace_id": "w1", "revision": 4,
         "terminal_title_stripped": "dev server", "foreground_cwd": "/tmp/proyecto"},
        {"pane_id": "w3:p1", "tab_id": "w3:t1", "workspace_id": "w3", "revision": 1,
         "terminal_title_stripped": "super shell", "foreground_cwd": "/tmp"},
    ]
    snap["agents"].append({"pane_id": "w3:p2", "tab_id": "w3:t1", "workspace_id": "w3", "agent": "claude",
                           "agent_status": "idle", "terminal_title_stripped": "claude del super"})
    snap["panes"].append({"pane_id": "w3:p2", "tab_id": "w3:t1", "workspace_id": "w3", "revision": 1})
    return snap


def _proceso_de_argv(argv) -> InfoProceso | Exception:
    if isinstance(argv, Exception):
        return argv
    return info_proceso(argv)


def make_terminales(procs=None, output=ANSI):
    """FakeTerminales con terminales; `procs` mapea pane_id -> argv (o Exception)."""
    snap = snapshot_con_terminales()
    for pane in snap.get("panes", []):
        pane.setdefault("terminal_id", f"term-{pane['pane_id']}")
    fake = FakeTerminales.desde_snapshot(snap)
    procs = dict(procs) if procs is not None else {}
    pane_ids = {p["pane_id"] for p in snap_de(fake).get("panes", [])} | set(procs)
    for pane_id in pane_ids:
        if pane_id in procs:
            fake.procesos[pane_id] = _proceso_de_argv(procs[pane_id])
        elif pane_id not in fake.procesos:
            fake.procesos[pane_id] = info_proceso(["bash"])
        fake.pantallas.setdefault(pane_id, output)
    return fake
