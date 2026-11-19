import json
import time

from conftest import SID, make_snapshot
from orquestador import contexto as ctxmod
from orquestador.board import build_board
from orquestador.contexto import ContextoService
from orquestador.digest import DigestService
from orquestador.transcript import parse_file

OPUS = "claude-opus-5-5"
HAIKU = "claude-haiku-4-5-20251001"


def assistant(tokens, model=OPUS, ts="2026-11-01T10:00:00Z", side=False, cache=0):
    obj = {"type": "assistant", "timestamp": ts, "message": {"model": model, "content": [{"type": "text", "text": "x"}],
           "usage": {"input_tokens": tokens - cache, "cache_read_input_tokens": cache, "cache_creation_input_tokens": 0}}}
    if side:
        obj["isSidechain"] = True
    return obj


def boundary(pre=229_000, post=22_600, trigger="auto", ts="2026-11-01T11:00:00Z"):
    return {"type": "system", "subtype": "compact_boundary", "timestamp": ts,
            "compactMetadata": {"trigger": trigger, "preTokens": pre, "postTokens": post}}


def write(projects, lines, sid=SID, raw_tail=""):
    folder = projects / "-p"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sid}.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n" + raw_tail, encoding="utf-8")
    return path


def service(projects, tmp_path):
    return ContextoService(DigestService(projects), tmp_path / "ctx")


def snap(tmp_path, tokens, window, ts, sid=SID):
    folder = tmp_path / "ctx"
    folder.mkdir(exist_ok=True)
    (folder / f"{sid}.json").write_text(json.dumps({"session_id": sid, "pct": round(tokens * 100 / window),
                                                    "context_window_size": window, "total_input_tokens": tokens,
                                                    "ts": ts, "model_id": OPUS}))


def test_transcript_fallback_uses_last_main_assistant(tmp_path):
    projects = tmp_path / "pr"
    write(projects, [assistant(100_000), assistant(500_000, side=True), assistant(180_000, cache=170_000)])
    ctx = service(projects, tmp_path).for_session(SID)
    assert ctx["tokens"] == 180_000 and ctx["pct"] == 18 and ctx["window"] == 1_000_000
    assert ctx["fuente"] == "transcript" and ctx["compactaciones"] == 0 and ctx["ultima_compactacion"] is None


def test_haiku_45_window_is_200k(tmp_path):
    projects = tmp_path / "pr"
    write(projects, [assistant(100_000, model=HAIKU)])
    ctx = service(projects, tmp_path).for_session(SID)
    assert ctx["window"] == 200_000 and ctx["pct"] == 50


def test_fresh_snapshot_wins(tmp_path):
    projects = tmp_path / "pr"
    ts = time.mktime((2026, 11, 1, 10, 0, 0, 0, 0, 0))
    write(projects, [assistant(100_000, ts="2026-11-01T10:00:00+00:00")])
    snap(tmp_path, 300_000, 1_000_000, 4_000_000_000)
    ctx = service(projects, tmp_path).for_session(SID)
    assert ctx["fuente"] == "statusline" and ctx["tokens"] == 300_000 and ctx["pct"] == 30


def test_snapshot_with_1m_window(tmp_path):
    projects = tmp_path / "pr"
    write(projects, [assistant(100_000, model=HAIKU)])
    snap(tmp_path, 100_000, 1_000_000, 4_000_000_000)
    ctx = service(projects, tmp_path).for_session(SID)
    assert ctx["window"] == 1_000_000 and ctx["pct"] == 10


def test_stale_snapshot_is_ignored(tmp_path):
    projects = tmp_path / "pr"
    write(projects, [assistant(100_000, ts="2026-11-01T10:00:00Z")])
    snap(tmp_path, 900_000, 1_000_000, 1_000_000)
    assert service(projects, tmp_path).for_session(SID)["fuente"] == "transcript"


def test_boundary_without_later_assistant_uses_post_tokens(tmp_path):
    projects = tmp_path / "pr"
    write(projects, [assistant(229_000), boundary(), {"type": "user", "isCompactSummary": True,
                                                       "message": {"content": "resumen"}}])
    ctx = service(projects, tmp_path).for_session(SID)
    assert ctx["tokens"] == 22_600 and ctx["pct"] == 2
    assert ctx["compactaciones"] == 1
    assert ctx["ultima_compactacion"] == {"ts": "2026-11-01T11:00:00Z", "trigger": "auto", "pre": 229_000, "post": 22_600}


def test_assistant_after_boundary_wins_and_counts_all(tmp_path):
    projects = tmp_path / "pr"
    write(projects, [assistant(200_000), boundary(trigger="manual"), assistant(40_000), boundary(), assistant(60_000)])
    ctx = service(projects, tmp_path).for_session(SID)
    assert ctx["tokens"] == 60_000 and ctx["compactaciones"] == 2


