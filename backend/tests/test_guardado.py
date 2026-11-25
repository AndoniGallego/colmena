"""Guardar en Engram antes de cerrar (spec 16): pedido fijo, turno real, timeout sin cierre solo, tanda. Herdr y timers falsos."""
import asyncio

import pytest

from conftest import make_snapshot
from orquestador.cierre import CierreBody, CierreService
from orquestador.enchufe import FakeTerminales, Tiempo
from orquestador.enchufe.modelo import InfoProceso
from orquestador.guardado import MENSAJE, GuardadoService
from orquestador.locks import PaneLocks
from orquestador.state import StateStore
from orquestador.traspaso import TraspasoError
from terminales_support import aplicar_snapshot, info_proceso, snap_de


def run(coro):
    return asyncio.run(coro)


def _fix_counts(snap):
    for tab in snap["tabs"]:
        tab["pane_count"] = sum(1 for p in snap["panes"] if p["tab_id"] == tab["tab_id"])
    for ws in snap["workspaces"]:
        ws["pane_count"] = sum(1 for p in snap["panes"] if p["workspace_id"] == ws["workspace_id"])


def _mut_snap(m, fn):
    snap = snap_de(m.t)
    fn(snap)
    _fix_counts(snap)
    aplicar_snapshot(m.t, snap)


def tab_claude(snap, tab, pane, status="idle"):
    snap["tabs"].append({"tab_id": tab, "workspace_id": "w1", "label": f"Tab {tab}", "pane_count": 1})
    snap["panes"].append({"pane_id": pane, "tab_id": tab, "workspace_id": "w1"})
    snap["agents"].append({"pane_id": pane, "tab_id": tab, "workspace_id": "w1", "agent": "claude",
                           "agent_status": status, "state_change_seq": 1})
    w1 = next(w for w in snap["workspaces"] if w["workspace_id"] == "w1")
    w1["pane_count"] = sum(1 for p in snap["panes"] if p["workspace_id"] == "w1")


def tablero(**estados):
    agents = [{"pane_id": p, "session_id": None, "status": s, "pending": "", "title": p, "doing": p, "cwd": "/tmp"}
              for p, s in estados.items()]
    return {"workspaces": [{"id": "w1", "label": "Uno", "tabs": [{"id": "w1:t1", "label": "1", "agents": agents}]}]}


class Mundo:
    def __init__(self, tmp_path):
        snap = make_snapshot()
        tab_claude(snap, "w1:t2", "w1:p2")
        self.t = FakeTerminales.desde_snapshot(snap, poll=0.01)
        self.state = StateStore(tmp_path)
        self.locks = PaneLocks()
        self.cierres = CierreService(self.t, self.state, self.locks, lambda: {"w2:p9"}, ["Super orquestador"])
        self.timers, self.emitidos, self.pendientes = [], [], []
        self.svc = GuardadoService(self.cierres, self.t, self.locks, call_later=self.later,
                                   emit=lambda e, d: self.emitidos.append((e, d)),
                                   spawn=lambda coro: self.pendientes.append(coro))
        self.board = tablero(**{"w1:p2": "idle"})

    def later(self, delay, fn):
        h = type("H", (), {"cancelado": False, "cancel": lambda s: setattr(s, "cancelado", True)})()
        self.timers.append((delay, fn, h))
        return h

    def cambia(self, **estados):
        previo, self.board = self.board, tablero(**{**{p: a["status"] for p, a in self._agentes().items()}, **estados})
        self.svc.on_board(previo, self.board)

    def _agentes(self):
        return {a["pane_id"]: a for a in self.board["workspaces"][0]["tabs"][0]["agents"]}

    async def drena(self):
        while self.pendientes:
            await self.pendientes.pop(0)

    def prompts(self):
        return self.t.calls_of("mandar_prompt")

    def closes(self):
        return self.t.calls_of("cerrar")

    def body(self, target="w1:t2", ident="cierre-0001", **over):
        return CierreBody(id=ident, tipo="tab", target_id=target, huella="", origen="manual", **over)

    async def confirmar(self, target="w1:t2", ident="cierre-0001", **kw):
        prev = await self.cierres.preview(__import__("orquestador.cierre", fromlist=["PreviewBody"]).PreviewBody(tipo="tab", target_id=target))
        body = self.body(target, ident).model_copy(update={"huella": prev["huella"]})
        return await self.svc.iniciar_uno(body, **kw)


