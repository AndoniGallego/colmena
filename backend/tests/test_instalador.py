"""Instalador de Colmena: interacción inyectable, sin red ni systemctl real."""
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from conftest import UNITS_FALSAS

from orquestador.config import Config, hash_pin, load_config, save_config, verify_pin
from orquestador.instalador import InstaladorCtx, ejecutar_instalador


@pytest.fixture(autouse=True)
def _fuera_del_guardian(monkeypatch: pytest.MonkeyPatch) -> None:
    # Si los tests corren desde una terminal del guardián, esa marca cambia lo que pregunta el instalador.
    monkeypatch.delenv("COLMENA_TERMINAL", raising=False)

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "deploy"


class FakeCtx(InstaladorCtx):
    def __init__(
        self,
        *,
        home: Path,
        repo_root: Path,
        data_dir: Path,
        respuestas: list[str] | None = None,
        secretos: list[str] | None = None,
        confirmaciones: list[bool] | None = None,
        which_map: dict[str, str | None] | None = None,
        correr_map: dict[tuple, tuple[int, str, str]] | None = None,
    ):
        self.home = home
        xdg = os.environ.get("XDG_CONFIG_HOME")
        self.config_home = Path(xdg).expanduser() if xdg else home / ".config"
        self.repo_root = repo_root
        self.data_dir = data_dir
        self._respuestas = list(respuestas or [])
        self._secretos = list(secretos or [])
        self._confirmaciones = list(confirmaciones or [])
        self.which_map = dict(which_map or {})
        self.comandos: list[tuple[list[str], Path | None]] = []
        self.escrituras: list[Path] = []
        self.impresiones: list[str] = []
        self._correr_map = correr_map or {}
        self._ultima_salida = ""

    def preguntar(self, texto: str, default: str = "") -> str:
        if self._respuestas:
            val = self._respuestas.pop(0)
            return val if val else default
        return default

    def preguntar_secreto(self, texto: str) -> str:
        if not self._secretos:
            raise AssertionError(f"sin secreto para: {texto}")
        return self._secretos.pop(0)

    def confirmar(self, texto: str, default: bool = False) -> bool:
        if self._confirmaciones:
            return self._confirmaciones.pop(0)
        return default

    def correr(self, cmd: list[str], cwd: Path | None = None, timeout: float | None = None) -> int:
        self.comandos.append((list(cmd), cwd))
        key = (tuple(cmd), str(cwd) if cwd else None)
        if key in self._correr_map:
            code, out, _err = self._correr_map[key]
            self._ultima_salida = out
            return code
        self._ultima_salida = ""
        return 0

    def salida_correr(self) -> str:
        return getattr(self, "_ultima_salida", "")

    def which(self, nombre: str) -> str | None:
        return self.which_map.get(nombre)

    def imprimir(self, linea: str) -> None:
        self.impresiones.append(linea)

    def escribir_texto(self, path: Path, texto: str, modo: int) -> None:
        self.escrituras.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(texto, encoding="utf-8")
        os.chmod(path, modo)
        os.chmod(path.parent, 0o700)

    def escribir_bytes(self, path: Path, data: bytes, modo: int) -> None:
        self.escrituras.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.chmod(path, modo)


class EnsayoCtx(FakeCtx):
    def correr(self, cmd: list[str], cwd: Path | None = None, timeout: float | None = None) -> int:
        self.comandos.append((list(cmd), cwd))
        self.impresiones.append(f"haría: {' '.join(cmd)}")
        return 0

    def escribir_texto(self, path: Path, texto: str, modo: int) -> None:
        self.impresiones.append(f"haría: escribir {path}")

    def escribir_bytes(self, path: Path, data: bytes, modo: int) -> None:
        self.impresiones.append(f"haría: escribir {path}")


