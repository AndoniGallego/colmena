import json

import pytest

from orquestador.ganchos import colmena_gancho as g

SID = "8d889181-aaaa-bbbb-cccc-000000000001"


def base(evento, **extra):
    return {"hook_event_name": evento, "session_id": SID, "cwd": "/tmp/p", "transcript_path": "/tmp/t.jsonl", **extra}


@pytest.mark.parametrize("tope", [4096])
@pytest.mark.parametrize("delta,recortado", [(-1, False), (0, False), (1, True)])
def test_recorte_tool_input_limites(tope, delta, recortado):
    cmd = "x" * (tope - len(json.dumps({"command": ""})) + delta)
    m = g.armar_mensaje(base("PreToolUse", tool_name="Bash", tool_use_id="t1", tool_input={"command": cmd}), {})
    assert m["datos"].get("recortado", False) is recortado
    ti = m["datos"]["tool_input"]
    if isinstance(ti, str):
        assert len(ti.encode()) <= tope
    else:
        assert len(json.dumps(ti, ensure_ascii=False).encode()) <= tope


def test_recorte_multibyte_no_rompe():
    texto, cortado = g.recortar_texto("ñ" * 5000, 8191)
    assert cortado and len(texto.encode()) <= 8191
    texto.encode("utf-8")  # no lanza


def test_permission_request_hasta_48k_y_mensaje_final_8k():
    m = g.armar_mensaje(base("PermissionRequest", tool_name="Bash", tool_use_id="t1",
                             tool_input={"command": "a" * 40000}, permission_suggestions=[{"type": "setMode"}]), {})
    assert "recortado" not in m["datos"] and "permission_suggestions" not in m["datos"]
    s = g.armar_mensaje(base("Stop", last_assistant_message="z" * 9000), {})
    assert len(s["datos"]["last_assistant_message"].encode()) <= 8192 and s["datos"]["recortado"] is True
    assert len(_linea(m)) <= g.MAX_MENSAJE


def test_user_prompt_submit_no_manda_el_prompt():
    m = g.armar_mensaje(base("UserPromptSubmit", prompt="secreto"), {})
    assert "secreto" not in json.dumps(m)


@pytest.mark.parametrize("env,manda", [
    ({"COLMENA_SESION": "g1:p1", "COLMENA_GANCHO_ORIGEN": "global"}, False),
    ({"COLMENA_SESION": "g1:p1", "COLMENA_GANCHO_ORIGEN": "settings"}, True),
    ({"COLMENA_GANCHO_ORIGEN": "global"}, True),
    ({"COLMENA_GANCHO_ORIGEN": "settings"}, True),
])
def test_dedup_global_settings(env, manda):
    assert (g.armar_mensaje(base("Stop"), env) is not None) is manda


def test_identificacion_orden():
    herdr = {"HERDR_PANE_ID": "w1:p1", "HERDR_TAB_ID": "w1:t1", "HERDR_WORKSPACE_ID": "w1"}
    assert g.ids_de(base("Stop"), {"COLMENA_SESION": "g1:p1", **herdr}) == {
        "colmena": "g1:p1", "herdr_pane": None, "herdr_tab": None, "herdr_workspace": None, "claude": SID}
    assert g.ids_de(base("Stop"), herdr) == {
        "colmena": None, "herdr_pane": "w1:p1", "herdr_tab": "w1:t1", "herdr_workspace": "w1", "claude": SID}
    assert g.ids_de({}, {}) == {"colmena": None, "herdr_pane": None, "herdr_tab": None, "herdr_workspace": None, "claude": None}


def test_evento_desconocido_none_y_espera():
    assert g.armar_mensaje(base("Raro"), {}) is None
    pr = g.armar_mensaje(base("PermissionRequest", tool_name="Bash", tool_use_id="t1", tool_input={}), {})
    ask = g.armar_mensaje(base("PermissionRequest", tool_name="AskUserQuestion", tool_use_id="t2", tool_input={}), {})
    plan = g.armar_mensaje(base("PermissionRequest", tool_name="ExitPlanMode", tool_use_id="t3", tool_input={}), {})
    assert g.espera_respuesta(pr) and not g.espera_respuesta(ask)
    assert g.espera_respuesta(plan)
    assert not g.espera_respuesta(g.armar_mensaje(base("PreToolUse", tool_name="Bash", tool_use_id="t1"), {}))


