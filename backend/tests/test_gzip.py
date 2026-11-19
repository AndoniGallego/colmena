from fastapi.testclient import TestClient

from conftest import ORIGIN
from orquestador.app import create_app
from orquestador.state import StateStore


def test_gzip_large_asset(cfg, tmp_path, enchufe):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<h1>app</h1>")
    payload = '{"data":"' + ("x" * 2000) + '"}'
    (dist / "assets" / "big.json").write_text(payload)
    app = create_app(
        cfg,
        b"s",
        StateStore(tmp_path),
        enchufe=enchufe,
        dist=dist,
        uploads_dir=tmp_path / "uploads",
    )
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 1)) as c:
        r = c.get("/assets/big.json", headers={"Accept-Encoding": "gzip, deflate"})
        assert r.status_code == 200
        assert r.headers.get("content-encoding") == "gzip"
