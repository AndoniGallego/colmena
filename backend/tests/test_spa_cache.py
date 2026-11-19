from fastapi.testclient import TestClient

from conftest import ORIGIN
from orquestador.app import create_app
from orquestador.state import StateStore


def _client(tmp_path, enchufe, cfg):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>")
    (dist / "sw.js").write_text("// sw")
    (dist / "assets" / "x-abc.js").write_text("export {}")
    app = create_app(cfg, b"s", StateStore(tmp_path), enchufe=enchufe, dist=dist, uploads_dir=tmp_path / "up")
    return TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 1))


def test_spa_cache_headers(tmp_path, enchufe, cfg):
    with _client(tmp_path, enchufe, cfg) as c:
        r = c.get("/assets/x-abc.js")
        assert r.status_code == 200
        assert r.headers.get("cache-control") == "public, max-age=31536000, immutable"
        r = c.get("/sw.js")
        assert r.headers.get("cache-control") == "no-cache"
        r = c.get("/index.html")
        assert r.headers.get("cache-control") == "no-cache"
        r = c.get("/sesion/abc")
        assert r.status_code == 200
        assert "app" in r.text
        assert r.headers.get("cache-control") == "no-cache"
