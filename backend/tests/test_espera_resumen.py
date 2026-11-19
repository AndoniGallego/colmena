import asyncio
import json

import pytest
from orquestador.hook_andokit import DetectorHookAndokit
from orquestador.estado_sesiones import ESPERA_RESUMEN_S, EstadoSesiones
from orquestador.ganchos.mensaje import Ids, MensajeGancho

IDS_G = Ids("g1:p1", None, None, None, "s1")
IDS_H = Ids(None, "w1:p1", "w1:t1", "w1", "s2")
PANE = "g1:p1"

SIN_ESTADO = "Terminé el cambio."
CON_ESTADO = 'Terminé el cambio.\n\n```estado\n{"hizo": "Cambié X"}\n```'
PREGUNTA = "Terminé. ¿Lo dejo así?"


class Reloj:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class Programador:
    """Reemplaza call_later: guarda los temporizadores y los dispara a mano."""

    def __init__(self):
        self.pendientes = []

    def __call__(self, demora, cb):
        h = _Handle(demora, cb)
        self.pendientes.append(h)
        return h

    def activos(self):
        return [h for h in self.pendientes if not h.cancelado and not h.disparado]

    def disparar(self):
        for h in self.activos():
            h.disparado = True
            h.cb()


class _Handle:
    def __init__(self, demora, cb):
        self.demora, self.cb = demora, cb
        self.cancelado = False
        self.disparado = False

    def cancel(self):
        self.cancelado = True


def ev(evento, ids=IDS_G, **datos):
    return MensajeGancho(evento, "global", ids, datos)


@pytest.fixture
def ctx():
    r, p = Reloj(), Programador()
    e = EstadoSesiones(clock=r, programar=p, hook_instalado=lambda: True)
    avisos = []
    e.observadores.append(lambda pane, evento: avisos.append((pane, evento)))
    return e, r, p, avisos


def enviar(e, r, msg, pane=PANE):
    r.t += 2
    return e.recibir(msg, pane)


def test_constante():
    assert ESPERA_RESUMEN_S == 20


def test_stop_sin_estado_no_declara_fin_de_turno(ctx):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    avisos.clear()
    enviar(e, r, ev("Stop", last_assistant_message=SIN_ESTADO))
    assert e.estado_de(PANE).estado == "working"
    assert e.estado_de(PANE).stop_en is None
    assert avisos == []
    assert len(p.activos()) == 1
    assert p.activos()[0].demora == ESPERA_RESUMEN_S


def test_stop_con_estado_dentro_de_la_ventana_es_un_solo_fin(ctx):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    avisos.clear()
    enviar(e, r, ev("Stop", last_assistant_message=SIN_ESTADO))
    enviar(e, r, ev("Stop", last_assistant_message=CON_ESTADO))
    reg = e.estado_de(PANE)
    assert reg.estado == "done"
    assert "Cambié X" in reg.ultimo_mensaje
    assert avisos == [(PANE, "Stop")]
    assert p.activos() == []
    p.disparar()
    assert avisos == [(PANE, "Stop")]


def test_vence_la_espera_y_cierra_una_vez(ctx):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    avisos.clear()
    enviar(e, r, ev("Stop", last_assistant_message=SIN_ESTADO))
    r.t += ESPERA_RESUMEN_S
    p.disparar()
    reg = e.estado_de(PANE)
    assert reg.estado == "done"
    assert reg.ultimo_mensaje == SIN_ESTADO
    assert avisos == [(PANE, "Stop")]
    p.disparar()
    assert avisos == [(PANE, "Stop")]


@pytest.mark.parametrize("actividad", ["PreToolUse", "UserPromptSubmit"])
def test_actividad_cancela_la_espera(ctx, actividad):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    avisos.clear()
    enviar(e, r, ev("Stop", last_assistant_message=SIN_ESTADO))
    enviar(e, r, ev(actividad, tool_use_id="t1", tool_name="Bash"))
    assert p.activos() == []
    p.disparar()
    assert e.estado_de(PANE).estado == "working"
    assert (PANE, "Stop") not in avisos
    enviar(e, r, ev("Stop", last_assistant_message=CON_ESTADO))
    assert e.estado_de(PANE).estado == "done"
    assert avisos.count((PANE, "Stop")) == 1


def test_stop_con_estado_cierra_de_inmediato(ctx):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    avisos.clear()
    enviar(e, r, ev("Stop", last_assistant_message=CON_ESTADO))
    assert e.estado_de(PANE).estado == "done"
    assert avisos == [(PANE, "Stop")]
    assert p.pendientes == []


def test_pregunta_a_ando_no_espera(ctx):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    avisos.clear()
    enviar(e, r, ev("Stop", last_assistant_message=PREGUNTA))
    assert e.estado_de(PANE).estado == "done"
    assert avisos == [(PANE, "Stop")]
    assert p.pendientes == []


def test_terminal_que_no_es_de_colmena_no_espera(ctx):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit", ids=IDS_H), pane="w1:p1")
    enviar(e, r, ev("Stop", ids=IDS_H, last_assistant_message=SIN_ESTADO), pane="w1:p1")
    assert e.estado_de("w1:p1").estado == "done"
    assert p.pendientes == []


def test_error_en_el_temporizador_se_loguea_y_no_tumba(ctx, caplog):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    enviar(e, r, ev("Stop", last_assistant_message=SIN_ESTADO))

    def roto():
        raise RuntimeError("secreto-no-loguear")

    e._clock = roto
    with caplog.at_level("ERROR"):
        p.disparar()
    assert "fin de turno diferido falló" in caplog.text
    assert e._esperas == {}
    assert avisos == [(PANE, "UserPromptSubmit"), (PANE, "PreToolUse")]


