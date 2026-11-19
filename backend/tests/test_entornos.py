import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN
from orquestador import entornos as entornos_mod
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.config import Config
from orquestador.digest import DigestService
from orquestador.entornos import (
    armar_entornos,
    carpeta_corta,
    correr_docker,
    elegir_principal,
    estado_servicio,
    listar,
    parsear_labels,
    parsear_puertos,
)
from orquestador.state import StateStore

FIXTURE = (Path(__file__).parent / "fixtures" / "docker_ps.jsonl").read_text(encoding="utf-8")
FIXTURE_A = (Path(__file__).parent / "fixtures" / "docker_ps_a.jsonl").read_text(encoding="utf-8")
HOME = "/home/usuario"
HOME_AISLADO = str(Path.home())


def p(puerto, servicio, cont, abrible=True):
    return {"puerto": puerto, "servicio": servicio, "puerto_contenedor": cont, "abrible": abrible}


def svc(servicio, estado="corriendo", codigo=None, hace_s=None):
    return {"servicio": servicio, "estado": estado, "codigo": codigo, "hace_s": hace_s}


def ent(nombre, carpeta, principal, puertos, servicios, salud="verde", apagado=False):
    return {
        "nombre": nombre,
        "carpeta": carpeta,
        "principal": principal,
        "puertos": puertos,
        "servicios": servicios,
        "salud": salud,
        "apagado": apagado,
    }


EXTRAS_VACIOS = {"salud": None, "servicios": [], "apagado": False}


ESPERADO = [
    ent("gastos-casa", "~/Proyectos/gastos-casa", 8765, [p(8765, "gastos", 8765)], [svc("gastos")]),
    ent("ps9", "~/proyectos/acme/ps9", 8080,
        [p(8080, "web", 80), p(8092, "mock-login", 3000), p(8093, "mock-checkout", 3000)],
        [svc("db"), svc("mock-checkout"), svc("mock-login"), svc("php"), svc("web")]),
    ent("tienda-a", "~/proyectos/acme/tienda-a", 8088,
        [p(3306, "db", 3306), p(8025, "mailhog", 8025), p(8088, "tienda-b", 3000)],
        [svc("db"), svc("mailhog"), svc("tienda-b")]),
]


@pytest.mark.parametrize(
    "state,status,esperado",
    [
        ("running", "Up 2 hours (unhealthy)", ("enfermo", None, None)),
        ("running", "Up 10 seconds (health: starting)", ("arrancando", None, None)),
        ("running", "Up 3 minutes (healthy)", ("corriendo", None, None)),
        ("running", "Up 8 hours", ("corriendo", None, None)),
        ("restarting", "Restarting (1) 5 seconds ago", ("reiniciando", 1, 5)),
        ("paused", "Paused", ("pausado", None, None)),
        ("running", "Up 5 minutes (Paused)", ("pausado", None, None)),
        ("exited", "Exited (1) 2 hours ago", ("caido", 1, 7200)),
        ("exited", "Exited (0) 2 minutes ago", ("terminado", 0, 120)),
        ("exited", "Exited (0) 3 days ago", ("terminado", 0, 259200)),
        ("dead", "Dead", ("caido", None, None)),
        ("created", "Created", ("caido", None, None)),
        ("removing", "Removing", ("caido", None, None)),
        ("exited", "Exited (137) Less than a second ago", ("caido", 137, 0)),
        ("exited", "Exited (0) 42 seconds ago", ("terminado", 0, 42)),
        ("exited", "Exited (1) About a minute ago", ("caido", 1, 60)),
        ("exited", "Exited (2) 3 minutes ago", ("caido", 2, 180)),
        ("exited", "Exited (0) About an hour ago", ("terminado", 0, 3600)),
        ("exited", "Exited (0) 2 hours ago", ("terminado", 0, 7200)),
        ("exited", "Exited (0) 1 days ago", ("terminado", 0, 86400)),
        ("exited", "Exited (0) 2 weeks ago", ("terminado", 0, 1209600)),
        ("exited", "Exited (0) 3 months ago", ("terminado", 0, 7776000)),
        ("exited", "Exited (0) 1 years ago", ("terminado", 0, 31536000)),
        ("exited", "Exited (0) strange", ("terminado", 0, None)),
    ],
)
def test_estado_servicio(state, status, esperado):
    assert estado_servicio(state, status) == esperado


