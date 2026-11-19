import copy
import subprocess

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, SID, make_snapshot
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.config import Config, hash_pin
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.state import StateStore


def _git(cwd, *args):
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(cwd), "PATH": "/usr/bin:/bin"}
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def _cliente(tmp_path, projects, carpeta, permitidas):
    snap = copy.deepcopy(make_snapshot())
    snap["agents"][0]["cwd"] = str(carpeta)
    enchufe = FakeTerminales.desde_snapshot(snap, poll=0.01)
    cfg = Config(pin=hash_pin(PIN), claude_projects_dir=str(projects), claude_cwd=str(tmp_path),
                 plan_cwds=[str(p) for p in permitidas])
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    hub.self_pane_id = "w2:p9"
    handoffs = tmp_path / "handoffs"
    handoffs.mkdir()
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests, dist=tmp_path / "nodist",
                     handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads", enchufe=enchufe)
    c = TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000))
    c.__enter__()
    assert c.post("/api/login", json={"pin": PIN}).status_code == 200
    return c


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repos" / "r"
    r.mkdir(parents=True)
    _git(r, "init", "-q", "-b", "main")
    (r / "a.txt").write_text("uno\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    (r / "a.txt").write_text("uno\ndos\n")
    return r


def test_cambios_de_la_sesion(tmp_path, projects, repo):
    c = _cliente(tmp_path, projects, repo, [repo.parent])
    r = c.get(f"/api/sesiones/{SID}/cambios")
    assert r.status_code == 200
    body = r.json()
    assert body["repo"] is True and body["rama"] == "main" and body["sin_guardar"] == 1
    assert body["archivos"][0]["path"] == "a.txt" and "+dos" in body["archivos"][0]["diff"]


def test_carpeta_no_permitida_403(tmp_path, projects, repo):
    c = _cliente(tmp_path, projects, repo, [tmp_path / "otra"])
    assert c.get(f"/api/sesiones/{SID}/cambios").status_code == 403


def test_sesion_inexistente_404_y_sid_invalido_400(tmp_path, projects, repo):
    c = _cliente(tmp_path, projects, repo, [repo.parent])
    assert c.get("/api/sesiones/nope-nope/cambios").status_code == 404
    assert c.get("/api/sesiones/x%20y/cambios").status_code == 400


def test_refrescar_ignora_el_cache(tmp_path, projects, repo):
    c = _cliente(tmp_path, projects, repo, [repo.parent])
    assert c.get(f"/api/sesiones/{SID}/cambios").json()["archivos"][0]["adds"] == 1
    (repo / "a.txt").write_text("uno\ndos\ntres\n")
    assert c.get(f"/api/sesiones/{SID}/cambios").json()["archivos"][0]["adds"] == 1
    assert c.get(f"/api/sesiones/{SID}/cambios?refrescar=1").json()["archivos"][0]["adds"] == 2


def test_carpeta_que_no_es_repo(tmp_path, projects):
    d = tmp_path / "repos" / "plano"
    d.mkdir(parents=True)
    c = _cliente(tmp_path, projects, d, [d.parent])
    body = c.get(f"/api/sesiones/{SID}/cambios").json()
    assert body["repo"] is False
