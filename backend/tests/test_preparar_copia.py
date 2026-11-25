import hashlib
from pathlib import Path
import os

import pytest

from orquestador.preparar_copia import leer_setup
from orquestador.traspaso import TraspasoError

from test_nueva_tarea import _git, repo  # noqa: F401  (fixture de repo temporal)


def _poner_setup(repo, toml, extra=None, ejecutable=("scripts/setup.sh",)):
    (repo / ".colmena").mkdir(exist_ok=True)
    (repo / ".colmena" / "setup.toml").write_text(toml, encoding="utf-8")
    for ruta, texto in (extra or {}).items():
        p = repo / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
        if ruta in ejecutable:
            p.chmod(0o755)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")


def _malo(repo, toml, extra=None, ejecutable=("scripts/setup.sh",)):
    _poner_setup(repo, toml, extra, ejecutable)
    with pytest.raises(TraspasoError) as exc:
        leer_setup(str(repo), "main")
    assert exc.value.status == 400
    return exc.value.detail


def test_parsear_setup_valido_y_claves_desconocidas_400(repo):
    _poner_setup(repo, 'copiar = [".env"]\nscript = "scripts/setup.sh"\npuertos = 10\ndocker = "puertos-variables"\n',
                 {"scripts/setup.sh": "#!/bin/sh\necho hola\n"})
    s = leer_setup(str(repo), "main")
    assert s.copiar == [".env"] and s.script == "scripts/setup.sh" and s.puertos == 10
    assert s.docker == "puertos-variables" and s.origen == "repo"
    assert s.toml_sha == hashlib.sha256(s.toml_texto.encode()).hexdigest()
    assert s.script_sha == hashlib.sha256(s.script_texto.encode()).hexdigest()
    assert "echo hola" in s.script_texto


def test_sin_setup_devuelve_none_y_archivo_vacio_tambien(repo):
    assert leer_setup(str(repo), "main") is None
    _poner_setup(repo, "# nada\n")
    assert leer_setup(str(repo), "main") is None


@pytest.mark.parametrize("toml,fragmento", [
    ('raro = 1\n', "clave desconocida: raro"),
    ('puertos = 11\n', "`puertos` va de 1 a 10"),
    ('puertos = 0\n', "`puertos` va de 1 a 10"),
    ('puertos = true\n', "`puertos` va de 1 a 10"),
    ('docker = "otro"\n', "`docker` solo acepta"),
    ('copiar = ".env"\n', "`copiar` tiene que ser una lista"),
    ('copiar = [".env", ".env"]\n', "`copiar` tiene que ser una lista"),
    ('copiar = [%s]\n' % ", ".join(f'"a{i}"' for i in range(21)), "`copiar` tiene que ser una lista"),
    ('copiar = [1]\n', "`copiar` tiene que ser una lista"),
    ('esto no es toml = = =\n', "no es válido"),
])
def test_setup_invalido_400(repo, toml, fragmento):
    assert fragmento in _malo(repo, toml)


def test_setup_toml_muy_grande_400(repo):
    assert "no es válido" in _malo(repo, "# " + "x" * 17000 + "\n")


@pytest.mark.parametrize("ruta", ["../x", "/etc/passwd", "a//b", "./a", ".git/config", "-x", ".colmena/env",
                                  "con espacio", "a/", "a/../b", ".colmena/otra", "a;b", "a/.git/b"])
def test_rutas_invalidas_400(repo, ruta):
    assert "ruta no permitida" in _malo(repo, f'copiar = ["{ruta}"]\n')


def test_ruta_invalida_en_script_400(repo):
    assert "ruta no permitida" in _malo(repo, 'script = "../x.sh"\n')


def test_script_no_ejecutable_400(repo):
    assert "tiene que ser ejecutable" in _malo(repo, 'script = "scripts/setup.sh"\n', {"scripts/setup.sh": "#!/bin/sh\n"},
                                               ejecutable=())


def test_script_symlink_400(repo):
    (repo / "real.sh").write_text("#!/bin/sh\n")
    (repo / "real.sh").chmod(0o755)
    (repo / "scripts").mkdir()
    os.symlink("../real.sh", repo / "scripts" / "setup.sh")
    assert "enlace" in _malo(repo, 'script = "scripts/setup.sh"\n')


def test_script_inexistente_400(repo):
    assert "script" in _malo(repo, 'script = "scripts/nada.sh"\n')


def test_script_muy_grande_400(repo):
    assert "script" in _malo(repo, 'script = "scripts/setup.sh"\n', {"scripts/setup.sh": "#!/bin/sh\n" + "#" * 70000})


