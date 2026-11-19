import json
import os
import time

import pytest

from biblioteca_support import (ARTIFACT_URL, PROCESO, PNG, SECRET, SID, Env, artifact, result, text_msg, use)
from orquestador import biblioteca as bib


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def items(env):
    return sorted(env.lib.items.values(), key=lambda i: i["ts"])


def test_artifact_with_result_and_title(env):
    path = env.file("a/index.html")
    lines, tid = artifact(env, path, description="desc")
    env.append(lines)
    env.lib.index_all()
    [item] = items(env)
    assert item["kind"] == "html" and item["source"] == "artifact"
    assert item["title"] == "Mi página" and item["url"] == ARTIFACT_URL and item["version"] == 1
    assert item["description"] == "desc" and item["exists"] and item["copia"]
    assert bib.ITEM_ID.match(item["id"]) and env.lib.lib_ids_for_tool(tid) == [item["id"]]


def test_artifact_without_tool_use_result_uses_text_and_html_title(env):
    path = env.file("b.html", "<html><title>Del &amp; HTML</title></html>")
    lines, _ = artifact(env, path, tur=False)
    env.append(lines)
    env.lib.index_all()
    [item] = items(env)
    assert item["url"] == ARTIFACT_URL and item["version"] == 1 and item["title"] == "Del & HTML"


def test_error_read_and_asset_are_not_indexed(env):
    path = env.file("c.html")
    err, _ = artifact(env, path, error=True)
    tid = env.tid()
    read = [use(tid, "Artifact", {"action": "read", "url": ARTIFACT_URL}), result(tid, "<html>")]
    tid2 = env.tid()
    asset = [use(tid2, "Artifact", {"asset": True, "url": ARTIFACT_URL, "file_path": path}), result(tid2)]
    env.append(err + read + asset)
    env.lib.index_all()
    assert items(env) == []


def test_type_url_without_file_is_remote(env):
    tid = env.tid()
    env.append([use(tid, "Artifact", {"type_url": "https://claude.ai/types/x", "title": "Deck"}),
                result(tid, "Published", {"url": ARTIFACT_URL, "artifact_id": "AbCdEf123456", "title": "Deck",
                                          "version": 1})])
    env.lib.index_all()
    [item] = items(env)
    assert item["kind"] == "remoto" and item["title"] == "Deck"
    view = env.lib.view_of(item)
    assert not view["servible"] and view["src"] == ""


def test_republish_merges_and_adds_version(env):
    path = env.file("d.html")
    one, _ = artifact(env, path, ts="2026-11-01T10:00:00Z")
    two, _ = artifact(env, path, ts="2026-11-01T11:00:00Z", version=2)
    env.append(one + two)
    env.lib.index_all()
    [item] = items(env)
    assert item["version"] == 2 and [v["version"] for v in item["versions"]] == [1, 2]
    assert item["ts"] == "2026-11-01T11:00:00Z"


def test_duplicate_lines_make_one_item(env):
    path = env.file("e.html")
    lines, _ = artifact(env, path)
    env.append(lines, dup=True)
    png = env.file("p.png", PNG)
    tid = env.tid()
    env.append([use(tid, "SendUserFile", {"files": [png], "caption": "hola"}), result(tid, "1 files delivered")],
               dup=True)
    env.lib.index_all()
    assert len(items(env)) == 2


def test_files_map_with_root_from_and_remote(env):
    main = env.file("f/index.html")
    env.file("f/css/a.css", "body{}")
    env.file("f/img/x.png", PNG)
    lines, _ = artifact(env, main, files={"index.html": main, "css/a.css": {"from": "css/a.css"},
                                          "img/x.png": "img/x.png",
                                          "remote.js": {"artifact": ARTIFACT_URL, "path": "remote.js"}},
                        root=str(env.scratch / "f"))
    env.append(lines)
    env.lib.index_all()
    [item] = items(env)
    assert set(item["assets"]) == {"index.html", "css/a.css", "img/x.png"}
    assert item["assets"]["css/a.css"] == str(env.scratch / "f" / "css" / "a.css")


