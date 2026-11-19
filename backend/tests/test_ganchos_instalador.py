import os
import json
import shlex
import stat
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from orquestador.ganchos import definiciones as d, instalador as ins
from orquestador.ganchos.colmena_gancho import ESPERA_DEFAULT, EVENTOS

SCRIPT = Path("/opt/c/colmena_gancho.py")
AJENO = {"type": "command", "command": "bash ~/.claude/hooks/kit.sh"}
PARECIDO = {"type": "command", "command": "python3 /x/colmena-gancho-otro.py"}


def reloj():
    return datetime(2026, 11, 3, 10, 0, 0)


def leer(p):
    return json.loads(p.read_text())


def colmena(hooks_evento):
    return [h for e in hooks_evento for h in e["hooks"] if d.es_de_colmena(h.get("command"))]


def test_definiciones_coherencia_con_gancho():
    assert set(d.EVENTOS_ASYNC) | {"PermissionRequest"} == EVENTOS
    assert int(ESPERA_DEFAULT) == 125


def test_definiciones_forma():
    defs = d.definiciones_hooks(SCRIPT, espera=120)
    assert set(defs) == set(d.EVENTOS_ASYNC) | {"PermissionRequest"}
    for ev in d.EVENTOS_ASYNC:
        (h,) = defs[ev][0]["hooks"]
        assert h["async"] is True and h["timeout"] == 10 and "COLMENA_GANCHO_ORIGEN=global" in h["command"]
        assert h["command"].startswith("COLMENA_GANCHO_ORIGEN=global python3 -I -S ")
        assert str(SCRIPT.resolve()) in h["command"]
        assert h["command"].endswith("|| true")
    pr = defs["PermissionRequest"][0]
    assert pr["matcher"] == "*" and "async" not in pr["hooks"][0] and pr["hooks"][0]["timeout"] == 130
    assert "COLMENA_GANCHO_ESPERA=125" in pr["hooks"][0]["command"]
    assert defs["PreToolUse"][0]["matcher"] == "*" and "matcher" not in defs["Stop"][0]
    assert d.definiciones_hooks(SCRIPT, espera=200)["PermissionRequest"][0]["hooks"][0]["timeout"] == 210


def test_comando_termina_en_or_true():
    cmd = d.comando(SCRIPT)
    assert cmd.endswith("|| true")
    assert shlex.split(cmd)[-2:] == ["||", "true"]


def test_comando_script_inexistente_exit_cero():
    r = subprocess.run(
        ["sh", "-c", d.comando(Path("/no/existe.py"))],
        input=b"{}",
        capture_output=True,
    )
    assert r.returncode == 0
    assert r.stdout == b""


def test_es_de_colmena_estricto():
    assert d.es_de_colmena(d.comando(SCRIPT))
    viejo = "COLMENA_GANCHO_ORIGEN=global python3 -I -S /opt/c/colmena_gancho.py"
    assert d.es_de_colmena(viejo)
    for otro in (
        "python3 /x/colmena-gancho-otro.py",
        "python3 -I -S /x/colmena_gancho.py.bak",
        None,
        3,
        "echo colmena_gancho.py",
        f"{viejo} || false",
    ):
        assert not d.es_de_colmena(otro)


def test_instalar_agrega_solo_marcadas(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(
        json.dumps({"model": "x", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [AJENO, PARECIDO]}]}})
    )
    r = ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    datos = leer(s)
    assert r.cambio and r.respaldo.exists() and datos["model"] == "x"
    assert AJENO in datos["hooks"]["PreToolUse"][0]["hooks"] and PARECIDO in datos["hooks"]["PreToolUse"][0]["hooks"]
    for ev in list(d.EVENTOS_ASYNC) + ["PermissionRequest"]:
        assert len(colmena(datos["hooks"][ev])) == 1


def test_instalar_dos_veces_no_duplica_y_actualiza_timeout(tmp_path):
    s = tmp_path / "settings.json"
    ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=200, ahora=reloj)
    (h,) = colmena(leer(s)["hooks"]["PermissionRequest"])
    assert h["timeout"] == 210
    r = ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=200, ahora=reloj)
    assert r.cambio is False