def _linea_ps(proyecto, servicio, state, status, ports=""):
    wd = f"/home/usuario/Proyectos/{proyecto}"
    labels = (
        f"com.docker.compose.project={proyecto},"
        f"com.docker.compose.project.working_dir={wd},"
        f"com.docker.compose.service={servicio}"
    )
    return json.dumps(
        {
            "ID": f"id-{proyecto}-{servicio}",
            "Image": "img",
            "Labels": labels,
            "Names": f"{proyecto}-{servicio}-1",
            "Ports": ports,
            "State": state,
            "Status": status,
        },
    )


def test_web_y_migrate_terminado_verde_no_apagado():
    salida = "\n".join(
        [
            _linea_ps("demo", "web", "running", "Up 1 hour", "0.0.0.0:9200->80/tcp"),
            _linea_ps("demo", "migrate", "exited", "Exited (0) 1 hour ago"),
        ],
    )
    e = next(x for x in armar_entornos(salida, Config(), HOME) if x["nombre"] == "demo")
    assert e["salud"] == "verde"
    assert e["apagado"] is False
    migrate = next(s for s in e["servicios"] if s["servicio"] == "migrate")
    assert migrate == svc("migrate", "terminado", 0, 3600)


def test_todo_exited_cero_reciente_rojo_apagado():
    salida = "\n".join(
        [
            _linea_ps("off", "web", "exited", "Exited (0) 5 minutes ago"),
            _linea_ps("off", "db", "exited", "Exited (0) 5 minutes ago"),
        ],
    )
    e = next(x for x in armar_entornos(salida, Config(), HOME) if x["nombre"] == "off")
    assert e["salud"] == "rojo"
    assert e["apagado"] is True


def test_arma_entornos_salud_y_apagados_desde_ps_a():
    entornos = {e["nombre"]: e for e in armar_entornos(FIXTURE_A, Config(), HOME)}
    assert entornos["todo-verde"]["salud"] == "verde"
    assert entornos["mixto-amarillo"]["salud"] == "amarillo"
    worker = next(s for s in entornos["mixto-amarillo"]["servicios"] if s["servicio"] == "worker")
    assert worker == svc("worker", "caido", 1, 300)
    assert entornos["todo-caido-reciente"]["salud"] == "rojo"
    assert entornos["todo-caido-reciente"]["apagado"] is False
    assert entornos["todo-apagado"]["salud"] == "rojo"
    assert entornos["todo-apagado"]["apagado"] is True
    assert entornos["todo-apagado"]["principal"] is None
    assert all(s["estado"] == "terminado" for s in entornos["todo-apagado"]["servicios"])
    assert entornos["enfermo-proj"]["salud"] == "amarillo"
    assert next(s for s in entornos["enfermo-proj"]["servicios"] if s["servicio"] == "app")[
        "estado"
    ] == "enfermo"
    nombres = [e["nombre"] for e in armar_entornos(FIXTURE_A, Config(), HOME)]
    assert nombres.index("todo-apagado") == len(nombres) - 1
    assert all(n != "todo-apagado" for n in nombres[: nombres.index("todo-apagado")])


def test_parsea_puertos_publicados_sin_duplicar():
    assert parsear_puertos("0.0.0.0:8080->80/tcp, [::]:8080->80/tcp") == [(8080, 80)]
    assert parsear_puertos("127.0.0.1:8092->3000/tcp") == [(8092, 3000)]
    assert parsear_puertos("3306/tcp, 33060/tcp") == []
    assert parsear_puertos("") == []
    assert parsear_puertos("0.0.0.0:5353->5353/udp") == []
    assert parsear_puertos("0.0.0.0:8000-8001->8000-8001/tcp") == [(8000, 8000), (8001, 8001)]


