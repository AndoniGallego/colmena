import pytest
from orquestador.estado_sesiones import EstadoSesiones, dueno_de
from orquestador.ganchos.mensaje import Ids, MensajeGancho
from orquestador.redaccion import redactar

SID = "s1"
IDS = Ids(None, "w1:p1", "w1:t1", "w1", SID)


class Reloj:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def ev(evento, tool_use_id=None, tool_name="Bash", **datos):
    if tool_use_id:
        datos.update(tool_use_id=tool_use_id, tool_name=tool_name)
    return MensajeGancho(evento, "global", IDS, datos)


@pytest.fixture
def agg():
    r = Reloj()
    return EstadoSesiones(clock=r), r


@pytest.mark.parametrize(
    "secuencia,final",
    [
        ([ev("SessionStart")], "idle"),
        ([ev("UserPromptSubmit")], "working"),
        ([ev("PreToolUse", "t1")], "working"),
        ([ev("PostToolUse", "t1")], "working"),
        ([ev("PreToolUse", "t1"), ev("PermissionRequest", "t1")], "blocked"),
        (
            [
                ev("PreToolUse", "t1", tool_name="AskUserQuestion"),
                ev("PermissionRequest", "t1", tool_name="AskUserQuestion"),
            ],
            "blocked",
        ),
        (
            [
                ev("PreToolUse", "t1", tool_name="ExitPlanMode"),
                ev("PermissionRequest", "t1", tool_name="ExitPlanMode"),
            ],
            "blocked",
        ),
        ([ev("PreToolUse", "t1"), ev("Notification", notification_type="permission_prompt")], "blocked"),
        ([ev("Stop", last_assistant_message="listo")], "done"),
        ([ev("Stop"), ev("Notification", notification_type="idle_prompt")], "done"),
    ],
)
def test_transiciones(agg, secuencia, final):
    a, r = agg
    for m in secuencia:
        r.t += 2
        a.recibir(m, "w1:p1")
    assert a.estado_de("w1:p1").estado == final


def test_done_a_idle_solo_por_visto(agg):
    a, r = agg
    a.recibir(ev("Stop", last_assistant_message="fin"), "w1:p1")
    assert a.estado_de("w1:p1").ultimo_mensaje == "fin"
    assert a.marcar_visto(SID) and a.estado_de("w1:p1").estado == "idle"
    assert a.marcar_visto("otra") is False


def test_idle_prompt_va_a_ignorados(agg):
    a, _ = agg
    a.recibir(ev("Notification", notification_type="idle_prompt"), "w1:p1")
    assert list(a.ignorados) == ["idle_prompt"]


def test_idle_prompt_sin_pane_no_crea_registro(agg):
    a, _ = agg
    a.recibir(ev("Notification", notification_type="idle_prompt"), None)
    assert a.estado_de("w1:p1") is None


def test_idle_prompt_sin_session_start_no_crea_registro(agg):
    a, _ = agg
    a.recibir(ev("Notification", notification_type="idle_prompt"), "w1:p1")
    assert a.estado_de("w1:p1") is None


def test_ignorados_acotado(agg):
    a, r = agg
    a.recibir(ev("SessionStart"), "w1:p1")
    for _ in range(250):
        r.t += 2
        a.recibir(ev("Notification", notification_type="idle_prompt"), "w1:p1")
    assert len(a.ignorados) == 200


def test_dedup_notification_types_distintos_en_ventana(agg):
    a, r = agg
    a.recibir(ev("SessionStart"), "w1:p1")
    a.recibir(ev("Stop"), "w1:p1")
    r.t += 0.1
    assert a.recibir(ev("Notification", notification_type="idle_prompt"), "w1:p1") is True
    r.t += 0.1
    assert (
        a.recibir(ev("Notification", notification_type="permission_prompt"), "w1:p1") is True
    )


def test_dedup_sin_session_id_distingue_panes(agg):
    a, r = agg
    m1 = MensajeGancho("Stop", "global", Ids(None, "w1:p1", None, None, None), {})
    m2 = MensajeGancho("Stop", "global", Ids(None, "w2:p2", None, None, None), {})
    assert a.recibir(m1, "w1:p1") is True
    r.t += 0.1
    assert a.recibir(m2, "w2:p2") is True


def test_stop_luego_permission_prompt_queda_done(agg):
    a, r = agg
    a.recibir(ev("PreToolUse", "t1"), "w1:p1")
    a.recibir(ev("Stop"), "w1:p1")
    r.t += 0.1
    a.recibir(ev("Notification", notification_type="permission_prompt"), "w1:p1")
    assert a.estado_de("w1:p1").estado == "done"


