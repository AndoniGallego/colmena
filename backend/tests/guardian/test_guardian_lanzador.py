import json
import os
import stat
import uuid
from pathlib import Path

import pytest

from orquestador.guardian import lanzador as lz


def test_bypass_rechazado():
    with pytest.raises(lz.ConfigInvalida):
        lz.ajustes_de({"permission_mode": "bypassPermissions"}, {})


def test_entorno_hijo_filtra():
    base = {
        "HOME": "/home/u",
        "HERDR_PANE_ID": "w1:p1",
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "x",
        "LC_ALL": "es_AR.UTF-8",
        "SECRET": "no",
    }
    env = lz.entorno_hijo(base, "g1:p2", lz.AjustesGuardian())
    assert "HERDR_PANE_ID" not in env
    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_SESSION_ID" not in env
    assert env["LC_ALL"] == "es_AR.UTF-8"
    assert env["COLMENA_SESION"] == "g1:p2"


def test_env_extra():
    base = {"HOME": "/h", "MI_VAR": "ok", "CLAUDE_CODE_FOO": "bar"}
    a = lz.ajustes_de({"env_extra": ["MI_VAR", "CLAUDE_CODE_FOO"]}, base)
    env = lz.entorno_hijo(base, "g1:p1", a)
    assert env["MI_VAR"] == "ok"
    assert env["CLAUDE_CODE_FOO"] == "bar"


def test_argv_claude_nuevo():
    uid = str(uuid.uuid4())
    a = lz.AjustesGuardian(permission_mode="plan")
    argv = lz.argv_claude(a, Path("/tmp/hooks.json"), session_id=uid)
    assert argv == [
        "claude",
        "--session-id",
        uid,
        "--settings",
        "/tmp/hooks.json",
        "--permission-mode",
        "plan",
    ]


def test_argv_claude_resume():
    uid = str(uuid.uuid4())
    a = lz.AjustesGuardian()
    argv = lz.argv_claude(a, Path("/s.json"), resume=uid)
    assert argv[1] == "--resume" and argv[2] == uid


def test_argv_shell():
    assert lz.argv_shell(lz.AjustesGuardian(), {"SHELL": "/bin/zsh"}) == ["/bin/zsh", "-l"]


def test_hooks_json(tmp_path):
    ruta = lz.escribir_hooks(tmp_path, 15)
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    data = json.loads(ruta.read_text())
    cmds = []
    for bloques in data["hooks"].values():
        for bloque in bloques:
            for hook in bloque.get("hooks", []):
                cmds.append(hook["command"])
    assert cmds and all("COLMENA_GANCHO_ORIGEN=settings" in c for c in cmds)


def test_argv_claude_modo_por_lanzamiento_default():
    uid = str(uuid.uuid4())
    a = lz.AjustesGuardian(permission_mode="auto")
    argv = lz.argv_claude(a, Path("/s.json"), session_id=uid, modo="default")
    assert argv[-2:] == ["--permission-mode", "default"]
    argv = lz.argv_claude(a, Path("/s.json"), resume=uid, modo="plan")
    assert argv[-2:] == ["--permission-mode", "plan"]
    argv = lz.argv_claude(a, Path("/s.json"), resume=uid, modo=None)
    assert argv[-2:] == ["--permission-mode", "auto"]


@pytest.mark.parametrize("modo", ["auto", "dontAsk", "acceptEdits", "bypassPermissions", "", "DEFAULT"])
def test_argv_claude_rechaza_modos_que_relajan(modo):
    uid = str(uuid.uuid4())
    with pytest.raises(ValueError):
        lz.argv_claude(lz.AjustesGuardian(), Path("/s.json"), session_id=uid, modo=modo)
    assert lz.MODOS_POR_LANZAMIENTO == frozenset({"default", "plan"})