def test_toml_symlink_400(repo):
    (repo / "otro.toml").write_text('puertos = 3\n')
    (repo / ".colmena").mkdir()
    os.symlink("../otro.toml", repo / ".colmena" / "setup.toml")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "x")
    with pytest.raises(TraspasoError) as exc:
        leer_setup(str(repo), "main")
    assert exc.value.status == 400 and "no es válido" in exc.value.detail


def test_override_reemplaza_al_toml(repo):
    _poner_setup(repo, 'puertos = 2\n')
    s = leer_setup(str(repo), "main", {"puertos": 5})
    assert s.puertos == 5 and s.origen == "config"
    assert s.toml_texto == '{"puertos":5}'
    with pytest.raises(TraspasoError):
        leer_setup(str(repo), "main", {"puertos": 5, "raro": 1})


# ---------- orígenes, copia, puertos, confianza, env ----------
import json
import stat

from orquestador.nueva_tarea import Worktrees, crear_worktree
from orquestador.preparar_copia import (ConfianzaPreparar, Setup, coincide_en_copia, copiar_ignorados, escribir_env,
                                        hay_compose, validar_origenes, verificar_ignorados)

SECRETO = "TOKEN=super-secreto-123\n"


def _ignorar(repo, *patrones):
    (repo / ".gitignore").write_text("\n".join(patrones) + "\n")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-q", "-m", "ignore")


def _setup(*copiar):
    return Setup(copiar=list(copiar))


def test_copiar_trackeado_400_sin_crear_copia(repo):
    (repo / ".env").write_text(SECRETO)
    _git(repo, "add", "-f", ".env")
    _git(repo, "commit", "-q", "-m", "mal")
    with pytest.raises(TraspasoError) as exc:
        validar_origenes(str(repo), "main", _setup(".env"))
    assert exc.value.status == 400 and "está versionado" in exc.value.detail
    assert not list(repo.parent.glob("proy-*"))


def test_copiar_trackeado_solo_en_la_base_400(repo):
    (repo / ".env").write_text(SECRETO)
    _git(repo, "add", "-f", ".env")
    _git(repo, "commit", "-q", "-m", "mal")
    _git(repo, "rm", "-q", "--cached", ".env")
    with pytest.raises(TraspasoError) as exc:
        validar_origenes(str(repo), "main", _setup(".env"))
    assert "está versionado" in exc.value.detail


def test_copiar_no_ignorado_400(repo):
    (repo / ".env").write_text(SECRETO)
    with pytest.raises(TraspasoError) as exc:
        validar_origenes(str(repo), "main", _setup(".env"))
    assert exc.value.status == 400 and "no está ignorado por git" in exc.value.detail


def test_origen_symlink_o_padre_symlink_400(repo, tmp_path):
    _ignorar(repo, ".env", "cfg/", "enlace.env")
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "secreto.env").write_text(SECRETO)
    os.symlink(fuera / "secreto.env", repo / "enlace.env")
    with pytest.raises(TraspasoError) as exc:
        validar_origenes(str(repo), "main", _setup("enlace.env"))
    assert exc.value.status == 400 and "enlace" in exc.value.detail
    os.symlink(fuera, repo / "cfg")
    with pytest.raises(TraspasoError) as exc:
        validar_origenes(str(repo), "main", _setup("cfg/secreto.env"))
    assert exc.value.status == 400 and "enlace" in exc.value.detail
    assert not list(repo.parent.glob("proy-*"))


def test_origen_directorio_o_muy_grande_400(repo):
    _ignorar(repo, "dir", "grande.env")
    (repo / "dir").mkdir()
    with pytest.raises(TraspasoError):
        validar_origenes(str(repo), "main", _setup("dir"))
    (repo / "grande.env").write_text("x" * (1024 * 1024 + 1))
    with pytest.raises(TraspasoError) as exc:
        validar_origenes(str(repo), "main", _setup("grande.env"))
    assert "1 MiB" in exc.value.detail


def test_copiar_inexistente_va_a_omitidos(repo):
    _ignorar(repo, ".env", ".env.local")
    (repo / ".env").write_text(SECRETO)
    existentes, omitidos = validar_origenes(str(repo), "main", _setup(".env", ".env.local"))
    assert existentes == [".env"] and omitidos == [".env.local"]