def test_pre_huerfano_no_bloquea_tras_user_prompt(agg):
    a, r = agg
    a.recibir(ev("PreToolUse", "t1"), "w1:p1")
    a.recibir(ev("Stop"), "w1:p1")
    r.t += 2
    a.recibir(ev("UserPromptSubmit"), "w1:p1")
    r.t += 0.1
    a.recibir(ev("Notification", notification_type="permission_prompt"), "w1:p1")
    assert a.estado_de("w1:p1").estado == "working"


def test_stop_sin_last_assistant_message_deja_ultimo_none(agg):
    a, r = agg
    a.recibir(ev("Stop", last_assistant_message="fin"), "w1:p1")
    assert a.estado_de("w1:p1").ultimo_mensaje == "fin"
    r.t += 2
    a.recibir(ev("UserPromptSubmit"), "w1:p1")
    r.t += 2
    a.recibir(ev("Stop"), "w1:p1")
    assert a.estado_de("w1:p1").ultimo_mensaje is None


def test_stop_last_assistant_message_no_string_deja_ultimo_none(agg):
    a, r = agg
    a.recibir(ev("Stop", last_assistant_message="prev"), "w1:p1")
    r.t += 2
    a.recibir(ev("UserPromptSubmit"), "w1:p1")
    r.t += 2
    a.recibir(ev("Stop", last_assistant_message=123), "w1:p1")
    assert a.estado_de("w1:p1").ultimo_mensaje is None


def test_post_tardio_sin_tool_use_id_en_done_no_working(agg):
    a, r = agg
    a.recibir(ev("Stop"), "w1:p1")
    r.t += 1
    a.recibir(ev("PostToolUse"), "w1:p1")
    assert a.estado_de("w1:p1").estado == "done"


def test_sin_dueno_usa_wall_clock():
    mono = Reloj()
    wall = Reloj()
    wall.t = 2000.0
    a = EstadoSesiones(clock=mono, wall_clock=wall)
    a.recibir(ev("PreToolUse", "t1"), None)
    assert a.sin_dueno[0]["hora"] == 2000.0
    mono.t += 100
    assert a.sin_dueno[0]["hora"] == 2000.0


def test_dedup_por_tool_use_id(agg):
    a, r = agg
    assert a.recibir(ev("PreToolUse", "t1"), "w1:p1") is True
    r.t += 50
    assert a.recibir(ev("PreToolUse", "t1"), "w1:p1") is False
    assert a.recibir(ev("PreToolUse", "t2"), "w1:p1") is True
    assert a.recibir(ev("PostToolUse", "t1"), "w1:p1") is True


@pytest.mark.parametrize("delta,cuenta", [(0.9, False), (1.1, True)])
def test_dedup_ventana_sin_tool_use_id(agg, delta, cuenta):
    a, r = agg
    a.recibir(ev("Stop"), "w1:p1")
    r.t += delta
    assert a.recibir(ev("Stop"), "w1:p1") is cuenta


def test_tabla_de_vistos_acotada():
    r = Reloj()
    a = EstadoSesiones(clock=r, max_vistos=10)
    for i in range(50):
        a.recibir(ev("PreToolUse", f"t{i}"), "w1:p1")
    assert a.vistos_count() <= 10


def test_post_tardio_tras_stop_no_vuelve_a_working(agg):
    a, r = agg
    a.recibir(ev("PreToolUse", "t1"), "w1:p1")
    r.t += 1
    a.recibir(ev("Stop"), "w1:p1")
    r.t += 1
    a.recibir(ev("PostToolUse", "t1"), "w1:p1")
    assert a.estado_de("w1:p1").estado == "done"


def test_herramientas_previas_stop_se_limpia_en_user_prompt(agg):
    a, r = agg
    a.recibir(ev("PreToolUse", "t1"), "w1:p1")
    a.recibir(ev("Stop"), "w1:p1")
    a.recibir(ev("PostToolUse", "t1"), "w1:p1")
    assert a.estado_de("w1:p1").estado == "done"
    r.t += 2
    a.recibir(ev("UserPromptSubmit"), "w1:p1")
    reg = a.estado_de("w1:p1")
    assert reg.estado == "working"
    assert reg.herramientas_previas_stop == set()
    a.recibir(ev("PreToolUse", "t2"), "w1:p1")
    a.recibir(ev("Stop"), "w1:p1")
    a.recibir(ev("PostToolUse", "t2"), "w1:p1")
    assert a.estado_de("w1:p1").estado == "done"


def test_permission_prompt_tras_resolver_no_rebloquea(agg):
    a, r = agg
    a.recibir(ev("PreToolUse", "t1"), "w1:p1")
    a.recibir(ev("PermissionRequest", "t1"), "w1:p1")
    a.recibir(ev("PostToolUse", "t1"), "w1:p1")
    r.t += 6
    a.recibir(ev("Notification", notification_type="permission_prompt"), "w1:p1")
    assert a.estado_de("w1:p1").estado == "working"