def test_transcript_without_usage_is_none(tmp_path):
    projects = tmp_path / "pr"
    write(projects, [{"type": "user", "message": {"content": "hola"}},
                     {"type": "assistant", "message": {"model": OPUS, "content": []}}])
    assert service(projects, tmp_path).for_session(SID) is None


def test_unknown_session_is_none(tmp_path):
    projects = tmp_path / "pr"
    projects.mkdir()
    assert service(projects, tmp_path).for_session("nope") is None


def test_tail_cuts_a_line_in_half(tmp_path, monkeypatch):
    monkeypatch.setattr(ctxmod, "TAIL_BYTES", 600)
    projects = tmp_path / "pr"
    write(projects, [assistant(10_000)] + [{"type": "user", "message": {"content": "x" * 80}}] * 12 + [assistant(77_000)])
    ctx = service(projects, tmp_path).for_session(SID)
    assert ctx["tokens"] == 77_000


def test_reads_back_when_tail_has_no_assistant(tmp_path, monkeypatch):
    monkeypatch.setattr(ctxmod, "TAIL_BYTES", 400)
    projects = tmp_path / "pr"
    big = [{"type": "user", "message": {"content": "y" * 300}}] * 6
    write(projects, [assistant(55_000)] + big)
    assert service(projects, tmp_path).for_session(SID)["tokens"] == 55_000


def test_cache_invalidates_on_size(tmp_path):
    projects = tmp_path / "pr"
    path = write(projects, [assistant(100_000)])
    svc = service(projects, tmp_path)
    assert svc.for_session(SID)["tokens"] == 100_000
    with path.open("a") as fh:
        fh.write(json.dumps(assistant(150_000)) + "\n" + json.dumps(boundary()) + "\n")
    ctx = svc.for_session(SID)
    assert ctx["tokens"] == 22_600 and ctx["compactaciones"] == 1


def test_incremental_count_does_not_double_count(tmp_path):
    projects = tmp_path / "pr"
    path = write(projects, [assistant(1), boundary()])
    svc = service(projects, tmp_path)
    assert svc.for_session(SID)["compactaciones"] == 1
    with path.open("a") as fh:
        fh.write(json.dumps(assistant(5)) + "\n")
    assert svc.for_session(SID)["compactaciones"] == 1


def test_no_alarm_levels_in_payload(tmp_path):
    projects = tmp_path / "pr"
    write(projects, [assistant(900_000)])
    ctx = service(projects, tmp_path).for_session(SID)
    assert set(ctx) == {"pct", "tokens", "window", "fuente", "compactaciones", "ultima_compactacion"}


# Paridad con claude-statusline-context.sh: valores anotados a mano con su `jq`
# (usage del último assistant sin isSidechain; denominador por tabla).
PARIDAD = [
    ([assistant(179_402, cache=150_000)], 18),
    ([assistant(50_000, model=HAIKU), assistant(900_000, side=True)], 25),
    ([assistant(499_999), boundary(499_999, 30_000), assistant(30_100)], 3),
]


def test_parity_with_statusline_script(tmp_path):
    for i, (lines, pct) in enumerate(PARIDAD):
        projects = tmp_path / f"pr{i}"
        write(projects, lines)
        assert service(projects, tmp_path).for_session(SID)["pct"] == pct


def test_board_has_ctx_and_null_without_digest(projects, tmp_path):
    folder = projects / "-proj"
    path = folder / f"{SID}.jsonl"
    with path.open("a") as fh:
        fh.write(json.dumps(assistant(120_000)) + "\n")
    board = build_board(make_snapshot(), DigestService(projects), contexto=ContextoService(DigestService(projects)))
    agents = [a for ws in board["workspaces"] for t in ws["tabs"] for a in t["agents"]]
    by_pane = {a["pane_id"]: a for a in agents}
    assert by_pane["w1:p1"]["ctx"]["pct"] == 12
    assert by_pane["w2:p9"]["ctx"] is None
    assert build_board(make_snapshot(), DigestService(projects))["workspaces"][1]["tabs"][0]["agents"] == []


def test_transcript_compact_item_carries_boundary(tmp_path):
    projects = tmp_path / "pr"
    path = write(projects, [assistant(100), boundary(trigger="manual"),
                            {"type": "user", "isCompactSummary": True, "timestamp": "t", "message": {"content": "resumen"}}])
    items, _ = parse_file(path)
    compact = [i for i in items if i["kind"] == "compact"][0]
    assert compact["compact"] == {"trigger": "manual", "pre": 229_000, "post": 22_600}