def test_send_user_file_attachments_and_fallback(env):
    a = env.file("a.png", PNG)
    b = env.file("b.png", PNG)
    pdf = env.file("c.pdf", b"%PDF-1.4 x")
    t1, t2, t3 = env.tid(), env.tid(), env.tid()
    env.append([
        use(t1, "SendUserFile", {"files": [a, b], "caption": "dos"}),
        result(t1, "2 files delivered", {"attachments": [{"path": a, "size": 40}, {"path": b, "size": 40}]}),
        use(t2, "SendUserFile", {"files": [pdf]}), result(t2, "1 files delivered"),
        use(t3, "SendUserFile", {"files": [a]}), result(t3, "boom", error=True),
    ])
    env.lib.index_all()
    kinds = sorted(i["kind"] for i in items(env))
    assert kinds == ["image", "image", "pdf"]
    assert all(i["caption"] == "dos" for i in items(env) if i["kind"] == "image")


def test_diagramas_de_pasos_closed_unclosed_and_two_blocks(env):
    two = "x\n" + PROCESO + "\ntexto\n" + PROCESO.replace("Login", "Otro")
    env.append([text_msg(two, "m1"), text_msg('```diagrama\n{"tipo": "proceso", "pasos": [{"texto": "u"}]}', "m2"),
                text_msg('```diagrama\n{"tipo": "proceso", "nada": 1}\n```', "m3"), text_msg("sin bloque", "m4")])
    env.lib.index_all()
    its = items(env)
    assert sorted(i["title"] for i in its) == ["Diagrama", "Login", "Otro"]
    assert all(i["kind"] == "diagrama" and i["diagrama_raw"] for i in its)
    assert env.lib.lib_ids_for_diagramas(SID, "m1", 0, 2)


def test_subagent_attributed_to_parent_and_invalid_session_ignored(env):
    png = env.file("s.png", PNG)
    tid = env.tid()
    env.append([use(tid, "SendUserFile", {"files": [png]}), result(tid)], sub="abc")
    bad = env.projects / "-proj" / "mala sesion.jsonl"
    bad.write_text("x")
    env.lib.index_all()
    [item] = items(env)
    assert item["session_id"] == SID and item["subagent"] is True
    assert str(bad) not in env.lib.files


def test_incremental_parses_only_delta_and_pending_result_later(env):
    png = env.file("i.png", PNG)
    tid = env.tid()
    env.append([use(tid, "SendUserFile", {"files": [png]})])
    env.lib.index_all()
    assert items(env) == []
    offset = env.lib.files[str(env.transcript_path())]["offset"]
    env.append([result(tid)])
    ids = env.lib.index_sessions([SID])
    assert len(ids) == 1 and env.lib.files[str(env.transcript_path())]["offset"] > offset
    assert env.lib.index_sessions([SID]) == []


def test_delta_does_not_reparse_old_lines(env, monkeypatch):
    lines, _ = artifact(env, env.file("o.html"))
    env.append(lines)
    env.lib.index_all()
    calls = []
    real = env.lib._line
    monkeypatch.setattr(env.lib, "_line", lambda raw, ctx: (calls.append(raw), real(raw, ctx)))
    env.append([text_msg("hola")])
    env.lib.index_all()
    assert len(calls) == 1


