import os
import stat
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from orquestador.config import private_write


def test_private_write_content_and_permissions(tmp_path):
    path = tmp_path / "secret"
    private_write(path, "hola\n")
    assert path.read_text(encoding="utf-8") == "hola\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_private_write_no_tmp_left(tmp_path):
    path = tmp_path / "data.json"
    private_write(path, "{}")
    left = list(tmp_path.glob("*.tmp"))
    assert left == []


def test_private_write_concurrent_two_threads(tmp_path):
    path = tmp_path / "slot"
    content_a = "A" * 200
    content_b = "B" * 200
    errors: list[str] = []

    def writer(text: str) -> None:
        for _ in range(20):
            private_write(path, text)
            got = path.read_text(encoding="utf-8")
            if got != content_a and got != content_b:
                errors.append(got)

    t1 = threading.Thread(target=writer, args=(content_a,))
    t2 = threading.Thread(target=writer, args=(content_b,))
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)
    assert not t1.is_alive() and not t2.is_alive()
    assert errors == []
    final = path.read_text(encoding="utf-8")
    assert final in (content_a, content_b)


def test_private_write_failure_cleans_tmp_and_preserves_file(tmp_path):
    path = tmp_path / "keep.toml"
    path.write_text("original", encoding="utf-8")
    with patch("os.replace", side_effect=OSError("boom")):
        with pytest.raises(OSError, match="boom"):
            private_write(path, "replaced")
    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob("*.tmp")) == []
