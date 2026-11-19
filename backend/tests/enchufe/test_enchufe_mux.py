import asyncio
import pytest
from conftest import make_snapshot
from orquestador.config import Config
from orquestador.enchufe import Evento, FakeTerminales, Mux, NoDisponible, crear_terminales, sesion_propia, VARIABLES_PROPIAS
from orquestador.enchufe.mux import _SuscripcionMux
from orquestador.enchufe.herdr import AdaptadorHerdr
from orquestador.enchufe.modelo import Espacio, Linea, Sesion, Tablero

def guardian():
    s = Sesion("g3:p1", "g3:t1", "g3", "claude", "idle", "guardian", None, "/tmp", None, "", 1, "guardian")
    return FakeTerminales(Tablero((Espacio("g3", "G", ("g3:t1",)),), (Linea("g3:t1", "g3", "l", ("g3:p1",)),), (s,), 4),
                          nombre="guardian")

def run(c):
    return asyncio.run(c)

@pytest.mark.parametrize("sid,dest", [("g3:p1", "guardian"), ("w1:p1", "herdr"), ("g3x:p1", "herdr"), ("gx", "herdr")])
def test_enruta_por_la_regex(sid, dest):
    h, g = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr"), guardian()
    m = Mux([h, g])
    try:
        run(m.interrumpir(sid))
    except Exception:
        pass
    assert [x.calls_of("interrumpir") for x in (h, g)] == ([[("interrumpir", sid)], []] if dest == "herdr" else [[], [("interrumpir", sid)]])

def test_sin_guardian_no_cae_a_herdr():
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    with pytest.raises(NoDisponible):
        run(Mux([h]).interrumpir("g3:p1"))
    assert h.calls == []

def test_tablero_une_y_suma_revisiones():
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    t = run(Mux([h, guardian()]).tablero())
    assert {"w1:p1", "g3:p1"} <= {s.id for s in t.sesiones}
    assert t.revision == run(h.tablero()).revision + 4

def test_crear_espacio_va_a_nuevas_en_y_linea_al_dueno_del_espacio():
    h, g = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr"), guardian()
    m = Mux([h, g], nuevas_en="guardian")
    run(m.crear_espacio("N", "/tmp"))
    run(m.crear_linea("w1", "x", "/tmp"))
    assert g.calls_of("crear_espacio") and h.calls_of("crear_linea") and not g.calls_of("crear_linea")

def test_enfocar_sin_foco_es_no_op():
    g = guardian()
    g.capacidades = frozenset({"renombrar"})
    run(Mux([g]).enfocar("g3:t1"))
    assert g.calls == []

def test_fabrica_arma_mux_con_herdr(herdr):
    m = crear_terminales(Config(), cliente=herdr)
    assert isinstance(m, Mux) and [type(b) for b in m.backends] == [AdaptadorHerdr]
    assert m.backends[0].cliente is herdr

def test_sesion_propia(monkeypatch):
    monkeypatch.setenv("HERDR_PANE_ID", "w4:p2")
    assert sesion_propia() == "w4:p2"
    assert "HERDR_PANE_ID" in VARIABLES_PROPIAS and "HERDR_WORKSPACE_ID" in VARIABLES_PROPIAS

def test_la_app_recibe_el_enchufe(client):
    assert type(client.app.state.enchufe).__name__ == "FakeTerminales"


def test_mux_suscribir_aclose_cierra_backends():
    async def escenario():
        h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr", poll=0.01)
        g = guardian()
        g.poll = 0.01
        m = Mux([h, g])
        it = m.suscribir()
        await asyncio.wait_for(it.aclose(), 0.2)
        await asyncio.sleep(0.05)
        assert len(h._colas) == 0 and len(g._colas) == 0

    asyncio.run(escenario())


class _SuscripcionQueExplota:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise RuntimeError("boom")

    async def aclose(self) -> None:
        pass


class _BackendConSuscripcionRota:
    nombre = "herdr"
    capacidades = frozenset()

    def suscribir(self):
        return _SuscripcionQueExplota()


def test_mux_suscribir_excepcion_backend_relanza_y_limpia_bombas():
    async def escenario():
        estable = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr", poll=0.01)
        roto = _BackendConSuscripcionRota()
        m = Mux([estable, roto])
        it = m.suscribir()
        with pytest.raises(RuntimeError, match="boom"):
            await asyncio.wait_for(it.__anext__(), 0.2)
        assert all(t.done() for t in it._tareas)
        assert len(estable._colas) == 0

    asyncio.run(escenario())


def test_mux_suscribir_cancelar_anext_limpia_bombas_y_hijos():
    async def escenario():
        h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
        g = guardian()
        m = Mux([h, g])
        it = m.suscribir()
        liberado = asyncio.Event()
        esperando = asyncio.Event()

        async def consumidor():
            esperando.set()
            try:
                await it.__anext__()
            except asyncio.CancelledError:
                liberado.set()
                raise

        t = asyncio.create_task(consumidor())
        await asyncio.wait_for(esperando.wait(), 0.2)
        t.cancel()
        await asyncio.wait_for(liberado.wait(), 0.2)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(t, 0.2)
        await asyncio.wait_for(asyncio.gather(*it._tareas, return_exceptions=True), 0.2)
        assert all(x.done() for x in it._tareas)
        assert len(h._colas) == 0 and len(g._colas) == 0

    asyncio.run(escenario())


