import asyncio
import os

import pytest

from orquestador.enchufe import herdr
from orquestador.enchufe.herdr import HerdrClient, HerdrError


def fake_bin(tmp_path, body):
    path = tmp_path / "fake-herdr"
    path.write_text("#!/bin/sh\n" + body + "\n")
    os.chmod(path, 0o755)
    return str(path)


def test_run_returns_output(tmp_path):
    client = HerdrClient(fake_bin(tmp_path, "echo ok"))
    assert asyncio.run(client.run("x")).strip() == "ok"


def test_run_kills_and_raises_on_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(herdr, "RUN_TIMEOUT", 0.2)
    marker = tmp_path / "pid"
    client = HerdrClient(fake_bin(tmp_path, f"echo $$ > {marker}; exec sleep 30"))
    with pytest.raises(HerdrError, match="a tiempo"):
        asyncio.run(client.run("x"))
    pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_budget_adds_command_timeout():
    assert HerdrClient._budget(("agent", "wait", "p", "--timeout", "3000")) == herdr.RUN_TIMEOUT + 3
    assert HerdrClient._budget(("x", "--timeout", "zz")) == herdr.RUN_TIMEOUT
    assert HerdrClient._budget(("x",)) == herdr.RUN_TIMEOUT
