"""Instalación guiada de Colmena en esta máquina."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from .config import (
    MIN_PIN_LENGTH,
    REPO_ROOT,
    Config,
    data_dir,
    hash_pin,
    load_config,
    normalize_origin,
    save_config,
)


class InstaladorCtx(ABC):
    home: Path
    config_home: Path
    repo_root: Path
    data_dir: Path

    @abstractmethod
    def preguntar(self, texto: str, default: str = "") -> str: ...

    @abstractmethod
    def preguntar_secreto(self, texto: str) -> str: ...

    @abstractmethod
    def confirmar(self, texto: str, default: bool = False) -> bool: ...

    @abstractmethod
    def correr(self, cmd: list[str], cwd: Path | None = None, timeout: float | None = None) -> int: ...

    def salida_correr(self) -> str:
        return ""

    @abstractmethod
    def which(self, nombre: str) -> str | None: ...

    @abstractmethod
    def imprimir(self, linea: str) -> None: ...

    @abstractmethod
    def escribir_texto(self, path: Path, texto: str, modo: int) -> None: ...

    def escribir_bytes(self, path: Path, data: bytes, modo: int) -> None:
        self.escribir_texto(path, data.decode("utf-8"), modo)


class RealInstaladorCtx(InstaladorCtx):
    def __init__(self, repo_root: Path | None = None):
        self.home = Path.home()
        xdg = os.environ.get("XDG_CONFIG_HOME")
        self.config_home = Path(xdg).expanduser() if xdg else self.home / ".config"
        self.repo_root = repo_root or REPO_ROOT
        self.data_dir = data_dir()
        self._ultima_salida = ""

    def preguntar(self, texto: str, default: str = "") -> str:
        suf = f" [{default}]" if default else ""
        val = input(f"{texto}{suf}: ").strip()
        return val if val else default

    def preguntar_secreto(self, texto: str) -> str:
        import getpass

        return getpass.getpass(f"{texto}: ")

    def confirmar(self, texto: str, default: bool = False) -> bool:
        opc = "S/n" if default else "s/N"
        val = input(f"{texto} ({opc}): ").strip().lower()
        if not val:
            return default
        return val in ("s", "si", "sí", "y", "yes")

    def correr(self, cmd: list[str], cwd: Path | None = None, timeout: float | None = None) -> int:
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            self._ultima_salida = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            self.imprimir(f"El comando tardó demasiado ({timeout}s): {' '.join(cmd)}")
            if exc.stderr:
                err = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode(errors="replace")
                if err.strip():
                    self.imprimir(err.strip())
            return 124
        except OSError as exc:
            self._ultima_salida = ""
            self.imprimir(f"No pude ejecutar {' '.join(cmd)}: {exc}")
            return 1
        self._ultima_salida = proc.stdout or ""
        if proc.returncode != 0 and proc.stderr:
            self.imprimir(proc.stderr.strip())
        return proc.returncode

    def salida_correr(self) -> str:
        return self._ultima_salida

    def which(self, nombre: str) -> str | None:
        return shutil.which(nombre)

    def imprimir(self, linea: str) -> None:
        print(linea)

    def escribir_texto(self, path: Path, texto: str, modo: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(texto, encoding="utf-8")
        os.chmod(path, modo)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass


class EnsayoRealCtx(RealInstaladorCtx):
    def correr(self, cmd: list[str], cwd: Path | None = None, timeout: float | None = None) -> int:
        self.imprimir(f"haría: {' '.join(cmd)}" + (f" (cwd={cwd})" if cwd else ""))
        return 0

    def escribir_texto(self, path: Path, texto: str, modo: int) -> None:
        self.imprimir(f"haría: escribir {path} ({modo:o})")


def validar_pin(pin: str, repetir: str) -> str | None:
    if pin != repetir:
        return "Los PIN no coinciden."
    if len(pin) < MIN_PIN_LENGTH:
        return f"El PIN debe tener al menos {MIN_PIN_LENGTH} caracteres."
    return None


def aplicar_pin(cfg: Config, pin: str, repetir: str) -> str | None:
    err = validar_pin(pin, repetir)
    if err:
        return err
    cfg.pin = hash_pin(pin)
    return None


def _default_plan_cwds(home: Path) -> str:
    proyectos = home / "Proyectos"
    return "~/Proyectos/*" if proyectos.is_dir() else ""


def _parse_cwds(texto: str) -> list[str]:
    partes = [p.strip() for p in texto.split(",") if p.strip()]
    return [str(Path(p).expanduser()) for p in partes]


def _dns_tailscale(ctx: InstaladorCtx) -> str:
    ts = ctx.which("tailscale")
    if not ts:
        return ""
    if ctx.correr([ts, "status", "--json"]) != 0:
        return ""
    try:
        data = json.loads(ctx.salida_correr())
        dns = (data.get("Self") or {}).get("DNSName") or ""
        return dns.rstrip(".")
    except (json.JSONDecodeError, TypeError):
        return ""


def _host_de_origen(origen: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(origen).hostname or "" if origen else ""


def _path_entorno(ctx: InstaladorCtx) -> Path:
    return ctx.config_home / "orquestador" / "orquestador.env"


def _leer_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


_ORQ_ENV = frozenset({"ORQ_APP_ORIGIN", "ORQ_VIEWER_ORIGIN", "ORQ_VAPID_SUB"})


def _escribir_env(
    ctx: InstaladorCtx,
    valores: dict[str, str],
    ensayo: bool,
    *,
    modo_tailscale: bool,
) -> None:
    path = _path_entorno(ctx)
    actual = _leer_env(path) if path.exists() else {}
    for k, v in valores.items():
        if k not in _ORQ_ENV:
            continue
        if modo_tailscale and not v and k in ("ORQ_APP_ORIGIN", "ORQ_VIEWER_ORIGIN"):
            continue
        if v or k != "ORQ_VAPID_SUB":
            actual[k] = v
    if "ORQ_VAPID_SUB" not in actual:
        actual["ORQ_VAPID_SUB"] = "mailto:colmena@localhost"

    if path.exists():
        nuevas: list[str] = []
        vistos: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, _ = stripped.partition("=")
                k = k.strip()
                if k in _ORQ_ENV and k in actual:
                    nuevas.append(f"{k}={actual[k]}")
                    vistos.add(k)
                    continue
            nuevas.append(line)
        for k in _ORQ_ENV:
            if k not in vistos and k in actual:
                nuevas.append(f"{k}={actual[k]}")
        texto = "\n".join(nuevas) + "\n"
    else:
        lineas = [
            "# Origen HTTPS de la app (tailscale serve, puerto 8444).",
            f"ORQ_APP_ORIGIN={actual.get('ORQ_APP_ORIGIN', '')}",
            "# Origen HTTPS del visor (puerto 8445).",
            f"ORQ_VIEWER_ORIGIN={actual.get('ORQ_VIEWER_ORIGIN', '')}",
            "# Contacto VAPID para notificaciones push.",
            f"ORQ_VAPID_SUB={actual.get('ORQ_VAPID_SUB', 'mailto:colmena@localhost')}",
            "",
        ]
        texto = "\n".join(lineas)
    if ensayo:
        ctx.imprimir(f"haría: escribir {path}")
        return
    ctx.escribir_texto(path, texto, 0o600)


def _armar_path(ctx: InstaladorCtx) -> str:
    dirs: list[str] = []
    for nombre in ("uv", "claude", "node", "npm", "glab", "herdr"):
        ruta = ctx.which(nombre)
        if ruta:
            parent = str(Path(ruta).parent)
            if parent not in dirs:
                dirs.append(parent)
    for fijo in ("/usr/local/bin", "/usr/bin", "/bin"):
        if fijo not in dirs:
            dirs.append(fijo)
    return ":".join(dirs)


def _generar_unit(plantilla: str, ctx: InstaladorCtx) -> str:
    uv = ctx.which("uv") or "uv"
    path = _armar_path(ctx)
    home = str(ctx.home)
    env_file = _path_entorno(ctx)
    texto = plantilla.replace("%h/Proyectos/orquestador", str(ctx.repo_root))
    texto = texto.replace("%h/.local/bin/uv", uv)
    texto = texto.replace("%h/.local/bin/herdr", ctx.which("herdr") or f"{home}/.local/bin/herdr")
    texto = texto.replace(
        "Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin",
        f"Environment=PATH={path}",
    )
    texto = texto.replace("EnvironmentFile=%h/.config/orquestador/orquestador.env", f"EnvironmentFile={env_file}")
    return texto


def _working_dir_unit(texto: str) -> str:
    m = re.search(r"^WorkingDirectory=(.+)$", texto, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _units_cambiarian(ctx: InstaladorCtx, destino_systemd: Path, nombres: list[str]) -> list[tuple[str, str, str]]:
    cambios: list[tuple[str, str, str]] = []
    for nombre in nombres:
        dest = destino_systemd / nombre
        if not dest.exists():
            continue
        plantilla = (ctx.repo_root / "deploy" / nombre).read_text(encoding="utf-8")
        nuevo = _generar_unit(plantilla, ctx)
        viejo = dest.read_text(encoding="utf-8")
        if viejo.strip() == nuevo.strip():
            continue
        wd_v = _working_dir_unit(viejo)
        wd_n = _working_dir_unit(nuevo)
        cambios.append((nombre, wd_v, wd_n))
    return cambios


def _instalar_units(ctx: InstaladorCtx, ensayo: bool, sin_servicios: bool) -> bool:
    deploy = ctx.repo_root / "deploy"
    nombres = ["colmena-guardian.service", "orquestador.service"]
    if ctx.which("herdr"):
        nombres.append("herdr-server.service")
    destino_systemd = ctx.config_home / "systemd" / "user"
    destino_data = ctx.data_dir / "units"
    if not sin_servicios:
        cambios = _units_cambiarian(ctx, destino_systemd, nombres)
        if cambios:
            for nombre, wd_v, wd_n in cambios:
                ctx.imprimir(f"{nombre}: WorkingDirectory {wd_v or '(vacío)'} → {wd_n or '(vacío)'}")
            if not ctx.confirmar("¿Reemplazo las units de systemd con estas versiones?", default=False):
                ctx.imprimir("Dejé las units y systemd como estaban; sigo con el resto.")
                return True
    for nombre in nombres:
        plantilla = (deploy / nombre).read_text(encoding="utf-8")
        unit = _generar_unit(plantilla, ctx)
        if sin_servicios:
            out = destino_data / nombre
            ctx.imprimir(f"Unit {nombre} → {out}")
            if ensayo:
                ctx.imprimir(f"haría: escribir {out}")
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                ctx.escribir_texto(out, unit, 0o644)
            continue
        dest = destino_systemd / nombre
        if ensayo:
            ctx.imprimir(f"haría: escribir {dest}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            ctx.escribir_texto(dest, unit, 0o644)
    if sin_servicios:
        ctx.imprimir(
            f"Para prender los servicios: copiá {destino_data}/*.service a "
            f"{destino_systemd}/ y corré:"
        )
        ctx.imprimir("  systemctl --user daemon-reload")
        ctx.imprimir("  systemctl --user enable --now colmena-guardian.service orquestador.service")
        return True
    unidades = ["colmena-guardian.service", "orquestador.service"]
    if os.environ.get("COLMENA_TERMINAL") == "1":
        if not ctx.confirmar(
            "Reiniciar los servicios va a cortar esta terminal del guardián. ¿Seguís?",
            default=False,
        ):
            ctx.imprimir("Salté systemctl; copiá las units a mano o corré el instalador fuera del guardián.")
            return True
    # restart aplica units regeneradas aunque ya estuvieran corriendo.
    pasos = [["systemctl", "--user", "daemon-reload"],
             ["systemctl", "--user", "enable", "--now", *unidades],
             ["systemctl", "--user", "restart", *unidades]]
    for cmd in pasos:
        if ensayo:
            ctx.imprimir(f"haría: {' '.join(cmd)}")
        elif ctx.correr(cmd) != 0:
            ctx.imprimir(f"Falló: {' '.join(cmd)}. Mirá `journalctl --user -u orquestador` y volvé a correr el instalador.")
            return False
    return True


def _frontend(ctx: InstaladorCtx, ensayo: bool) -> None:
    front = ctx.repo_root / "frontend"
    ctx.imprimir("Armando el frontend (npm install y build)...")
    for cmd in (["npm", "install"], ["npm", "run", "build"]):
        if ensayo:
            ctx.imprimir(f"haría: {' '.join(cmd)} en {front}")
            continue
        if ctx.correr(cmd, cwd=front) != 0:
            print(f"Falló: {' '.join(cmd)} en {front}", file=sys.stderr)
            raise SystemExit(f"No pude armar el frontend ({' '.join(cmd)}).")


def _configurar_mrs(ctx: InstaladorCtx, cfg: Config) -> None:
    glab = ctx.which("glab")
    if not glab:
        ctx.imprimir("MRs apagados: instalá glab y corré `glab auth login`, después volvé a correr el instalador")
        return
    if ctx.correr([glab, "api", "user"], timeout=5) != 0:
        ctx.imprimir("MRs apagados: instalá glab y corré `glab auth login`, después volvé a correr el instalador")
        return
    try:
        data = json.loads(ctx.salida_correr())
    except json.JSONDecodeError:
        ctx.imprimir("MRs apagados: no pude leer tu usuario de GitLab.")
        return
    if not isinstance(data, dict):
        ctx.imprimir("MRs apagados: la respuesta de GitLab no es válida.")
        return
    username = data.get("username")
    uid = data.get("id")
    if not isinstance(username, str) or not username.strip() or not isinstance(uid, int) or uid <= 0:
        ctx.imprimir("MRs apagados: faltan username o id de GitLab.")
        return
    if not ctx.confirmar("¿Querés prender los MRs de GitLab?", default=False):
        return
    cfg.mrs = dict(cfg.mrs)
    cfg.mrs["usuario"] = username.strip()
    cfg.mrs["usuario_id"] = uid
    repos = ctx.preguntar("¿Qué repos? (rutas separadas por coma)", ",".join(cfg.mrs.get("repos") or []))
    cfg.mrs["repos"] = _parse_cwds(repos) if repos else list(cfg.mrs.get("repos") or [])


def _instalar_kit(ctx: InstaladorCtx, ensayo: bool, sin_servicios: bool, quiere: bool | None = None) -> bool:
    from dataclasses import replace
    from datetime import datetime

    from .kit_instalador import KitInvalido, destinos, instalar_kit

    kit = ctx.repo_root / "kit"
    if not kit.is_dir():
        ctx.imprimir("Sin kit/ en el repo; salteo el kit.")
        return True
    if quiere is False:
        ctx.imprimir("Salteo el andokit.")
        return True
    if quiere is None and not ctx.confirmar(
        "¿Instalás el andokit? Son las reglas, skills y hooks personales de Ando para Claude."
        " Si no sos Ando, probablemente no.",
        default=False,
    ):
        return True
    d = destinos(os.environ, ctx.home, kit)
    if d.systemd == ctx.home / ".config" / "systemd" / "user":
        d = replace(d, systemd=ctx.config_home / "systemd" / "user")
    modo = "ensayo" if ensayo else "instalar"
    try:
        rc = instalar_kit(
            kit, ctx.repo_root / "deploy", d, modo, ctx.imprimir, ctx.correr, datetime.now, units=not sin_servicios
        )
    except KitInvalido as e:
        ctx.imprimir(f"ERROR: {e}")
        return False
    return rc == 0


def ejecutar_instalador(
    ctx: InstaladorCtx | None = None,
    *,
    ensayo: bool = False,
    sin_servicios: bool = False,
    kit: bool | None = None,
) -> int:
    if ctx is None:
        ctx = EnsayoRealCtx() if ensayo else RealInstaladorCtx()
    os.umask(0o077)
    try:
        _frontend(ctx, ensayo)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1

    directory = ctx.data_dir
    directory.mkdir(parents=True, exist_ok=True)
    config_path = directory / "config.toml"
    if config_path.exists() or not ensayo:
        cfg = load_config(directory)
    else:
        cfg = Config()
    ctx.imprimir(f"Datos en {directory}")

    nombre_def = cfg.nombre or ""
    nombre = ctx.preguntar("¿Cómo te llamo?", nombre_def)
    if nombre:
        cfg.nombre = nombre

    if cfg.pin and cfg.pin.startswith("pbkdf2$"):
        if ctx.confirmar("Ya hay PIN guardado. ¿Lo querés cambiar?", default=False):
            p1 = ctx.preguntar_secreto("PIN nuevo")
            p2 = ctx.preguntar_secreto("Repetí el PIN")
            err = aplicar_pin(cfg, p1, p2)
            if err:
                ctx.imprimir(err)
                return 1
    elif not ensayo:
        p1 = ctx.preguntar_secreto("PIN nuevo")
        p2 = ctx.preguntar_secreto("Repetí el PIN")
        err = aplicar_pin(cfg, p1, p2)
        if err:
            ctx.imprimir(err)
            return 1
    elif ensayo:
        ctx.imprimir("haría: pedir PIN nuevo")

    cwds_def = ",".join(cfg.plan_cwds) if cfg.plan_cwds else _default_plan_cwds(ctx.home)
    cwds_txt = ctx.preguntar("¿En qué carpetas trabajás? (separadas por coma, admite ~ y *)", cwds_def)
    if cwds_txt:
        cfg.plan_cwds = _parse_cwds(cwds_txt)

    app_origin = ""
    viewer_origin = ""
    entrada = dict(cfg.entrada or {})
    ya_tailscale = config_path.exists() and "tailscale" in (entrada.get("modos") or ["tailscale"])
    if ctx.confirmar("¿Vas a usar Colmena desde el celu u otra compu?", default=ya_tailscale):
        cfg.entrada = {**entrada, "modos": ["tailscale"]}
        ctx.imprimir(
            "Tailscale: misma cuenta en compu y celu; en la consola activá MagicDNS y HTTPS Certificates."
        )
        ctx.imprimir(
            f"  tailscale serve --bg --https=8444 http://127.0.0.1:{cfg.port}"
        )
        ctx.imprimir(
            f"  tailscale serve --bg --https=8445 http://127.0.0.1:{cfg.viewer_port}"
        )
        env_prev = _leer_env(_path_entorno(ctx))
        dns_def = (
            _dns_tailscale(ctx)
            or _host_de_origen(cfg.app_origin)
            or _host_de_origen(env_prev.get("ORQ_APP_ORIGIN", ""))
        )
        dns = ctx.preguntar(
            "Nombre de tu compu en Tailscale (ej. micompu.tu-red.ts.net)",
            dns_def,
        )
        if dns:
            app_origin = normalize_origin(f"https://{dns}:8444")
            viewer_origin = normalize_origin(f"https://{dns}:8445")
            cfg.app_origin = app_origin
            cfg.viewer_origin = viewer_origin
        ts_user = ctx.preguntar("Tu cuenta de Tailscale (ej. vos@gmail.com; Enter para no restringir)", cfg.tailscale_user)
        if ts_user:
            cfg.tailscale_user = ts_user
        url_final = app_origin or cfg.app_origin
    else:
        sl_cfg = dict(entrada.get("solo-local") or {})
        sl_cfg.setdefault("puerto_app", 8774)
        sl_cfg.setdefault("origen_app", f"http://localhost:{sl_cfg['puerto_app']}")
        cfg.entrada = {**entrada, "modos": ["solo-local"], "solo-local": sl_cfg}
        cfg.app_origin = ""
        cfg.viewer_origin = ""
        url_final = sl_cfg["origen_app"]

    term = dict(cfg.terminales or {})
    if "nuevas_en" not in term:
        term["nuevas_en"] = "guardian"
    if "vivo" not in term:
        term["vivo"] = True
    cfg.terminales = term
    if ctx.which("herdr"):
        ctx.imprimir("Herdr sigue disponible; las sesiones nuevas abren en las terminales propias de Colmena.")

    _configurar_mrs(ctx, cfg)

    ctx.imprimir("Guardando config...")
    if ensayo:
        ctx.imprimir(f"haría: save_config en {directory}")
    else:
        save_config(cfg, directory)

    vapid_def = _leer_env(_path_entorno(ctx)).get("ORQ_VAPID_SUB") or "mailto:colmena@localhost"
    mail = ctx.preguntar("Email para notificaciones push (VAPID; Enter para default)", vapid_def.replace("mailto:", ""))
    vapid = f"mailto:{mail}" if mail and "@" in mail else (mail if mail.startswith("mailto:") else vapid_def)
    modos = cfg.entrada.get("modos") or []
    env_vals: dict[str, str] = {"ORQ_VAPID_SUB": vapid}
    if "solo-local" in modos and "tailscale" not in modos:
        env_vals["ORQ_APP_ORIGIN"] = ""
        env_vals["ORQ_VIEWER_ORIGIN"] = ""
    else:
        env_vals["ORQ_APP_ORIGIN"] = cfg.app_origin or ""
        env_vals["ORQ_VIEWER_ORIGIN"] = cfg.viewer_origin or ""
    modo_tailscale = "tailscale" in modos and "solo-local" not in modos
    _escribir_env(ctx, env_vals, ensayo, modo_tailscale=modo_tailscale)

    if modo_tailscale:
        prev_origin = _leer_env(_path_entorno(ctx)).get("ORQ_APP_ORIGIN", "")
        if not (cfg.app_origin or prev_origin):
            ctx.imprimir(
                "En modo Tailscale Colmena necesita ORQ_APP_ORIGIN (nombre ts.net y tailscale serve). "
                "Sin eso no arranca bien; configurá el origen y volvé a correr el instalador."
            )
            return 1

    ctx.imprimir("Los ganchos de Claude avisan a Colmena cuando una sesión termina o pide permiso.")
    if ctx.confirmar("¿Los instalo?", default=False):
        if ensayo:
            ctx.imprimir("haría: ganchos instalar")
        else:
            from . import cli

            cli.ganchos("instalar", None, True)

    if not _instalar_kit(ctx, ensayo, sin_servicios, kit):
        return 1

    ctx.imprimir("Configurando servicios systemd de usuario...")
    if not _instalar_units(ctx, ensayo, sin_servicios):
        return 1

    if ctx.confirmar("¿Bajo el modelo de voz para dictar? (~500 MB)", default=False):
        if ensayo:
            ctx.imprimir("haría: descargar_modelo")
        else:
            from . import cli

            cli.descargar_modelo()

    ctx.imprimir("")
    ctx.imprimir(f"Abrí Colmena en {url_final}")
    ctx.imprimir("En el celu podés agregarla como app desde el navegador.")
    ctx.imprimir("Logs: journalctl --user -u orquestador -f")
    return 0


def instalar(*, ensayo: bool = False, sin_servicios: bool = False, kit: bool | None = None) -> int:
    return ejecutar_instalador(None, ensayo=ensayo, sin_servicios=sin_servicios, kit=kit)
