"""Rutas /api/reunion/*, eventos SSE y cableado del copiloto de reuniones en create_app."""
import asyncio
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, make_snapshot
from orquestador import reunion as R
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.state import StateStore
from orquestador.uso_claude import project_key

DEV = "device-abc123"


class Prog:
    def __init__(self, delay, fn):
        self.delay, self.fn, self.cancelado = delay, fn, False

    def cancel(self):
        self.cancelado = True


class Runner:
    """`claude -p` falso: detecta una pregunta y resume con un título fijo."""

    def __init__(self):
        self.llamadas = []

    async def __call__(self, args, entrada, cwd, env):
        prompt = entrada.decode()
        self.llamadas.append((args, cwd))
        if prompt.startswith("Resumí"):
            res = {"titulo": "Plan de reembolsos", "resumen": ["se habló de reembolsos"], "pendientes": []}
        else:
            res = {"items": [{"tipo": "pregunta", "texto": "¿Hay reembolsos parciales?"}]}
        return 0, json.dumps({"result": json.dumps(res), "usage": {}}).encode(), b""


class Armado:
    def __init__(self, tmp_path, cfg, handoffs, opts=True, guardar_memoria=None):
        self.home = Path(os.environ["HOME"])
        self.repo = self.home / "development" / "repo-a"
        self.repo.mkdir(parents=True)
        (self.home / "development" / ".oculto").mkdir()
        self.progs: list = []
        self.runner = Runner()
        self.datos = tmp_path / "datos"
        self.datos.mkdir(exist_ok=True)
        self.enchufe = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
        digests = DigestService(cfg.projects_dir())
        hub = BoardHub(self.enchufe, digests)
        hub.self_pane_id = "w2:p9"
        self.carpeta = tmp_path / "cop"
        opciones = {"runner": self.runner, "programar": self._programar, "carpeta": self.carpeta,
                    "guardar_memoria": guardar_memoria} if opts else None
        self.app = create_app(cfg, b"secret", StateStore(self.datos), hub=hub, digests=digests,
                              dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads",
                              enchufe=self.enchufe, reunion_opts=opciones)
        self.abiertos: list = []
        self.mensajes: list = []

    def _programar(self, delay, fn):
        p = Prog(delay, fn)
        if delay != R.SIN_TEXTO_S:
            self.progs.append(p)
        return p

    def falsear_terminales(self):
        abiertos, mensajes = self.abiertos, self.mensajes

        async def abrir(ctx, item, **kw):
            abiertos.append((item, kw))
            return {"ok": True, "pane_id": "w1:p1", "pane_ids": ["w1:p1"],
                    "detalle": [{"pane_id": "w1:p1", "tipo": "claude", "mensaje": item["mensaje"], "pegado": True}]}

        async def execute(body):
            mensajes.append(body)
            return {"ok": True}

        self.app.state.tacciones.abrir_desde_pedido_pestana = abrir
        self.app.state.mensajes.execute = execute


@pytest.fixture
def armado(cfg, tmp_path, handoffs):
    return Armado(tmp_path, cfg, handoffs)


