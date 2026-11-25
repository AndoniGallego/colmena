"""Acciones del MCP de Colmena y su ciclo de vida como Tasks (CA11-13, CA18, CA21)."""
import asyncio
from types import SimpleNamespace

import pytest
from test_pedido_cursor import RunnerFalso
from test_pedidos_pestana import SID, apagada_app, enchufe, sender, wall  # noqa: F401

from orquestador import mcp_canal, mcp_colmena, mcp_ops
from orquestador.colmena_pestana import PREFIJO_PEDIDO
from orquestador.pedidos_pestana import PedidosPestanaStore
from orquestador.pedidos_sesion import PedidosSesion
from orquestador.traspaso import TraspasoError

YO = {"sesion_id": "g1:p1", "pane_id": "g1:p1", "nombre": "Yo", "claude_session_id": "c-yo", "modo": None}
OTRO = {"sesion_id": "g2:p1", "pane_id": "g2:p1", "nombre": "Otra", "claude_session_id": "c-otra", "modo": None}

SESIONES = [
    {"id": "g1:p1", "nombre": "Yo", "estado": "idle", "claude_session_id": "c-yo", "modo": None, "cwd": "/tmp"},
    {"id": "g2:p1", "nombre": "Otra", "estado": "idle", "claude_session_id": "c-otra", "modo": None, "cwd": "/tmp"},
    {"id": "g3:p1", "nombre": "Copi", "estado": "idle", "claude_session_id": "c-copi", "modo": "copiloto",
     "cwd": "/tmp"},
]


class _Push:
    async def dispatch_pestana(self, *a, **kw):
        return 1


def _armar(tmp_path):
    store = PedidosPestanaStore()
    tareas = []
    ps = PedidosSesion(store, lambda: {}, SimpleNamespace(plan_cwds=[str(tmp_path)]), _Push(),
                       lambda coro: (tareas.append(coro), coro.close()), cierres=None)

    async def listar():
        return SESIONES

    return mcp_ops.OpsAcciones(ps, store, listar), store


def _error(coro) -> mcp_canal.ErrorCanal:
    with pytest.raises(mcp_canal.ErrorCanal) as exc:
        asyncio.run(coro)
    return exc.value


def test_handlers_cubren_las_acciones_y_el_estado(tmp_path):
    ops, _ = _armar(tmp_path)
    assert set(ops.handlers()) == {"abrir", "cerrar", "cursor", "mensaje", "programar", "tarea_ticket",
                                   "estado_pedido"}
    assert set(ops.handlers()) | {"sesiones", "leer_sesion", "pedidos", "buscar_memoria"} == mcp_canal.OPS


# --- respuesta sin Tasks (CA12) ---

def test_abrir_devuelve_pedido_pendiente(tmp_path):
    ops, store = _armar(tmp_path)
    res = asyncio.run(ops.abrir(YO, {"carpeta": str(tmp_path), "mensaje": "hacé x"}))
    assert set(res) == {"pedido_id", "estado", "vence"} and res["estado"] == "pendiente"
    item = store.get(res["pedido_id"])
    assert item["via"] == "mcp" and item["origen"]["pane_id"] == "g1:p1" and item["origen"]["session_id"] == "c-yo"


def test_abrir_ignora_una_accion_colada_en_los_argumentos(tmp_path):
    ops, store = _armar(tmp_path)
    assert _error(ops.abrir(YO, {"carpeta": str(tmp_path), "mensaje": "x", "accion": "cerrar",
                                 "terminal": "t"})).codigo == "argumentos_invalidos"
    assert store._items == {}


def test_descarte_se_devuelve_como_error_con_el_motivo(tmp_path):
    ops, _ = _armar(tmp_path)
    err = _error(ops.abrir(YO, {"carpeta": "/no/existe", "mensaje": "x"}))
    assert err.codigo == "carpeta_no_permitida"
    asyncio.run(ops.abrir(YO, {"carpeta": str(tmp_path), "mensaje": "x"}))
    assert _error(ops.abrir(YO, {"carpeta": str(tmp_path), "mensaje": "y"})).codigo == "cooldown"


