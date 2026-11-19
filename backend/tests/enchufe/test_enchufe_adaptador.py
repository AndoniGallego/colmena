import asyncio, json
import pytest
from conftest import FakeHerdr
from orquestador.enchufe.base import GrupoRequerido, Ilegible, NoDisponible, NoExiste, NoTomado, TerminalesError, Tiempo
from orquestador.enchufe.herdr import AdaptadorHerdr, HerdrError, info_de_process_json
from terminales_support import process_info

def run(coro):
    return asyncio.run(coro)

@pytest.fixture
def fh():
    return FakeHerdr()

@pytest.fixture
def ad(fh):
    return AdaptadorHerdr(fh)

CREADO = json.dumps({"result": {"root_pane": {"pane_id": "w1:p7"}, "tab": {"tab_id": "w1:t7"}, "workspace": {"workspace_id": "w1"}}})

@pytest.mark.parametrize("op,args,kw,argv", [
    ("mandar_prompt", ("w1:p1", "hola"), {}, ("agent", "prompt", "w1:p1", "hola", "--wait", "--until", "working", "--until", "blocked", "--until", "done", "--timeout", "30000")),
    ("interrumpir", ("w1:p1",), {}, ("pane", "send-keys", "w1:p1", "esc")),
    ("esperar", ("w1:p1", frozenset({"idle", "done"}), 600.0), {}, ("agent", "wait", "w1:p1", "--until", "idle", "--until", "done", "--timeout", "600000")),
    ("esperar", ("w1:p1", frozenset({"working", "idle", "done"}), 3.0), {}, ("agent", "wait", "w1:p1", "--until", "working", "--until", "idle", "--until", "done", "--timeout", "3000")),
    ("esperar_listo", ("w1:p1", 90.0), {}, ("agent", "wait", "w1:p1", "--until", "idle", "--until", "done", "--timeout", "90000")),
    ("teclas", ("w1:p1", ["arriba", "derecha", "ctrl-c", "ctrl-e", "ctrl-u", "esc", "enter", "4"]), {}, ("pane", "send-keys", "w1:p1", "up", "right", "ctrl+c", "ctrl+e", "ctrl+u", "esc", "enter", "4")),
    ("escribir", ("w1:p1", "Frutilla"), {}, ("pane", "send-text", "w1:p1", "Frutilla")),
    ("ejecutar", ("w3:p1", "ls -la"), {}, ("pane", "run", "w3:p1", "ls -la")),
    ("cerrar", ("w1:t1",), {}, ("tab", "close", "w1:t1")),
    ("cerrar", ("w2",), {}, ("workspace", "close", "w2")),
    ("cerrar", ("w1:p5",), {}, ("pane", "close", "w1:p5")),
    ("renombrar", ("w1:t1", "nuevo"), {}, ("tab", "rename", "w1:t1", "nuevo")),
    ("renombrar", ("w2", "Dos bis"), {}, ("workspace", "rename", "w2", "Dos bis")),
    ("arrancar_claude", ("w1:p7", "ana"), {}, ("agent", "start", "ana", "--kind", "claude", "--pane", "w1:p7")),
    ("proceso", ("w3:p1",), {}, ("pane", "process-info", "--pane", "w3:p1")),
    ("leer", ("w1:p1",), {"fuente": "deteccion", "lineas": 60}, ("pane", "read", "w1:p1", "--source", "detection", "--lines", "60", "--format", "text")),
    ("leer", ("w3:p1",), {"fuente": "reciente", "lineas": 500, "formato": "ansi"}, ("pane", "read", "w3:p1", "--source", "recent-unwrapped", "--lines", "500", "--format", "ansi")),
    ("leer", ("w3:p1",), {}, ("pane", "read", "w3:p1", "--source", "visible", "--format", "text")),
])
def test_cada_operacion_da_el_argv_de_hoy(fh, ad, op, args, kw, argv):
    fh.apply_closes = False
    run(getattr(ad, op)(*args, **kw))
    assert fh.calls == [argv]

