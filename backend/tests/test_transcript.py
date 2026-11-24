import json
import pytest

from conftest import SID
from orquestador.board import session_activity
from orquestador.transcript import TranscriptService, mr_creados_glab_en_transcript, parse_items


def write_rich(projects, count=0):
    lines = [
        {"type": "user", "timestamp": "t1", "message": {"content": "hola"}},
        {"type": "user", "message": {"content": "<system-reminder>x</system-reminder>"}},
        {"type": "user", "message": {"content": "<task-notification>\n<task-id>a</task-id>"}},
        {"type": "user", "isMeta": True, "message": {"content": "Informe de un subagente"}},
        {"type": "user", "promptSource": "system", "message": {"content": "Aviso del sistema"}},
        {"type": "assistant", "timestamp": "t2", "message": {"content": [
            {"type": "thinking", "thinking": "..."},
            {"type": "text", "text": "voy a leer"},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/a/b.py"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "git   status\n" + "x" * 300}},
            {"type": "tool_use", "name": "Other", "input": {"zzz": 1}},
        ]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "SECRETO"}]}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "mirá"}, {"type": "image", "source": {}}]}},
        {"type": "user", "message": {"content": [{"type": "image", "source": {}}]}},
        {"type": "assistant", "message": {"content": "no es lista"}},
    ]
    lines += [{"type": "user", "message": {"content": f"m{i}"}} for i in range(count)]
    path = projects / "-proj" / f"{SID}.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\nbasura\n", encoding="utf-8")
    return path


def test_parse_items_filters_and_shapes(projects):
    items = parse_items(write_rich(projects))
    assert [i["kind"] for i in items] == ["user", "claude", "tool", "tool", "tool", "user", "user"]
    assert items[0] == {"kind": "user", "text": "hola", "ts": "t1"}
    assert items[2] == {"kind": "tool", "name": "Read", "summary": "/a/b.py", "ts": "t2"}
    assert items[3]["summary"].startswith("git status ") and len(items[3]["summary"]) == 160
    assert items[4]["summary"] == ""
    assert items[5]["text"] == "mirá\n[imagen]" and items[6]["text"] == "[imagen]"
    assert "SECRETO" not in json.dumps(items)


def test_clip_at_20000(projects):
    path = projects / "-proj" / f"{SID}.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"content": "a" * 25000}}) + "\n")
    text = parse_items(path)[0]["text"]
    assert len(text) < 20020 and text.endswith("…[recortado]")


def test_pagination_walks_back_to_start(projects):
    write_rich(projects, count=10)
    svc = TranscriptService(__import__("orquestador.digest", fromlist=["x"]).DigestService(projects))
    tail = svc.page(SID, None, 5)
    assert [i["text"] for i in tail["items"]] == ["m5", "m6", "m7", "m8", "m9"]
    seen = list(tail["items"])
    cursor = tail["before"]
    while cursor is not None:
        page = svc.page(SID, cursor, 5)
        seen = page["items"] + seen
        cursor = page["before"]
    assert len(seen) == 17 and seen[0]["text"] == "hola"
    assert svc.page(SID, 9999, 3)["items"][-1]["text"] == "m9"


def test_cache_follows_mtime(projects):
    path = write_rich(projects)
    from orquestador.digest import DigestService
    svc = TranscriptService(DigestService(projects))
    first = svc._items(SID)
    assert svc._items(SID) is first
    path.write_text(path.read_text() + json.dumps({"type": "user", "message": {"content": "nuevo"}}) + "\n")
    assert svc._items(SID)[-1]["text"] == "nuevo"


def test_endpoint_ok(authed, projects):
    write_rich(projects)
    r = authed.get(f"/api/sessions/{SID}/transcript?limit=3")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3 and body["before"] == 4
    assert (body["pane_id"], body["status"], body["title"]) == ("w1:p1", "idle", "Título terminal")
    older = authed.get(f"/api/sessions/{SID}/transcript?limit=200&before=4").json()
    assert len(older["items"]) == 4 and older["before"] is None


def test_endpoint_limit_clamped_and_before_validated(authed, projects):
    write_rich(projects, count=250)
    assert len(authed.get(f"/api/sessions/{SID}/transcript?limit=9999").json()["items"]) == 200
    assert len(authed.get(f"/api/sessions/{SID}/transcript?limit=0").json()["items"]) == 1
    assert authed.get(f"/api/sessions/{SID}/transcript?before=abc").status_code == 422


def test_session_outside_board_404(authed, projects, tmp_path):
    other = "99999999-2222-3333-4444-555555555555"
    (projects / "-proj" / f"{other}.jsonl").write_text('{"type":"user","message":{"content":"x"}}\n')
    assert authed.get(f"/api/sessions/{other}/transcript").status_code == 404


