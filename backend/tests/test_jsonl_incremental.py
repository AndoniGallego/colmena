import json
import os
from pathlib import Path

from conftest import SID
from orquestador.digest import DigestService, parse_transcript
from orquestador.transcript import TranscriptService, parse_file


def _proj(tmp_path: Path, sub: str = "-proj") -> Path:
    p = tmp_path / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


def _line(obj: dict) -> str:
    return json.dumps(obj) + "\n"


def _user(text: str, **kw) -> dict:
    return {"type": "user", "message": {"content": text}, **kw}


def _assistant(text: str, **kw) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}, **kw}


def _digest_key(d):
    return (d.title, d.last_prompt, d.last_message, d.turns, d.local_tail, d.tail)


def test_digest_incremental_matches_full_and_skips_reparse(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    n = 5
    lines = [_line(_user(f"u{i}")) for i in range(n)]
    path.write_text("".join(lines), encoding="utf-8")
    projects = tmp_path
    svc = DigestService(projects)
    loads = 0
    real = json.loads

    def counting(raw, *a, **k):
        nonlocal loads
        loads += 1
        return real(raw, *a, **k)

    monkeypatch.setattr("orquestador.digest.json.loads", counting)
    a = svc.get(SID)
    assert a is not None
    first_loads = loads

    m = 3
    extra = [_line(_assistant(f"c{i}")) for i in range(m)]
    with path.open("a", encoding="utf-8") as fh:
        fh.write("".join(extra))
    loads = 0
    b = svc.get(SID)
    assert loads <= m + 2  # solo líneas nuevas (más margen por título/metadata)
    fresh = DigestService(projects)
    full = fresh.get(SID)
    assert _digest_key(b) == _digest_key(full)
    assert first_loads >= n


def test_transcript_page_incremental_matches_full(tmp_path, monkeypatch):
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    lines = [_line(_user("hola")), _line(_assistant("ok"))]
    path.write_text("".join(lines), encoding="utf-8")
    dig = DigestService(tmp_path)
    svc = TranscriptService(dig)
    loads = 0
    real = json.loads

    def counting(raw, *a, **k):
        nonlocal loads
        loads += 1
        return real(raw, *a, **k)

    monkeypatch.setattr("orquestador.transcript.json.loads", counting)
    p1 = svc.page(SID, None, 200)
    assert [i["text"] for i in p1["items"]] == ["hola", "ok"]
    first = loads
    path.write_text(path.read_text() + _line(_user("nuevo")), encoding="utf-8")
    loads = 0
    p2 = svc.page(SID, None, 200)
    assert loads <= 2
    dig2 = DigestService(tmp_path)
    p_full = TranscriptService(dig2).page(SID, None, 200)
    assert p2["items"] == p_full["items"]


def test_truncated_file_reprised_like_full_parse(tmp_path):
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    big = [_line(_user(f"x{i}")) for i in range(20)]
    path.write_text("".join(big), encoding="utf-8")
    svc = DigestService(tmp_path)
    svc.get(SID)
    short = [_line(_user("solo"))]
    path.write_text("".join(short), encoding="utf-8")
    got = svc.get(SID)
    expect = parse_transcript(path)
    assert _digest_key(got) == _digest_key(expect)


def test_replaced_file_other_inode(tmp_path):
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    path.write_text(_line(_user("viejo")), encoding="utf-8")
    svc = DigestService(tmp_path)
    svc.get(SID)
    tmp = proj / "replacement.jsonl"
    tmp.write_text(_line(_user("nuevo")) + _line(_assistant("resp")), encoding="utf-8")
    os.replace(tmp, path)
    got = svc.get(SID)
    expect = parse_transcript(path)
    assert _digest_key(got) == _digest_key(expect)


def test_partial_final_line_without_newline(tmp_path):
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    path.write_text(_line(_user("uno")), encoding="utf-8")
    svc = DigestService(tmp_path)
    d1 = svc.get(SID)
    assert len(d1.turns) == 1
    partial = json.dumps(_user("dos"))
    with path.open("ab") as fh:
        fh.write(partial.encode("utf-8"))
    d2 = svc.get(SID)
    assert len(d2.turns) == 1
    with path.open("ab") as fh:
        fh.write(b"\n")
    d3 = svc.get(SID)
    expect = parse_transcript(path)
    assert _digest_key(d3) == _digest_key(expect)
    assert len(d3.turns) == 2


def test_find_caches_path_skips_second_glob(tmp_path):
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    path.write_text(_line(_user("x")), encoding="utf-8")
    svc = DigestService(tmp_path)
    glob_calls = {"n": 0}
    orig_glob = Path.glob

    def spy(self, pattern):
        glob_calls["n"] += 1
        return orig_glob(self, pattern)

    Path.glob = spy
    try:
        assert svc.find(SID) == path
        assert glob_calls["n"] == 1
        assert svc.find(SID) == path
        assert glob_calls["n"] == 1
    finally:
        Path.glob = orig_glob


def test_find_rediscovers_after_move(tmp_path):
    p1 = _proj(tmp_path, "proj-a")
    p2 = _proj(tmp_path, "proj-b")
    path = p1 / f"{SID}.jsonl"
    path.write_text(_line(_user("a")), encoding="utf-8")
    svc = DigestService(tmp_path)
    assert svc.find(SID) == path
    path.unlink()
    path2 = p2 / f"{SID}.jsonl"
    path2.write_text(_line(_user("b")), encoding="utf-8")
    assert svc.find(SID) == path2


def test_find_does_not_cache_missing(tmp_path):
    _proj(tmp_path)
    svc = DigestService(tmp_path)
    assert svc.find("no-existe-00000000-0000-0000-0000-000000000099") is None
    assert "no-existe-00000000-0000-0000-0000-000000000099" not in getattr(svc, "_path_cache", {})


def test_transcript_incremental_fotos_two_reads_match_full(tmp_path):
    from test_capturas import JPEG, chrome_use, img_block, tool_result_images
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    tid, ts_img, ts_claude = "t1", "2026-01-01T10:00:05Z", "2026-01-01T10:00:10Z"
    chunk1 = _line(chrome_use(tid, "2026-01-01T10:00:00Z")) + _line(
        tool_result_images(tid, [img_block(JPEG, "image/jpeg")], ts=ts_img)
    )
    path.write_text(chunk1, encoding="utf-8")
    dig = DigestService(tmp_path)
    svc = TranscriptService(dig)
    mid = svc._parsed(SID)
    chunk2 = _line(_assistant("listo", **{"timestamp": ts_claude}))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(chunk2)
    got = svc._parsed(SID)
    full = parse_file(path)
    assert got == full
    imgs = [i for i in got[0] if i["kind"] == "imagenes"]
    assert len(imgs) == 1 and imgs[0]["ts"] == ts_claude


def test_transcript_incremental_fotos_dedup_rutas_fotos(tmp_path):
    import hashlib
    from test_capturas import JPEG, chrome_use, img_block, tool_result_images
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    tid = "t2"
    sha = hashlib.sha256(JPEG).hexdigest()
    from orquestador.biblioteca import item_id
    cap_id = item_id(SID, f"c:{sha}", 0)
    chunk1 = _line(chrome_use(tid)) + _line(tool_result_images(tid, [img_block(JPEG, "image/jpeg")]))
    path.write_text(chunk1, encoding="utf-8")
    dig = DigestService(tmp_path)
    svc = TranscriptService(dig)
    svc._parsed(SID)
    ruta = "/tmp/cap.jpg"
    claude = {"type": "assistant", "timestamp": "2026-01-01T10:00:10Z",
              "message": {"content": [{"type": "text", "text": f"![x]({ruta})"}]}}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_line(claude))
    lookup = lambda p: cap_id if p == ruta else None

    class _Lib:
        rutas_gen = 0

        def captura_ruta_lookup(self, _sid):
            return lookup

    svc.library = _Lib()
    got = svc._parsed(SID)
    full_items, full_meta = parse_file(path, lookup)
    assert got == (full_items, full_meta)
    fotos = [f for i in got[0] if i["kind"] == "imagenes" for f in i["fotos"]]
    assert cap_id in {f["id"] for f in fotos}
    assert sum(1 for i in got[0] if i["kind"] == "imagenes") == 1


