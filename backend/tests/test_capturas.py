import base64
import json

import pytest
from fastapi.testclient import TestClient

from biblioteca_support import PNG, SECRET, SID, Env, result, use
from conftest import PIN
from orquestador import biblioteca as bib
from orquestador.biblioteca_viewer import create_viewer_app
from orquestador.config import hash_pin
from orquestador.transcript import parse_file

# JPEG mínimo válido (1x1)
JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x03\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xaa\xff\xd9"
)

FAKE_SVG = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'


def img_block(data: bytes, media: str = "image/png"):
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": base64.b64encode(data).decode()}}


def tool_result_images(tid, images, ts="2026-11-01T10:00:05Z", error=False):
    content = [{"type": "tool_result", "tool_use_id": tid, "content": images,
                **({"is_error": True} if error else {})}]
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": content}}


def chrome_use(tid, ts="2026-11-01T10:00:00Z"):
    return use(tid, "mcp__claude-in-chrome__computer", {"action": "screenshot"}, ts=ts)


def read_use(tid, path, ts="2026-11-01T10:00:00Z"):
    return use(tid, "Read", {"file_path": path}, ts=ts)


def captura_id(session_id: str, sha: str) -> str:
    return bib.item_id(session_id, f"c:{sha}", 0)


def sha_of(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def env(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    e = Env(tmp_path)
    e.cfg.pin = hash_pin(PIN)
    e.lib.uploads_dir = uploads
    return e


def items(env):
    return sorted(env.lib.items.values(), key=lambda i: i["ts"])


def test_tool_result_png_indexed_as_captura(env):
    tid = env.tid()
    env.append([chrome_use(tid), tool_result_images(tid, [img_block(PNG)])])
    env.lib.index_all()
    [item] = [i for i in items(env) if i.get("source") == "captura"]
    sha = sha_of(PNG)
    assert item["kind"] == "image" and item["copia"]
    assert item["title"] == "Captura del navegador"
    assert item["keys"] == [f"c:{sha}"]
    assert item["id"] == captura_id(SID, sha)
    assert (env.lib.copies / "blobs" / sha).is_file()


def test_same_image_twice_one_item(env):
    tid1, tid2 = env.tid(), env.tid()
    env.append([
        chrome_use(tid1), tool_result_images(tid1, [img_block(PNG)], ts="2026-11-01T10:00:00Z"),
        chrome_use(tid2), tool_result_images(tid2, [img_block(PNG)], ts="2026-11-01T10:01:00Z"),
    ])
    env.lib.index_all()
    caps = [i for i in items(env) if i.get("source") == "captura"]
    assert len(caps) == 1


def test_svg_and_bad_magic_skipped(env):
    tid = env.tid()
    env.append([read_use(tid, "/x.png"), tool_result_images(tid, [
        img_block(FAKE_SVG, "image/svg+xml"),
        img_block(b"not-a-png", "image/png"),
    ])])
    env.lib.index_all()
    assert [i for i in items(env) if i.get("source") == "captura"] == []


def test_oversized_image_skipped(env, monkeypatch):
    monkeypatch.setattr(bib, "CAPTURA_MAX", 50)
    tid = env.tid()
    big = PNG + b"\x00" * 100
    env.append([chrome_use(tid), tool_result_images(tid, [img_block(big)])])
    env.lib.index_all()
    assert [i for i in items(env) if i.get("source") == "captura"] == []


def test_read_from_uploads_dir_skipped(env):
    up = env.lib.uploads_dir / "20260101-x.png"
    up.write_bytes(PNG)
    tid = env.tid()
    env.append([read_use(tid, str(up)), tool_result_images(tid, [img_block(PNG)])])
    env.lib.index_all()
    assert [i for i in items(env) if i.get("source") == "captura"] == []


def test_user_attachment_not_indexed(env):
    line = {"type": "user", "timestamp": "2026-11-01T10:00:00Z",
            "message": {"role": "user", "content": [img_block(PNG), {"type": "text", "text": "mirá"}]}}
    env.append([line])
    env.lib.index_all()
    assert [i for i in items(env) if i.get("source") == "captura"] == []


def test_read_title_uses_basename(env):
    path = env.file("capturas/pantalla.png", PNG)
    tid = env.tid()
    env.append([read_use(tid, path), tool_result_images(tid, [img_block(PNG)])])
    env.lib.index_all()
    [item] = [i for i in items(env) if i.get("source") == "captura"]
    assert item["title"] == "pantalla.png"


def test_transcript_groups_and_splits(env):
    t1, t2, t3, t4 = env.tid(), env.tid(), env.tid(), env.tid()
    sha = sha_of(JPEG)
    iid = captura_id(SID, sha)
    lines = [
        chrome_use(t1), tool_result_images(t1, [img_block(JPEG, "image/jpeg")]),
        chrome_use(t2), tool_result_images(t2, [img_block(JPEG, "image/jpeg")]),
        chrome_use(t3), tool_result_images(t3, [img_block(JPEG, "image/jpeg")]),
        {"type": "assistant", "timestamp": "2026-11-01T10:02:00Z", "uuid": "c1",
         "message": {"content": [{"type": "text", "text": "Entre medio"}]}},
        chrome_use(t4), tool_result_images(t4, [img_block(JPEG, "image/jpeg")], ts="2026-11-01T10:03:05Z"),
    ]
    env.append(lines)
    path = env.transcript_path()
    parsed, _ = parse_file(path)
    imgs = [i for i in parsed if i["kind"] == "imagenes"]
    assert len(imgs) == 2
    assert len(imgs[0]["fotos"]) == 3
    assert imgs[0]["fotos"][0]["id"] == iid
    assert len(imgs[1]["fotos"]) == 1
    raw = path.read_text()
    assert "base64" not in raw or all("fotos" in json.dumps(i) for i in imgs)
    assert not any("data" in json.dumps(i) for i in parsed if i["kind"] == "imagenes")


def test_transcript_no_base64_in_items(env):
    tid = env.tid()
    env.append([chrome_use(tid), tool_result_images(tid, [img_block(PNG)])])
    items_p, _ = parse_file(env.transcript_path())
    blob = json.dumps(items_p)
    assert "/9j/" not in blob and "iVBOR" not in blob


def test_serve_captura_bytes(env):
    tid = env.tid()
    env.append([chrome_use(tid), tool_result_images(tid, [img_block(PNG)])])
    env.lib.index_all()
    item = next(i for i in items(env) if i.get("source") == "captura")
    app = create_viewer_app(env.lib, SECRET, lambda: env.epoch[0], env.cfg)
    exp, sig = bib.make_token(SECRET, item["id"], env.epoch[0])
    with TestClient(app, client=("127.0.0.1", 1), base_url="https://h.ts.net:8445") as c:
        r = c.get(f"/v/{item['id']}/{exp}/{sig}/")
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_biblioteca_detail_servible(env):
    tid = env.tid()
    env.append([chrome_use(tid), tool_result_images(tid, [img_block(PNG)])])
    env.lib.index_all()
    item = next(i for i in items(env) if i.get("source") == "captura")
    view = env.lib.detail(item["id"])
    assert view["source"] == "captura" and view["servible"] and view["src"]


class _Digests:
    def __init__(self, path):
        self.path = path

    def find(self, session_id):
        return self.path


def _service(env, tmp_path):
    from orquestador.transcript import TranscriptService
    svc = TranscriptService(_Digests(env.transcript_path()), title_dir=tmp_path / "t", ctx_dir=tmp_path / "c")
    svc.library = env.lib
    return svc


def test_page_drops_fotos_not_in_library(env, tmp_path):
    up = env.lib.uploads_dir / "20260101-x.png"
    up.write_bytes(PNG)
    t1, t2 = env.tid(), env.tid()
    env.append([read_use(t1, str(up)), tool_result_images(t1, [img_block(PNG)]),
                chrome_use(t2), tool_result_images(t2, [img_block(JPEG, "image/jpeg")])])
    page = _service(env, tmp_path).page(SID, None, 50)
    [grupo] = [i for i in page["items"] if i["kind"] == "imagenes"]
    assert [f["id"] for f in grupo["fotos"]] == [captura_id(SID, sha_of(JPEG))]


def test_page_omits_group_when_all_fotos_missing(env, tmp_path):
    up = env.lib.uploads_dir / "20260101-x.png"
    up.write_bytes(PNG)
    tid = env.tid()
    env.append([read_use(tid, str(up)), tool_result_images(tid, [img_block(PNG)])])
    page = _service(env, tmp_path).page(SID, None, 50)
    assert [i for i in page["items"] if i["kind"] == "imagenes"] == []


def test_page_does_not_rewrite_index_when_unchanged(env, tmp_path, monkeypatch):
    tid = env.tid()
    env.append([chrome_use(tid), tool_result_images(tid, [img_block(PNG)])])
    svc = _service(env, tmp_path)
    svc.page(SID, None, 50)
    calls = []
    monkeypatch.setattr(env.lib, "save", lambda: calls.append(1))
    svc.page(SID, None, 50)
    svc.page(SID, None, 50)
    assert calls == []


def test_pending_keeps_only_needed_input(env):
    tid = env.tid()
    env.append([use(tid, "Write", {"file_path": "/x/y.txt", "content": "SECRETO" * 100})])
    env.lib.index_all()
    state = json.dumps(env.lib.files)
    assert "SECRETO" not in state


def chrome_result(tid, images, screenshot_path=None, ts="2026-11-01T10:00:05Z", error=False):
    pieces = []
    if screenshot_path:
        pieces.append({"type": "text", "text": f"Screenshot saved to: {screenshot_path}"})
    pieces.extend(images)
    return tool_result_images(tid, pieces, ts=ts, error=error)


def _simular_indice_sin_capturas(env):
    path = env.transcript_path()
    st = path.stat()
    key = str(path)
    env.lib.files[key] = {
        "inode": st.st_ino,
        "size": st.st_size,
        "offset": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "pending": {},
        "cwd": "",
    }
    env.lib.save()


def test_backfill_indexa_capturas_con_offset_al_final(env):
    tid = env.tid()
    shot = "/tmp/claude-chrome-screenshots-abc/screenshot-1-0.jpg"
    env.append([chrome_use(tid), chrome_result(tid, [img_block(PNG)], shot)])
    _simular_indice_sin_capturas(env)
    assert [i for i in items(env) if i.get("source") == "captura"] == []
    env.lib.run_capturas_backfill()
    caps = [i for i in items(env) if i.get("source") == "captura"]
    assert len(caps) == 1
    assert caps[0].get("ruta") == shot
    assert env.lib.files[str(env.transcript_path())]["offset"] == env.transcript_path().stat().st_size
    env.lib.run_capturas_backfill()
    assert len([i for i in items(env) if i.get("source") == "captura"]) == 1


def test_backfill_respeta_quitados(env):
    tid = env.tid()
    env.append([chrome_use(tid), chrome_result(tid, [img_block(PNG)])])
    _simular_indice_sin_capturas(env)
    iid = captura_id(SID, sha_of(PNG))
    env.lib.quitados.add(iid)
    env.lib.save()
    env.lib.run_capturas_backfill()
    assert iid not in env.lib.items


def test_captura_guarda_indice_ruta(env):
    tid = env.tid()
    shot = "/tmp/claude-chrome-screenshots-x/screenshot-2-0.jpg"
    env.append([chrome_use(tid), chrome_result(tid, [img_block(PNG)], shot)])
    env.lib.index_all()
    item = next(i for i in items(env) if i.get("source") == "captura")
    assert env.lib.captura_id_for_ruta(SID, shot) == item["id"]


def test_transcript_resuelve_imagen_markdown_por_ruta(env):
    from orquestador.transcript import parse_file

    tid = env.tid()
    shot = "/tmp/claude-chrome-screenshots-Ruwdqp/screenshot-179-0.jpg"
    env.append([
        chrome_use(tid),
        chrome_result(tid, [img_block(PNG)], shot),
        {"type": "assistant", "timestamp": "2026-11-01T10:01:00Z", "uuid": "c2",
         "message": {"content": [{"type": "text", "text": f"Mirá ![Búsqueda mug]({shot}) acá"}]}},
    ])
    env.lib.index_all()
    lookup = env.lib.captura_ruta_lookup(SID)
    parsed, _ = parse_file(env.transcript_path(), captura_ruta=lookup)
    kinds = [i["kind"] for i in parsed]
    idx = kinds.index("claude")
    assert parsed[idx + 1]["kind"] == "imagenes"
    assert parsed[idx + 1]["fotos"][0]["id"] == captura_id(SID, sha_of(PNG))
    assert shot not in parsed[idx]["text"]
    assert "Búsqueda mug" not in parsed[idx]["text"] or "![Búsqueda" not in parsed[idx]["text"]


def test_transcript_ruta_desconocida_deja_alt(env):
    from orquestador.transcript import parse_file

    shot = "/tmp/claude-chrome-screenshots-nope/screenshot-9-0.jpg"
    env.append([{"type": "assistant", "timestamp": "2026-11-01T10:00:00Z", "uuid": "c1",
                 "message": {"content": [{"type": "text", "text": f"![solo alt]({shot})"}]}}])
    parsed, _ = parse_file(env.transcript_path(), captura_ruta=lambda _r: None)
    [entry] = [i for i in parsed if i["kind"] == "claude"]
    assert "solo alt" in entry["text"]
    assert shot not in entry["text"]


def _backfill_termina(env, segundos=10):
    import threading
    t = threading.Thread(target=env.lib.run_capturas_backfill, daemon=True)
    t.start()
    t.join(segundos)
    return not t.is_alive()


def test_backfill_saltea_linea_mas_larga_que_la_tanda(env, monkeypatch):
    monkeypatch.setattr(bib, "PASS_BYTES", 4096)
    tid = env.tid()
    env.append([{"type": "user", "message": {"content": "x" * 10000}}, chrome_use(tid),
                chrome_result(tid, [img_block(PNG)])])
    _simular_indice_sin_capturas(env)
    assert _backfill_termina(env)
    assert len([i for i in items(env) if i.get("source") == "captura"]) == 1


def test_backfill_termina_con_tramo_sin_salto_final(env):
    tid = env.tid()
    env.append([chrome_use(tid), chrome_result(tid, [img_block(PNG)])])
    path = env.transcript_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"type": "user", "message": {"content": "sin salto"}}')
    _simular_indice_sin_capturas(env)
    assert _backfill_termina(env)
    assert len([i for i in items(env) if i.get("source") == "captura"]) == 1


def test_chat_abierto_antes_del_backfill_ve_la_captura_despues(env, tmp_path):
    tid = env.tid()
    shot = "/tmp/claude-chrome-screenshots-q/screenshot-9-0.jpg"
    env.append([chrome_use(tid), chrome_result(tid, [img_block(PNG)], shot),
                {"type": "assistant", "timestamp": "2026-11-01T10:00:09Z",
                 "message": {"content": [{"type": "text", "text": f"Mirá: ![captura]({shot})"}]}}])
    _simular_indice_sin_capturas(env)
    svc = _service(env, tmp_path)
    def foto_tras_texto(parsed):
        kinds = [i.get("kind") for i in parsed]
        return "claude" in kinds and "imagenes" in kinds[kinds.index("claude") + 1:]

    antes, _ = svc._parsed(SID)
    assert not foto_tras_texto(antes)
    env.lib.run_capturas_backfill()
    despues, _ = svc._parsed(SID)
    assert foto_tras_texto(despues)


def test_transcript_evidencias_de_pruebas():
    import json as _j
    from orquestador.transcript import _pruebas_evidencias
    texto = "```pruebas\n" + _j.dumps({"titulo": "T", "casos": [
        {"nombre": "a", "resultado": "ok", "evidencia": "/x/a.png"},
        {"nombre": "b", "resultado": "ok", "evidencia": "/x/b.png"}]}) + "\n```"
    assert _pruebas_evidencias(texto, lambda r: "id1" if r == "/x/a.png" else None) == {"/x/a.png": "id1"}
    assert _pruebas_evidencias(texto, lambda r: None) == {}
    assert _pruebas_evidencias("sin bloque", lambda r: "id") == {}


def test_transcript_item_lleva_evidencias_resueltas(env):
    import json as _j
    from orquestador.transcript import parse_file
    img = env.file("ev.png", PNG)
    texto = "```pruebas\n" + _j.dumps({"titulo": "T", "casos": [
        {"nombre": "a", "resultado": "ok", "evidencia": img}]}) + "\n```"
    env.append([{"type": "assistant", "timestamp": "2026-11-01T10:00:00Z", "uuid": "c1",
                 "message": {"content": [{"type": "text", "text": texto}]}}])
    env.lib.index_all()
    parsed, _ = parse_file(env.transcript_path(), captura_ruta=env.lib.captura_ruta_lookup(SID))
    [entry] = [i for i in parsed if i["kind"] == "claude"]
    assert entry["text"] == texto and entry["evidencias"] == {img: captura_id(SID, sha_of(PNG))}
    parsed, _ = parse_file(env.transcript_path(), captura_ruta=lambda _r: None)
    assert "evidencias" not in [i for i in parsed if i["kind"] == "claude"][0]


def _chrome_con_id(env, ss="ss_abc123", img=PNG):
    tid = env.tid()
    texto = {"type": "text", "text": f"Successfully captured screenshot (784x372, jpeg) - ID: {ss}"}
    env.append([chrome_use(tid), tool_result_images(tid, [texto, img_block(img)])])


def _pruebas_ev(ev):
    import json as _j
    return "```pruebas\n" + _j.dumps({"titulo": "T", "casos": [
        {"nombre": "a", "resultado": "ok", "evidencia": ev}]}) + "\n```"


def _informe(env, ev, mid="p1"):
    env.append([{"type": "assistant", "timestamp": "2026-11-01T10:00:09Z", "uuid": mid,
                 "message": {"content": [{"type": "text", "text": _pruebas_ev(ev)}]}}])


def test_captura_indexa_id_de_captura_del_chrome(env):
    _chrome_con_id(env)
    env.lib.index_all()
    item = next(i for i in items(env) if i.get("source") == "captura")
    assert env.lib.captura_id_for_ruta(SID, "ss_abc123") == item["id"]


def test_pruebas_evidencia_por_id_resuelve_a_la_captura(env):
    _chrome_con_id(env)
    _informe(env, "ss_abc123")
    env.lib.index_all()
    pr = next(i for i in items(env) if i["kind"] == "pruebas")
    assert pr["evidencias"] == {"ss_abc123": captura_id(SID, sha_of(PNG))}
    assert "ss_abc123" in pr["pruebas_raw"]


def test_pruebas_id_desconocido_no_rompe(env):
    _informe(env, "ss_zzz999")
    env.lib.index_all()
    pr = next(i for i in items(env) if i["kind"] == "pruebas")
    assert pr["evidencias"] == {} and "ss_zzz999" in pr["pruebas_raw"]


def test_pruebas_id_de_otra_sesion_no_resuelve(env):
    _chrome_con_id(env)
    env.lib.index_all()
    assert env.lib.captura_id_for_ruta("otra-sesion", "ss_abc123") is None
    assert env.lib.captura_ruta_lookup("otra-sesion")("ss_abc123") is None


def test_pruebas_id_con_formato_invalido_se_descarta(env):
    for malo in ("ss_", "ss_AB", "xx_abc123", "ss_abc 123", "ss_" + "a" * 41):
        data = bib._pruebas_normalizadas({"titulo": "T", "casos": [
            {"nombre": "a", "resultado": "ok", "evidencia": malo}]})
        assert "evidencia" not in data["casos"][0], malo
    data = bib._pruebas_normalizadas({"titulo": "T", "casos": [
        {"nombre": "a", "resultado": "ok", "evidencia": "ss_abc123"}]})
    assert data["casos"][0]["evidencia"] == "ss_abc123"


def test_pruebas_evidencia_se_recorta_antes_de_validar():
    data = bib._pruebas_normalizadas({"titulo": "T", "casos": [
        {"nombre": "a", "resultado": "ok", "evidencia": " ss_abcd12 \n"},
        {"nombre": "b", "resultado": "ok", "evidencia": "  /ruta/a.png "}]})
    assert data["casos"][0]["evidencia"] == "ss_abcd12"
    assert data["casos"][1]["evidencia"] == "/ruta/a.png"


def test_backfill_indexa_id_de_captura(env):
    _chrome_con_id(env)
    _simular_indice_sin_capturas(env)
    env.lib.run_capturas_backfill()
    item = next(i for i in items(env) if i.get("source") == "captura")
    assert env.lib.captura_id_for_ruta(SID, "ss_abc123") == item["id"]


def test_transcript_evidencias_resuelve_id(env):
    from orquestador.transcript import _pruebas_evidencias
    assert _pruebas_evidencias(_pruebas_ev("ss_abc123"), lambda r: "id1" if r == "ss_abc123" else None) \
        == {"ss_abc123": "id1"}


def test_backfill_viejo_sin_version_reprocesa_y_completa_id(env):
    _chrome_con_id(env)
    env.lib.index_all()
    iid = captura_id(SID, sha_of(PNG))
    env.lib.items[iid].pop("shot_id", None)
    env.lib.keymap.pop((SID, "r:ss_abc123"), None)
    env.lib._capturas_backfill = {"done": True, "files": {}}
    env.lib.save()
    env.reload()
    env.lib.run_capturas_backfill()
    caps = [i for i in items(env) if i.get("source") == "captura"]
    assert len(caps) == 1 and caps[0]["shot_id"] == "ss_abc123"
    assert env.lib.captura_id_for_ruta(SID, "ss_abc123") == iid


def test_backfill_con_version_actual_no_reprocesa(env):
    from orquestador.biblioteca import CAPTURAS_BACKFILL_V
    _chrome_con_id(env)
    env.lib.index_all()
    iid = captura_id(SID, sha_of(PNG))
    env.lib.items[iid].pop("shot_id", None)
    env.lib._capturas_backfill = {"done": True, "files": {}, "v": CAPTURAS_BACKFILL_V}
    env.lib.save()
    env.reload()
    env.lib.run_capturas_backfill()
    assert "shot_id" not in env.lib.items[iid]


def test_id_de_evidencia_con_salto_de_linea_adentro_se_descarta():
    data = bib._pruebas_normalizadas({"titulo": "T", "casos": [
        {"nombre": "a", "resultado": "ok", "evidencia": "ss_abc\n123"}]})
    assert "evidencia" not in data["casos"][0]


def test_id_solo_si_el_texto_es_de_captura_y_gana_el_primero(env):
    from orquestador.captura_rutas import id_desde_tool_result
    def mk(t):
        return {"content": [{"type": "text", "text": t}]}
    assert id_desde_tool_result(mk("otra cosa - ID: ss_abc123")) is None
    assert id_desde_tool_result(mk("Successfully captured screenshot (1x1, png) - ID: ss_abc123")) == "ss_abc123"
    otra = PNG + b"\x00"
    for img in (PNG, otra):
        tid = env.tid()
        texto = {"type": "text", "text": "Successfully captured screenshot (1x1, png) - ID: ss_abc123"}
        env.append([chrome_use(tid), tool_result_images(tid, [texto, img_block(img)])])
    env.lib.index_all()
    assert env.lib.captura_id_for_ruta(SID, "ss_abc123") == captura_id(SID, sha_of(PNG))