def test_invalid_id_400(authed):
    assert authed.get("/api/sessions/a.b/transcript").status_code == 400
    assert authed.get("/api/sessions/..%2Fx/transcript").status_code in (400, 404)


def test_requires_auth(client):
    assert client.get(f"/api/sessions/{SID}/transcript").status_code == 401


def test_session_activity_map():
    board = {"workspaces": [{"tabs": [{"agents": [{"session_id": "a", "last_activity": "x", "transcript_mtime": "t"},
                                                   {"session_id": None}]}]}]}
    assert session_activity(board) == {"a": "t"}


def test_compact_summary_is_its_own_item(projects):
    path = write_rich(projects)
    extra = {"type": "user", "isCompactSummary": True, "timestamp": "t9",
             "message": {"content": [{"type": "text", "text": "Resumen de lo hecho"}]}}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(extra) + "\n")
    items = parse_items(path)
    assert items[-1] == {"kind": "compact", "text": "Resumen de lo hecho", "ts": "t9"}
    assert not [i for i in items if i["kind"] == "user" and "Resumen" in i["text"]]


def test_pending_cache_is_thread_safe_and_bounded(tmp_path):
    import types
    from concurrent.futures import ThreadPoolExecutor

    paths = {}
    for i in range(40):
        path = tmp_path / f"s{i}.jsonl"
        path.write_text(json.dumps({"type": "user", "message": {"content": "x"}}) + "\n", encoding="utf-8")
        paths[f"s{i}"] = path
    service = TranscriptService(types.SimpleNamespace(find=paths.get))
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(service.pending, [f"s{i % 40}" for i in range(400)]))
    assert all(r is not None for r in results) and len(service._pending_cache) <= 16


def queued_lines(prompt="seguí con eso", **att):
    attachment = {"type": "queued_command", "prompt": prompt, "commandMode": "prompt",
                  "origin": {"kind": "human"}, "timestamp": "t9", "humanTurn": True, **att}
    return [
        {"type": "queue-operation", "operation": "enqueue", "timestamp": "t8", "content": prompt},
        {"type": "queue-operation", "operation": "remove", "content": prompt, "reason": "absorbed_mid_turn"},
        {"type": "attachment", "timestamp": "t9", "attachment": attachment},
    ]


def write_lines(projects, lines):
    path = projects / "-proj" / f"{SID}.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


def test_queued_command_becomes_user_item_in_place(projects):
    lines = [{"type": "user", "timestamp": "t1", "message": {"content": "hola"}},
             {"type": "assistant", "timestamp": "t2", "message": {"content": [{"type": "text", "text": "ok"}]}},
             *queued_lines("mirá esto (Adjunto: /a/b.png)"),
             {"type": "assistant", "timestamp": "t10", "message": {"content": [{"type": "text", "text": "visto"}]}}]
    items = parse_items(write_lines(projects, lines))
    assert [(i["kind"], i.get("text")) for i in items] == [
        ("user", "hola"), ("claude", "ok"), ("user", "mirá esto (Adjunto: /a/b.png)"), ("claude", "visto")]
    assert items[2]["ts"] == "t9"


def test_queued_command_filters(projects):
    lines = [*queued_lines("<system-reminder>x</system-reminder>"),
             *queued_lines("slash", commandMode="slash"),
             *queued_lines("no humano", origin={"kind": "task"}, humanTurn=False),
             *queued_lines("   "),
             {"type": "attachment", "timestamp": "t", "attachment": {"type": "hook_success"}}]
    assert parse_items(write_lines(projects, lines)) == []


def test_queued_command_counts_for_digest(projects):
    from orquestador.digest import parse_transcript
    path = write_lines(projects, queued_lines("hola cola"))
    digest = parse_transcript(path)
    assert digest.turns == [{"role": "user", "text": "hola cola"}]
    assert digest.last_message == "t9"


def test_resumen_de_herramientas_colmena():
    from orquestador.transcript import _tool_summary
    assert _tool_summary({"pane_id": "w3:p1", "texto": "dale\ncon eso"}, "mcp__colmena__mandar") == "w3:p1: dale con eso"
    assert _tool_summary({"id": "e1", "titulo": "Login"}, "mcp__colmena__encargo_crear") == "Login"
    assert _tool_summary({}, "mcp__colmena__tablero") == ""
    assert _tool_summary({"file_path": "/a"}, "Read") == "/a"


def test_session_in_board_without_transcript_is_empty(authed, projects):
    next(projects.glob(f"*/{SID}.jsonl")).unlink()
    r = authed.get(f"/api/sessions/{SID}/transcript")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == [] and body["before"] is None and body["pane_id"] == "w1:p1"


def _svc(projects, count=10):
    write_rich(projects, count=count)
    from orquestador.digest import DigestService
    return TranscriptService(DigestService(projects))