def test_truncate_or_new_inode_reindexes_with_stable_ids(env):
    lines, _ = artifact(env, env.file("t.html"))
    env.append(lines)
    env.lib.index_all()
    before = {i["id"] for i in items(env)}
    path = env.transcript_path()
    data = path.read_bytes()
    path.unlink()
    path.write_bytes(data)
    env.lib.index_all()
    assert {i["id"] for i in items(env)} == before and len(items(env)) == 1
    path.write_bytes(data[: len(data) // 2] + b"\n")
    env.lib.index_all()
    assert env.lib.files[str(path)]["size"] == path.stat().st_size


def test_id_stable_across_reindex_and_persisted(env):
    lines, _ = artifact(env, env.file("st.html"))
    env.append(lines)
    env.lib.index_all()
    first = items(env)[0]["id"]
    lib2 = env.reload()
    assert first in lib2.items
    env.transcript_path().unlink()
    lib3 = env.reload()
    lib3.files.clear()
    env.append(lines)
    lib3.index_all()
    assert first in lib3.items and len(lib3.items) == 1


# ---------- rutas ----------

def check(env, path):
    return env.lib.policy.check(path)


def test_paths_roots_hidden_blacklist(env):
    ok = env.file("ok.html")
    assert check(env, ok) is not None
    assert check(env, str(env.home / "x.html")) is not None
    assert check(env, "/etc/passwd") is None
    assert check(env, "relativo.html") is None
    assert check(env, env.file(".ssh/id.html", where=env.home)) is None
    assert check(env, env.file(".env.local", where=env.home)) is None
    for name in ("clave.pem", "id_rsa", "mi-credentials.png", "secret.png", "password.pdf", "token.html", "x.sqlite"):
        assert check(env, env.file(name, PNG)) is None


def test_symlink_out_of_root_rejected(env, tmp_path):
    outside = tmp_path / "outside.html"
    outside.write_text("<html>")
    link = env.scratch / "link.html"
    link.symlink_to(outside)
    assert check(env, str(link)) is None


def _only(env, path, tur=False):
    lines, _ = artifact(env, path, tur=tur)
    env.append(lines)
    env.lib.index_all()
    return items(env)[-1]


def test_unsupported_extension_and_magic_mismatch(env):
    txt = env.file("n.txt", "hola")
    tid = env.tid()
    env.append([use(tid, "SendUserFile", {"files": [txt]}), result(tid)])
    fake = env.file("fake.png", "<html><script>x</script></html>")
    tid2 = env.tid()
    env.append([use(tid2, "SendUserFile", {"files": [fake]}), result(tid2)])
    env.lib.index_all()
    by = {i["path"]: i for i in items(env)}
    assert by[txt]["kind"] == "otro" and by[txt]["motivo"] == "Tipo no soportado"
    assert not by[fake]["allowed"]
    assert env.lib.open_main(by[fake]) is None
    assert not env.lib.view_of(by[txt])["servible"]


def test_other_uid_not_served(env):
    path = env.file("u.html")
    item = _only(env, path)
    env.lib.policy.uid = os.getuid() + 1
    assert env.lib.open_main(item) is None or item["copia"]
    env.lib.cfg.biblioteca_copias = False
    item["copia"] = False
    assert env.lib.open_main(item) is None


def test_deleted_file_exists_false_and_copy_serves(env):
    path = env.file("del.html")
    item = _only(env, path)
    os.unlink(path)
    env.lib._stat.clear()
    view = env.lib.view_of(item)
    assert view["exists"] is False and view["copia"] and view["servible"]
    served = env.lib.open_main(item)
    assert served is not None
    os.close(served.fd)


def test_deleted_file_without_copy_is_404(tmp_path):
    env = Env(tmp_path, biblioteca_copias=False)
    path = env.file("del2.html")
    item = _only(env, path)
    os.unlink(path)
    env.lib._stat.clear()
    view = env.lib.view_of(item)
    assert view["exists"] is False and not view["servible"] and view["motivo"] == "Ya no está en disco"
    assert env.lib.open_main(item) is None


def test_open_checked_rejects_symlink_and_inode_swap(env, monkeypatch):
    real = env.file("r.html")
    link = env.scratch / "l.html"
    link.symlink_to(real)
    assert bib.open_checked(link) is None
    opened = bib.open_checked(bib.Path(real))
    assert opened is not None
    os.close(opened[0])
    real_stat = os.stat

    class Fake:
        st_dev, st_ino, st_mode = 1, 999999, os.stat(real).st_mode

    monkeypatch.setattr(os, "stat", lambda p, *a, **k: Fake if str(p) == real else real_stat(p, *a, **k))
    assert bib.open_checked(bib.Path(real)) is None


def test_size_limit_not_served(tmp_path):
    env = Env(tmp_path, biblioteca_copias=False)
    big = env.file("big.html", b"<html>" + b"a" * (5 * 1024 * 1024))
    item = _only(env, big)
    assert not item["allowed"] and item["motivo"].startswith("Demasiado grande")
    assert env.lib.open_main(item) is None


# ---------- assets ----------

def asset(env, item, rel):
    s = env.lib.open_asset(item, rel)
    if s:
        os.close(s.fd)
    return s


def test_assets_declared_and_subtree_and_rejections(env):
    main = env.file("w/index.html")
    env.file("w/css/a.css", "body{}")
    env.file("w/datos.json", "{}")
    env.file("other/secret.js", "1", )
    env.file("w/.hidden.js", "1")
    env.file("w/clave.pem", "x")
    declared = env.file("elsewhere/lib.js", "1")
    decl_json = env.file("elsewhere/cfg.json", "{}")
    lines, _ = artifact(env, main, files={"vendor/lib.js": declared, "cfg.json": decl_json,
                                          "remote.js": {"artifact": ARTIFACT_URL, "path": "r"}})
    env.append(lines)
    env.lib.index_all()
    [item] = items(env)
    assert asset(env, item, "css/a.css") and asset(env, item, "vendor/lib.js") and asset(env, item, "cfg.json")
    assert asset(env, item, "datos.json") is None
    for bad in ("../other/secret.js", "%2e%2e/other/secret.js", "%252e%252e/x.js", "a\\b.js", "a\x00b.js", "/etc/passwd",
                ".hidden.js", "w/../x.js", "css//a.css", "./css/a.css", "clave.pem", "remote.js", "nada.js",
                "x/" * 13 + "a.js", "a" * 600 + ".js"):
        assert asset(env, item, bad) is None, bad


def test_html_in_home_has_no_relative_assets(env):
    main = env.file("repo/index.html", where=env.home)
    env.file("repo/app.js", "1", where=env.home)
    tid = env.tid()
    env.append([use(tid, "SendUserFile", {"files": [main]}), result(tid)])
    env.lib.index_all()
    [item] = items(env)
    assert item["kind"] == "html"
    item = dict(item, kind="html")
    assert env.lib.open_main(item) is not None
    assert asset(env, item, "app.js") is None


def test_asset_served_from_copy_after_deletion(env):
    main = env.file("c1/index.html")
    css = env.file("c1/a.css", "body{}")
    lines, _ = artifact(env, main)
    env.append(lines)
    env.lib.index_all()
    [item] = items(env)
    os.unlink(css)
    assert asset(env, item, "a.css") is not None
    assert asset(env, item, "zzz.css") is None


# ---------- tokens ----------

def test_token_valid_and_failures():
    ident = "a" * 32
    now = 1_800_000_000
    exp, sig = bib.make_token(SECRET, ident, 0, now)
    assert bib.token_valid(SECRET, ident, str(exp), sig, 0, now)
    assert not bib.token_valid(SECRET, ident, str(exp), sig, 0, now + 31 * 60)
    far, farsig = bib.make_token(SECRET, ident, 0, now + 3600)
    assert not bib.token_valid(SECRET, ident, str(far), farsig, 0, now)
    assert not bib.token_valid(SECRET, "b" * 32, str(exp), sig, 0, now)
    assert not bib.token_valid(SECRET, ident, str(exp), sig, 1, now)
    assert not bib.token_valid(SECRET, ident, str(exp), sig[:-1], 0, now)
    assert not bib.token_valid(SECRET, ident, str(exp), sig.replace(sig[0], "!", 1), 0, now)


# ---------- consultas ----------

def test_listing_filters_search_pagination_and_no_abs_path(env):
    for n in range(5):
        env.append([text_msg(PROCESO.replace("Login", f"Proceso número {n}"), f"mm{n}", ts=f"2026-11-0{n + 1}T10:00:00Z")])
    png = env.file("acción.png", PNG)
    tid = env.tid()
    env.append([use(tid, "SendUserFile", {"files": [png], "caption": "Gráfico ÚLTIMO"}), result(tid, ts="2026-10-20T10:00:00Z")])
    env.lib.index_all()
    full = env.lib.listing(limit=3)
    assert full["total"] == 6 and len(full["items"]) == 3 and full["cursor"]
    nxt = env.lib.listing(cursor=full["cursor"], limit=3)
    seen = {i["id"] for i in full["items"]} | {i["id"] for i in nxt["items"]}
    assert len(seen) == 6 and nxt["cursor"] is None
    assert env.lib.listing(q="ultimo")["total"] == 1
    assert env.lib.listing(q="ACCION")["total"] == 1
    assert env.lib.listing(tipo="image,pdf")["total"] == 1
    assert env.lib.listing(desde="2026-11-03", hasta="2026-11-04")["total"] == 2
    assert env.lib.listing(session="otra")["total"] == 0
    dump = str(env.lib.listing())
    assert str(env.scratch) not in dump and "/tmp" not in dump
    img = next(i for i in env.lib.listing(tipo="image")["items"])
    assert img["nombre"] == "acción.png" and img["donde"] == "scratchpad" and "/v/" in img["src"]


def test_detail_neighbors_and_donde_home(env):
    home_png = env.file("proy/g.png", PNG, where=env.home)
    tids = [env.tid(), env.tid()]
    env.append([use(tids[0], "SendUserFile", {"files": [home_png]}), result(tids[0], ts="2026-11-01T09:00:00Z"),
                use(tids[1], "SendUserFile", {"files": [env.file("h.png", PNG)]}), result(tids[1], ts="2026-11-01T10:00:00Z")])
    env.lib.index_all()
    ids = [i["id"] for i in env.lib.listing()["items"]]
    detail = env.lib.detail(ids[0])
    assert detail["vecinos"] == {"anterior": None, "siguiente": ids[1]}
    assert env.lib.detail(ids[1])["donde"] == "~/proy/g.png"
    assert env.lib.detail("0" * 32) is None and env.lib.detail("../x") is None


def test_viewer_origin_missing_means_no_src(tmp_path):
    env = Env(tmp_path)
    env.cfg.viewer_origin = ""
    _only(env, env.file("z.html"))
    assert env.lib.listing()["items"][0]["src"] == ""


def test_purge_by_copy_age(env):
    item = _only(env, env.file("old.html"))
    item["ts"] = "2999-01-01T00:00:00Z"
    item["copied_at"] = time.time() - (bib.COPY_DAYS + 1) * 86400
    env.lib.purge()
    assert item["copia"] is False and not list((env.lib.copies / "blobs").iterdir())


def test_listener_called_with_new_ids(env):
    got = []
    env.lib.listeners.append(got.append)
    env.append([text_msg(PROCESO)])
    env.lib.index_all()
    assert len(got) == 1 and len(got[0]) == 1
    env.lib.index_all()
    assert len(got) == 1


def test_rescan_on_demand_throttled(env):
    now = [1000.0]
    env.lib.clock = lambda: now[0]
    env.lib._last_scan = 1000.0
    assert env.lib.rescan_on_demand() is False
    now[0] += bib.RESCAN_THROTTLE + 1
    assert env.lib.rescan_on_demand() is True
    assert env.lib.rescan_on_demand() is False


def test_extract_bloques_pasos_unit():
    assert bib.extract_bloques("nada") == []
    assert len(bib.extract_bloques(PROCESO + "\n~~~diagrama\n{\"tipo\": \"secuencia\", \"pasos\": [1]}\n~~~")) == 2
    assert bib.extract_bloques('```diagrama\n{"tipo": "proceso", "pasos": []}\n```') == []
    assert bib.extract_bloques('```diagrama\n{"tipo": "proceso", "pasos": [1],}\n```')
    assert bib.extract_bloques('```diagrama\n{"tipo": "raro", "nodos": [{"id": "a"}]}\n```') == []


DIAGRAMA = ('```diagrama\n{"titulo": "Arquitectura", "nodos": [{"id": "app", "nombre": "La app"}, '
            '{"id": "srv", "nombre": "El servidor"}], "conexiones": [{"de": "app", "a": "srv"}]}\n```')


def test_diagramas_of_every_tipo_indexed_in_order(env):
    mixed = "x\n" + DIAGRAMA + "\ny\n" + PROCESO
    env.append([text_msg(mixed, "m1"), text_msg('```diagrama\n{"nodos": []}\n```', "m2"),
                text_msg('```diagrama\n{"pasos": [{"texto": "u"}]}\n```', "m3"),
                text_msg('~~~diagrama\n{"nodos": [{"id": "a"}],}\n~~~', "m4")])
    env.lib.index_all()
    its = items(env)
    assert sorted(i["title"] for i in its) == ["Arquitectura", "Diagrama", "Login"]
    assert all(i["diagrama_raw"] and i["kind"] == i["source"] == "diagrama" for i in its)
    ids = env.lib.lib_ids_for_diagramas(SID, "m1", 0, 2)
    assert [env.lib.items[i]["title"] for i in ids] == ["Arquitectura", "Login"]
    assert len(env.lib.filtered(tipo="diagrama")) == 3
    view = env.lib.view_of(env.lib.items[ids[0]])
    assert view["exists"] and not view["servible"] and view["src"] == ""


def test_extract_bloques_strict_shape_and_limits():
    assert bib.extract_bloques("nada") == []
    [(body, title)] = bib.extract_bloques(DIAGRAMA)
    assert title == "Arquitectura" and body.startswith("{")
    assert bib.extract_bloques('```diagrama\n{"nodos": "x"}\n```') == []
    assert bib.extract_bloques('```diagrama\n{"nodos": [1, "a"]}\n```') == []
    assert bib.extract_bloques('```diagrama\n{"nodos": [{"id": ""}]}\n```') == []
    assert bib.extract_bloques('```diagrama\n{"nodos": [{"id": "a"}], "conexiones": "x"}\n```') == []
    many = json.dumps({"nodos": [{"id": f"n{i}"} for i in range(bib.MAX_DIAGRAMA_NODOS + 1)]})
    assert bib.extract_bloques(f"```diagrama\n{many}\n```") == []
    edges = json.dumps({"nodos": [{"id": "a"}], "conexiones": [{"de": "a", "a": "a"}] * (bib.MAX_DIAGRAMA_CONEXIONES + 1)})
    assert bib.extract_bloques(f"```diagrama\n{edges}\n```") == []
    huge = json.dumps({"nodos": [{"id": "a", "nombre": "x" * (bib.MAX_DIAGRAMA_BYTES + 1)}]})
    assert bib.extract_bloques(f"```diagrama\n{huge}\n```") == []
    assert bib.extract_bloques(DIAGRAMA + "\n" + PROCESO)[1] == (PROCESO.split("\n")[1], "Login")


def test_index_second_pass_without_changes_skips_save(env, monkeypatch):
    from orquestador import biblioteca as bibmod

    env.append([text_msg(PROCESO)])
    env.lib.index_all()
    writes = []
    orig = bibmod.private_write

    def spy(path, text):
        writes.append((path, text))
        return orig(path, text)

    monkeypatch.setattr(bibmod, "private_write", spy)
    env.lib.index_all()
    bib_writes = [w for w in writes if w[0] == env.lib.path]
    assert bib_writes == []


def test_index_purge_throttled_twice_one_run(env, monkeypatch):
    purge_calls = []
    orig = env.lib.purge

    def spy_purge():
        purge_calls.append(1)
        return orig()

    env.lib.PURGE_GC_INTERVAL = 600.0
    env.lib._last_purge_gc = env.lib.clock() - env.lib.PURGE_GC_INTERVAL - 1
    monkeypatch.setattr(env.lib, "purge", spy_purge)
    env.lib._index([])
    env.lib._index([])
    assert len(purge_calls) == 1


def test_index_purge_runs_each_pass_with_zero_interval(env, monkeypatch):
    purge_calls = []
    orig = env.lib.purge

    def spy_purge():
        purge_calls.append(1)
        return orig()

    env.lib.PURGE_GC_INTERVAL = 0.0
    env.lib._last_purge_gc = 0.0
    monkeypatch.setattr(env.lib, "purge", spy_purge)
    env.lib._index([])
    env.lib._index([])
    assert len(purge_calls) == 2


def _spy_writes(env, monkeypatch):
    from orquestador import biblioteca as bibmod

    writes = []
    orig = bibmod.private_write

    def spy(path, text):
        writes.append(path)
        return orig(path, text)

    monkeypatch.setattr(bibmod, "private_write", spy)
    return lambda: len([w for w in writes if w == env.lib.path])


def test_two_indexations_within_window_write_once(env, monkeypatch):
    env.lib.SAVE_DELAY = 60.0
    n = _spy_writes(env, monkeypatch)
    lines, _ = artifact(env, env.file("w1.html"))
    env.append(lines)
    env.lib.index_all()
    lines2, _ = artifact(env, env.file("w2.html"), ts="2026-11-01T10:01:00Z")
    env.append(lines2)
    env.lib.index_all()
    assert n() == 0
    env.lib.flush()
    assert n() == 1
    env.lib.flush()
    assert n() == 1


def test_flush_writes_pending_index(env):
    env.lib.SAVE_DELAY = 60.0
    lines, _ = artifact(env, env.file("fl.html"))
    env.append(lines)
    env.lib.index_all()
    assert not env.lib.path.exists()
    env.lib.flush()
    assert env.lib.path.exists()
    assert len(env.reload().items) == 1


def test_reindexing_same_span_after_crash_does_not_duplicate(env):
    env.lib.SAVE_DELAY = 60.0
    lines, _ = artifact(env, env.file("cr.html"))
    env.append(lines)
    env.lib.index_all()
    first = items(env)[0]["id"]
    lib2 = env.reload()
    lib2.index_all()
    assert list(lib2.items) == [first]


def _pruebas(casos, titulo="Informe de pruebas", fence="```"):
    return f"{fence}pruebas\n" + json.dumps({"titulo": titulo, "casos": casos}) + f"\n{fence}"


def test_extract_pruebas_valida_y_normaliza():
    ok = bib.extract_pruebas(_pruebas([{"nombre": "a", "resultado": "OK"}, {"nombre": "b", "resultado": "raro"},
                                       {"nombre": "c", "resultado": "falla", "detalle": "x"}]))
    assert len(ok) == 1
    data = json.loads(ok[0][0])
    assert [c["resultado"] for c in data["casos"]] == ["ok", "falla"] and ok[0][1] == "Informe de pruebas"
    assert bib.extract_pruebas(_pruebas([{"nombre": "a", "resultado": "raro"}])) == []
    assert bib.extract_pruebas(_pruebas([])) == []
    assert bib.extract_pruebas(_pruebas([{"nombre": "a", "resultado": "ok"}], titulo="")) == []
    assert len(bib.extract_pruebas(_pruebas([{"nombre": "a", "resultado": "ok"}], fence="~~~"))) == 1


def test_pruebas_item_en_biblioteca(env):
    casos = [{"nombre": f"c{i}", "resultado": "ok"} for i in range(11)] + [{"nombre": "z", "resultado": "falla"}]
    env.append([text_msg("hola\n" + _pruebas(casos), "m1"), text_msg("nada de pruebas", "m2")])
    env.lib.index_all()
    [item] = items(env)
    assert item["kind"] == item["source"] == "pruebas" and item["title"] == "Informe de pruebas"
    assert item["description"] == "11 ok · 1 falla"
    assert json.loads(item["pruebas_raw"])["casos"][0]["nombre"] == "c0"
    assert item["diagrama_raw"] is None
    assert len(env.lib.filtered(tipo="pruebas")) == 1
    view = env.lib.view_of(item)
    assert view["pruebas_raw"] == item["pruebas_raw"] and view["evidencias"] == {}


def test_pruebas_y_diagrama_en_el_mismo_mensaje_no_chocan(env):
    env.append([text_msg(PROCESO + "\n" + _pruebas([{"nombre": "a", "resultado": "omitida"}]), "m1")])
    env.lib.index_all()
    assert sorted(i["kind"] for i in items(env)) == ["diagrama", "pruebas"]


def test_pruebas_evidencia_se_copia_como_captura(env):
    img = env.file("ev.png", PNG)
    txt = env.file("nota.txt", "hola")
    fuera = "/etc/passwd"
    casos = [{"nombre": "a", "resultado": "ok", "evidencia": img},
             {"nombre": "b", "resultado": "ok", "evidencia": txt},
             {"nombre": "c", "resultado": "ok", "evidencia": fuera},
             {"nombre": "d", "resultado": "ok", "evidencia": img + ".no"}]
    env.append([text_msg(_pruebas(casos), "m1")])
    env.lib.index_all()
    pr = [i for i in items(env) if i["kind"] == "pruebas"]
    caps = [i for i in items(env) if i["source"] == "captura"]
    assert len(pr) == 1 and len(caps) == 1
    assert pr[0]["evidencias"] == {img: caps[0]["id"]} and caps[0]["copia"]
    assert env.lib.captura_ruta_lookup(SID)(img) == caps[0]["id"]
    os.unlink(img)
    assert env.reload() is not None


def test_pruebas_evidencia_reusa_captura_existente(env):
    img = env.file("ev.png", PNG)
    env.append([text_msg(_pruebas([{"nombre": "a", "resultado": "ok", "evidencia": img}]), "m1")])
    env.lib.index_all()
    env.append([text_msg(_pruebas([{"nombre": "a", "resultado": "ok", "evidencia": img}], titulo="Otro"), "m2")])
    env.lib.index_all()
    assert len([i for i in items(env) if i["source"] == "captura"]) == 1
    assert all(len(i["evidencias"]) == 1 for i in items(env) if i["kind"] == "pruebas")
