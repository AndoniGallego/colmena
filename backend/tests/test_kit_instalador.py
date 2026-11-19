import copy
import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from conftest import UNITS_FALSAS

from orquestador import kit_instalador as ki
from orquestador.kit_instalador import (
    KIT_DIR,
    MARCA_HOOK,
    KitInvalido,
    Reporte,
    aplicar_links,
    destinos,
    escribir_settings,
    fusionar_hooks,
    fusionar_statusline,
    hooks_deseados,
    instalar_kit,
    items_kit,
)


UNITS = UNITS_FALSAS


@pytest.fixture(autouse=True)
def _units_config(units_en_config):
    return units_en_config


def _kit(tmp_path: Path) -> Path:
    kit = tmp_path / "kit"
    for rel in (
        "bin/kit-update-all",
        "statusline/andokit-statusline",
        "reglas/colmena/estado-sesion.md",
        "ganchos/andokit-stop-bloques.sh",
        "skills/orquestador/SKILL.md",
    ):
        p = kit / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")
    (kit / "reglas" / "trabajo").mkdir(parents=True)
    return kit


@pytest.fixture
def entorno(tmp_path):
    kit = _kit(tmp_path)
    viejo = tmp_path / "andokit"
    viejo.mkdir()
    home = tmp_path / "home"
    d = destinos(
        {"ANDOKIT_NO_CONFIG_LOCAL": "1", "ANDOKIT_REPO_VIEJO": str(viejo)}, home, kit
    )
    return kit, viejo, home, d


def _instalar(kit, d, modo="instalar"):
    rep = Reporte(lineas=[])
    aplicar_links(
        items_kit(kit, d), d, modo, rep, d.state / "backup" / "t", kit_dir=kit
    )
    return rep


def test_destinos_defaults(entorno):
    _, _, home, d = entorno
    assert d.rules == home / ".claude" / "rules"
    assert d.hooks == home / ".claude" / "hooks"
    assert d.skills == home / ".claude" / "skills"
    assert d.settings == home / ".claude" / "settings.json"
    assert d.state == home / ".local" / "state" / "andokit"
    assert d.bin == home / ".local" / "bin"
    assert d.systemd == home / ".config" / "systemd" / "user"


def test_config_local_pisa_entorno(tmp_path):
    kit = _kit(tmp_path)
    (kit / "config.local").write_text(
        'ANDOKIT_SETTINGS="$HOME/canario.json"\n', encoding="utf-8"
    )
    d = destinos({"ANDOKIT_SETTINGS": "/otro.json"}, tmp_path / "home", kit)
    assert d.settings == tmp_path / "home" / "canario.json"


def test_config_local_ignorado_con_guarda(tmp_path):
    kit = _kit(tmp_path)
    (kit / "config.local").write_text(
        "ANDOKIT_SETTINGS=~/canario.json\n", encoding="utf-8"
    )
    d = destinos({"ANDOKIT_NO_CONFIG_LOCAL": "1"}, tmp_path / "home", kit)
    assert d.settings == tmp_path / "home" / ".claude" / "settings.json"


def test_instala_links(entorno):
    kit, _, _, d = entorno
    rep = _instalar(kit, d)
    assert not rep.fallo
    assert os.readlink(d.rules / "estado-sesion.md") == str(
        kit / "reglas/colmena/estado-sesion.md"
    )
    assert os.readlink(d.hooks / "andokit-stop-bloques.sh") == str(
        kit / "ganchos/andokit-stop-bloques.sh"
    )
    assert os.readlink(d.skills / "orquestador") == str(kit / "skills/orquestador")
    assert os.readlink(d.bin / "kit-update-all") == str(
        kit / "bin/kit-update-all"
    )
    assert os.readlink(d.bin / "andokit-statusline") == str(
        kit / "statusline/andokit-statusline"
    )


def test_migra_links_viejos_sin_respaldo(entorno):
    kit, viejo, _, d = entorno
    d.rules.mkdir(parents=True)
    os.symlink(viejo / "rules" / "estado-sesion.md", d.rules / "estado-sesion.md")
    _instalar(kit, d)
    assert os.readlink(d.rules / "estado-sesion.md") == str(
        kit / "reglas/colmena/estado-sesion.md"
    )
    assert not (d.state / "backup").exists()


def test_ajeno_se_respalda(entorno):
    kit, _, _, d = entorno
    d.rules.mkdir(parents=True)
    (d.rules / "estado-sesion.md").write_text("mío\n", encoding="utf-8")
    _instalar(kit, d)
    assert (d.state / "backup" / "t" / "rules" / "estado-sesion.md").read_text(
        encoding="utf-8"
    ) == "mío\n"
    assert os.readlink(d.rules / "estado-sesion.md") == str(
        kit / "reglas/colmena/estado-sesion.md"
    )


