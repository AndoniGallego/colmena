import json

import pytest

from conftest import SID
from orquestador import statusline
from orquestador.digest import DigestService
from orquestador.transcript import TranscriptService


@pytest.mark.parametrize("raw,name", [
    ("claude-opus-5-5", "Opus 5.5"),
    ("claude-sonnet-5-5", "Sonnet 5.5"),
    ("claude-haiku-5-5", "Haiku 5.5"),
    ("claude-fable-5-1", "Fable 5.1"),
    ("claude-opus-4-7", "Opus 4.7"),
    ("claude-haiku-4-5-20251001", "Haiku 4.5"),
    ("claude-opus-5", "Opus 5"),
    ("claude-opus-5-5[1m]", "Opus 5.5"),
    ("claude-mystery-9", "mystery-9"),
    ("gpt-x", "gpt-x"),
    ("", ""),
])
def test_model_name(raw, name):
    assert statusline.model_name(raw) == name


def test_context_window_table():
    assert statusline.context_window("claude-haiku-4-5-20251001") == 200_000
    assert statusline.context_window("claude-opus-4-7") == 1_000_000
    assert statusline.context_window("claude-unknown") == 1_000_000


def test_used_tokens_sums_three_fields():
    usage = {"input_tokens": 10, "cache_read_input_tokens": 200, "cache_creation_input_tokens": 30, "output_tokens": 999}
    assert statusline.used_tokens(usage) == 240
    assert statusline.used_tokens(None) is None
    assert statusline.used_tokens({"input_tokens": "x"}) == 0


def test_ctx_thresholds_default_25():
    model = "claude-opus-5-5"
    assert statusline.ctx_state(None, model) == (None, "unknown")
    assert statusline.ctx_state(0, model) == (None, "unknown")
    assert statusline.ctx_state(149_999, model) == (15, "ok")
    assert statusline.ctx_state(150_000, model) == (15, "caution")
    assert statusline.ctx_state(249_999, model) == (25, "caution")
    assert statusline.ctx_state(250_000, model) == (25, "warn")
    assert statusline.ctx_state(100_000, "claude-haiku-4-5") == (50, "warn")


def test_ctx_warn_pct_env(monkeypatch):
    monkeypatch.setenv("COLMENA_CTX_WARN_PCT", "50")
    assert statusline.ctx_state(300_000, "claude-opus-5-5")[1] == "caution"
    assert statusline.ctx_state(500_000, "claude-opus-5-5")[1] == "warn"
    monkeypatch.setenv("COLMENA_CTX_WARN_PCT", "basura")
    assert statusline.warn_pct() == 25


def test_read_ticket(tmp_path):
    (tmp_path / f"{SID}.json").write_text(json.dumps({"ticket": "SITE-1", "title": "Algo"}))
    assert statusline.read_ticket(tmp_path, SID) == "SITE-1 - Algo"
    (tmp_path / f"{SID}.json").write_text(json.dumps({"ticket": "SITE-1"}))
    assert statusline.read_ticket(tmp_path, SID) == "SITE-1"
    (tmp_path / f"{SID}.json").write_text(json.dumps({"title": "sin ticket"}))
    assert statusline.read_ticket(tmp_path, SID) == ""
    (tmp_path / f"{SID}.json").write_text("{roto")
    assert statusline.read_ticket(tmp_path, SID) == ""
    (tmp_path / f"{SID}.json").write_text("[1]")
    assert statusline.read_ticket(tmp_path, SID) == ""
    assert statusline.read_ticket(tmp_path, "otra") == ""


def fake_net(tmp_path, names):
    for n in names:
        (tmp_path / n).mkdir()
    return str(tmp_path)


def test_vpn_states(tmp_path, monkeypatch):
    sysfs = fake_net(tmp_path, ["eth0", "tun0", "tun1"])
    monkeypatch.setattr(statusline, "_has_ipv4", lambda iface: iface == "tun1")
    assert statusline.vpn_state(sysfs) == "up"
    monkeypatch.setattr(statusline, "_has_ipv4", lambda iface: iface == "eth0")
    assert statusline.vpn_state(sysfs) == "down"


