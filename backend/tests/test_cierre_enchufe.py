import asyncio

import pytest

from conftest import make_snapshot
from orquestador.cierre import CierreBody, CierreService, PreviewBody
from orquestador.enchufe import FakeTerminales, GrupoRequerido
from orquestador.guardado import MENSAJE, GuardadoService
from orquestador.locks import PaneLocks
from orquestador.state import StateStore
from orquestador.traspaso import TraspasoError
from terminales_support import info_proceso

ID = "6f1c1e0b-4a55-4e1d-9d33-1f3c2a7d9e10"


def run(coro):
    return asyncio.run(coro)


def cierre_stack(tmp_path, t):
    state = StateStore(tmp_path)
    locks = PaneLocks()
    cierres = CierreService(t, state, locks, lambda: set(), ["Super orquestador"])
    return state, cierres


def test_cerrar_tab_por_el_enchufe_y_verifica_que_no_esta(tmp_path):
    t = FakeTerminales.desde_snapshot(make_snapshot())
    state, cierres = cierre_stack(tmp_path, t)
    prev = run(cierres.preview(PreviewBody(tipo="tab", target_id="w2:t1")))
    body = CierreBody(
        id=ID,
        tipo="tab",
        target_id="w2:t1",
        huella=prev["huella"],
        origen="manual",
        sin_guardar=True,
    )
    run(cierres.execute(body, guardado="saltado"))
    assert t.calls_of("cerrar") == [("cerrar", "w2:t1")]
    assert state.cierres()[-1]["target_id"] == "w2:t1" and state.cierres()[-1]["ok"] is True


def test_grupo_requerido_da_409_de_hoy(tmp_path):
    t = FakeTerminales.desde_snapshot(make_snapshot())
    t.fallas["cerrar"] = GrupoRequerido('{"error":{"code":"workspace_group_close_required"}}')
    _, cierres = cierre_stack(tmp_path, t)
    prev = run(cierres.preview(PreviewBody(tipo="workspace", target_id="w1")))
    body = CierreBody(
        id=ID,
        tipo="workspace",
        target_id="w1",
        huella=prev["huella"],
        origen="manual",
        sin_guardar=True,
    )
    with pytest.raises(TraspasoError) as exc:
        run(cierres.execute(body, guardado="saltado"))
    assert exc.value.status == 409 and exc.value.detail == "Tiene worktrees vinculados: cerralo en la terminal"


def test_guardado_pide_luego_espera_y_cierra_en_ese_orden(tmp_path):
    t = FakeTerminales.desde_snapshot(make_snapshot())
    state, cierres = cierre_stack(tmp_path, t)
    locks = PaneLocks()
    pendientes = []
    svc = GuardadoService(
        cierres,
        t,
        locks,
        call_later=lambda d, fn: asyncio.get_running_loop().call_later(d, fn),
        spawn=lambda coro: pendientes.append(coro),
    )
    prev = run(cierres.preview(PreviewBody(tipo="tab", target_id="w1:t1")))
    body = CierreBody(
        id="cierre-0001",
        tipo="tab",
        target_id="w1:t1",
        huella=prev["huella"],
        origen="manual",
    )

    def tablero(**estados):
        agents = [
            {"pane_id": p, "session_id": None, "status": s, "pending": "", "title": p, "doing": p, "cwd": "/tmp"}
            for p, s in estados.items()
        ]
        return {"workspaces": [{"id": "w1", "label": "Uno", "tabs": [{"id": "w1:t1", "label": "1", "agents": agents}]}]}

    async def go():
        await svc.iniciar_uno(body)
        previo = tablero(**{"w1:p1": "idle"})
        svc.on_board(None, previo)
        svc.on_board(previo, tablero(**{"w1:p1": "working"}))
        svc.on_board(tablero(**{"w1:p1": "working"}), tablero(**{"w1:p1": "idle"}))
        while pendientes:
            await pendientes.pop(0)

    run(go())
    ops = [c[0] for c in t.calls if c[0] in ("mandar_prompt", "cerrar")]
    assert ops == ["mandar_prompt", "cerrar"]
    assert t.calls_of("mandar_prompt") == [("mandar_prompt", "w1:p1", MENSAJE)]


def test_shell_con_claude_en_primer_plano_bloquea(tmp_path):
    t = FakeTerminales.desde_snapshot(make_snapshot())
    t.procesos["w2:p1"] = info_proceso(["node", "/x/claude"])
    _, cierres = cierre_stack(tmp_path, t)
    prev = run(cierres.preview(PreviewBody(tipo="tab", target_id="w2:t1")))
    assert prev["bloqueantes"] == [{"pane_id": "w2:p1", "status": "unknown"}]
    body = CierreBody(
        id=ID,
        tipo="tab",
        target_id="w2:t1",
        huella=prev["huella"],
        origen="manual",
        sin_guardar=True,
    )
    with pytest.raises(TraspasoError) as exc:
        run(cierres.execute(body, guardado="saltado"))
    assert exc.value.status == 409
    assert not t.calls_of("cerrar")
