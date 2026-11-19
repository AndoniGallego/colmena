import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from orquestador.cierre import CierreService
from orquestador.enchufe import NoDisponible
from orquestador.enchufe.fake import FakeTerminales
from orquestador.enchufe.herdr import tablero_de_snapshot
from orquestador.enchufe.modelo import (
    Creado,
    Espacio,
    InfoProceso,
    Lanzamiento,
    Linea,
    ProcesoPrimerPlano,
    Sesion,
    Tablero,
)
from orquestador.locks import PaneLocks
from orquestador.mudanza import (
    MudanzaBody,
    MudanzaService,
    MudanzaStore,
    MudarTodasBody,
    RetomarBody,
    remapear_en,
)
from orquestador.state import StateStore
from orquestador.traspaso import TraspasoError

SID = "6f1c1e0b-4a55-4e1d-9d33-1f3c2a7d9e10"
SID2 = "7a2d2f1c-5b66-4f2e-8e44-2a4d3b8e0f21"
CWD = "/home/x/proj"


def run(coro):
    return asyncio.run(coro)


def snapshot(status_p1="idle"):
    return {
        "workspaces": [
            {"workspace_id": "w1", "number": 1, "label": "Proyecto X"},
            {"workspace_id": "w2", "number": 2, "label": "Otro"},
            {"workspace_id": "w3", "number": 3, "label": "Tercero"},
        ],
        "tabs": [
            {"tab_id": "w1:t1", "workspace_id": "w1", "label": "api"},
            {"tab_id": "w2:t1", "workspace_id": "w2", "label": "ocupada"},
            {"tab_id": "w2:t2", "workspace_id": "w2", "label": "doble"},
            {"tab_id": "w3:t1", "workspace_id": "w3", "label": "shell"},
        ],
        "agents": [
            {"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "agent": "claude",
             "agent_status": status_p1, "cwd": CWD, "terminal_title_stripped": "API",
             "state_change_seq": 3, "agent_session": {"kind": "id", "value": SID}},
            {"pane_id": "w2:p1", "tab_id": "w2:t1", "workspace_id": "w2", "agent": "claude",
             "agent_status": "working", "cwd": CWD, "state_change_seq": 1,
             "agent_session": {"kind": "id", "value": SID2}},
            {"pane_id": "w2:p2", "tab_id": "w2:t2", "workspace_id": "w2", "agent": "claude",
             "agent_status": "idle", "cwd": CWD, "state_change_seq": 1,
             "agent_session": {"kind": "id", "value": "8b3e3a2d-6c77-4a3f-9f55-3b5e4c9f1a32"}},
        ],
        "panes": [
            {"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "cwd": CWD},
            {"pane_id": "w2:p1", "tab_id": "w2:t1", "workspace_id": "w2"},
            {"pane_id": "w2:p2", "tab_id": "w2:t2", "workspace_id": "w2"},
            {"pane_id": "w2:p3", "tab_id": "w2:t2", "workspace_id": "w2"},
            {"pane_id": "w3:p1", "tab_id": "w3:t1", "workspace_id": "w3"},
        ],
    }


def info_claude(pid=4242, cwd=CWD):
    return InfoProceso(pid=pid, comando="claude", cwd=cwd, es_claude=True,
                       procesos=(ProcesoPrimerPlano(pid, "claude", ("claude",), cwd),), grupo=pid, shell_pid=1)


class FakeGuardian(FakeTerminales):
    def __init__(self, tablero=None, **kw):
        super().__init__(tablero, nombre="guardian", **kw)
        self.proximos_ids = [("g1", "g1:t1", "g1:p1"), ("g1", "g1:t2", "g1:p2"), ("g2", "g2:t1", "g2:p1")]
        self.falla_arranque: Exception | None = None

    async def crear_linea(self, espacio_id, nombre, cwd, programa=Lanzamiento("shell")) -> Creado:
        if self.falla_arranque:
            self._registrar("crear_linea_fallida", espacio_id, nombre, cwd, programa.programa, programa.resume)
            raise self.falla_arranque
        creado = await super().crear_linea(espacio_id, nombre, cwd, programa)
        self.calls[-1] = ("crear_linea", espacio_id, nombre, cwd, programa.programa, programa.resume)
        return creado

    async def arrancar_claude(self, sesion_id, nombre, resume=None) -> None:
        self._registrar("arrancar_claude", sesion_id, nombre, resume)
        if self.falla_arranque:
            raise self.falla_arranque


class Pids:
    def __init__(self, herdr, pane="w1:p1", siempre_vivo=False):
        self.herdr, self.pane, self.siempre_vivo = herdr, pane, siempre_vivo
        self.consultas: list[int] = []

    def __call__(self, pid: int) -> bool:
        self.consultas.append(pid)
        if self.siempre_vivo:
            return True
        return any(s.id == self.pane for s in self.herdr.tablero_actual.sesiones)


def armar(tmp_path, *, guardian="vacio", estado_ganchos=None, transcript=None, pid_vivo=None, remapeos=()):
    herdr = FakeTerminales(tablero_de_snapshot(snapshot(), 1), nombre="herdr")
    herdr.procesos["w1:p1"] = info_claude()
    herdr.procesos["w2:p2"] = info_claude(pid=5151)
    g = FakeGuardian() if guardian == "vacio" else guardian
    state = StateStore(tmp_path)
    locks = PaneLocks()
    cierre = CierreService(herdr, state, locks, lambda: set(), [])
    store = MudanzaStore(tmp_path / "mudanzas.json")
    eventos: list[dict] = []
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    svc = MudanzaService(
        herdr=herdr,
        guardian=lambda: g,
        cierre=cierre,
        locks=locks,
        store=store,
        estado_ganchos=estado_ganchos or (lambda pane: None),
        transcript=transcript or (lambda sid: Path(f"/claude/projects/-home-x-proj/{sid}.jsonl")),
        pid_vivo=pid_vivo or Pids(herdr),
        remapeos=list(remapeos),
        al_mudar=eventos.append,
        sleep=fake_sleep,
        confirmar_timeout=2.0,
        paso=0.5,
    )
    return svc, herdr, g, store, eventos


def body(pane="w1:p1", ident="mud-0001"):
    return MudanzaBody(id=ident, pane_id=pane, confirmado=True)


def test_orden_cerrar_confirmar_y_retomar_en_el_guardian(tmp_path):
    orden: list[str] = []
    svc, herdr, g, store, eventos = armar(tmp_path)
    cerrar_herdr, crear_g, arrancar_g = herdr.cerrar, g.crear_espacio, g.arrancar_claude
    pids = svc.pid_vivo

    async def cerrar(oid):
        orden.append(f"cerrar {oid}")
        await cerrar_herdr(oid)

    async def crear(nombre, cwd):
        orden.append(f"crear_espacio {nombre}")
        return await crear_g(nombre, cwd)

    async def arrancar(sid, nombre, resume=None):
        orden.append(f"arrancar {sid} {resume}")
        await arrancar_g(sid, nombre, resume)

    def vivo(pid):
        r = pids(pid)
        orden.append(f"pid {pid} {'vivo' if r else 'muerto'}")
        return r

    herdr.cerrar, g.crear_espacio, g.arrancar_claude, svc.pid_vivo = cerrar, crear, arrancar, vivo
    out = run(svc.mudar(body()))
    assert orden[0] == "cerrar w1:t1"
    assert "pid 4242 muerto" in orden
    assert orden.index("pid 4242 muerto") < orden.index("crear_espacio Proyecto X")
    assert orden[-1] == f"arrancar g1:p1 {SID}"
    assert g.calls_of("crear_espacio") == [("crear_espacio", "Proyecto X", CWD)]
    assert g.calls_of("arrancar_claude") == [("arrancar_claude", "g1:p1", "api", SID)]
    m = out["mudanza"]
    assert out["ok"] is True
    assert (m["pane_viejo"], m["pane_nuevo"], m["session_id"], m["estado"]) == ("w1:p1", "g1:p1", SID, "ok")
    assert store.get("mud-0001")["estado"] == "ok"
    assert eventos and eventos[-1]["id"] == "mud-0001"


def test_reusa_el_workspace_del_guardian_con_el_mismo_nombre(tmp_path):
    ses = Sesion(id="g1:p1", linea_id="g1:t1", espacio_id="g1", programa="shell", estado="idle",
                 estado_fuente="guardian", claude_session_id=None, cwd="/tmp", cwd_primer_plano=None,
                 titulo="", revision=None, backend="guardian")
    g = FakeGuardian(Tablero((Espacio("g1", "proyecto x", ("g1:t1",)),), (Linea("g1:t1", "g1", "x", ("g1:p1",)),),
                             (ses,), 1))
    g.proximos_ids = [(None, "g1:t2", "g1:p2")]
    svc, herdr, g, store, _ = armar(tmp_path, guardian=g)
    out = run(svc.mudar(body()))
    assert g.calls_of("crear_espacio") == []
    assert g.calls_of("crear_linea") == [("crear_linea", "g1", "api", CWD, "claude", SID)]
    assert out["mudanza"]["pane_nuevo"] == "g1:p2"


def test_si_no_se_confirma_el_cierre_no_arranca_nada(tmp_path):
    svc, herdr, g, store, _ = armar(tmp_path)
    svc.pid_vivo = Pids(herdr, siempre_vivo=True)
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 502
    assert SID in exc.value.detail
    assert herdr.calls_of("cerrar") == [("cerrar", "w1:t1")]
    assert g.calls_of("crear_espacio") == g.calls_of("crear_linea") == g.calls_of("arrancar_claude") == []
    assert store.get("mud-0001")["estado"] == "sin_confirmar"


def test_si_herdr_no_cierra_no_arranca_nada(tmp_path):
    svc, herdr, g, store, _ = armar(tmp_path)
    herdr.aplicar_cierres = False
    with pytest.raises(TraspasoError):
        run(svc.mudar(body()))
    assert g.calls == []


def test_trabajando_segun_los_ganchos_no_toca_nada(tmp_path):
    svc, herdr, g, store, _ = armar(tmp_path, estado_ganchos=lambda pane: "working")
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 409
    assert herdr.calls_of("cerrar") == [] and g.calls == []
    assert store.get("mud-0001") is None


def test_se_puso_a_trabajar_justo_antes_de_cerrar(tmp_path):
    svc, herdr, g, store, _ = armar(tmp_path)
    proceso = herdr.proceso

    async def proceso_y_arranca(pane):
        info = await proceso(pane)
        herdr.tablero_actual = tablero_de_snapshot(snapshot(status_p1="working"), 2)
        return info

    herdr.proceso = proceso_y_arranca
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 409
    assert herdr.calls_of("cerrar") == [] and g.calls == []


def test_falla_del_guardian_tras_cerrar_deja_para_volver_a_abrir(tmp_path):
    svc, herdr, g, store, eventos = armar(tmp_path)
    g.falla_arranque = NoDisponible("guardián caído")
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 502 and SID in exc.value.detail
    assert herdr.calls_of("cerrar") == [("cerrar", "w1:t1")]
    assert herdr.calls_of("crear_espacio") == herdr.calls_of("crear_linea") == herdr.calls_of("arrancar_claude") == []
    entry = store.get("mud-0001")
    assert entry["estado"] == "pendiente" and entry["session_id"] == SID and entry.get("error")

    g.falla_arranque = None
    out = run(svc.retomar(RetomarBody(id="ret-0001", mudanza_id="mud-0001", confirmado=True)))
    assert out["mudanza"]["estado"] == "ok"
    assert out["mudanza"]["pane_nuevo"].startswith("g")
    assert herdr.calls_of("cerrar") == [("cerrar", "w1:t1")]


def test_volver_a_abrir_se_niega_si_la_conversacion_ya_esta_abierta(tmp_path):
    svc, herdr, g, store, _ = armar(tmp_path)
    g.falla_arranque = NoDisponible("guardián caído")
    with pytest.raises(TraspasoError):
        run(svc.mudar(body()))
    g.falla_arranque = None
    herdr.tablero_actual = tablero_de_snapshot(snapshot(), 5)
    with pytest.raises(TraspasoError) as exc:
        run(svc.retomar(RetomarBody(id="ret-0001", mudanza_id="mud-0001", confirmado=True)))
    assert exc.value.status == 409
    assert g.calls_of("arrancar_claude") == [("arrancar_claude", "g1:p1", "api", SID)]


def test_remapea_un_servicio_registrado_y_lo_registra(tmp_path):
    encargos = {"items": [{"id": "enc1", "sesiones": ["w1:p1", "w9:p1"]}]}

    def remap(viejo, nuevo):
        return remapear_en(encargos, viejo, nuevo)

    svc, *_ = armar(tmp_path, remapeos=[("encargos", remap)])
    out = run(svc.mudar(body()))
    assert encargos["items"][0]["sesiones"] == ["g1:p1", "w9:p1"]
    assert out["mudanza"]["remapeos"] == {"encargos": 1}


def test_remapear_en_cambia_solo_ids_exactos():
    data = {
        "items": [
            {"pane_id": "w1:p1", "texto": "w1:p1 dice algo", "destino": {"pane_id": "w1:p1"}},
            {"pane": "w1:p10", "desde": "w1:p1", "hacia": "$paso2"},
            {"sesiones": ["w1:p1", "w2:p1"], "panes": {"w1:p1": {"fin": 1}, "w3:p1": {}}},
        ]
    }
    n = remapear_en(data, "w1:p1", "g1:p1")
    assert n == 5
    assert data["items"][0] == {"pane_id": "g1:p1", "texto": "w1:p1 dice algo", "destino": {"pane_id": "g1:p1"}}
    assert data["items"][1] == {"pane": "w1:p10", "desde": "g1:p1", "hacia": "$paso2"}
    assert data["items"][2] == {"sesiones": ["g1:p1", "w2:p1"], "panes": {"g1:p1": {"fin": 1}, "w3:p1": {}}}


def test_un_remapeo_que_falla_no_frena_la_mudanza(tmp_path):
    def roto(viejo, nuevo):
        raise RuntimeError("x")

    svc, *_ = armar(tmp_path, remapeos=[("roto", roto)])
    out = run(svc.mudar(body()))
    assert out["mudanza"]["estado"] == "ok"
    assert out["mudanza"]["remapeos"] == {"roto": "error"}


def test_mudar_todas_saltea_las_que_no_estan_quietas(tmp_path):
    svc, herdr, g, store, _ = armar(tmp_path)
    out = run(svc.mudar_todas(MudarTodasBody(id="lote-0001", pane_ids=["w1:p1", "w2:p1", "w2:p2", "w3:p1"],
                                             confirmado=True)))
    assert [m["pane_viejo"] for m in out["mudadas"]] == ["w1:p1"]
    saltadas = {s["pane_id"]: s["motivo"] for s in out["saltadas"]}
    assert set(saltadas) == {"w2:p1", "w2:p2", "w3:p1"}
    assert all(saltadas.values())
    assert herdr.calls_of("cerrar") == [("cerrar", "w1:t1")]


def test_mudar_todas_frena_si_el_guardian_falla(tmp_path):
    snap = snapshot()
    snap["tabs"].append({"tab_id": "w3:t2", "workspace_id": "w3", "label": "otra"})
    snap["agents"].append({"pane_id": "w3:p2", "tab_id": "w3:t2", "workspace_id": "w3", "agent": "claude",
                           "agent_status": "done", "cwd": CWD, "state_change_seq": 1,
                           "agent_session": {"kind": "id", "value": SID2}})
    snap["panes"].append({"pane_id": "w3:p2", "tab_id": "w3:t2", "workspace_id": "w3", "cwd": CWD})
    svc, herdr, g, store, _ = armar(tmp_path)
    herdr.tablero_actual = tablero_de_snapshot(snap, 3)
    herdr.procesos["w3:p2"] = info_claude(pid=6161)
    g.falla_arranque = NoDisponible("caído")
    out = run(svc.mudar_todas(MudarTodasBody(id="lote-0001", pane_ids=["w1:p1", "w3:p2"], confirmado=True)))
    assert out["mudadas"] == []
    assert out["fallidas"][0]["pane_id"] == "w1:p1"
    assert [s["pane_id"] for s in out["saltadas"]] == ["w3:p2"]
    assert herdr.calls_of("cerrar") == [("cerrar", "w1:t1")]


def test_idempotencia_por_id(tmp_path):
    svc, herdr, g, store, _ = armar(tmp_path)
    run(svc.mudar(body()))
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 409
    assert herdr.calls_of("cerrar") == [("cerrar", "w1:t1")]


def test_confirmacion_requerida():
    with pytest.raises(ValidationError):
        MudanzaBody(id="mud-0001", pane_id="w1:p1", confirmado=False)
    with pytest.raises(ValidationError):
        MudanzaBody(id="mud-0001", pane_id="w1:p1")
    with pytest.raises(ValidationError):
        MudarTodasBody(id="lote-0001", pane_ids=["w1:p1"], confirmado=False)


def test_sin_guardian_no_cierra_nada(tmp_path):
    svc, herdr, g, store, _ = armar(tmp_path)
    svc.guardian = lambda: None
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 503
    assert herdr.calls_of("cerrar") == []


def test_guardian_caido_no_cierra_nada(tmp_path):
    svc, herdr, g, store, _ = armar(tmp_path)
    g.caer()
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 503
    assert herdr.calls_of("cerrar") == []
    out = run(svc.candidatas())
    assert out["disponible"] is False and out["motivo"]


def test_conversacion_que_no_esta_en_la_carpeta_del_cwd(tmp_path):
    svc, herdr, *_ = armar(tmp_path, transcript=lambda sid: Path(f"/claude/projects/-otra/{sid}.jsonl"))
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 409
    assert herdr.calls_of("cerrar") == []
    svc2, herdr2, *_ = armar(tmp_path / "b", transcript=lambda sid: None)
    with pytest.raises(TraspasoError):
        run(svc2.mudar(body()))
    assert herdr2.calls_of("cerrar") == []


def test_si_el_guardian_ya_tiene_esa_conversacion_no_cierra(tmp_path):
    ses = Sesion(id="g1:p1", linea_id="g1:t1", espacio_id="g1", programa="claude", estado="idle",
                 estado_fuente="guardian", claude_session_id=SID, cwd=CWD, cwd_primer_plano=None,
                 titulo="", revision=None, backend="guardian")
    g = FakeGuardian(Tablero((Espacio("g1", "Proyecto X", ("g1:t1",)),), (Linea("g1:t1", "g1", "api", ("g1:p1",)),),
                             (ses,), 1))
    svc, herdr, *_ = armar(tmp_path, guardian=g)
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 409
    assert herdr.calls_of("cerrar") == []


def test_sin_pid_de_claude_no_cierra(tmp_path):
    svc, herdr, *_ = armar(tmp_path)
    herdr.procesos["w1:p1"] = InfoProceso(pid=None, comando=None, cwd=None, es_claude=False)
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 409
    assert herdr.calls_of("cerrar") == []


def test_no_muda_ids_del_guardian(tmp_path):
    svc, herdr, *_ = armar(tmp_path)
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body(pane="g1:p1")))
    assert exc.value.status in (400, 404)


