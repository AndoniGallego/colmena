"""Serialización TOML de config (fechas, escapes, tablas anidadas)."""
from datetime import date, datetime, time

import tomllib

from orquestador.config import Config, load_config, save_config


def test_toml_datetime_y_escape_control(tmp_path):
    cuando = datetime(2026, 3, 15, 14, 30, 0)
    dia = date(2026, 3, 15)
    hora = time(9, 5, 0)
    texto = "línea\x7f\tfin"
    save_config(
        Config(
            pin="x",
            mrs={
                "usuario": "dev",
                "equipo": [{"usuario": "a", "id": 1, "nombre": texto}],
            },
            estado={"cuando": cuando, "dia": dia, "hora": hora, "texto": texto},
        ),
        tmp_path,
    )
    raw = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "\\u007f" in raw
    parsed = tomllib.loads(raw)
    assert parsed["estado"]["cuando"] == cuando
    assert parsed["estado"]["dia"] == dia
    assert parsed["estado"]["hora"] == hora
    assert parsed["mrs"]["equipo"][0]["nombre"] == texto
    cfg = load_config(tmp_path)
    assert cfg.estado["cuando"] == cuando
    assert cfg.mrs["equipo"][0]["nombre"] == texto


def test_sse_gzip_default_true_y_se_conserva_apagado(tmp_path):
    assert Config().sse_gzip is True
    (tmp_path / "config.toml").write_text("sse_gzip = false\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.sse_gzip is False
    save_config(cfg, tmp_path)
    assert load_config(tmp_path).sse_gzip is False