@pytest.mark.parametrize("op,args,argv", [
    ("crear_linea", ("w1", "nueva", "/tmp"), ("tab", "create", "--workspace", "w1", "--cwd", "/tmp", "--label", "nueva", "--no-focus")),
    ("crear_espacio", ("Nuevo", "/tmp"), ("workspace", "create", "--cwd", "/tmp", "--label", "Nuevo", "--no-focus")),
])
def test_crear_lleva_no_focus_y_devuelve_los_tres_ids(fh, ad, op, args, argv):
    fh.responses[" ".join(argv[:2])] = CREADO
    creado = run(getattr(ad, op)(*args))
    assert fh.calls == [argv]
    assert (creado.espacio_id, creado.linea_id, creado.sesion_id) == ("w1", "w1:t7", "w1:p7")

@pytest.mark.parametrize("respuesta", ["no es json", json.dumps({"result": {"root_pane": {"pane_id": "--mal"}}})])
def test_crear_con_respuesta_ilegible(fh, ad, respuesta):
    fh.responses["tab create"] = respuesta
    with pytest.raises(Ilegible):
        run(ad.crear_linea("w1", "x", "/tmp"))

def test_enfocar_resuelve_el_espacio_desde_la_linea(fh, ad):
    run(ad.enfocar("w1:t1"))
    assert fh.focused == [("ws", "w1"), ("tab", "w1:t1")]
    with pytest.raises(NoExiste):
        run(ad.enfocar("w9:t9"))

def test_tecla_fuera_de_la_lista_no_llega_al_argv(fh, ad):
    with pytest.raises(ValueError):
        run(ad.teclas("w1:p1", ["enter", "f5"]))
    assert fh.calls == []

@pytest.mark.parametrize("texto,clase", [
    ("herdr no respondió a tiempo", Tiempo),
    ('{"error":{"code":"workspace_group_close_required"}}', GrupoRequerido),
    ('{"error":{"code":"pane_not_found"}}', NoExiste),
])
def test_traduccion_de_errores_conserva_el_texto(fh, ad, texto, clase):
    fh.responses["tab close"] = HerdrError(texto)
    with pytest.raises(clase) as info:
        run(ad.cerrar("w1:t1"))
    assert str(info.value) == texto

def test_error_desconocido_va_a_no_disponible_con_el_mismo_texto(fh, ad):
    fh.responses["pane send-keys"] = HerdrError("herdr salió con 1")
    with pytest.raises(NoDisponible, match="^herdr salió con 1$"):
        run(ad.interrumpir("w1:p1"))

def test_prompt_fallido_es_no_tomado(fh, ad):
    fh.responses["agent prompt"] = HerdrError("boom")
    with pytest.raises(NoTomado, match="^boom$"):
        run(ad.mandar_prompt("w1:p1", "x"))

def test_herdr_error_nunca_sale(fh, ad):
    fh.responses["pane run"] = HerdrError("x")
    with pytest.raises(Exception) as info:
        run(ad.ejecutar("w3:p1", "ls"))
    assert not isinstance(info.value, HerdrError)

def test_capacidades():
    assert AdaptadorHerdr(FakeHerdr()).capacidades == {"foco", "renombrar", "estado_propio", "retoma"}

def test_info_de_proceso():
    info = info_de_process_json(process_info(["bash"], pid=7))
    assert (info.pid, info.comando, info.es_claude, info.shell_pid) == (7, "bash", False, 1)
    assert info.procesos[0].argv == ("bash",)
    assert info_de_process_json("no es json").procesos == ()


@pytest.mark.parametrize("raw", ['{"result":{"process_info":null}}', '{"result":{"process_info":[1]}}',
                                 '{"result":{"process_info":"x"}}', '[]', 'null'])
def test_info_de_proceso_con_forma_rara_es_vacio(raw):
    info = info_de_process_json(raw)
    assert (info.pid, info.procesos, info.es_claude) == (None, (), False)


class FakeHerdrSoloErrores(FakeHerdr):
    async def snapshot(self):
        raise HerdrError("fallo snapshot")

    async def focus_workspace(self, ws):
        raise HerdrError("fallo focus_workspace")

    async def focus_tab(self, tab):
        raise HerdrError("fallo focus_tab")