@pytest.fixture
def rc(armado):
    armado.falsear_terminales()
    with TestClient(armado.app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


async def _suscribir(hub):
    return hub.subscribe()


async def _vaciar(q):
    out = []
    while not q.empty():
        item = q.get_nowait()
        if isinstance(item, tuple) and item[0].startswith("reunion"):
            out.append(item)
    return out


async def _esperar_tareas(app):
    while app.state.reunion_tareas:
        await asyncio.gather(*list(app.state.reunion_tareas), return_exceptions=True)


async def _correr(fn):
    fn()


class Eventos:
    def __init__(self, c):
        self.c = c
        self.q = c.portal.call(_suscribir, c.app.state.hub)
        self.todos: list = []

    def tomar(self):
        self.c.portal.call(_esperar_tareas, self.c.app)
        self.todos += self.c.portal.call(_vaciar, self.q)
        return self.todos

    def de(self, nombre):
        self.tomar()
        return [d for e, d in self.todos if e == nombre]


def _empezar(c, repos=None, todos=False, **extra):
    r = c.get("/api/reunion/repos")
    assert r.status_code == 200
    ruta = [x["ruta"] for x in r.json()["repos"] if x["nombre"] == "repo-a"][0]
    return c.post("/api/reunion/empezar", json={"device": DEV, "repos": repos if repos is not None else [ruta],
                                                 "todos": todos, **extra})


def test_flujo_completo(rc, armado):
    ev = Eventos(rc)
    r = _empezar(rc)
    assert r.status_code == 200
    rid = r.json()["reunion"]
    assert r.json()["estado"] == "escuchando"
    estados = ev.de("reunion-estado")
    assert [e["copiloto"] for e in estados] == ["abriendo", "listo"]
    assert estados[0]["solo_a_mano"] is False and estados[0]["tope_detecciones"] == 180
    item, kw = armado.abiertos[0]
    assert kw["permiso"] == "copiloto" and item["carpeta"] == str(armado.carpeta)
    assert armado.mensajes[0].origen == "copiloto" and armado.mensajes[0].pane_id == "w1:p1"
    assert json.loads((armado.carpeta / ".claude" / "settings.json").read_text())["permissions"][
        "additionalDirectories"] == [str(armado.repo)]

    r = rc.post("/api/reunion/texto", json={"reunion": rid, "device": DEV, "texto": "¿Tenemos reembolsos parciales?"})
    assert r.status_code == 202
    assert [p.delay for p in armado.progs] == [20]
    rc.portal.call(_correr, armado.progs[0].fn)
    lineas = ev.de("reunion-linea")
    assert lineas == [{"reunion": rid, "id": "l1", "texto": "¿Hay reembolsos parciales?", "tipo": "pregunta"}]
    assert armado.runner.llamadas[0][1] == str(armado.datos / "reunion-claude")

    r = rc.post("/api/reunion/tocar", json={"reunion": rid, "linea": "l1"})
    assert r.status_code == 202 and r.json() == {"estado": "buscando"}
    pregunta = armado.mensajes[-1]
    assert pregunta.origen == "copiloto" and "l1" in pregunta.texto

    bloque = 'listo\n```copiloto\n{"linea": "l1", "texto": "Sí, en pagos.py", "archivos": ["pagos.py"]}\n```'
    for cb in rc.app.state.estados.al_stop:
        rc.portal.call(_correr, lambda: cb("w1:p1", bloque))
    resp = ev.de("reunion-respuesta")
    assert resp[-1] == {"reunion": rid, "linea": "l1", "estado": "lista", "texto": "Sí, en pagos.py",
                        "archivos": ["pagos.py"]}

    snap = rc.get("/api/reunion/estado")
    assert snap.headers["cache-control"] == "no-store"
    assert snap.json()["reunion"] == rid and snap.json()["solo_a_mano"] is False
    assert snap.json()["lineas"][0]["respuesta"]["estado"] == "lista"

    assert rc.post("/api/reunion/terminar", json={"reunion": rid}).status_code == 202
    guardada = ev.de("reunion-guardada")
    assert len(guardada) == 1 and guardada[0]["reunion"] == rid
    bid = guardada[0]["biblioteca"]
    lista = rc.get("/api/biblioteca", params={"tipo": "reunion"}).json()
    assert bid in [x["id"] for x in lista["items"]]
    charla = rc.get(f"/api/biblioteca/{bid}/charla")
    assert charla.status_code == 200 and charla.headers["cache-control"] == "no-store"
    assert "reembolsos parciales" in charla.json()["charla"]
    assert rc.get("/api/reunion/estado").json() is None
    assert ("cerrar", "w1:t1") in armado.enchufe.calls_of("cerrar")


def test_empezar_con_repo_fuera_de_la_lista_es_422(rc, tmp_path):
    afuera = tmp_path / "afuera"
    afuera.mkdir()
    r = rc.post("/api/reunion/empezar", json={"device": DEV, "repos": [str(afuera)], "todos": False})
    assert r.status_code == 422
    assert rc.get("/api/reunion/estado").json() is None


def test_repos_lista_development_sin_ocultas(rc, armado):
    r = rc.get("/api/reunion/repos").json()
    assert r["todos"] == str(armado.home / "development")
    assert [x["nombre"] for x in r["repos"]] == ["repo-a"]


def test_repos_no_ofrece_el_repo_de_colmena(rc, armado, cfg):
    colmena = armado.home / "development" / "colmena"
    colmena.mkdir()
    cfg.self_repo = str(colmena)
    nombres = [x["nombre"] for x in rc.get("/api/reunion/repos").json()["repos"]]
    assert "colmena" not in nombres and "repo-a" in nombres
    r = rc.post("/api/reunion/empezar", json={"device": DEV, "repos": [str(colmena)], "todos": False})
    assert r.status_code == 422


def test_segunda_reunion_es_409(rc):
    assert _empezar(rc).status_code == 200
    assert _empezar(rc).status_code == 409


def test_texto_sin_reunion_o_de_otro_device_es_409(rc):
    r = rc.post("/api/reunion/texto", json={"reunion": "r1-1", "device": DEV, "texto": "hola"})
    assert r.status_code == 409
    rid = _empezar(rc).json()["reunion"]
    r = rc.post("/api/reunion/texto", json={"reunion": rid, "device": "device-otro99", "texto": "hola"})
    assert r.status_code == 409


@pytest.mark.parametrize("body", [{"texto": ""}, {"texto": "x" * 2001}])
def test_texto_valida_largo(rc, body):
    rid = _empezar(rc).json()["reunion"]
    assert rc.post("/api/reunion/texto", json={"reunion": rid, "device": DEV, **body}).status_code == 422


def test_tocar_valida_la_linea(rc):
    rid = _empezar(rc).json()["reunion"]
    assert rc.post("/api/reunion/tocar", json={"reunion": rid, "linea": "x1"}).status_code == 422
    assert rc.post("/api/reunion/tocar", json={"reunion": rid, "linea": "l99"}).status_code == 404


def test_pausar_seguir_y_preguntar_ultimo(rc, armado):
    ev = Eventos(rc)
    rid = _empezar(rc).json()["reunion"]
    assert rc.post("/api/reunion/pausar", json={"reunion": rid}).status_code == 202
    assert rc.get("/api/reunion/estado").json()["estado"] == "pausada"
    assert rc.post("/api/reunion/seguir", json={"reunion": rid}).status_code == 202
    rc.post("/api/reunion/texto", json={"reunion": rid, "device": DEV, "texto": "algo"})
    ev.tomar()
    assert rc.post("/api/reunion/preguntar-ultimo", json={"reunion": rid}).status_code == 202
    assert ev.de("reunion-linea")[-1]["tipo"] == "manual"


def test_estado_sin_reunion_es_null(rc):
    r = rc.get("/api/reunion/estado")
    assert r.status_code == 200 and r.json() is None and r.headers["cache-control"] == "no-store"


def test_charla_de_item_que_no_es_reunion_es_404(rc):
    assert rc.get("/api/biblioteca/abc/charla").status_code == 404


def test_rutas_piden_sesion(armado):
    with TestClient(armado.app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.get("/api/reunion/estado").status_code == 401
        assert c.get("/api/reunion/repos").status_code == 401


def test_pc_desconectada_pasa_a_sin_pc(armado):
    armado.falsear_terminales()
    app = armado.app
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        cookie = "; ".join(f"{k}={v}" for k, v in c.cookies.items())
    visto = {}

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
                llego.set()

        t = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(llego.wait(), 5)
        await app.state.reunion.empezar(DEV, [], True)
        await _esperar_tareas(app)
        visto["dentro"] = app.state.reunion.snapshot()["estado"]
        desconectar.set()
        t.cancel()
        try:
            await t
        except BaseException:
            pass
        visto["fuera"] = app.state.reunion.snapshot()["estado"]
        visto["abandono"] = [p.delay for p in armado.progs if not p.cancelado]

    asyncio.run(correr())
    assert visto == {"dentro": "escuchando", "fuera": "sin_pc", "abandono": [1800]}


def test_arranque_recupera_diario(cfg, tmp_path, handoffs):
    reuniones = tmp_path / "datos" / "reuniones"
    reuniones.mkdir(parents=True)
    (reuniones / "x.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"e": "inicio", "device": DEV, "repos": [], "todos": True, "ts": 1000.0},
        {"e": "texto", "ts": 1001.0, "texto": "lo que se dijo"}]) + "\n", encoding="utf-8")
    a = Armado(tmp_path, cfg, handoffs)
    with TestClient(a.app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        items = c.get("/api/biblioteca", params={"tipo": "reunion"}).json()["items"]
        assert len(items) == 1
        raw = json.loads(items[0]["reunion_raw"])
        assert raw["motivo"] == "interrumpida"
        assert "lo que se dijo" in c.get(f"/api/biblioteca/{items[0]['id']}/charla").json()["charla"]
    assert not (reuniones / "x.jsonl").exists()


def test_reunion_claude_excluida_de_claude_uso(armado):
    excluir = armado.app.state.uso_claude.excluir
    assert project_key(armado.datos / "reunion-claude") in excluir
    assert project_key(armado.carpeta) in excluir
    assert project_key(armado.carpeta) in armado.app.state.tacciones.sesiones_viejas.excluir_carpetas


# ---- Mostrame

PNG_CHICO = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x04\x00\x00\x00\x03\x08\x02\x00\x00\x00"
             b"\x00\x00\x00\x00")


