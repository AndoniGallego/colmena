import pytest

from orquestador.guardian.__main__ import main


def test_main_sin_xdg_runtime(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_carpeta_del_copiloto_es_confiable(tmp_path, monkeypatch):
    from orquestador.guardian import lanzador as lz
    from orquestador.guardian.__main__ import _cargar_config

    destino = tmp_path / "reunion-copiloto"
    destino.mkdir()
    monkeypatch.setattr(lz, "CARPETA_COPILOTO", destino)
    _, confiable, _ = _cargar_config()
    assert confiable(str(destino))
    assert not confiable(str(tmp_path))


def test_cwd_confiable_acepta_la_carpeta_guia_aunque_no_exista(tmp_path, monkeypatch):
    from orquestador.guardian import lanzador as lz
    from orquestador.guardian.__main__ import _cargar_config

    destino = tmp_path / "guia"
    monkeypatch.setattr(lz, "CARPETA_GUIA", destino)
    _, confiable, _ = _cargar_config()
    assert confiable(str(destino))
    assert not confiable(str(tmp_path))
