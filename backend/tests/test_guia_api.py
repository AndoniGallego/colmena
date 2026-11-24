"""Rutas /api/guia/*, SSE `guia` y cableado de la guía por atajo en create_app."""
import asyncio
import base64
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, make_snapshot
from orquestador import mostrar as mostrar_mod
from orquestador.app import carpetas_internas, create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.guia import TOPE
from orquestador.nudo import crear_manejador
from orquestador.state import StateStore
from orquestador.traspaso import TraspasoError
from orquestador.uso_claude import project_key

DEV = "device-abc123"
OTRA = "device-otra999"
PANE_GUIA = "w9:p1"

PNG_CHICO = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x04\x00\x00\x00\x03\x08\x02\x00\x00\x00"
             b"\x00\x00\x00\x00")
IMAGEN = {"tipo": "png", "ancho": 4, "alto": 3, "b64": base64.b64encode(PNG_CHICO).decode()}
FOTO = {"foto": 7, "ventana": {"titulo": "Planilla", "proceso": "excel.exe"},
        "controles": [{"n": 1, "tipo": "boton", "nombre": "Archivo"}]}


def _pedir(device=DEV, pregunta="¿cómo exporto a PDF?", **extra):
    body = {"device": device, "pregunta": pregunta, "foto": FOTO, "imagen": IMAGEN}
    body.update(extra)
    return body


def _siguiente(device=DEV, **extra):
    body = {"device": device, "foto": FOTO, "imagen": IMAGEN}
    body.update(extra)
    return body


class Prog:
    def __init__(self, delay, fn):
        self.delay, self.fn, self.cancelado = delay, fn, False

    def cancel(self):
        self.cancelado = True


class Runner:
    async def __call__(self, args, entrada, cwd, env):
        return 0, b'{"result": "{\\"items\\": []}", "usage": {}}', b""


class Armado:
    def __init__(self, tmp_path, cfg, handoffs, snapshot=None):
        self.home = Path(os.environ["HOME"])
        (self.home / "development" / "repo-a").mkdir(parents=True, exist_ok=True)
        self.datos = tmp_path / "datos"
        self.datos.mkdir(exist_ok=True)
        self.progs: list = []
        self.enchufe = FakeTerminales.desde_snapshot(snapshot or make_snapshot(), poll=0.01)
        digests = DigestService(cfg.projects_dir())
        hub = BoardHub(self.enchufe, digests)
        hub.self_pane_id = "w2:p9"
        self.carpeta_cop = tmp_path / "cop"
        self.carpeta = tmp_path / "guia"
        self.projects = cfg.projects_dir()
        opciones = {"runner": Runner(), "programar": self._programar, "carpeta": self.carpeta_cop,
                    "carpeta_guia": self.carpeta}
        self.app = create_app(cfg, b"secret", StateStore(self.datos), hub=hub, digests=digests,
                              dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads",
                              enchufe=self.enchufe, reunion_opts=opciones)
        self.abiertos: list = []
        self.mensajes: list = []

    def _programar(self, delay, fn):
        p = Prog(delay, fn)
        self.progs.append(p)
        return p

    def falsear_terminales(self, falla=None):
        abiertos, mensajes = self.abiertos, self.mensajes

        async def abrir(ctx, item, **kw):
            if falla is not None and kw.get("permiso") == "guia":
                raise falla
            abiertos.append((item, kw))
            pane = PANE_GUIA if kw.get("permiso") == "guia" else "w1:p1"
            return {"ok": True, "pane_id": pane, "pane_ids": [pane],
                    "detalle": [{"pane_id": pane, "tipo": "claude", "mensaje": item["mensaje"], "pegado": True}]}

        async def execute(body):
            mensajes.append(body)
            return {"ok": True}

        self.app.state.tacciones.abrir_desde_pedido_pestana = abrir
        self.app.state.mensajes.execute = execute


