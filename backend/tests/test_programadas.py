import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from orquestador import programadas as pg
from orquestador.programadas import Cuando, Programadas, ocurrencias, proxima
from orquestador.traspaso import TraspasoError

MAD = ZoneInfo("Europe/Madrid")
UTC = timezone.utc


def mad(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=MAD)


def diaria(hora="09:00"):
    return Cuando(tipo="diaria", hora=hora)


def dias(lista, hora="09:00"):
    return Cuando(tipo="dias", hora=hora, dias=lista)


def semanal(dia, hora="09:00"):
    return Cuando(tipo="semanal", hora=hora, dia=dia)


# ---------- funciones puras ----------

@pytest.mark.parametrize("cuando,desde,esperada", [
    (diaria("09:00"), mad(2026, 11, 17, 8, 0), mad(2026, 11, 17, 9, 0)),
    (diaria("09:00"), mad(2026, 11, 17, 10, 0), mad(2026, 11, 18, 9, 0)),
    (dias([0, 2, 4], "18:30"), mad(2026, 11, 17, 8, 0), mad(2026, 11, 18, 18, 30)),  # martes -> miércoles
    (dias([0, 2, 4], "18:30"), mad(2026, 11, 20, 19, 0), mad(2026, 11, 23, 18, 30)),  # viernes tarde -> lunes
    (semanal(4, "10:00"), mad(2026, 11, 17, 8, 0), mad(2026, 11, 20, 10, 0)),
    (semanal(1, "10:00"), mad(2026, 11, 17, 11, 0), mad(2026, 11, 24, 10, 0)),
    (diaria("23:59"), mad(2026, 11, 30, 23, 59), mad(2026, 12, 1, 23, 59)),  # fin de mes
    (semanal(6, "08:00"), mad(2026, 11, 28, 12, 0), mad(2026, 11, 29, 8, 0)),  # fin de semana
])
def test_proxima_diaria_dias_semanal(cuando, desde, esperada):
    assert proxima(cuando, desde) == esperada


def test_proxima_borde_exacto():
    assert proxima(diaria("09:00"), mad(2026, 11, 17, 9, 0)) == mad(2026, 11, 18, 9, 0)
    assert proxima(diaria("09:00"), mad(2026, 11, 17, 8, 59)) == mad(2026, 11, 17, 9, 0)


def test_proxima_dst_hora_inexistente_y_repetida():
    # 2026-03-29 02:30 no existe en Madrid: corre a la hora válida siguiente (03:30 CEST = 01:30 UTC)
    p = proxima(diaria("02:30"), mad(2026, 3, 28, 12, 0))
    assert p.astimezone(UTC) == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    # 2026-10-25 02:30 ocurre dos veces: corre solo la primera (00:30 UTC) y la siguiente es el día 26
    primera = proxima(diaria("02:30"), mad(2026, 10, 24, 12, 0))
    assert primera.astimezone(UTC) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    despues = proxima(diaria("02:30"), primera)
    assert despues.astimezone(MAD).date().isoformat() == "2026-10-26"
    segunda_vuelta = datetime(2026, 10, 25, 1, 30, tzinfo=UTC).astimezone(MAD)
    assert proxima(diaria("02:30"), segunda_vuelta).astimezone(MAD).date().isoformat() == "2026-10-26"


def test_ocurrencias_entre_fechas_con_maximo():
    todas = ocurrencias(diaria("09:00"), mad(2026, 11, 10, 12, 0), mad(2026, 11, 14, 12, 0), 99)
    assert todas == [mad(2026, 11, d, 9, 0) for d in (11, 12, 13, 14)]
    ultimas = ocurrencias(diaria("09:00"), mad(2026, 11, 10, 12, 0), mad(2026, 11, 14, 12, 0), 2)
    assert ultimas == [mad(2026, 11, 13, 9, 0), mad(2026, 11, 14, 9, 0)]
    assert ocurrencias(diaria("09:00"), mad(2026, 11, 14, 12, 0), mad(2026, 11, 14, 13, 0), 5) == []


