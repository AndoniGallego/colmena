import json
from dataclasses import dataclass

from conftest import FakeHerdr, make_snapshot
from orquestador.enchufe.base import Tiempo
from orquestador.enchufe.fake import FakeTerminales
from orquestador.enchufe.herdr import AdaptadorHerdr, HerdrError


def _ids_en_snapshot(snap: dict) -> set[str]:
    ids: set[str] = set()
    for pane in snap.get("panes", []) + snap.get("agents", []):
        if pid := pane.get("pane_id"):
            ids.add(pid)
    for tab in snap.get("tabs", []):
        if tid := tab.get("tab_id"):
            ids.add(tid)
    for ws in snap.get("workspaces", []):
        if wid := ws.get("workspace_id"):
            ids.add(wid)
    return ids


def _id_de_args(args: tuple) -> str | None:
    for i, a in enumerate(args):
        if a in ("--pane", "--workspace") and i + 1 < len(args):
            return args[i + 1]
    if len(args) >= 3 and args[0] in ("pane", "agent", "tab", "workspace"):
        if args[0] == "pane" and args[1] in ("read", "run", "send-keys", "send-text", "process-info", "close"):
            if args[1] == "process-info":
                return None
            return args[2]
        if args[0] == "agent" and args[1] in ("prompt", "wait", "start"):
            return args[2]
        if args[1] in ("close", "rename", "focus") and args[0] in ("tab", "workspace"):
            return args[2]
    return None


def _siguiente_ws(snap: dict) -> tuple[str, str, str]:
    nums = []
    for ws in snap.get("workspaces", []):
        wid = ws.get("workspace_id", "")
        if wid.startswith("w") and wid[1:].isdigit():
            nums.append(int(wid[1:]))
    n = max(nums, default=0) + 1
    ws = f"w{n}"
    return ws, f"{ws}:t1", f"{ws}:p1"


def _siguiente_tab(snap: dict, espacio_id: str) -> tuple[str, str]:
    nums = []
    for tab in snap.get("tabs", []):
        if tab.get("workspace_id") != espacio_id:
            continue
        tid = tab.get("tab_id", "")
        prefix = f"{espacio_id}:t"
        if tid.startswith(prefix) and tid[len(prefix) :].isdigit():
            nums.append(int(tid[len(prefix) :]))
    n = max(nums, default=0) + 1
    return f"{espacio_id}:t{n}", f"{espacio_id}:p{n}"


def _respuesta_creado(ws: str, tab: str, pane: str) -> str:
    return json.dumps(
        {
            "result": {
                "root_pane": {"pane_id": pane},
                "tab": {"tab_id": tab},
                "workspace": {"workspace_id": ws},
            }
        }
    )


@dataclass
class Arnes:
    t: FakeTerminales | AdaptadorHerdr

    def caer(self) -> None:
        if isinstance(self.t, FakeTerminales):
            self.t.caer()
        else:
            self.t.cliente.caido = True

    def volver(self) -> None:
        if isinstance(self.t, FakeTerminales):
            self.t.volver()
        else:
            self.t.cliente.caido = False

    def no_tomar(self, sesion_id: str) -> None:
        if isinstance(self.t, FakeTerminales):
            self.t.estados_tras_prompt[sesion_id] = "idle"
        else:
            self.t.cliente.responses["agent prompt"] = HerdrError("no tomado")

    def vencer(self, sesion_id: str) -> None:
        if isinstance(self.t, FakeTerminales):
            self.t.fallas["esperar"] = Tiempo("espera vencida")
        else:
            self.t.cliente.responses["agent wait"] = HerdrError("herdr no respondió a tiempo")


def arnes_fake() -> Arnes:
    return Arnes(FakeTerminales.desde_snapshot(make_snapshot()))


def arnes_herdr() -> Arnes:
    fh = FakeHerdr(make_snapshot())

    def tab_create(args: tuple) -> str:
        ws = args[args.index("--workspace") + 1]
        label = args[args.index("--label") + 1]
        tid, pid = _siguiente_tab(fh.current, ws)
        fh.current["tabs"].append({"tab_id": tid, "workspace_id": ws, "label": label})
        fh.current["panes"].append({"pane_id": pid, "tab_id": tid, "workspace_id": ws})
        return _respuesta_creado(ws, tid, pid)

    def ws_create(args: tuple) -> str:
        ws, tid, pid = _siguiente_ws(fh.current)
        label = args[args.index("--label") + 1]
        num = int(ws[1:])
        fh.current["workspaces"].append(
            {"workspace_id": ws, "number": num, "label": label, "agent_status": "idle"}
        )
        fh.current["tabs"].append({"tab_id": tid, "workspace_id": ws, "label": label})
        fh.current["panes"].append({"pane_id": pid, "tab_id": tid, "workspace_id": ws})
        return _respuesta_creado(ws, tid, pid)

    fh.handlers["tab create"] = tab_create
    fh.handlers["workspace create"] = ws_create

    run_orig = fh.run

    async def run_envuelto(*args):
        oid = _id_de_args(args)
        if oid is not None and oid not in _ids_en_snapshot(fh.current):
            raise HerdrError('{"error":{"code":"pane_not_found"}}')
        return await run_orig(*args)

    fh.run = run_envuelto

    return Arnes(AdaptadorHerdr(fh, poll=60))
