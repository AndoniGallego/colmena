import pytest

from conftest import PIN
from orquestador.traspaso import TraspasoError

PID_MALO = "zz" * 16


class Claude:
    def __init__(self):
        self.calls = []

    async def __call__(self, repo, mensaje, nombre, ident):
        self.calls.append((repo, mensaje, nombre, ident))
        return {"pane_id": "w1:p1", "ruta": repo + "-c", "rama": "feature/x", "pegado": True}


@pytest.fixture
def mundo(app, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    svc = app.state.programadas
    svc.plan_cwds = lambda: [str(tmp_path)]
    svc.real = svc.lanzar_claude
    svc.lanzar_claude = Claude()
    return svc, repo


def body(repo, **kw):
    base = {"nombre": "Revisar PRs", "repo": str(repo), "pedido": "Mirá los PRs", "agente": "claude",
            "cuando": {"tipo": "diaria", "hora": "09:00"}}
    base.update(kw)
    return base


def test_instalacion_nueva_apagada_y_sin_programas(authed, mundo):
    r = authed.get("/api/programadas")
    assert r.status_code == 200
    d = r.json()
    assert d["habilitado"] is False and d["programas"] == [] and isinstance(d["cursor_disponible"], bool)


def test_todos_los_endpoints_exigen_sesion(client):
    pid = "a" * 32
    pedidos = [
        ("get", "/api/programadas", None), ("get", "/api/programadas/historial", None),
        ("post", "/api/programadas", {}), ("put", f"/api/programadas/{pid}", {}),
        ("delete", f"/api/programadas/{pid}", None), ("post", f"/api/programadas/{pid}/pausa", {}),
        ("post", f"/api/programadas/{pid}/correr", {}), ("post", "/api/programadas/habilitar", {}),
    ]
    for metodo, ruta, cuerpo in pedidos:
        r = getattr(client, metodo)(ruta, **({"json": cuerpo} if cuerpo is not None else {}))
        assert r.status_code == 401, (metodo, ruta, r.status_code)


def test_crud_por_api(authed, mundo):
    svc, repo = mundo
    r = authed.post("/api/programadas", json=body(repo))
    assert r.status_code == 200 and r.json()["pausada"] is True
    pid = r.json()["id"]
    r = authed.put(f"/api/programadas/{pid}", json=body(repo, nombre="Otro"))
    assert r.status_code == 200 and r.json()["nombre"] == "Otro"
    r = authed.post(f"/api/programadas/{pid}/pausa", json={"pausada": False})
    assert r.status_code == 200 and r.json()["pausada"] is False
    lista = authed.get("/api/programadas").json()
    assert lista["programas"][0]["proxima"] > 0
    assert authed.delete(f"/api/programadas/{pid}").status_code == 200
    assert authed.delete(f"/api/programadas/{pid}").status_code == 404
    assert authed.get("/api/programadas").json()["programas"] == []


def test_repo_fuera_de_lo_permitido_400_y_cuerpo_invalido_422(authed, mundo):
    svc, repo = mundo
    assert authed.post("/api/programadas", json=body("/etc")).status_code == 400
    assert authed.post("/api/programadas", json=body(repo, agente="otro")).status_code == 422
    assert authed.post("/api/programadas", json=body(repo, modelo="a b;rm")).status_code == 422
    assert authed.post("/api/programadas", json={**body(repo), "extra": 1}).status_code == 422
    assert authed.put(f"/api/programadas/{PID_MALO}", json=body(repo)).status_code == 422
    assert authed.post(f"/api/programadas/{PID_MALO}/pausa", json={"pausada": True}).status_code == 422
    r = authed.post("/api/programadas", json=body(repo, pedido=""))
    assert r.status_code == 422 and "Mirá" not in r.text


def test_habilitar_exige_pin_para_prender_y_no_para_apagar(authed, mundo):
    svc, _ = mundo
    assert authed.post("/api/programadas/habilitar", json={"habilitado": True}).status_code == 403
    assert authed.post("/api/programadas/habilitar", json={"habilitado": True, "pin": "mal-pin-12"}).status_code == 403
    assert svc.habilitado is False
    r = authed.post("/api/programadas/habilitar", json={"habilitado": True, "pin": PIN})
    assert r.status_code == 200 and r.json() == {"habilitado": True}
    assert svc.habilitado is True
    assert authed.post("/api/programadas/habilitar", json={"habilitado": False}).status_code == 200
    assert svc.habilitado is False


def test_pin_malo_repetido_limita(authed, mundo):
    codigos = [authed.post("/api/programadas/habilitar", json={"habilitado": True, "pin": "mal-pin-12"}).status_code
               for _ in range(12)]
    assert codigos[0] == 403 and 429 in codigos


def test_correr_ahora_idempotente_y_con_global_apagado(authed, mundo):
    svc, repo = mundo
    pid = authed.post("/api/programadas", json=body(repo)).json()["id"]
    r1 = authed.post(f"/api/programadas/{pid}/correr", json={"id": "corrida-1234"})
    assert r1.status_code == 200 and r1.json()["estado"] == "ok" and r1.json()["manual"] is True
    r2 = authed.post(f"/api/programadas/{pid}/correr", json={"id": "corrida-1234"})
    assert r2.json()["id"] == r1.json()["id"] and len(svc.lanzar_claude.calls) == 1
    assert authed.post(f"/api/programadas/{pid}/correr", json={}).status_code == 422
    h = authed.get(f"/api/programadas/historial?programa={pid}&limite=5").json()
    assert len(h) == 1 and h[0]["estado"] == "ok"
    assert authed.get("/api/programadas/historial?programa=xx").status_code == 422


def test_correr_ahora_bloqueado_da_409(authed, mundo):
    svc, repo = mundo
    pid = authed.post("/api/programadas", json=body(repo)).json()["id"]
    svc.sesion_abierta = lambda pane: True
    assert authed.post(f"/api/programadas/{pid}/correr", json={"id": "corrida-aaaa"}).status_code == 200
    r = authed.post(f"/api/programadas/{pid}/correr", json={"id": "corrida-bbbb"})
    assert r.status_code == 409 and "abierta" in r.json()["detail"]


def test_la_corrida_claude_va_con_permiso_default(authed, mundo, monkeypatch):
    """El callback del ancla llama a nueva_tarea con permiso='default' y el mensaje de la tarea programada."""
    from orquestador import terminales_acciones as tacc
    svc, repo = mundo
    visto = {}

    async def falsa(self, ctx, body, *, permiso=None):
        visto.update(ctx=ctx, body=body, kw={"permiso": permiso})
        return {"detalle": [], "pane_id": "w1:p1", "ruta": "/r", "rama": "feature/x", "tarea": body.tarea}

    monkeypatch.setattr(tacc.TerminalActions, "nueva_tarea", falsa)
    svc.lanzar_claude = svc.real
    pid = authed.post("/api/programadas", json=body(repo)).json()["id"]
    r = authed.post(f"/api/programadas/{pid}/correr", json={"id": "corrida-cccc"})
    assert r.json()["estado"] == "ok"
    assert visto["kw"] == {"permiso": "default"}
    assert visto["ctx"].user == "colmena"
    assert visto["body"].tarea.startswith("Tarea programada «Revisar PRs»")



def test_los_dobles_respetan_las_firmas_reales_de_e1():
    import inspect
    from orquestador import terminales_acciones as tacc
    from orquestador.cursor_runner import CursorRunner
    real = inspect.signature(CursorRunner.lanzar)
    assert {"carpeta", "pedido", "nombre", "origen", "base", "modelo"} <= set(real.parameters)
    assert real.parameters["base"].default == "head"
    assert inspect.signature(tacc.TerminalActions.nueva_tarea).parameters["permiso"].kind is inspect.Parameter.KEYWORD_ONLY


def test_programa_de_cursor_pasa_por_lanzar_con_base_defecto(authed, mundo):
    svc, repo = mundo
    from tests.test_programadas import CursorFalso
    falso = CursorFalso()
    svc.cursor_runner = lambda: falso
    pid = authed.post("/api/programadas", json=body(repo, agente="cursor", modelo="auto")).json()["id"]
    r = authed.post(f"/api/programadas/{pid}/correr", json={"id": "corrida-dddd"})
    assert r.status_code == 200
    kw = falso.calls[0]
    assert kw["base"] == "defecto" and kw["modelo"] == "auto" and kw["origen"]["tipo"] == "programada"
    assert set(kw) <= {"carpeta", "pedido", "nombre", "origen", "base", "modelo"}


def test_modelo_con_caracter_invalido_o_guion_inicial_da_422(authed, mundo):
    _, repo = mundo
    assert authed.post("/api/programadas", json=body(repo, modelo="--force")).status_code == 422


def test_i1_dos_corridas_del_mismo_programa_dan_ramas_distintas(authed, mundo, monkeypatch):
    """La rama sale del texto como en el real (rama_para): sin sufijo, la segunda corrida chocaría."""
    import os
    from orquestador import terminales_acciones as tacc
    from orquestador.nueva_tarea import rama_para
    from orquestador.traspaso import TraspasoError
    svc, repo = mundo
    usadas: list[str] = []

    async def falsa(self, ctx, body, *, permiso=None):
        rama = body.rama or rama_para(os.path.basename(str(repo)), body.tarea)
        if rama in usadas:
            raise TraspasoError(409, f"Ya hay una rama {rama}")
        usadas.append(rama)
        return {"detalle": [], "pane_id": "w1:p1", "ruta": "/r", "rama": rama, "tarea": body.tarea}

    monkeypatch.setattr(tacc.TerminalActions, "nueva_tarea", falsa)
    svc.lanzar_claude = svc.real
    pid = authed.post("/api/programadas", json=body(repo)).json()["id"]
    a = authed.post(f"/api/programadas/{pid}/correr", json={"id": "corrida-aaaa1"}).json()
    svc.sesion_abierta = lambda pane: False
    b = authed.post(f"/api/programadas/{pid}/correr", json={"id": "corrida-bbbb2"}).json()
    assert a["estado"] == "ok" and b["estado"] == "ok" and a["rama"] != b["rama"]
    assert a["rama"].startswith("feature/")


def test_m5_el_mensaje_se_pega_con_origen_programada(authed, mundo, monkeypatch):
    from orquestador import terminales_acciones as tacc
    from orquestador.mensaje import MensajeService
    svc, repo = mundo
    vistos = []

    async def falsa(self, ctx, body, *, permiso=None):
        return {"detalle": [{"tipo": "claude", "mensaje": "hola", "pegado": True, "pane_id": "w1:p1"}],
                "pane_id": "w1:p1", "ruta": "/r", "rama": "feature/x"}

    async def execute(self, cuerpo, auditoria=None):
        vistos.append(cuerpo.origen)
        return {}

    monkeypatch.setattr(tacc.TerminalActions, "nueva_tarea", falsa)
    monkeypatch.setattr(MensajeService, "execute", execute)
    svc.lanzar_claude = svc.real
    pid = authed.post("/api/programadas", json=body(repo)).json()["id"]
    assert authed.post(f"/api/programadas/{pid}/correr", json={"id": "corrida-mmmm5"}).json()["estado"] == "ok"
    assert vistos == ["programada"]
