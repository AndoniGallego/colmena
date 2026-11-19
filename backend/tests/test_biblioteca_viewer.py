import logging

import pytest
from fastapi.testclient import TestClient

from biblioteca_support import ARTIFACT_URL, PROCESO, PNG, SECRET, SID, Env, artifact, result, text_msg, use
from conftest import ORIGIN, PIN
from orquestador import biblioteca as bib
from orquestador.app import create_app
from orquestador.biblioteca_viewer import create_viewer_app, pdf_csp
from orquestador.config import hash_pin
from orquestador.state import StateStore


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    e.cfg.pin = hash_pin(PIN)
    return e


def seed_html(env, name="v/index.html", body="<html><title>T</title><script src='a.js'></script></html>", **inp):
    main = env.file(name, body)
    env.file("v/a.js", "1")
    env.file("v/datos.json", "{}")
    env.file("v/otro.json", "{}")
    env.file("v/nota.md", "# x")
    inp.setdefault("files", {"datos.json": str(env.scratch / "v/datos.json")})
    lines, tid = artifact(env, main, **inp)
    env.append(lines)
    env.lib.index_all()
    return next(iter(env.lib.items.values()))


def viewer(env, client=("127.0.0.1", 1)):
    app = create_viewer_app(env.lib, SECRET, lambda: env.epoch[0], env.cfg)
    return TestClient(app, client=client, base_url="https://h.ts.net:8445")


def url_for(env, item, rel=""):
    exp, sig = bib.make_token(SECRET, item["id"], env.epoch[0])
    return f"/v/{item['id']}/{exp}/{sig}/{rel}"


def test_html_headers_exact(env):
    item = seed_html(env)
    with viewer(env) as c:
        r = c.get(url_for(env, item), headers={"Cookie": "__Host-orq_session=1"})
    assert r.status_code == 200 and "<title>T</title>" in r.text
    csp = r.headers["content-security-policy"]
    assert csp.startswith("sandbox allow-scripts;") and "allow-same-origin" not in csp
    assert "frame-ancestors https://h.ts.net:8444" in csp and "form-action 'none'" in csp
    assert "https://cdnjs.cloudflare.com" in csp and "unsafe-eval" not in csp
    assert "set-cookie" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["content-type"].startswith("text/html")
    assert "access-control-allow-origin" not in r.headers
    assert "camera=()" in r.headers["permissions-policy"]


def test_asset_headers_and_content(env):
    item = seed_html(env)
    with viewer(env) as c:
        r = c.get(url_for(env, item, "datos.json"))
        assert r.status_code == 200 and r.json() == {} and r.headers["access-control-allow-origin"] == "*"
        assert r.headers["cross-origin-resource-policy"] == "cross-origin"
        assert c.get(url_for(env, item, "../x.js")).status_code == 404
        assert c.get(url_for(env, item, "nada.js")).status_code == 404
        assert c.get(url_for(env, item, "a.js")).status_code == 200
        assert c.get(url_for(env, item, "otro.json")).status_code == 404
        assert c.get(url_for(env, item, "nota.md")).status_code == 404


def test_all_token_failures_identical_404(env):
    item = seed_html(env)
    good = url_for(env, item)
    exp = good.split("/")[3]
    sig = good.split("/")[4]
    bad = [f"/v/{item['id']}/{exp}/{sig[:-1]}/", f"/v/{'0' * 32}/{exp}/{sig}/", f"/v/{item['id']}/1/{sig}/",
           f"/v/{item['id']}/{int(exp) + 10**6}/{sig}/", f"/v/xx/{exp}/{sig}/"]
    with viewer(env) as c:
        bodies = {c.get(u).text + str(c.get(u).status_code) for u in bad}
        assert bodies == {"not found404"}
        env.epoch[0] += 1
        assert c.get(good).status_code == 404


def test_methods_cidr_and_cookie_logging(env, caplog):
    item = seed_html(env)
    with viewer(env) as c:
        assert c.post(url_for(env, item)).status_code == 405
        assert c.put("/anything").status_code == 405
        assert c.head(url_for(env, item)).status_code == 200
    with viewer(env, client=("8.8.8.8", 1)) as c:
        assert c.get(url_for(env, item)).status_code == 403
    caplog.set_level(logging.DEBUG)
    with viewer(env) as c:
        c.get(url_for(env, item), headers={"Cookie": "__Host-orq_session=SECRETO-COOKIE"})
    assert "SECRETO-COOKIE" not in caplog.text


