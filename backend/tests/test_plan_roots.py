"""plan_roots decide en qué carpetas se pueden abrir terminales nuevas (lo usa nueva_terminal)."""
import os

from orquestador.nueva_terminal import plan_roots


def test_home_no_es_una_raiz():
    assert plan_roots([os.path.expanduser("~")]) == []


def test_comodin_ignora_symlinks_y_ocultas(tmp_path):
    base = tmp_path / "P"
    (base / "real").mkdir(parents=True)
    (base / ".oculta").mkdir()
    (base / "link").symlink_to(tmp_path)
    assert plan_roots([str(base) + "/*"]) == [os.path.realpath(base / "real")]
