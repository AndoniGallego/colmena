import pytest
from fastapi.testclient import TestClient
from biblioteca_support import SECRET, Env
from conftest import PIN, make_snapshot
from orquestador.enchufe import FakeTerminales
from test_push import subscribe_body
from orquestador import auth, entrada
from orquestador.app import create_app
from orquestador.biblioteca_viewer import create_viewer_app
from orquestador.config import Config, hash_pin
from orquestador.state import StateStore

APP, VISOR, YO = "https://h.ts.net:8444", "https://h.ts.net:8445", "yo@example.com"
OK = {"Origin": APP, "Tailscale-User-Login": YO, "X-Forwarded-For": "100.64.0.9"}


@pytest.fixture
def prod(tmp_path, projects):
    return Config(pin=hash_pin(PIN), claude_projects_dir=str(projects), tailscale_user=YO, app_origin=APP,
                  viewer_origin=VISOR, entrada={"modos": ["tailscale", "solo-local"],
                                                "tailscale": {"cabecera_ip": "X-Forwarded-For"}})


def cliente(cfg, tmp_path, modo, base, headers):
    enchufe = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    app = create_app(cfg, b"secret", StateStore(tmp_path), dist=tmp_path / "nodist",
                     uploads_dir=tmp_path / "uploads", entrada_interna=False, enchufe=enchufe)
    return TestClient(entrada.pila_para(modo, cfg)(app), base_url=base, headers=headers, client=("127.0.0.1", 5000))


def test_tailscale_sin_header_desde_loopback_403(prod, tmp_path):
    headers = {"Origin": APP, "X-Forwarded-For": "100.64.0.9", "Host": "127.0.0.1:8770"}
    with cliente(prod, tmp_path, "tailscale", APP, headers) as c:
        assert c.get("/api/me").status_code == 403


def _cookie_flags(raw: str) -> None:
    low = raw.lower()
    assert "__host-orq_session=" in low
    assert "secure" in low
    assert "httponly" in low
    assert "samesite=strict" in low
    assert "path=/" in low
    assert "domain=" not in low


def test_cookies_tailscale_tienen_flags(prod, tmp_path):
    with cliente(prod, tmp_path, "tailscale", APP, OK) as c:
        r = c.post("/api/login", json={"pin": PIN})
    assert r.status_code == 200
    _cookie_flags(r.headers.get("set-cookie", ""))


def test_cookies_solo_local_tienen_flags(prod, tmp_path):
    base = "http://localhost:8774"
    with cliente(prod, tmp_path, "solo-local", base, {"Origin": base}) as c:
        r = c.post("/api/login", json={"pin": PIN})
    assert r.status_code == 200
    _cookie_flags(r.headers.get("set-cookie", ""))


def test_produccion_realista_no_regresa(prod, tmp_path):
    with cliente(prod, tmp_path, "tailscale", APP, OK) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        assert c.get("/api/me").status_code == 200
        assert c.post("/api/push/subscribe", json=subscribe_body()).status_code == 200
        assert c.get("/api/me", headers={"Host": "evil.example"}).status_code == 400
        assert c.get("/api/me", headers={"Tailscale-User-Login": ""}).status_code == 403
        assert c.get("/api/me", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 403
        assert c.post("/api/login", json={"pin": PIN}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_sse_pasa_entera_por_la_pila(prod):
    async def sse(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
        await send({"type": "http.response.body", "body": b"event: a\n\n", "more_body": True})
        await send({"type": "http.response.body", "body": b"event: b\n\n"})
    c = TestClient(entrada.pila_para("tailscale", prod)(sse), base_url=APP, headers=OK, client=("127.0.0.1", 1))
    r = c.get("/api/events")
    assert r.status_code == 200 and r.text == "event: a\n\nevent: b\n\n"


def test_visor_por_la_pila(prod, tmp_path):
    env = Env(tmp_path, tailscale_user=YO)
    c = TestClient(entrada.pila_visor_para("tailscale", prod)(create_viewer_app(env.lib, SECRET, lambda: 0, env.cfg)),
                   base_url=VISOR, headers={"Tailscale-User-Login": YO, "X-Forwarded-For": "100.64.0.9"},
                   client=("127.0.0.1", 1))
    assert c.get("/v/x/1/y/").status_code == 404
    assert c.get("/v/x/1/y/", headers={"Host": "evil.example"}).status_code == 400


def test_solo_local_sin_header_tailscale_con_pin_y_csrf(prod, tmp_path):
    base = "http://localhost:8774"
    with cliente(prod, tmp_path, "solo-local", base, {"Origin": base}) as c:
        r = c.post("/api/login", json={"pin": PIN})
        assert r.status_code == 200
        cookie = {"cookie": f"{auth.COOKIE_NAME}={r.cookies[auth.COOKIE_NAME]}"}
        assert c.get("/api/me", headers=cookie).status_code == 200
        assert c.get("/api/me").status_code == 401
        assert c.post("/api/login", json={"pin": PIN}, headers={"Origin": APP}).status_code == 403
        assert c.get("/api/me", headers={"Host": "h.ts.net"}).status_code == 400


def test_pila_para_un_solo_juego_cabeceras_seguridad(prod, tmp_path):
    with cliente(prod, tmp_path, "tailscale", APP, OK) as c:
        r = c.post("/api/login", json={"pin": PIN})
    assert r.status_code == 200
    assert len(r.headers.get_list("content-security-policy")) == 1
    assert len(r.headers.get_list("x-content-type-options")) == 1


def test_visor_pila_rechaza_ip_fuera_cidr(prod, tmp_path):
    env = Env(tmp_path, tailscale_user=YO)
    c = TestClient(entrada.pila_visor_para("tailscale", prod)(create_viewer_app(env.lib, SECRET, lambda: 0, env.cfg)),
                   base_url=VISOR, headers={"Tailscale-User-Login": YO, "X-Forwarded-For": "8.8.8.8"},
                   client=("127.0.0.1", 1))
    assert c.get("/v/x/1/y/").status_code == 403


def test_visor_pila_rechaza_sin_header_tailscale(prod, tmp_path):
    env = Env(tmp_path, tailscale_user=YO)
    c = TestClient(entrada.pila_visor_para("tailscale", prod)(create_viewer_app(env.lib, SECRET, lambda: 0, env.cfg)),
                   base_url=VISOR, headers={"X-Forwarded-For": "100.64.0.9"}, client=("127.0.0.1", 1))
    assert c.get("/v/x/1/y/").status_code == 403


def test_bad_host_lleva_cabeceras_seguridad(prod, tmp_path):
    app = create_app(prod, b"secret", StateStore(tmp_path), dist=tmp_path / "nodist",
                     uploads_dir=tmp_path / "uploads", entrada_interna=False)
    c = TestClient(entrada.pila_para("tailscale", prod)(app), base_url=APP, headers=OK, client=("127.0.0.1", 5000))
    r = c.get("/api/me", headers={"Host": "evil.example"})
    assert r.status_code == 400
    assert "content-security-policy" in r.headers
    assert r.headers.get("cache-control") == "no-store"