def test_cerrar_exige_exactamente_un_destino(tmp_path):
    ops, _ = _armar(tmp_path)
    assert _error(ops.cerrar(YO, {})).codigo == "argumentos_invalidos"
    assert _error(ops.cerrar(YO, {"sesion": "a", "tarjeta": "b"})).codigo == "argumentos_invalidos"


def test_cursor_valida_como_la_marca(tmp_path):
    ops, _ = _armar(tmp_path)
    assert _error(ops.cursor(YO, {"carpeta": str(tmp_path), "nombre": "x"})).codigo == "argumentos_invalidos"
    res = asyncio.run(ops.cursor(YO, {"carpeta": str(tmp_path), "nombre": "Renombrar", "pedido": "x por y"}))
    assert res["estado"] == "pendiente"


def test_mensaje_resuelve_el_destino_y_rechaza_copiloto_y_la_propia(tmp_path):
    ops, store = _armar(tmp_path)
    assert _error(ops.mensaje(YO, {"sesion": "g9:p9", "texto": "x"})).codigo == "no_encontrada"
    assert _error(ops.mensaje(YO, {"sesion": "g3:p1", "texto": "x"})).codigo == "sesion_no_permitida"
    assert _error(ops.mensaje(YO, {"sesion": "g1:p1", "texto": "x"})).codigo == "sesion_no_permitida"
    res = asyncio.run(ops.mensaje(YO, {"sesion": "g2:p1", "texto": "revisá esto"}))
    item = store.get(res["pedido_id"])
    assert item["estado"] == "pendiente" and item["envio"]["texto"] == PREFIJO_PEDIDO + "revisá esto"


def test_programar_va_a_la_propia_si_no_hay_destino(tmp_path):
    ops, store = _armar(tmp_path)
    assert _error(ops.programar(YO, {"texto": "x", "cuando": "mañana"})).codigo == "argumentos_invalidos"
    res = asyncio.run(ops.programar(YO, {"texto": "acordate", "cuando": "18:00"}))
    assert store.get(res["pedido_id"])["programada"]["pane_id"] == "g1:p1"


def test_tarea_ticket(tmp_path):
    ops, store = _armar(tmp_path)
    assert _error(ops.tarea_ticket(YO, {"ticket": "x", "carpeta": str(tmp_path)})).codigo == "argumentos_invalidos"
    res = asyncio.run(ops.tarea_ticket(YO, {"ticket": "SITE-9", "carpeta": str(tmp_path)}))
    assert store.get(res["pedido_id"])["tarea"] == {"ticket": "SITE-9"}


# --- estado_pedido y ciclo de vida (CA11, CA12, CA13) ---

def _nuevo(ops, tmp_path, ident=YO):
    return asyncio.run(ops.abrir(ident, {"carpeta": str(tmp_path), "mensaje": "x"}))["pedido_id"]


def _estado(ops, ident, pid, **kw):
    return asyncio.run(ops.estado_pedido(ident, {"pedido_id": pid, **kw}))


@pytest.mark.parametrize("final, esperado, task", [
    (None, {"estado": "pendiente"}, "working"),
    ("abierto", {"estado": "aprobado"}, "completed"),
    ("rechazado", {"estado": "rechazado"}, "failed"),
    ("vencido", {"estado": "vencido"}, "failed"),
])
def test_estados_del_pedido_y_su_task(tmp_path, final, esperado, task):
    ops, store = _armar(tmp_path)
    pid = _nuevo(ops, tmp_path)
    if final == "vencido":
        store._items[pid]["vence"] = 0
    elif final:
        store.marcar(pid, final)
    res = _estado(ops, YO, pid)
    assert res["pedido_id"] == pid and {k: res[k] for k in esperado} == esperado
    assert mcp_colmena.task_de_estado(pid, res)["status"] == task


def test_falla_al_ejecutar_queda_failed_con_el_codigo(tmp_path):
    ops, store = _armar(tmp_path)
    pid = _nuevo(ops, tmp_path)
    store.fallar(pid, "tope_alcanzado", retry_after=60)
    res = _estado(ops, YO, pid)
    assert res["estado"] == "descartado" and res["detalle"] == "tope_alcanzado" and res["retry_after"] == 60
    assert mcp_colmena.task_de_estado(pid, res)["status"] == "failed"