def test_desde_devuelve_solo_la_cola_con_solapamiento(projects):
    svc = _svc(projects)  # 17 items, idx 0..16
    page = svc.page(SID, None, 60, desde=15)
    assert page["before"] == 10  # 15 - K(5)
    assert [i["text"] for i in page["items"]] == ["m3", "m4", "m5", "m6", "m7", "m8", "m9"]
    full = svc.page(SID, None, 60)
    assert page["items"] == full["items"][10:]


def test_desde_cerca_del_inicio_no_baja_de_cero(projects):
    svc = _svc(projects)
    page = svc.page(SID, None, 60, desde=2)
    assert page["before"] is None and len(page["items"]) == 17


def test_desde_pasado_el_final_cae_a_la_pagina_completa(projects):
    svc = _svc(projects)  # transcript truncado o rotado: el cliente conocia mas de lo que hay
    page = svc.page(SID, None, 5, desde=500)
    assert page == svc.page(SID, None, 5)
    assert len(page["items"]) == 5


def test_desde_respeta_el_limite(projects):
    svc = _svc(projects)
    page = svc.page(SID, None, 3, desde=1)
    assert [i["text"] for i in page["items"]] == ["m7", "m8", "m9"] and page["before"] == 14


def test_sin_desde_no_cambia(projects):
    svc = _svc(projects)
    assert svc.page(SID, None, 5)["before"] == 12


class _SinFotos:
    def foto_disponible(self, _id):
        return False

    def lib_ids_for_tool(self, _tid):
        return []


def _con_item_descartado():
    items = [{"kind": "claude", "text": f"m{i}", "name": "", "summary": "", "ts": ""} for i in range(20)]
    items[3] = {"kind": "imagenes", "fotos": [{"id": "x"}], "ts": ""}
    return items, {}


def test_items_llevan_su_indice_absoluto_aunque_se_descarte_uno(tmp_path):
    svc = TranscriptService(None, title_dir=tmp_path)
    svc.library = _SinFotos()
    svc._snapshot = lambda *_a, **_k: {}
    parsed = _con_item_descartado()
    full = svc._pagina("s", parsed, None, 60)
    assert [i["idx"] for i in full["items"]] == [i for i in range(20) if i != 3]
    tail = svc._pagina("s", parsed, None, 60, desde=15)
    assert tail["before"] == 10
    assert [(i["idx"], i["text"]) for i in tail["items"]] == [(i, f"m{i}") for i in range(10, 20)]


# ---------- mr_creados_glab_en_transcript: solo cuenta glab mr create ejecutado ----------

def _glab_transcript(path, cmd, url="https://gitlab.com/grupo/repo7/-/merge_requests/41"):
    lines = [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "tu1", "name": "Bash", "input": {"command": cmd}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tu1", "content": url}]}},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("cmd", [
    "cd /x && ~/.local/bin/glab mr create -R a/b --yes --title x",
    "glab mr create --fill",
    "/usr/bin/glab mr create --fill",
    "ERR=$(mktemp) && glab mr create \\\n  --title x \\\n  --yes",
    "git push; glab mr create --fill",
    "false || glab mr create --fill",
    "echo $(glab mr create --fill)",
    "cat x | glab mr create --fill",
])
def test_glab_mr_create_ejecutado_cuenta(tmp_path, cmd):
    p = _glab_transcript(tmp_path / "t.jsonl", cmd)
    assert mr_creados_glab_en_transcript(p) == [("grupo/repo7", 41)]


@pytest.mark.parametrize("cmd", [
    'grep -c "glab mr create" f.jsonl',
    "grep -oE 'glab mr create[^\"]{0,200}' f",
    'echo "usá glab mr create"',
    "rg 'glab mr create'",
    "grep -c \"glab mr create\" f.jsonl; grep -oE 'https://x/merge_requests/[0-9]+' f.jsonl",
])
def test_glab_mr_create_en_busqueda_no_cuenta(tmp_path, cmd):
    p = _glab_transcript(tmp_path / "t.jsonl", cmd)
    assert mr_creados_glab_en_transcript(p) == []


def test_pending_con_un_resultado_grande_en_paralelo(tmp_path):
    from orquestador.transcript import parse_pending
    p = tmp_path / "s.jsonl"
    relleno = {"type": "user", "message": {"content": "x" * 2000}}
    usos = {"type": "assistant", "version": "2.1.0", "message": {"content": [
        {"type": "tool_use", "id": "toolu_lento", "name": "Bash", "input": {"command": "sleep 60"}},
        {"type": "tool_use", "id": "toolu_rapido", "name": "Read", "input": {"file_path": "/x"}}]}}
    grande = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "toolu_rapido", "content": "y" * 600_000}]}}
    p.write_text("\n".join(json.dumps(o) for o in [relleno] * 3000 + [usos, grande]) + "\n")
    out = parse_pending(p)
    assert [u["id"] for u in out["pendientes"]] == ["toolu_lento"]
    assert out["version"] == "2.1.0"