def test_instalar_preserva_bloques_y_eventos_vacios_ajenos(tmp_path):
    bloque_vacio = {"matcher": "Bash", "hooks": []}
    hooks_inicial = {
        "PreToolUse": [bloque_vacio],
        "EventoAjeno": [],
    }
    s = tmp_path / "settings.json"
    texto_inicial = json.dumps({"hooks": hooks_inicial})
    s.write_text(texto_inicial)
    r1 = ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert r1.cambio
    assert leer(s)["hooks"]["PreToolUse"][0] == bloque_vacio
    assert leer(s)["hooks"]["EventoAjeno"] == []
    bytes_tras_primera = s.read_bytes()
    r2 = ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert r2.cambio is False
    assert s.read_bytes() == bytes_tras_primera


def test_instalar_cambio_false_no_altera_bytes(tmp_path):
    s = tmp_path / "settings.json"
    ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    antes = s.read_bytes()
    r = ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert r.cambio is False
    assert s.read_bytes() == antes


def test_instalar_settings_inexistente(tmp_path):
    s = tmp_path / "settings.json"
    resp = tmp_path / "nuevo" / "respaldos"
    r = ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    assert r.cambio
    assert r.respaldo is None
    manifest = json.loads((resp / "ultimo.json").read_text())
    assert manifest["existia"] is False
    assert manifest["respaldo"] is None
    datos = leer(s)
    for ev in list(d.EVENTOS_ASYNC) + ["PermissionRequest"]:
        assert len(colmena(datos["hooks"][ev])) == 1


def test_instalar_json_invalido_no_toca(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text("{ no es json")
    bytes_antes = s.read_bytes()
    with pytest.raises(ins.SettingsInvalido):
        ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert s.read_bytes() == bytes_antes


def test_instalar_raiz_no_objeto_no_toca(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text("[1, 2]")
    bytes_antes = s.read_bytes()
    with pytest.raises(ins.SettingsInvalido):
        ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert s.read_bytes() == bytes_antes


def test_instalar_symlink_rechazado(tmp_path):
    real = tmp_path / "real.json"
    real.write_text("{}")
    link = tmp_path / "settings.json"
    link.symlink_to(real)
    bytes_real_antes = real.read_bytes()
    with pytest.raises(ins.SettingsInvalido):
        ins.instalar(link, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert real.read_bytes() == bytes_real_antes


def test_validar_hook_no_dict(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"hooks": {"Stop": [{"hooks": ["no-es-dict"]}]}}))
    with pytest.raises(ins.SettingsInvalido):
        ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)


def test_respaldar_crea_directorio_padre(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text("{}")
    resp = tmp_path / "a" / "b" / "respaldos"
    r = ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    assert r.cambio
    assert resp.is_dir()
    assert (resp / "ultimo.json").exists()


ORIGINAL = b'{\n    "zeta": 1,\n  "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "bash kit.sh"}]}]},\n "alfa": [3,2]\n}\n'


def test_round_trip_byte_a_byte(tmp_path):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    s.chmod(0o640)
    ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    ins.desinstalar(s, tmp_path / "resp")
    assert s.read_bytes() == ORIGINAL and stat.S_IMODE(s.stat().st_mode) == 0o640


def test_round_trip_conserva_modo_con_umask_estricta(tmp_path):
    """La CLI corre con umask 077: el modo del settings del usuario no debe cambiar."""
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    s.chmod(0o640)
    prev = os.umask(0o077)
    try:
        ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
        assert stat.S_IMODE(s.stat().st_mode) == 0o640
        ins.desinstalar(s, tmp_path / "resp")
    finally:
        os.umask(prev)
    assert s.read_bytes() == ORIGINAL and stat.S_IMODE(s.stat().st_mode) == 0o640


def test_reinstalar_tras_edicion_conserva_clave_y_quita_colmena(tmp_path):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    datos = leer(s)
    datos["clave_ajena"] = "conservar"
    s.write_text(json.dumps(datos))
    ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=200, ahora=reloj)
    ins.desinstalar(s, tmp_path / "resp")
    final = leer(s)
    assert final["clave_ajena"] == "conservar"
    hooks = final.get("hooks") or {}
    for ev in list(d.EVENTOS_ASYNC) + ["PermissionRequest"]:
        assert colmena(hooks.get(ev, [])) == []


