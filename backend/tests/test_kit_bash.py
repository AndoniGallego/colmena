import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
KIT_DIR = REPO / "kit"
SCRIPTS = sorted((KIT_DIR / "tests").glob("*.sh"))


def _entorno(home: Path) -> dict:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("ANDOKIT_") and k != "COLMENA_TERMINAL"
    }
    env["HOME"] = str(home)
    return env


def test_hay_scripts():
    assert len(SCRIPTS) >= 10


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_del_kit(script, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    r = subprocess.run(
        ["bash", str(script)], env=_entorno(home), capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 0, f"{script.name} rc={r.returncode}\n{r.stdout}\n{r.stderr}"