def test_link_ajeno_se_respalda(entorno):
    kit, _, _, d = entorno
    d.rules.mkdir(parents=True)
    os.symlink("/x/otra-regla.md", d.rules / "estado-sesion.md")
    _instalar(kit, d)
    assert (
        os.readlink(d.state / "backup" / "t" / "rules" / "estado-sesion.md")
        == "/x/otra-regla.md"
    )


def test_saca_huerfanos_del_repo_viejo(entorno):
    kit, viejo, _, d = entorno
    d.skills.mkdir(parents=True)
    os.symlink(viejo / "skills" / "mis-tickets", d.skills / "mis-tickets")
    os.symlink("/x/acmekit-skill", d.skills / "acmekit-skill")
    rep = _instalar(kit, d, "check")
    assert rep.drift
    assert any(ln.startswith("SOBRA") and "mis-tickets" in ln for ln in rep.lineas)
    _instalar(kit, d)
    assert not os.path.lexists(d.skills / "mis-tickets")
    assert os.readlink(d.skills / "acmekit-skill") == "/x/acmekit-skill"


def test_regla_duplicada_aborta(entorno):
    kit, _, _, d = entorno
    (kit / "reglas" / "trabajo" / "estado-sesion.md").write_text(
        "x\n", encoding="utf-8"
    )
    with pytest.raises(KitInvalido):
        items_kit(kit, d)
    assert not d.rules.exists()


def test_check_limpio_despues_de_instalar(entorno):
    kit, _, _, d = entorno
    _instalar(kit, d)
    rep = _instalar(kit, d, "check")
    assert not rep.drift
    assert all(ln.startswith("OK") for ln in rep.lineas)


@pytest.mark.parametrize("modo", ["check", "ensayo"])
def test_check_y_ensayo_no_escriben(entorno, modo):
    kit, viejo, home, d = entorno
    d.skills.mkdir(parents=True)
    os.symlink(viejo / "skills" / "mis-tickets", d.skills / "mis-tickets")
    antes = sorted(str(p) for p in home.rglob("*"))
    _instalar(kit, d, modo)
    assert sorted(str(p) for p in home.rglob("*")) == antes


# --- Tarea 7: settings.json, statusline y units ---


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


def _settings_base(hooks_dir: Path) -> dict:
    return {
        "env": {"A": "1"},
        "permissions": {"allow": ["Bash(ls)"]},
        "hooks": {
            "PreToolUse": [COLMENA],
            "Stop": [
                COLMENA,
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/old/andokit-stop-bloques.sh",
                            "timeout": 99,
                        }
                    ]
                },
            ],
            "PostToolUse": [ACMEKIT],
        },
    }


def _sha(p: Path) -> str:
    return hashlib.sha256(p.resolve().read_bytes()).hexdigest()


def _deploy(tmp_path: Path) -> Path:
    dep = tmp_path / "deploy"
    dep.mkdir(exist_ok=True)
    for u in UNITS:
        (dep / u).write_text(f"[Unit]\nDescription={u}\n", encoding="utf-8")
    return dep


def _correr_kit(tmp_path, d, modo="instalar", kit=None, llamadas=None):
    out: list[str] = []
    llamadas = [] if llamadas is None else llamadas
    rc = instalar_kit(
        kit or _kit_si_falta(tmp_path),
        _deploy(tmp_path),
        d,
        modo,
        out.append,
        lambda cmd: llamadas.append(cmd) or 0,
        lambda: datetime(2026, 11, 17, 12, 0, 0),
    )
    return rc, out


def _kit_si_falta(tmp_path):
    kit = tmp_path / "kit"
    return kit if kit.exists() else _kit(tmp_path)


def _escribir(p: Path, data: dict, modo=0o640):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(p, modo)


def test_fusion_conserva_ajenos_y_orden(tmp_path):
    base = _settings_base(tmp_path)
    orig = copy.deepcopy(base)
    nuevo = fusionar_hooks(base, hooks_deseados(tmp_path / "h"))
    assert base == orig
    for ev, grupos in nuevo["hooks"].items():
        marca = [
            g
            for g in grupos
            if any(MARCA_HOOK in h.get("command", "") for h in g["hooks"])
        ]
        assert len(marca) <= 1
        ajenos_antes = [
            g
            for g in orig["hooks"].get(ev, [])
            if g not in marca and "/andokit-" not in json.dumps(g)
        ]
        assert [g for g in grupos if g not in marca] == ajenos_antes
    assert len(nuevo["hooks"]["Stop"]) == 2
    assert nuevo["hooks"]["Stop"][-1] == hooks_deseados(tmp_path / "h")["Stop"][0]
    assert nuevo["hooks"]["PostToolUse"] == [ACMEKIT]
    assert {k: v for k, v in nuevo.items() if k != "hooks"} == {
        k: v for k, v in orig.items() if k != "hooks"
    }


