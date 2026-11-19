import os

import pytest

from orquestador.permisos_regla import NEGADOS, PERMITIDOS, Regla, regla_acotada

CWD = "/home/u/proy"
HOME = "/home/u"
ident = lambda p: p


@pytest.mark.parametrize(
    "cmd,contenido",
    [
        ("touch foo", "touch:*"),
        ("ls -la src", "ls:*"),
        ("grep -r foo src", "grep:*"),
    ],
)
def test_bash_acotado(cmd, contenido):
    r = regla_acotada("Bash", {"command": cmd}, CWD, realpath=ident, home=HOME)
    assert r == Regla("Bash", contenido, "/home/u/proy/.claude/settings.local.json")


def test_permitidos_y_negados_disjuntos():
    assert PERMITIDOS & NEGADOS == set()


@pytest.mark.parametrize("cmd", ["uniq a b", "jq -n env"])
def test_uniq_y_jq_env_rechazados_como_printenv(cmd):
    assert regla_acotada("Bash", {"command": cmd}, CWD, realpath=ident, home=HOME) is None


@pytest.mark.parametrize(
    "cmd",
    [
        "python3.11 x",
        "python2 x",
        "pypy3 x",
        "nodejs x",
        "php8.2 x",
        "vim a",
        "less a",
        "gawk x",
        "gh pr",
        "glab mr",
        "source x",
        "ksh",
        "unshare x",
        "rg --pre x a",
        "sort --compress-program=x a",
        "pytest",
        "sqlite3 a",
        "make",
    ],
)
def test_bash_denylist_abierta(cmd):
    assert regla_acotada("Bash", {"command": cmd}, CWD, realpath=ident, home=HOME) is None


@pytest.mark.parametrize("cmd", sorted(PERMITIDOS))
def test_todo_permitido_recibe_regla(cmd):
    r = regla_acotada("Bash", {"command": f"{cmd} foo"}, CWD, realpath=ident, home=HOME)
    assert r == Regla("Bash", f"{cmd}:*", "/home/u/proy/.claude/settings.local.json")


HOSTILES = [
    "ls | sh",
    "ls; rm -rf /",
    "ls && curl x",
    "echo $(id)",
    "echo `id`",
    "ls > /etc/x",
    "ls < x",
    "ls\nrm -rf /",
    "sudo ls",
    "rm -rf build",
    "",
    "   ",
    "TOKEN=abc ls",
    "ls ~",
    "touch 'a b'",
    'touch "a"',
    "./script.sh",
    "/bin/ls",
    "bash -c ls",
    "git push",
    "find . -exec rm {} ;",
    "ls *",
    "Ls",
    "ls\\",
    "a" * 40,
    "nice ls",
    "tar xf a",
    "unlink a",
    "ls\tfoo",
    "ls\x00",
]


@pytest.mark.parametrize("cmd", HOSTILES)
def test_hostiles_no_ofrecen_siempre(cmd):
    assert regla_acotada("Bash", {"command": cmd}, CWD, realpath=ident, home=HOME) is None


@pytest.mark.parametrize("cmd", ["touch foo", "ls -la", "cat README.md", "head -n1 x"])
def test_propiedad_regla_nunca_mas_amplia(cmd):
    r = regla_acotada("Bash", {"command": cmd}, CWD, realpath=ident, home=HOME)
    assert r.contenido != "*" and r.contenido.endswith(":*") and cmd.split()[0] == r.contenido[:-2]
    assert "setMode" not in str(r) and "addDirectories" not in str(r)


def test_redaccion_altera_comando_sin_regla():
    assert regla_acotada("Bash", {"command": "export --password hunter2xyz"}, CWD, realpath=ident, home=HOME) is None


@pytest.mark.parametrize("entrada", [{"command": 3}, {}, None, "ls"])
def test_entrada_rara(entrada):
    assert regla_acotada("Bash", entrada, CWD, realpath=ident, home=HOME) is None


def test_edit_dentro_del_cwd():
    r = regla_acotada("Edit", {"file_path": "/home/u/proy/src/a.py"}, CWD, realpath=ident, home=HOME)
    assert r.contenido == "//home/u/proy/src/a.py" and r.herramienta == "Edit"


def test_write_app_py_siempre_acotado():
    r = regla_acotada(
        "Write", {"file_path": "/home/u/proy/src/app.py", "content": "x"}, CWD, realpath=ident, home=HOME
    )
    assert r is not None and r.herramienta == "Write"


