import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from biblioteca_support import PROCESO, PNG, SECRET, SID, Env, artifact, result, text_msg, use
from conftest import ORIGIN, PIN
from orquestador import biblioteca as bib
from orquestador.app import create_app
from orquestador.biblioteca_viewer import create_viewer_app
from orquestador.config import hash_pin
from orquestador.state import StateStore

SID2 = "bbbbbbbb-0000-4000-8000-000000000002"
ORIGIN_APP = "https://h.ts.net:8444"


def png(n: int) -> bytes:
    return PNG + n.to_bytes(4, "big") + b"\x00" * 1000


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    e.cfg.pin = hash_pin(PIN)
    return e


def send(env, paths, sid=SID):
    tid = env.tid()
    env.append([use(tid, "SendUserFile", {"files": paths}), result(tid)], sid=sid)


def seed(env):
    a, b = env.file("a.png", png(1)), env.file("b.png", png(2))
    send(env, [a, b])
    env.append([text_msg(PROCESO)])
    env.append([text_msg(PROCESO, uuid="m9")], sid=SID2)
    env.lib.index_all()
    return env.lib


def ids(lib, **match):
    return sorted(i["id"] for i in lib.items.values() if all(i[k] == v for k, v in match.items()))


def blobs(env):
    d = env.data / "biblioteca" / "blobs"
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def test_quitar_removes_persists_and_ignores_unknown(env):
    lib = seed(env)
    imgs = ids(lib, kind="image")
    assert len(lib.items) == 4 and len(blobs(env)) == 2
    assert lib.quitar(imgs[:1] + ["0" * 32, "no-es-id"]) == 1
    assert imgs[0] not in lib.items and len(blobs(env)) == 1
    data = json.loads((env.data / "biblioteca.json").read_text())
    assert imgs[0] in data["quitados"] and imgs[0] not in data["items"]
    again = env.reload()
    assert imgs[0] not in again.items and imgs[0] in again.quitados


def test_missing_quitados_key_is_tolerated(env):
    seed(env).flush()
    p = env.data / "biblioteca.json"
    data = json.loads(p.read_text())
    data.pop("quitados", None)
    p.write_text(json.dumps(data))
    lib = env.reload()
    assert lib.quitados == set() and len(lib.items) == 4


def test_does_not_come_back_after_reindex_same_transcript_or_from_scratch(env):
    lib = seed(env)
    gone = ids(lib, kind="diagrama") + ids(lib, kind="image")[:1]
    lib.quitar(gone)
    env.append([text_msg("otra cosa", uuid="m3")])
    lib.index_all()
    assert not set(gone) & set(lib.items)
    fresh = env.reload()
    fresh.files = {}
    fresh.items = {}
    fresh.index_all()
    assert not set(gone) & set(fresh.items) and len(fresh.items) == 1
    fresh.save()
    assert not set(gone) & set(env.reload().items)


def test_quitar_artifact_survives_new_version(env):
    main = env.file("v/index.html", "<html><title>T</title></html>")
    lines, _ = artifact(env, main)
    env.append(lines)
    env.lib.index_all()
    (item,) = env.lib.items.values()
    assert env.lib.quitar([item["id"]]) == 1
    lines, _ = artifact(env, main, version=2, ts="2026-11-02T10:00:00Z")
    env.append(lines)
    env.lib.index_all()
    assert env.lib.items == {}
    assert env.lib.keymap == {}


def test_shared_blobs_kept_until_last_item_removed(env):
    same = env.file("same.png", png(7))
    send(env, [same, same])
    env.lib.index_all()
    a, b = ids(env.lib)
    assert len(blobs(env)) == 1
    env.lib.quitar([a])
    assert len(blobs(env)) == 1 and env.lib.items[b]["copia"]
    env.lib.quitar([b])
    assert blobs(env) == []
    assert Path(same).exists()


def test_original_files_never_deleted(env):
    a = env.file("a.png", png(1))
    send(env, [a])
    env.lib.index_all()
    env.lib.quitar(list(env.lib.items))
    assert Path(a).read_bytes() == png(1)