def test_argv_copiloto_solo_lectura():
    uid = str(uuid.uuid4())
    a = lz.AjustesGuardian(permission_mode="auto")
    argv = lz.argv_claude(a, Path("/s.json"), session_id=uid, modo="copiloto")
    # El Copiloto usa su propio --settings: los hooks de siempre más el bloqueo de lecturas afuera.
    assert argv == [a.claude_bin, "--session-id", uid, "--settings", "/ajustes-copiloto.json",
                    *lz.args_memoria("copiloto", ""), *lz.ARGS_COPILOTO]
    assert lz.ARGS_COPILOTO == ("--permission-mode", "dontAsk", "--tools", "Read,Grep,Glob,Bash",
                                "--setting-sources", "project,local", "--strict-mcp-config",
                                "--model", "sonnet")
    junto = " ".join(argv)
    assert "acceptEdits" not in junto and "auto" not in argv and "--dangerously-skip-permissions" not in junto
    assert argv.count("--permission-mode") == 1
    argv = lz.argv_claude(a, Path("/s.json"), resume=uid, modo="copiloto")
    assert argv[1:3] == ["--resume", uid]
    with pytest.raises(ValueError):
        lz.argv_claude(a, Path("/s.json"), session_id=uid, modo="dontAsk")


def test_copiloto_es_modo_interno_y_no_de_lanzamiento():
    assert lz.MODOS_INTERNOS == frozenset({"copiloto", "guia"})
    assert "copiloto" not in lz.MODOS_POR_LANZAMIENTO


def test_es_carpeta_copiloto(tmp_path, monkeypatch):
    destino = tmp_path / "reunion-copiloto"
    destino.mkdir()
    monkeypatch.setattr(lz, "CARPETA_COPILOTO", destino)
    assert lz.es_carpeta_copiloto(str(destino))
    assert lz.es_carpeta_copiloto(str(destino) + "/")
    assert not lz.es_carpeta_copiloto(str(tmp_path))
    assert not lz.es_carpeta_copiloto(str(destino / "sub"))
    assert lz.CARPETA_COPILOTO.name == "reunion-copiloto"


def test_carpeta_copiloto_fuera_del_repo_y_del_data_dir(tmp_path):
    assert lz.carpeta_copiloto({"XDG_DATA_HOME": str(tmp_path / "xdg"), "HOME": str(tmp_path / "h")}) == (
        tmp_path / "xdg" / "orquestador" / "reunion-copiloto")
    assert lz.carpeta_copiloto({"HOME": str(tmp_path / "h")}) == (
        tmp_path / "h" / ".local" / "share" / "orquestador" / "reunion-copiloto")
    # Un XDG_DATA_HOME relativo no vale (la especificación XDG lo ignora).
    assert lz.carpeta_copiloto({"XDG_DATA_HOME": "rel", "HOME": str(tmp_path / "h")}).is_relative_to(tmp_path / "h")
    # Si XDG_DATA_HOME cae dentro del repo o del data dir, se usa la de HOME.
    dentro = lz.carpeta_copiloto({"XDG_DATA_HOME": str(lz.REPO_ROOT / "data"), "HOME": str(tmp_path / "h")})
    assert not dentro.is_relative_to(lz.REPO_ROOT)
    datos = tmp_path / "datos"
    otra = lz.carpeta_copiloto({"XDG_DATA_HOME": str(datos / "x"), "ORQ_DATA_DIR": str(datos),
                                "HOME": str(tmp_path / "h")})
    assert not otra.is_relative_to(datos)
    real = lz.CARPETA_COPILOTO
    assert not real.is_relative_to(lz.REPO_ROOT) and "data" not in real.relative_to(real.anchor).parts[-2:]


def test_rutas_protegidas_incluye_repo_y_data_dir(tmp_path):
    assert lz.rutas_protegidas({"ORQ_DATA_DIR": str(tmp_path / "d")}) == [str(lz.REPO_ROOT), str(tmp_path / "d")]
    assert lz.rutas_protegidas({}) == [str(lz.REPO_ROOT), str(lz.REPO_ROOT / "data")]