def test_instalar_respaldo_y_permisos(entorno, tmp_path):
    kit, _, _, d = entorno
    _escribir(d.settings, _settings_base(d.hooks))
    sha0 = _sha(d.settings)
    rc, _ = _correr_kit(tmp_path, d)
    assert rc == 0
    assert oct(d.settings.stat().st_mode & 0o777) == "0o640"
    respaldos = list((d.state / "backup").glob("*/settings/settings.json"))
    assert len(respaldos) == 1 and _sha(respaldos[0]) == sha0


def test_idempotente(entorno, tmp_path):
    _, _, _, d = entorno
    _escribir(d.settings, _settings_base(d.hooks))
    _correr_kit(tmp_path, d)
    sha1 = _sha(d.settings)
    n = len(list((d.state / "backup").glob("*/settings/*")))
    _correr_kit(tmp_path, d)
    assert _sha(d.settings) == sha1
    assert len(list((d.state / "backup").glob("*/settings/*"))) == n


def _linea(out, ruta):
    return next(ln for ln in out if str(ruta) in ln and "hooks" in ln)


def test_check_estados(entorno, tmp_path):
    _, _, _, d = entorno
    _escribir(d.settings, {"env": {}})
    rc, out = _correr_kit(tmp_path, d, "check")
    assert rc == 1 and _linea(out, d.settings).startswith("FALTA")
    _escribir(d.settings, _settings_base(d.hooks))
    rc, out = _correr_kit(tmp_path, d, "check")
    assert rc == 1 and _linea(out, d.settings).startswith("DISTINTA")
    _correr_kit(tmp_path, d)
    rc, out = _correr_kit(tmp_path, d, "check")
    assert (
        rc == 0 and _linea(out, d.settings).startswith("OK") and out[-1] == "sin drift"
    )
    s = json.loads(d.settings.read_text(encoding="utf-8"))
    s["hooks"]["Stop"][-1]["hooks"][0]["timeout"] = 3
    _escribir(d.settings, s)
    rc, out = _correr_kit(tmp_path, d, "check")
    assert (
        rc == 1
        and _linea(out, d.settings).startswith("DISTINTA")
        and out[-1] == "hay drift"
    )
    _correr_kit(tmp_path, d)
    s = json.loads(d.settings.read_text(encoding="utf-8"))
    assert s["hooks"]["Stop"][-1]["hooks"][0]["timeout"] == 10


def test_settings_inexistente_se_crea(entorno, tmp_path):
    _, _, _, d = entorno
    rc, _ = _correr_kit(tmp_path, d)
    s = json.loads(d.settings.read_text(encoding="utf-8"))
    assert rc == 0 and len(s["hooks"]) == 2


def test_settings_invalido_no_se_toca(entorno, tmp_path):
    _, _, _, d = entorno
    d.settings.parent.mkdir(parents=True)
    d.settings.write_text("{no es json", encoding="utf-8")
    sha0 = _sha(d.settings)
    rc, out = _correr_kit(tmp_path, d)
    assert rc == 1 and any("FAILED" in ln for ln in out) and _sha(d.settings) == sha0


def test_dir_no_escribible(entorno, tmp_path):
    _, _, _, d = entorno
    _escribir(d.settings, {"env": {}})
    os.chmod(d.settings.parent, 0o500)
    try:
        rep = ki.Reporte()
        escribir_settings(
            d.settings, {"env": {}, "x": 1}, d.state / "backup" / "t", rep
        )
    finally:
        os.chmod(d.settings.parent, 0o700)
    assert rep.fallo
    assert sorted(p.name for p in d.settings.parent.iterdir()) == ["settings.json"]


def test_settings_symlink_sigue_siendo_link(entorno, tmp_path):
    _, _, _, d = entorno
    real = tmp_path / "dotfiles" / "settings.json"
    _escribir(real, {"env": {}})
    d.settings.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(real, d.settings)
    _correr_kit(tmp_path, d)
    assert d.settings.is_symlink()
    assert "hooks" in json.loads(real.read_text(encoding="utf-8"))