def test_env_ignorado_se_copia_igual_y_0600(repo):
    _ignorar(repo, ".env", "cfg/")
    (repo / ".env").write_text(SECRETO)
    (repo / "cfg").mkdir()
    (repo / "cfg" / "a.env").write_text("A=1\n")
    ruta = str(repo.parent / "proy-x")
    crear_worktree(str(repo), "feature/x", ruta, "main")
    copiar_ignorados(str(repo), ruta, [".env", "cfg/a.env"])
    assert open(os.path.join(ruta, ".env")).read() == SECRETO
    assert stat.S_IMODE(os.stat(os.path.join(ruta, ".env")).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(os.path.join(ruta, "cfg", "a.env")).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(os.path.join(ruta, "cfg")).st_mode) == 0o700
    assert _git(ruta, "status", "--porcelain") == ""


def test_destino_fuera_de_la_copia_por_symlink_versionado_se_rechaza(repo, tmp_path):
    _ignorar(repo, "orig.env")
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    os.symlink(fuera, repo / "cfg")
    _git(repo, "add", "cfg")
    _git(repo, "commit", "-q", "-m", "enlace")
    ruta = str(repo.parent / "proy-x")
    crear_worktree(str(repo), "feature/x", ruta, "main")
    # en el repo principal `cfg` pasa a ser una carpeta real con un ignorado; en la copia sigue siendo el enlace
    os.unlink(repo / "cfg")
    (repo / "cfg").mkdir()
    (repo / "cfg" / "orig.env").write_text(SECRETO)
    with pytest.raises(TraspasoError) as exc:
        copiar_ignorados(str(repo), ruta, ["cfg/orig.env"])
    assert exc.value.status == 400
    assert list(fuera.iterdir()) == []


def test_copiar_destino_existente_se_rechaza(repo):
    _ignorar(repo, "x.env")
    (repo / "x.env").write_text(SECRETO)
    ruta = str(repo.parent / "proy-x")
    crear_worktree(str(repo), "feature/x", ruta, "main")
    (Path(ruta) / "x.env").write_text("otro")
    with pytest.raises(TraspasoError):
        copiar_ignorados(str(repo), ruta, ["x.env"])
    assert (Path(ruta) / "x.env").read_text() == "otro"


def test_verificar_ignorados_y_coincide_en_copia(repo):
    _ignorar(repo, ".env", ".colmena/env")
    _poner_setup(repo, 'script = "scripts/setup.sh"\n', {"scripts/setup.sh": "#!/bin/sh\necho 1\n"})
    s = leer_setup(str(repo), "main")
    ruta = str(repo.parent / "proy-x")
    crear_worktree(str(repo), "feature/x", ruta, "main")
    assert coincide_en_copia(ruta, s) is True
    verificar_ignorados(ruta, [".colmena/env", ".env"])
    (Path(ruta) / "scripts" / "setup.sh").write_text("#!/bin/sh\necho 2\n")
    assert coincide_en_copia(ruta, s) is False


def test_verificar_ignorados_falla_si_no_estan_ignorados(repo):
    ruta = str(repo.parent / "proy-x")
    crear_worktree(str(repo), "feature/x", ruta, "main")
    with pytest.raises(TraspasoError) as exc:
        verificar_ignorados(ruta, [".colmena/env"])
    assert exc.value.status == 400 and "no está ignorado" in exc.value.detail


def test_hash_se_lee_de_la_base_no_del_arbol_de_trabajo(repo):
    _poner_setup(repo, 'script = "scripts/setup.sh"\n', {"scripts/setup.sh": "#!/bin/sh\necho base\n"})
    (repo / "scripts" / "setup.sh").write_text("#!/bin/sh\necho local\n")
    (repo / ".colmena" / "setup.toml").write_text('script = "scripts/setup.sh"\npuertos = 9\n')
    s = leer_setup(str(repo), "main")
    assert "echo base" in s.script_texto and s.puertos is None


# ---------- puertos ----------

def _entrada(n):
    return {"ruta": f"/r/c{n}", "repo": "/r", "rama": f"feature/x{n}", "base": "main"}


def test_reservar_bloques_distintos_y_libera_al_quitar(tmp_path):
    w = Worktrees(tmp_path)
    assert w.reservar({**_entrada(1), "puertos": 10}, True) == 41000
    assert w.reservar({**_entrada(2), "puertos": 3}, True) == 41010
    assert w.get("/r/c2")["puerto"] == 41010 and w.get("/r/c2")["puertos"] == 3
    w.quitar("/r/c1")
    assert w.reservar({**_entrada(3), "puertos": 10}, True) == 41000
    assert w.reservar(_entrada(4), False) is None
    assert "puerto" not in w.get("/r/c4")


def test_reservar_saltea_bloqueados_y_puertos_de_colmena(tmp_path):
    w = Worktrees(tmp_path)
    vedados = frozenset({41005, 41029})
    assert w.reservar({**_entrada(1), "puertos": 1}, True, bloqueados=vedados) == 41010
    assert w.reservar({**_entrada(2), "puertos": 1}, True, bloqueados=vedados) == 41030


