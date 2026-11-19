import json
import os
import stat
import time

from biblioteca_support import PNG, SID, Env, result, use
from orquestador import biblioteca as bib


def png(n: int, size: int = 100_000) -> bytes:
    return PNG + n.to_bytes(4, "big") + b"\x00" * size


def send(env, paths, ts="2026-11-01T10:00:00Z"):
    tid = env.tid()
    env.append([use(tid, "SendUserFile", {"files": paths}, ts), result(tid, ts=ts)])


def blobs(env):
    d = env.data / "biblioteca" / "blobs"
    return list(d.iterdir()) if d.is_dir() else []


def test_copies_are_content_addressed(tmp_path):
    env = Env(tmp_path)
    same = env.file("a.png", png(1))
    for _ in range(10):
        send(env, [same] * 5)
    env.lib.index_all()
    assert len(env.lib.items) == 50 and all(i["copia"] for i in env.lib.items.values())
    assert len(blobs(env)) == 1
    assert env.lib._copy_bytes == sum(b.stat().st_size for b in blobs(env))


def test_total_budget_checked_before_each_copy(tmp_path, monkeypatch):
    env = Env(tmp_path)
    monkeypatch.setattr(bib, "COPY_TOTAL_CAP", 250_000)
    paths = [env.file(f"{n}.png", png(n)) for n in range(5)]
    for p in paths:
        send(env, [p])
    env.lib.index_all()
    used = sum(b.stat().st_size for b in blobs(env))
    assert used <= 250_000 and env.lib._copy_bytes == used
    kept = [i for i in env.lib.items.values() if i["copia"]]
    assert 1 <= len(kept) <= 2
    assert bib.COPY_TOTAL_CAP == 250_000


def test_single_file_over_budget_is_not_copied(tmp_path, monkeypatch):
    env = Env(tmp_path)
    monkeypatch.setattr(bib, "COPY_TOTAL_CAP", 1000)
    send(env, [env.file("big.png", png(1))])
    env.lib.index_all()
    [item] = env.lib.items.values()
    assert item["copia"] is False and not blobs(env)


def test_per_item_cap(tmp_path, monkeypatch):
    env = Env(tmp_path)
    monkeypatch.setattr(bib, "MAX_COPY_ITEM", 50_000)
    send(env, [env.file("big.png", png(1))])
    env.lib.index_all()
    assert not next(iter(env.lib.items.values()))["copia"]


def test_copy_dirs_are_private(tmp_path):
    env = Env(tmp_path)
    os.umask(0o022)
    send(env, [env.file("a.png", png(1))])
    env.lib.index_all()
    assert stat.S_IMODE((env.data / "biblioteca").stat().st_mode) == 0o700
    assert stat.S_IMODE((env.data / "biblioteca" / "blobs").stat().st_mode) == 0o700
    assert stat.S_IMODE(blobs(env)[0].stat().st_mode) == 0o600


def test_copy_age_ignores_transcript_ts(tmp_path):
    env = Env(tmp_path)
    send(env, [env.file("a.png", png(1))], ts="2999-01-01T00:00:00Z")
    send(env, [env.file("b.png", png(2))], ts="2001-01-01T00:00:00Z")
    env.lib.index_all()
    assert all(i["copia"] for i in env.lib.items.values())
    for i in env.lib.items.values():
        i["copied_at"] = time.time() - (bib.COPY_DAYS + 1) * 86400
    env.lib.purge()
    assert not any(i["copia"] for i in env.lib.items.values()) and not blobs(env)


def test_old_per_item_copies_are_discarded(tmp_path):
    env = Env(tmp_path)
    send(env, [env.file("a.png", png(1))])
    env.lib.index_all()
    legacy = env.data / "biblioteca" / ("0" * 32) / "main"
    legacy.mkdir(parents=True)
    (legacy / "file.png").write_bytes(b"x")
    next(iter(env.lib.items.values())).pop("blobs")
    env.lib.save()
    lib = env.reload()
    assert not legacy.exists() and not any(i["copia"] for i in lib.items.values())


def test_pending_bounded_and_fast(tmp_path):
    env = Env(tmp_path, biblioteca_copias=False)
    n = 8000
    with env.transcript_path().open("w") as fh:
        for i in range(n):
            fh.write(json.dumps(use(f"toolu_p{i:06d}", "Artifact", {"file_path": "/x"})) + "\n")
        for i in range(n):
            fh.write(json.dumps({"type": "user", "timestamp": "x",
                                 "message": {"content": [{"type": "text", "text": "Artifact hola"}]}}) + "\n")
    t = time.time()
    env.lib.index_all()
    assert time.time() - t < 2
    [state] = env.lib.files.values()
    assert len(state["pending"]) == bib.MAX_PENDING
    assert "toolu_p000000" not in state["pending"] and f"toolu_p{n - 1:06d}" in state["pending"]


def test_pending_result_still_resolves_by_regex(tmp_path):
    env = Env(tmp_path, biblioteca_copias=False)
    tid = env.tid()
    p = env.file("a.png", PNG)
    env.append([use(tid, "SendUserFile", {"files": [p]})])
    env.lib.index_all()
    env.append([result(tid)])
    env.lib.index_all()
    assert len(env.lib.items) == 1


def test_indexer_reads_bounded_chunks_and_resumes(tmp_path, monkeypatch):
    env = Env(tmp_path, biblioteca_copias=False)
    monkeypatch.setattr(bib, "PASS_BYTES", 1500)
    for _ in range(40):
        send(env, [env.file("a.png", PNG)])
    total = env.transcript_path().stat().st_size
    assert total > 1500 * 5
    env.lib.index_all()
    [state] = env.lib.files.values()
    assert 0 < state["offset"] <= 1500 and len(env.lib.items) < 40
    for _ in range(40):
        env.lib.index_all()
    assert len(env.lib.items) == 40 and env.lib.files[next(iter(env.lib.files))]["offset"] == total


def test_giant_line_is_skipped_without_losing_the_rest(tmp_path, monkeypatch):
    env = Env(tmp_path, biblioteca_copias=False)
    monkeypatch.setattr(bib, "PASS_BYTES", 2000)
    with env.transcript_path().open("w") as fh:
        fh.write(json.dumps({"type": "ai-title", "aiTitle": "x" * 9000}) + "\n")
    send(env, [env.file("a.png", PNG)])
    for _ in range(20):
        env.lib.index_all()
    assert len(env.lib.items) == 1


def test_open_checked_rejects_swapped_inode(tmp_path):
    env = Env(tmp_path)
    path = env.file("a.png", PNG)
    real, ident = env.lib.policy.check_id(path)
    assert ident == (os.stat(path).st_dev, os.stat(path).st_ino)
    fd, _ = bib.open_checked(real, ident)
    os.close(fd)
    other = env.file("b.png", PNG)
    os.replace(other, path)
    assert bib.open_checked(real, ident) is None


def test_index_sessions_filters_session_ids(tmp_path, monkeypatch):
    env = Env(tmp_path, biblioteca_copias=False)
    asked = []
    monkeypatch.setattr(env.lib, "_discover_for", lambda sid: asked.append(sid) or [])
    env.lib.index_sessions(["../../x", "*", SID, 5])
    assert asked == [SID]