def test_edicion_del_usuario_en_el_medio_se_conserva(tmp_path):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    datos = leer(s)
    datos["nuevo"] = True
    s.write_text(json.dumps(datos))
    ins.desinstalar(s, tmp_path / "resp")
    final = leer(s)
    assert final["nuevo"] is True and final["hooks"] == json.loads(ORIGINAL)["hooks"]


def test_settings_inexistente_se_borra_al_desinstalar(tmp_path):
    s = tmp_path / "settings.json"
    ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert s.exists()
    ins.desinstalar(s, tmp_path / "resp")
    assert not s.exists()


def test_desinstalar_sin_instalado_no_reescribe(tmp_path):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    antes = s.stat().st_mtime_ns
    r = ins.desinstalar(s, tmp_path / "resp")
    assert r.cambio is False and s.stat().st_mtime_ns == antes


def test_backup_previo_no_se_pisa_y_si_falla_no_escribe(tmp_path, monkeypatch):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    r1 = ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert r1.respaldo.read_bytes() == ORIGINAL
    s.write_bytes(ORIGINAL)
    (tmp_path / "resp" / "ultimo.json").unlink()
    r2 = ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert r2.respaldo != r1.respaldo and r1.respaldo.read_bytes() == ORIGINAL
    s.write_bytes(ORIGINAL)
    (tmp_path / "resp" / "ultimo.json").unlink()
    monkeypatch.setattr(ins, "_respaldar", lambda *a, **k: (_ for _ in ()).throw(OSError("disco")))
    with pytest.raises(OSError):
        ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert s.read_bytes() == ORIGINAL


def test_escritura_atomica_fallo_a_mitad(tmp_path, monkeypatch):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    monkeypatch.setattr(ins.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("corte")))
    with pytest.raises(OSError):
        ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    assert s.read_bytes() == ORIGINAL and not list(tmp_path.glob("settings.json.*.tmp"))


@pytest.mark.parametrize("contenido", [b"", b"   \n"])
def test_vacio_es_objeto_vacio(tmp_path, contenido):
    s = tmp_path / "settings.json"
    s.write_bytes(contenido)
    ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    ins.desinstalar(s, tmp_path / "resp")
    assert s.read_bytes() == contenido


@pytest.mark.parametrize(
    "contenido",
    [
        b"{no json",
        b'{"hooks": []}',
        b'{"hooks": {"Stop": null}}',
        b'{"hooks": {"Stop": [{"matcher": "x"}]}}',
        b"\xef\xbb\xbf{}",
        b'{"a": 1 // coment\n}',
        b"[]",
    ],
)
def test_formas_raras_no_rompen_ni_tocan(tmp_path, contenido):
    s = tmp_path / "settings.json"
    s.write_bytes(contenido)
    try:
        ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)
    except ins.SettingsInvalido as e:
        assert str(s) in str(e)
        assert s.read_bytes() == contenido
        return
    ins.desinstalar(s, tmp_path / "resp")
    assert s.read_bytes() == contenido


def test_symlink_se_rehusa(tmp_path):
    real = tmp_path / "real.json"
    real.write_bytes(b"{}")
    s = tmp_path / "settings.json"
    s.symlink_to(real)
    with pytest.raises(ins.SettingsInvalido):
        ins.instalar(s, tmp_path / "resp", script=SCRIPT, espera=120, ahora=reloj)


def _tiene_colmena_en_datos(datos: dict) -> bool:
    hooks = datos.get("hooks")
    if not isinstance(hooks, dict):
        return False
    for bloques in hooks.values():
        if not isinstance(bloques, list):
            continue
        for bloque in bloques:
            if not isinstance(bloque, dict):
                continue
            inner = bloque.get("hooks")
            if not isinstance(inner, list):
                continue
            for h in inner:
                if d.es_de_colmena(h.get("command") if isinstance(h, dict) else None):
                    return True
    return False


