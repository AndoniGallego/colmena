from __future__ import annotations

import fnmatch
import os

_COMANDOS_RED_LIST = (
    "curl wget http https httpie nc ncat netcat socat ssh scp sftp rsync ftp telnet "
    "ping dig nslookup aws gcloud az kubectl helm terraform apt apt-get brew"
).split()

COMANDOS_RED: frozenset[str] = frozenset(_COMANDOS_RED_LIST)
FORJAS: frozenset[str] = frozenset({"gh", "glab"})
COMANDOS_CONTAMINAN: frozenset[str] = COMANDOS_RED | FORJAS | frozenset({"docker"})

GIT_SUB_REMOTOS: frozenset[str] = frozenset(
    "push fetch pull clone ls-remote submodule config credential daemon filter-branch "
    "send-email update-ref".split()
)
GIT_SUB_CONTAMINAN: frozenset[str] = GIT_SUB_REMOTOS | frozenset({"remote"})

INSTALADORES_RED: frozenset[str] = frozenset({"pip", "pip3", "pipx", "uvx", "pnpm", "yarn", "bunx"})
GESTORES_PAQUETES: frozenset[str] = frozenset(
    {"npm", "pnpm", "yarn", "pip", "pip3", "uv", "uvx", "npx", "bunx", "composer", "cargo", "go"}
)
SUB_INSTALACION: frozenset[str] = frozenset({"install", "add", "update", "publish", "get", "i"})
EJECUTORES_REMOTOS: frozenset[str] = frozenset({"npx", "uvx", "bunx"})

VARIABLES_PELIGROSAS: frozenset[str] = frozenset(
    "PATH LD_PRELOAD LD_LIBRARY_PATH PAGER GIT_PAGER EDITOR VISUAL BASH_ENV ENV "
    "NODE_OPTIONS PYTHONPATH PYTHONSTARTUP PYTHONHOME PERL5OPT RUBYOPT RIPGREP_CONFIG_PATH".split()
)
PREFIJOS_VARIABLES_PELIGROSAS: tuple[str, ...] = ("GIT_", "npm_config_")

_BASENAMES_VIEJOS = frozenset(
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
_BASENAMES_NUEVOS = frozenset(
    {
        "usercustomize.py",
        "composer.json",
        ".npmrc",
        ".yarnrc",
        ".yarnrc.yml",
        "uv.lock",
        "uv.toml",
    }
)
BASENAMES_SENSIBLES: frozenset[str] = _BASENAMES_VIEJOS | _BASENAMES_NUEVOS

PATRONES_EJECUTABLES: tuple[str, ...] = (
    "vitest.config.*",
    "vitest.workspace.*",
    "vite.config.*",
    "jest.config.*",
    "eslint.config.*",
    ".eslintrc.*",
    "babel.config.*",
    ".babelrc*",
    "postcss.config.*",
    "tailwind.config.*",
    "vue.config.*",
    "nuxt.config.*",
    "webpack.config.*",
    "rollup.config.*",
    "playwright.config.*",
    "phpunit.xml*",
    "*.pth",
)

SEGMENTOS_SENSIBLES: frozenset[str] = frozenset(
    {".claude", ".git", ".github", ".husky", ".vscode", ".venv", "venv", "node_modules", ".githooks"}
)

RUTAS_EJECUTABLES: tuple[str, ...] = ("scripts/test-unit.sh", "vendor/bin/*")


def _coincide_patron(base: str) -> bool:
    return any(fnmatch.fnmatchcase(base, patron) for patron in PATRONES_EJECUTABLES)


def _segmentos_a_revisar(ruta: str, rel: str | None) -> tuple[str, ...]:
    if rel is not None:
        return tuple(seg for seg in rel.replace("\\", "/").split("/") if seg)
    return tuple(seg for seg in ruta.replace("\\", "/").split("/") if seg)


def es_archivo_sensible(ruta: str, proyecto: str | None = None) -> bool:
    base = os.path.basename(ruta)
    if base in BASENAMES_SENSIBLES or _coincide_patron(base):
        return True

    rel: str | None
    if proyecto and os.path.isabs(ruta):
        proj = os.path.normpath(proyecto)
        ruta_n = os.path.normpath(ruta)
        if ruta_n == proj or ruta_n.startswith(proj + os.sep):
            rel = os.path.relpath(ruta_n, proj)
        else:
            rel = None
    elif not os.path.isabs(ruta):
        rel = os.path.normpath(ruta)
    else:
        rel = None

    for seg in _segmentos_a_revisar(ruta, rel):
        if seg in SEGMENTOS_SENSIBLES:
            return True

    if rel is not None:
        rel_slash = rel.replace("\\", "/")
        for patron in RUTAS_EJECUTABLES:
            if fnmatch.fnmatchcase(rel_slash, patron):
                return True

    return False


def destino_mv_sensible(
    origen: str,
    dest: str,
    proyecto: str | None,
    dest_resuelto: str | None = None,
) -> bool:
    dest_slash = dest.replace("\\", "/").rstrip("/")
    candidatos = [dest, f"{dest_slash}/{os.path.basename(origen)}"]
    if dest_resuelto:
        candidatos.append(dest_resuelto)
        candidatos.append(f"{dest_resuelto.rstrip(os.sep)}/{os.path.basename(origen)}")
    for cand in candidatos:
        if es_archivo_sensible(cand, proyecto):
            return True
    ref = dest_resuelto or dest_slash
    rel_cmp = os.path.normpath(ref.replace("\\", "/"))
    if proyecto:
        try:
            rel_proj = os.path.relpath(rel_cmp, os.path.normpath(proyecto))
            if not rel_proj.startswith(".."):
                rel_cmp = rel_proj
        except ValueError:
            pass
    rel = os.path.normpath(rel_cmp)
    if rel in (".", ""):
        return False
    primero = rel.replace("\\", "/").split("/")[0]
    if primero in SEGMENTOS_SENSIBLES:
        return True
    for patron in RUTAS_EJECUTABLES:
        raiz = patron.split("/")[0]
        if fnmatch.fnmatchcase(primero, raiz) or primero == raiz:
            return True
    return False