@pytest.fixture
def m(tmp_path):
    return Mundo(tmp_path)


def test_pide_guardar_con_argv_fijo_y_no_cierra_todavia(m):
    lote = run(m.confirmar())
    assert m.prompts() == [("mandar_prompt", "w1:p2", MENSAJE)]
    assert not m.closes() and lote.public()["targets"][0]["panes"][0]["estado"] == "guardando"
    assert m.timers[0][0] == 300.0


def test_turno_real_cierra_con_huella_fresca_y_guardado_ok(m):
    run(m.confirmar())
    _mut_snap(m, lambda s: s["agents"][-1].__setitem__("state_change_seq", 50))
    m.cambia(**{"w1:p2": "working"})
    m.cambia(**{"w1:p2": "idle"})
    run(m.drena())
    assert m.closes() == [("cerrar", "w1:t2")]
    cierre = m.state.cierres()[-1]
    assert cierre["ok"] and cierre["guardado"] == "ok"
    assert m.svc.lote("cierre-0001").terminado and m.timers[0][2].cancelado


def _consola_con_claude_a_mano(m):
    def f(s):
        s["panes"].append({"pane_id": "w1:p3", "tab_id": "w1:t2", "workspace_id": "w1"})
    _mut_snap(m, f)
    m.t.procesos["w1:p3"] = info_proceso(["claude"])


def test_cerrar_igual_con_agente_y_consola_con_claude_llega_al_cierre_del_lote(m):
    _consola_con_claude_a_mano(m)
    PreviewBody = __import__("orquestador.cierre", fromlist=["PreviewBody"]).PreviewBody
    prev = run(m.cierres.preview(PreviewBody(tipo="tab", target_id="w1:t2")))
    body = m.body().model_copy(update={"huella": prev["huella"], "forzar": True})
    run(m.svc.iniciar_uno(body))
    _mut_snap(m, lambda s: s["agents"][-1].__setitem__("state_change_seq", 50))
    m.cambia(**{"w1:p2": "working"})
    m.cambia(**{"w1:p2": "idle"})
    run(m.drena())
    assert m.closes() == [("cerrar", "w1:t2")]


def test_comando_local_no_es_turno_real(m):
    run(m.confirmar())
    m.cambia(**{"w1:p2": "working"})
    previo = m.board
    m.board = tablero(**{"w1:p2": "idle"})
    m.board["workspaces"][0]["tabs"][0]["agents"][0]["turno_local"] = True
    m.svc.on_board(previo, m.board)
    run(m.drena())
    assert not m.closes()


def test_sin_guardar_cierra_ya_y_registra_saltado(m):
    r = run(m.confirmar(sin_guardar=True))
    assert r["ok"] and not m.prompts() and m.closes() == [("cerrar", "w1:t2")]
    assert m.state.cierres()[-1]["guardado"] == "saltado"


def test_sin_sesiones_claude_no_hay_pedido(m):
    def quitar_claude(s):
        s["agents"] = [a for a in s["agents"] if a["pane_id"] != "w1:p2"]
        for p in s["panes"]:
            if p["pane_id"] == "w1:p2":
                p.pop("agent", None)
                p.pop("agent_status", None)

    _mut_snap(m, quitar_claude)
    m.t.procesos["w1:p2"] = InfoProceso(None, None, None, False, (), shell_pid=1)
    r = run(m.confirmar())
    assert r["ok"] and not m.prompts()
    assert m.state.cierres()[-1]["guardado"] == "saltado"


def test_trabajando_se_frena_a_mano(m):
    _mut_snap(m, lambda s: s["agents"][-1].__setitem__("agent_status", "working"))
    with pytest.raises(TraspasoError) as exc:
        run(m.confirmar())
    assert exc.value.status == 409 and not m.prompts()


def test_timeout_espera_y_nunca_cierra_solo(m):
    lote = run(m.confirmar())
    _, fn, _ = m.timers[0]
    fn()
    run(m.drena())
    assert lote.public()["vencido"] and lote.public()["puede_cerrar_igual"] and not m.closes()


def test_esperar_mas_rearma_5_minutos(m):
    run(m.confirmar())
    m.timers[0][1]()
    run(m.svc.accion("cierre-0001", "esperar_mas"))
    assert len(m.timers) == 2 and m.timers[1][0] == 300.0 and not m.svc.lote("cierre-0001").vencido
    with pytest.raises(TraspasoError):
        run(m.svc.accion("cierre-0001", "esperar_mas"))


