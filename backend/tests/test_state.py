import json
import logging
import threading
from unittest.mock import patch

import pytest

from orquestador import config
from orquestador.state import MAX_MENSAJES, MAX_TRASPASOS, StateStore

_DEFAULT_MESSAGES: list = []


def test_corrupt_json_sin_respaldar_si_replace_falla(tmp_path, caplog):
    path = tmp_path / "state.json"
    path.write_text("{ nope", encoding="utf-8")
    caplog.set_level(logging.ERROR, logger="orquestador.state")
    with patch("orquestador.state.os.replace", side_effect=OSError(13, "permiso")):
        store = StateStore(tmp_path)
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "{ nope"
    assert not list(tmp_path.glob("state.json.roto-*"))
    assert store.data["messages"] == _DEFAULT_MESSAGES
    assert any("no parseable" in r.message for r in caplog.records)


def test_flush_restaura_dirty_si_private_write_falla(tmp_path, caplog):
    path = tmp_path / "state.json"
    store = StateStore(tmp_path)
    store.data["marker"] = "uno"
    store._dirty = True
    intentos = {"n": 0}

    def flaky_write(p, text):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise OSError("disco")
        config.private_write(p, text)

    caplog.set_level(logging.ERROR, logger="orquestador.state")
    with patch("orquestador.state.private_write", side_effect=flaky_write):
        store.flush()
        assert store._dirty is True
        assert any("no pude guardar state.json" in r.message for r in caplog.records)
        store.flush()
    assert store._dirty is False
    assert json.loads(path.read_text(encoding="utf-8")).get("marker") == "uno"


def test_corrupt_json_quarantines_and_default_state(tmp_path, caplog):
    path = tmp_path / "state.json"
    path.write_text("{ nope", encoding="utf-8")
    caplog.set_level(logging.ERROR, logger="orquestador.state")
    store = StateStore(tmp_path)
    backups = sorted(tmp_path.glob("state.json.roto-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{ nope"
    assert not path.exists()
    assert store.data["messages"] == _DEFAULT_MESSAGES
    assert backups[0].name in caplog.text


@pytest.mark.parametrize("raw", ["5", "[]"])
def test_non_object_json_quarantines(tmp_path, caplog, raw):
    path = tmp_path / "state.json"
    path.write_text(raw, encoding="utf-8")
    caplog.set_level(logging.ERROR, logger="orquestador.state")
    store = StateStore(tmp_path)
    assert list(tmp_path.glob("state.json.roto-*"))
    assert not path.exists()
    assert store.data["messages"] == _DEFAULT_MESSAGES


def test_valid_dict_state_loaded(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"marker": "ok", "messages": [{"id": 1}]}), encoding="utf-8")
    store = StateStore(tmp_path)
    assert store.data.get("marker") == "ok"
    assert store.data["messages"] == [{"id": 1}]


def test_flush_waits_for_in_progress_write(tmp_path):
    enter_write = threading.Event()
    allow_finish = threading.Event()

    def slow_write(path, text):
        enter_write.set()
        assert allow_finish.wait(timeout=1.0)
        config.private_write(path, text)

    store = StateStore(tmp_path, save_delay=0.05)
    with patch("orquestador.state.private_write", side_effect=slow_write):
        store.data["blocked"] = True
        store.save()
        assert enter_write.wait(timeout=1.0), "escritura del timer no arrancó"
        flush_done = threading.Event()

        def do_flush():
            store.flush()
            flush_done.set()

        thr = threading.Thread(target=do_flush)
        thr.start()
        assert not flush_done.wait(timeout=0.15), "flush terminó antes de liberar la escritura"
        allow_finish.set()
        thr.join(timeout=1.0)
        assert flush_done.is_set()


def test_debounce_ten_saves_one_write_on_flush(tmp_path):
    store = StateStore(tmp_path, save_delay=60.0)
    calls = []
    with patch("orquestador.state.private_write", side_effect=lambda p, t: calls.append(t)):
        for _ in range(10):
            store.data["messages"].append({"x": 1})
            store.save()
        assert calls == []
        store.flush()
        assert len(calls) == 1
        store.flush()
        assert len(calls) == 1


def test_no_flush_file_unchanged_then_flush_readable(tmp_path):
    store = StateStore(tmp_path, save_delay=60.0)
    store.data["marker"] = "alpha"
    store.save()
    path = tmp_path / "state.json"
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    assert "alpha" not in json.loads(before) if before else True
    store.flush()
    again = StateStore(tmp_path)
    assert again.data.get("marker") == "alpha"


def test_traspaso_cap(tmp_path):
    store = StateStore(tmp_path)
    for i in range(MAX_TRASPASOS + 10):
        store.add_traspaso({"n": i})
    store.flush()
    assert len(store.traspasos()) == MAX_TRASPASOS
    assert store.traspasos()[0]["n"] == 10


def test_mensajes_cap(tmp_path):
    store = StateStore(tmp_path)
    for i in range(MAX_MENSAJES + 10):
        store.add_mensaje({"n": i})
    store.flush()
    assert len(store.mensajes()) == MAX_MENSAJES
    assert store.mensajes()[0]["n"] == 10


def test_flush_without_changes_does_not_write(tmp_path):
    store = StateStore(tmp_path, save_delay=60.0)
    store.flush()
    calls = []
    with patch("orquestador.state.private_write", side_effect=lambda p, t: calls.append(t)):
        store.flush()
    assert calls == []
