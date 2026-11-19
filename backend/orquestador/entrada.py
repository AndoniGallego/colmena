import re
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

from orquestador import auth
from orquestador.auth import rechazar, valores_header
from orquestador.hardening import HardeningMiddleware, build_csp

MODOS_CONOCIDOS = ("tailscale", "solo-local")
MODOS_DISPONIBLES = MODOS_CONOCIDOS
HOSTS_LOCALES = frozenset({"localhost", "127.0.0.1", "::1"})
_PUERTO_SL_DEFAULT = 8774
_CABECERA_IP = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_ORIGEN = re.compile(
    r"^https?://(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]+)(:\d{1,5})?$"
)


class EntradaInvalida(ValueError):
    pass


@dataclass(frozen=True)
class Listener:
    modo: str
    rol: str
    host: str
    puerto: int


@dataclass(frozen=True)
class Ajustes:
    modo: str
    origen_app: str
    origen_visor: str
    cabecera_ip: str
    hosts_app: frozenset
    hosts_visor: frozenset
    usuario_tailscale: str


def _validar_origen(origen: str, clave: str = "origen") -> str:
    if not _ORIGEN.fullmatch(origen):
        raise EntradaInvalida(f"{clave} mal formado")
    return origen


_HOST = re.compile(r"(?:\[([0-9a-f:.]+)\]|([a-z0-9.-]+))(?::[0-9]{1,5})?", re.ASCII)


def host_pedido(scope) -> Optional[str]:
    vals = valores_header(scope, "host")
    if len(vals) != 1:
        return None
    m = _HOST.fullmatch(vals[0].lower())
    if not m:
        return None
    return m.group(1) or m.group(2)


class HostPermitidoMiddleware:
    def __init__(self, app, hosts: frozenset):
        self.app = app
        self.hosts = hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            h = host_pedido(scope)
            if h is None or h not in self.hosts:
                await rechazar(scope, receive, send, 400, "bad host")
                return
        await self.app(scope, receive, send)


def host_de(origen: str) -> str:
    if not origen:
        return ""
    try:
        parsed = urlparse(origen if "://" in origen else f"//{origen}")
    except ValueError:
        raise EntradaInvalida("origen mal formado")
    host = parsed.hostname or ""
    return host.lower()


def _entrada_dict(cfg) -> dict:
    e = cfg.entrada
    if not isinstance(e, dict):
        raise EntradaInvalida("entrada inválida")
    return e


def _cabecera_ip_de(ts: dict) -> str:
    if "cabecera_ip" not in ts:
        return ""
    val = ts["cabecera_ip"]
    if val is None or val == "":
        return ""
    if type(val) is not str:
        raise EntradaInvalida("cabecera_ip debe ser texto")
    if not _CABECERA_IP.fullmatch(val):
        raise EntradaInvalida("cabecera_ip inválida")
    return val


def _validar_puerto(val, clave: str = "puerto") -> int:
    if type(val) is not int or isinstance(val, bool):
        raise EntradaInvalida(f"{clave} debe ser un número entre 1 y 65535")
    if not 1 <= val <= 65535:
        raise EntradaInvalida(f"{clave} debe ser un número entre 1 y 65535")
    return val


def modos(cfg) -> list[str]:
    e = _entrada_dict(cfg)
    raw = e.get("modos", ["tailscale"])
    if not isinstance(raw, list):
        raise EntradaInvalida("modos inválido")
    if not raw:
        raise EntradaInvalida("modos vacío")
    vistos: set[str] = set()
    out: list[str] = []
    for m in raw:
        if type(m) is not str or not m:
            raise EntradaInvalida("modo inválido")
        if m == "cloudflare":
            raise EntradaInvalida("el modo cloudflare ya no existe; usá tailscale o solo-local")
        if m not in MODOS_DISPONIBLES:
            raise EntradaInvalida(f"modo desconocido: {m}")
        if m in vistos:
            raise EntradaInvalida(f"modo repetido: {m}")
        vistos.add(m)
        out.append(m)
    return out