def test_candidatas(tmp_path):
    svc, *_ = armar(tmp_path)
    out = run(svc.candidatas())
    assert out["disponible"] is True
    por_pane = {s["pane_id"]: s for s in out["sesiones"]}
    assert por_pane["w1:p1"]["puede"] is True
    assert por_pane["w1:p1"]["session_id"] == SID
    assert por_pane["w2:p1"]["puede"] is False and por_pane["w2:p1"]["motivo"]
    assert por_pane["w2:p2"]["puede"] is False
    assert "w3:p1" not in por_pane
    assert out["pendientes"] == []


def test_si_claude_no_arranca_en_el_guardian_queda_pendiente(tmp_path):
    from dataclasses import replace

    svc, herdr, g, store, eventos = armar(tmp_path)
    arrancar = g.arrancar_claude

    async def arranca_y_muere(sid, nombre, resume=None):
        await arrancar(sid, nombre, resume)
        g.tablero_actual = replace(g.tablero_actual, sesiones=tuple(
            replace(s, estado="perdida") if s.id == sid else s for s in g.tablero_actual.sesiones))

    g.arrancar_claude = arranca_y_muere
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 502 and SID in exc.value.detail
    assert store.get("mud-0001")["estado"] == "pendiente"
    assert eventos == []


def test_guardian_que_no_responde_dentro_del_lock_no_cierra(tmp_path):
    svc, herdr, g, store, _ = armar(tmp_path)
    tablero = g.tablero
    llamadas = []

    async def falla_la_segunda():
        llamadas.append(1)
        if len(llamadas) > 1:
            raise NoDisponible("caído")
        return await tablero()

    g.tablero = falla_la_segunda
    with pytest.raises(TraspasoError) as exc:
        run(svc.mudar(body()))
    assert exc.value.status == 503
    assert herdr.calls_of("cerrar") == []
