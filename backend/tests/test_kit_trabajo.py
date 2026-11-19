"""Integraciones con un kit de trabajo externo: valores genéricos sin config, los configurados con ella."""
import asyncio
from pathlib import Path

import pytest

from orquestador import kit_trabajo, statusline
from orquestador.config import Config, load_config, save_config
from orquestador.nueva_tarea import mensaje_ticket
from orquestador.transcript import TranscriptService


@pytest.fixture
def datos(tmp_path, monkeypatch):
    d = tmp_path / "datos"
    d.mkdir()
    monkeypatch.setenv("ORQ_DATA_DIR", str(d))
    return d


def configurar(datos, **valores):
    cfg = Config(kit_trabajo=valores)
    save_config(cfg, datos)


def test_sin_config_valores_genericos(datos):
    assert kit_trabajo.valor("prefijo_vars") == "COLMENA"
    assert kit_trabajo.valor("comando_flujo") == "/flujo-tickets"
    assert kit_trabajo.valor("units") == []
    assert kit_trabajo.valor("apoyo_entornos") == []


def test_config_pisa_solo_lo_declarado(datos):
    configurar(datos, prefijo_vars="XX")
    assert kit_trabajo.valor("prefijo_vars") == "XX"
    assert kit_trabajo.valor("comando_flujo") == "/flujo-tickets"
    assert load_config(datos).kit_trabajo == {"prefijo_vars": "XX"}


def test_config_rota_vuelve_a_genericos(datos):
    (datos / "config.toml").write_text("esto = [no es toml", encoding="utf-8")
    assert kit_trabajo.valor("prefijo_vars") == "COLMENA"


def test_warn_pct_usa_prefijo_configurado(datos, monkeypatch):
    monkeypatch.setenv("KITX_CTX_WARN_PCT", "50")
    assert statusline.warn_pct() == 25
    configurar(datos, prefijo_vars="KITX")
    assert statusline.warn_pct() == 50


def test_warn_pct_generico_lee_colmena(datos, monkeypatch):
    monkeypatch.setenv("COLMENA_CTX_WARN_PCT", "40")
    assert statusline.warn_pct() == 40


def test_vpn_usa_prefijo_configurado(datos, monkeypatch, tmp_path):
    monkeypatch.setenv("KITX_VPN_STATUSLINE_ENABLED", "false")
    base = tmp_path / "net"
    base.mkdir()
    assert statusline.vpn_state(str(base)) == "down"
    configurar(datos, prefijo_vars="KITX")
    assert statusline.vpn_state(str(base)) is None


def test_titulos_dir_por_defecto_y_configurado(datos):
    svc = TranscriptService(None)
    assert svc.title_dir == Path.home() / ".claude" / ".kit-session-title"
    configurar(datos, carpeta_titulos=".otros-titulos")
    assert svc.title_dir == Path.home() / ".claude" / ".otros-titulos"


def test_mensaje_ticket_generico_y_configurado(datos):
    gen = mensaje_ticket("ABC-123", "feature/ABC-123", "")
    assert "/flujo-tickets" in gen and "lector-tickets" not in gen
    configurar(datos, comando_flujo="/mi-flujo", agente_tickets="lector-tickets")
    cfg = mensaje_ticket("ABC-123", "feature/ABC-123", "")
    assert "agente lector-tickets" in cfg and "seguí /mi-flujo desde" in cfg


def test_flow_script_por_defecto_y_configurado(datos):
    from orquestador.mrs import script_flujo_git
    assert script_flujo_git() == str(Path.home() / ".local" / "bin" / "git-flow.sh")
    configurar(datos, script_flujo_git="mi-flow.sh")
    assert script_flujo_git() == str(Path.home() / ".local" / "bin" / "mi-flow.sh")


def test_apoyo_entornos(datos):
    from orquestador import entornos
    assert not entornos._servicio_tiene_apoyo("datos-x-1")
    configurar(datos, apoyo_entornos=["datos-x"])
    assert entornos._servicio_tiene_apoyo("datos-x-1")
    assert entornos._servicio_tiene_apoyo("mailhog")


def test_units(datos):
    from orquestador import kit_instalador
    assert kit_instalador.units_kit() == ()
    configurar(datos, units=["a.path", "a.service"])
    assert kit_instalador.units_kit() == ("a.path", "a.service")


def test_suite_ignora_config_local_del_repo():
    """Aunque exista data/config.toml con [kit_trabajo] en el repo, la suite ve los genéricos."""
    from orquestador.config import REPO_ROOT
    assert kit_trabajo._directorio() != REPO_ROOT / "data"
    assert kit_trabajo.valor("prefijo_vars") == "COLMENA"