def test_sin_dueno_se_guarda_aparte(agg):
    a, _ = agg
    msg = ev("PreToolUse", "t1", tool_input={"command": "secreto"})
    assert a.recibir(msg, None) is True
    assert a.estado_de("w1:p1") is None and len(a.sin_dueno) == 1
    assert "secreto" not in str(a.sin_dueno)
    entry = a.sin_dueno[0]
    assert set(entry.keys()) == {"evento", "claude", "hora"}
    assert a.recibir(msg, None) is False


def test_usando_desde_pre(agg):
    a, _ = agg
    a.recibir(ev("PreToolUse", "t1", tool_name="Edit"), "w1:p1")
    assert a.estado_de("w1:p1").usando == "Edit"


def test_ultimo_mensaje_redactado_y_recortado(agg):
    a, _ = agg
    largo = "x" * 600
    crudo = f"password=supersecret123 {largo}"
    a.recibir(ev("Stop", last_assistant_message=crudo), "w1:p1")
    msg = a.estado_de("w1:p1").ultimo_mensaje
    assert msg is not None
    assert len(msg) <= 500
    assert "supersecret123" not in msg
    esperado = redactar(crudo)[:500]
    assert msg == esperado


def test_dueno_de():
    board = {"workspaces": [{"tabs": [{"agents": [{"pane_id": "w1:p1", "session_id": SID}]}]}]}
    assert dueno_de(IDS, board) == "w1:p1"
    assert dueno_de(Ids(None, None, None, None, SID), board) == "w1:p1"
    assert dueno_de(Ids(None, "w9:p9", None, None, "otra"), board) is None
    assert dueno_de(IDS, None) is None
    assert dueno_de(Ids("g1:p2", None, None, None, None), board) == "g1:p2"


def test_observadores_reciben_evento():
    r = Reloj()
    e = EstadoSesiones(clock=r)
    vistos = []
    e.observadores.append(lambda pid, evn: vistos.append((pid, evn)))
    e.recibir(ev("UserPromptSubmit"), "w1:p1")
    assert vistos == [("w1:p1", "UserPromptSubmit")]


def test_aplicar_fuente_herdr_aplica_ganchos_solo_guardian():
    from orquestador.estado_sesiones import aplicar_fuente

    board = {
        "workspaces": [
            {
                "tabs": [
                    {
                        "agents": [
                            {"pane_id": "w1:p1", "status": "idle"},
                            {"pane_id": "g1:p2", "status": "idle"},
                        ]
                    }
                ]
            }
        ]
    }
    e = EstadoSesiones(clock=Reloj())
    ids_g = Ids("g1:p2", None, None, None, SID)
    msg = MensajeGancho(
        "PermissionRequest",
        "global",
        ids_g,
        {"tool_use_id": "t1", "tool_name": "Bash"},
    )
    e.recibir(msg, "g1:p2")
    out = aplicar_fuente(board, e, "herdr")
    agents = out["workspaces"][0]["tabs"][0]["agents"]
    assert agents[0]["status"] == "idle"
    assert agents[1]["status"] == "blocked"


def test_al_stop_recibe_el_texto_crudo(agg):
    a, _ = agg
    visto = []
    a.al_stop.append(lambda pane, texto: visto.append((pane, texto)))
    crudo = "y" * 900
    a.recibir(ev("Stop", last_assistant_message=crudo), "w1:p1")
    assert visto == [("w1:p1", crudo)]
    assert len(a.estado_de("w1:p1").ultimo_mensaje) == 500


def test_al_stop_que_falla_no_frena_el_stop(agg, caplog):
    a, _ = agg

    def roto(pane, texto):
        raise RuntimeError("boom")

    visto = []
    a.al_stop.extend([roto, lambda p, t: visto.append(t)])
    a.recibir(ev("Stop", last_assistant_message="listo"), "w1:p1")
    assert a.estado_de("w1:p1").estado == "done"
    assert visto == ["listo"]
    assert "boom" in caplog.text or "al_stop" in caplog.text



def test_post_tool_use_failure_limpia_pendientes_y_sigue_working(agg):
    a, r = agg
    a.recibir(ev("PreToolUse", "t1"), "w1:p1")
    assert a._pre_pendientes["w1:p1"] == {"t1"}
    r.t += 1
    a.recibir(ev("PostToolUseFailure", "t1", error="Exit code 1"), "w1:p1")
    assert a._pre_pendientes["w1:p1"] == set()
    assert a.estado_de("w1:p1").estado == "working"
