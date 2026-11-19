from pathlib import Path

import orquestador

BORRADOS = ["aprobador_gris", "transcripts_gris", "bandeja", "cadenas", "centinela_api", "centinela_lineas",
            "centinela_ops", "centinela_power", "centinela_socket", "centinela_vivo", "chat", "colmena_aviso",
            "colmena_mcp", "context", "encargos", "engram_guardar", "frentes", "novedades", "planes",
            "memoria_mcp", "decisor", "interruptor", "politica_permisos", "observacion_permisos"]


def _raiz() -> Path:
    return Path(orquestador.__file__).parent


def test_modulos_borrados():
    assert [m for m in BORRADOS if (_raiz() / f"{m}.py").exists()] == []
    assert not (_raiz() / "centinela.md").exists()


def test_centinela_solo_en_tolerancias():
    con = sorted(p.name for p in _raiz().rglob("*.py") if "centinela" in p.read_text().lower())
    assert con == ["permisos.py"]
