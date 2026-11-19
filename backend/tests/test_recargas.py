"""Un /reload-plugins (u otro comando local) no es una respuesta: ni sin leer, ni aviso, ni cadena, ni reorden."""
import json
from datetime import timedelta

import pytest

from conftest import SID, make_snapshot
from orquestador.board import build_board
from orquestador.digest import DigestService, fin_de_turno, parse_transcript
from orquestador.push import PushService
from orquestador.replies import ReplyTracker
from orquestador.state import StateStore
from test_push import Clock as PushClock, Recorder
from test_replies import Clock as ReplyClock

PROMPT = {"type": "user", "message": {"content": "arreglá el test"}}
RESPUESTA = {"type": "assistant", "message": {"content": [{"type": "text", "text": "Listo, quedó verde."}]}}
PREGUNTA = {"type": "assistant", "message": {"content": [{"type": "text", "text": "¿Lo mergeo?"}]}}
CAVEAT = {"type": "user", "isMeta": True, "message": {"content": "<local-command-caveat>The command below was run "
                                                                  "directly in Claude Code.</local-command-caveat>"}}
RELOAD = [CAVEAT,
          {"type": "user", "message": {"content": "<command-name>/reload-plugins</command-name>\n"
                                                  "            <command-message>reload-plugins</command-message>\n"
                                                  "            <command-args>--force</command-args>"}},
          {"type": "system", "subtype": "local_command",
           "content": "<local-command-stdout>Reloaded: 4 plugins · 109 skills</local-command-stdout>"}]
COMPACT = [{"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted"},
           {"type": "user", "isCompactSummary": True, "message": {"content": "resumen de la charla"}},
           CAVEAT,
           {"type": "user", "message": {"content": "<command-name>/compact</command-name>"}},
           {"type": "user", "message": {"content": "<local-command-stdout>Compacted</local-command-stdout>"}}]
BASH = [{"type": "user", "message": {"content": "<bash-input>git status</bash-input>"}},
        {"type": "user", "message": {"content": "<bash-stdout>nada</bash-stdout><bash-stderr></bash-stderr>"}}]
SKILL = [{"type": "user", "message": {"content": "<command-name>/odd</command-name>"}},
         {"type": "user", "isMeta": True, "message": {"content": [{"type": "text", "text": "instrucciones del skill"}]}},
         {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t", "name": "Read", "input": {}}]}},
         {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "content": "x"}]}},
         RESPUESTA]


def write(folder, lines, sid=SID):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sid}.jsonl"
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("lines,local,tail", [
    ([PROMPT, RESPUESTA], False, "claude_text"),
    ([PROMPT, RESPUESTA, *RELOAD], True, "claude_text"),
    ([PROMPT, RESPUESTA, *COMPACT], True, "claude_text"),
    ([PROMPT, RESPUESTA, *BASH], True, "claude_text"),
    ([PROMPT, RESPUESTA, *RELOAD, *SKILL], False, "claude_text"),
    ([PROMPT, RESPUESTA, *RELOAD, PROMPT], False, "user"),
    ([PROMPT, RESPUESTA, *RELOAD, PROMPT, RESPUESTA], False, "claude_text"),
])
def test_digest_detecta_turno_sin_respuesta(tmp_path, lines, local, tail):
    digest = parse_transcript(write(tmp_path, lines))
    assert (digest.local_tail, digest.tail) == (local, tail)
    assert digest.last_claude_text() == "Listo, quedó verde."
    assert all("command" not in t["text"] for t in digest.turns)


def test_fin_de_turno():
    assert fin_de_turno({"status": "working"}, {"status": "idle"})
    assert fin_de_turno({"status": "working"}, {"status": "done", "turno_local": False})
    assert not fin_de_turno({"status": "working"}, {"status": "done", "turno_local": True})
    assert not fin_de_turno(None, {"status": "done"})
    assert not fin_de_turno({"status": "idle"}, {"status": "done"})


