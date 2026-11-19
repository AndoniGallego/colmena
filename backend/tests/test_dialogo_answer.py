import copy
import json
import logging

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, SID, make_snapshot
from dialogos_support import meta, multi_transcript_line, screen, tool_use, transcript_line
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.config import Config, hash_pin
from orquestador.digest import DigestService
from orquestador.dialogo import ALLOWED_KEYS
from orquestador.enchufe import FakeTerminales
from orquestador.enchufe.base import TECLAS
from orquestador.enchufe.herdr import tablero_de_snapshot
from orquestador.state import StateStore

CWD = "/tmp/claude-1000/-home-usuario-proyectos-acme/8d889181-7ef8-40d5-83bd-3dae622a4c82/scratchpad/fase0/proj"
PANE = "w1:p1"


class Scripted(FakeTerminales):
    """Pantalla viva: cada teclas/escribir aplica el siguiente paso del guion."""

    def __init__(self, projects):
        super().__init__(tablero_de_snapshot(make_snapshot(), 0))
        self.projects = projects
        self._snap = make_snapshot()
        self.screen = ""
        self.script = []
        self.pending_ids = []

    @property
    def current(self):
        return self._snap

    @property
    def sent(self):
        out = []
        for c in self.calls:
            if c[0] == "teclas":
                out.append(("pane", "send-keys", c[1], *c[2]))
            elif c[0] == "escribir":
                out.append(("pane", "send-text", c[1], c[2]))
        return out

    def set_dialog(self, screen_name, transcript_name, seq):
        self.screen = screen(screen_name)
        self.pantallas[PANE] = self.screen
        self.seq = seq
        path = self.projects / "-proj" / f"{SID}.jsonl"
        line = transcript_name if isinstance(transcript_name, dict) else transcript_line(transcript_name)
        path.write_text(json.dumps(line) + "\n", encoding="utf-8")
        self.tool_id = line["message"]["content"][0]["id"]
        agent = self.current["agents"][0]
        agent.update(agent_status="blocked", state_change_seq=seq, cwd=CWD)

    def _append(self, line):
        with open(self.projects / "-proj" / f"{SID}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")

    def _apply(self, step):
        agent = self.current["agents"][0]
        self.screen = step.get("screen", self.screen)
        self.pantallas[PANE] = self.screen
        agent["agent_status"] = step.get("status", agent.get("agent_status"))
        agent["state_change_seq"] = step.get("seq", agent.get("state_change_seq"))
        if step.get("resolve"):
            self._append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": self.tool_id,
                                                                    "content": "ok"}]}})
        if step.get("transcript"):
            self._append(transcript_line(step["transcript"]))

    async def tablero(self):
        self.tablero_actual = tablero_de_snapshot(copy.deepcopy(self._snap), self.tablero_actual.revision)
        return await super().tablero()

    async def teclas(self, sesion_id, teclas):
        await super().teclas(sesion_id, teclas)
        if self.script:
            self._apply(self.script.pop(0))

    async def escribir(self, sesion_id, texto):
        await super().escribir(sesion_id, texto)
        if self.script:
            self._apply(self.script.pop(0))


@pytest.fixture
def herd(projects):
    return Scripted(projects)


@pytest.fixture
def app(cfg, tmp_path, herd, handoffs):
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(herd, digests)
    hub.self_pane_id = "w2:p9"

    async def no_sleep(_):
        return None

    return create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests,
                      dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads",
                      dialog_sleep=no_sleep, enchufe=herd)


@pytest.fixture
def api(app):
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def current(api):
    return api.get(f"/api/sessions/{SID}/dialog").json()


def body(api, hu, **over):
    data = {"id": "id-" + str(len(api.cookies)) + "x" * 6, "session_id": SID, "pane_id": PANE, "huella": hu,
            "tipo": "permiso", "permiso": "si"}
    data.update(over)
    return data


def post(api, hu, **over):
    return api.post("/api/sessions/dialog/answer", json=body(api, hu, **over))


def keys(herd):
    return [c[2] for c in herd.calls_of("teclas")]