def test_cerrar_igual_tras_timeout_aunque_siga_trabajando(m):
    run(m.confirmar())
    m.cambia(**{"w1:p2": "working"})
    _mut_snap(m, lambda s: s["agents"][-1].__setitem__("agent_status", "working"))
    m.timers[0][1]()
    run(m.svc.accion("cierre-0001", "cerrar_igual"))
    assert m.closes() == [("cerrar", "w1:t2")]
    assert m.state.cierres()[-1]["guardado"] == "vencido"


def test_cerrar_igual_antes_del_timeout_409(m):
    run(m.confirmar())
    with pytest.raises(TraspasoError) as exc:
        run(m.svc.accion("cierre-0001", "cerrar_igual"))
    assert exc.value.status == 409 and not m.closes()


def test_blocked_durante_el_guardado_ofrece_cerrar_igual_sin_esperar_timeout(m):
    lote = run(m.confirmar())
    m.cambia(**{"w1:p2": "working"})
    m.cambia(**{"w1:p2": "blocked"})
    pub = lote.public()
    assert pub["targets"][0]["panes"][0]["estado"] == "bloqueado" and pub["puede_cerrar_igual"] and not pub["vencido"]
    m.cambia(**{"w1:p2": "working"})
    assert not lote.public()["puede_cerrar_igual"]


def test_estructura_distinta_no_cierra_y_queda_en_error(m):
    lote = run(m.confirmar())
    _mut_snap(m, lambda s: s["panes"].append({"pane_id": "w1:p8", "tab_id": "w1:t2", "workspace_id": "w1"}))
    m.cambia(**{"w1:p2": "working"})
    m.cambia(**{"w1:p2": "idle"})
    run(m.drena())
    t = lote.public()["targets"][0]
    assert t["estado"] == "error" and "cambió" in t["error"] and not m.closes()


def test_pedido_que_no_llega_queda_en_fallo_y_ofrece_cerrar_igual(m):
    m.t.fallas["mandar_prompt"] = Tiempo("no respondió a tiempo")
    lote = run(m.confirmar())
    assert lote.public()["targets"][0]["panes"][0]["estado"] == "fallo" and lote.public()["puede_cerrar_igual"]


def test_huella_vieja_409(m):
    prev_huella = "x" * 10
    with pytest.raises(TraspasoError) as exc:
        run(m.svc.iniciar_uno(m.body().model_copy(update={"huella": prev_huella})))
    assert exc.value.status == 409 and "cambió, revisalo" in exc.value.detail


def test_mismo_id_devuelve_el_lote_activo_sin_repetir_el_pedido(m):
    a = run(m.confirmar())
    b = run(m.confirmar())
    assert a is b and len(m.prompts()) == 1


def test_cancelar_deja_de_esperar_y_no_cierra(m):
    lote = run(m.confirmar())
    m.svc.cancelar("cierre-0001")
    m.cambia(**{"w1:p2": "working"})
    m.cambia(**{"w1:p2": "idle"})
    run(m.drena())
    assert lote.terminado and not m.closes()


def dos_tabs(m):
    _mut_snap(m, lambda s: tab_claude(s, "w1:t3", "w1:p3"))
    m.board = tablero(**{"w1:p2": "idle", "w1:p3": "idle"})


def entradas(m, *targets):
    out = []
    for i, t in enumerate(targets):
        out.append((f"p{i + 1}", CierreBody(id=f"tanda-000{i}", tipo="tab", target_id=t, huella="", origen="plan",
                                            lote_id="plan-tanda-01"), ""))
    return out


def test_tanda_pide_a_todos_a_la_vez_un_timer_y_cierra_cada_target_al_terminar_el_suyo(m):
    dos_tabs(m)
    lote = run(m.svc.iniciar_tanda("plan-tanda-01", entradas(m, "w1:t2", "w1:t3")))
    assert sorted(p[1] for p in m.prompts()) == ["w1:p2", "w1:p3"] and len(m.timers) == 1
    m.cambia(**{"w1:p2": "working", "w1:p3": "working"})
    m.cambia(**{"w1:p2": "idle"})
    run(m.drena())
    assert m.closes() == [("cerrar", "w1:t2")] and not lote.terminado
    m.cambia(**{"w1:p3": "idle"})
    run(m.drena())
    assert [c[1] for c in m.closes()] == ["w1:t2", "w1:t3"] and lote.terminado
    assert [c["guardado"] for c in m.state.cierres()] == ["ok", "ok"]