def test_reservar_sin_bloques_409(tmp_path):
    w = Worktrees(tmp_path)
    for n in range(100):
        w.reservar({**_entrada(n), "puertos": 1}, True)
    assert w.get("/r/c99")["puerto"] == 41990
    with pytest.raises(TraspasoError) as exc:
        w.reservar({**_entrada(100), "puertos": 1}, True)
    assert exc.value.status == 409 and "puertos libres" in exc.value.detail
    assert w.get("/r/c100") is None


def test_worktrees_agregar_conserva_puerto_y_todas_tolera_basura(tmp_path):
    w = Worktrees(tmp_path)
    w.agregar({**_entrada(1), "puerto": 41000, "puertos": 10})
    assert w.get("/r/c1")["puerto"] == 41000
    w.agregar(_entrada(2))
    assert "puerto" not in w.get("/r/c2")
    w.path.write_text(json.dumps({"v": 1, "copias": [
        {**_entrada(3), "puerto": "malo", "puertos": True}, {**_entrada(4), "puerto": 41010, "puertos": 2}, "x"]}))
    assert [e["ruta"] for e in w.todas()] == ["/r/c3", "/r/c4"]
    assert "puerto" not in w.get("/r/c3") and "puertos" not in w.get("/r/c3")
    assert w.get("/r/c4")["puerto"] == 41010


# ---------- confianza ----------

def test_confianza_falta_cambia_toml_cambia_script_y_json_corrupto(tmp_path):
    c = ConfianzaPreparar(tmp_path)
    repo = "/abs/repo"
    a, b, a2, b2 = "a" * 64, "b" * 64, "c" * 64, "d" * 64
    assert c.hay(repo, a, b) is False
    c.guardar(repo, a, b)
    assert c.hay(repo, a, b) is True
    assert c.hay(repo, a2, b) is False and c.hay(repo, a, b2) is False and c.hay(repo, a, None) is False
    assert c.hay("/otro", a, b) is False
    c.guardar(repo, a2, None)
    assert c.hay(repo, a, b) is False and c.hay(repo, a2, None) is True
    assert stat.S_IMODE(os.stat(c.path).st_mode) == 0o600
    c.path.write_text("{no es json")
    assert c.hay(repo, a2, None) is False
    c.path.write_text(json.dumps({"v": 1, "repos": {repo: "basura"}}))
    assert c.hay(repo, a2, None) is False


# ---------- .colmena/env ----------

def test_env_colmena_contenido_y_0600_con_y_sin_compose(tmp_path):
    copia = tmp_path / "Tienda-SITE_123"
    copia.mkdir()
    escribir_env(str(copia), 41000, 10, True)
    texto = (copia / ".colmena" / "env").read_text()
    assert texto == "COLMENA_PORT=41000\nCOLMENA_PORT_COUNT=10\nCOMPOSE_PROJECT_NAME=tienda-site_123\n"
    assert stat.S_IMODE(os.stat(copia / ".colmena" / "env").st_mode) == 0o600
    otra = tmp_path / "Raro"
    otra.mkdir()
    escribir_env(str(otra), 41010, 2, False)
    assert (otra / ".colmena" / "env").read_text() == "COLMENA_PORT=41010\nCOLMENA_PORT_COUNT=2\n"
    fijo = tmp_path / "fijo"
    fijo.mkdir()
    escribir_env(str(fijo), None, None, True)
    assert (fijo / ".colmena" / "env").read_text() == "COMPOSE_PROJECT_NAME=fijo\n"
    cx = tmp_path / "Mi Tienda.x"
    cx.mkdir()
    escribir_env(str(cx), 41010, 2, True)
    assert "COMPOSE_PROJECT_NAME=mi-tienda-x\n" in (cx / ".colmena" / "env").read_text()


def test_env_colmena_rechaza_symlink_y_destino_existente(tmp_path):
    copia = tmp_path / "c"
    copia.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    os.symlink(fuera, copia / ".colmena")
    with pytest.raises(TraspasoError):
        escribir_env(str(copia), 41000, 1, False)
    assert list(fuera.iterdir()) == []
    os.unlink(copia / ".colmena")
    (copia / ".colmena").mkdir()
    (copia / ".colmena" / "env").write_text("previo")
    with pytest.raises(TraspasoError):
        escribir_env(str(copia), 41000, 1, False)


def test_hay_compose(tmp_path):
    assert hay_compose(str(tmp_path)) is False
    (tmp_path / "compose.yaml").write_text("services: {}\n")
    assert hay_compose(str(tmp_path)) is True