def test_get_dialog_none_when_not_blocked(api, herd):
    herd.current["agents"][0]["agent_status"] = "idle"
    assert current(api) == {"tipo": "ninguno"}


def test_get_dialog_permiso(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    d = current(api)
    assert d["tipo"] == "permiso" and d["permiso"]["herramienta"] == "Bash"
    assert d["permiso"]["opciones"] == ["si", "si_auto", "no"] and d["huella"] and d["pane_id"] == PANE


def test_get_dialog_unknown_shows_screen(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    herd.screen = "algo raro\n"
    herd.pantallas[PANE] = herd.screen
    d = current(api)
    assert d["tipo"] == "desconocido" and "algo raro" in d["pantalla"]


def test_si_sends_digit_and_confirms(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    herd.script = [{"screen": screen("bash-1-after-digit1"), "status": "idle", "seq": 15, "resolve": True}]
    r = post(api, current(api)["huella"], id="ok-id-0001")
    assert r.status_code == 200 and r.json() == {"ok": True, "interrumpida": False}
    assert keys(herd) == [("1",)]
    assert any(c[0] == "esperar" for c in herd.calls)


def test_no_interrupts(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    herd.script = [{"status": "idle", "seq": 15, "resolve": True}]
    r = post(api, current(api)["huella"], id="ok-id-0002", permiso="no")
    assert r.json() == {"ok": True, "interrumpida": True} and keys(herd) == [("4",)]


def test_si_siempre_pin_rules(api, herd, caplog):
    herd.set_dialog("bash-2-dialog", "bash-2-dialog", 22)
    hu = current(api)["huella"]
    assert post(api, hu, id="pin-0000-1", permiso="si_siempre").status_code == 400
    assert post(api, hu, id="pin-0000-2", permiso="si", pin=PIN).status_code == 400
    with caplog.at_level(logging.DEBUG):
        assert post(api, hu, id="pin-0000-3", permiso="si_siempre", pin="00000000").status_code == 401
        herd.script = [{"status": "idle", "seq": 23, "resolve": True}]
        r = post(api, hu, id="pin-0000-4", permiso="si_siempre", pin=PIN)
    assert r.status_code == 200 and keys(herd) == [("2",)]
    assert PIN not in caplog.text and "00000000" not in caplog.text
    assert PIN not in json.dumps(api.app.state.dialogos.state.respuestas())


def test_wrong_pin_counts_and_locks(api, herd):
    herd.set_dialog("bash-2-dialog", "bash-2-dialog", 22)
    hu = current(api)["huella"]
    codes = [post(api, hu, id=f"bad-pin-{i:02d}", permiso="si_siempre", pin="00000000").status_code for i in range(8)]
    assert 401 in codes and codes[-1] == 429
    r = post(api, hu, id="bad-pin-99", permiso="si_siempre", pin=PIN)
    assert r.status_code == 429 and r.headers.get("retry-after")
    assert herd.sent == []


def test_si_siempre_unavailable_in_directory_variant(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    r = post(api, current(api)["huella"], id="dir-0001", permiso="si_siempre", pin=PIN)
    assert r.status_code == 409 and herd.sent == []


def test_long_command_incomplete_blocks_yes_but_not_no(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    d = api.app.state.dialogos
    real = d._inspect

    async def incomplete(agent):
        dialogo, hu, scr = await real(agent)
        dialogo.completo = False
        return dialogo, hu, scr

    d._inspect = incomplete
    hu = current(api)["huella"]
    assert post(api, hu, id="long-0001").status_code == 409 and herd.sent == []


def test_still_blocked_same_tool_is_502(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    r = post(api, current(api)["huella"], id="same-0001")
    assert r.status_code == 502 and "No se confirmó" in r.json()["detail"]
    assert len(keys(herd)) == 1


def test_still_blocked_other_tool_is_ok(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    herd.script = [{"screen": screen("bash-3-dialog"), "seq": 15, "resolve": True, "transcript": "bash-3-dialog"}]
    assert post(api, current(api)["huella"], id="next-0001").status_code == 200


def test_stale_fingerprint_not_blocked_unknown(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    hu = current(api)["huella"]
    herd.current["agents"][0]["state_change_seq"] = 99
    r = post(api, hu, id="stale-001")
    assert r.status_code == 409 and r.json()["detail"] == "El diálogo cambió"
    herd.current["agents"][0]["agent_status"] = "idle"
    assert post(api, hu, id="stale-002").status_code == 409
    herd.current["agents"][0]["agent_status"] = "blocked"
    herd.screen = "raro\n"
    herd.pantallas[PANE] = herd.screen
    assert post(api, hu, id="stale-003").status_code == 409
    assert herd.sent == []


def test_idempotent_id(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    hu = current(api)["huella"]
    herd.script = [{"status": "idle", "seq": 15, "resolve": True}]
    assert post(api, hu, id="dup-00001").status_code == 200
    r = post(api, hu, id="dup-00001")
    assert r.status_code == 409 and "Ya se respondió" in r.json()["detail"] and len(herd.sent) == 1


def test_schema_violations_are_422_without_echo(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    hu = current(api)["huella"]
    r = post(api, hu, id="schema-001", extra_field=1, pin="secreto-123")
    assert r.status_code == 422 and "secreto-123" not in r.text
    assert post(api, hu, id="schema-002", permiso="modo_auto").status_code == 422
    assert post(api, hu, id="schema-003", origen="x").status_code == 422


def test_protected_pane_rejected(api, herd):
    r = post(api, "x", id="prot-0001", pane_id="w2:p9")
    assert r.status_code == 400


def test_requires_auth_and_csrf(app, herd):
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.get(f"/api/sessions/{SID}/dialog").status_code == 401
        assert c.post("/api/sessions/dialog/answer", json={}).status_code in (401, 403)


def test_rate_limit(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    last = None
    for i in range(22):
        last = post(api, "x" * 10, id=f"rate-{i:04d}x")
    assert last.status_code == 429


def question(api, herd):
    herd.set_dialog("auq-1-dialog", "auq-2-dialog", 40)
    return current(api)


def test_question_label(api, herd):
    d = question(api, herd)
    assert d["tipo"] == "pregunta"
    herd.script = [{"status": "idle", "seq": 41, "resolve": True}]
    r = post(api, d["huella"], id="q-label-01", tipo="pregunta", permiso=None, respuestas=[{"opciones": [1]}])
    assert r.status_code == 200 and keys(herd) == [("2",)]


def test_question_other_flow(api, herd):
    herd.set_dialog("auq-2-dialog", "auq-3-dialog", 40)
    d = current(api)
    herd.script = [{"screen": screen("auq-2-after-digit4")}, {"screen": screen("auq-2-after-text")},
                   {"screen": screen("auq-2-after-enter"), "status": "idle", "seq": 42, "resolve": True}]
    r = post(api, d["huella"], id="q-other-01", tipo="pregunta", permiso=None, respuestas=[{"otro": "Frutilla"}])
    assert r.status_code == 200
    assert herd.calls_of("escribir") == [("escribir", PANE, "Frutilla")]
    assert keys(herd) == [("4",), ("enter",)]


def test_question_other_half_done_stops(api, herd):
    herd.set_dialog("auq-2-dialog", "auq-3-dialog", 40)
    d = current(api)
    herd.script = [{"screen": screen("auq-2-dialog")}]
    r = post(api, d["huella"], id="q-half-001", tipo="pregunta", permiso=None, respuestas=[{"otro": "Frutilla"}])
    assert r.status_code == 502 and "medio" in r.json()["detail"]
    assert herd.sent == [("pane", "send-keys", PANE, "4")]


def test_question_other_seq_changed_stops(api, herd):
    herd.set_dialog("auq-2-dialog", "auq-3-dialog", 40)
    d = current(api)
    herd.script = [{"screen": screen("auq-2-after-digit4"), "seq": 41}]
    r = post(api, d["huella"], id="q-seq-0001", tipo="pregunta", permiso=None, respuestas=[{"otro": "Frutilla"}])
    assert r.status_code == 502 and len(herd.sent) == 1


@pytest.mark.parametrize("resp", [
    [{"opciones": [3]}], [{"opciones": [-1]}], [{"opciones": [0, 1]}], [{"opciones": []}],
    [{"opciones": [0], "otro": "x"}], [{"otro": "a\nb"}], [{"otro": "a\x1bb"}], [{"otro": "x" * 501}],
    [{"otro": ""}], [{"opciones": [0]}, {"opciones": [0]}],
])
def test_question_shape_errors(api, herd, resp):
    d = question(api, herd)
    r = post(api, d["huella"], id="shape-0001", tipo="pregunta", permiso=None, respuestas=resp)
    assert r.status_code == 400 and herd.sent == []


def test_leading_dash_gets_space(api, herd):
    herd.set_dialog("auq-2-dialog", "auq-3-dialog", 40)
    d = current(api)
    herd.script = [{"screen": screen("auq-2-after-digit4")}]
    post(api, d["huella"], id="dash-00001", tipo="pregunta", permiso=None, respuestas=[{"otro": "-rf"}])
    assert herd.sent[1] == ("pane", "send-text", PANE, " -rf")


def test_never_a_non_whitelisted_key(api, herd):
    herd.set_dialog("bash-2-dialog", "bash-2-dialog", 22)
    hu = current(api)["huella"]
    herd.script = [{"status": "idle", "seq": 23, "resolve": True}]
    post(api, hu, id="keys-0001", permiso="si_siempre", pin=PIN)
    for call in herd.calls_of("teclas"):
        assert all(k in ALLOWED_KEYS for k in call[2]) and len(call[2]) == 1
    assert "3" not in [k[0] for k in keys(herd)]


def test_mode_change_never_sent_even_if_asked(api, herd):
    herd.set_dialog("bash-2-dialog", "bash-2-dialog", 22)
    hu = current(api)["huella"]
    r = post(api, hu, id="mode-00001", permiso="modo_auto")
    assert r.status_code == 422 and herd.sent == []


def test_answer_recorded_in_state_without_pin(api, herd, tmp_path):
    herd.set_dialog("bash-2-dialog", "bash-2-dialog", 22)
    herd.script = [{"status": "idle", "seq": 23, "resolve": True}]
    post(api, current(api)["huella"], id="rec-00001", permiso="si_siempre", pin=PIN)
    text = json.dumps(api.app.state.dialogos.state.respuestas())
    assert "rec-00001" in text and PIN not in text


def test_lock_is_shared_with_pane_locks(api, herd):
    assert api.app.state.dialogos.locks is api.app.state.locks


def test_no_second_key_after_failed_attempt_even_with_new_id(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    hu = current(api)["huella"]
    assert post(api, hu, id="first-0001").status_code == 502
    r = post(api, hu, id="second-001")
    assert r.status_code == 409 and "Ya se mandó" in r.json()["detail"]
    assert len(keys(herd)) == 1


def test_sent_keys_survive_restart(api, herd, tmp_path):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    assert post(api, current(api)["huella"], id="first-0002").status_code == 502
    assert StateStore(tmp_path).teclas_enviadas(PANE, tool_use("bash-1-dialog")["id"])


def test_answer_requires_json_content_type(api, herd):
    herd.set_dialog("bash-1-dialog", "bash-1-dialog", 14)
    data = json.dumps(body(api, current(api)["huella"], id="ctype-0001"))
    r = api.post("/api/sessions/dialog/answer", content=data, headers={"Content-Type": "text/plain"})
    assert r.status_code == 415 and herd.sent == []


def test_get_dialog_offers_mode_options(api, herd):
    herd.set_dialog("edit-1-dialog", "edit-1-dialog", 60)
    assert current(api)["permiso"]["opciones"] == ["si", "si_ediciones", "no"]
    herd.set_dialog("bash-2-dialog", "bash-2-dialog", 22)
    d = current(api)["permiso"]
    assert d["opciones"] == ["si", "si_siempre", "si_auto", "no"] and d["mas_en_terminal"] is False


def test_si_ediciones_needs_pin_and_sends_the_digit_from_the_screen(api, herd, caplog):
    herd.set_dialog("edit-1-dialog", "edit-1-dialog", 60)
    hu = current(api)["huella"]
    assert post(api, hu, id="mode-0001", permiso="si_ediciones").status_code == 400
    with caplog.at_level(logging.DEBUG):
        assert post(api, hu, id="mode-0002", permiso="si_ediciones", pin="00000000").status_code == 401
    assert herd.sent == [] and "00000000" not in caplog.text
    herd.script = [{"screen": screen("edit-2-after-digit2"), "status": "idle", "seq": 76, "resolve": True}]
    r = post(api, hu, id="mode-0003", permiso="si_ediciones", pin=PIN)
    assert r.status_code == 200 and r.json() == {"ok": True, "interrumpida": False}
    assert keys(herd) == [("2",)] and any(c[0] == "esperar" for c in herd.calls)
    assert PIN not in json.dumps(api.app.state.dialogos.state.respuestas())


def test_si_auto_sends_the_auto_mode_digit(api, herd):
    herd.set_dialog("bash-2-dialog", "bash-2-dialog", 22)
    hu = current(api)["huella"]
    assert post(api, hu, id="auto-0001", permiso="si_auto").status_code == 400
    herd.script = [{"status": "idle", "seq": 23, "resolve": True}]
    assert post(api, hu, id="auto-0002", permiso="si_auto", pin=PIN).status_code == 200
    assert keys(herd) == [("3",)]


def test_wrong_pin_on_mode_option_counts_in_the_limiter(api, herd):
    herd.set_dialog("bash-2-dialog", "bash-2-dialog", 22)
    hu = current(api)["huella"]
    codes = [post(api, hu, id=f"mpin-{i:04d}x", permiso="si_auto", pin="00000000").status_code for i in range(8)]
    assert 401 in codes and codes[-1] == 429 and herd.sent == []


def test_mode_option_absent_from_the_dialog_is_refused(api, herd):
    herd.set_dialog("edit-1-dialog", "edit-1-dialog", 60)
    r = post(api, current(api)["huella"], id="absent-001", permiso="si_auto", pin=PIN)
    assert r.status_code == 409 and herd.sent == []
    herd.set_dialog("bash-2-dialog", "bash-2-dialog", 22)
    r = post(api, current(api)["huella"], id="absent-002", permiso="si_ediciones", pin=PIN)
    assert r.status_code == 409 and herd.sent == []


def test_mode_option_refused_when_command_is_incomplete(api, herd):
    herd.set_dialog("bash-2-dialog", "bash-2-dialog", 22)
    d = api.app.state.dialogos
    real = d._inspect

    async def incomplete(agent):
        dialogo, hu, scr = await real(agent)
        dialogo.completo = False
        return dialogo, hu, scr

    d._inspect = incomplete
    assert post(api, current(api)["huella"], id="inc-mode-01", permiso="si_auto", pin=PIN).status_code == 409
    assert herd.sent == []


def multi_dialog(api, herd, screen_name="auq-3-dialog"):
    herd.set_dialog(screen_name, multi_transcript_line(), 44)
    return current(api)


def answer_q(api, hu, respuestas, ident):
    return post(api, hu, id=ident, tipo="pregunta", permiso=None, respuestas=respuestas)


def test_multi_select_sends_digits_right_then_submit(api, herd):
    d = multi_dialog(api, herd)
    assert d["tipo"] == "pregunta" and d["pregunta"]["preguntas"][0]["multi"] is True
    herd.script = [{"screen": screen("auq-3-after-digit3")}, {"screen": screen("auq-3-after-right")},
                   {"screen": screen("auq-3-after-submit1"), "status": "idle", "seq": 46, "resolve": True}]
    r = answer_q(api, d["huella"], [{"opciones": [2, 0]}], "multi-0001")
    assert r.status_code == 200 and r.json() == {"ok": True, "interrumpida": False}
    assert keys(herd) == [("1", "3"), ("derecha",), ("1",)]
    assert [e["resumen"] for e in api.app.state.dialogos.state.respuestas()] == ["Pregunta: Python, Go"]


def test_tecla_derecha_llega_al_enchufe_con_nombre_neutral(api, herd):
    d = multi_dialog(api, herd)
    herd.script = [{"screen": screen("auq-3-after-digit3")}, {"screen": screen("auq-4-after-enter-submit")}]
    answer_q(api, d["huella"], [{"opciones": [0, 2]}], "neutral-001")
    assert keys(herd) == [("1", "3"), ("derecha",)]
    assert all(c[0] != "teclas" or set(c[2]) <= TECLAS for c in herd.calls)


def test_two_questions_advance_with_the_digit_then_submit(api, herd):
    herd.set_dialog("auq-5-dialog", "auq-5-dialog", 51)
    d = current(api)
    assert len(d["pregunta"]["preguntas"]) == 2
    herd.script = [{"screen": screen("auq-5-after-q1-digit2")}, {"screen": screen("auq-5-review")},
                   {"screen": screen("auq-5-after-submit"), "status": "idle", "seq": 53, "resolve": True}]
    r = answer_q(api, d["huella"], [{"opciones": [1]}, {"opciones": [1]}], "two-q-0001")
    assert r.status_code == 200 and keys(herd) == [("2",), ("2",), ("1",)]


def test_review_that_does_not_match_stops_before_the_submit(api, herd):
    d = multi_dialog(api, herd)
    herd.script = [{"screen": screen("auq-3-after-digit3")}, {"screen": screen("auq-4-after-enter-submit")}]
    r = answer_q(api, d["huella"], [{"opciones": [0, 2]}], "review-0001")
    assert r.status_code == 502 and "medio" in r.json()["detail"]
    assert keys(herd) == [("1", "3"), ("derecha",)]


def test_wrong_boxes_stop_before_right(api, herd):
    d = multi_dialog(api, herd)
    herd.script = [{"screen": screen("auq-3-after-digit1")}]
    r = answer_q(api, d["huella"], [{"opciones": [0, 2]}], "boxes-0001")
    assert r.status_code == 502 and keys(herd) == [("1", "3")]


def test_state_change_between_steps_stops(api, herd):
    d = multi_dialog(api, herd)
    herd.script = [{"screen": screen("auq-3-after-digit3"), "seq": 45}]
    r = answer_q(api, d["huella"], [{"opciones": [0, 2]}], "seq-00001")
    assert r.status_code == 502 and len(herd.sent) == 1


def test_second_question_screen_that_does_not_show_stops(api, herd):
    herd.set_dialog("auq-5-dialog", "auq-5-dialog", 51)
    d = current(api)
    herd.script = [{"screen": screen("auq-5-dialog")}]
    r = answer_q(api, d["huella"], [{"opciones": [1]}, {"opciones": [1]}], "tab-00001")
    assert r.status_code == 502 and keys(herd) == [("2",)]


def test_other_answer_is_not_offered_with_several_questions_or_multi(api, herd):
    herd.set_dialog("auq-5-dialog", "auq-5-dialog", 51)
    d = current(api)
    assert all(q["otro"] is False for q in d["pregunta"]["preguntas"])
    assert answer_q(api, d["huella"], [{"otro": "x"}, {"opciones": [0]}], "otro-00001").status_code == 400
    assert answer_q(api, d["huella"], [{"otro": "x"}], "otro-00002").status_code == 400
    d = multi_dialog(api, herd)
    assert answer_q(api, d["huella"], [{"otro": "x"}], "otro-00003").status_code == 400
    assert herd.sent == []


@pytest.mark.parametrize("resp", [
    [{"opciones": []}], [{"opciones": [0, 0]}], [{"opciones": [0, 1, 2, 3, 4]}], [{"opciones": [3]}], [{"opciones": [-1]}],
    [{"opciones": [0]}, {"opciones": [0]}], [], [{"opciones": [0], "otro": "x"}],
])
def test_multi_shape_errors(api, herd, resp):
    d = multi_dialog(api, herd)
    r = answer_q(api, d["huella"], resp, "mshape-0001")
    assert r.status_code in (400, 422) and herd.sent == []


@pytest.mark.parametrize("resp", [
    [{"opciones": [1]}], [{"opciones": [0, 1]}, {"opciones": [0]}], [{"opciones": [1]}, {"opciones": []}],
    [{"opciones": [1]}, {"opciones": [2]}], [{"opciones": [3]}, {"opciones": [0]}],
])
def test_two_question_shape_errors(api, herd, resp):
    herd.set_dialog("auq-5-dialog", "auq-5-dialog", 51)
    d = current(api)
    assert answer_q(api, d["huella"], resp, "tshape-0001").status_code == 400 and herd.sent == []


def test_multi_never_sends_forbidden_keys(api, herd):
    d = multi_dialog(api, herd)
    herd.script = [{"screen": screen("auq-3-after-digit3")}, {"screen": screen("auq-3-after-right")},
                   {"screen": screen("auq-3-after-submit1"), "status": "idle", "seq": 46, "resolve": True}]
    answer_q(api, d["huella"], [{"opciones": [0, 2]}], "keysm-0001")
    sent = [k for call in keys(herd) for k in call]
    assert set(sent) <= ALLOWED_KEYS and "2" not in sent[-1:] and all(len(a) <= 5 for a in herd.sent)
    assert not {"esc", "tab", "up", "down", "space"} & set(sent)


def _screen(tabs, question, rows, footer="Enter to select · Tab/Arrow keys to navigate · Esc to cancel"):
    bar = "─" * 110
    return f"\n{bar}\n{tabs}\n{question}\n{rows}\n{footer}\n"


def test_mixed_simple_then_multi_flow(api, herd):
    questions = [
        {"question": "¿Qué editor usás?", "header": "Editor", "multiSelect": False,
         "options": [{"label": "Vim", "description": "modal"}, {"label": "VSCode", "description": "gráfico"}]},
        {"question": "¿Qué lenguajes usás?", "header": "Lenguajes", "multiSelect": True,
         "options": [{"label": "Python", "description": "interpretado"}, {"label": "Go", "description": "compilado"}]},
    ]
    line = {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_mixed_0001",
                                                           "name": "AskUserQuestion", "input": {"questions": questions}}]}}
    rule = "─" * 110
    first = _screen("←  ☐ Editor  ☐ Lenguajes  ✔ Submit  →", "¿Qué editor usás?",
                    f"❯ 1. Vim\n     modal\n  2. VSCode\n     gráfico\n  3. Type something.\n{rule}\n  4. Chat about this")

    def multi_rows(py, go):
        return (f"❯ 1. [{py}] Python\n         interpretado\n  2. [{go}] Go\n         compilado\n  3. [ ] Type something\n"
                f"     Submit\n{rule}\n  4. Chat about this")
    tabs2 = "←  ☒ Editor  {m} Lenguajes  ✔ Submit  →"
    ask2 = "¿Qué lenguajes usás?"
    review = _screen("←  ☒ Editor  ☒ Lenguajes  ✔ Submit  →", "Review your answers",
                     " ● ¿Qué editor usás?\n   → VSCode\n ● ¿Qué lenguajes usás?\n   → Python, Go\nReady to submit your answers?\n"
                     "❯ 1. Submit answers\n  2. Cancel", footer="").replace("Review your answers\n ●", "Review your answers\n ●")
    herd.set_dialog("auq-5-dialog", line, 51)
    herd.screen = first
    herd.pantallas[PANE] = first
    d = current(api)
    assert d["tipo"] == "pregunta" and len(d["pregunta"]["preguntas"]) == 2
    herd.script = [{"screen": _screen(tabs2.format(m="☐"), ask2, multi_rows(" ", " "))},
                   {"screen": _screen(tabs2.format(m="☒"), ask2, multi_rows("✔", "✔"))},
                   {"screen": review},
                   {"screen": screen("auq-5-after-submit"), "status": "idle", "seq": 53, "resolve": True}]
    r = answer_q(api, d["huella"], [{"opciones": [1]}, {"opciones": [0, 1]}], "mixed-00001")
    assert r.status_code == 200, r.text
    assert keys(herd) == [("2",), ("1", "2"), ("derecha",), ("1",)]