def test_aprobado_trae_el_resultado(tmp_path):
    ops, store = _armar(tmp_path)
    pid = _nuevo(ops, tmp_path)
    store.marcar(pid, "abierto")
    store.poner_resultado(pid, {"pane_id": "w7:p1"})
    assert _estado(ops, YO, pid)["resultado"] == {"pane_id": "w7:p1"}


def test_pedido_de_otra_sesion_es_no_encontrada(tmp_path):
    ops, _ = _armar(tmp_path)
    pid = _nuevo(ops, tmp_path, ident=OTRO)
    assert _error(ops.estado_pedido(YO, {"pedido_id": pid})).codigo == "no_encontrada"
    assert _error(ops.estado_pedido(YO, {"pedido_id": pid, "cancelar": True})).codigo == "no_encontrada"
    assert _error(ops.estado_pedido(YO, {"pedido_id": "no-existe"})).codigo == "no_encontrada"


def test_mismo_pane_con_otra_sesion_de_claude_tampoco_lo_ve(tmp_path):
    ops, _ = _armar(tmp_path)
    pid = _nuevo(ops, tmp_path)
    otra_vida = {**YO, "claude_session_id": "c-nueva"}
    assert _error(ops.estado_pedido(otra_vida, {"pedido_id": pid})).codigo == "no_encontrada"


def test_cancelar_marca_descartado_y_nunca_aprueba(tmp_path):
    ops, store = _armar(tmp_path)
    pid = _nuevo(ops, tmp_path)
    res = _estado(ops, YO, pid, cancelar=True)
    assert res["estado"] == "descartado" and res["detalle"] == "cancelado"
    assert mcp_colmena.task_de_estado(pid, res)["status"] == "cancelled"
    ops2, store2 = _armar(tmp_path)  # otro store: sin el cooldown del primero
    pid2 = asyncio.run(ops2.cursor(YO, {"carpeta": str(tmp_path), "nombre": "N", "pedido": "p"}))
    store2.marcar(pid2["pedido_id"], "abierto")
    assert _estado(ops2, YO, pid2["pedido_id"], cancelar=True)["estado"] == "aprobado"


def test_esperar_vuelve_apenas_cambia_el_estado(tmp_path):
    ops, store = _armar(tmp_path)

    async def caso():
        pid = (await ops.abrir(YO, {"carpeta": str(tmp_path), "mensaje": "x"}))["pedido_id"]
        espera = asyncio.create_task(ops.estado_pedido(YO, {"pedido_id": pid, "esperar": 20}))
        await asyncio.sleep(0.05)
        assert not espera.done()
        store.marcar(pid, "rechazado")
        return await asyncio.wait_for(espera, 2)

    assert asyncio.run(caso())["estado"] == "rechazado"


def test_esperar_sin_cambios_vuelve_pendiente_al_vencer_la_espera(tmp_path):
    ops, _ = _armar(tmp_path)

    async def caso():
        pid = (await ops.abrir(YO, {"carpeta": str(tmp_path), "mensaje": "x"}))["pedido_id"]
        ops.unidad_espera = 0.01
        return await asyncio.wait_for(ops.estado_pedido(YO, {"pedido_id": pid, "esperar": 1}), 2)

    assert asyncio.run(caso())["estado"] == "pendiente"


@pytest.mark.parametrize("args", [{}, {"pedido_id": 3}, {"pedido_id": "x", "esperar": 26},
                                  {"pedido_id": "x", "esperar": True}, {"pedido_id": "x", "cancelar": "si"}])
def test_estado_pedido_argumentos_invalidos(tmp_path, args):
    ops, _ = _armar(tmp_path)
    assert _error(ops.estado_pedido(YO, args)).codigo == "argumentos_invalidos"