def test_vpn_no_interface_and_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(statusline, "_has_ipv4", lambda iface: True)
    assert statusline.vpn_state(fake_net(tmp_path, ["eth0"])) == "down"
    assert statusline.vpn_state(str(tmp_path / "nope")) is None


def test_vpn_env(tmp_path, monkeypatch):
    sysfs = fake_net(tmp_path, ["wg0", "tun0"])
    monkeypatch.setattr(statusline, "_has_ipv4", lambda iface: iface == "wg0")
    monkeypatch.setenv("COLMENA_VPN_SYSFS_DIR", sysfs)
    assert statusline.vpn_state() == "down"
    monkeypatch.setenv("COLMENA_VPN_INTERFACE", "wg")
    assert statusline.vpn_state() == "up"
    monkeypatch.setenv("COLMENA_VPN_STATUSLINE_ENABLED", "false")
    assert statusline.vpn_state() is None


def write_model_transcript(projects, lines):
    path = projects / "-proj" / f"{SID}.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def asst(model, **usage):
    return {"type": "assistant", "message": {"model": model, "usage": usage, "content": [{"type": "text", "text": "x"}]}}


def test_page_status_line_uses_latest_real_assistant(projects, tmp_path, monkeypatch):
    net = tmp_path / "net"
    net.mkdir()
    monkeypatch.setattr(statusline, "_has_ipv4", lambda iface: True)
    monkeypatch.setenv("COLMENA_VPN_SYSFS_DIR", fake_net(net, ["tun0"]))
    titles = tmp_path / "titles"
    titles.mkdir()
    (titles / f"{SID}.json").write_text(json.dumps({"ticket": "SITE-7", "title": "Carrito"}))
    write_model_transcript(projects, [
        asst("claude-sonnet-5-5", input_tokens=1, cache_read_input_tokens=1000),
        {"type": "user", "message": {"content": "hola"}},
        asst("claude-opus-5-5", input_tokens=5, cache_read_input_tokens=300_000, cache_creation_input_tokens=5_000),
        {**asst("claude-haiku-5-5", input_tokens=9), "isSidechain": True},
        asst("<synthetic>", input_tokens=0),
    ])
    svc = TranscriptService(DigestService(projects), title_dir=titles)
    sl = svc.page(SID, None, 10)["status_line"]
    assert sl == {"model": "Opus 5.5", "ticket": "SITE-7 - Carrito", "ctx_pct": 31, "ctx_level": "warn", "vpn": "up"}


def test_page_status_line_without_data(projects, tmp_path):
    write_model_transcript(projects, [{"type": "user", "message": {"content": "hola"}}])
    svc = TranscriptService(DigestService(projects), title_dir=tmp_path / "nada")
    sl = svc.page(SID, None, 10)["status_line"]
    assert sl["model"] == "" and sl["ticket"] == "" and sl["ctx_pct"] is None and sl["ctx_level"] == "unknown"


def snap_file(directory, **over):
    data = {"session_id": SID, "model_id": "claude-opus-5-5", "total_input_tokens": 400_000,
            "context_window_size": 1_000_000, "pct": 40, "ts": 2_000_000_000}
    data.update(over)
    directory.mkdir(exist_ok=True)
    (directory / f"{SID}.json").write_text(json.dumps(data))
    return directory


def stamped(model, ts, **usage):
    return {**asst(model, **usage), "timestamp": ts}


def test_snapshot_replaces_transcript_estimate(projects, tmp_path):
    write_model_transcript(projects, [stamped("claude-opus-5-5", "2033-05-18T03:33:20Z", input_tokens=100_000)])
    ctx = snap_file(tmp_path / "ctx")
    svc = TranscriptService(DigestService(projects), title_dir=tmp_path / "t", ctx_dir=ctx)
    sl = svc.page(SID, None, 10)["status_line"]
    assert sl["ctx_pct"] == 40 and sl["ctx_level"] == "warn" and sl["model"] == "Opus 5.5"


