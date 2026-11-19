import time

from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN
from orquestador import auth


def test_cidr_denied_returns_403(app):
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("8.8.8.8", 1)) as c:
        assert c.get("/api/board").status_code == 403
        assert c.post("/api/login", json={"pin": PIN}).status_code == 403
        assert c.get("/").status_code == 403


def test_ip_allowed():
    nets = auth.parse_networks(["127.0.0.0/8", "100.64.0.0/10"])
    assert auth.ip_allowed("100.100.1.1", nets)
    assert auth.ip_allowed("::ffff:127.0.0.1", nets)
    assert not auth.ip_allowed("192.168.1.5", nets)
    assert not auth.ip_allowed("testclient", nets)
    assert not auth.ip_allowed(None, nets)


def test_api_requires_cookie(client):
    assert client.get("/api/board").status_code == 401
    assert client.get("/api/events").status_code == 401
    assert client.post("/api/focus", json={"tab_id": "w1:t1"}).status_code == 401


def test_login_flow(client):
    assert client.post("/api/login", json={"pin": "0000"}).status_code == 401
    r = client.post("/api/login", json={"pin": PIN})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/me").status_code == 200
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_forged_cookie_rejected(client):
    client.cookies.set(auth.COOKIE_NAME, "9999999999.deadbeef")
    assert client.get("/api/me").status_code == 401


def test_session_signature_and_expiry():
    token = auth.sign_session(b"k", now=1000)
    assert auth.valid_session(b"k", token, now=1001)
    assert not auth.valid_session(b"otra", token, now=1001)
    assert not auth.valid_session(b"k", token, now=1000 + auth.COOKIE_TTL + 1)


def test_rate_limit_locks_after_five_failures(client):
    for _ in range(5):
        assert client.post("/api/login", json={"pin": "bad"}).status_code == 401
    r = client.post("/api/login", json={"pin": PIN})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_limiter_unlocks_with_clock():
    now = [0.0]
    limiter = auth.LoginLimiter(clock=lambda: now[0])
    for _ in range(auth.MAX_FAILURES):
        limiter.fail("ip")
    assert limiter.retry_after("ip") > 0
    now[0] += auth.LOCK_SECONDS + 1
    assert limiter.retry_after("ip") == 0
    limiter.fail("ip")
    assert limiter.retry_after("ip") == 0