@pytest.fixture
def armado(cfg, tmp_path, handoffs):
    return Armado(tmp_path, cfg, handoffs)


def _cliente(app):
    return TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000))


@pytest.fixture
def rc(armado):
    armado.falsear_terminales()
    with _cliente(armado.app) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


async def _esperar_tareas(app):
    while app.state.reunion_tareas:
        await asyncio.gather(*list(app.state.reunion_tareas), return_exceptions=True)


class Pc:
    """La PC conectada (como lo haría /api/events?pc=1): recibe la orden del nudo y los eventos de la guía."""

    def __init__(self, c, device=DEV):
        self.c = c
        app = c.app

        async def conectar():
            q = app.state.hub.subscribe()
            app.state.nudo.pc_conectada(device, q)
            app.state.guia.pc_conectada(device, q)
            return q

        self.q = c.portal.call(conectar)
        self.todos: list = []

    def tomar(self):
        async def vaciar():
            await _esperar_tareas(self.c.app)
            out = []
            while not self.q.empty():
                item = self.q.get_nowait()
                if isinstance(item, tuple):
                    out.append(item)
            return out

        self.todos += self.c.portal.call(vaciar)
        return self.todos

    def de(self, nombre):
        self.tomar()
        return [d for e, d in self.todos if e == nombre]


def test_pedir_flujo(armado, tmp_path):
    """La PC entra por el SSE real (pc=1): el pedido arranca el ayudante y el evento `guia` le llega a ella."""
    armado.falsear_terminales()
    app = armado.app
    with _cliente(app) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        cookies = dict(c.cookies.items())
    cookie = "; ".join(f"{k}={v}" for k, v in cookies.items())
    visto: dict = {"cuerpos": []}

    async def correr():
        headers = [(b"host", b"testserver"), (b"origin", b"http://testserver"), (b"cookie", cookie.encode())]
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
                 "scheme": "https", "path": "/api/events", "raw_path": b"/api/events",
                 "query_string": f"cid={DEV}&pc=1".encode(), "headers": headers,
                 "client": ("127.0.0.1", 5000), "server": ("testserver", 443)}
        llego, desconectar = asyncio.Event(), asyncio.Event()

        async def receive():
            await desconectar.wait()
            return {"type": "http.disconnect"}

        async def send(msg):
            if msg["type"] == "http.response.body" and msg.get("body"):
                visto["cuerpos"].append(msg["body"].decode())
                llego.set()

        t = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(llego.wait(), 5)
        transporte = httpx.ASGITransport(app=app, client=("127.0.0.1", 5000))
        async with httpx.AsyncClient(transport=transporte, base_url="https://testserver",
                                     headers=ORIGIN, cookies=cookies) as h:
            r = await h.post("/api/guia/pedir", json=_pedir())
            visto["status"], visto["json"] = r.status_code, r.json()
        await _esperar_tareas(app)
        for _ in range(3):
            await asyncio.sleep(0)
        visto["snap"] = app.state.guia.snapshot()
        visto["capturas"] = list((armado.carpeta / "capturas").glob("cap-*.png"))
        visto["modo"] = [c.stat().st_mode & 0o777 for c in visto["capturas"]]
        visto["datos"] = [c.read_bytes() for c in visto["capturas"]]
        desconectar.set()
        t.cancel()
        try:
            await t
        except BaseException:
            pass
        visto["fuera"] = app.state.guia.snapshot()

    asyncio.run(correr())
    assert visto["status"] == 202 and visto["json"] == {"guia": 1, "estado": "preparando"}
    assert len(visto["capturas"]) == 1 and visto["modo"] == [0o600] and visto["datos"] == [PNG_CHICO]
    item, kw = armado.abiertos[0]
    assert kw["permiso"] == "guia" and item["carpeta"] == str(armado.carpeta)
    assert armado.mensajes[0].origen == "guia" and armado.mensajes[0].pane_id == PANE_GUIA
    assert visto["snap"]["pane"] == PANE_GUIA and visto["snap"]["ayudante"] == "listo"
    sse = "".join(visto["cuerpos"])
    assert "event: guia" in sse and '"estado": "mirando"' in sse
    # La PC se fue (SSE cerrado): la guía termina y no quedan capturas.
    assert visto["fuera"]["guia"] is None
    assert not list((armado.carpeta / "capturas").glob("cap-*"))