def test_viewer_token_gives_404_after_quitar(env):
    a = env.file("a.png", png(1))
    send(env, [a])
    env.lib.index_all()
    (item,) = env.lib.items.values()
    exp, sig = bib.make_token(SECRET, item["id"], 0)
    path = f"/v/{item['id']}/{exp}/{sig}/"
    c = TestClient(create_viewer_app(env.lib, SECRET, lambda: 0, env.cfg), client=("127.0.0.1", 1),
                   base_url="https://h.ts.net:8445")
    assert c.get(path).status_code == 200
    env.lib.quitar([item["id"]])
    assert c.get(path).status_code == 404


@pytest.fixture
def api(env, tmp_path, enchufe):
    env.cfg.claude_cwd = str(tmp_path)
    app = create_app(env.cfg, SECRET, StateStore(env.data), dist=tmp_path / "nodist",
                     uploads_dir=tmp_path / "uploads", library=env.lib, enchufe=enchufe)
    with TestClient(app, headers={"Origin": ORIGIN_APP}, client=("127.0.0.1", 1), base_url=ORIGIN_APP) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def test_endpoint_quita_y_cuenta(env, api):
    lib = seed(env)
    target = ids(lib, kind="diagrama")
    r = api.post("/api/biblioteca/quitar", json={"ids": target + ["0" * 32]})
    assert r.status_code == 200 and r.json() == {"quitados": len(target)}
    assert api.get("/api/biblioteca").json()["total"] == 2


def test_endpoint_rejects_bad_input(env, api):
    seed(env)
    post = api.post
    assert post("/api/biblioteca/quitar", json={"ids": ["../x"]}).status_code == 422
    assert post("/api/biblioteca/quitar", json={"ids": []}).status_code == 422
    assert post("/api/biblioteca/quitar", json={"ids": [5]}).status_code == 422
    assert post("/api/biblioteca/quitar", json={"ids": ["0" * 32] * 501}).status_code == 422
    assert post("/api/biblioteca/quitar", json={"ids": ["0" * 32] * 500}).status_code == 200
    assert post("/api/biblioteca/quitar", content=b"x", headers={"Content-Type": "text/plain"}).status_code == 415
    assert post("/api/biblioteca/quitar", headers={"Origin": "https://h.ts.net:8445"},
                json={"ids": ["0" * 32]}).status_code == 403
    assert post("/api/biblioteca/quitar", headers={"Sec-Fetch-Site": "cross-site"},
                json={"ids": ["0" * 32]}).status_code == 403
    assert len(api.app.state.library.items) == 4


def test_endpoint_requires_auth(env, api):
    seed(env)
    api.cookies.clear()
    assert api.post("/api/biblioteca/quitar", json={"ids": ["0" * 32]}).status_code == 401
    assert len(env.lib.items) == 4


@pytest.fixture
def script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "biblioteca_quitar.py"
    spec = importlib.util.spec_from_file_location("biblioteca_quitar", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_dry_run_lists_without_removing(env, script, capsys):
    lib = seed(env)
    assert script.main(["--kind", "image", "--source", "send_user_file", "--dry-run"], library=lib) == 0
    out = capsys.readouterr().out
    assert "[dry-run] 2" in out and all(i in out for i in ids(lib, kind="image"))
    assert len(lib.items) == 4 and lib.quitados == set()


def test_script_filters_by_kind_and_session_prefix(env, script, capsys):
    lib = seed(env)
    assert script.main(["--kind", "diagrama", "--session", SID2[:8]], library=lib) == 0
    assert "Quitados 1" in capsys.readouterr().out
    assert len(ids(lib, kind="diagrama")) == 1 and ids(lib, kind="diagrama", session_id=SID)
    assert script.main(["--kind", "image", "--source", "send_user_file"], library=lib) == 0
    assert ids(lib, kind="image") == [] and len(lib.items) == 1
    assert env.reload().items.keys() == lib.items.keys()


def test_script_requires_a_filter(env, script):
    with pytest.raises(SystemExit):
        script.main([], library=seed(env))


def test_guardado_diferido_y_flush_corren_bajo_el_lock_del_indexador(env):
    lib = env.lib
    lib.SAVE_DELAY = 60.0
    vistos = []
    real = lib.save
    lib.save = lambda: (vistos.append(lib._index_lock.locked()), real())[1]
    lib._timer_save()
    lib.flush()
    assert vistos == [True, True]
    assert not lib._index_lock.locked()
