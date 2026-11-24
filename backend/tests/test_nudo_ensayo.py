"""Ensayo de punta a punta del nudo con una PC de mentira.

La PC falsa hace lo que la app de Windows: se suscribe (acá, `pc_conectada` con una cola, igual que el SSE
`/events?pc=1`), recibe las órdenes de la cola y contesta por `POST /api/nudo/{id}/respuesta`.
La sesión usa el mismo manejador que el socket Unix de la CLI; los códigos de salida salen de `main_nudo`
con el socket reemplazado por una llamada directa al manejador.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, make_snapshot
from orquestador import nudo_cli
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.nudo import INACTIVIDAD_DUENO_S, crear_manejador
from orquestador.push import PushService
from orquestador.state import StateStore
from test_avisos import Sender

DEV = "device-abc123"
A, B = "w1:p1", "w1:p2"
CONTROLES = {"foto": 3, "ventana": {"titulo": "Mail", "proceso": "mail.exe"}, "monitor": "1920x1080",
             "controles": [{"n": 1, "tipo": "boton", "nombre": "Enviar"},
                           {"n": 2, "tipo": "campo", "nombre": "Para"}]}


class Reloj:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t


def _tablero():
    return {"workspaces": [{"tabs": [{"agents": [{"pane_id": A, "title": "Sesión A"},
                                                  {"pane_id": B, "title": "Sesión B"}]}]}]}


class Ensayo:
    """La PC falsa y la sesión, sobre el mismo store que usa la app."""

    def __init__(self, c: TestClient):
        self.c = c
        self.store = c.app.state.nudo
        self.reloj = Reloj()
        self.store._clock = self.reloj
        self.manejar = crear_manejador(self.store, _tablero)
        self.cola: asyncio.Queue = asyncio.Queue(maxsize=16)
        self.eventos: list[dict] = []

    # --- PC ---
    def conectar_pc(self, cola=None):
        self.cola = cola if cola is not None else asyncio.Queue(maxsize=16)
        self._en_el_loop(self.store.pc_conectada, DEV, self.cola)

    def desconectar_pc(self):
        self._en_el_loop(self.store.pc_desconectada, DEV, self.cola)

    def _en_el_loop(self, f, *a):
        async def _r():
            return f(*a)

        return self.c.portal.call(_r)

    def recibir(self) -> dict:
        async def _g():
            return await asyncio.wait_for(self.cola.get(), 5)

        nombre, ev = self.c.portal.call(_g)
        assert nombre == "nudo"
        self.eventos.append(ev)
        return ev

    def dueno(self):
        return self._en_el_loop(self.store.dueno)

    def vaciar(self) -> list[dict]:
        out = []
        while not self.cola.empty():
            out.append(self.cola.get_nowait()[1])
        return out

    def responder(self, ev: dict, resultado, status=200):
        r = self.c.post(f"/api/nudo/{ev['id']}/respuesta",
                        json={"device": DEV, "token": ev["token"], "resultado": resultado})
        assert r.status_code == status, r.text
        return r

    # --- sesión ---
    def pedir(self, op, sesion=A, args=None):
        """Lanza el pedido sin esperar; devuelve el future."""
        return self.c.portal.start_task_soon(self.manejar, {"op": op, "sesion": sesion, "args": args or {}})

    def pedir_y_responder(self, op, resultado, sesion=A, args=None, status=200):
        fut = self.pedir(op, sesion, args)
        ev = self.recibir()
        assert ev["op"] == op
        self.responder(ev, resultado, status)
        return fut.result(5), ev

    def pedir_directo(self, op, sesion=A, args=None):
        return self.c.portal.call(self.manejar, {"op": op, "sesion": sesion, "args": args or {}})

    def leer(self, sesion=A):
        datos, _ = self.pedir_y_responder("controles", CONTROLES, sesion)
        assert datos["ok"] is True
        return datos


@pytest.fixture
def ens(cfg, tmp_path, handoffs):
    enchufe = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    push = PushService(tmp_path, sender=Sender(), wall=lambda: 1_800_000_000.0)
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, push=push, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        e = Ensayo(c)
        e.conectar_pc()
        e.vaciar()  # el limpiar interno de la conexión
        yield e


def _cli(ens, capsys, argv, sesion=A):
    """Corre `orquestador nudo ...` con el socket reemplazado por el manejador; devuelve (código, out, err)."""
    original = nudo_cli._hablar
    nudo_cli._hablar = lambda ruta, pedido, timeout: (ens.c.portal.call(ens.manejar, pedido), None)
    try:
        codigo = nudo_cli.main_nudo(argv, {"COLMENA_SESION": sesion, "XDG_RUNTIME_DIR": "/x"})
    finally:
        nudo_cli._hablar = original
    cap = capsys.readouterr()
    return codigo, cap.out.strip(), cap.err.strip()


# --- recorrido feliz ---

def test_estado_prendido(ens):
    datos, ev = ens.pedir_y_responder("estado", {"prendido": True, "se_ve_al_compartir": False})
    assert datos == {"ok": True, "datos": {"prendido": True, "se_ve_al_compartir": False}}
    assert ev["sesion"] == "Sesión A"


def test_leer_devuelve_controles_sin_foto(ens):
    datos = ens.leer()
    assert "foto" not in datos["datos"]
    assert datos["datos"]["controles"][0] == {"n": 1, "tipo": "boton", "nombre": "Enviar"}
    assert ens.dueno() is None  # leer no toma el turno


def test_senalar_sin_esperar_toma_el_turno(ens):
    ens.leer()
    datos, ev = ens.pedir_y_responder("senalar", {"resultado": "ok"}, args={"n": 1, "texto": "Tocá Enviar"})
    assert datos == {"ok": True, "datos": {"resultado": "ok"}}
    assert ev["args"] == {"n": 1, "texto": "Tocá Enviar", "esperar": None, "foto": 3}
    assert ens.dueno() == (A, "Sesión A")


def test_senalar_esperando_listo(ens):
    ens.leer()
    fut = ens.pedir("senalar", args={"n": 1, "texto": "Tocá Enviar", "esperar": 90})
    ev = ens.recibir()
    assert ev["args"]["esperar"] == 90
    ens.responder(ev, {"resultado": "listo"})
    assert fut.result(5) == {"ok": True, "datos": {"resultado": "listo"}}
    assert ens.dueno() == (A, "Sesión A")


def test_senalar_esperando_usado(ens):
    ens.leer()
    fut = ens.pedir("senalar", args={"n": 2, "texto": "Escribí", "esperar": 0})
    ev = ens.recibir()
    assert ev["args"]["esperar"] == 120
    ens.responder(ev, {"resultado": "usado"})
    assert fut.result(5)["datos"] == {"resultado": "usado"}


def test_salir_desde_la_pc_en_medio_de_una_espera_libera(ens):
    ens.leer()
    fut = ens.pedir("senalar", args={"n": 1, "texto": "x", "esperar": 60})
    ev = ens.recibir()
    ens.responder(ev, {"resultado": "salir"})
    assert fut.result(5)["datos"] == {"resultado": "salir"}
    assert ens.dueno() is None
    fut = ens.pedir("controles", B)  # B ya puede pedir
    ev = ens.recibir()
    assert ev["op"] == "controles"
    ens.responder(ev, CONTROLES)
    assert fut.result(5)["ok"] is True


def test_post_salir_de_la_pc_libera_al_dueno(ens):
    ens.leer()
    ens.pedir_y_responder("marcar", {"resultado": "ok"}, args={"marcas": [{"n": 1, "etiqueta": "Acá"}]})
    assert ens.dueno() is not None
    assert ens.c.post("/api/nudo/salir", json={"device": DEV}).json() == {"ok": True}
    assert ens.dueno() is None
    assert ens.vaciar() == []  # salir no manda limpiar: la PC ya limpió


def test_marcar_y_limpiar(ens):
    ens.leer()
    datos, _ = ens.pedir_y_responder("marcar", {"resultado": "ok"},
                                     args={"marcas": [{"n": 1, "etiqueta": "Enviar"}, {"n": 2, "etiqueta": "Para"}]})
    assert datos["ok"] is True and ens.dueno() == (A, "Sesión A")
    datos, ev = ens.pedir_y_responder("limpiar", {"resultado": "ok"})
    assert datos == {"ok": True, "datos": {"resultado": "ok"}}
    assert ens.dueno() is None


def test_limpiar_sin_ser_dueno_no_molesta_a_la_pc(ens):
    assert ens.pedir_directo("limpiar") == {"ok": True, "datos": {"resultado": "ok", "nada": True}}
    assert ens.vaciar() == []


def test_senalar_sin_leer_es_foto_vieja(ens):
    r = ens.pedir_directo("senalar", args={"n": 1, "texto": "x"})
    assert r["ok"] is False and r["error"] == "foto_vieja"
    assert ens.vaciar() == []


# --- errores de la PC ---

@pytest.mark.parametrize("error", ["apagado", "sin_ventana", "sin_controles", "fallo_pc"])
def test_errores_de_la_pc_en_controles(ens, error):
    datos, _ = ens.pedir_y_responder("controles", {"error": error})
    assert datos["ok"] is False and datos["error"] == error
    assert ens.store._pend is None


@pytest.mark.parametrize("error", ["foto_vieja", "sin_control", "invalido"])
def test_errores_de_la_pc_en_senalar_no_toman_el_turno(ens, error):
    ens.leer()
    datos, _ = ens.pedir_y_responder("senalar", {"error": error}, args={"n": 1, "texto": "x"})
    assert datos["ok"] is False and datos["error"] == error
    assert ens.dueno() is None


def test_respuesta_basura_de_la_pc_es_fallo_pc(ens):
    fut = ens.pedir("controles")
    ev = ens.recibir()
    ens.responder(ev, {"controles": "nada"}, status=422)
    r = fut.result(5)
    assert r["ok"] is False and r["error"] == "fallo_pc"
    assert ens.store._pend is None


def test_error_desconocido_de_la_pc_es_fallo_pc(ens):
    fut = ens.pedir("estado")
    ev = ens.recibir()
    ens.responder(ev, {"error": "me_aburri"}, status=422)
    assert fut.result(5)["error"] == "fallo_pc"


def test_respuesta_repetida_o_con_token_ajeno_es_404(ens):
    fut = ens.pedir("estado")
    ev = ens.recibir()
    r = ens.c.post(f"/api/nudo/{ev['id']}/respuesta", json={"device": DEV, "token": "x" * 30,
                                                             "resultado": {"prendido": True, "se_ve_al_compartir": True}})
    assert r.status_code == 404
    ens.responder(ev, {"prendido": True, "se_ve_al_compartir": True})
    fut.result(5)
    ens.responder(ev, {"prendido": True, "se_ve_al_compartir": True}, status=404)


# --- sesión ocupada ---

def test_otra_sesion_ocupada_por_el_dueno(ens, capsys):
    ens.leer()
    ens.pedir_y_responder("senalar", {"resultado": "ok"}, args={"n": 1, "texto": "x"})
    r = ens.pedir_directo("controles", B)
    assert r == {"ok": False, "error": "ocupado", "mensaje": "Ocupado por Sesión A."}
    assert ens.vaciar() == []
    codigo, out, err = _cli(ens, capsys, ["controles"], sesion=B)
    assert (codigo, err) == (9, "Ocupado por Sesión A.")
    # el dueño sigue pudiendo
    assert ens.leer()["ok"] is True


def test_otra_sesion_ocupada_mientras_hay_un_pedido_en_vuelo(ens):
    ens.leer()
    fut = ens.pedir("senalar", args={"n": 1, "texto": "x", "esperar": 60})
    ev = ens.recibir()
    r = ens.pedir_directo("controles", B)
    assert r["error"] == "ocupado" and r["mensaje"] == "Ocupado por Sesión A."
    r = ens.pedir_directo("controles", A)
    assert r["error"] == "en_curso"
    ens.responder(ev, {"resultado": "listo"})
    fut.result(5)


def test_estado_no_se_bloquea_con_el_dueno(ens):
    ens.leer()
    ens.pedir_y_responder("marcar", {"resultado": "ok"}, args={"marcas": [{"n": 1, "etiqueta": "x"}]})
    datos, _ = ens.pedir_y_responder("estado", {"prendido": True, "se_ve_al_compartir": True}, sesion=B)
    assert datos["ok"] is True


def test_el_dueno_vence_a_los_120_segundos_y_la_pc_limpia(ens):
    ens.leer()
    ens.pedir_y_responder("marcar", {"resultado": "ok"}, args={"marcas": [{"n": 1, "etiqueta": "x"}]})
    ens.reloj.t += INACTIVIDAD_DUENO_S - 1
    assert ens.dueno() == (A, "Sesión A")
    assert ens.vaciar() == []
    ens.reloj.t += 2
    assert ens.dueno() is None
    (limpiar,) = ens.vaciar()
    assert limpiar["op"] == "limpiar" and limpiar["sesion"] == ""
    ens.responder(limpiar, {"resultado": "ok"})  # la PC contesta y el back lo acepta (200)
    # la lectura vieja quedó borrada: B puede leer y A necesita leer de nuevo
    assert ens.leer(B)["ok"] is True
    assert ens.pedir_directo("senalar", A, {"n": 1, "texto": "x"})["error"] == "foto_vieja"


def test_actividad_del_dueno_renueva_el_vencimiento(ens):
    ens.leer()
    ens.pedir_y_responder("marcar", {"resultado": "ok"}, args={"marcas": [{"n": 1, "etiqueta": "x"}]})
    ens.reloj.t += INACTIVIDAD_DUENO_S - 5
    ens.leer()
    ens.reloj.t += INACTIVIDAD_DUENO_S - 5
    assert ens.dueno() == (A, "Sesión A")


# --- PC desconectada y reconexión ---

def test_sin_pc_es_exit_4(ens, capsys):
    ens.desconectar_pc()
    codigo, out, err = _cli(ens, capsys, ["estado"])
    assert codigo == 4 and err == "PC no conectada: la app de Windows no está abierta."
    r = ens.pedir_directo("controles")
    assert r["error"] == "sin_pc"


def test_pc_que_se_cae_con_un_pedido_en_vuelo(ens):
    fut = ens.pedir("controles")
    ens.recibir()
    ens.desconectar_pc()
    assert fut.result(5)["error"] == "sin_pc"
    assert ens.store._pend is None


def test_pc_que_se_cae_libera_al_dueno_sin_mandar_limpiar(ens):
    ens.leer()
    ens.pedir_y_responder("marcar", {"resultado": "ok"}, args={"marcas": [{"n": 1, "etiqueta": "x"}]})
    ens.desconectar_pc()
    assert ens.dueno() is None
    assert ens.vaciar() == []


def test_reconexion_manda_un_limpiar_interno_y_la_pc_lo_contesta(ens):
    ens.desconectar_pc()
    ens.conectar_pc()
    ev = ens.recibir()
    assert ev["op"] == "limpiar" and ev["sesion"] == ""
    ens.responder(ev, {"resultado": "ok"})  # la app contesta igual que a cualquier orden


def test_reconexion_con_dueno_vivo_no_limpia(ens):
    # misma PC con una segunda conexión mientras A es dueña: no se pisa su marca
    ens.leer()
    ens.pedir_y_responder("marcar", {"resultado": "ok"}, args={"marcas": [{"n": 1, "etiqueta": "x"}]})
    ens.conectar_pc(asyncio.Queue(maxsize=16))
    assert ens.vaciar() == []
    assert ens.dueno() == (A, "Sesión A")


def test_pedido_justo_despues_de_reconectar_no_espera_al_limpiar_interno(ens):
    ens.desconectar_pc()
    ens.conectar_pc()
    fut = ens.pedir("controles")
    limpiar, lectura = ens.recibir(), ens.recibir()
    assert (limpiar["op"], lectura["op"]) == ("limpiar", "controles")  # en orden, la PC los atiende como llegan
    ens.responder(lectura, CONTROLES)
    assert fut.result(5)["ok"] is True
    ens.responder(limpiar, {"resultado": "ok"})  # y la respuesta tardía del limpiar igual se acepta


def test_limpiar_interno_que_la_pc_no_contesta_no_deja_nada_colgado(ens):
    ens.desconectar_pc()
    ens.conectar_pc()
    interno = ens.store._pend_interno
    assert interno is not None
    async def cancelar():
        ens.store._cancelar_interno(interno)
        await asyncio.sleep(0)
        return ens.store._pend_interno

    assert ens.c.portal.call(cancelar) is None
    ens.responder(ens.recibir(), {"resultado": "ok"}, status=404)


def test_al_irse_la_ultima_pc_se_olvidan_todas_las_lecturas(ens):
    ens.leer(A)
    ens.leer(B)
    ens.desconectar_pc()
    ens.conectar_pc()
    ens.vaciar()
    for sesion in (A, B):
        assert ens.pedir_directo("senalar", sesion, {"n": 1, "texto": "x"})["error"] == "foto_vieja"


def test_dueno_que_queda_sin_pc_no_sobrevive(ens):
    # la PC contesta y se cae antes de que la sesión retome el hilo
    ens.leer()
    fut = ens.pedir("marcar", args={"marcas": [{"n": 1, "etiqueta": "x"}]})
    ev = ens.recibir()

    async def contestar_y_caer():
        assert ens.store.resolver(ev["id"], DEV, ev["token"], {"resultado": "ok"})
        ens.store.pc_desconectada(DEV, ens.cola)

    ens.c.portal.call(contestar_y_caer)
    fut.result(5)
    assert ens.dueno() is None
    ens.conectar_pc()
    assert [e["op"] for e in ens.vaciar()] == ["limpiar"]


def test_cli_codigos_de_salida_de_punta_a_punta(ens, capsys):
    # Sin foto previa: foto_vieja = 5
    codigo, _, err = _cli(ens, capsys, ["senalar", "1", "hola"])
    assert codigo == 5 and "Foto vieja" in err
    # marca inválida: 2, sin tocar a la PC
    codigo, _, err = _cli(ens, capsys, ["marcar", "sinetiqueta"])
    assert codigo == 2 and ens.vaciar() == []
    # limpiar sin ser dueño
    codigo, out, _ = _cli(ens, capsys, ["limpiar"])
    assert (codigo, out) == (0, "no había nada tuyo")