def test_al_vencer_refresca_el_tablero(ctx):
    e, r, p, avisos = ctx
    llamadas = []
    e.al_cierre_diferido = lambda: llamadas.append(1)
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    enviar(e, r, ev("Stop", last_assistant_message=SIN_ESTADO))
    assert llamadas == []
    p.disparar()
    assert llamadas == [1]


def test_estado_roto_seguido_de_uno_valido_cuenta_como_sin_estado(ctx):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    msg = 'Listo.\n```estado\n{roto\n```\n```estado\n{"hizo": "X"}\n```'
    enviar(e, r, ev("Stop", last_assistant_message=msg))
    assert e.estado_de(PANE).estado == "working"
    assert len(p.activos()) == 1


def test_turno_sin_herramientas_cierra_de_inmediato(ctx):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("Stop", last_assistant_message=SIN_ESTADO))
    assert e.estado_de(PANE).estado == "done"
    assert p.pendientes == []


def test_herramientas_del_turno_anterior_no_cuentan(ctx):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    enviar(e, r, ev("Stop", last_assistant_message=CON_ESTADO))
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("Stop", last_assistant_message=SIN_ESTADO))
    assert e.estado_de(PANE).estado == "done"
    assert p.pendientes == []


@pytest.mark.parametrize("previo", ["blocked", "idle"])
def test_solo_espera_si_estaba_working(ctx, previo):
    e, r, p, avisos = ctx
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    e.estado_de(PANE).estado = previo
    enviar(e, r, ev("Stop", last_assistant_message=SIN_ESTADO))
    assert e.estado_de(PANE).estado == "done"
    assert p.pendientes == []


def test_sin_loop_ni_programador_cierra_de_inmediato():
    r = Reloj()
    e = EstadoSesiones(clock=r)
    r.t += 2
    e.recibir(ev("UserPromptSubmit"), PANE)
    r.t += 2
    e.recibir(ev("Stop", last_assistant_message=SIN_ESTADO), PANE)
    assert e.estado_de(PANE).estado == "done"


def _turno_con_stop(e, r):
    enviar(e, r, ev("UserPromptSubmit"))
    enviar(e, r, ev("PreToolUse", tool_use_id="t0", tool_name="Bash"))
    enviar(e, r, ev("Stop", last_assistant_message=SIN_ESTADO))


def _settings(tmp_path, contenido):
    f = tmp_path / "settings.json"
    f.write_text(contenido if isinstance(contenido, str) else json.dumps(contenido))
    return f


HOOK = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "bash /x/andokit-stop-bloques.sh"}]}]}}


def test_con_el_hook_instalado_espera(tmp_path):
    r, p = Reloj(), Programador()
    f = _settings(tmp_path, HOOK)
    e = EstadoSesiones(clock=r, programar=p, hook_instalado=DetectorHookAndokit(lambda: f))
    _turno_con_stop(e, r)
    assert e.estado_de(PANE).estado == "working"
    assert len(p.activos()) == 1


@pytest.mark.parametrize("contenido", [
    {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "otra-cosa.sh"}]}]}},
    {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "andokit-stop-bloques"}]}]}},
    {},
    "{no es json",
])
def test_sin_el_hook_o_settings_ilegible_cierra_de_inmediato(tmp_path, contenido):
    r, p = Reloj(), Programador()
    f = _settings(tmp_path, contenido)
    e = EstadoSesiones(clock=r, programar=p, hook_instalado=DetectorHookAndokit(lambda: f))
    _turno_con_stop(e, r)
    assert e.estado_de(PANE).estado == "done"
    assert p.pendientes == []


def test_settings_inexistente_cierra_de_inmediato(tmp_path):
    r, p = Reloj(), Programador()
    e = EstadoSesiones(clock=r, programar=p, hook_instalado=DetectorHookAndokit(lambda: tmp_path / "no.json"))
    _turno_con_stop(e, r)
    assert e.estado_de(PANE).estado == "done"


def test_detector_cachea_con_ttl(tmp_path):
    t = [0.0]
    f = _settings(tmp_path, {})
    d = DetectorHookAndokit(lambda: f, ttl=60, clock=lambda: t[0])
    assert d() is False
    _settings(tmp_path, HOOK)
    t[0] = 30
    assert d() is False
    t[0] = 61
    assert d() is True


def test_sin_detector_no_espera():
    r, p = Reloj(), Programador()
    e = EstadoSesiones(clock=r, programar=p)
    _turno_con_stop(e, r)
    assert e.estado_de(PANE).estado == "done"
    assert p.pendientes == []


def test_temporizador_real_vence_y_cierra():
    avisos = []

    async def correr():
        cerrado = asyncio.Event()
        e = EstadoSesiones(espera_resumen=0.01, hook_instalado=lambda: True)
        e.observadores.append(lambda pane, evento: (avisos.append((pane, evento)), evento == "Stop" and cerrado.set()))
        e.recibir(ev("UserPromptSubmit"), PANE)
        e.recibir(ev("PreToolUse", tool_use_id="t0", tool_name="Bash"), PANE)
        avisos.clear()
        e.recibir(ev("Stop", last_assistant_message=SIN_ESTADO), PANE)
        assert e.estado_de(PANE).estado == "working"
        await asyncio.wait_for(cerrado.wait(), 2)
        return e

    e = asyncio.run(correr())
    assert e.estado_de(PANE).estado == "done"
    assert avisos.count((PANE, "Stop")) == 1