def test_parse_transcript_last_line_without_trailing_newline(tmp_path):
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    lines = _line(_user("uno")) + _line(_user("dos")).rstrip("\n")
    path.write_text(lines, encoding="utf-8")
    d = parse_transcript(path)
    assert [t["text"] for t in d.turns] == ["uno", "dos"]


def test_parse_file_last_line_without_trailing_newline(tmp_path):
    from orquestador.transcript import parse_file
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    lines = _line(_user("uno")) + _line(_assistant("dos")).rstrip("\n")
    path.write_text(lines, encoding="utf-8")
    items, _ = parse_file(path)
    assert [i["text"] for i in items if "text" in i] == ["uno", "dos"]


def test_transcript_parse_cache_lru_keeps_hot_session(tmp_path, monkeypatch):
    import orquestador.transcript as mod
    monkeypatch.setattr(mod, "CACHE_SIZE", 2)
    dig = DigestService(tmp_path)
    svc = TranscriptService(dig)
    hot = "hot11111-1111-4111-8111-111111111111"
    for sid in (hot, "cold0000-0000-4000-8000-000000000001", "cold0000-0000-4000-8000-000000000002"):
        p = _proj(tmp_path, f"p-{sid[:4]}")
        (p / f"{sid}.jsonl").write_text(_line(_user("x")), encoding="utf-8")
    svc._parsed(hot)
    svc._parsed("cold0000-0000-4000-8000-000000000001")
    svc._parsed("cold0000-0000-4000-8000-000000000002")
    svc._parsed(hot)
    assert hot in svc._parse