def ajustes(modo: str, cfg) -> Ajustes:
    e = _entrada_dict(cfg)
    if modo == "tailscale":
        ts = e.get("tailscale", {})
        if not isinstance(ts, dict):
            raise EntradaInvalida("tailscale inválido")
        cab = _cabecera_ip_de(ts)
        origen_app = cfg.app_origin
        origen_visor = cfg.viewer_origin
        if origen_app:
            _validar_origen(origen_app, "app_origin")
        if origen_visor:
            _validar_origen(origen_visor, "viewer_origin")
        h_app = host_de(origen_app)
        h_vis = host_de(origen_visor)
        hosts_app = HOSTS_LOCALES | ({h_app} if h_app else set())
        hosts_visor = HOSTS_LOCALES | ({h_vis} if h_vis else set())
        return Ajustes(modo, origen_app, origen_visor, cab, frozenset(hosts_app), frozenset(hosts_visor),
                       cfg.tailscale_user)
    if modo == "solo-local":
        sl = e.get("solo-local", {})
        if not isinstance(sl, dict):
            raise EntradaInvalida("solo-local inválido")
        if "cabecera_ip" in sl:
            raise EntradaInvalida("solo-local no admite cabecera_ip")
        puerto_app = _validar_puerto(sl.get("puerto_app", _PUERTO_SL_DEFAULT), "puerto_app")
        origen_raw = sl.get("origen_app", "")
        if origen_raw != "" and type(origen_raw) is not str:
            raise EntradaInvalida("origen_app inválido")
        origen_app = origen_raw or f"http://localhost:{puerto_app}"
        _validar_origen(origen_app, "origen_app")
        h = host_de(origen_app)
        if h not in HOSTS_LOCALES:
            raise EntradaInvalida(f"origen_app no es local: {h}")
        return Ajustes(modo, origen_app, "", "", HOSTS_LOCALES, frozenset(), "")
    raise EntradaInvalida(f"modo desconocido: {modo}")


def listeners(cfg) -> list[Listener]:
    if cfg.host not in HOSTS_LOCALES:
        raise EntradaInvalida(f"host de bind no es local: {cfg.host}")
    ms = modos(cfg)
    for m in ms:
        ajustes(m, cfg)
    out: list[Listener] = []
    puertos: list[int] = []
    e = _entrada_dict(cfg)
    for m in ms:
        if m == "tailscale":
            p_app = _validar_puerto(cfg.port, "port")
            puertos.append(p_app)
            out.append(Listener("tailscale", "app", "127.0.0.1", p_app))
            if cfg.viewer_origin:
                p_vis = _validar_puerto(cfg.viewer_port, "viewer_port")
                puertos.append(p_vis)
                out.append(Listener("tailscale", "visor", "127.0.0.1", p_vis))
        elif m == "solo-local":
            sl = e.get("solo-local", {})
            p = _validar_puerto(
                sl.get("puerto_app", _PUERTO_SL_DEFAULT) if isinstance(sl, dict) else _PUERTO_SL_DEFAULT,
                "puerto_app",
            )
            puertos.append(p)
            out.append(Listener("solo-local", "app", "127.0.0.1", p))
    if len(puertos) != len(set(puertos)):
        dup = next(p for p in puertos if puertos.count(p) > 1)
        raise EntradaInvalida(f"puertos repetidos: {dup}")
    return out


def avisos(cfg) -> list[str]:
    try:
        ms = modos(cfg)
    except EntradaInvalida:
        return []
    out: list[str] = []
    if "tailscale" in ms:
        e = cfg.entrada if isinstance(cfg.entrada, dict) else {}
        ts = e.get("tailscale", {})
        if not isinstance(ts, dict):
            ts = {}
        if not cfg.tailscale_user:
            out.append("Falta tailscale_user: cualquiera de la tailnet llega al PIN")
        if not cfg.app_origin:
            out.append(
                "Falta app_origin: sin URL pública de la app solo se aceptan hosts locales "
                "y las peticiones por Tailscale se rechazan"
            )
        if not cfg.viewer_origin:
            out.append("Falta viewer_origin: la Biblioteca no muestra contenido")
        if not ts.get("cabecera_ip"):
            out.append("Sin entrada.tailscale.cabecera_ip: el bloqueo por PIN es global")
    return out


def origenes_principales(cfg) -> tuple[str, str]:
    modos(cfg)
    return (cfg.app_origin, cfg.viewer_origin)


def _pila_entrada(modo: str, cfg, *, hardening: bool) -> Callable:
    # Visor (hardening=False): cabeceras de seguridad en respond(); sin SecurityMiddleware externo.
    a = ajustes(modo, cfg)
    hosts = a.hosts_app if hardening else a.hosts_visor

    def wrap(app):
        wrapped = app
        if hardening:
            wrapped = HardeningMiddleware(wrapped, app_origin=a.origen_app)
        if modo == "tailscale":
            wrapped = auth.TailscaleUserMiddleware(wrapped, user=a.usuario_tailscale, estricto=True)
        wrapped = auth.CidrMiddleware(wrapped, networks=auth.parse_networks(cfg.allowed_cidrs))
        wrapped = auth.IpRealMiddleware(wrapped, cabecera=a.cabecera_ip)
        wrapped = HostPermitidoMiddleware(wrapped, hosts=hosts)
        if hardening:
            from orquestador.app import SecurityMiddleware

            wrapped = SecurityMiddleware(wrapped, csp=build_csp(cfg.viewer_origin))
        return wrapped

    return wrap


def pila_para(modo: str, cfg) -> Callable:
    return _pila_entrada(modo, cfg, hardening=True)


def pila_visor_para(modo: str, cfg) -> Callable:
    return _pila_entrada(modo, cfg, hardening=False)