def test_instalar_fallo_restaura_manifest_y_borra_respaldo_huerfano(tmp_path, monkeypatch):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    resp = tmp_path / "resp"
    real_replace = ins.os.replace

    def replace_selectivo(src, dst):
        if Path(dst).name == "settings.json":
            raise OSError("corte")
        return real_replace(src, dst)

    monkeypatch.setattr(ins.os, "replace", replace_selectivo)
    with pytest.raises(OSError):
        ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    assert not (resp / "ultimo.json").exists()
    assert not list(resp.glob("settings-*.json"))
    assert s.read_bytes() == ORIGINAL


def test_instalar_segunda_vez_reusa_manifest_y_respaldo(tmp_path):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    resp = tmp_path / "resp"
    r1 = ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    m1 = (resp / "ultimo.json").read_text()
    b1 = r1.respaldo
    r2 = ins.instalar(s, resp, script=SCRIPT, espera=200, ahora=reloj)
    assert r2.respaldo == b1
    m2 = json.loads((resp / "ultimo.json").read_text())
    m1d = json.loads(m1)
    assert m2["existia"] == m1d["existia"] and m2["respaldo"] == m1d["respaldo"]
    assert m2["sha_instalado"] != m1d["sha_instalado"]


def test_desinstalar_sin_manifest_preserva_hook_ajeno(tmp_path):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    datos = leer(s)
    datos["hooks"]["Stop"][0]["hooks"].append(AJENO)
    s.write_text(json.dumps(datos))
    (resp / "ultimo.json").unlink()
    ins.desinstalar(s, resp)
    final = leer(s)
    assert AJENO in final["hooks"]["Stop"][0]["hooks"]
    assert not _tiene_colmena_en_datos(final)


def test_desinstalar_sin_manifest_preserva_hook_ajeno_sin_hooks_en_respaldo(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"model": "m1"}))
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    datos = leer(s)
    datos["hooks"]["PreToolUse"] = [{"matcher": "Bash", "hooks": [AJENO]}]
    s.write_text(json.dumps(datos))
    (resp / "ultimo.json").unlink()
    ins.desinstalar(s, resp)
    final = leer(s)
    assert final["model"] == "m1"
    assert AJENO in final["hooks"]["PreToolUse"][0]["hooks"]
    assert not _tiene_colmena_en_datos(final)


def test_desinstalar_respaldo_borrado_cae_estructural(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"model": "keep", "hooks": {"Stop": [{"hooks": [AJENO]}]}}))
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    assert ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj).cambio is False
    manifest = json.loads((resp / "ultimo.json").read_text())
    Path(manifest["respaldo"]).unlink()
    ins.desinstalar(s, resp)
    final = leer(s)
    assert final["model"] == "keep"
    assert AJENO in final["hooks"]["Stop"][0]["hooks"]
    assert not _tiene_colmena_en_datos(final)


def test_desinstalar_manifest_otro_settings_no_borra_manifest(tmp_path):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    manifest_antes = (resp / "ultimo.json").read_text()
    otro = tmp_path / "otro.json"
    otro.write_bytes(ORIGINAL)
    ins.desinstalar(otro, resp)
    assert (resp / "ultimo.json").read_text() == manifest_antes
    assert _tiene_colmena_en_datos(leer(s))


def test_desinstalar_preserva_evento_vacio_del_respaldo(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"hooks": {"Stop": []}}))
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    assert _tiene_colmena_en_datos(leer(s))
    ins.desinstalar(s, resp)
    assert leer(s)["hooks"]["Stop"] == []


def test_desinstalar_preserva_evento_vacio_sin_respaldo_borra_clave(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"hooks": {"Stop": []}}))
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    (resp / "ultimo.json").unlink()
    for p in resp.glob("settings-*.json"):
        p.unlink()
    ins.desinstalar(s, resp)
    final = leer(s)
    assert "Stop" not in final.get("hooks", {})
    assert not _tiene_colmena_en_datos(final)