def _cuerpo_mostrar(rid, **extra):
    import base64
    body = {"reunion": rid, "device": DEV, "pregunta": "¿cómo exporto esto?",
            "foto": {"foto": 7, "ventana": {"titulo": "Pedidos", "proceso": "chrome.exe"},
                     "controles": [{"n": 1, "tipo": "boton", "nombre": "Guardar"}]},
            "imagen": {"tipo": "png", "ancho": 4, "alto": 3, "b64": base64.b64encode(PNG_CHICO).decode()}}
    body.update(extra)
    return body


def test_mostrar_flujo(rc, armado):
    rid = _empezar(rc).json()["reunion"]
    r = rc.post("/api/reunion/mostrar", json=_cuerpo_mostrar(rid))
    assert r.status_code == 202 and r.json() == {"linea": "l1", "estado": "buscando"}
    capturas = list((armado.carpeta / "capturas").glob("cap-*.png"))
    assert len(capturas) == 1 and (capturas[0].stat().st_mode & 0o777) == 0o600
    assert capturas[0].read_bytes() == PNG_CHICO
    assert rc.app.state.nudo._fotos["w1:p1"][0] == 7
    assert "capturas" in armado.mensajes[-1].texto


def test_mostrar_cuerpo_grande_es_413(rc):
    _empezar(rc)
    r = rc.post("/api/reunion/mostrar", content=b"x", headers={"Content-Length": str(8 * 1024 * 1024),
                                                               "Content-Type": "application/json"})
    assert r.status_code == 413


