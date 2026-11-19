import pytest

from orquestador import listas_seguridad as ls

_T_BASH_NET = frozenset(
    {
        "curl",
        "wget",
        "nc",
        "ncat",
        "netcat",
        "ssh",
        "scp",
        "sftp",
        "rsync",
        "ftp",
        "telnet",
        "ping",
        "dig",
        "nslookup",
        "http",
        "https",
        "httpie",
        "aws",
        "gcloud",
        "az",
        "kubectl",
        "docker",
        "gh",
        "glab",
        "apt",
        "apt-get",
        "brew",
    }
)
_T_GIT_REMOTO = frozenset(
    {"clone", "fetch", "pull", "push", "ls-remote", "remote", "submodule"}
)
_T_PKG = frozenset({"npm", "pnpm", "yarn", "pip", "pip3", "uv", "uvx", "npx", "bunx", "composer", "cargo", "go"})
_T_PKG_SUB = frozenset({"install", "add", "update", "publish", "get", "i"})
_T_EJEC = frozenset({"npx", "uvx", "bunx"})
_P_REDA = frozenset(
    "curl wget http https nc ncat socat ssh scp sftp rsync ftp telnet aws gcloud az "
    "kubectl helm terraform".split()
)
_P_FORJA = frozenset({"glab", "gh"})
_P_GIT_REMOTO = frozenset(
    "push fetch pull clone ls-remote submodule config credential daemon filter-branch "
    "send-email update-ref".split()
)
_P_INSTALADORES = frozenset({"pip", "pip3", "pipx", "uvx", "pnpm", "yarn", "bunx"})
_R_BASENAMES = frozenset(
    {
        ".mcp.json",
        ".envrc",
        ".bashrc",
        ".profile",
        ".zshrc",
        ".bash_profile",
        "authorized_keys",
        "package.json",
        "Makefile",
        "makefile",
        "GNUmakefile",
        "conftest.py",
        "CLAUDE.md",
        "AGENTS.md",
        "pyproject.toml",
        "setup.py",
        ".gitlab-ci.yml",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "tox.ini",
        "noxfile.py",
        "setup.cfg",
        "pytest.ini",
        "Justfile",
        "justfile",
        "Rakefile",
        ".pre-commit-config.yaml",
        "sitecustomize.py",
    }
)
_R_SEGMENTOS = frozenset({".claude", ".git", ".github", ".husky", ".vscode"})


def test_listas_viejas_incluidas_en_las_unificadas():
    assert _T_BASH_NET <= ls.COMANDOS_CONTAMINAN
    assert _P_REDA <= ls.COMANDOS_RED
    assert _P_FORJA <= ls.FORJAS
    assert _P_GIT_REMOTO == ls.GIT_SUB_REMOTOS
    assert _T_GIT_REMOTO <= ls.GIT_SUB_CONTAMINAN
    assert "remote" not in ls.GIT_SUB_REMOTOS
    assert _P_INSTALADORES <= ls.INSTALADORES_RED
    assert _T_PKG <= ls.GESTORES_PAQUETES and _T_PKG_SUB <= ls.SUB_INSTALACION
    assert _T_EJEC <= ls.EJECUTORES_REMOTOS
    assert _R_BASENAMES <= ls.BASENAMES_SENSIBLES
    assert _R_SEGMENTOS <= ls.SEGMENTOS_SENSIBLES
    assert "docker" in ls.COMANDOS_CONTAMINAN and "docker" not in ls.COMANDOS_RED


@pytest.mark.parametrize(
    "ruta",
    [
        "usercustomize.py",
        "composer.json",
        ".npmrc",
        ".yarnrc",
        ".yarnrc.yml",
        "uv.lock",
        "uv.toml",
        "vitest.config.ts",
        "vitest.workspace.ts",
        "vite.config.mjs",
        "jest.config.js",
        "eslint.config.js",
        ".eslintrc.json",
        "babel.config.js",
        ".babelrc",
        "postcss.config.cjs",
        "tailwind.config.ts",
        "vue.config.js",
        "nuxt.config.ts",
        "webpack.config.js",
        "rollup.config.mjs",
        "playwright.config.ts",
        "phpunit.xml",
        "phpunit.xml.dist",
        "lib/x.pth",
        ".venv/x.py",
        "venv/lib/x.py",
        "node_modules/.bin/vitest",
        ".githooks/pre-commit",
        ".vscode/settings.json",
        "src/sub/conftest.py",
    ],
)
def test_sensible(ruta):
    assert ls.es_archivo_sensible(ruta) is True
    assert ls.es_archivo_sensible(f"/p/{ruta}", "/p") is True


@pytest.mark.parametrize("nombre", sorted(_R_BASENAMES))
def test_basenames_viejos_siguen_sensibles(nombre):
    assert ls.es_archivo_sensible(f"/p/src/{nombre}", "/p") is True


@pytest.mark.parametrize(
    "ruta,proyecto",
    [
        ("/p/scripts/test-unit.sh", "/p"),
        ("/p/vendor/bin/phpunit", "/p"),
        ("vendor/bin/phpunit", None),
    ],
)
def test_rutas_ejecutables(ruta, proyecto):
    assert ls.es_archivo_sensible(ruta, proyecto) is True


@pytest.mark.parametrize(
    "ruta,proyecto",
    [
        ("/p/src/a.py", "/p"),
        ("/p/tests/test_x.py", "/p"),
        ("/p/README.md", "/p"),
        ("/p/tsconfig.json", "/p"),
        ("/p/package-lock.json", "/p"),
        ("/p/src/scripts/test-unit.sh", "/p"),
        ("/x/.venv/proj/src/a.py", "/x/.venv/proj"),
    ],
)
def test_no_sensible(ruta, proyecto):
    assert ls.es_archivo_sensible(ruta, proyecto) is False