@pytest.mark.parametrize(
    "herramienta,ruta",
    [
        ("Write", "/home/u/proy/package.json"),
        ("Edit", "/home/u/proy/Makefile"),
        ("MultiEdit", "/home/u/proy/conftest.py"),
        ("Write", "/home/u/proy/CLAUDE.md"),
        ("Edit", "/home/u/proy/.github/workflows/ci.yml"),
        ("Write", "/home/u/proy/.husky/pre-commit"),
        ("Edit", "/home/u/proy/.gitlab-ci.yml"),
        ("Write", "/home/u/proy/Dockerfile"),
        ("Edit", "/home/u/proy/docker-compose.yml"),
        ("Edit", "/home/u/proy/tox.ini"),
        ("Write", "/home/u/proy/Justfile"),
        ("Edit", "/home/u/proy/.pre-commit-config.yaml"),
        ("Write", "/home/u/proy/.vscode/tasks.json"),
    ],
)
def test_siempre_rechaza_archivos_sensibles(herramienta, ruta):
    entrada = {"file_path": ruta}
    if herramienta == "MultiEdit":
        entrada["edits"] = [{"old_string": "a", "new_string": "b"}]
    elif herramienta == "Write":
        entrada["content"] = "x"
    assert regla_acotada(herramienta, entrada, CWD, realpath=ident, home=HOME) is None


@pytest.mark.parametrize(
    "ruta",
    [
        "/etc/passwd",
        "/home/u/proy/../otro/a.py",
        "/home/u/proy/*.py",
        "src/a.py",
        "/home/u/proy/.claude/settings.local.json",
        "/home/u/proy",
        "/home/u/proy2/x",
        "/home/u/proy/sub/.claude/x",
        "/home/u/proy/.git/hooks/pre-commit",
    ],
)
def test_edit_fuera_o_raro(ruta):
    assert (
        regla_acotada(
            "Write",
            {"file_path": ruta},
            CWD,
            realpath=lambda p: p.replace("/proy/../otro", "/otro"),
            home=HOME,
        )
        is None
    )


@pytest.mark.parametrize(
    "basename",
    [
        ".mcp.json",
        ".envrc",
        ".bashrc",
        ".profile",
        ".zshrc",
        ".bash_profile",
        "authorized_keys",
    ],
)
def test_edit_rechaza_basenames_sensibles(basename):
    ruta = f"/home/u/proy/src/{basename}"
    assert regla_acotada("Write", {"file_path": ruta}, CWD, realpath=ident, home=HOME) is None


@pytest.mark.parametrize(
    "rel",
    [
        "composer.json",
        ".npmrc",
        "uv.lock",
        "vitest.config.ts",
        ".venv/x.py",
        "usercustomize.py",
        ".yarnrc.yml",
        "uv.toml",
        "phpunit.xml.dist",
        "vendor/bin/phpunit",
    ],
)
def test_edit_rechaza_archivos_que_se_ejecutan(rel):
    ruta = f"/home/u/proy/{rel}"
    assert regla_acotada("Edit", {"file_path": ruta}, CWD, realpath=ident, home=HOME) is None


@pytest.mark.parametrize("char", ["\\", "!", "#"])
def test_edit_rechaza_caracteres_en_file_path(char):
    ruta = f"/home/u/proy/src/a{char}b.py"
    assert regla_acotada("Edit", {"file_path": ruta}, CWD, realpath=ident, home=HOME) is None


def test_edit_file_path_nulo_sin_lanzar():
    ruta = "/home/u/proy/src/a\x00b.py"
    assert regla_acotada("Edit", {"file_path": ruta}, CWD, realpath=os.path.realpath, home=HOME) is None


def test_symlink_que_sale_del_cwd():
    rp = lambda p: "/etc/shadow" if p.endswith("link") else p
    assert regla_acotada("Edit", {"file_path": "/home/u/proy/link"}, CWD, realpath=rp, home=HOME) is None


@pytest.mark.parametrize("cwd", ["relativo", "/home/u/../u/proy", None, ""])
def test_cwd_invalido(cwd):
    assert regla_acotada("Bash", {"command": "ls"}, cwd, realpath=ident, home=HOME) is None


def test_cwd_con_symlink():
    assert regla_acotada("Bash", {"command": "ls"}, "/home/u/link", realpath=lambda p: "/home/u/real", home=HOME) is None


@pytest.mark.parametrize("cwd", ["/", HOME])
def test_cwd_raiz_o_home_rechazado(cwd):
    assert regla_acotada("Bash", {"command": "ls"}, cwd, realpath=ident, home=HOME) is None


@pytest.mark.parametrize("h", ["ExitPlanMode", "WebFetch", "mcp__x__y", "AskUserQuestion"])
def test_otras_herramientas(h):
    assert regla_acotada(h, {"command": "ls"}, CWD, realpath=ident, home=HOME) is None


def test_huella_estable_y_distinta():
    a = Regla("Bash", "ls:*", "/x/.claude/settings.local.json")
    assert a.huella() == Regla("Bash", "ls:*", "/x/.claude/settings.local.json").huella()
    assert a.huella() != Regla("Bash", "touch:*", "/x/.claude/settings.local.json").huella()


@pytest.mark.parametrize("token", sorted(NEGADOS))
def test_negados_nunca_regla(token):
    cmd = f"{token} foo" if token not in ("su",) else f"{token} root"
    assert regla_acotada("Bash", {"command": cmd}, CWD, realpath=ident, home=HOME) is None


def test_realpath_que_lanza_devuelve_none():
    def boom(_p):
        raise OSError("no")

    assert regla_acotada("Bash", {"command": "ls"}, CWD, realpath=boom, home=HOME) is None
