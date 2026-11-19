import asyncio
import copy
import json
import os
import shlex
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

pytest_plugins = ["permisos_support"]

from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.config import Config, hash_pin
from orquestador.enchufe import FakeTerminales, crear_terminales, herdr as herdr_module
from orquestador.enchufe.herdr import HerdrError
from orquestador.digest import DigestService
from orquestador.state import StateStore

SID = "11111111-2222-3333-4444-555555555555"
PIN = "43215678"
ORIGIN = {"Origin": "http://testserver"}


def make_snapshot(status="idle"):
    return {
        "focused_tab_id": "w1:t1",
        "workspaces": [
            {"workspace_id": "w2", "number": 2, "label": "Dos", "agent_status": "idle"},
            {"workspace_id": "w1", "number": 1, "label": "Uno", "agent_status": status},
        ],
        "tabs": [
            {"tab_id": "w1:t1", "workspace_id": "w1", "label": "1"},
            {"tab_id": "w2:t1", "workspace_id": "w2", "label": "vacío"},
            {"tab_id": "w2:t2", "workspace_id": "w2", "label": "propio"},
        ],
        "agents": [
            {"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1", "agent": "claude",
             "agent_status": status, "cwd": "/tmp", "terminal_title_stripped": "Título terminal",
             "state_change_seq": 7, "agent_session": {"kind": "id", "value": SID}},
            {"pane_id": "w2:p9", "tab_id": "w2:t2", "workspace_id": "w2", "agent": "claude",
             "agent_status": "weird", "terminal_title_stripped": "Propio",
             "agent_session": {"kind": "id", "value": "nope"}},
        ],
        "panes": [
            {"pane_id": "w1:p1", "tab_id": "w1:t1", "workspace_id": "w1"},
            {"pane_id": "w2:p1", "tab_id": "w2:t1", "workspace_id": "w2"},
            {"pane_id": "w2:p9", "tab_id": "w2:t2", "workspace_id": "w2"},
        ],
    }


def write_transcript(projects, sid=SID):
    folder = projects / "-proj"
    folder.mkdir(parents=True)
    lines = [
        {"type": "ai-title", "aiTitle": "Viejo"},
        {"type": "user", "message": {"content": "<system-reminder>x</system-reminder>"}},
        {"type": "user", "message": {"content": "hola uno"}},
        {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "..."},
                                                        {"type": "text", "text": "respuesta uno"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "Another Claude session sent a message"}]}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "segundo"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "¿Seguimos con esto?"}]}},
        {"type": "ai-title", "aiTitle": "Título nuevo"},
        {"type": "last-prompt", "lastPrompt": "segundo"},
    ]
    path = folder / f"{sid}.jsonl"
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\nbasura\n", encoding="utf-8")
    return path


class FakeHerdr:
    supports_socket = False

    def __init__(self, snapshot=None):
        self.current = snapshot or make_snapshot()
        self.focused = []
        self.calls = []
        self.responses = {}
        self.apply_closes = True
        self.fail_snapshot_after_close = False
        self.caido = False
        self.handlers = {}

    async def snapshot(self):
        if self.caido:
            raise HerdrError("sin respuesta")
        if self.fail_snapshot_after_close and any(c[1:2] == ("close",) for c in self.calls):
            raise HerdrError("sin respuesta")
        snap = copy.deepcopy(self.current)
        seen: dict = {}
        for source in ("panes", "agents"):
            for pane in snap.get(source, []):
                pane.setdefault("terminal_id", f"term-{pane['pane_id']}")
                seen[pane["pane_id"]] = pane
        for key, items in (("tab_id", snap.get("tabs", [])), ("workspace_id", snap.get("workspaces", []))):
            for item in items:
                item.setdefault("pane_count", sum(1 for p in seen.values() if p.get(key) == item[key]))
        return snap

    def _drop(self, tabs: set, workspaces: set) -> None:
        snap = self.current
        snap["tabs"] = [t for t in snap["tabs"] if t["tab_id"] not in tabs]
        gone = tabs | {t["tab_id"] for t in snap["tabs"] if t["workspace_id"] in workspaces}
        snap["panes"] = [p for p in snap.get("panes", []) if p["tab_id"] not in gone and p["workspace_id"] not in workspaces]
        snap["agents"] = [a for a in snap["agents"] if a["tab_id"] not in gone and a["workspace_id"] not in workspaces]
        left = {t["workspace_id"] for t in snap["tabs"]}
        snap["workspaces"] = [w for w in snap["workspaces"] if w["workspace_id"] in left and w["workspace_id"] not in workspaces]

    def _close(self, args) -> None:
        if args[:2] == ("tab", "close"):
            self._drop({args[2]}, set())
        elif args[:2] == ("workspace", "close"):
            snap = self.current
            self._drop({t["tab_id"] for t in snap["tabs"] if t["workspace_id"] == args[2]}, {args[2]})
        elif args[:2] == ("pane", "close"):
            snap = self.current
            pane = next((p for p in snap.get("panes", []) if p["pane_id"] == args[2]), None)
            snap["panes"] = [p for p in snap.get("panes", []) if p["pane_id"] != args[2]]
            snap["agents"] = [a for a in snap["agents"] if a["pane_id"] != args[2]]
            if pane and not any(p["tab_id"] == pane["tab_id"] for p in snap["panes"]):
                self._drop({pane["tab_id"]}, set())

    async def run(self, *args):
        self.calls.append(args)
        key = " ".join(args[:2])
        if self.apply_closes and key not in self.responses:
            self._close(args)
        if key in self.handlers:
            return self.handlers[key](args)
        if key in self.responses:
            reply = self.responses[key]
            if isinstance(reply, Exception):
                raise reply
            return reply
        return "{}"

    async def focus_workspace(self, ws):
        self.focused.append(("ws", ws))

    async def focus_tab(self, tab):
        self.focused.append(("tab", tab))


