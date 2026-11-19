import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from orquestador.enchufe import FakeTerminales
from orquestador.replies import ReplyTracker
from orquestador.state import StateStore
from terminales_support import aplicar_snapshot

from conftest import SID, make_snapshot


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


def board_with(status, sid=SID):
    return {"workspaces": [{"tabs": [{"agents": [{"session_id": sid, "status": status}]}]}]}


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def tracker(tmp_path):
    clock = Clock()
    return ReplyTracker(StateStore(tmp_path), clock), clock


def test_working_to_idle_marks_unread(tmp_path):
    t, _ = tracker(tmp_path)
    t.observe(board_with("working"), board_with("idle"))
    assert t.is_unread(SID)
    assert t.annotate(board_with("idle"))["workspaces"][0]["tabs"][0]["agents"][0]["unread"] is True


def test_other_transitions_do_not_mark(tmp_path):
    t, _ = tracker(tmp_path)
    t.observe(None, board_with("idle"))
    t.observe(board_with("idle"), board_with("working"))
    t.observe(board_with("blocked"), board_with("idle"))
    assert not t.is_unread(SID)


def test_seen_clears_and_new_reply_marks_again(tmp_path):
    t, clock = tracker(tmp_path)
    t.observe(board_with("working"), board_with("done"))
    clock.now += timedelta(seconds=5)
    t.mark_seen(SID)
    assert not t.is_unread(SID)
    clock.now += timedelta(seconds=5)
    t.observe(board_with("working"), board_with("idle"))
    assert t.is_unread(SID)


def test_persists_across_restart(tmp_path):
    t, _ = tracker(tmp_path)
    t.observe(board_with("working"), board_with("idle"))
    again = ReplyTracker(StateStore(tmp_path))
    assert again.is_unread(SID)


def test_prunes_sessions_gone_for_a_week(tmp_path):
    t, clock = tracker(tmp_path)
    t.observe(board_with("working"), board_with("idle"))
    clock.now += timedelta(days=8)
    t.observe(board_with("idle", "otra"), board_with("idle", "otra"))
    assert SID not in t.entries


def flip(enchufe, status):
    snap = make_snapshot(status)
    snap["agents"][0]["agent_status"] = status
    snap["workspaces"][1]["agent_status"] = status
    aplicar_snapshot(enchufe, snap)


def agent_of(board):
    return next(a for w in board["workspaces"] for t in w["tabs"] for a in t["agents"] if a["session_id"] == SID)


def test_api_flow(authed, app, enchufe):
    hub = app.state.hub
    flip(enchufe, "working")
    asyncio.run(hub.refresh())
    flip(enchufe, "idle")
    asyncio.run(hub.refresh())
    assert agent_of(authed.get("/api/board").json())["unread"] is True
    assert authed.post(f"/api/sessions/{SID}/seen").status_code == 204
    assert agent_of(authed.get("/api/board").json())["unread"] is False


def test_seen_broadcasts_fresh_board(authed, app, enchufe):
    hub = app.state.hub
    flip(enchufe, "working")
    asyncio.run(hub.refresh())
    flip(enchufe, "idle")
    asyncio.run(hub.refresh())
    queue = asyncio.Queue(maxsize=8)
    hub.subscribers.add(queue)
    authed.post(f"/api/sessions/{SID}/seen")
    assert agent_of(queue.get_nowait())["unread"] is False


def test_seen_requires_auth(client):
    assert client.post(f"/api/sessions/{SID}/seen").status_code == 401


def test_seen_invalid_id(authed):
    assert authed.post("/api/sessions/a.b/seen").status_code == 400


def test_seen_outside_board(authed):
    assert authed.post("/api/sessions/99999999-2222-3333-4444-555555555555/seen").status_code == 404
