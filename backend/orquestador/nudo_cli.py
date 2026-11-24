import argparse
import json
import socket
import sys
from typing import Any, Optional

from .nudo import ruta_socket

MENSAJES = {
    "offline": "Colmena no está andando.",
    "apagado": "El nudo está apagado en la PC. Lo prende Ando desde la bandeja.",
    "sin_pc": "PC no conectada: la app de Windows no está abierta.",
    "foto_vieja": 'Foto vieja: la ventana cambió. Pedí "orquestador nudo controles" de nuevo o, si venías de Mostrame, pedile a Ando que vuelva a tocar "Mostrame".',
    "sin_control": "Ese número no está en la última lista de controles.",
    "sin_controles": "La app al frente no informa sus controles (sin controles accesibles).",
    "sin_ventana": "No hay ninguna ventana al frente para leer (PC bloqueada o solo Colmena abierta).",
    "ocupado": "Ocupado por otra sesión.",
    "en_curso": "Ya hay un pedido tuyo en curso en el nudo.",
    "vencido": "La PC no respondió a tiempo.",
    "fallo_pc": "La PC no pudo hacerlo.",
}
CODIGOS_SALIDA = {
    "offline": 1,
    "invalido": 2,
    "apagado": 3,
    "sin_pc": 4,
    "foto_vieja": 5,
    "sin_control": 6,
    "sin_controles": 7,
    "sin_ventana": 8,
    "ocupado": 9,
    "en_curso": 9,
    "vencido": 10,
    "fallo_pc": 11,
}
OPS_SOCKET = {"senalar-zona": "senalar_zona", "marcar-zonas": "marcar_zonas"}
MSG_FOTO_VIEJA_ZONA = 'Foto vieja: la ventana cambió o pasaron 5 minutos. Pedile a Ando que vuelva a tocar "Mostrame".'
MAX_MARCAS = 8
ESPERA_POR_DEFECTO = 120


def parsear_marca(token: str) -> dict:
    n, sep, etiqueta = token.partition(":")
    if not sep or not etiqueta.strip():
        raise ValueError(f'La marca "{token}" tiene que ser número:etiqueta, por ejemplo 12:Guardar.')
    try:
        return {"n": int(n), "etiqueta": etiqueta}
    except ValueError:
        raise ValueError(f'La marca "{token}" tiene que empezar con el número del control.') from None


def parsear_zona(token: str) -> dict:
    ejemplo = 'La zona "%s" tiene que ser x,y,ancho,alto:etiqueta, por ejemplo 10,20,200,40:Menú.' % token
    coords, sep, etiqueta = token.partition(":")
    if not sep or not etiqueta.strip():
        raise ValueError(ejemplo)
    partes = coords.split(",")
    if len(partes) != 4:
        raise ValueError(ejemplo)
    try:
        x, y, ancho, alto = (int(v) for v in partes)
    except ValueError:
        raise ValueError(ejemplo) from None
    return {"x": x, "y": y, "ancho": ancho, "alto": alto, "etiqueta": etiqueta}


def timeout_para(op: str, args: dict) -> float:
    if op == "senalar" and args.get("esperar") is not None:
        return float(args["esperar"] or ESPERA_POR_DEFECTO) + 20.0
    if op == "controles":
        return 20.0
    return 15.0


def _construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="orquestador nudo")
    sub = p.add_subparsers(dest="op", required=True)
    sub.add_parser("controles")
    s = sub.add_parser("senalar")
    s.add_argument("n", type=int)
    s.add_argument("texto")
    s.add_argument("--esperar", nargs="?", type=int, const=ESPERA_POR_DEFECTO, default=None)
    m = sub.add_parser("marcar")
    m.add_argument("marcas", nargs="+")
    sz = sub.add_parser("senalar-zona")
    for n in ("x", "y", "ancho", "alto"):
        sz.add_argument(n, type=int)
    sz.add_argument("texto")
    mz = sub.add_parser("marcar-zonas")
    mz.add_argument("zonas", nargs="+")
    sub.add_parser("limpiar")
    sub.add_parser("estado")
    return p


def _hablar(ruta, pedido: dict, timeout: float) -> tuple[Optional[dict], Optional[str]]:
    """Devuelve (respuesta, falla) con falla en 'offline' o 'vencido'."""
    if not ruta or not ruta.exists():
        return None, "offline"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(str(ruta))
        sock.sendall(json.dumps(pedido, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
        buf = b""
        while b"\n" not in buf and len(buf) < 4 * 1024 * 1024:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
        if not buf:
            return None, "offline"
        return json.loads(buf.split(b"\n", 1)[0].decode()), None
    except socket.timeout:
        return None, "vencido"
    except (OSError, ValueError):
        return None, "offline"
    finally:
        sock.close()


def _salida(op: str, datos: Any) -> str:
    if op in ("controles", "estado"):
        return json.dumps(datos, ensure_ascii=False)
    datos = datos if isinstance(datos, dict) else {}
    if op in ("marcar", "limpiar", "senalar_zona", "marcar_zonas"):
        return "no había nada tuyo" if datos.get("nada") else "ok"
    return str(datos.get("resultado", "ok"))


def _fallar(codigo: str, mensaje: Optional[str] = None) -> int:
    print(mensaje or MENSAJES.get(codigo, codigo), file=sys.stderr)
    return CODIGOS_SALIDA.get(codigo, 2)


def main_nudo(argv: list[str], environ: Optional[dict] = None) -> int:
    import os

    env = environ if environ is not None else os.environ
    try:
        ns = _construir_parser().parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    sesion = env.get("COLMENA_SESION")
    if not sesion:
        return _fallar("invalido", "El nudo se usa solo desde una sesión de Colmena.")
    args: dict = {}
    op = OPS_SOCKET.get(ns.op, ns.op)
    if ns.op == "senalar-zona":
        args = {"zona": {"x": ns.x, "y": ns.y, "ancho": ns.ancho, "alto": ns.alto}, "texto": ns.texto}
    elif ns.op == "marcar-zonas":
        if len(ns.zonas) > MAX_MARCAS:
            return _fallar("invalido", f"Máximo {MAX_MARCAS} zonas por vez.")
        try:
            args = {"zonas": [parsear_zona(t) for t in ns.zonas]}
        except ValueError as e:
            return _fallar("invalido", str(e))
    elif ns.op == "senalar":
        args = {"n": ns.n, "texto": ns.texto}
        if ns.esperar is not None:
            args["esperar"] = ns.esperar
    elif ns.op == "marcar":
        if len(ns.marcas) > MAX_MARCAS:
            return _fallar("invalido", f"Máximo {MAX_MARCAS} marcas por vez.")
        try:
            args = {"marcas": [parsear_marca(t) for t in ns.marcas]}
        except ValueError as e:
            return _fallar("invalido", str(e))
    resp, falla = _hablar(
        ruta_socket(env), {"op": op, "sesion": sesion, "args": args}, timeout_para(op, args)
    )
    if falla:
        return _fallar(falla)
    if not isinstance(resp, dict):
        return _fallar("offline")
    if resp.get("ok"):
        print(_salida(op, resp.get("datos")))
        return 0
    codigo = str(resp.get("error") or "invalido")
    mensaje = resp.get("mensaje") if codigo in ("invalido", "ocupado") else None
    if codigo == "foto_vieja" and op in OPS_SOCKET.values():
        mensaje = MSG_FOTO_VIEJA_ZONA
    return _fallar(codigo, mensaje)