def test_cuando_valida_forma():
    with pytest.raises(ValueError):
        Cuando(tipo="dias", hora="09:00", dias=[])
    with pytest.raises(ValueError):
        Cuando(tipo="dias", hora="09:00", dias=[1, 1])
    with pytest.raises(ValueError):
        Cuando(tipo="semanal", hora="09:00")
    with pytest.raises(ValueError):
        Cuando(tipo="diaria", hora="9:00")
    with pytest.raises(ValueError):
        Cuando(tipo="diaria", hora="09:00", dias=[1])


# ---------- servicio ----------

class Reloj:
    def __init__(self, dt):
        self.dt = dt

    def ahora(self):
        return self.dt

    def tiempo(self):
        return self.dt.timestamp()

    def avanzar(self, **kw):
        self.dt = (self.dt.astimezone(UTC) + timedelta(**kw)).astimezone(MAD)


class Claude:
    def __init__(self):
        self.calls = []
        self.error = None
        self.pegado = True

    async def __call__(self, repo, mensaje, nombre, ident):
        self.calls.append({"repo": repo, "mensaje": mensaje, "nombre": nombre, "ident": ident})
        if self.error:
            raise self.error
        n = len(self.calls)
        return {"pane_id": f"w1:p{n}", "ruta": f"{repo}-copia{n}", "rama": f"feature/t{n}", "pegado": self.pegado}


