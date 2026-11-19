import pytest

from orquestador.guardian.__main__ import main


def test_main_sin_xdg_runtime(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