def test_tanda_target_que_cambio_queda_en_error_y_el_resto_sigue(m):
    dos_tabs(m)
    lote = run(m.svc.iniciar_tanda("plan-tanda-01", entradas(m, "w1:t2", "w1:t3")))
    _mut_snap(m, lambda s: s["panes"].append({"pane_id": "w1:p9", "tab_id": "w1:t2", "workspace_id": "w1"}))
    m.cambia(**{"w1:p2": "working", "w1:p3": "working"})
    m.cambia(**{"w1:p2": "idle", "w1:p3": "idle"})
    run(m.drena())
    estados = {t["key"]: t["estado"] for t in lote.public()["targets"]}
    assert estados == {"p1": "error", "p2": "cerrado"} and m.closes() == [("cerrar", "w1:t3")]


def test_tanda_huella_vista_distinta_deja_ese_target_en_error(m):
    dos_tabs(m)
    ent = entradas(m, "w1:t2", "w1:t3")
    ent[0] = (ent[0][0], ent[0][1], "vieja")
    lote = run(m.svc.iniciar_tanda("plan-tanda-01", ent))
    t = {t["key"]: t for t in lote.public()["targets"]}
    assert t["p1"]["estado"] == "error" and t["p2"]["estado"] == "guardando"
    assert [p[1] for p in m.prompts()] == ["w1:p3"]


def test_tanda_sin_guardar_cierra_todo_en_orden_sin_pedido(m):
    dos_tabs(m)
    lote = run(m.svc.iniciar_tanda("plan-tanda-01", entradas(m, "w1:t2", "w1:t3"), sin_guardar=True))
    assert lote.terminado and not m.prompts() and [c[1] for c in m.closes()] == ["w1:t2", "w1:t3"]
    assert {c["guardado"] for c in m.state.cierres()} == {"saltado"}


def test_tanda_cerrar_igual_cierra_solo_los_que_siguen_guardando(m):
    dos_tabs(m)
    lote = run(m.svc.iniciar_tanda("plan-tanda-01", entradas(m, "w1:t2", "w1:t3")))
    m.cambia(**{"w1:p2": "working", "w1:p3": "working"})
    m.cambia(**{"w1:p2": "idle"})
    run(m.drena())
    m.timers[0][1]()
    run(m.svc.accion("plan-tanda-01", "cerrar_igual"))
    assert lote.terminado
    assert [(c["target_id"], c["guardado"]) for c in m.state.cierres()] == [("w1:t2", "ok"), ("w1:t3", "vencido")]


def test_emite_cada_cambio_del_lote(m):
    run(m.confirmar())
    assert m.emitidos and m.emitidos[-1][0] == "guardado" and m.emitidos[-1][1]["id"] == "cierre-0001"


def test_cerrar_igual_antes_del_timeout_solo_cierra_el_target_trabado(m):
    dos_tabs(m)
    lote = run(m.svc.iniciar_tanda("plan-tanda-01", entradas(m, "w1:t2", "w1:t3")))
    m.cambia(**{"w1:p2": "working", "w1:p3": "working"})
    m.cambia(**{"w1:p2": "blocked"})
    assert lote.public()["puede_cerrar_igual"] and not lote.vencido
    out = run(m.svc.accion("plan-tanda-01", "cerrar_igual"))
    estados = {t["target_id"]: t["estado"] for t in out["targets"]}
    assert estados == {"w1:t2": "cerrado", "w1:t3": "guardando"}
    assert m.closes() == [("cerrar", "w1:t2")]
    cierre = m.state.cierres()[-1]
    assert cierre["guardado"] == "vencido" and cierre["ok"]  # sesión bloqueada: 16.3 pide "vencido"


def test_un_pane_que_falla_no_habilita_cerrar_a_otro_que_sigue_guardando(m):
    def _rompe_tab(s):
        tab_claude(s, "w1:p3x", "w1:p3")
        s["tabs"].pop()
        s["panes"][-1]["tab_id"] = "w1:t2"
        s["agents"][-1]["tab_id"] = "w1:t2"

    _mut_snap(m, _rompe_tab)
    m.board = tablero(**{"w1:p2": "idle", "w1:p3": "idle"})
    lote = run(m.confirmar())
    m.cambia(**{"w1:p2": "working", "w1:p3": "working"})
    m.cambia(**{"w1:p2": "blocked"})
    assert not lote.public()["puede_cerrar_igual"]
    with pytest.raises(TraspasoError):
        run(m.svc.accion("cierre-0001", "cerrar_igual"))
    assert not m.closes()


