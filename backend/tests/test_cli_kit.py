import json
import os
import sys
from pathlib import Path

import pytest

from conftest import configurar_kit_trabajo
from orquestador import cli
from orquestador.kit_instalador import KIT_DIR, MARCA_HOOK, desinstalar_kit, destinos

SIN_PIEZAS_DEL_TRABAJO = pytest.mark.skipif(
    not (KIT_DIR / "statusline").is_dir(),
    reason="el kit publicado no trae el statusline ni las units del trabajo",
)

COLMENA = {
    "hooks": [
        {
            "type": "command",
            "command": "COLMENA_GANCHO_ORIGEN=x python3 /c/colmena_gancho.py",
        }
    ]
}
ACMEKIT = {
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": "/k/acmekit-post.sh"}],
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    for k in list(os.environ):
        if k.startswith("ANDOKIT_"):
            monkeypatch.delenv(k)
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("ANDOKIT_NO_CONFIG_LOCAL", "1")
    monkeypatch.setenv("ANDOKIT_NO_RELOAD", "1")
    return h


def _d(home):
    return destinos(dict(os.environ), home, KIT_DIR)


def _todo(p: Path) -> list[str]:
    return sorted(str(x.relative_to(p)) for x in p.rglob("*"))


def _links_al_kit(d) -> list[Path]:
    return [
        p
        for carpeta in (d.bin, d.skills, d.rules, d.hooks)
        if carpeta.is_dir()
        for p in carpeta.iterdir()
        if p.is_symlink() and str(KIT_DIR) in os.readlink(p)
    ]


def test_cli_kit_check_no_escribe(home):
    assert cli.kit("instalar", False, True) == 1
    assert _todo(home) == []


def test_cli_kit_instalar_y_check_limpio(home, capsys):
    assert cli.kit("instalar", False, False) == 0
    capsys.readouterr()
    assert cli.kit("instalar", False, True) == 0
    assert capsys.readouterr().out.rstrip().endswith("sin drift")


def test_cli_kit_accion_invalida(home, capsys):
    assert cli.kit(None, False, False) == 1
    assert "Acción requerida: instalar o desinstalar" in capsys.readouterr().err
    assert cli.kit("desinstalar", True, False) == 2
    assert cli.kit("desinstalar", False, True) == 2


@SIN_PIEZAS_DEL_TRABAJO
def test_desinstalar_solo_lo_propio(home):
    d = _d(home)
    assert cli.kit("instalar", False, False) == 0
    (d.skills / "ajeno").symlink_to("/x/acmekit-skill")
    s = json.loads(d.settings.read_text(encoding="utf-8"))
    s["hooks"]["Stop"].insert(0, COLMENA)
    s["hooks"]["PostToolUse"] = [ACMEKIT]
    d.settings.write_text(json.dumps(s), encoding="utf-8")
    previos = _todo(d.state / "backup") if (d.state / "backup").exists() else []
    out: list[str] = []
    assert desinstalar_kit(KIT_DIR, d, out.append) == 0
    assert os.readlink(d.skills / "ajeno") == "/x/acmekit-skill"
    assert [p.name for p in _links_al_kit(d)] == ["andokit-statusline"]
    nuevo = json.loads(d.settings.read_text(encoding="utf-8"))
    assert MARCA_HOOK not in json.dumps(nuevo["hooks"])
    assert nuevo["hooks"]["Stop"] == [COLMENA]
    assert nuevo["hooks"]["PostToolUse"] == [ACMEKIT]
    assert set(previos) <= set(_todo(d.state / "backup"))


@SIN_PIEZAS_DEL_TRABAJO
def test_desinstalar_conserva_statusline_en_uso(home):
    d = _d(home)
    assert cli.kit("instalar", False, False) == 0
    s = json.loads(d.settings.read_text(encoding="utf-8"))
    assert s["statusLine"]["command"].endswith("andokit-statusline")
    out: list[str] = []
    desinstalar_kit(KIT_DIR, d, out.append)
    assert (d.bin / "andokit-statusline").is_symlink()
    assert any("andokit-statusline" in ln and "statusLine" in ln for ln in out)


@SIN_PIEZAS_DEL_TRABAJO
def test_desinstalar_saca_statusline_si_no_se_usa(home):
    d = _d(home)
    assert cli.kit("instalar", False, False) == 0
    s = json.loads(d.settings.read_text(encoding="utf-8"))
    s["statusLine"] = {"type": "command", "command": "/x/otra"}
    d.settings.write_text(json.dumps(s), encoding="utf-8")
    desinstalar_kit(KIT_DIR, d, lambda _: None)
    assert _links_al_kit(d) == []


def test_main_parsea_kit(monkeypatch):
    llamadas = []
    monkeypatch.setattr(sys, "argv", ["orquestador", "kit", "instalar", "--check"])
    monkeypatch.setattr(cli, "kit", lambda *a: llamadas.append(a) or 0)
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0
    assert llamadas == [("instalar", False, True)]


def test_cli_kit_regla_duplicada_sin_traceback(home, tmp_path, monkeypatch, capsys):
    from orquestador import kit_instalador

    kit = tmp_path / "kitdup"
    for rel in ("reglas/colmena/x.md", "reglas/trabajo/x.md"):
        (kit / rel).parent.mkdir(parents=True, exist_ok=True)
        (kit / rel).write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(kit_instalador, "KIT_DIR", kit)
    assert cli.kit("instalar", False, False) == 1
    assert "ERROR" in capsys.readouterr().err
    assert not (home / ".claude").exists()


def test_desinstalar_si_falla_settings_no_saca_links(home):
    d = _d(home)
    assert cli.kit("instalar", False, False) == 0
    os.chmod(d.settings.parent, 0o500)
    try:
        out: list[str] = []
        assert desinstalar_kit(KIT_DIR, d, out.append) == 1
    finally:
        os.chmod(d.settings.parent, 0o700)
    assert (d.hooks / "andokit-stop-bloques.sh").is_symlink()
    assert (d.rules / "estado-sesion.md").is_symlink()


def test_desinstalar_avisa_units(home, tmp_path, monkeypatch):
    reales = sorted(p.name for p in (KIT_DIR.parent / "deploy").glob("*-update-all.*"))
    if len(reales) != 2:
        pytest.skip("el kit publicado no trae las units del trabajo")
    datos = tmp_path / "datos-kit"
    datos.mkdir()
    monkeypatch.setenv("ORQ_DATA_DIR", str(datos))
    configurar_kit_trabajo(datos, units=reales)
    d = _d(home)
    assert cli.kit("instalar", False, False) == 0
    out: list[str] = []
    desinstalar_kit(KIT_DIR, d, out.append)
    path = next(n for n in reales if n.endswith(".path"))
    assert any(path in ln and "disable" in ln for ln in out)
    assert (d.systemd / path).exists()