def test_snapshot_window_drives_level(projects, tmp_path):
    write_model_transcript(projects, [{"type": "user", "message": {"content": "hola"}}])
    ctx = snap_file(tmp_path / "ctx", total_input_tokens=100_000, context_window_size=200_000, pct=50)
    svc = TranscriptService(DigestService(projects), title_dir=tmp_path / "t", ctx_dir=ctx)
    sl = svc.page(SID, None, 10)["status_line"]
    assert sl["ctx_pct"] == 50 and sl["ctx_level"] == "warn" and sl["model"] == "Opus 5.5"


def test_stale_snapshot_falls_back_to_transcript(projects, tmp_path):
    write_model_transcript(projects, [stamped("claude-opus-5-5", "2033-05-18T03:33:20Z", input_tokens=100_000)])
    ctx = snap_file(tmp_path / "ctx", ts=2_000_000_000 - 3600)
    svc = TranscriptService(DigestService(projects), title_dir=tmp_path / "t", ctx_dir=ctx)
    assert svc.page(SID, None, 10)["status_line"]["ctx_pct"] == 10


def test_snapshot_within_tolerance_is_used(projects, tmp_path):
    write_model_transcript(projects, [stamped("claude-opus-5-5", "2033-05-18T03:33:20Z", input_tokens=100_000)])
    ctx = snap_file(tmp_path / "ctx", ts=2_000_000_000 - 30)
    svc = TranscriptService(DigestService(projects), title_dir=tmp_path / "t", ctx_dir=ctx)
    assert svc.page(SID, None, 10)["status_line"]["ctx_pct"] == 40


@pytest.mark.parametrize("over", [
    {"session_id": "otra"}, {"pct": None}, {"pct": "40"}, {"pct": True}, {"pct": -1},
    {"context_window_size": 0}, {"total_input_tokens": None}, {"ts": "ayer"}, {"ts": None},
])
def test_invalid_snapshot_is_ignored(projects, tmp_path, over):
    write_model_transcript(projects, [asst("claude-opus-5-5", input_tokens=100_000)])
    ctx = snap_file(tmp_path / "ctx", **over)
    svc = TranscriptService(DigestService(projects), title_dir=tmp_path / "t", ctx_dir=ctx)
    assert svc.page(SID, None, 10)["status_line"]["ctx_pct"] == 10


def test_snapshot_broken_json_or_non_dict(projects, tmp_path):
    write_model_transcript(projects, [asst("claude-opus-5-5", input_tokens=100_000)])
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    svc = TranscriptService(DigestService(projects), title_dir=tmp_path / "t", ctx_dir=ctx)
    assert svc.page(SID, None, 10)["status_line"]["ctx_pct"] == 10
    (ctx / f"{SID}.json").write_text("{roto")
    assert svc.page(SID, None, 10)["status_line"]["ctx_pct"] == 10
    (ctx / f"{SID}.json").write_text("[1]")
    assert svc.page(SID, None, 10)["status_line"]["ctx_pct"] == 10


@pytest.mark.parametrize("sid", ["../x", "a/b", "", "x" * 81, "a b"])
def test_snapshot_path_only_from_valid_session_id(tmp_path, sid):
    (tmp_path / "x.json").write_text(json.dumps({"session_id": sid, "pct": 1, "total_input_tokens": 1,
                                                  "context_window_size": 10, "ts": 1}))
    assert statusline.read_snapshot(tmp_path / "ctx", sid, None) is None
    assert statusline.read_snapshot(tmp_path / "ctx", None, None) is None


def test_ctx_dir_env_and_default(tmp_path, monkeypatch):
    assert statusline.ctx_dir().parts[-4:] == (".local", "state", "andokit", "ctx")
    monkeypatch.setenv("ORQ_CTX_DIR", str(tmp_path / "otro"))
    assert statusline.ctx_dir() == tmp_path / "otro"


def test_service_reads_snapshot_from_env_dir(projects, tmp_path, monkeypatch):
    write_model_transcript(projects, [asst("claude-opus-5-5", input_tokens=100_000)])
    monkeypatch.setenv("ORQ_CTX_DIR", str(snap_file(tmp_path / "envctx")))
    svc = TranscriptService(DigestService(projects), title_dir=tmp_path / "t")
    assert svc.page(SID, None, 10)["status_line"]["ctx_pct"] == 40