@pytest.fixture
def projects(tmp_path):
    write_transcript(tmp_path / "projects")
    return tmp_path / "projects"


@pytest.fixture
def cfg(tmp_path, projects):
    return Config(pin=hash_pin(PIN), claude_projects_dir=str(projects), claude_cwd=str(tmp_path))


@pytest.fixture
def herdr():
    return FakeHerdr()


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


@pytest.fixture
def handoffs(tmp_path):
    path = tmp_path / "handoffs"
    path.mkdir()
    return path


@pytest.fixture
def app(cfg, tmp_path, handoffs, enchufe):
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    hub.self_pane_id = "w2:p9"
    return create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests,
                      dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads",
                      enchufe=enchufe)


@pytest.fixture
def client(app):
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        yield c


@pytest.fixture
def authed(client):
    assert client.post("/api/login", json={"pin": PIN}).status_code == 200
    return client


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path_factory.mktemp("xdg")))
    monkeypatch.setenv("ORQ_NO_AUTOINDEX", "1")
    monkeypatch.setenv("ORQ_DATA_DIR", str(tmp_path_factory.mktemp("datos-vacios")))
    for name in (
        "COLMENA_SESION",
        "COLMENA_GANCHO_ORIGEN",
        "COLMENA_GANCHO_ESPERA",
        "HERDR_PANE_ID",
        "HERDR_TAB_ID",
        "HERDR_WORKSPACE_ID",
        "COLMENA_CTX_WARN_PCT",
        "COLMENA_VPN_STATUSLINE_ENABLED",
        "COLMENA_VPN_INTERFACE",
        "COLMENA_VPN_SYSFS_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


def _tokens(args) -> list:
    if isinstance(args, (str, bytes, os.PathLike)):
        args = [args]
    out: list = []
    for arg in args or []:
        try:
            text = os.fsdecode(arg)
        except TypeError:
            continue
        try:
            out += shlex.split(text)
        except ValueError:
            out += text.split()
    return out


def _lanza_prohibido(args) -> bool:
    """Tokens cuyo basename es herdr/glab (prefijo) o claude (exacto)."""
    for t in _tokens(args):
        base = os.path.basename(t.rstrip(";&|"))
        if base.startswith(("herdr", "glab")) or base == "claude":
            return True
    return False


@pytest.fixture(autouse=True)
def anti_herdr(tmp_path_factory, monkeypatch):
    """Ningún test lanza herdr, glab ni claude reales: lo intentan y el test (y su teardown) falla."""
    attempts: list = []
    monkeypatch.setenv("HERDR_SOCKET_PATH", str(tmp_path_factory.mktemp("sin-herdr") / "herdr.sock"))
    real_which = shutil.which
    monkeypatch.setattr(herdr_module.shutil, "which",
                        lambda name, *a, **k: "/nonexistent/herdr" if name == "herdr" else real_which(name, *a, **k))
    real_exec = asyncio.create_subprocess_exec

    async def guarded_exec(*args, **kwargs):
        if _lanza_prohibido(args):
            attempts.append(args)
            raise AssertionError(f"un test intentó lanzar herdr o claude: {args[:3]}")
        return await real_exec(*args, **kwargs)

    class GuardedPopen(subprocess.Popen):
        def __init__(self, args, *a, **kw):
            if _lanza_prohibido(args):
                attempts.append(args)
                raise AssertionError("un test intentó lanzar herdr o claude con subprocess")
            super().__init__(args, *a, **kw)

    async def guarded_shell(cmd, *args, **kwargs):
        if _lanza_prohibido(cmd):
            attempts.append(cmd)
            raise AssertionError("un test intentó lanzar herdr o claude con una shell")
        return await real_shell(cmd, *args, **kwargs)

    def guarded_system(cmd):
        if _lanza_prohibido(cmd):
            attempts.append(cmd)
            raise AssertionError("un test intentó lanzar herdr o claude con os.system")
        return real_system(cmd)

    def guarded_spawn(real):
        def spawn(path, argv, *a, **kw):
            if _lanza_prohibido([path, *argv]):
                attempts.append(argv)
                raise AssertionError("un test intentó lanzar herdr o claude con posix_spawn")
            return real(path, argv, *a, **kw)
        return spawn

    real_shell = asyncio.create_subprocess_shell
    real_system = os.system
    monkeypatch.setattr(asyncio, "create_subprocess_exec", guarded_exec)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", guarded_shell)
    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)
    monkeypatch.setattr(os, "system", guarded_system)
    for name in ("posix_spawn", "posix_spawnp"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, guarded_spawn(getattr(os, name)))
    yield attempts
    assert not attempts, f"algún código lanzó herdr o claude durante el test: {attempts}"


UNITS_FALSAS = ("kit-update-all.path", "kit-update-all.service")


def configurar_kit_trabajo(directorio, **valores) -> None:
    """Escribe la tabla [kit_trabajo] en el config.toml de `directorio` (la carpeta de datos del test)."""
    from orquestador.config import Config, save_config
    save_config(Config(kit_trabajo=valores), directorio)


@pytest.fixture
def units_en_config(tmp_path, monkeypatch):
    datos = tmp_path / "datos-kit"
    datos.mkdir()
    monkeypatch.setenv("ORQ_DATA_DIR", str(datos))
    configurar_kit_trabajo(datos, units=list(UNITS_FALSAS))
    return UNITS_FALSAS