def test_no_pisa_si_cambio(entorno, monkeypatch):
    _, _, _, d = entorno
    _escribir(d.settings, {"env": {}})
    original = ki._sha256
    llamadas = []

    def sha_y_tercero(p):
        llamadas.append(p)
        if len(llamadas) == 2:
            p.write_text('{"tercero": true}', encoding="utf-8")
        return original(p)

    monkeypatch.setattr(ki, "_sha256", sha_y_tercero)
    rep = ki.Reporte()
    escribir_settings(d.settings, {"env": {}, "x": 1}, d.state / "backup" / "t", rep)
    assert rep.fallo and any("FAILED" in ln for ln in rep.lineas)
    assert json.loads(d.settings.read_text(encoding="utf-8")) == {"tercero": True}


def test_migracion_settings_identico(entorno, tmp_path):
    _, _, _, d = entorno
    s = fusionar_statusline(
        fusionar_hooks(_settings_base(d.hooks), hooks_deseados(d.hooks)), d.bin
    )
    _escribir(d.settings, s)
    sha0 = _sha(d.settings)
    _correr_kit(tmp_path, d)
    assert _sha(d.settings) == sha0
    assert not list((d.state / "backup").glob("*/settings"))


def test_statusline_solo_si_falta(entorno, tmp_path):
    _, _, home, d = entorno
    assert fusionar_statusline({}, Path.home() / ".local" / "bin")["statusLine"] == {
        "type": "command",
        "command": "$HOME/.local/bin/andokit-statusline",
    }
    assert (
        fusionar_statusline({}, Path("/x/bin"))["statusLine"]["command"]
        == "/x/bin/andokit-statusline"
    )
    ajeno = {"statusLine": {"type": "command", "command": "/x/otro"}}
    assert fusionar_statusline(ajeno, d.bin) == ajeno
    _escribir(d.settings, ajeno)
    _correr_kit(tmp_path, d)
    _, out = _correr_kit(tmp_path, d, "check")
    assert (
        json.loads(d.settings.read_text(encoding="utf-8"))["statusLine"]
        == ajeno["statusLine"]
    )
    assert any(ln.startswith("INFO") and "statusLine" in ln for ln in out)


def test_units_copiadas_y_reload(entorno, tmp_path):
    _, _, _, d = entorno
    llamadas: list = []
    _correr_kit(tmp_path, d, llamadas=llamadas)
    _correr_kit(tmp_path, d, llamadas=llamadas)
    assert llamadas == [["systemctl", "--user", "daemon-reload"]]
    for u in UNITS:
        assert (d.systemd / u).read_bytes() == (tmp_path / "deploy" / u).read_bytes()
    (d.systemd / UNITS[0]).write_text("cambiada\n", encoding="utf-8")
    rc, out = _correr_kit(tmp_path, d, "check")
    assert rc == 1 and any(ln.startswith("DISTINTA") and UNITS[0] in ln for ln in out)


def test_units_sin_reload(tmp_path):
    kit = _kit(tmp_path)
    d = destinos(
        {"ANDOKIT_NO_CONFIG_LOCAL": "1", "ANDOKIT_NO_RELOAD": "1"},
        tmp_path / "home",
        kit,
    )
    llamadas: list = []
    _correr_kit(tmp_path, d, kit=kit, llamadas=llamadas)
    assert llamadas == []


def test_ganchos_linkeados_funcionan(tmp_path):
    d = destinos(
        {"ANDOKIT_NO_CONFIG_LOCAL": "1", "ANDOKIT_NO_RELOAD": "1"},
        tmp_path / "home",
        KIT_DIR,
    )
    rc, _ = _correr_kit(tmp_path, d, kit=KIT_DIR)
    assert rc == 0
    r = subprocess.run(
        [str(d.hooks / "andokit-sin-askuser.sh")],
        input='{"tool_name":"AskUserQuestion"}',
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert '"deny"' in r.stdout


def test_reload_fallido_es_aviso(entorno, tmp_path):
    _, _, _, d = entorno
    out: list[str] = []
    rc = instalar_kit(
        _kit_si_falta(tmp_path),
        _deploy(tmp_path),
        d,
        "instalar",
        out.append,
        lambda cmd: 1,
        lambda: datetime(2026, 11, 17, 12, 0, 0),
    )
    assert rc == 0
    assert any(ln.startswith("AVISO") and "daemon-reload" in ln for ln in out)


def test_sin_units_no_copia_ni_recarga(entorno, tmp_path):
    _, _, _, d = entorno
    llamadas: list = []
    out: list[str] = []
    rc = instalar_kit(
        _kit_si_falta(tmp_path),
        _deploy(tmp_path),
        d,
        "instalar",
        out.append,
        lambda cmd: llamadas.append(cmd) or 0,
        lambda: datetime(2026, 11, 17, 12, 0, 0),
        units=False,
    )
    assert rc == 0 and llamadas == [] and not d.systemd.exists()