@pytest.mark.parametrize("op,args", [
    ("tablero", ()),
    ("enfocar", ("w2",)),
])
def test_snapshot_y_focus_traducen_herdr_error(op, args):
    fh = FakeHerdrSoloErrores()
    ad = AdaptadorHerdr(fh)
    with pytest.raises(TerminalesError) as info:
        run(getattr(ad, op)(*args))
    assert not isinstance(info.value, HerdrError)


class FakeHerdrCancelled(FakeHerdr):
    async def run(self, *args):
        raise asyncio.CancelledError()


def test_cancelled_error_se_propaga_desde_llamar():
    ad = AdaptadorHerdr(FakeHerdrCancelled())
    with pytest.raises(asyncio.CancelledError):
        run(ad.ejecutar("w3:p1", "ls"))


def test_timeout_ms_redondea_en_lugar_de_truncar(fh, ad):
    run(ad.esperar("w1:p1", frozenset({"done"}), 4.35))
    argv = fh.calls[-1]
    assert argv[argv.index("--timeout") + 1] == "4350"


def test_teclas_vacia_no_llama_a_herdr(fh, ad):
    with pytest.raises(ValueError):
        run(ad.teclas("w1:p1", []))
    assert fh.calls == []


def test_tab_sin_workspace_id_en_snapshot_da_ilegible(fh, ad):
    snap = fh.current
    snap["tabs"] = [{"tab_id": "w1:t99", "label": "mal"}]
    with pytest.raises(Ilegible):
        run(ad.tablero())


class FakeHerdrSnapshotValueError(FakeHerdr):
    async def snapshot(self):
        raise ValueError("snapshot corrupto")


def test_value_error_en_snapshot_da_ilegible():
    ad = AdaptadorHerdr(FakeHerdrSnapshotValueError())
    with pytest.raises(Ilegible, match="snapshot corrupto"):
        run(ad.tablero())


def test_oserror_del_cliente_da_no_disponible(fh, ad):
    fh.responses["pane run"] = FileNotFoundError("herdr no está")
    with pytest.raises(NoDisponible, match="herdr no está"):
        run(ad.ejecutar("w3:p1", "ls"))


def test_value_error_en_mandar_prompt_da_no_tomado(fh, ad):
    fh.responses["agent prompt"] = ValueError("pane ocupado")
    with pytest.raises(NoTomado, match="pane ocupado"):
        run(ad.mandar_prompt("w1:p1", "x"))


def test_cancelled_error_se_propaga_desde_mandar_prompt():
    ad = AdaptadorHerdr(FakeHerdrCancelled())
    with pytest.raises(asyncio.CancelledError):
        run(ad.mandar_prompt("w1:p1", "x"))


class FakeHerdrFocusTabFalla(FakeHerdr):
    async def focus_tab(self, tab):
        raise HerdrError("tab_not_found")


def test_enfocar_linea_con_focus_tab_fallido_da_terminales_error():
    ad = AdaptadorHerdr(FakeHerdrFocusTabFalla())
    with pytest.raises(TerminalesError) as info:
        run(ad.enfocar("w1:t1"))
    assert not isinstance(info.value, HerdrError)


def test_tablero_logea_conflicto_solo_cuando_cambia_el_conjunto(fh, ad, caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="orquestador.enchufe.herdr")
    snap = fh.current
    snap["tabs"] = list(snap["tabs"]) + [{"tab_id": "g7:t1", "workspace_id": "w1", "label": "raro"}]
    fh.current = snap
    run(ad.tablero())
    run(ad.tablero())
    msgs = [r.message for r in caplog.records if "guardián" in r.message]
    assert msgs.count("id con forma de guardián en snapshot de Herdr: g7:t1") == 1


def test_herdr_con_modo_no_disponible(fh, ad):
    with pytest.raises(NoDisponible, match="modo de permisos"):
        run(ad.arrancar_claude("w1:p7", "ana", modo="default"))
    assert not any("start" in c for c in getattr(fh, "calls", []))