def test_labels_con_comas_en_valores():
    assert parsear_labels("a=1,com.docker.compose.project.config_files=/x/a.yml,/x/b.yml,"
                          "com.docker.compose.depends_on=db:s:false,php:s:false,com.docker.compose.service=web") == {
        "a": "1", "com.docker.compose.project.config_files": "/x/a.yml",
        "com.docker.compose.depends_on": "db:s:false", "com.docker.compose.service": "web"}


def test_carpeta_corta():
    assert carpeta_corta("/home/usuario/proyectos/acme/ps9", HOME) == "~/proyectos/acme/ps9"
    assert carpeta_corta("/home/usuario", HOME) == "~"
    assert carpeta_corta("/home/usuariox/a", HOME) == "/home/usuariox/a"


def test_arma_entornos_desde_docker_ps_real():
    assert armar_entornos(FIXTURE, Config(), HOME) == ESPERADO


def test_lineas_rotas_se_ignoran():
    assert armar_entornos("no es json\n[]\n\n" + FIXTURE, Config(), HOME) == ESPERADO


def test_principal_heuristica():
    assert elegir_principal([p(8280, "tienda-d", 80), p(8281, "mock-sso", 3000)]) == 8280
    assert elegir_principal([p(8100, "admin", 8100), p(8280, "front", 3000), p(8290, "web", 80)]) == 8290
    assert elegir_principal([p(8100, "admin", 8100), p(8280, "front", 3000)]) == 8280
    assert elegir_principal([p(3306, "db", 3306), p(8025, "mailhog", 8025)]) == 3306
    assert elegir_principal([p(80, "web", 80, abrible=False)]) is None


def test_guard_principal_override_solo_si_abrible():
    cfg = Config(entornos_extra=[{"nombre": "solo-guard-ov", "puertos": [9000, 8770], "principal": 8770}])
    e = next(x for x in armar_entornos("", cfg, HOME) if x["nombre"] == "solo-guard-ov")
    assert e["principal"] == 9000


def test_guard_puerto_menor_1024_no_abrible():
    cfg = Config(entornos_extra=[{"nombre": "solo-guard-bajo", "puertos": [80, 9001], "principal": 9001}])
    e = next(x for x in armar_entornos("", cfg, HOME) if x["nombre"] == "solo-guard-bajo")
    assert next(x for x in e["puertos"] if x["puerto"] == 80)["abrible"] is False


def test_guard_puerto_en_lista_bloqueados_no_abrible():
    cfg = Config(entornos_extra=[{"nombre": "solo-guard-bloq", "puertos": [8770], "principal": 8770}])
    e = next(x for x in armar_entornos("", cfg, HOME) if x["nombre"] == "solo-guard-bloq")
    assert e["puertos"][0]["abrible"] is False


def test_principal_override():
    ent_a = lambda cfg: next(e for e in armar_entornos(FIXTURE, cfg, HOME) if e["nombre"] == "tienda-a")
    assert ent_a(Config(entornos_principal={"tienda-a": 8025}))["principal"] == 8025
    assert ent_a(Config(entornos_principal={"tienda-a": 9999}))["principal"] == 8088


def test_entornos_extra():
    cfg = Config(entornos_extra=[
        {"nombre": "floci", "puertos": [4566], "principal": 4566},
        {"nombre": "dup", "puertos": [8080, 9100], "principal": 8080},
        {"nombre": "Mal Nombre", "puertos": [9200]},
        {"nombre": "raro", "puertos": ["x", 70000]},
        "no soy dict",
    ])
    extra = {e["nombre"]: e for e in armar_entornos(FIXTURE, cfg, HOME) if e["nombre"] not in ("gastos-casa", "tienda-a", "ps9")}
    assert extra == {
        "floci": {
            "nombre": "floci", "carpeta": "", "principal": 4566, "puertos": [p(4566, "floci", None)],
            **EXTRAS_VACIOS,
        },
        "dup": {
            "nombre": "dup", "carpeta": "", "principal": 9100, "puertos": [p(9100, "dup", None)],
            **EXTRAS_VACIOS,
        },
    }