def agent_of(projects, status):
    return build_board(make_snapshot(status), DigestService(projects))["workspaces"][0]["tabs"][0]["agents"][0]


def test_board_marca_turno_local_y_mantiene_la_pregunta(tmp_path):
    projects = tmp_path / "projects"
    path = write(projects / "-p", [PROMPT, PREGUNTA])
    assert agent_of(projects, "working")["asks_user"] is True
    assert agent_of(projects, "done")["turno_local"] is False
    write(projects / "-p", [PROMPT, PREGUNTA, *RELOAD])
    done = agent_of(projects, "done")
    assert done["turno_local"] is True and done["asks_user"] is True
    path.write_text("\n".join(json.dumps(l) for l in [PROMPT, PREGUNTA, *RELOAD, PROMPT]), encoding="utf-8")
    working = agent_of(projects, "working")
    assert working["asks_user"] is False and working["turno_local"] is False


def rboard(status, local=False):
    return {"workspaces": [{"tabs": [{"agents": [{"session_id": SID, "status": status, "turno_local": local}]}]}]}


def tracker(tmp_path):
    clock = ReplyClock()
    return ReplyTracker(StateStore(tmp_path), clock), clock


def test_recarga_no_marca_sin_leer(tmp_path):
    t, _ = tracker(tmp_path)
    t.observe(rboard("working"), rboard("done", local=True))
    assert not t.is_unread(SID)


def test_recarga_no_pisa_una_respuesta_sin_leer(tmp_path):
    t, clock = tracker(tmp_path)
    t.observe(rboard("working"), rboard("idle"))
    replied = t.entries[SID]["replied_at"]
    clock.now += timedelta(minutes=10)
    t.observe(rboard("idle"), rboard("working"))
    t.observe(rboard("working"), rboard("done", local=True))
    assert t.is_unread(SID) and t.entries[SID]["replied_at"] == replied


def test_transcript_tardio_deshace_el_sin_leer(tmp_path):
    t, clock = tracker(tmp_path)
    t.observe(rboard("working"), rboard("idle"))
    clock.now += timedelta(seconds=5)
    t.mark_seen(SID)
    clock.now += timedelta(minutes=10)
    t.observe(rboard("idle"), rboard("working"))
    t.observe(rboard("working"), rboard("done"))
    assert t.is_unread(SID)
    clock.now += timedelta(seconds=2)
    t.observe(rboard("done"), rboard("done", local=True))
    assert not t.is_unread(SID)


def test_comando_local_tardio_no_borra_una_respuesta_real_vieja(tmp_path):
    t, clock = tracker(tmp_path)
    t.observe(rboard("working"), rboard("idle"))
    clock.now += timedelta(minutes=5)
    t.observe(rboard("idle"), rboard("idle", local=True))
    assert t.is_unread(SID)


def pboard(status, asks=False, local=False):
    return {"workspaces": [{"label": "Uno", "tabs": [{"agents": [
        {"pane_id": "p1", "status": status, "asks_user": asks, "pending": "", "session_id": SID,
         "turno_local": local}]}]}]}


def test_push_silencioso_en_recargas(tmp_path):
    svc = PushService(tmp_path, sender=Recorder(), clock=PushClock())
    assert svc.observe(pboard("working"), pboard("done", local=True)) == []
    assert svc.observe(pboard("working"), pboard("idle", asks=True, local=True)) == []
    assert svc.observe(pboard("working", asks=False), pboard("done", asks=True, local=True)) == []
    assert [e["kind"] for e in svc.observe(pboard("working"), pboard("done"))] == ["done"]


def test_push_bloqueado_sigue_avisando_aunque_haya_comando_local(tmp_path):
    svc = PushService(tmp_path, sender=Recorder(), clock=PushClock())
    assert [e["kind"] for e in svc.observe(pboard("working"), pboard("blocked", local=True))] == ["blocked"]
