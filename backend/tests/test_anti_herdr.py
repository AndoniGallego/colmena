import asyncio
import subprocess
from pathlib import Path

import pytest

from anti_herdr_estatico import violaciones
from orquestador.enchufe.herdr import HerdrClient

RAIZ = Path(__file__).resolve().parents[1] / "orquestador"
# instalador.py solo usa which("herdr") para escribir la unit systemd, no habla con Herdr.
PENDIENTES = frozenset({"instalador.py"})


def test_nada_fuera_del_enchufe_toca_herdr():
    assert violaciones(RAIZ, PENDIENTES) == []


def test_la_allowlist_no_tiene_muertos():
    for nombre in PENDIENTES:
        assert violaciones(RAIZ, PENDIENTES - {nombre}), f"{nombre} ya no viola: sacalo de PENDIENTES"


def test_detecta_una_violacion_sembrada(tmp_path):
    (tmp_path / "malo.py").write_text(
        "from .herdr import HerdrClient\nimport asyncio\nasyncio.create_subprocess_exec('herdr', 'api')\nx = ['herdr', 'pane']\n")
    (tmp_path / "enchufe").mkdir()
    (tmp_path / "enchufe" / "ok.py").write_text("from .herdr import HerdrClient\n")
    assert [v.split(":")[1] for v in violaciones(tmp_path, frozenset())] == ["1", "3", "4"]


@pytest.mark.parametrize("codigo,motivo", [
    ("from orquestador.herdr import HerdrSnapshot\n", "import"),
    ("from orquestador.herdr.algo import x\n", "import"),
    ("from .herdr.algo import x\n", "import"),
    ("from orquestador import herdr\n", "import"),
    ("from . import herdr\n", "import"),
    ("import orquestador.herdr\n", "import"),
    ("from .enchufe.herdr import HerdrError\n", "import"),
    ("x = ('herdr', 'pane')\n", "tupla"),
    ("def f(:\n", "no parseable"),
])
def test_cada_patron_se_detecta(tmp_path, codigo, motivo):
    (tmp_path / "malo.py").write_text(codigo)
    (v,) = violaciones(tmp_path, frozenset())
    assert motivo in v


def test_el_enchufe_propio_no_es_violacion(tmp_path):
    (tmp_path / "ok.py").write_text("from orquestador.enchufe import ids\nimport shutil\nshutil.which('git')\n")
    assert violaciones(tmp_path, frozenset()) == []


def test_exec_de_claude_bloqueado(anti_herdr):
    with pytest.raises(AssertionError):
        subprocess.run(["claude", "-p", "hola"])
    with pytest.raises(AssertionError):
        subprocess.run(["sh", "-c", "/home/x/.local/bin/claude --resume x"])
    assert len(anti_herdr) == 2
    anti_herdr.clear()


def test_rutas_con_claude_en_el_medio_no_se_bloquean():
    assert subprocess.run(["true", "/tmp/claude-1000/x", "claude_projects"]).returncode == 0


def test_client_default_bin_never_resolves_the_real_herdr():
    assert HerdrClient().bin == "/nonexistent/herdr"


def test_exec_of_herdr_is_blocked_and_recorded(anti_herdr):
    with pytest.raises(AssertionError):
        asyncio.run(asyncio.create_subprocess_exec("herdr", "api", "snapshot"))
    with pytest.raises(AssertionError):
        asyncio.run(asyncio.create_subprocess_exec("/home/x/.local/bin/herdr", "pane", "get", "a"))
    assert len(anti_herdr) == 2
    anti_herdr.clear()


def test_subprocess_of_herdr_is_blocked_and_recorded(anti_herdr):
    with pytest.raises(AssertionError):
        subprocess.run(["herdr", "pane", "list"])
    with pytest.raises(AssertionError):
        subprocess.Popen("herdr api snapshot", shell=True)
    assert len(anti_herdr) == 2
    anti_herdr.clear()


def test_other_programs_still_run():
    assert subprocess.run(["true"]).returncode == 0


def test_indirect_launches_are_blocked_too(anti_herdr):
    with pytest.raises(AssertionError):
        subprocess.run(["sh", "-c", "cd / && herdr pane run w1:p1 ls"])
    with pytest.raises(AssertionError):
        subprocess.run(["env", "X=1", "/opt/herdr-0.9/herdr", "api", "snapshot"])
    with pytest.raises(AssertionError):
        asyncio.run(asyncio.create_subprocess_shell("herdr pane send-keys w1:p1 enter"))
    import os
    with pytest.raises(AssertionError):
        os.system("herdr api snapshot")
    with pytest.raises(AssertionError):
        os.posix_spawnp("herdr", ["herdr", "api", "snapshot"], dict(os.environ))
    assert len(anti_herdr) == 5
    anti_herdr.clear()


def test_el_shim_ya_no_existe():
    assert not (RAIZ / "herdr.py").exists()


def test_solo_los_tests_del_adaptador_usan_fake_herdr():
    tests = Path(__file__).resolve().parent
    usan = {p.name for p in tests.rglob("test_*.py") if "FakeHerdr" in p.read_text(encoding="utf-8")}
    assert usan <= {"test_enchufe_tablero.py", "test_enchufe_adaptador.py", "test_enchufe_eventos.py",
                    "test_enchufe_contrato.py", "test_enchufe_hub.py", "test_enchufe_mux.py",
                    "test_herdr_client.py", "test_anti_herdr.py"}


def test_the_app_client_points_nowhere(client):
    assert type(client.app.state.enchufe).__name__ == "FakeTerminales"