def test_pedir_desde_otro_device_es_409_otra_pc(rc):
    Pc(rc)
    r = rc.post("/api/guia/pedir", json=_pedir(device=OTRA))
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "otra_pc"
    assert r.json()["detail"]["mensaje"] == "La guía está en otra PC"


def test_pedir_con_reunion_en_curso_es_409_reunion(rc):
    Pc(rc)
    assert rc.post("/api/reunion/empezar", json={"device": DEV, "repos": [], "todos": True}).status_code == 200
    r = rc.post("/api/guia/pedir", json=_pedir())
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "reunion"


@pytest.mark.parametrize("ruta", ["/api/guia/pedir", "/api/guia/siguiente"])
def test_cuerpo_grande_es_413(rc, ruta):
    r = rc.post(ruta, content=b"x", headers={"Content-Length": str(mostrar_mod.CUERPO_MAX + 1),
                                             "Content-Type": "application/json"})
    assert r.status_code == 413


def test_cuerpo_de_una_captura_real_no_es_413(rc):
    Pc(rc)
    grande = {"tipo": "png", "ancho": 4, "alto": 3, "b64": base64.b64encode(b"x" * 200_000).decode()}
    r = rc.post("/api/guia/pedir", json=_pedir(imagen=grande))
    assert r.status_code == 422


@pytest.mark.parametrize("cambio", [
    {"imagen": {"tipo": "png", "ancho": 4, "alto": 3, "b64": "AAAA"}},
    {"imagen": {"tipo": "gif", "ancho": 4, "alto": 3, "b64": "AAAA"}},
    {"foto": {"foto": -1, "ventana": {}, "controles": []}},
])
def test_imagen_invalida_es_422_invalida(rc, cambio):
    Pc(rc)
    r = rc.post("/api/guia/pedir", json=_pedir(**cambio))
    assert r.status_code == 422
    assert r.json()["detail"] == {"codigo": "invalida", "mensaje": "La captura no es válida."}


@pytest.mark.parametrize("pregunta", ["", "   "])
def test_pregunta_vacia_es_422_sin_pregunta(rc, pregunta):
    Pc(rc)
    r = rc.post("/api/guia/pedir", json=_pedir(pregunta=pregunta))
    assert r.status_code == 422
    assert r.json()["detail"] == {"codigo": "sin_pregunta", "mensaje": "Escribí qué querés hacer"}


def test_pregunta_de_mas_de_300_es_422(rc):
    Pc(rc)
    assert rc.post("/api/guia/pedir", json=_pedir(pregunta="a" * 300)).status_code == 202
    assert rc.post("/api/guia/pedir", json=_pedir(pregunta="a" * 301)).status_code == 422


def test_campo_de_mas_es_422(rc):
    Pc(rc)
    assert rc.post("/api/guia/pedir", json=_pedir(otro=1)).status_code == 422
    assert rc.post("/api/guia/salir", json={"device": DEV, "otro": 1}).status_code == 422


def test_siguiente_sin_guia_es_409_sin_guia(rc):
    Pc(rc)
    r = rc.post("/api/guia/siguiente", json=_siguiente())
    assert r.status_code == 409
    assert r.json()["detail"] == {"codigo": "sin_guia", "mensaje": "No hay una guía en curso"}