def test_ruta_socket():
    assert g.ruta_socket({"XDG_RUNTIME_DIR": "/run/user/1000"}) == "/run/user/1000/colmena/ganchos.sock"
    assert g.ruta_socket({}) is None and g.ruta_socket({"XDG_RUNTIME_DIR": ""}) is None


def _linea(m):
    return (json.dumps(m, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def test_encajar_en_max_rerecorte_caracteres_json():
    """tool_input ~48 KB de comillas y backslashes: el JSON serializado casi duplica tamaño."""
    payload = ('\\"' * 24000)[:48000]
    m = g.armar_mensaje(
        base("PermissionRequest", tool_name="Bash", tool_use_id="t1", tool_input={"command": payload}),
        {},
    )
    assert m is not None
    assert len(_linea(m)) <= g.MAX_MENSAJE
    assert m["datos"].get("recortado") is True


def test_stop_cwd_enorme_respeta_max_mensaje():
    m = g.armar_mensaje(base("Stop", cwd="a" * 100_000), {})
    assert m is not None
    assert len(_linea(m)) <= g.MAX_MENSAJE


def test_transcript_path_enorme_respeta_max_mensaje():
    m = g.armar_mensaje(base("Stop", transcript_path="p" * 100_000), {})
    assert m is not None
    assert len(_linea(m)) <= g.MAX_MENSAJE


def test_notification_message_enorme_respeta_max_mensaje():
    m = g.armar_mensaje(
        base("Notification", notification_type="info", message="m" * 100_000),
        {},
    )
    assert m is not None
    assert len(_linea(m)) <= g.MAX_MENSAJE


def test_session_start_source_enorme_respeta_max_mensaje():
    m = g.armar_mensaje(base("SessionStart", source="s" * 100_000), {})
    assert m is not None
    assert len(_linea(m)) <= g.MAX_MENSAJE


def test_armar_mensaje_none_si_ids_no_entran_en_max():
    env = {
        "HERDR_PANE_ID": "w" * 80_000,
        "HERDR_TAB_ID": "t" * 80_000,
        "HERDR_WORKSPACE_ID": "x" * 80_000,
    }
    assert g.armar_mensaje(base("Stop"), env) is None


def test_armar_mensaje_none_si_campo_fijo_no_entra_en_max():
    m = g.armar_mensaje(
        base(
            "PermissionRequest",
            tool_name="Bash",
            tool_use_id="u" * 100_000,
            tool_input={"command": "ls"},
        ),
        {},
    )
    assert m is None


def test_permission_request_recorta_cwd_antes_que_tool_input():
    m = g.armar_mensaje(
        base(
            "PermissionRequest",
            tool_name="Bash",
            tool_use_id="t1",
            tool_input={"command": "ls"},
            cwd="c" * 100_000,
        ),
        {},
    )
    assert m is not None
    assert m["datos"]["tool_input"] == {"command": "ls"}
    assert len(_linea(m)) <= g.MAX_MENSAJE


def test_post_tool_use_failure_viaja_con_error_recortado_e_interrupcion():
    m = g.armar_mensaje(base("PostToolUseFailure", tool_name="Bash", tool_use_id="t1",
                             tool_input={"command": "pytest"}, error="Exit code 1\n" + "x" * 2000,
                             is_interrupt=False, duration_ms=5), {})
    assert m is not None and m["evento"] == "PostToolUseFailure"
    d = m["datos"]
    assert d["tool_name"] == "Bash" and d["tool_use_id"] == "t1" and d["tool_input"] == {"command": "pytest"}
    assert d["error"].startswith("Exit code 1") and len(d["error"].encode()) <= 512
    assert d["is_interrupt"] is False
    assert d["recortado"] is True