def test_bloqueados_y_bajos_no_abribles():
    cfg = Config(entornos_extra=[{"nombre": "colmena", "puertos": [8770, 80, 7437, 5173], "principal": 5173}])
    e = next(x for x in armar_entornos("", cfg, HOME) if x["nombre"] == "colmena")
    assert [(x["puerto"], x["abrible"]) for x in e["puertos"]] == [(80, False), (5173, True), (7437, False), (8770, False)]
    assert e["principal"] == 5173


class FakeDocker:
    def __init__(self, respuesta=(0, FIXTURE.encode(), b"")):
        self.respuesta, self.llamadas = respuesta, []

    async def __call__(self, args):
        self.llamadas.append(args)
        if isinstance(self.respuesta, BaseException):
            raise self.respuesta
        return self.respuesta


def test_correr_docker_timeout_mata_proceso(monkeypatch):
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.kill = MagicMock()
    proc.wait = AsyncMock()

    async def fake_exec(*_a, **_k):
        return proc

    async def fake_wait_for(coro, timeout):
        try:
            raise asyncio.TimeoutError()
        finally:
            coro.close()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(correr_docker(["/usr/bin/docker", "ps", "--format", "{{json .}}"]))
    proc.kill.assert_called_once()
    proc.wait.assert_awaited_once()


def test_correr_docker_cancelacion_mata_proceso(monkeypatch):
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    proc.returncode = None

    async def fake_exec(*_a, **_k):
        return proc

    async def fake_wait_for(coro, timeout):
        try:
            raise asyncio.CancelledError()
        finally:
            coro.close()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(correr_docker(["/usr/bin/docker", "ps", "--format", "{{json .}}"]))
    proc.kill.assert_called_once()
    proc.wait.assert_awaited_once()


def test_listar_pasa_argv_fijo():
    fake = FakeDocker()
    r = asyncio.run(listar(Config(docker_bin="/usr/bin/docker"), fake, HOME))
    assert fake.llamadas == [["/usr/bin/docker", "ps", "-a", "--format", "{{json .}}"]]
    assert r == {"entornos": ESPERADO, "error": None}


@pytest.mark.parametrize("respuesta", [
    (1, b"", b"Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?"),
    asyncio.TimeoutError(), FileNotFoundError("docker"),
])
def test_docker_caido_lista_vacia_con_error(respuesta):
    r = asyncio.run(listar(Config(docker_bin="/usr/bin/docker"), FakeDocker(respuesta), HOME_AISLADO))
    assert r == {"entornos": [], "error": "Docker no responde"}


def test_sin_docker(monkeypatch):
    monkeypatch.setattr(entornos_mod.shutil, "which", lambda name: None)
    fake = FakeDocker()
    assert asyncio.run(listar(Config(), fake, HOME_AISLADO)) == {
        "entornos": [], "error": "No encuentro docker en la notebook",
    }
    assert fake.llamadas == []


@pytest.fixture
def eclient(cfg, tmp_path, handoffs, enchufe):
    cfg.docker_bin = "/usr/bin/docker"
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    hub.self_pane_id = "w2:p9"
    app = create_app(
        cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests, dist=tmp_path / "nodist",
        handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads", enchufe=enchufe, entornos_runner=FakeDocker(),
    )
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def test_endpoint_devuelve_entornos(eclient):
    r = eclient.get("/api/entornos")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert [e["nombre"] for e in r.json()["entornos"]] == ["gastos-casa", "ps9", "tienda-a"]
    assert r.json()["error"] is None


def test_endpoint_sin_sesion_401(client):
    assert client.get("/api/entornos").status_code == 401