class _SuscripcionHijoAcloseFalla:
    def __init__(self, fake: FakeTerminales):
        self._fake = fake
        self._cola: asyncio.Queue = asyncio.Queue()
        fake._colas.add(self._cola)
        self._cerrada = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._cerrada:
            raise StopAsyncIteration
        return await self._cola.get()

    async def aclose(self) -> None:
        raise OSError("aclose falló")


def test_mux_suscribir_aclose_si_hijo_falla_igual_cancela_bombas():
    async def escenario():
        h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr", poll=0.01)
        sub_malo = _SuscripcionHijoAcloseFalla(h)
        it = _SuscripcionMux([sub_malo])
        with pytest.raises(OSError, match="aclose falló"):
            await asyncio.wait_for(it.aclose(), 0.2)
        assert all(t.done() for t in it._tareas)
        await asyncio.wait_for(it.aclose(), 0.2)

    asyncio.run(escenario())


def test_mux_suscribir_aclose_despierta_consumidor_en_anext():
    async def escenario():
        h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr", poll=0.01)
        m = Mux([h])
        it = m.suscribir()
        despertado = asyncio.Event()

        async def consumidor():
            try:
                await it.__anext__()
            except StopAsyncIteration:
                despertado.set()

        t = asyncio.create_task(consumidor())
        for _ in range(50):
            await asyncio.sleep(0)
        await asyncio.wait_for(it.aclose(), 0.2)
        await asyncio.wait_for(asyncio.wait_for(t, 1.0), 1.0)
        assert despertado.is_set()

    asyncio.run(escenario())


def test_mux_suscribir_error_luego_aclose_anext_no_cuelga():
    async def escenario():
        roto = _BackendConSuscripcionRota()
        m = Mux([roto])
        it = m.suscribir()
        for _ in range(20):
            await asyncio.sleep(0)
        await it.aclose()
        with pytest.raises((RuntimeError, StopAsyncIteration)):
            await asyncio.wait_for(it.__anext__(), 1.0)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(it.__anext__(), 0.2)

    asyncio.run(escenario())


def test_backend_nombre_sin_backend_mensaje_claro():
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    m = Mux([h], nuevas_en="guardian")
    run(m.crear_espacio("N", "/tmp"))
    assert h.calls_of("crear_espacio")


def test_tablero_guardian_caido_usa_ultimo_y_marca_caidos():
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    g = guardian()
    m = Mux([h, g])
    run(m.tablero())
    g.caer()
    t = run(m.tablero())
    assert {s.id for s in t.sesiones} >= {"w1:p1", "g3:p1"}
    assert t.caidos == ("guardian",)


def test_crear_espacio_guardian_caido_cae_en_herdr():
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    g = guardian()
    g.caer()
    m = Mux([h, g], nuevas_en="guardian")
    run(m.crear_espacio("N", "/tmp"))
    assert h.calls_of("crear_espacio") and not g.calls_of("crear_espacio")


def test_caido_guardian_llega_como_tablero_seguridad():
    async def escenario():
        h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr", poll=0.01)
        g = guardian()
        m = Mux([h, g])
        it = m.suscribir()
        g.emitir(Evento("caido", "guardian"))
        ev = await asyncio.wait_for(it.__anext__(), 1.0)
        assert ev.tipo == "tablero" and ev.datos.get("motivo") == "seguridad"
        await it.aclose()

    asyncio.run(escenario())


def test_crear_terminales_default_solo_herdr(herdr):
    m = crear_terminales(Config(), cliente=herdr)
    assert len(m.backends) == 1 and m.backends[0].nombre == "herdr"


def test_crear_terminales_con_guardian(herdr):
    g = guardian()
    cfg = Config(terminales={"nuevas_en": "guardian"})
    m = crear_terminales(cfg, cliente=herdr, guardian=g)
    assert len(m.backends) == 2
    assert {b.nombre for b in m.backends} == {"herdr", "guardian"}
    assert m.nuevas_en == "guardian"

def test_esperar_listo_va_al_dueno_y_el_fake_responde_al_instante():
    h, g = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr"), guardian()
    assert run(Mux([h, g]).esperar_listo("g3:p1", 90.0)) == "guardian"
    assert g.calls_of("esperar_listo") == [("esperar_listo", "g3:p1", 90.0)]
    assert h.calls_of("esperar_listo") == []


def test_mux_reenvia_modo_y_fake_lo_registra():
    h, g = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr"), guardian()
    m = Mux([h, g])
    run(m.arrancar_claude("g3:p1", "x", modo="default"))
    run(m.arrancar_claude("g3:p1", "y"))
    assert g.calls_of("arrancar_claude") == [("arrancar_claude", "g3:p1", "x", None, "default"),
                                             ("arrancar_claude", "g3:p1", "y", None)]