def test_lista_de_pedidos_del_cliente_arma_tasks():
    srv = mcp_colmena.ServidorStdio(None)
    srv._llamar = lambda op, args, **kw: ({"pedidos": [{"pedido_id": "p1", "accion": "abrir", "estado": "pendiente",
                                                        "vence": 1}]}, None)
    tasks = srv.manejar({"jsonrpc": "2.0", "id": 1, "method": "tasks/list"})["result"]["tasks"]
    assert [t["taskId"] for t in tasks] == ["p1"] and tasks[0]["status"] == "working"


# --- topes de creación por hora (CA21) ---

def test_topes_de_creacion_por_hora():
    reloj = [0.0]
    topes = mcp_canal.Topes(reloj=lambda: reloj[0])
    for _ in range(30):
        topes.cobrar("abrir", "g1:p1")
    with pytest.raises(mcp_canal.ErrorCanal) as exc:
        topes.cobrar("cursor", "g1:p1")
    assert exc.value.codigo == "tope_alcanzado" and exc.value.extra["retry_after"] > 0
    for i in range(60):
        topes.cobrar("abrir", f"g{i + 10}:p1")
    with pytest.raises(mcp_canal.ErrorCanal):
        topes.cobrar("abrir", "g99:p1")  # global: 90 por hora
    reloj[0] = 3601
    for _ in range(10):
        topes.cobrar("mensaje", "g5:p1")
    with pytest.raises(mcp_canal.ErrorCanal) as exc:
        topes.cobrar("mensaje", "g5:p1")
    assert exc.value.codigo == "tope_alcanzado"
    topes.cobrar("abrir", "g5:p1")  # el tope de mensajes no frena las otras acciones
    topes.cobrar("leer_sesion", "g1:p1")  # ni las lecturas


# --- aprobación de las acciones (app) ---



def _mcp(app, metodo, *args):
    item, motivo = getattr(app.state.pedidos_sesion, metodo)(*args, "w1:p1", SID, "Uno", via="mcp")
    assert motivo is None, motivo
    return item["id"]


def test_aprobar_mensaje_lo_manda_con_prefijo_a_la_destino(apagada_app, monkeypatch):
    c, app, _, _, _ = apagada_app
    enviados = []

    async def execute(body, auditoria=None):
        enviados.append(body)
        return {"ok": True}

    monkeypatch.setattr(app.state.mensajes, "execute", execute)
    pid = _mcp(app, "mensaje", {"pane_id": "w2:p1", "nombre": "Dos"}, "revisá el MR")
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 200, r.text
    [body] = enviados
    assert body.pane_id == "w2:p1" and body.texto == PREFIJO_PEDIDO + "revisá el MR"
    assert body.origen == "pedido-pestana"
    item = app.state.pedidos_pestana.get(pid)
    assert item["estado"] == "abierto" and item["resultado"] == {"pane_id": "w2:p1"}


def test_mensaje_que_no_se_pudo_mandar_queda_failed_para_el_mcp(apagada_app, monkeypatch):
    c, app, _, _, _ = apagada_app

    async def execute(body, auditoria=None):
        raise TraspasoError(409, "la sesión está ocupada")

    monkeypatch.setattr(app.state.mensajes, "execute", execute)
    pid = _mcp(app, "mensaje", {"pane_id": "w2:p1", "nombre": "Dos"}, "hola")
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 409
    item = app.state.pedidos_pestana.get(pid)
    assert item["estado"] == "descartado" and item["resultado"]["codigo"] == "error_al_ejecutar"


def test_aprobar_programada_la_agenda_una_sola_vez(apagada_app, monkeypatch):
    c, app, _, _, _ = apagada_app
    agendadas = []
    monkeypatch.setattr(app.state, "agendar_programada_unica", lambda item: agendadas.append(item["id"]) or 3600.0)
    pid = _mcp(app, "programada", "acordate del deploy", "09:30", {"pane_id": "w1:p1", "nombre": "Uno"})
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 200, r.text
    assert agendadas == [pid]
    item = app.state.pedidos_pestana.get(pid)
    assert item["estado"] == "abierto" and item["resultado"] == {"cuando": "09:30", "en_segundos": 3600}


