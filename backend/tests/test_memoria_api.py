from orquestador.engram import EngramError
from orquestador.memoria import MemoriaService
from orquestador.config import Config

from conftest import SID


class FakeEngram:
    def __init__(self, caido=False, texto="Docker sin egress: usar password=hunter22 en local"):
        self.caido = caido
        self.texto = texto
        self.llamadas = []
        self.cerrado = False

    def herramientas(self):
        if self.caido:
            raise EngramError("no")
        return ["mem_search", "mem_get_observation", "mem_context", "mem_timeline"]

    def llamar(self, nombre, args):
        self.llamadas.append((nombre, args))
        if self.caido:
            raise EngramError("no")
        return self.texto

    def cerrar(self):
        self.cerrado = True


def test_estado_reindexar_y_borrar(authed, app):
    memoria = app.state.memoria
    memoria.indice.actualizar()
    fake = FakeEngram()
    memoria._engram_factory = lambda: fake
    estado = authed.get("/api/memoria/estado").json()
    assert estado["habilitada"] is True and estado["indexados"] == 1 and estado["turnos"] == 4
    assert estado["engram"] == "ok" and estado["ultima_actualizacion"]
    assert authed.post("/api/memoria/reindexar", headers={"Origin": "http://testserver"}).status_code == 200
    assert authed.post("/api/memoria/reindexar", headers={"Origin": "http://testserver"}).status_code == 429
    assert authed.delete("/api/memoria/indice", headers={"Origin": "http://testserver"}).status_code == 200
    memoria.indice.actualizar(esperar=True)
    memoria.borrar()
    assert authed.get("/api/memoria/estado").json()["indexados"] == 0


def test_cita_de_sesion_y_de_engram_redactadas(authed, app):
    memoria = app.state.memoria
    memoria.indice.actualizar()
    cita = authed.get(f"/api/memoria/cita?session_id={SID}&turno=1").json()
    assert cita["texto"] == "respuesta uno" and cita["titulo"] == "Título nuevo" and cita["rol"] == "claude"
    assert authed.get(f"/api/memoria/cita?session_id={SID}&turno=99").status_code == 404
    assert authed.get("/api/memoria/cita?session_id=../x&turno=1").status_code == 400
    assert authed.get(f"/api/memoria/cita?session_id={SID}").status_code == 400
    fake = FakeEngram()
    memoria._engram_factory = lambda: fake
    r = authed.get("/api/memoria/cita?engram=412")
    assert r.status_code == 200 and "hunter22" not in r.text and "Docker sin egress" in r.text
    assert fake.llamadas == [("mem_get_observation", {"id": 412})] and fake.cerrado
    memoria._engram_factory = lambda: FakeEngram(caido=True)
    assert authed.get("/api/memoria/cita?engram=412").status_code == 404
    assert authed.get("/api/memoria/cita?engram=0").status_code == 400


def test_endpoints_requieren_sesion(client):
    assert client.get("/api/memoria/estado").status_code == 401
    assert client.get(f"/api/memoria/cita?session_id={SID}&turno=1").status_code == 401


def test_engram_caido_y_cache(tmp_path):
    reloj = [0.0]
    creados = []

    def factory():
        creados.append(FakeEngram(caido=True))
        return creados[-1]

    svc = MemoriaService(Config(claude_projects_dir=str(tmp_path)), tmp_path, clock=lambda: reloj[0],
                         engram_factory=factory)
    assert svc.estado_engram() == "caido"
    assert svc.estado_engram() == "caido" and len(creados) == 1
    reloj[0] = 301.0
    svc.estado_engram()
    assert len(creados) == 2
    svc.cfg.memoria_habilitada = False
    assert svc.estado_engram() == "deshabilitado"
    assert MemoriaService(Config(claude_projects_dir=str(tmp_path), docker_bin=""), tmp_path,
                          engram_factory=lambda: None).estado_engram() == "caido"


def test_memoria_no_depende_del_mcp():
    import inspect

    from orquestador import memoria

    assert "memoria_mcp" not in inspect.getsource(memoria)
    assert not hasattr(memoria, "mcp_config") and not hasattr(MemoriaService, "mcp_config")


def test_tablero_con_throttle(tmp_path):
    reloj = [0.0]
    svc = MemoriaService(Config(claude_projects_dir=str(tmp_path)), tmp_path, clock=lambda: reloj[0])
    lanzados = []
    svc.fondo = lambda: lanzados.append(reloj[0])
    svc.on_board(None, {})
    reloj[0] = 30.0
    svc.on_board(None, {})
    reloj[0] = 61.0
    svc.on_board(None, {})
    assert lanzados == [0.0, 61.0]
