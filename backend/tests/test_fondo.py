import json
from datetime import datetime

from orquestador.fondo import FONDO_MAX_S, tareas_pendientes

TS0 = "2026-11-04T12:00:00.000Z"
TS1 = "2026-11-04T12:05:00.000Z"


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def tu(name, inp, tid="toolu_1", ts=TS0):
    return json.dumps({"type": "assistant", "timestamp": ts,
                       "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}})


def tr(tid, content="ok", is_error=False, ts=TS1):
    return json.dumps({"type": "user", "timestamp": ts,
                       "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": content,
                                                "is_error": is_error}]}})


def notify(tid, status="completed", ts=TS1):
    body = (f"<task-notification>\n<tool-use-id>{tid}</tool-use-id>\n"
            f"<status>{status}</status>\n</task-notification>")
    return json.dumps({"type": "queue-operation", "timestamp": ts, "content": body})


def test_bash_background_hasta_notificacion():
    lines = [
        tu("Bash", {"description": "Correr cursor-agent en repo", "command": "cursor-agent --secret x",
            "run_in_background": True}, "toolu_bash"),
        tr("toolu_bash", "Background command started"),
    ]
    now = _epoch(TS1)
    out = tareas_pendientes(lines, now=now)
    assert len(out) == 1
    assert out[0]["id"] == "toolu_bash"
    assert out[0]["tipo"] == "cursor"
    assert "cursor" in out[0]["texto"].lower() or "Correr" in out[0]["texto"]
    assert "secret" not in out[0]["texto"] and "/home" not in out[0]["texto"]

    lines.append(notify("toolu_bash"))
    assert tareas_pendientes(lines, now=now) == []


def test_agent_async_sin_run_in_background_en_input():
    lines = [
        tu("Agent", {"description": "Auditoría de estilos", "prompt": "x"}, "toolu_ag"),
        tr("toolu_ag", "Async agent launched successfully.\nagentId: abc"),
    ]
    now = _epoch(TS1)
    out = tareas_pendientes(lines, now=now)
    assert len(out) == 1 and out[0]["tipo"] == "agente" and out[0]["texto"] == "Auditoría de estilos"


def test_error_en_tool_result_no_cuenta():
    lines = [
        tu("Bash", {"description": "Servidor", "run_in_background": True}, "toolu_x"),
        tr("toolu_x", "fail", is_error=True),
    ]
    assert tareas_pendientes(lines, now=_epoch(TS1)) == []


def test_vencimiento_dos_horas():
    lines = [
        tu("Bash", {"description": "Largo", "run_in_background": True}, "toolu_old", ts=TS0),
        tr("toolu_old", "ok", ts=TS0),
    ]
    now = _epoch(TS0) + FONDO_MAX_S + 1
    assert tareas_pendientes(lines, now=now) == []


def test_workflow_cuenta_como_pendiente():
    lines = [
        tu("Workflow", {"description": "Deploy preview"}, "toolu_wf"),
        tr("toolu_wf", "started"),
    ]
    out = tareas_pendientes(lines, now=_epoch(TS1))
    assert len(out) == 1 and out[0]["tipo"] == "workflow"


def test_service_default_clock_is_live(monkeypatch, tmp_path):
    import orquestador.fondo as m
    calls = []

    class Fake(datetime):
        @classmethod
        def now(cls, tz=None):
            calls.append(1)
            return datetime(2026, 11, 4, 12, 0, 0)

    monkeypatch.setattr(m, "datetime", Fake)
    svc = m.FondoService(lambda sid: None)
    before = len(calls)
    svc._clock()
    svc._clock()
    assert len(calls) - before == 2