@pytest.fixture
def repo_falso(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(DEPLOY, root / "deploy")
    (root / "frontend").mkdir()
    return root


@pytest.fixture
def units_falsas(repo_falso, monkeypatch):
    from orquestador import kit_instalador
    monkeypatch.setattr(kit_instalador, "units_kit", lambda: UNITS_FALSAS)
    for u in UNITS_FALSAS:
        (repo_falso / "deploy" / u).write_text(f"[Unit]\nDescription={u}\n", encoding="utf-8")


def _uv_fake(repo_root: Path) -> str:
    uv = repo_root / "bin" / "uv"
    uv.parent.mkdir(parents=True, exist_ok=True)
    uv.write_text("#!/bin/sh\necho uv\n", encoding="utf-8")
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)
    return str(uv)


def _respuestas_solo_local(nombre="Ana", cwds="~/Proyectos/*"):
    return [nombre, cwds, ""]


def test_solo_local_config_y_env(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    data = home / "data"
    uv = _uv_fake(repo_falso)
    ctx = FakeCtx(
        home=home,
        repo_root=repo_falso,
        data_dir=data,
        respuestas=_respuestas_solo_local(),
        secretos=["pinlargo1", "pinlargo1"],
        confirmaciones=[False, False, False],
        which_map={"uv": uv, "node": "/usr/bin/node", "npm": "/usr/bin/npm"},
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 0

    cfg = load_config(data)
    assert cfg.nombre == "Ana"
    assert cfg.entrada.get("modos") == ["solo-local"]
    assert cfg.pin.startswith("pbkdf2$")
    assert verify_pin("pinlargo1", cfg.pin)
    assert "Proyectos" in cfg.plan_cwds[0]

    env_path = home / ".config" / "orquestador" / "orquestador.env"
    assert env_path.exists()
    text = env_path.read_text(encoding="utf-8")
    assert "ORQ_APP_ORIGIN=" in text
    assert "ORQ_VIEWER_ORIGIN=" in text
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600

    npm_cmds = [c for c, _ in ctx.comandos if c and c[0] == "npm"]
    assert len(npm_cmds) >= 2


def test_tailscale_dns_y_sin_tailscale_serve(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    data = home / "data"
    uv = _uv_fake(repo_falso)
    dns_json = json.dumps({"Self": {"DNSName": "micompu.red.ts.net."}})
    ctx = FakeCtx(
        home=home,
        repo_root=repo_falso,
        data_dir=data,
        respuestas=[
            "Bob",
            "",
            "",  # dns default
            "",  # tailscale_user vacío
            "",  # vapid
        ],
        secretos=["otropin12", "otropin12"],
        confirmaciones=[True, False, False],
        which_map={
            "uv": uv,
            "node": "/usr/bin/node",
            "npm": "/usr/bin/npm",
            "tailscale": "/usr/bin/tailscale",
        },
            correr_map={
                (("/usr/bin/tailscale", "status", "--json"), None): (0, dns_json, ""),
            },
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 0
    cfg = load_config(data)
    assert cfg.entrada.get("modos") == ["tailscale"]
    assert cfg.app_origin == "https://micompu.red.ts.net:8444"
    assert cfg.viewer_origin == "https://micompu.red.ts.net:8445"
    tailscale_cmds = [c for c, _ in ctx.comandos if c and ("tailscale" in c[0] or c[0] == "tailscale")]
    assert not any("serve" in " ".join(c) or "funnel" in " ".join(c) for c in tailscale_cmds)


def test_units_sin_servicios(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    data = home / "data"
    uv = _uv_fake(repo_falso)
    ctx = FakeCtx(
        home=home,
        repo_root=repo_falso,
        data_dir=data,
        respuestas=_respuestas_solo_local(),
        secretos=["pinlargo1", "pinlargo1"],
        confirmaciones=[False, False],
        which_map={
            "uv": uv,
            "node": "/usr/bin/node",
            "npm": "/usr/bin/npm",
            "claude": "/opt/node/bin/claude",
        },
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    ejecutar_instalador(ctx, ensayo=False, sin_servicios=True)
    units_dir = data / "units"
    orq = (units_dir / "orquestador.service").read_text(encoding="utf-8")
    assert f"WorkingDirectory={repo_falso}" in orq
    assert f"ExecStart={uv} run orquestador" in orq
    assert "%h/Proyectos/orquestador" not in orq
    assert "/home/" + "cc" not in orq
    assert "/opt/node/bin" in orq
    assert not (units_dir / "herdr-server.service").exists()
    systemctl = [c for c, _ in ctx.comandos if c and c[0] == "systemctl"]
    assert systemctl == []


def test_units_con_herdr_y_systemctl(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    data = home / "data"
    uv = _uv_fake(repo_falso)
    herdr = str(repo_falso / "herdr")
    Path(herdr).write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(herdr, 0o755)
    ctx = FakeCtx(
        home=home,
        repo_root=repo_falso,
        data_dir=data,
        respuestas=_respuestas_solo_local(),
        secretos=["pinlargo1", "pinlargo1"],
        confirmaciones=[False, False],
        which_map={"uv": uv, "node": "/usr/bin/node", "npm": "/usr/bin/npm", "herdr": herdr},
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    ejecutar_instalador(ctx, ensayo=False, sin_servicios=False)
    unit = home / ".config" / "systemd" / "user" / "orquestador.service"
    assert unit.exists()
    assert (home / ".config" / "systemd" / "user" / "herdr-server.service").exists()
    cmds = [c for c, _ in ctx.comandos if c and c[0] == "systemctl"]
    flat = " ".join(" ".join(c) for c in cmds)
    assert "daemon-reload" in flat
    assert "enable --now" in flat


def test_idempotencia_pin_y_tabla_desconocida(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    data = home / "data"
    data.mkdir()
    pin_viejo = hash_pin("pinexistente")
    (data / "config.toml").write_text(
        '[custom]\nclave = "secreta"\npin = "ignored"\n',
        encoding="utf-8",
    )
    save_config(
        Config(
            pin=pin_viejo,
            nombre="Viejo",
            entrada={"modos": ["solo-local"], "solo-local": {"puerto_app": 8774}},
            terminales={"nuevas_en": "herdr", "vivo": False},
            mrs={"usuario": "x"},
        ),
        data,
    )
    antes = (data / "config.toml").read_text(encoding="utf-8")
    uv = _uv_fake(repo_falso)
    ctx = FakeCtx(
        home=home,
        repo_root=repo_falso,
        data_dir=data,
        respuestas=["", "", ""],
        confirmaciones=[False, False, False, False],
        which_map={"uv": uv, "node": "/n", "npm": "/n"},
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    ejecutar_instalador(ctx, ensayo=False, sin_servicios=True)
    despues = load_config(data)
    assert despues.pin == pin_viejo
    assert despues.nombre == "Viejo"
    assert despues.mrs.get("usuario") == "x"
    assert despues.terminales.get("nuevas_en") == "herdr"
    raw = (data / "config.toml").read_text(encoding="utf-8")
    assert "custom" in raw or "secreta" in raw


def test_ensayo_no_escribe(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    data = home / "data"
    uv = _uv_fake(repo_falso)
    ctx = EnsayoCtx(
        home=home,
        repo_root=repo_falso,
        data_dir=data,
        respuestas=_respuestas_solo_local(),
        secretos=["pinlargo1", "pinlargo1"],
        which_map={"uv": uv, "node": "/n", "npm": "/n"},
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    ejecutar_instalador(ctx, ensayo=True, sin_servicios=True)
    assert not (data / "config.toml").exists()
    assert ctx.escrituras == []
    assert any("haría:" in i for i in ctx.impresiones)


def test_mrs_con_glab(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    data = home / "data"
    uv = _uv_fake(repo_falso)
    glab = str(repo_falso / "glab")
    Path(glab).write_text("#!/bin/sh\necho '{\"username\":\"devx\",\"id\":5}'\n", encoding="utf-8")
    os.chmod(glab, 0o755)

    ctx = FakeCtx(
        home=home,
        repo_root=repo_falso,
        data_dir=data,
        respuestas=["", "", "~/r/a", ""],
        secretos=["pinlargo1", "pinlargo1"],
        confirmaciones=[False, True, False, False],
        which_map={"uv": uv, "node": "/n", "npm": "/n", "glab": glab},
        correr_map={
            ((glab, "api", "user"), None): (0, '{"username":"devx","id":5}', ""),
        },
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    ejecutar_instalador(ctx, ensayo=False, sin_servicios=True)
    cfg = load_config(data)
    assert cfg.mrs.get("usuario") == "devx"
    assert cfg.mrs.get("usuario_id") == 5
    assert cfg.mrs.get("repos")


def test_mrs_sin_glab_sigue(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    data = home / "data"
    uv = _uv_fake(repo_falso)
    ctx = FakeCtx(
        home=home,
        repo_root=repo_falso,
        data_dir=data,
        respuestas=_respuestas_solo_local(),
        secretos=["pinlargo1", "pinlargo1"],
        which_map={"uv": uv, "node": "/n", "npm": "/n"},
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    ejecutar_instalador(ctx, ensayo=False, sin_servicios=True)
    assert load_config(data).mrs == {}


def test_save_config_conserva_tablas(tmp_path):
    entrada = {"modos": ["tailscale"], "tailscale": {"cabecera_ip": "X-Forwarded-For"}}
    save_config(
        Config(
            pin="x",
            terminales={"vivo": True, "nuevas_en": "guardian"},
            mrs={"usuario": "a"},
            engram={"contenedor": "c", "proyecto": "p"},
            entrada=entrada,
        ),
        tmp_path,
    )
    cfg = load_config(tmp_path)
    assert cfg.terminales == {"vivo": True, "nuevas_en": "guardian"}
    assert cfg.mrs["usuario"] == "a"
    assert cfg.engram == {"contenedor": "c", "proyecto": "p"}
    assert cfg.entrada == entrada
    (tmp_path / "config.toml").write_text(
        (tmp_path / "config.toml").read_text() + '\n[extra]\nfoo = "bar"\n',
        encoding="utf-8",
    )
    save_config(Config(host="127.0.0.1"), tmp_path)
    raw = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "extra" in raw or "foo" in raw


def test_instalar_sh_existe_y_bash_n():
    script = REPO / "instalar.sh"
    assert script.is_file()
    assert os.access(script, os.X_OK)
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_instalar_sh_falta_uv(tmp_path):
    script = REPO / "instalar.sh"
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    r = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
    )
    assert r.returncode == 1
    assert "uv" in (r.stdout + r.stderr).lower()


def _ctx_basico(home, repo, data, **kw):
    uv = _uv_fake(repo)
    kw.setdefault("which_map", {"uv": uv, "node": "/n", "npm": "/n"})
    kw.setdefault("confirmaciones", [False, False])
    return FakeCtx(home=home, repo_root=repo, data_dir=data, **kw)


def test_reinstalar_conserva_tailscale_y_entrada(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    data = home / "data"
    data.mkdir(parents=True)
    save_config(
        Config(
            pin=hash_pin("pinexistente"),
            nombre="Ana",
            app_origin="https://compu.red.ts.net:8444",
            viewer_origin="https://compu.red.ts.net:8445",
            entrada={"modos": ["tailscale"], "tailscale": {"cabecera_ip": "X-Forwarded-For", "extra": 1}},
        ),
        data,
    )
    ctx = _ctx_basico(
        home,
        repo_falso,
        data,
        respuestas=["", "", "", "", ""],
        confirmaciones=[False, True, False],
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 0
    cfg = load_config(data)
    assert cfg.entrada["modos"] == ["tailscale"]
    assert cfg.entrada["tailscale"]["extra"] == 1
    assert cfg.app_origin == "https://compu.red.ts.net:8444"


def test_env_toma_valores_nuevos(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    data = home / "data"
    env = home / ".config" / "orquestador" / "orquestador.env"
    env.parent.mkdir(parents=True)
    env.write_text("ORQ_APP_ORIGIN=https://vieja:8444\nORQ_VIEWER_ORIGIN=https://vieja:8445\n", encoding="utf-8")
    ctx = _ctx_basico(home, repo_falso, data, respuestas=_respuestas_solo_local(),
                      secretos=["pinlargo1", "pinlargo1"])
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 0
    text = env.read_text(encoding="utf-8")
    assert "vieja" not in text


def test_servicios_se_reinician_y_falla_se_informa(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    data = home / "data"
    ctx = _ctx_basico(home, repo_falso, data, respuestas=_respuestas_solo_local(),
                      secretos=["pinlargo1", "pinlargo1"])
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=False) == 0
    flat = [" ".join(c) for c, _ in ctx.comandos if c and c[0] == "systemctl"]
    assert any("restart" in c and "orquestador.service" in c for c in flat)

    home2 = tmp_path / "home2"
    data2 = home2 / "data"
    ctx2 = _ctx_basico(home2, repo_falso, data2, respuestas=_respuestas_solo_local(),
                       secretos=["pinlargo1", "pinlargo1"],
                       correr_map={(("systemctl", "--user", "daemon-reload"), None): (1, "", "boom")})
    monkeypatch.setenv("ORQ_DATA_DIR", str(data2))
    assert ejecutar_instalador(ctx2, ensayo=False, sin_servicios=False) == 1
    assert any("systemctl" in l for l in ctx2.impresiones)


def test_env_conserva_otras_claves(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    data = home / "data"
    env = home / ".config" / "orquestador" / "orquestador.env"
    env.parent.mkdir(parents=True)
    env.write_text("ORQ_APP_ORIGIN=https://vieja:8444\nMI_CLAVE=secreta\n", encoding="utf-8")
    ctx = _ctx_basico(home, repo_falso, data, respuestas=_respuestas_solo_local(), secretos=["pinlargo1", "pinlargo1"])
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 0
    text = env.read_text(encoding="utf-8")
    assert "MI_CLAVE=secreta" in text


def test_env_tailscale_no_pisa_origen_vacio(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    data = home / "data"
    env = home / ".config" / "orquestador" / "orquestador.env"
    env.parent.mkdir(parents=True)
    env.write_text("ORQ_APP_ORIGIN=https://compu.red.ts.net:8444\n", encoding="utf-8")
    uv = _uv_fake(repo_falso)
    ctx = FakeCtx(
        home=home,
        repo_root=repo_falso,
        data_dir=data,
        respuestas=["", "", "", "", ""],
        secretos=["pinlargo1", "pinlargo1"],
        confirmaciones=[True, False, False],
        which_map={"uv": uv, "node": "/n", "npm": "/n", "tailscale": "/n/ts"},
        correr_map={
            (("/n/ts", "status", "--json"), None): (0, "{}", ""),
        },
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 0
    assert "https://compu.red.ts.net:8444" in env.read_text(encoding="utf-8")


def test_tailscale_sin_origen_aborta(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    data = home / "data"
    uv = _uv_fake(repo_falso)
    ctx = FakeCtx(
        home=home,
        repo_root=repo_falso,
        data_dir=data,
        respuestas=["", "", "", "", ""],
        secretos=["pinlargo1", "pinlargo1"],
        confirmaciones=[True, False, False],
        which_map={"uv": uv, "node": "/n", "npm": "/n", "tailscale": "/n/ts"},
        correr_map={
            (("/n/ts", "status", "--json"), None): (0, "{}", ""),
        },
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 1
    assert any("ORQ_APP_ORIGIN" in l for l in ctx.impresiones)


def test_mrs_glab_json_invalido(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    data = home / "data"
    glab = str(repo_falso / "glab")
    Path(glab).write_text("#!/bin/sh\necho '[]'\n", encoding="utf-8")
    os.chmod(glab, 0o755)
    ctx = _ctx_basico(
        home,
        repo_falso,
        data,
        respuestas=_respuestas_solo_local() + [""],
        secretos=["pinlargo1", "pinlargo1"],
        which_map={"uv": _uv_fake(repo_falso), "node": "/n", "npm": "/n", "glab": glab},
        correr_map={((glab, "api", "user"), None): (0, "[]", "")},
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    ejecutar_instalador(ctx, ensayo=False, sin_servicios=True)
    assert load_config(data).mrs == {}


def test_unit_environmentfile_xdg(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    data = home / "data"
    cfg_dir = home / "cfg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg_dir))
    ctx = _ctx_basico(home, repo_falso, data, respuestas=_respuestas_solo_local(), secretos=["pinlargo1", "pinlargo1"])
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    ejecutar_instalador(ctx, ensayo=False, sin_servicios=True)
    unit = (data / "units" / "orquestador.service").read_text(encoding="utf-8")
    assert f"EnvironmentFile={cfg_dir / 'orquestador' / 'orquestador.env'}" in unit


def test_units_no_pisa_si_rechaza(tmp_path, repo_falso, monkeypatch):
    home = tmp_path / "home"
    data = home / "data"
    systemd = home / ".config" / "systemd" / "user"
    systemd.mkdir(parents=True)
    vieja = systemd / "orquestador.service"
    vieja.write_text("[Service]\nWorkingDirectory=/otro\n", encoding="utf-8")
    ctx = _ctx_basico(
        home,
        repo_falso,
        data,
        respuestas=_respuestas_solo_local(),
        secretos=["pinlargo1", "pinlargo1"],
        confirmaciones=[False, False],
    )
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    ejecutar_instalador(ctx, ensayo=False, sin_servicios=False)
    assert vieja.read_text(encoding="utf-8") == "[Service]\nWorkingDirectory=/otro\n"
    assert not any(c and c[0] == "systemctl" for c, _ in ctx.comandos)


def test_correr_oserror(repo_falso):
    from orquestador.instalador import RealInstaladorCtx

    logs: list[str] = []
    r = RealInstaladorCtx(repo_root=repo_falso)
    r.imprimir = logs.append
    assert r.correr(["/no/existe/comando-colmena-xyz"]) == 1
    assert logs


def _kit_minimo(repo: Path) -> None:
    for rel in ("kit/reglas/colmena/estado-sesion.md", "kit/ganchos/andokit-stop-bloques.sh"):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")


def _sin_andokit(monkeypatch):
    for k in list(os.environ):
        if k.startswith("ANDOKIT_"):
            monkeypatch.delenv(k)
    monkeypatch.setenv("ANDOKIT_NO_RELOAD", "1")


def _ctx_kit(cls, tmp_path, repo, monkeypatch, confirmaciones=(False, False, True)):
    home = tmp_path / "home"
    home.mkdir()
    data = home / "data"
    monkeypatch.setenv("ORQ_DATA_DIR", str(data))
    uv = _uv_fake(repo)
    return home, cls(
        home=home,
        repo_root=repo,
        data_dir=data,
        respuestas=_respuestas_solo_local(),
        secretos=["pinlargo1", "pinlargo1"],
        confirmaciones=list(confirmaciones),
        which_map={"uv": uv, "node": "/usr/bin/node", "npm": "/usr/bin/npm"},
    )


def test_paso_kit_instala_links(tmp_path, repo_falso, monkeypatch):
    _kit_minimo(repo_falso)
    _sin_andokit(monkeypatch)
    home, ctx = _ctx_kit(FakeCtx, tmp_path, repo_falso, monkeypatch)
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 0
    regla = home / ".claude" / "rules" / "estado-sesion.md"
    assert os.readlink(regla) == str(repo_falso / "kit" / "reglas" / "colmena" / "estado-sesion.md")


def test_paso_kit_ensayo_no_escribe(tmp_path, repo_falso, monkeypatch):
    _kit_minimo(repo_falso)
    _sin_andokit(monkeypatch)
    home, ctx = _ctx_kit(EnsayoCtx, tmp_path, repo_falso, monkeypatch)
    assert ejecutar_instalador(ctx, ensayo=True, sin_servicios=True) == 0
    assert not (home / ".claude").exists()


def test_paso_kit_sin_carpeta_sigue(tmp_path, repo_falso, monkeypatch):
    _sin_andokit(monkeypatch)
    _, ctx = _ctx_kit(FakeCtx, tmp_path, repo_falso, monkeypatch, confirmaciones=(False, False))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 0
    assert "Sin kit/ en el repo; salteo el kit." in ctx.impresiones


def test_paso_kit_sin_servicios_no_toca_units(tmp_path, repo_falso, monkeypatch, units_falsas):
    _kit_minimo(repo_falso)
    _sin_andokit(monkeypatch)
    monkeypatch.delenv("ANDOKIT_NO_RELOAD")
    home, ctx = _ctx_kit(FakeCtx, tmp_path, repo_falso, monkeypatch)
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 0
    assert not (ctx.config_home / "systemd" / "user" / "kit-update-all.path").exists()
    assert not [c for c, _ in ctx.comandos if c[:1] == ["systemctl"]]


def test_paso_kit_units_respetan_config_home(tmp_path, repo_falso, monkeypatch, units_falsas):
    _kit_minimo(repo_falso)
    _sin_andokit(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    home, ctx = _ctx_kit(FakeCtx, tmp_path, repo_falso, monkeypatch, confirmaciones=(False, False, True, False))
    ejecutar_instalador(ctx, ensayo=False, sin_servicios=False)
    assert (tmp_path / "xdg" / "systemd" / "user" / "kit-update-all.path").exists()
    assert not (home / ".config" / "systemd" / "user" / "kit-update-all.path").exists()


def test_paso_kit_regla_duplicada_corta_con_mensaje(tmp_path, repo_falso, monkeypatch):
    _kit_minimo(repo_falso)
    (repo_falso / "kit" / "reglas" / "trabajo").mkdir(parents=True)
    (repo_falso / "kit" / "reglas" / "trabajo" / "estado-sesion.md").write_text("x\n", encoding="utf-8")
    _sin_andokit(monkeypatch)
    _, ctx = _ctx_kit(FakeCtx, tmp_path, repo_falso, monkeypatch)
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 1
    assert any(ln.startswith("ERROR") for ln in ctx.impresiones)


def test_paso_kit_sin_respuesta_no_instala(tmp_path, repo_falso, monkeypatch):
    _kit_minimo(repo_falso)
    _sin_andokit(monkeypatch)
    home, ctx = _ctx_kit(FakeCtx, tmp_path, repo_falso, monkeypatch, confirmaciones=(False, False))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True) == 0
    assert not (home / ".claude" / "rules").exists()


def test_paso_kit_pregunta_nombra_al_andokit(tmp_path, repo_falso, monkeypatch):
    _kit_minimo(repo_falso)
    _sin_andokit(monkeypatch)
    _, ctx = _ctx_kit(FakeCtx, tmp_path, repo_falso, monkeypatch)
    vistas: list[str] = []
    original = ctx.confirmar

    def confirmar(texto, default=False):
        vistas.append(texto)
        return original(texto, default)

    ctx.confirmar = confirmar
    ejecutar_instalador(ctx, ensayo=False, sin_servicios=True)
    assert any("andokit" in t and "Ando" in t for t in vistas)


def test_paso_kit_con_kit_no_pregunta(tmp_path, repo_falso, monkeypatch):
    _kit_minimo(repo_falso)
    _sin_andokit(monkeypatch)
    home, ctx = _ctx_kit(FakeCtx, tmp_path, repo_falso, monkeypatch, confirmaciones=(False, False))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True, kit=True) == 0
    assert (home / ".claude" / "rules" / "estado-sesion.md").is_symlink()


def test_paso_kit_sin_kit_no_pregunta_ni_instala(tmp_path, repo_falso, monkeypatch):
    _kit_minimo(repo_falso)
    _sin_andokit(monkeypatch)
    home, ctx = _ctx_kit(FakeCtx, tmp_path, repo_falso, monkeypatch, confirmaciones=(False, False))
    assert ejecutar_instalador(ctx, ensayo=False, sin_servicios=True, kit=False) == 0
    assert not (home / ".claude" / "rules").exists()
    assert "Salteo el andokit." in ctx.impresiones


def test_cli_instalar_flags_kit(monkeypatch):
    import sys as _sys

    from orquestador import cli, instalador

    vistos: list[dict] = []
    monkeypatch.setattr(instalador, "instalar", lambda **kw: vistos.append(kw) or 0)
    for flags, esperado in ((["--con-kit"], True), (["--sin-kit"], False), ([], None)):
        monkeypatch.setattr(_sys, "argv", ["orquestador", "instalar", *flags])
        with pytest.raises(SystemExit):
            cli.main()
        assert vistos[-1]["kit"] is esperado
