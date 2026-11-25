import hashlib
import hmac
import json
import os
import re
import secrets
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
PBKDF2_ITERATIONS = 200_000
MIN_PIN_LENGTH = 8
HANDOFFS_DIR = Path.home() / ".local" / "share" / "orquestador" / "handoffs"
DEFAULT_CDNS = ["https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net", "https://unpkg.com",
                "https://cdn.tailwindcss.com", "https://code.jquery.com"]
UPLOADS_DIR = Path.home() / ".local" / "share" / "orquestador" / "uploads"
DEFAULT_PLAN_CWDS: list = []


def private_write(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception:
        if tmp.exists():
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def normalize_origin(value: str) -> str:
    return (value or "").strip().rstrip("/")


def data_dir() -> Path:
    env = os.environ.get("ORQ_DATA_DIR")
    path = Path(env).expanduser() if env else REPO_ROOT / "data"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8770
    pin: str = ""
    allowed_cidrs: list = field(
        default_factory=lambda: ["127.0.0.0/8", "::1/128", "100.64.0.0/10", "fd7a:115c:a1e0::/48"]
    )
    tailscale_user: str = ""
    claude_bin: str = ""
    herdr_bin: str = ""
    claude_projects_dir: str = ""
    claude_cwd: str = ""
    # Vacío por defecto: el "Super orquestador" ya no es especial. Quien lo configure fija y protege esos workspaces.
    protected_workspaces: list = field(default_factory=list)
    viewer_port: int = 8771
    app_origin: str = ""
    viewer_origin: str = ""
    biblioteca_roots: list = field(default_factory=list)
    biblioteca_cdns: list = field(default_factory=lambda: list(DEFAULT_CDNS))
    biblioteca_copias: bool = True
    # Comprime con gzip el stream /api/events si el cliente lo acepta; apagalo si un proxy lo acumula.
    sse_gzip: bool = True
    voz_habilitada: bool = True
    voz_modelo: str = "small"
    terminales_escritura: bool = False
    terminales_comandos_rapidos: list = field(default_factory=list)
    limpieza_dias: int = 7
    cierre_hora: str = "17:30"
    cierre_dias: list = field(default_factory=lambda: [0, 1, 2, 3, 4])
    dios_modelo: str = "sonnet"
    dios_tope_diario_tokens: int = 1_500_000
    dios_tope_mensaje_usd: float = 2.0
    # MR: vacío o negativo = hereda lo de dios_* / dios-ajustes.json.
    mrs_modelo: str = ""
    mrs_tope_mensaje_usd: float = -1.0
    mrs_tope_diario_tokens: int = -1
    nombre: str = ""
    memoria_habilitada: bool = True
    memoria_excluir: list = field(default_factory=list)
    memoria_retencion_dias: int = 0
    docker_bin: str = ""
    plan_cwds: list = field(default_factory=lambda: list(DEFAULT_PLAN_CWDS))
    entornos_extra: list = field(default_factory=list)
    entornos_principal: dict = field(default_factory=dict)
    mrs: dict = field(default_factory=dict)
    engram: dict = field(default_factory=dict)
    # Repo del propio Orquestador (spec 18): vacío = el repo desde donde corre este código.
    self_repo: str = ""
    entrada: dict = field(default_factory=dict)
    estado: dict = field(default_factory=dict)
    permisos: dict = field(default_factory=dict)
    terminales: dict = field(default_factory=dict)
    guardian: dict = field(default_factory=dict)
    reunion: dict = field(default_factory=dict)
    # Umbrales del detector de sesiones trabadas (ver trabas.Umbrales); vacío = valores por defecto.
    trabas: dict = field(default_factory=dict)
    # Nombres propios de un kit de trabajo externo (ver kit_trabajo.py); vacío = genéricos.
    kit_trabajo: dict = field(default_factory=dict)
    # Preparar la copia de una tarea de ticket: tabla `[preparar."<ruta del repo>"]`, reemplaza al `.colmena/setup.toml`.
    preparar: dict = field(default_factory=dict)

    def self_repo_path(self) -> Path:
        return Path(self.self_repo).expanduser() if self.self_repo else REPO_ROOT

    def plan_cwds_con_self(self) -> list:
        """Carpetas permitidas para planes: las configuradas más el repo propio (spec 10.2 y 18)."""
        return [*self.plan_cwds, str(self.self_repo_path())]

    def projects_dir(self) -> Path:
        if self.claude_projects_dir:
            return Path(self.claude_projects_dir).expanduser()
        return Path.home() / ".claude" / "projects"

    def cwd(self) -> Path:
        return Path(self.claude_cwd).expanduser() if self.claude_cwd else Path.home()

    def nombre_display(self) -> str:
        n = (self.nombre or "").strip()
        return n if n else "el usuario"


def _toml_key(key) -> str:
    key = str(key)
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key, ensure_ascii=False)


def _toml_str(text: str) -> str:
    out: list[str] = []
    for ch in text:
        o = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20 or o == 0x7F:
            out.append(f"\\u{o:04x}")
        else:
            out.append(ch)
    return f'"{"".join(out)}"'


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_toml_key(k)} = {_toml_value(v)}" for k, v in value.items()) + " }" if value else "{}"
    if isinstance(value, str):
        return _toml_str(value)
    return _toml_str(str(value))


def save_config(cfg: Config, directory: Path) -> None:
    path = directory / "config.toml"
    merged: dict = {}
    if path.exists():
        merged = tomllib.loads(path.read_text(encoding="utf-8"))
    for k, v in asdict(cfg).items():
        merged[k] = v
    lines = [f"{k} = {_toml_value(v)}" for k, v in merged.items()]
    private_write(path, "\n".join(lines) + "\n")


def load_config(directory: Path) -> Config:
    path = directory / "config.toml"
    if not path.exists():
        cfg = Config()
        save_config(cfg, directory)
        return cfg
    os.chmod(path, 0o600)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    known = {k: v for k, v in raw.items() if k in Config.__dataclass_fields__}
    cfg = Config(**known)
    # El env pisa al toml: la unit de systemd define los orígenes públicos igual que ORQ_VAPID_SUB.
    cfg.app_origin = normalize_origin(os.environ.get("ORQ_APP_ORIGIN") or cfg.app_origin)
    cfg.viewer_origin = normalize_origin(os.environ.get("ORQ_VIEWER_ORIGIN") or cfg.viewer_origin)
    return cfg


def load_secret(directory: Path) -> bytes:
    path = directory / "secret"
    if path.exists():
        return path.read_bytes()
    value = secrets.token_bytes(32)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(value)
    return value


def load_epoch(directory: Path) -> int:
    try:
        return int((directory / "epoch").read_text().strip())
    except (OSError, ValueError):
        return 0


def bump_epoch(directory: Path) -> int:
    value = load_epoch(directory) + 1
    private_write(directory / "epoch", str(value))
    return value


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    if not stored.startswith("pbkdf2$"):
        return False
    try:
        _, iters, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(calc.hex(), digest)
    except ValueError:
        return False
