import asyncio
import os
import stat

import pytest
from fastapi.testclient import TestClient

from conftest import PIN, make_snapshot
from orquestador.enchufe import FakeTerminales
from orquestador import auth, cli
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.config import Config, bump_epoch, hash_pin, load_config, load_secret, save_config, verify_pin
from orquestador.digest import DigestService
from orquestador.state import StateStore


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


def make_client(cfg, tmp_path, handoffs, enchufe=None, base="https://testserver", **kw):
    enchufe = enchufe or FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    app = create_app(cfg, b"secret", StateStore(tmp_path), dist=tmp_path / "nodist",
                     handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads", enchufe=enchufe)
    return TestClient(app, base_url=base, headers={"Origin": base}, client=("127.0.0.1", 1), **kw)


def test_short_pin_rejected_by_set_pin(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ORQ_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "corto12")
    old = os.umask(0o022)
    try:
        assert cli.set_pin() == 1
    finally:
        os.umask(old)
    assert "8" in capsys.readouterr().err


def test_set_pin_ok_hashes(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQ_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "unpinlargo")
    old = os.umask(0o022)
    try:
        assert cli.set_pin() == 0
    finally:
        os.umask(old)
    cfg = load_config(tmp_path / "d")
    assert cfg.pin.startswith("pbkdf2$") and verify_pin("unpinlargo", cfg.pin)


def test_plain_pin_refuses_to_start(tmp_path, monkeypatch, capsys):
    directory = tmp_path / "d"
    monkeypatch.setenv("ORQ_DATA_DIR", str(directory))
    directory.mkdir()
    save_config(Config(pin="textoplano123"), directory)
    old = os.umask(0o022)
    try:
        assert cli.serve() == 1
    finally:
        os.umask(old)
    assert "hasheado" in capsys.readouterr().err
    assert not verify_pin("textoplano123", "textoplano123")


def test_global_lockout():
    now = [0.0]
    limiter = auth.LoginLimiter(clock=lambda: now[0])
    for i in range(auth.GLOBAL_MAX_FAILURES + 1):
        limiter.fail(f"10.0.0.{i}")
    assert limiter.retry_after("10.9.9.9") > 0
    now[0] += auth.GLOBAL_LOCK_SECONDS + 1
    assert limiter.retry_after("10.9.9.9") == 0


def test_epoch_revoke_all_invalidates_old_cookies(cfg, tmp_path, handoffs):
    with make_client(cfg, tmp_path, handoffs) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        old = c.cookies.get(auth.COOKIE_NAME)
        assert c.get("/api/me").status_code == 200
        assert c.post("/api/sessions/revoke-all").status_code == 200
        assert (tmp_path / "epoch").read_text() == "1" and mode(tmp_path / "epoch") == 0o600
        c.cookies.set(auth.COOKIE_NAME, old)
        assert c.get("/api/me").status_code == 401
        c.cookies.clear()
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        assert c.get("/api/me").status_code == 200


def test_epoch_in_signature():
    token = auth.sign_session(b"k", now=1000, epoch=0)
    assert auth.valid_session(b"k", token, now=1001, epoch=0)
    assert not auth.valid_session(b"k", token, now=1001, epoch=1)


def test_session_cookie_is_host_prefixed_and_secure(cfg, tmp_path, handoffs):
    assert auth.COOKIE_NAME == "__Host-orq_session"
    with make_client(cfg, tmp_path, handoffs) as c:
        cookie = c.post("/api/login", json={"pin": PIN}).headers["set-cookie"].lower()
    assert cookie.startswith("__host-orq_session=") and "secure" in cookie and "path=/" in cookie
    assert "domain" not in cookie


def test_cookie_ttl_seven_days():
    assert auth.COOKIE_TTL == 7 * 24 * 3600


def test_tailscale_user_mismatch(tmp_path, handoffs, projects):
    cfg = Config(pin=hash_pin(PIN), claude_projects_dir=str(projects), tailscale_user="yo@example.com")
    with make_client(cfg, tmp_path, handoffs) as c:
        bad = c.post("/api/login", json={"pin": PIN}, headers={"Tailscale-User-Login": "otro@example.com"})
        assert bad.status_code == 403
        ok = c.post("/api/login", json={"pin": PIN}, headers={"Tailscale-User-Login": "yo@example.com"})
        assert ok.status_code == 200
        assert c.get("/api/me").status_code == 200
        assert c.get("/api/me", headers={"Tailscale-User-Login": "otro@example.com"}).status_code == 403


def test_ipv6_cidrs_default():
    nets = auth.parse_networks(Config().allowed_cidrs)
    assert Config().host == "127.0.0.1"
    assert auth.ip_allowed("::1", nets)
    assert auth.ip_allowed("fd7a:115c:a1e0::1234", nets)
    assert auth.ip_allowed("100.100.5.5", nets)
    assert not auth.ip_allowed("2001:db8::1", nets)
    assert not auth.ip_allowed("192.168.1.5", nets)


def test_security_headers(client):
    r = client.get("/api/me")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "img-src 'self' data: blob:" in csp
    page = client.get("/")
    assert "content-security-policy" in page.headers and page.headers.get("cache-control") != "no-store"


PRES = {"device": "dev-12345", "visible": False}


def test_body_too_large_413(authed):
    r = authed.post("/api/focus", json={"tab_id": "x" * 70000})
    assert r.status_code == 413
    assert authed.post("/api/login", content=b"x" * 70000).status_code == 413


def test_field_limits(authed, client):
    assert client.post("/api/login", json={"pin": "x" * 129}).status_code == 422


def test_sse_cap_503(authed, app):
    hub = app.state.hub
    for _ in range(10):
        hub.subscribers.add(asyncio.Queue())
    assert authed.get("/api/events").status_code == 503


def test_sse_queue_full_does_not_block_others():
    from orquestador.enchufe import FakeTerminales
    from conftest import make_snapshot
    hub = BoardHub(FakeTerminales.desde_snapshot(make_snapshot()), DigestService(None))
    slow, fast = asyncio.Queue(maxsize=2), asyncio.Queue(maxsize=2)
    hub.subscribers.update({slow, fast})
    for i in range(5):
        BoardHub._offer(slow, {"n": i})
        hub._offer(fast, {"n": i})
        fast.get_nowait()
    assert slow.full() and [slow.get_nowait()["n"], slow.get_nowait()["n"]] == [3, 4]


def test_sse_refresh_with_full_queue(enchufe, projects):
    async def scenario():
        hub = BoardHub(enchufe, DigestService(projects))
        full = asyncio.Queue(maxsize=1)
        other = asyncio.Queue(maxsize=1)
        full.put_nowait("viejo")
        hub.subscribers.update({full, other})
        board = await hub.refresh(force=True)
        assert full.get_nowait() is board and other.get_nowait() is board
    asyncio.run(scenario())


def test_file_permissions(tmp_path):
    old = os.umask(0o022)
    try:
        d = tmp_path / "d"
        d.mkdir()
        load_secret(d)
        save_config(Config(), d)
        state = StateStore(d)
        state.add_respuesta({"id": "1"})
        state.flush()
        bump_epoch(d)
    finally:
        os.umask(old)
    for name in ("secret", "config.toml", "state.json", "epoch"):
        assert mode(d / name) == 0o600, name
    assert load_secret(d) == (d / "secret").read_bytes()


def _hard_client(cfg, tmp_path, handoffs, **cfg_over):
    for k, v in cfg_over.items():
        setattr(cfg, k, v)
    return make_client(cfg, tmp_path, handoffs)


def test_sec_fetch_site_blocks_cross_and_same_site(cfg, tmp_path, handoffs):
    with _hard_client(cfg, tmp_path, handoffs) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        for site in ("cross-site", "same-site"):
            assert c.get("/api/me", headers={"Sec-Fetch-Site": site}).status_code == 403
            assert c.post("/api/presencia", headers={"Sec-Fetch-Site": site}).status_code == 403
        for site in ("same-origin", "none"):
            assert c.get("/api/me", headers={"Sec-Fetch-Site": site}).status_code == 200
        assert c.get("/api/me").status_code == 200


def test_post_needs_matching_origin(cfg, tmp_path, handoffs):
    with _hard_client(cfg, tmp_path, handoffs) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        for origin in ("http://evil.example", "null", "https://testserver:8445"):
            assert c.post("/api/presencia", headers={"Origin": origin}).status_code == 403
        no_origin = c.post("/api/presencia", headers={"Origin": ""})
        assert no_origin.status_code == 403
        assert c.get("/api/me", headers={"Origin": "http://evil.example"}).status_code == 200


def test_app_origin_is_exact_when_configured(cfg, tmp_path, handoffs):
    app_origin = "https://host.ts.net:8444"
    with _hard_client(cfg, tmp_path, handoffs, app_origin=app_origin,
                      viewer_origin="https://host.ts.net:8445") as c:
        assert c.post("/api/login", json={"pin": PIN}, headers={"Origin": app_origin}).status_code == 200
        assert c.post("/api/presencia", headers={"Origin": "https://host.ts.net:8445"}).status_code == 403
        assert c.post("/api/presencia", headers={"Origin": "http://testserver"}).status_code == 403
        assert c.post("/api/presencia", json=PRES, headers={"Origin": app_origin}).status_code == 200


def test_post_body_must_be_json(cfg, tmp_path, handoffs):
    with _hard_client(cfg, tmp_path, handoffs) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        r = c.post("/api/focus", content='{"tab_id": "w1:t1"}', headers={"Content-Type": "text/plain"})
        assert r.status_code == 415
        r = c.post("/api/focus", content="tab_id=x", headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 415
        assert c.post("/api/presencia", json=PRES).status_code == 200


def test_csp_and_corp_follow_viewer_origin(cfg, tmp_path, handoffs):
    with _hard_client(cfg, tmp_path, handoffs, viewer_origin="https://host.ts.net:8445") as c:
        r = c.get("/api/me", headers={"Sec-Fetch-Site": "same-origin"})
        csp = c.get("/").headers["content-security-policy"]
        assert "frame-src https://host.ts.net:8445" in csp
        assert "img-src 'self' data: blob: https://host.ts.net:8445" in csp
        assert "media-src 'self' https://host.ts.net:8445" in csp
        assert r.headers["cross-origin-resource-policy"] == "same-origin"
    with _hard_client(cfg, tmp_path, handoffs, viewer_origin="") as c:
        assert "frame-src 'none'" in c.get("/").headers["content-security-policy"]