def test_vencido_se_registra_solo_si_vencio(m):
    run(m.confirmar())
    m.timers[0][1]()
    run(m.svc.accion("cierre-0001", "cerrar_igual"))
    assert m.state.cierres()[-1]["guardado"] == "vencido"


def test_esperar_mas_vuelve_a_dormir_a_quien_espera(m):
    lote = run(m.confirmar())
    m.timers[0][1]()
    assert lote.hecho.is_set()
    run(m.svc.accion("cierre-0001", "esperar_mas"))
    assert not lote.hecho.is_set()


def test_cancelar_mientras_se_manda_el_pedido_frena_el_cierre(m):
    async def go():
        suelta = asyncio.Event()
        orig = m.t.mandar_prompt

        async def lento(sesion_id, texto, **kw):
            await suelta.wait()
            return await orig(sesion_id, texto, **kw)

        m.t.mandar_prompt = lento
        tarea = asyncio.ensure_future(m.confirmar())
        for _ in range(20):
            await asyncio.sleep(0)
            if m.svc.lote("cierre-0001") and m.svc.lote("cierre-0001").targets:
                break
        m.svc.cancelar("cierre-0001")
        suelta.set()
        lote = await tarea
        m.cambia(**{"w1:p2": "working"})
        m.cambia(**{"w1:p2": "idle"})
        await m.drena()
        return lote

    lote = run(go())
    assert lote.terminado and lote.targets["t1"].estado == "cancelado" and not m.closes()


def test_dos_confirmaciones_del_mismo_id_comparten_lote_y_un_pedido(m):
    async def go():
        a, b = await asyncio.gather(m.confirmar(), m.confirmar())
        return a, b

    a, b = run(go())
    assert a is b and len(m.prompts()) == 1


def test_target_sin_sesiones_claude_en_la_tanda_se_audita_saltado(m):
    def tab_sin_claude(s):
        s["tabs"].append({"tab_id": "w1:t3", "workspace_id": "w1", "label": "Sin Claude", "pane_count": 1})
        s["panes"].append({"pane_id": "w1:p3", "tab_id": "w1:t3", "workspace_id": "w1"})

    _mut_snap(m, tab_sin_claude)
    run(m.svc.iniciar_tanda("plan-tanda-01", entradas(m, "w1:t3")))
    run(m.drena())
    assert m.state.cierres()[-1]["guardado"] == "saltado"


def _preview_lento(m):
    """El primer preview después de armar el cuerpo espera a `suelta`: deja cancelar con el lote reservado y sin targets."""
    suelta, entro = asyncio.Event(), asyncio.Event()
    orig = m.cierres.preview

    async def lento(body):
        entro.set()
        await suelta.wait()
        return await orig(body)

    m.cierres.preview = lento
    return suelta, entro, orig


def test_cancelar_mientras_espera_el_preview_no_pide_ni_cierra(m):
    async def go():
        prev = await m.cierres.preview(__import__("orquestador.cierre", fromlist=["PreviewBody"]).PreviewBody(tipo="tab", target_id="w1:t2"))
        body = m.body().model_copy(update={"huella": prev["huella"]})
        suelta, entro, _ = _preview_lento(m)
        tarea = asyncio.ensure_future(m.svc.iniciar_uno(body))
        await entro.wait()
        m.svc.cancelar("cierre-0001")
        suelta.set()
        lote = await tarea
        m.cambia(**{"w1:p2": "working"})
        m.cambia(**{"w1:p2": "idle"})
        await m.drena()
        return lote

    lote = run(go())
    assert not m.prompts() and not m.closes()
    assert lote.terminado and lote.targets["t1"].estado == "cancelado"


def test_on_board_no_cierra_un_lote_cancelado(m):
    lote = run(m.confirmar())
    lote.cancelado = True
    m.cambia(**{"w1:p2": "working"})
    m.cambia(**{"w1:p2": "idle"})
    run(m.drena())
    assert not m.closes()


