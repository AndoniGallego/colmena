import json
import os
import time

from conftest import SID
from orquestador.digest import DigestService
from orquestador.subagentes import SubagentService

SECRET = "sk-SECRETO-123"


def tu(name, inp, mid="m1", model="claude-sonnet-5-5", out=10):
    return {"type": "assistant", "timestamp": "2026-10-01T19:00:00.000Z",
            "message": {"id": mid, "model": model, "usage": {"input_tokens": 5, "output_tokens": out},
                        "content": [{"type": "tool_use", "id": "x", "name": name, "input": inp}]}}


def make_agent(projects, aid, lines, desc="Revisar algo", tool_id="toolu_1", old=0):
    folder = projects / "-proj" / SID / "subagents"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"agent-{aid}.meta.json").write_text(json.dumps(
        {"agentType": "general-purpose", "description": desc, "toolUseId": tool_id, "prompt": SECRET}))
    log = folder / f"agent-{aid}.jsonl"
    log.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    if old:
        t = time.time() - old
        os.utime(log, (t, t))
    return log


def svc(projects):
    d = DigestService(projects)
    return SubagentService(projects, d.find)


def test_working_step_and_no_secrets(tmp_path, projects):
    make_agent(projects, "aaaa1111bbbb", [
        {"type": "user", "timestamp": "2026-10-01T18:59:00.000Z", "message": {"content": SECRET}},
        tu("Read", {"file_path": f"/home/x/{SECRET}/dir/app.py"}, "m1", out=7),
        tu("Bash", {"command": f"curl -H 'Authorization: {SECRET}' x", "description": "Corre los tests"}, "m2", out=3),
    ])
    items = svc(projects).listar(SID)
    assert len(items) == 1
    it = items[0]
    assert it["estado"] == "trabajando" and it["paso"] == "Corriendo: Corre los tests"
    assert it["descripcion"] == "Revisar algo" and it["modelo"] == "sonnet" and it["id"] == "aaaa1111"
    assert it["tokens"] == 20
    assert SECRET not in json.dumps(items)


def test_steps_translation(tmp_path, projects):
    cases = [("Read", {"file_path": "/a/b/c.py"}, "Leyendo c.py"), ("Edit", {"file_path": "/a/z.vue", "new_string": SECRET}, "Editando z.vue"),
             ("Bash", {"command": SECRET}, "Corriendo un comando"), ("Grep", {"pattern": SECRET}, "Buscando en el código"),
             ("WebFetch", {"url": SECRET}, "Buscando en internet"), ("Agent", {"prompt": SECRET}, "Lanzando un agente"),
             ("Foo", {}, "Usando Foo"), ("Bash", {"description": "x" * 200}, "Corriendo: " + "x" * 79 + "…")]
    for n, (name, inp, want) in enumerate(cases):
        make_agent(projects, f"id{n}", [tu(name, inp)], desc=f"d{n}")
    got = {i["descripcion"]: i["paso"] for i in svc(projects).listar(SID)}
    for n, (_, _, want) in enumerate(cases):
        assert got[f"d{n}"] == want
        assert SECRET not in got[f"d{n}"]


def test_finished_by_parent_notification(tmp_path, projects):
    make_agent(projects, "done1", [tu("Read", {"file_path": "a.py"})], tool_id="toolu_done")
    parent = projects / "-proj" / f"{SID}.jsonl"
    parent.write_text(parent.read_text() + json.dumps({"type": "queue-operation", "content":
        "<task-notification>\n<task-id>done1</task-id>\n<tool-use-id>toolu_done</tool-use-id>\n<output-file>/x</output-file>\n<status>completed</status>\n</task-notification>"}) + "\n")
    it = svc(projects).listar(SID)[0]
    assert it["estado"] == "termino" and it["paso"] == "Terminó"


def test_finished_by_handback_and_idle(tmp_path, projects):
    make_agent(projects, "hb", [tu("SubagentHandback", {"message": SECRET})], desc="a")
    make_agent(projects, "idle", [tu("Read", {"file_path": "a.py"})], desc="b", old=3600)
    got = {i["descripcion"]: i for i in svc(projects).listar(SID)}
    assert got["a"]["estado"] == "termino"
    assert got["b"]["estado"] == "sin_actividad" and got["b"]["paso"] == ""
    order = [i["estado"] for i in svc(projects).listar(SID)]
    assert order == ["sin_actividad", "termino"]


def test_tail_only_and_cap(tmp_path, projects):
    big = [tu("Read", {"file_path": "old.py"}, f"m{i}") for i in range(2000)]
    big.append(tu("Edit", {"file_path": "/z/new.py"}, "last"))
    make_agent(projects, "big", big)
    assert svc(projects).listar(SID)[0]["paso"] == "Editando new.py"
    for n in range(40):
        make_agent(projects, f"c{n:02d}", [tu("Read", {"file_path": "a"})], desc=f"c{n}")
    assert len(svc(projects).listar(SID)) == 30


def test_traversal_and_symlinks(tmp_path, projects):
    s = svc(projects)
    assert s.listar("../etc") == [] and s.listar("nada") == []
    outside = tmp_path / "fuera"
    outside.mkdir()
    (outside / "agent-evil.meta.json").write_text(json.dumps({"description": SECRET}))
    (outside / "agent-evil.jsonl").write_text(json.dumps(tu("Read", {"file_path": "a"})) + "\n")
    folder = projects / "-proj" / SID
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "subagents").symlink_to(outside)
    assert s.listar(SID) == []
    (folder / "subagents").unlink()
    real = folder / "subagents"
    real.mkdir()
    (real / "agent-evil.meta.json").symlink_to(outside / "agent-evil.meta.json")
    assert s.listar(SID) == []


def test_endpoint(authed, projects, client):
    make_agent(projects, "ep1", [tu("Glob", {"pattern": "*"})])
    r = authed.get(f"/api/sessions/{SID}/subagentes")
    assert r.status_code == 200 and r.json()["items"][0]["paso"] == "Buscando en el código"
    assert authed.get("/api/sessions/..%2Fx/subagentes").status_code in (400, 404)


def test_endpoint_requires_auth(client, projects):
    assert client.get(f"/api/sessions/{SID}/subagentes").status_code == 401


def test_parent_status_cached_until_parent_changes(tmp_path, projects, monkeypatch):
    from orquestador import subagentes as sa

    parent = projects / "-proj" / f"{SID}.jsonl"
    parent.write_text(json.dumps({"type": "queue-operation", "content":
        "<tool-use-id>toolu_x</tool-use-id><status>completed</status>"}) + "\n")
    s = svc(projects)
    tails = []
    orig_tail = sa._read_tail

    def spy_tail(path, n):
        tails.append(1)
        return orig_tail(path, n)

    monkeypatch.setattr(sa, "_read_tail", spy_tail)
    s._parent_status(parent)
    s._parent_status(parent)
    assert len(tails) == 1
    parent.write_text(parent.read_text() + "\n")
    s._parent_status(parent)
    assert len(tails) == 2
    s._parent_status(parent)
    assert len(tails) == 2