@pytest.mark.parametrize("cambio", [
    {"imagen": {"tipo": "png", "ancho": 4, "alto": 3, "b64": "AAAA"}},
    {"imagen": {"tipo": "gif", "ancho": 4, "alto": 3, "b64": "AAAA"}},
    {"foto": {"foto": -1, "ventana": {}, "controles": []}},
])
def test_mostrar_imagen_invalida_es_422(rc, cambio):
    rid = _empezar(rc).json()["reunion"]
    r = rc.post("/api/reunion/mostrar", json=_cuerpo_mostrar(rid, **cambio))
    assert r.status_code == 422


def test_mostrar_otra_reunion_es_409(rc):
    _empezar(rc)
    assert rc.post("/api/reunion/mostrar", json=_cuerpo_mostrar("r0-9")).status_code == 409


def test_terminar_borra_capturas(rc, armado):
    ev = Eventos(rc)
    rid = _empezar(rc).json()["reunion"]
    rc.post("/api/reunion/mostrar", json=_cuerpo_mostrar(rid))
    assert (armado.carpeta / "capturas").is_dir()
    rc.post("/api/reunion/terminar", json={"reunion": rid})
    ev.tomar()
    assert not (armado.carpeta / "capturas").exists()


def test_arranque_borra_capturas(cfg, tmp_path, handoffs):
    a = Armado(tmp_path, cfg, handoffs)
    (a.carpeta / "capturas").mkdir(parents=True)
    (a.carpeta / "capturas" / "cap-x.png").write_bytes(b"x")
    a.falsear_terminales()
    with TestClient(a.app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)):
        pass
    assert not (a.carpeta / "capturas" / "cap-x.png").exists()


def _con_linea_detectada(rc, armado, ev):
    rid = _empezar(rc).json()["reunion"]
    rc.post("/api/reunion/texto", json={"reunion": rid, "device": DEV, "texto": "¿Tenemos reembolsos parciales?"})
    rc.portal.call(_correr, armado.progs[0].fn)
    assert ev.de("reunion-linea")[-1]["id"] == "l1"
    return rid


def test_descartar_linea_por_api(rc, armado):
    ev = Eventos(rc)
    rid = _con_linea_detectada(rc, armado, ev)
    r = rc.post("/api/reunion/descartar", json={"reunion": rid, "linea": "l1"})
    assert r.status_code == 202 and r.json() == {"estado": "descartada"}
    assert ev.de("reunion-descartada") == [{"reunion": rid, "linea": "l1"}]
    assert rc.get("/api/reunion/estado").json()["lineas"] == []
    assert rc.post("/api/reunion/descartar", json={"reunion": "otra", "linea": "l1"}).status_code == 409
    assert rc.post("/api/reunion/descartar", json={"reunion": rid, "linea": "l99"}).status_code == 404
    assert rc.post("/api/reunion/descartar", json={"reunion": rid, "linea": "x1"}).status_code == 422