def test_cancelar_un_lote_vacio_de_la_tanda_libera_su_timer(m):
    async def go():
        suelta, entro, _ = _preview_lento(m)
        tarea = asyncio.ensure_future(m.svc.iniciar_tanda("tanda-vacia-01", entradas(m, "w1:t2")))
        await entro.wait()
        tarea.cancel()
        m.svc.cancelar("tanda-vacia-01")
        try:
            await tarea
        except asyncio.CancelledError:
            pass

    run(go())
    assert m.timers[0][2].cancelado and m.svc.lote("tanda-vacia-01") is None


def test_descartar_avisa_a_quien_espera_el_lote_reservado(m):
    def tab_sin_claude(s):
        s["tabs"].append({"tab_id": "w1:t3", "workspace_id": "w1", "label": "Sin Claude", "pane_count": 1})
        s["panes"].append({"pane_id": "w1:p3", "tab_id": "w1:t3", "workspace_id": "w1"})

    _mut_snap(m, tab_sin_claude)
    run(m.confirmar("w1:t3"))
    assert m.emitidos and m.emitidos[-1][0] == "guardado"


def test_sesion_bloqueada_desde_el_principio_ofrece_cerrar_igual(m):
    _mut_snap(m, lambda s: s["agents"][-1].__setitem__("agent_status", "blocked"))
    lote = run(m.confirmar())
    pub = lote.public()
    assert pub["targets"][0]["panes"][0]["estado"] == "bloqueado" and pub["puede_cerrar_igual"] and not pub["vencido"]
    run(m.svc.accion("cierre-0001", "cerrar_igual"))
    assert m.closes() and m.state.cierres()[-1]["guardado"] == "vencido"


def test_sesion_bloqueada_que_se_destraba_recibe_el_pedido_y_deja_de_estar_trabada(m):
    _mut_snap(m, lambda s: s["agents"][-1].__setitem__("agent_status", "blocked"))
    m.board = tablero(**{"w1:p2": "blocked"})
    lote = run(m.confirmar())
    assert lote.public()["puede_cerrar_igual"] and not m.prompts()
    _mut_snap(m, lambda s: s["agents"][-1].__setitem__("agent_status", "working"))
    m.cambia(**{"w1:p2": "working"})  # el usuario contestó el diálogo
    run(m.drena())
    pub = lote.public()
    assert len(m.prompts()) == 1 and pub["targets"][0]["panes"][0]["estado"] == "guardando"
    assert not pub["puede_cerrar_igual"]
    with pytest.raises(TraspasoError):
        run(m.svc.accion("cierre-0001", "cerrar_igual"))
    assert not m.closes()
    _mut_snap(m, lambda s: s["agents"][-1].__setitem__("agent_status", "idle"))
    m.cambia(**{"w1:p2": "idle"})
    run(m.drena())
    assert m.closes() and m.state.cierres()[-1]["guardado"] == "ok"


def test_cerrar_igual_no_fuerza_una_sesion_que_esta_trabajando_si_no_vencio(m):
    _mut_snap(m, lambda s: s["agents"][-1].__setitem__("agent_status", "blocked"))
    lote = run(m.confirmar())
    assert lote.public()["puede_cerrar_igual"]
    _mut_snap(m, lambda s: s["agents"][-1].__setitem__("agent_status", "working"))  # retomó antes de que llegara el aviso del tablero
    run(m.svc.accion("cierre-0001", "cerrar_igual"))
    assert not m.closes() and lote.targets["t1"].estado == "guardando"


def test_guardado_avisa_al_escribir_con_el_pane(tmp_path):
    llamadas = []
    m = Mundo(tmp_path)
    m.svc.al_escribir = llamadas.append
    run(m.confirmar())
    assert llamadas == ["w1:p2"]


def test_guardado_que_falla_igual_marcaba_antes(tmp_path):
    llamadas = []
    m = Mundo(tmp_path)
    m.svc.al_escribir = llamadas.append
    m.t.mandar_prompt = _falla_prompt
    run(m.confirmar())
    assert llamadas == ["w1:p2"]


async def _falla_prompt(*a, **k):
    from orquestador.enchufe import TerminalesError
    raise TerminalesError("caído")


def test_guardado_marca_el_pane_antes_de_mandar_el_prompt(tmp_path):
    orden = []
    m = Mundo(tmp_path)
    m.svc.al_escribir = orden.append
    original = m.t.mandar_prompt

    async def espiado(*a, **k):
        orden.append("mandar")
        return await original(*a, **k)
    m.t.mandar_prompt = espiado
    run(m.confirmar())
    assert orden == ["w1:p2", "mandar"]