class CursorFalso:
    MAX_SIMULTANEOS = 2

    def __init__(self, ok=True):
        self.al_terminar = []
        self.ok = ok
        self.calls = []
        self.trabajadores = {}
        self.error = None

    def disponible(self):
        return self.ok

    async def lanzar(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        tid = f"cur{len(self.calls):03d}"
        t = {"id": tid, "nombre": kw["nombre"], "estado": "corriendo", "ruta": kw["carpeta"] + "-c", "rama": "feature/c",
             "base": "main", "inicio": 0, "origen": kw["origen"]}
        self.trabajadores[tid] = t
        return dict(t)

    def get(self, tid):
        return self.trabajadores.get(tid)

    def terminar(self, tid, estado="ok", codigo=0):
        t = {**self.trabajadores[tid], "estado": estado, "codigo": codigo, "archivos": [], "resumen": ""}
        self.trabajadores[tid] = t
        for cb in list(self.al_terminar):
            cb(t)


class Mundo:
    def __init__(self, tmp_path, ahora=None):
        self.tmp = tmp_path
        self.repo = tmp_path / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.reloj = Reloj(ahora or mad(2026, 11, 17, 8, 0))
        self.claude = Claude()
        self.cursor = CursorFalso()
        self.usar_cursor = True
        self.abiertas = set()
        self.eventos = []
        self.avisos = []
        self.svc = self.nuevo()

    def nuevo(self):
        async def avisar(titulo, cuerpo, tag, pane_id=""):
            self.avisos.append((titulo, cuerpo))

        return Programadas(
            self.tmp / "data", lanzar_claude=self.claude,
            cursor_runner=lambda: self.cursor if self.usar_cursor else None,
            plan_cwds=lambda: [str(self.tmp)], sesion_abierta=lambda pane: pane in self.abiertas,
            emit=lambda ev, d: self.eventos.append((ev, d)), avisar=avisar,
            reloj=self.reloj.tiempo, ahora=self.reloj.ahora)

    def body(self, **kw):
        base = {"nombre": "Revisar PRs", "repo": str(self.repo), "pedido": "Mirá los PRs abiertos", "agente": "claude",
                "cuando": {"tipo": "diaria", "hora": "09:00"}}
        base.update(kw)
        return pg.ProgramaBody(**base)

    def crear(self, activo=True, **kw):
        p = self.svc.crear(self.body(**kw))
        if activo:
            self.svc.pausar(p["id"], False)
        return p


@pytest.fixture
def mundo(tmp_path):
    return Mundo(tmp_path)


def run(coro):
    async def con_tope():
        return await asyncio.wait_for(coro, 5)
    return asyncio.run(con_tope())


def test_nace_pausada_y_global_apagado(mundo):
    p = mundo.svc.crear(mundo.body())
    assert p["pausada"] is True
    assert mundo.svc.habilitado is False
    assert len(p["id"]) == 32
    listado = mundo.svc.listar()
    assert listado["habilitado"] is False and listado["programas"][0]["id"] == p["id"]


def test_crud_persistencia_privada_y_tope_30(mundo):
    p = mundo.svc.crear(mundo.body())
    archivo = mundo.tmp / "data" / "programadas.json"
    assert archivo.exists() and (archivo.stat().st_mode & 0o777) == 0o600
    assert json.loads(archivo.read_text())["programas"][0]["id"] == p["id"]
    editado = mundo.svc.editar(p["id"], mundo.body(nombre="Otro nombre"))
    assert editado["nombre"] == "Otro nombre" and editado["pausada"] is True and editado["id"] == p["id"]
    assert mundo.nuevo().listar()["programas"][0]["nombre"] == "Otro nombre"
    mundo.svc.borrar(p["id"])
    assert mundo.svc.listar()["programas"] == []
    for i in range(30):
        mundo.svc.crear(mundo.body(nombre=f"t{i}"))
    with pytest.raises(TraspasoError) as e:
        mundo.svc.crear(mundo.body(nombre="una más"))
    assert e.value.status == 409
    with pytest.raises(TraspasoError) as e:
        mundo.svc.editar("0" * 32, mundo.body())
    assert e.value.status == 404


def test_repo_no_permitido_400_al_crear_y_fallo_al_correr(mundo, tmp_path):
    with pytest.raises(TraspasoError) as e:
        mundo.svc.crear(mundo.body(repo="/etc"))
    assert e.value.status == 400
    sin_git = tmp_path / "sin-git"
    sin_git.mkdir()
    with pytest.raises(TraspasoError) as e:
        mundo.svc.crear(mundo.body(repo=str(sin_git)))
    assert e.value.status == 400
    p = mundo.crear()
    mundo.svc.plan_cwds = lambda: [str(tmp_path / "otro")]
    c = run(mundo.svc.correr(p["id"], manual=True))
    assert c["estado"] == "fallo" and mundo.claude.calls == []


def test_repo_de_colmena_no_es_valido(mundo):
    from orquestador.config import REPO_ROOT
    mundo.svc.plan_cwds = lambda: [str(REPO_ROOT.parent)]
    with pytest.raises(TraspasoError) as e:
        mundo.svc.crear(mundo.body(repo=str(REPO_ROOT)))
    assert e.value.status == 400


def test_bucle_no_dispara_con_global_apagado(mundo):
    mundo.crear()
    mundo.reloj.dt = mad(2026, 11, 17, 9, 1)
    run(mundo.svc.tick())
    assert mundo.claude.calls == []
    assert mundo.svc.historial() == []


def test_tick_dispara_claude_con_mensaje_exacto(mundo):
    p = mundo.crear()
    mundo.svc.habilitar(True)
    mundo.reloj.dt = mad(2026, 11, 17, 9, 1)
    run(mundo.svc.tick())
    assert len(mundo.claude.calls) == 1
    llamada = mundo.claude.calls[0]
    assert llamada["mensaje"] == "Tarea programada «Revisar PRs» (Todos los días a las 09:00). Mirá los PRs abiertos"
    assert llamada["repo"] == str(mundo.repo) and llamada["nombre"] == "Revisar PRs"
    assert 8 <= len(llamada["ident"]) <= 64
    h = mundo.svc.historial()
    assert h[0]["estado"] == "ok" and h[0]["pane_id"] == "w1:p1" and h[0]["rama"] == "feature/t1"
    assert h[0]["programa_id"] == p["id"] and h[0]["manual"] is False and h[0]["agente"] == "claude"
    assert mundo.avisos[0][0] == "Arrancó la tarea programada «Revisar PRs»"
    run(mundo.svc.tick())
    assert len(mundo.claude.calls) == 1


def test_tick_no_dispara_programa_pausado(mundo):
    mundo.crear(activo=False)
    mundo.svc.habilitar(True)
    mundo.reloj.dt = mad(2026, 11, 17, 9, 1)
    run(mundo.svc.tick())
    assert mundo.claude.calls == [] and mundo.svc.historial() == []


def test_fallo_de_claude_queda_en_historial_y_avisa(mundo):
    mundo.claude.error = TraspasoError(409, "git dijo que no")
    mundo.crear()
    mundo.svc.habilitar(True)
    mundo.reloj.dt = mad(2026, 11, 17, 9, 0)
    run(mundo.svc.tick())
    h = mundo.svc.historial()[0]
    assert h["estado"] == "fallo" and "git dijo que no" in h["motivo"]
    assert mundo.avisos[-1][0] == "No pude correr «Revisar PRs»"
    assert "git dijo que no" in mundo.avisos[-1][1]


def test_tick_dispara_cursor_con_base_defecto(mundo):
    mundo.crear(agente="cursor", modelo="auto")
    mundo.svc.habilitar(True)
    mundo.reloj.dt = mad(2026, 11, 17, 9, 2)
    run(mundo.svc.tick())
    assert len(mundo.cursor.calls) == 1
    kw = mundo.cursor.calls[0]
    assert kw["base"] == "defecto" and kw["carpeta"] == str(mundo.repo) and kw["pedido"] == "Mirá los PRs abiertos"
    assert kw["origen"]["tipo"] == "programada" and kw["origen"]["programa_id"] and kw["origen"]["corrida_id"]
    assert kw["modelo"] == "auto"
    h = mundo.svc.historial()[0]
    assert h["estado"] == "en_curso" and h["trabajador_id"] == "cur001" and h["agente"] == "cursor"
    assert mundo.claude.calls == []


def test_cursor_sin_runner_fallo(mundo):
    p = mundo.crear(agente="cursor")
    mundo.usar_cursor = False
    c = run(mundo.svc.correr(p["id"], manual=True))
    assert c["estado"] == "fallo" and c["motivo"] == "Cursor no está disponible"
    mundo.usar_cursor = True
    mundo.cursor.ok = False
    c = run(mundo.svc.correr(p["id"], manual=True))
    assert c["estado"] == "fallo" and c["motivo"] == "Cursor no está disponible"


def test_al_terminar_trabajador_cierra_corrida(mundo):
    p = mundo.crear(agente="cursor")
    c = run(mundo.svc.correr(p["id"], manual=True))
    assert c["estado"] == "en_curso"
    mundo.cursor.terminar("cur001", "ok", 0)
    assert mundo.svc.historial()[0]["estado"] == "ok"
    c2 = run(mundo.svc.correr(p["id"], manual=True))
    mundo.cursor.terminar("cur002", "error", 1)
    h = mundo.svc.historial()[0]
    assert h["id"] == c2["id"] and h["estado"] == "error" and h["motivo"]


def test_cursor_que_ya_termino_al_volver_lanzar_cierra_corrida(mundo):
    p = mundo.crear(agente="cursor")
    orig = mundo.cursor.lanzar

    async def lanzar_y_terminar(**kw):
        t = await orig(**kw)
        mundo.cursor.trabajadores[t["id"]] = {**t, "estado": "ok", "codigo": 0}
        return t

    mundo.cursor.lanzar = lanzar_y_terminar
    c = run(mundo.svc.correr(p["id"], manual=True))
    assert c["estado"] == "ok"


def test_arranque_marca_salteadas_sin_lanzar(mundo):
    mundo.crear()
    mundo.svc.habilitar(True)
    # la notebook estuvo apagada dos días: el último chequeo es de hace 2 días
    mundo.svc._estado["ultimo_chequeo"] = mad(2026, 11, 14, 10, 0).timestamp()
    mundo.svc._estado["programas"][0]["actualizada"] = mad(2026, 11, 1, 10, 0).timestamp()
    mundo.reloj.dt = mad(2026, 11, 17, 8, 0)
    run(mundo.svc.tick())
    h = mundo.svc.historial()
    assert [c["estado"] for c in h] == ["salteada", "salteada"]
    assert all("apagada o suspendida" in c["motivo"] for c in h)
    assert [c["previsto"] for c in h] == sorted([c["previsto"] for c in h], reverse=True)
    assert mundo.claude.calls == []


def test_corrida_perdida_hace_mas_de_10_min_se_saltea(mundo):
    mundo.crear()
    mundo.svc.habilitar(True)
    mundo.svc._estado["ultimo_chequeo"] = mad(2026, 11, 17, 8, 0).timestamp()
    mundo.reloj.dt = mad(2026, 11, 17, 9, 11)
    run(mundo.svc.tick())
    assert mundo.svc.historial()[0]["estado"] == "salteada" and mundo.claude.calls == []


def test_prender_global_no_recupera_lo_anterior(mundo):
    mundo.crear()
    mundo.reloj.dt = mad(2026, 11, 20, 12, 0)
    run(mundo.svc.tick())
    mundo.svc.habilitar(True)
    run(mundo.svc.tick())
    assert mundo.svc.historial() == []


def test_tope_simultaneas_y_anterior_abierta_salteada(mundo):
    a = mundo.crear(nombre="A")
    mundo.crear(nombre="B")
    c = mundo.crear(nombre="C")
    progs = mundo.svc.listar()["programas"]
    mundo.reloj.dt = mad(2026, 11, 17, 8, 50)
    for p in progs[:2]:
        run(mundo.svc.correr(p["id"], manual=True))
    mundo.abiertas |= {"w1:p1", "w1:p2"}
    mundo.svc.habilitar(True)
    mundo.svc._estado["ultimo_chequeo"] = mad(2026, 11, 17, 8, 0).timestamp()
    mundo.reloj.dt = mad(2026, 11, 17, 9, 0)
    run(mundo.svc.tick())
    estados = {h["nombre"]: (h["estado"], h["motivo"]) for h in mundo.svc.historial() if not h["manual"]}
    assert estados["A"][0] == "salteada" and "sigue abierta" in estados["A"][1]
    assert estados["C"][0] == "salteada" and "2" in estados["C"][1]
    with pytest.raises(TraspasoError) as e:
        run(mundo.svc.correr(c["id"], manual=True))
    assert e.value.status == 409
    mundo.abiertas.discard("w1:p1")
    run(mundo.svc.correr(c["id"], manual=True))
    assert len(mundo.claude.calls) == 3
    assert a["id"]


def test_sesion_vieja_de_30_min_no_cuenta_como_abierta(mundo):
    a = mundo.crear(nombre="A")
    run(mundo.svc.correr(a["id"], manual=True))
    mundo.abiertas.add("w1:p1")
    with pytest.raises(TraspasoError):
        run(mundo.svc.correr(a["id"], manual=True))
    mundo.reloj.avanzar(minutes=31)
    run(mundo.svc.correr(a["id"], manual=True))


def test_correr_ahora_funciona_con_global_apagado_e_idempotente(mundo):
    p = mundo.crear(activo=False)
    c = run(mundo.svc.correr(p["id"], manual=True, ident="abc12345"))
    assert c["estado"] == "ok" and c["manual"] is True
    c2 = run(mundo.svc.correr(p["id"], manual=True, ident="abc12345"))
    assert c2["id"] == c["id"] and len(mundo.claude.calls) == 1


def test_editar_despierta(mundo):
    p = mundo.crear()
    ev = mundo.svc._evento
    ev.clear()
    mundo.svc.editar(p["id"], mundo.body(nombre="Nuevo"))
    assert ev.is_set()
    ev.clear()
    mundo.svc.pausar(p["id"], True)
    assert ev.is_set()
    ev.clear()
    mundo.svc.habilitar(True)
    assert ev.is_set()
    ev.clear()
    mundo.svc.borrar(p["id"])
    assert ev.is_set()


def test_bucle_duerme_la_siesta_maxima_y_se_despierta_al_editar(mundo):
    mundo.crear()
    mundo.svc.habilitar(True)
    esperas = []
    original = asyncio.wait_for

    async def wait_for(aw, timeout):
        esperas.append(timeout)
        return await original(aw, timeout)

    async def escenario():
        asyncio.wait_for = wait_for
        try:
            tarea = asyncio.create_task(mundo.svc.bucle())
            for _ in range(3):
                await asyncio.sleep(0)
            mundo.svc.pausar(mundo.svc.listar()["programas"][0]["id"], True)
            for _ in range(3):
                await asyncio.sleep(0)
            tarea.cancel()
            with pytest.raises(asyncio.CancelledError):
                await tarea
        finally:
            asyncio.wait_for = original

    run(escenario())
    assert esperas[0] == 900
    assert len(esperas) >= 2


def test_historial_se_recorta_a_500(mundo):
    p = mundo.crear()
    for i in range(505):
        mundo.svc._registrar({"id": f"{i:032x}", "programa_id": p["id"], "previsto": i, "inicio": i,
                              "estado": "salteada", "motivo": "x", "agente": "claude", "manual": False, "nombre": "n"})
    assert len(mundo.svc.historial(limite=999)) == 200
    lineas = (mundo.tmp / "data" / "programadas-historial.jsonl").read_text().splitlines()
    assert len(lineas) == 500
    assert mundo.svc.historial(programa_id="x" * 32) == []


def test_corrida_en_curso_de_antes_del_reinicio_se_cierra(mundo):
    p = mundo.crear(agente="cursor")
    run(mundo.svc.correr(p["id"], manual=True))
    nuevo = mundo.nuevo()
    mundo.cursor.trabajadores.clear()
    run(nuevo.tick())
    assert nuevo.historial()[0]["estado"] == "error"


# ---------- arreglos de revisión ----------

class ClaudeConPuerta(Claude):
    """Se queda esperando adentro de lanzar_claude hasta que el test abre la puerta."""

    def __init__(self):
        super().__init__()
        self.puerta = asyncio.Event()

    async def __call__(self, repo, mensaje, nombre, ident):
        self.calls.append({"repo": repo, "mensaje": mensaje, "nombre": nombre, "ident": ident})
        await self.puerta.wait()
        n = len(self.calls)
        return {"pane_id": f"w1:p{n}", "ruta": f"{repo}-c{n}", "rama": f"feature/t{n}", "pegado": True}


def test_i3_bucle_y_correr_ahora_a_la_vez_dan_una_sola_corrida(mundo):
    mundo.claude = ClaudeConPuerta()
    mundo.svc = mundo.nuevo()
    p = mundo.crear()
    mundo.svc.habilitar(True)
    mundo.reloj.dt = mad(2026, 11, 17, 9, 0)

    async def escenario():
        a = asyncio.create_task(mundo.svc.tick())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        b = asyncio.create_task(mundo.svc.correr(p["id"], manual=True, ident="mano-0001"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        mundo.claude.puerta.set()
        resultados = await asyncio.gather(a, b, return_exceptions=True)
        return resultados

    resultados = run(escenario())
    assert len(mundo.claude.calls) == 1
    assert any(isinstance(r, TraspasoError) and r.status == 409 for r in resultados) or \
        sum(1 for c in mundo.svc.historial() if c["estado"] == "ok") == 1


def test_i3_tres_correr_ahora_concurrentes_respetan_el_maximo(mundo):
    mundo.claude = ClaudeConPuerta()
    mundo.svc = mundo.nuevo()
    ps = [mundo.crear(nombre=f"T{i}", pedido=f"p{i}") for i in range(3)]

    async def escenario():
        tareas = [asyncio.create_task(mundo.svc.correr(p["id"], manual=True, ident=f"mano-000{i}")) for i, p in enumerate(ps)]
        for _ in range(4):
            await asyncio.sleep(0)
        mundo.claude.puerta.set()
        return await asyncio.gather(*tareas, return_exceptions=True)

    res = run(escenario())
    assert len(mundo.claude.calls) == 2
    assert sum(1 for r in res if isinstance(r, TraspasoError) and r.status == 409) == 1


def test_i3_mismo_id_en_vuelo_da_409_y_se_libera_al_terminar(mundo):
    mundo.claude = ClaudeConPuerta()
    mundo.svc = mundo.nuevo()
    p = mundo.crear()

    async def escenario():
        a = asyncio.create_task(mundo.svc.correr(p["id"], manual=True, ident="mano-0001"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        with pytest.raises(TraspasoError) as e:
            await mundo.svc.correr(p["id"], manual=True, ident="mano-0001")
        assert e.value.status == 409
        mundo.claude.puerta.set()
        return await a

    assert run(escenario())["estado"] == "ok"
    assert mundo.svc._en_vuelo == {} and mundo.svc._contador_vuelo == 0


def test_i3_la_reserva_se_libera_si_el_lanzamiento_revienta(mundo):
    mundo.claude.error = RuntimeError("boom")
    p = mundo.crear()
    assert run(mundo.svc.correr(p["id"], manual=True, ident="mano-0001"))["estado"] == "fallo"
    assert mundo.svc._en_vuelo == {} and mundo.svc._contador_vuelo == 0


def test_i2_pedido_en_el_tope_entra_en_nueva_tarea():
    from orquestador.terminales_acciones import NuevaTareaBody
    nombre = "N" * 60
    c = Cuando(tipo="dias", hora="09:00", dias=[0, 1, 2, 3, 4, 5, 6])
    mensaje = f"Tarea programada «{nombre}» ({pg.cuando_texto(c)}). " + "x" * pg.MAX_PEDIDO
    NuevaTareaBody(id="progaaaaaaaaaaaaaaaa", repo="/r", tarea=mensaje, nombre=nombre, rama="feature/a")
    with pytest.raises(Exception):
        pg.ProgramaBody(nombre="n", repo="/r", pedido="x" * (pg.MAX_PEDIDO + 1), agente="claude", cuando={"tipo": "diaria", "hora": "09:00"})


def test_i2_validation_error_deja_un_motivo_legible(mundo):
    from orquestador.terminales_acciones import NuevaTareaBody
    try:
        NuevaTareaBody(id="x")
    except Exception as exc:  # pydantic.ValidationError
        mundo.claude.error = exc
    p = mundo.crear()
    c = run(mundo.svc.correr(p["id"], manual=True))
    assert c["estado"] == "fallo" and c["motivo"] != "No pude abrirla" and "pedido" in c["motivo"].lower()


def test_m1_offset_fijo_como_en_produccion(monkeypatch):
    import time as t
    monkeypatch.setenv("TZ", "Europe/Madrid")
    t.tzset()
    try:
        desde = datetime(2026, 3, 28, 12, 0).astimezone()  # tzinfo de offset fijo (+01:00), no ZoneInfo
        assert not isinstance(desde.tzinfo, ZoneInfo)
        sig = proxima(diaria("09:00"), desde)
        assert sig.astimezone(UTC) == datetime(2026, 3, 29, 7, 0, tzinfo=UTC)  # ya en CEST (+02:00)
        assert proxima(diaria("02:30"), desde).astimezone(UTC) == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    finally:
        monkeypatch.undo()
        t.tzset()


def test_m2_un_salto_del_reloj_hacia_atras_no_vuelve_a_correr(mundo):
    p = mundo.crear()
    mundo.svc.habilitar(True)
    mundo.reloj.dt = mad(2026, 11, 17, 9, 0)
    run(mundo.svc.tick())
    assert len(mundo.claude.calls) == 1
    ultimo = mundo.svc._estado["ultimo_chequeo"]
    mundo.reloj.dt = mad(2026, 11, 17, 7, 0)  # el reloj retrocede
    run(mundo.svc.tick())
    assert mundo.svc._estado["ultimo_chequeo"] == ultimo
    mundo.reloj.dt = mad(2026, 11, 17, 9, 2)
    mundo.abiertas.clear()
    run(mundo.svc.tick())
    assert len(mundo.claude.calls) == 1
    assert p


def test_m3_correr_automatico_revalida_pausada_y_habilitado(mundo):
    p = mundo.crear()
    mundo.svc.habilitar(True)
    mundo.svc.pausar(p["id"], True)
    run(mundo.svc.correr(p["id"], manual=False))
    assert mundo.claude.calls == []
    mundo.svc.pausar(p["id"], False)
    mundo.svc.habilitar(False)
    run(mundo.svc.correr(p["id"], manual=False))
    assert mundo.claude.calls == []
    run(mundo.svc.correr(p["id"], manual=True))  # a mano sí se puede
    assert len(mundo.claude.calls) == 1


def test_m4_archivo_ilegible_se_copia_y_ultimo_chequeo_invalido_no_tira_el_arranque(mundo):
    d = mundo.tmp / "data"
    d.mkdir(parents=True)
    (d / "programadas.json").write_text("{no es json")
    nuevo = mundo.nuevo()
    assert nuevo.listar()["programas"] == []
    copias = list(d.glob("programadas.json.corrupto-*"))
    assert len(copias) == 1 and copias[0].read_text() == "{no es json"
    (d / "programadas.json").write_text(json.dumps({"habilitado": True, "ultimo_chequeo": "ayer", "programas": []}))
    assert mundo.nuevo()._estado["ultimo_chequeo"] == 0.0


def test_reloj_que_estuvo_adelantado_no_congela_las_tareas(mundo):
    mundo.crear()
    mundo.svc.habilitar(True)
    mundo.svc._estado["ultimo_chequeo"] = mad(2026, 12, 25, 0, 0).timestamp()  # reloj adelantado 5 semanas
    mundo.reloj.dt = mad(2026, 11, 17, 8, 0)
    run(mundo.svc.tick())
    assert mundo.svc._estado["ultimo_chequeo"] == mundo.reloj.dt.timestamp()