def test_salir_sin_guia_es_ok(rc):
    r = rc.post("/api/guia/salir", json={"device": DEV})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_siguiente_flujo_y_salir_borra_capturas(rc, armado):
    pc = Pc(rc)
    assert rc.post("/api/guia/pedir", json=_pedir()).status_code == 202
    pc.tomar()
    bloque = 'listo\n```guia\n{"guia": "1.1", "paso": 1, "total": 3, "texto": "Tocá Archivo", "fin": false}\n```'
    for cb in rc.app.state.estados.al_stop:
        rc.portal.call(lambda: _llamar(cb, PANE_GUIA, bloque))
    assert pc.de("guia")[-1] == {"guia": 1, "estado": "paso", "paso": 1, "total": 3, "texto": "Tocá Archivo"}
    r = rc.post("/api/guia/siguiente", json=_siguiente())
    assert r.status_code == 202 and r.json() == {"guia": 1, "estado": "mirando"}
    assert armado.mensajes[-1].origen == "guia" and "Ando hizo el paso 1" in armado.mensajes[-1].texto
    r = rc.post("/api/guia/siguiente", json=_siguiente())
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "mirando"
    assert (armado.carpeta / "capturas").is_dir()
    assert rc.post("/api/guia/salir", json={"device": DEV}).json() == {"ok": True}
    assert not (armado.carpeta / "capturas").exists()


async def _llamar(fn, *args):
    fn(*args)


def test_error_al_guardar_la_captura_no_tumba_la_ruta(rc):
    Pc(rc)

    async def falla(*a):
        raise OSError("disco lleno")

    rc.app.state.puente_guia.guardar_captura = falla
    r = rc.post("/api/guia/pedir", json=_pedir())
    assert r.status_code == 500 and r.json()["detail"]["codigo"] == "fallo"
    assert rc.app.state.guia.snapshot()["guia"] is None


def test_tope_por_hora_llega_como_error_de_la_guia(armado):
    armado.falsear_terminales(falla=TraspasoError(429, "tope"))
    with _cliente(armado.app) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        pc = Pc(c)
        r = c.post("/api/guia/pedir", json=_pedir())
        assert r.status_code == 202
        errores = [e for e in pc.de("guia") if e["estado"] == "error"]
        assert errores and errores[-1]["texto"] == TOPE


def test_empezar_reunion_termina_la_guia(rc):
    pc = Pc(rc)
    assert rc.post("/api/guia/pedir", json=_pedir()).status_code == 202
    pc.tomar()
    assert rc.app.state.guia.snapshot()["ayudante"] == "listo"
    assert rc.post("/api/reunion/empezar", json={"device": DEV, "repos": [], "todos": True}).status_code == 200
    pc.tomar()
    snap = rc.app.state.guia.snapshot()
    assert snap["guia"] is None and snap["ayudante"] == "apagado"


def test_orden_del_pane_guia_lleva_guia_true(rc):
    pc = Pc(rc)
    assert rc.post("/api/guia/pedir", json=_pedir()).status_code == 202
    pc.tomar()
    app = rc.app
    manejar = crear_manejador(app.state.nudo, lambda: None)

    async def pedir_orden(sesion):
        t = asyncio.ensure_future(manejar({"op": "senalar", "sesion": sesion, "args": {"n": 1, "texto": "Acá"}}))
        for _ in range(5):
            await asyncio.sleep(0)
        t.cancel()
        try:
            await t
        except BaseException:
            pass

    rc.portal.call(pedir_orden, PANE_GUIA)
    ordenes = [o for o in pc.de("nudo") if o.get("op") == "senalar"]
    assert ordenes and ordenes[-1]["guia"] is True
    assert app.state.nudo.es_guia(PANE_GUIA) and not app.state.nudo.es_guia("w1:p1")


