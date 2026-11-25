import json
from datetime import datetime, timedelta, timezone

from orquestador.trabas import detectar

BASE = datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc)


def iso(minutos=0.0):
    return (BASE + timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def ep(minutos=0.0):
    return (BASE + timedelta(minutes=minutos)).timestamp()


def prompt(texto="hacé algo", m=0.0):
    return json.dumps({"type": "user", "timestamp": iso(m), "message": {"role": "user", "content": texto}})


def tu(name, inp, tid, m=0.0):
    return json.dumps({"type": "assistant", "timestamp": iso(m),
                       "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}})


def tr(tid, content="ok", is_error=False, m=0.0):
    return json.dumps({"type": "user", "timestamp": iso(m),
                       "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": content,
                                                "is_error": is_error}]}})


def llamada(name, inp, n, m=0.0, content="ok", is_error=False):
    tid = f"t{n}"
    return [tu(name, inp, tid, m), tr(tid, content, is_error, m)]


def tipos(out):
    return sorted(t.tipo for t in out)


def run(lineas, m, **kw):
    kw.setdefault("mtime", ep(m))
    return detectar(lineas, ep(m), **kw)


# ---- deben saltar ----

def test_cuatro_grep_identicos_saltan():
    ls = [prompt()]
    for i in range(4):
        ls += llamada("Grep", {"pattern": "foo", "path": "src"}, i, m=i * 0.1)
    out = run(ls, 1)
    assert tipos(out) == ["repetida"]
    assert "Grep" in out[0].detalle


def test_descripcion_distinta_no_evita_la_repeticion():
    ls = [prompt()]
    for i in range(4):
        ls += llamada("Bash", {"command": "ls -la", "description": f"listar {i}"}, i, m=i * 0.1)
    assert tipos(run(ls, 1)) == ["repetida"]


def test_cuatro_fallas_de_pytest_alternadas_con_edit_saltan():
    ls = [prompt()]
    n = 0
    for i in range(4):
        ls += llamada("Bash", {"command": "cd /repo && uv  run pytest tests/x.py"}, n, m=i,
                      content="Exit code 1\nFAILED", is_error=True)
        n += 1
        ls += llamada("Edit", {"file_path": "/repo/a.py", "old_string": f"a{i}", "new_string": "b"}, n, m=i)
        n += 1
    out = run(ls, 5)
    assert "fallando" in tipos(out)
    f = [t for t in out if t.tipo == "fallando"][0]
    assert "pytest" in f.detalle


def test_falla_por_exit_code_en_texto_sin_is_error():
    ls = [prompt()]
    for i in range(4):
        ls += llamada("Bash", {"command": "make"}, i, m=i, content="Exit code 2\nboom")
    assert "fallando" in tipos(run(ls, 5))


def test_bash_pendiente_mas_que_su_timeout_salta():
    ls = [prompt(), tu("Bash", {"command": "sleep 999", "timeout": 60000}, "tx", m=0)]
    out = run(ls, 4)
    assert tipos(out) == ["colgada"]
    assert out[0].desde == ep(0)


def test_transcript_quieto_once_minutos_en_working_salta():
    ls = [prompt(), *llamada("Read", {"file_path": "/a"}, 1, m=0)]
    out = detectar(ls, ep(11), fondo=[], subagentes_activos=False, mtime=ep(0))
    assert tipos(out) == ["quieta"]


def test_mcp_pendiente_diez_minutos_salta():
    ls = [prompt(), tu("mcp__x__y", {"a": 1}, "tm", m=0)]
    assert tipos(run(ls, 11)) == ["colgada"]


def test_agent_en_primer_plano_sin_subagente_activo_salta():
    ls = [prompt(), tu("Agent", {"prompt": "x", "description": "d"}, "ta", m=0)]
    assert tipos(run(ls, 11, subagentes_activos=False)) == ["colgada"]


# ---- no deben saltar ----

def test_build_con_timeout_largo_a_los_ocho_minutos_no_salta():
    ls = [prompt(), tu("Bash", {"command": "npm run build", "timeout": 600000}, "tb", m=0)]
    assert run(ls, 8) == []


def test_bash_en_segundo_plano_y_monitor_esperando_no_salta():
    ls = [prompt(),
          tu("Bash", {"command": "make watch", "run_in_background": True}, "tb", m=0),
          tr("tb", "Background command started", m=0),
          tu("Monitor", {"command": "tail", "timeout_ms": 3600000}, "tm", m=1)]
    fondo = [{"id": "tb", "tipo": "comando", "texto": "x", "desde": ep(0)}]
    assert run(ls, 15, fondo=fondo, mtime=ep(1)) == []


def test_sesion_con_fondo_y_transcript_quieto_no_salta():
    ls = [prompt(), *llamada("Bash", {"command": "x", "run_in_background": True}, 1, m=0)]
    fondo = [{"id": "t1", "tipo": "comando", "texto": "x", "desde": ep(0)}]
    assert run(ls, 20, fondo=fondo, mtime=ep(0)) == []


def test_agent_en_primer_plano_con_subagente_escribiendo_no_salta():
    ls = [prompt(), tu("Agent", {"prompt": "x"}, "ta", m=0)]
    assert run(ls, 30, subagentes_activos=True, mtime=ep(0)) == []


def test_cuatro_bashoutput_seguidos_no_salta():
    ls = [prompt()]
    for i in range(4):
        ls += llamada("BashOutput", {"bash_id": "b1"}, i, m=i * 0.1)
    assert run(ls, 1) == []


def test_falla_edita_falla_pasa_no_salta():
    ls = [prompt()]
    ls += llamada("Bash", {"command": "pytest"}, 1, m=0, content="Exit code 1", is_error=True)
    ls += llamada("Edit", {"file_path": "/a", "old_string": "a", "new_string": "b"}, 2, m=0)
    ls += llamada("Bash", {"command": "pytest"}, 3, m=0, content="Exit code 1", is_error=True)
    ls += llamada("Edit", {"file_path": "/a", "old_string": "b", "new_string": "c"}, 4, m=0)
    ls += llamada("Bash", {"command": "pytest"}, 5, m=0, content="2 passed")
    ls += llamada("Bash", {"command": "pytest"}, 6, m=0, content="Exit code 1", is_error=True)
    assert "fallando" not in tipos(run(ls, 1))


def test_read_repetido_con_edit_en_el_medio_no_salta():
    ls = [prompt()]
    n = 0
    for i in range(4):
        ls += llamada("Read", {"file_path": "/a.py"}, n, m=i * 0.1)
        n += 1
        ls += llamada("Edit", {"file_path": "/a.py", "old_string": f"{i}", "new_string": "z"}, n, m=i * 0.1)
        n += 1
    assert "repetida" not in tipos(run(ls, 1))


def test_turno_anterior_no_cuenta():
    ls = [prompt("viejo")]
    for i in range(5):
        ls += llamada("Grep", {"pattern": "foo"}, i, m=0)
    ls.append(prompt("nuevo", m=0.5))
    assert run(ls, 1) == []


def test_umbrales_se_leen_del_toml_y_descartan_lo_invalido():
    from orquestador.config import Config
    from orquestador.trabas import Umbrales
    u = Umbrales.de_dict(Config(trabas={"repetidas": 6, "quieta": 900, "fallas": "x", "ventana": -1}).trabas)
    assert (u.repetidas, u.quieta, u.fallas, u.ventana) == (6, 900.0, 4, 12)
    ls = [prompt()]
    for i in range(4):
        ls += llamada("Grep", {"pattern": "foo"}, i, m=0)
    assert run(ls, 1, umbrales=u) == []