def test_desinstalar_manifest_sin_colmena_retira_manifest_sin_tocar_bytes(tmp_path):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    s.write_bytes(ORIGINAL)
    bytes_usuario = s.read_bytes()
    assert not _tiene_colmena_en_datos(leer(s))
    assert (resp / "ultimo.json").exists()
    r = ins.desinstalar(s, resp)
    assert r.cambio is False
    assert s.read_bytes() == bytes_usuario
    assert not (resp / "ultimo.json").exists()


def test_instalar_fallo_restaura_manifest_previo(tmp_path, monkeypatch):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    manifest_previo = (resp / "ultimo.json").read_text()
    real_replace = ins.os.replace

    def replace_selectivo(src, dst):
        if Path(dst).name == "settings.json":
            raise OSError("corte")
        return real_replace(src, dst)

    monkeypatch.setattr(ins.os, "replace", replace_selectivo)
    with pytest.raises(OSError, match="corte"):
        ins.instalar(s, resp, script=SCRIPT, espera=200, ahora=reloj)
    assert (resp / "ultimo.json").read_text() == manifest_previo


def test_instalar_fallo_propaga_excepcion_original_si_restauracion_falla(tmp_path, monkeypatch):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    real_replace = ins.os.replace
    reemplazos_ultimo = [0]

    def replace_selectivo(src, dst):
        dst_path = Path(dst)
        if dst_path.name == "settings.json":
            raise OSError("corte")
        if dst_path.name == "ultimo.json":
            reemplazos_ultimo[0] += 1
            if reemplazos_ultimo[0] > 1:
                raise OSError("restore-fail")
        return real_replace(src, dst)

    monkeypatch.setattr(ins.os, "replace", replace_selectivo)
    with pytest.raises(OSError, match="corte"):
        ins.instalar(s, resp, script=SCRIPT, espera=200, ahora=reloj)


def test_instalar_fallo_propaga_excepcion_original_si_unlink_respaldo_falla(tmp_path, monkeypatch):
    s = tmp_path / "settings.json"
    s.write_bytes(ORIGINAL)
    resp = tmp_path / "resp"
    real_replace = ins.os.replace
    real_unlink = Path.unlink

    def replace_selectivo(src, dst):
        if Path(dst).name == "settings.json":
            raise OSError("corte")
        return real_replace(src, dst)

    def unlink_selectivo(self, missing_ok=False):
        if self.parent == resp and self.name.startswith("settings-"):
            raise OSError("unlink-fail")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(ins.os, "replace", replace_selectivo)
    monkeypatch.setattr(Path, "unlink", unlink_selectivo)
    with pytest.raises(OSError, match="corte"):
        ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)


def test_desinstalar_respaldo_corrupto_cae_estructural_preserva_ajenos(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"model": "keep", "hooks": {"Stop": [{"hooks": [AJENO]}]}}))
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    manifest = json.loads((resp / "ultimo.json").read_text())
    Path(manifest["respaldo"]).write_text("{ bad json")
    ins.desinstalar(s, resp)
    final = leer(s)
    assert final["model"] == "keep"
    assert AJENO in final["hooks"]["Stop"][0]["hooks"]
    assert not _tiene_colmena_en_datos(final)


def test_desinstalar_estructural_preserva_stop_vacio_y_extra_usuario(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"hooks": {"Stop": []}}))
    resp = tmp_path / "resp"
    ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    datos = leer(s)
    datos["extra"] = True
    s.write_text(json.dumps(datos))
    ins.desinstalar(s, resp)
    final = leer(s)
    assert final.get("extra") is True
    assert final["hooks"]["Stop"] == []
    assert not _tiene_colmena_en_datos(final)


def test_directorio_de_respaldos_queda_privado(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text('{"a": 1}')
    resp = tmp_path / "nuevo" / "respaldos"
    prev = os.umask(0o022)
    try:
        ins.instalar(s, resp, script=SCRIPT, espera=120, ahora=reloj)
    finally:
        os.umask(prev)
    assert stat.S_IMODE(resp.stat().st_mode) == 0o700
