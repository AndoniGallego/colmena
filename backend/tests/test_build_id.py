import os

from orquestador.app import build_id


def test_reads_the_stamped_version_and_follows_changes(tmp_path):
    cache: dict = {}
    sw = tmp_path / "sw.js"
    sw.write_text("const VERSION = 'mo1abc'\nconst CACHE = `orq-${VERSION}`\n")
    assert build_id(tmp_path, cache) == "mo1abc"
    sw.write_text("const VERSION = 'mo2xyz'\n")
    os.utime(sw, ns=(1, 1))
    assert build_id(tmp_path, cache) == "mo2xyz"


def test_unstamped_or_missing_gives_empty(tmp_path):
    assert build_id(tmp_path, {}) == ""
    (tmp_path / "sw.js").write_text("const VERSION = '__BUILD_ID__'\n")
    assert build_id(tmp_path, {}) == ""
