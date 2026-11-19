import os
import stat
import time

import pytest

from conftest import make_snapshot
from orquestador.enchufe import FakeTerminales
from orquestador import uploads
from orquestador.app import create_app
from orquestador.state import StateStore
from fastapi.testclient import TestClient

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
ID_RE = uploads.UPLOAD_ID_RE


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


def send(authed, name, data, ctype="application/octet-stream"):
    return authed.post("/api/uploads", files={"file": (name, data, ctype)})


def test_png_roundtrip_and_permissions(authed, tmp_path):
    r = send(authed, "Captura de Pantalla Ñandú.PNG", PNG, "image/png")
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "image" and body["size"] == len(PNG) and body["name"] == "Captura de Pantalla Ñandú.PNG"
    assert ID_RE.match(body["id"]) and body["id"].endswith("-captura-de-pantalla-nandu.png")
    path = tmp_path / "uploads" / body["id"]
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
    assert not [p for p in path.parent.iterdir() if p.name.startswith(".tmp")]
    got = authed.get(f"/api/uploads/{body['id']}")
    assert got.status_code == 200 and got.content == PNG
    assert got.headers["content-type"] == "image/png"
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["content-disposition"].startswith("inline")


@pytest.mark.parametrize("name,data,kind", [
    ("a.jpg", b"\xff\xd8\xff\xe0abc", "image"), ("a.gif", b"GIF89a....", "image"),
    ("a.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image"), ("a.heic", b"\x00\x00\x00\x18ftypheic....", "image"),
    ("doc.pdf", b"%PDF-1.7\n...", "pdf"), ("n.md", "años\n".encode(), "text"), ("d.json", b"{}", "text"),
])
def test_allowed_types(authed, name, data, kind):
    r = send(authed, name, data)
    assert r.status_code == 200 and r.json()["kind"] == kind


@pytest.mark.parametrize("name,data", [
    ("a.png", b"GIF89a....."), ("a.jpg", PNG), ("a.pdf", b"hola"), ("a.txt", b"\xff\xfe\x00bad"),
    ("a.txt", b"nul\x00byte"), ("a.svg", b"<svg/>"), ("a.exe", b"MZ"), ("a.zip", b"PK\x03\x04"),
    ("sin_extension", b"hola"), ("a.png", b""),
])
def test_rejected_types(authed, name, data, tmp_path):
    assert send(authed, name, data).status_code == 415
    folder = tmp_path / "uploads"
    assert not folder.exists() or not any(folder.iterdir())


def test_size_limit_streaming(authed, tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_UPLOAD", 1000)
    assert send(authed, "a.txt", b"x" * 1000).status_code == 200
    r = send(authed, "b.txt", b"x" * 1001)
    assert r.status_code == 413
    assert not [p for p in (tmp_path / "uploads").iterdir() if p.name.startswith(".tmp") or "-b." in p.name]


def test_content_length_over_limit_413(authed):
    r = authed.post("/api/uploads", content=b"x", headers={"content-type": "multipart/form-data; boundary=x",
                                                           "content-length": str(uploads.MAX_UPLOAD + 10 ** 6)})
    assert r.status_code == 413


def test_other_routes_keep_small_limit(authed):
    assert authed.post("/api/chat", content=b"x" * 70000).status_code == 413


def test_two_files_or_not_multipart(authed):
    r = authed.post("/api/uploads", files=[("file", ("a.txt", b"x", "text/plain")),
                                           ("file", ("b.txt", b"y", "text/plain"))])
    assert r.status_code == 400
    assert authed.post("/api/uploads", json={"a": 1}).status_code == 415
    assert authed.post("/api/uploads", files={"campo": (None, "solo texto")}).status_code == 400


def test_client_path_in_filename_is_dropped(authed, tmp_path):
    r = send(authed, "../../etc/passwd.txt", b"x")
    assert r.status_code == 200 and r.json()["name"] == "passwd.txt"
    assert (tmp_path / "uploads" / r.json()["id"]).is_file()


def test_same_name_same_second_does_not_collide(authed):
    ids = {send(authed, "a.txt", b"x").json()["id"] for _ in range(3)}
    assert len(ids) == 3


def test_get_text_is_attachment(authed):
    ident = send(authed, "n.txt", b"hola").json()["id"]
    r = authed.get(f"/api/uploads/{ident}")
    assert r.headers["content-disposition"].startswith("attachment")
    assert r.headers["content-type"].startswith("text/plain")


@pytest.mark.parametrize("ident", ["..%2Fstate.json", "x.png", "20250101-000000-%2e%2e.png",
                                   "20250101-000000-a.png", "20250101-000000-a.PNG"])
def test_get_rejects_bad_or_missing_ids(authed, ident):
    assert authed.get(f"/api/uploads/{ident}").status_code == 404


def test_get_symlink_escape_404(authed, tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir(exist_ok=True)
    (tmp_path / "secreto.txt").write_text("s")
    (folder / "20250101-000000-link.txt").symlink_to(tmp_path / "secreto.txt")
    assert authed.get("/api/uploads/20250101-000000-link.txt").status_code == 404


def test_requires_auth(client):
    assert client.post("/api/uploads", files={"file": ("a.txt", b"x")}).status_code == 401
    assert client.get("/api/uploads/20250101-000000-a.txt").status_code == 401


def test_cleanup_removes_only_old(tmp_path):
    old, new = tmp_path / "old.txt", tmp_path / "new.txt"
    old.write_text("x")
    new.write_text("x")
    past = time.time() - 31 * 86400
    os.utime(old, (past, past))
    uploads.cleanup(tmp_path)
    assert not old.exists() and new.exists()


def test_cleanup_runs_at_app_creation(cfg, tmp_path, handoffs):
    folder = tmp_path / "up"
    folder.mkdir()
    old = folder / "20240101-000000-a.txt"
    old.write_text("x")
    past = time.time() - 40 * 86400
    os.utime(old, (past, past))
    t = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    create_app(cfg, b"s", StateStore(tmp_path), dist=tmp_path / "nd", handoffs_dir=handoffs,
               uploads_dir=folder, enchufe=t)
    assert not old.exists()