def test_asset_limit_429(env, monkeypatch):
    item = seed_html(env)
    monkeypatch.setattr(bib, "MAX_ASSETS_PER_TOKEN", 3)
    with viewer(env) as c:
        url = url_for(env, item, "a.js")
        codes = [c.get(url).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_pdf_without_sandbox_and_image_and_svg(env):
    pdf = env.file("d.pdf", b"%PDF-1.4 hola")
    png = env.file("i.png", PNG)
    svg = env.file("s.svg", "<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>")
    t = [env.tid() for _ in range(3)]
    env.append([use(t[0], "SendUserFile", {"files": [pdf, png, svg]}), result(t[0])])
    env.lib.index_all()
    by = {i["kind"]: i for i in env.lib.items.values()}
    with viewer(env) as c:
        r = c.get(url_for(env, by["pdf"]))
        assert r.headers["content-type"] == "application/pdf" and "sandbox" not in r.headers["content-security-policy"]
        assert r.headers["content-disposition"] == "inline"
        assert r.headers["content-security-policy"] == pdf_csp()
        assert "frame-ancestors 'none'" in pdf_csp() and "default-src 'none'" in pdf_csp()
        r = c.get(url_for(env, by["image"]))
        assert r.headers["content-type"] == "image/png" and "sandbox" in r.headers["content-security-policy"]
        r = c.get(url_for(env, by["svg"]))
        assert r.headers["content-security-policy"].startswith("sandbox allow-scripts;")


def test_video_range_206(env):
    data = b"\x1a\x45\xdf\xa3" + bytes(range(100))
    vid = env.file("m.webm", data)
    t = env.tid()
    env.append([use(t, "SendUserFile", {"files": [vid]}), result(t)])
    env.lib.index_all()
    item = next(iter(env.lib.items.values()))
    with viewer(env) as c:
        r = c.get(url_for(env, item), headers={"Range": "bytes=10-19"})
        assert r.status_code == 206 and r.content == data[10:20]
        assert r.headers["content-range"] == f"bytes 10-19/{len(data)}"
        assert c.get(url_for(env, item)).content == data
        assert c.get(url_for(env, item), headers={"Range": "bytes=9999-"}).status_code == 416


def test_too_big_and_missing_not_served(tmp_path):
    env = Env(tmp_path, biblioteca_copias=False)
    big = env.file("b.html", b"<html>" + b"a" * (5 * 1024 * 1024))
    lines, _ = artifact(env, big)
    env.append(lines)
    env.lib.index_all()
    item = next(iter(env.lib.items.values()))
    with viewer(env) as c:
        assert c.get(url_for(env, item)).status_code == 404


# ---------- app ----------

@pytest.fixture
def app_client(env, tmp_path, enchufe):
    env.cfg.claude_cwd = str(tmp_path)
    app = create_app(env.cfg, SECRET, StateStore(env.data), dist=tmp_path / "nodist",
                     uploads_dir=tmp_path / "uploads", library=env.lib, enchufe=enchufe)
    with TestClient(app, headers={"Origin": "https://h.ts.net:8444"}, client=("127.0.0.1", 1),
                    base_url="https://h.ts.net:8444") as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def test_api_list_detail_text_sessions(env, app_client):
    seed_html(env)
    md = env.file("n.md", "# Hola\n", where=env.scratch)
    t = env.tid()
    env.append([use(t, "SendUserFile", {"files": [md]}), result(t, ts="2026-11-02T10:00:00Z"),
                {"type": "ai-title", "aiTitle": "Mi sesión"}])
    env.lib.index_all()
    data = app_client.get("/api/biblioteca").json()
    assert data["total"] == 2 and data["indexando"] is False
    html = next(i for i in data["items"] if i["kind"] == "html")
    assert html["src"].startswith("https://h.ts.net:8445/v/") and html["url"] == ARTIFACT_URL
    assert str(env.scratch) not in str(data)
    detail = app_client.get(f"/api/biblioteca/{html['id']}?tipo=html").json()
    assert detail["id"] == html["id"] and "vecinos" in detail
    text = next(i for i in data["items"] if i["kind"] == "text")
    assert app_client.get(f"/api/biblioteca/{text['id']}/texto").json() == {"text": "# Hola\n"}
    assert app_client.get(f"/api/biblioteca/{html['id']}/texto").status_code == 404
    assert app_client.get("/api/biblioteca/" + "0" * 32).status_code == 404
    sess = app_client.get("/api/biblioteca/sesiones").json()
    assert sess[0]["session_id"] == SID and sess[0]["titulo"] == "Mi sesión" and sess[0]["n"] == 2
    assert app_client.get("/api/biblioteca?session=../x").status_code == 400
    assert app_client.get("/api/biblioteca?desde=mañana").status_code == 422
    assert app_client.get("/api/biblioteca?q=" + "a" * 101).status_code == 422


def test_api_requires_login_and_blocks_same_site(env, app_client):
    assert app_client.get("/api/biblioteca", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert app_client.post("/api/chat/stop", headers={"Origin": "https://h.ts.net:8445"}).status_code == 403
    app_client.cookies.clear()
    assert app_client.get("/api/biblioteca").status_code == 401


def test_revoke_all_invalidates_viewer_tokens(env, app_client):
    item = seed_html(env)
    src = app_client.get("/api/biblioteca").json()["items"][0]["src"]
    path = src.replace("https://h.ts.net:8445", "")
    with viewer(env) as v:
        assert v.get(path).status_code == 200
        assert app_client.post("/api/sessions/revoke-all").status_code == 200
        env.epoch[0] = app_client.app.state.epoch()
        assert v.get(path).status_code == 404


def test_sse_biblioteca_event_reaches_subscribers(env, app_client):
    hub = app_client.app.state.hub
    import asyncio
    queue = asyncio.Queue(maxsize=8)
    hub.subscribers.add(queue)
    try:
        env.append([text_msg(PROCESO)])
        env.lib.index_all()
        import time
        deadline = time.time() + 2
        got = None
        while time.time() < deadline and got is None:
            try:
                item = queue.get_nowait()
            except Exception:
                time.sleep(0.01)
                continue
            if isinstance(item, tuple):
                got = item
        assert got and got[0] == "biblioteca" and len(got[1]["nuevos"]) == 1
    finally:
        hub.subscribers.discard(queue)


def test_transcript_items_carry_lib_ids(env, app_client):
    main = env.file("t/index.html")
    lines, tid = artifact(env, main)
    png = env.file("z.png", PNG)
    t2 = env.tid()
    env.append([text_msg("hola\n" + PROCESO, "mm1")] + lines + [use(t2, "SendUserFile", {"files": [png]}), result(t2)])
    env.lib.index_all()
    transcripts = app_client.app.state.hub.digests
    from orquestador.transcript import TranscriptService
    svc = TranscriptService(transcripts)
    svc.library = env.lib
    page = svc.page(SID, None, 50)
    tools = [i for i in page["items"] if i["kind"] == "tool"]
    assert all("lib_ids" in t and "tid" not in t for t in tools) and len(tools) == 2
    claude = [i for i in page["items"] if i["kind"] == "claude"]
    assert len(claude[0]["lib_ids"]) == 1 and "mid" not in claude[0]


def test_viewer_rejects_non_served_kinds(env):
    note = env.file("n.md", "# hola", where=env.home / "Documents")
    tid = env.tid()
    env.append([use(tid, "SendUserFile", {"files": [note]}), result(tid)])
    env.append([text_msg(PROCESO)])
    env.lib.index_all()
    kinds = {i["kind"]: i for i in env.lib.items.values()}
    with viewer(env) as c:
        assert c.get(url_for(env, kinds["text"])).status_code == 404
        assert c.get(url_for(env, kinds["diagrama"])).status_code == 404
    assert env.lib.open_main(kinds["text"]) is None
    assert env.lib.text_of(kinds["text"]["id"]) == "# hola"


def test_rescan_only_on_open_without_cursor(env, app_client, monkeypatch):
    calls = []
    monkeypatch.setattr(env.lib, "rescan_on_demand", lambda: calls.append(1) or False)
    assert app_client.get("/api/biblioteca").status_code == 200
    assert calls == [1]
    app_client.get("/api/biblioteca?cursor=abc")
    app_client.get("/api/biblioteca/sesiones")
    assert calls == [1]
