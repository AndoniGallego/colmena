import os

from orquestador import jsonl


def test_append_privado(tmp_path):
    p = tmp_path / "x.jsonl"
    assert jsonl.append_privado(p, {"a": 1}) and oct(p.stat().st_mode & 0o777) == "0o600"
    p.chmod(0o400)
    assert jsonl.append_privado(p, {"a": 2}) is False


def test_append_privado_no_trunca_y_mantiene_modo(tmp_path):
    p = tmp_path / "x.jsonl"
    assert jsonl.append_privado(p, {"a": 1})
    assert jsonl.append_privado(p, {"b": 2})
    texto = p.read_text(encoding="utf-8")
    assert '"a": 1' in texto
    assert '"b": 2' in texto
    assert oct(p.stat().st_mode & 0o777) == "0o600"


def test_append_privado_unicode(tmp_path):
    p = tmp_path / "x.jsonl"
    assert jsonl.append_privado(p, {"texto": "café ñ"})
    assert "café ñ" in p.read_text(encoding="utf-8")


def test_append_privado_una_linea_por_llamada(tmp_path):
    p = tmp_path / "x.jsonl"
    jsonl.append_privado(p, {"n": 1})
    jsonl.append_privado(p, {"n": 2})
    raw = p.read_bytes()
    assert raw.count(b"\n") == 2
    lines = raw.decode("utf-8").split("\n")
    assert lines[-1] == ""
    assert len([ln for ln in lines if ln]) == 2


def test_append_privado_archivo_0644_queda_0600_sin_truncar(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"prev": true}\n', encoding="utf-8")
    p.chmod(0o644)
    assert jsonl.append_privado(p, {"a": 1})
    assert oct(p.stat().st_mode & 0o777) == "0o600"
    texto = p.read_text(encoding="utf-8")
    assert '"prev": true' in texto
    assert '"a": 1' in texto


def test_append_privado_umask_cero_archivo_nuevo_0600(tmp_path):
    p = tmp_path / "nuevo.jsonl"
    prev = os.umask(0)
    try:
        assert jsonl.append_privado(p, {"x": 1})
    finally:
        os.umask(prev)
    assert oct(p.stat().st_mode & 0o777) == "0o600"


def test_append_privado_symlink_no_toca_destino(tmp_path):
    destino = tmp_path / "real.jsonl"
    destino.write_text('{"ok": 1}\n', encoding="utf-8")
    enlace = tmp_path / "link.jsonl"
    enlace.symlink_to(destino)
    assert jsonl.append_privado(enlace, {"hack": 1}) is False
    assert destino.read_text(encoding="utf-8") == '{"ok": 1}\n'


def test_append_privado_entrada_no_serializable(tmp_path, caplog):
    p = tmp_path / "x.jsonl"
    import logging

    with caplog.at_level(logging.WARNING, logger="orquestador.jsonl"):
        assert jsonl.append_privado(p, {"a": object()}) is False
    assert not p.exists() or p.read_text(encoding="utf-8") == ""
    assert "secreto" not in caplog.text.lower()
    for record in caplog.records:
        assert "object()" not in record.getMessage()


def test_append_privado_surrogate_suelto(tmp_path, caplog):
    p = tmp_path / "x.jsonl"
    import logging

    with caplog.at_level(logging.WARNING, logger="orquestador.jsonl"):
        assert jsonl.append_privado(p, {"t": "\ud800"}) is False
    assert not p.exists() or p.stat().st_size == 0


def test_append_privado_fallo_registra_el_motivo(tmp_path, caplog):
    p = tmp_path / "x.jsonl"
    p.write_text("")
    p.chmod(0o400)
    with caplog.at_level("WARNING", logger="orquestador.jsonl"):
        assert jsonl.append_privado(p, {"a": 1}) is False
    assert any("Permission" in r.getMessage() for r in caplog.records)