def test_digest_parse_cache_lru_keeps_hot_session(tmp_path, monkeypatch):
    import orquestador.digest as mod
    monkeypatch.setattr(mod, "CACHE_SIZE", 2)
    svc = DigestService(tmp_path)
    hot = "hot22222-2222-4222-8222-222222222222"
    for sid in (hot, "cold0000-0000-4000-8000-000000000003", "cold0000-0000-4000-8000-000000000004"):
        p = _proj(tmp_path, f"q-{sid[:4]}")
        (p / f"{sid}.jsonl").write_text(_line(_user("x")), encoding="utf-8")
    svc.get(hot)
    svc.get("cold0000-0000-4000-8000-000000000003")
    svc.get("cold0000-0000-4000-8000-000000000004")
    svc.get(hot)
    assert hot in svc._parse


def test_digest_get_not_mutated_by_later_parse(tmp_path):
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    path.write_text(_line(_user("uno")), encoding="utf-8")
    svc = DigestService(tmp_path)
    first = svc.get(SID)
    n0 = len(first.turns)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_line(_user("dos")))
    svc.get(SID)
    assert len(first.turns) == n0


def test_transcript_parsed_not_mutated_by_later_parse(tmp_path):
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    path.write_text(_line(_user("uno")), encoding="utf-8")
    dig = DigestService(tmp_path)
    svc = TranscriptService(dig)
    first = svc._parsed(SID)
    n0 = len(first[0])
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_line(_user("dos")))
    svc._parsed(SID)
    assert len(first[0]) == n0


def test_rewrite_same_size_new_mtime_reprises(tmp_path):
    proj = _proj(tmp_path)
    path = proj / f"{SID}.jsonl"
    path.write_text(_line(_user("viejo")), encoding="utf-8")
    svc = DigestService(tmp_path)
    svc.get(SID)
    nuevo = _line(_user("nuevo"))
    assert len(nuevo) == len(path.read_text(encoding="utf-8"))
    path.write_text(nuevo, encoding="utf-8")
    os.utime(path, (path.stat().st_mtime + 2, path.stat().st_mtime + 2))
    got = svc.get(SID)
    expect = parse_transcript(path)
    assert _digest_key(got) == _digest_key(expect)


def _assistant_raw(i: int) -> bytes:
    return json.dumps({
        "type": "assistant",
        "timestamp": f"t{i}",
        "message": {"content": [{"type": "text", "text": f"r{i}"}]},
    }).encode()


def test_cold_read_race_no_double_count(tmp_path):
    """race.py escenario 1: archivo crece entre stat y read; sin duplicados."""
    proj = _proj(tmp_path)
    p = proj / "s.jsonl"
    p.write_bytes(_assistant_raw(0) + b"\n" + _assistant_raw(1))
    p_base = type(p)

    class Racy(p_base):
        calls = 0
        at = 4
        extra = b"\n" + _assistant_raw(2) + b"\n"

        def stat(self, *a, **k):
            st = super().stat(*a, **k)
            Racy.calls += 1
            if Racy.calls == Racy.at:
                with open(self, "ab") as fh:
                    fh.write(Racy.extra)
            return st

    rp = Racy(p)
    ds = DigestService(tmp_path)
    ds.find = lambda sid: rp
    ds.get("s")
    d = ds.get("s")
    full = parse_transcript(rp)
    assert [t["text"] for t in d.turns] == [t["text"] for t in full.turns]


def test_cold_read_race_valid_tail_then_growth(tmp_path):
    """race2.py: cola válida sin \\n y crecimiento antes del stat de final."""
    proj = _proj(tmp_path)
    p = proj / "s.jsonl"
    p.write_bytes(_assistant_raw(0) + b"\n" + _assistant_raw(1))
    p_base = type(p)

    class Racy(p_base):
        calls = 0

        def stat(self, *a, **k):
            Racy.calls += 1
            if Racy.calls == 4:
                with open(self, "ab") as fh:
                    fh.write(b"\n" + _assistant_raw(2) + b"\n" + _assistant_raw(3)[:10])
            return super().stat(*a, **k)

    rp = Racy(p)
    ds = DigestService(tmp_path)
    ds.find = lambda sid: rp
    ds.get("s")
    with open(rp, "ab") as fh:
        fh.write(_assistant_raw(3)[10:] + b"\n" + _assistant_raw(4) + b"\n")
    d = ds.get("s")
    full = parse_transcript(rp)
    assert [t["text"] for t in d.turns] == [t["text"] for t in full.turns]


def test_find_concurrent_path_cache(tmp_path, monkeypatch):
    import orquestador.digest as mod
    from concurrent.futures import ThreadPoolExecutor, as_completed

    monkeypatch.setattr(mod, "CACHE_SIZE", 4)
    proj = tmp_path
    n = 300
    for i in range(n):
        sub = proj / f"d{i}"
        sub.mkdir(parents=True, exist_ok=True)
        sid = f"s{i:04d}"
        (sub / f"{sid}.jsonl").write_text(_line(_user("x")), encoding="utf-8")
    svc = DigestService(tmp_path)
    errs = []

    def work(i):
        try:
            sid = f"s{i:04d}"
            got = svc.find(sid)
            assert got is not None
        except Exception as e:
            errs.append(e)

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(work, i) for i in range(n)]
        for f in as_completed(futs):
            f.result()
    assert not errs