def test_escribir_hooks_deja_los_ajustes_del_copiloto(tmp_path):
    ruta = lz.escribir_hooks(tmp_path, 15, protegidos=["/orq", "/orq/data"])
    cop = lz.ajustes_copiloto(ruta)
    assert cop == tmp_path / "ajustes-copiloto.json"
    assert stat.S_IMODE(cop.stat().st_mode) == 0o600
    datos = json.loads(cop.read_text())
    colmena = json.loads(ruta.read_text())["hooks"]
    for evento, bloques in colmena.items():
        assert all(b in datos["hooks"][evento] for b in bloques)
    assert datos["permissions"]["blockReadsOutsideWorkingDirectories"] is True
    assert datos["permissions"]["workingDirectoriesExclude"] == ["/orq", "/orq/data"]


def test_ajustes_del_copiloto_llevan_el_hook_que_limita_bash(tmp_path):
    import sys
    from orquestador.ganchos.copiloto_bash import definicion
    ruta = lz.escribir_hooks(tmp_path, 15, protegidos=[])
    datos = json.loads(lz.ajustes_copiloto(ruta).read_text())
    esperado = definicion(sys.executable)["PreToolUse"][0]
    assert esperado in datos["hooks"]["PreToolUse"]
    assert esperado not in json.loads(ruta.read_text())["hooks"]["PreToolUse"]


def test_entorno_hijo_del_copiloto_suma_el_bin_del_venv_al_path(tmp_path, monkeypatch):
    import sys
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "orquestador").write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "executable", str(bin_dir / "python"))
    a = lz.AjustesGuardian(path="/usr/bin:/bin")
    assert lz.entorno_hijo({}, "g1:p1", a)["PATH"] == "/usr/bin:/bin"
    assert lz.entorno_hijo({}, "g1:p1", a, copiloto=True)["PATH"] == f"/usr/bin:/bin:{bin_dir}"