def test_aprobar_tarea_con_requiere_confianza_queda_failed(apagada_app, tmp_path, monkeypatch):
    c, app, _, _, _ = apagada_app
    repo = tmp_path / "repo"
    repo.mkdir()
    vistos = []

    async def nueva_tarea(ctx, body, permiso=None, nota_ajena=False):
        vistos.append((body, permiso, nota_ajena))
        raise TraspasoError(409, "revisalo antes de confiar", {"codigo": "requiere_confianza", "confianza": {}})

    monkeypatch.setattr(app.state.tacciones, "nueva_tarea", nueva_tarea)
    pid = _mcp(app, "tarea", "SITE-12", str(repo), "mirá el CA2")
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 409
    body, permiso, nota_ajena = vistos[0]
    assert body.repo == str(repo) and body.ticket == "SITE-12" and permiso == "default"
    # La nota la escribió otra sesión: no puede llegar como "Nota de Ando".
    assert body.tarea == "mirá el CA2" and nota_ajena is True
    item = app.state.pedidos_pestana.get(pid)
    assert item["estado"] == "descartado" and item["resultado"]["codigo"] == "requiere_confianza"


def test_aprobar_tarea_ok_queda_completed(apagada_app, tmp_path, monkeypatch):
    c, app, _, _, _ = apagada_app
    repo = tmp_path / "repo"
    repo.mkdir()

    async def nueva_tarea(ctx, body, permiso=None, nota_ajena=False):
        return {"pane_id": "w8:p1", "ruta": "/r", "rama": "feature/SITE-12", "tarea": body.tarea, "detalle": []}

    monkeypatch.setattr(app.state.tacciones, "nueva_tarea", nueva_tarea)
    pid = _mcp(app, "tarea", "SITE-12", str(repo), "")
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 200
    item = app.state.pedidos_pestana.get(pid)
    assert item["estado"] == "abierto" and item["resultado"]["pane_id"] == "w8:p1"


def test_cursor_del_mcp_con_tope_429_queda_failed(apagada_app, tmp_path):
    c, app, _, _, _ = apagada_app
    repo = tmp_path / "repo"
    repo.mkdir()
    app.state.cursor_runner = RunnerFalso(TraspasoError(429, "tope", {"retry_after": 60}))
    item, motivo = asyncio.run(app.state.pedidos_sesion.desde_mcp(
        {"accion": "cursor", "carpeta": str(repo), "nombre": "N", "pedido": "p"}, "w1:p1", SID, "Uno"))
    assert c.post(f"/api/pedidos-pestana/{item['id']}/abrir").status_code == 429
    final = app.state.pedidos_pestana.get(item["id"])
    assert final["estado"] == "descartado"
    assert final["resultado"] == {"codigo": "tope_alcanzado", "retry_after": 60}


def test_la_app_expone_lectura_y_acciones_al_canal(apagada_app):
    _, app, _, _, _ = apagada_app
    assert {"sesiones", "leer_sesion", "abrir", "mensaje", "programar", "tarea_ticket", "estado_pedido"} <= \
        set(app.state.mcp_ops)


def test_cierre_del_mcp_trabajando_sigue_pendiente_para_cerrar_igual(apagada_app, enchufe):
    """El 409 "Está trabajando" deja el pedido pendiente para que Ando lo fuerce: no es una falla."""
    from orquestador.colmena_pestana import pedido_desde_dict
    from test_pedidos_pestana import _tablero_snapshot

    c, app, _, _, _ = apagada_app
    _tablero_snapshot(app)
    payload = pedido_desde_dict({"accion": "cerrar", "pestana": "propio"})
    item, motivo = asyncio.run(app.state.pedidos_sesion.desde_mcp(payload, "w1:p1", SID, "Uno"))
    assert motivo is None, motivo
    pid = item["id"]
    primero = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert primero.status_code == 409 and primero.json()["detail"] == "Está trabajando: revisalo"
    assert app.state.pedidos_pestana.get(pid)["estado"] == "pendiente"
    v = c.post(f"/api/pedidos-pestana/{pid}/vista-cierre").json()
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir", json={"forzar": True, "huella": v["huella"]})
    assert r.status_code == 200 and r.json()["cerrada"] is True
    assert app.state.pedidos_pestana.get(pid)["estado"] == "abierto"