def test_arranque_borra_capturas_y_transcripts_de_la_guia(cfg, tmp_path, handoffs):
    a = Armado(tmp_path, cfg, handoffs)
    (a.carpeta / "capturas").mkdir(parents=True)
    (a.carpeta / "capturas" / "cap-x.png").write_bytes(b"x")
    suyo = a.projects / project_key(a.carpeta)
    suyo.mkdir(parents=True)
    (suyo / "s.jsonl").write_text("{}\n")
    a.falsear_terminales()
    with _cliente(a.app):
        pass
    assert not (a.carpeta / "capturas" / "cap-x.png").exists()
    assert not (suyo / "s.jsonl").exists()


def test_arranque_cierra_los_panes_huerfanos_de_la_guia(cfg, tmp_path, handoffs):
    snap = make_snapshot()
    snap["agents"][0]["cwd"] = str(tmp_path / "guia")
    a = Armado(tmp_path, cfg, handoffs, snapshot=snap)
    a.falsear_terminales()
    with _cliente(a.app) as c:
        c.portal.call(_esperar_tareas, c.app)
    assert a.enchufe.calls_of("cerrar"), "el pane huérfano de la guía debería cerrarse"


def test_arranque_no_cierra_panes_de_otras_carpetas(cfg, tmp_path, handoffs):
    a = Armado(tmp_path, cfg, handoffs)
    a.falsear_terminales()
    with _cliente(a.app) as c:
        c.portal.call(_esperar_tareas, c.app)
    assert not a.enchufe.calls_of("cerrar")


def test_carpetas_internas_incluye_la_guia(armado, tmp_path):
    datos, cop, guia = tmp_path / "d", tmp_path / "c", tmp_path / "g"
    claves = carpetas_internas(datos, cop, guia)
    assert project_key(guia) in claves and project_key(cop) in claves
    assert project_key(datos / "reunion-claude") in claves
    assert project_key(armado.carpeta) in armado.app.state.uso_claude.excluir
    assert project_key(armado.carpeta) in armado.app.state.tacciones.sesiones_viejas.excluir_carpetas


def test_los_defaults_de_las_carpetas_internas_no_son_las_reales(tmp_path_factory):
    """Ningún test puede borrar capturas reales: los defaults que usa el arranque apuntan al tmp de pytest."""
    import orquestador.app as app_mod

    base = str(tmp_path_factory.getbasetemp())
    assert str(app_mod.CARPETA_GUIA).startswith(base)
    assert str(app_mod.CARPETA_COPILOTO).startswith(base)


def test_arranque_con_defaults_limpia_solo_la_carpeta_del_tmp(cfg, tmp_path, handoffs):
    import orquestador.app as app_mod

    base = str(tmp_path.parent.parent)
    assert str(app_mod.CARPETA_GUIA).startswith(base)  # nunca se planta nada fuera del tmp de pytest
    enchufe = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    digests = DigestService(cfg.projects_dir())
    (tmp_path / "d").mkdir()
    app = create_app(cfg, b"secret", StateStore(tmp_path / "d"), hub=BoardHub(enchufe, digests), digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads",
                     enchufe=enchufe)
    plantadas = [Path(app_mod.CARPETA_GUIA) / "capturas" / "cap-x.png",
                 Path(app_mod.CARPETA_COPILOTO) / "capturas" / "cap-x.png"]
    for p in plantadas:
        p.parent.mkdir(parents=True)
        p.write_bytes(b"x")
    with _cliente(app):
        pass
    assert not any(p.exists() for p in plantadas)


def test_salir_de_la_guia_limpia_el_dibujo_del_nudo(rc):
    pc = Pc(rc)
    assert rc.post("/api/guia/pedir", json=_pedir()).status_code == 202
    pc.tomar()
    app = rc.app
    app.state.nudo._poner_dueno(PANE_GUIA, "Guía")
    antes = len([o for o in pc.de("nudo") if o.get("op") == "limpiar"])
    assert rc.post("/api/guia/salir", json={"device": DEV}).status_code == 200
    pc.tomar()
    assert app.state.nudo.dueno() is None
    assert len([o for o in pc.de("nudo") if o.get("op") == "limpiar"]) == antes + 1