def test_entorno_hijo_del_copiloto_sin_orquestador_no_toca_el_path(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    a = lz.AjustesGuardian(path="/usr/bin:/bin")
    assert lz.entorno_hijo({}, "g1:p1", a, copiloto=True)["PATH"] == "/usr/bin:/bin"


def _entorno_prot(tmp_path):
    datos = tmp_path / "colmena-data"
    datos.mkdir(exist_ok=True)
    return {"ORQ_DATA_DIR": str(datos)}


def test_argv_copiloto_agrega_add_dir_por_cada_repo_valido(tmp_path):
    a = lz.AjustesGuardian()
    uid = str(uuid.uuid4())
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    r1.mkdir()
    r2.mkdir()
    base = lz.argv_claude(a, Path("/s.json"), session_id=uid, modo="copiloto")
    argv = lz.argv_claude(a, Path("/s.json"), session_id=uid, modo="copiloto",
                          dirs_extra=[str(r1), str(r2)], entorno=_entorno_prot(tmp_path))
    assert argv == [*base, "--add-dir", os.path.realpath(r1), "--add-dir", os.path.realpath(r2)]
    sin = lz.argv_claude(a, Path("/s.json"), session_id=uid, modo="copiloto", dirs_extra=[])
    assert sin == base
    res = lz.argv_claude(a, Path("/s.json"), resume=uid, modo="copiloto",
                         dirs_extra=[str(r1)], entorno=_entorno_prot(tmp_path))
    assert res[-2:] == ["--add-dir", os.path.realpath(r1)]


def test_dirs_extra_descarta_lo_invalido(tmp_path):
    entorno = _entorno_prot(tmp_path)
    ok = tmp_path / "ok"
    ok.mkdir()
    archivo = tmp_path / "f.txt"
    archivo.write_text("x")
    enlace = tmp_path / "enlace"
    enlace.symlink_to(ok)
    datos = Path(entorno["ORQ_DATA_DIR"])
    (datos / "sub").mkdir()
    candidatos = [
        "relativa/x", str(tmp_path / "no-existe"), str(archivo), str(lz.REPO_ROOT),
        str(lz.REPO_ROOT / "backend"), str(datos), str(datos / "sub"), 7, None, "/tmp/a\x00b", "/tmp/a\nb",
        str(ok), str(ok), str(enlace),
    ]
    assert lz.dirs_extra_validos(candidatos, entorno) == [os.path.realpath(ok)]


def test_dirs_extra_descarta_lo_que_contiene_a_colmena(tmp_path):
    entorno = _entorno_prot(tmp_path)
    datos = Path(entorno["ORQ_DATA_DIR"])
    candidatos = [str(lz.REPO_ROOT.parent), str(datos.parent), "/"]
    assert lz.dirs_extra_validos(candidatos, entorno) == []


def test_dirs_extra_tope_y_forma(tmp_path):
    entorno = _entorno_prot(tmp_path)
    dirs = []
    for i in range(lz.MAX_DIRS_EXTRA + 5):
        d = tmp_path / f"d{i}"
        d.mkdir()
        dirs.append(str(d))
    assert len(lz.dirs_extra_validos(dirs, entorno)) == lz.MAX_DIRS_EXTRA
    assert lz.dirs_extra_validos("no-es-lista", entorno) == []


def test_dirs_extra_solo_en_modo_copiloto(tmp_path):
    uid = str(uuid.uuid4())
    d = tmp_path / "d"
    d.mkdir()
    for modo in (None, "default", "plan"):
        with pytest.raises(ValueError):
            lz.argv_claude(lz.AjustesGuardian(), Path("/s.json"), session_id=uid, modo=modo, dirs_extra=[str(d)])


def test_guia_es_modo_interno():
    assert "guia" in lz.MODOS_INTERNOS
    assert "guia" not in lz.MODOS_POR_LANZAMIENTO


def test_carpeta_guia_xdg_y_respaldo(tmp_path):
    assert lz.carpeta_guia({"XDG_DATA_HOME": "/x/data", "HOME": str(tmp_path / "h")}) == Path("/x/data/orquestador/guia")
    por_defecto = tmp_path / "h" / ".local" / "share" / "orquestador" / "guia"
    assert lz.carpeta_guia({"XDG_DATA_HOME": "rel", "HOME": str(tmp_path / "h")}) == por_defecto
    protegida = lz.carpeta_guia({"XDG_DATA_HOME": str(lz.REPO_ROOT / "data"), "HOME": str(tmp_path / "h")})
    assert protegida == por_defecto
    assert lz.CARPETAS_INTERNAS == {"copiloto": "reunion-copiloto", "guia": "guia"}
    assert lz.CARPETA_GUIA.name == "guia"


def test_argv_guia_solo_lectura_sin_add_dir():
    a = lz.AjustesGuardian()
    uid = str(uuid.uuid4())
    argv = lz.argv_claude(a, Path("/s.json"), session_id=uid, modo="guia")
    assert argv == [a.claude_bin, "--session-id", uid, "--settings", "/ajustes-copiloto.json",
                    *lz.args_memoria("guia", ""), *lz.ARGS_COPILOTO]
    assert "--add-dir" not in argv


def test_dirs_extra_con_guia_es_error(tmp_path):
    a = lz.AjustesGuardian()
    with pytest.raises(ValueError):
        lz.argv_claude(a, Path("/s.json"), session_id=str(uuid.uuid4()), modo="guia", dirs_extra=[str(tmp_path)])


def test_es_carpeta_interna_no_cruza_modos(tmp_path, monkeypatch):
    cop, gui = tmp_path / "reunion-copiloto", tmp_path / "guia"
    cop.mkdir()
    gui.mkdir()
    monkeypatch.setattr(lz, "CARPETA_COPILOTO", cop)
    monkeypatch.setattr(lz, "CARPETA_GUIA", gui)
    assert lz.es_carpeta_interna("guia", str(gui))
    assert lz.es_carpeta_interna("copiloto", str(cop))
    assert not lz.es_carpeta_interna("guia", str(cop))
    assert not lz.es_carpeta_interna("copiloto", str(gui))
    assert not lz.es_carpeta_interna("otro", str(gui))
    assert lz.carpeta_de_modo("guia") == gui


def test_guia_y_copiloto_corren_con_sonnet():
    """Las sesiones internas hacen tareas cortas y repetidas: no usan el modelo caro por defecto."""
    a = lz.AjustesGuardian()
    uid = str(uuid.uuid4())
    for modo in ("guia", "copiloto"):
        argv = lz.argv_claude(a, Path("/s.json"), session_id=uid, modo=modo)
        i = argv.index("--model")
        assert argv[i + 1] == "sonnet"


def _server_engram(argv):
    import json

    i = argv.index("--mcp-config")
    assert argv[i + 2].startswith("--")
    config = json.loads(argv[i + 1])
    assert list(config["mcpServers"]) == ["engram"]
    return config["mcpServers"]["engram"]


def test_guia_y_copiloto_tienen_memoria_propia_en_engram():
    """Cada ayudante aprende en su proyecto de Engram, detrás del filtro que fuerza el proyecto."""
    import sys

    a = lz.AjustesGuardian(memoria_contenedor="mi-engram")
    uid = str(uuid.uuid4())
    proyectos = set()
    for modo in ("guia", "copiloto"):
        argv = lz.argv_claude(a, Path("/s.json"), session_id=uid, modo=modo)
        assert argv.count("--mcp-config") == 1 and "--strict-mcp-config" in argv
        server = _server_engram(argv)
        assert server["command"] == sys.executable
        args = server["args"]
        assert args[:3] == ["-I", "-m", "orquestador.memoria_filtro"]
        sep = args.index("--")
        propio = args[args.index("--propio") + 1]
        assert propio == f"colmena-{modo}"
        assert "--trabajo" not in args[:sep]
        hijo = args[sep + 1:]
        assert hijo[:6] == ["docker", "exec", "-i", "mi-engram", "engram", "mcp"]
        assert "--tools=mem_search,mem_save,mem_get_observation" in hijo
        assert hijo[hijo.index("--project") + 1] == propio
        proyectos.add(propio)
    assert len(proyectos) == 2


def test_memoria_de_trabajo_se_pasa_al_filtro():
    a = lz.AjustesGuardian(memoria_contenedor="mi-engram", memoria_trabajo="mi-trabajo")
    argv = lz.argv_claude(a, Path("/s.json"), session_id=str(uuid.uuid4()), modo="guia")
    args = _server_engram(argv)["args"]
    assert args[args.index("--trabajo") + 1] == "mi-trabajo"
    assert args.index("--trabajo") < args.index("--")


def test_sesion_normal_no_lleva_memoria_de_ayudante():
    a = lz.AjustesGuardian(memoria_contenedor="mi-engram")
    argv = lz.argv_claude(a, Path("/s.json"), session_id=str(uuid.uuid4()))
    assert "--mcp-config" not in argv


def test_sin_contenedor_configurado_los_ayudantes_no_tienen_memoria():
    argv = lz.argv_claude(lz.AjustesGuardian(), Path("/s.json"), session_id=str(uuid.uuid4()), modo="guia")
    assert "--mcp-config" not in argv


def test_memoria_contenedor_sale_de_la_config_y_se_valida():
    assert lz.ajustes_de({"memoria_contenedor": "mi-engram"}, {}).memoria_contenedor == "mi-engram"
    assert lz.ajustes_de({}, {}).memoria_contenedor == ""
    for malo in ("-x", "a b", "a;b", 3):
        with pytest.raises(lz.ConfigInvalida):
            lz.ajustes_de({"memoria_contenedor": malo}, {})


def test_memoria_trabajo_sale_de_la_config_y_se_valida():
    assert lz.ajustes_de({"memoria_trabajo": "mi-trabajo"}, {}).memoria_trabajo == "mi-trabajo"
    assert lz.ajustes_de({}, {}).memoria_trabajo == ""
    for malo in ("-x", "A", "a b", "a;b", 3, "x" * 65):
        with pytest.raises(lz.ConfigInvalida):
            lz.ajustes_de({"memoria_trabajo": malo}, {})