def test_descartar_linea_buscando_es_409_por_api(rc, armado):
    ev = Eventos(rc)
    rid = _con_linea_detectada(rc, armado, ev)
    assert rc.post("/api/reunion/tocar", json={"reunion": rid, "linea": "l1"}).status_code == 202
    r = rc.post("/api/reunion/descartar", json={"reunion": rid, "linea": "l1"})
    assert r.status_code == 409 and "buscando" in r.json()["detail"]


def test_anotar_linea_crea_la_nota_una_sola_vez(rc, armado):
    ev = Eventos(rc)
    rid = _con_linea_detectada(rc, armado, ev)
    r = rc.post("/api/reunion/anotar", json={"reunion": rid, "linea": "l1"})
    assert r.status_code == 202
    nota_id = r.json()["nota"]
    assert ev.de("reunion-anotada") == [{"reunion": rid, "linea": "l1", "nota": nota_id}]
    assert rc.post("/api/reunion/anotar", json={"reunion": rid, "linea": "l1"}).json() == {"nota": nota_id}
    notas = [n for n in rc.app.state.notas.listar() if n["id"] == nota_id]
    assert len(notas) == 1 and notas[0]["tipo"] == "apunte" and notas[0]["texto"] == "¿Hay reembolsos parciales?"
    assert rc.get("/api/reunion/estado").json()["lineas"][0]["nota"] == nota_id


def test_memoria_endpoint_guarda_una_vez_y_el_estado_lo_refleja(cfg, tmp_path, handoffs):
    guardados = []
    arm = Armado(tmp_path, cfg, handoffs, guardar_memoria=lambda t, c: guardados.append((t, c)))
    arm.falsear_terminales()
    with TestClient(arm.app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as rc:
        assert rc.post("/api/login", json={"pin": PIN}).status_code == 200
        ev = Eventos(rc)
        rid = _con_linea_detectada(rc, arm, ev)
        assert rc.post("/api/reunion/memoria", json={"reunion": rid, "linea": "l1"}).status_code == 409
        rc.post("/api/reunion/anotar", json={"reunion": rid, "linea": "l1"})
        r = rc.post("/api/reunion/memoria", json={"reunion": rid, "linea": "l1"})
        assert r.status_code == 202 and r.json() == {"memoria": True}
        rc.post("/api/reunion/memoria", json={"reunion": rid, "linea": "l1"})
        assert len(guardados) == 1
        assert ev.de("reunion-memoria") == [{"reunion": rid, "linea": "l1"}]
        est = rc.get("/api/reunion/estado").json()
        assert est["memoria_trabajo"] is True and est["lineas"][0]["memoria"] is True


def test_memoria_endpoint_sin_configurar_es_503(rc, armado):
    ev = Eventos(rc)
    rid = _con_linea_detectada(rc, armado, ev)
    rc.post("/api/reunion/anotar", json={"reunion": rid, "linea": "l1"})
    assert rc.get("/api/reunion/estado").json()["memoria_trabajo"] is False
    assert rc.post("/api/reunion/memoria", json={"reunion": rid, "linea": "l1"}).status_code == 503


def test_guardador_memoria_trabajo_valida_la_config(cfg):
    from orquestador.app import guardador_memoria_trabajo
    cfg.docker_bin = "/usr/bin/docker"
    cfg.guardian = {"memoria_contenedor": "engram", "memoria_trabajo": "trabajo"}
    assert callable(guardador_memoria_trabajo(cfg))
    for malo in ({"memoria_contenedor": "engram"}, {"memoria_contenedor": "engram", "memoria_trabajo": "Mal Nombre"},
                 {"memoria_contenedor": "-x", "memoria_trabajo": "trabajo"}, {"memoria_trabajo": "trabajo"}):
        cfg.guardian = malo
        assert guardador_memoria_trabajo(cfg) is None


def test_api_empezar_con_tema(rc, armado):
    assert _empezar(rc, tema="Plux en ps9").status_code == 200
    assert "La reunión trata de: Plux en ps9." in armado.abiertos[0][0]["mensaje"]


def test_api_tema_largo_422(rc, armado):
    assert _empezar(rc, tema="x" * 201).status_code == 422
    assert armado.abiertos == []
    assert _empezar(rc).status_code == 200


def test_api_tema_solo_espacios(rc, armado):
    assert _empezar(rc, tema="   \n ").status_code == 200
    assert "trata de" not in armado.abiertos[0][0]["mensaje"]
