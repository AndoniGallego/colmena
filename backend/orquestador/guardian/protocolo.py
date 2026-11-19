from __future__ import annotations

import json

VERSION = 1
MAX_LINEA = 1 << 20

NO_EXISTE = "no_existe"
NO_DISPONIBLE = "no_disponible"
INVALIDO = "invalido"
TIEMPO = "tiempo"
NO_TOMADO = "no_tomado"
INTERNO = "interno"

OPERACIONES = frozenset(
    {
        "hola",
        "tablero",
        "crear_espacio",
        "crear_linea",
        "arrancar_claude",
        "renombrar",
        "cerrar",
        "leer",
        "escribir",
        "teclas",
        "mandar_prompt",
        "interrumpir",
        "ejecutar",
        "proceso",
        "redimensionar",
        "suscribir",
        "desuscribir",
        "apagar_ordenado",
    }
)


class ErrorProtocolo(Exception):
    def __init__(self, codigo: str, mensaje: str, id: int | None = None) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.id = id


def codificar(obj: dict) -> bytes:
    linea = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    payload = linea.encode("utf-8")
    if len(payload) > MAX_LINEA:
        raise ErrorProtocolo(INVALIDO, "mensaje demasiado grande")
    return payload


def _id_valido(valor: object) -> int | None:
    if isinstance(valor, bool) or not isinstance(valor, int):
        return None
    if valor < 0:
        return None
    return valor


def leer_pedido(linea: bytes) -> tuple[int, str, dict]:
    if not linea.endswith(b"\n"):
        raise ErrorProtocolo(INVALIDO, "falta fin de línea")
    if len(linea) > MAX_LINEA:
        raise ErrorProtocolo(INVALIDO, "línea demasiado grande")
    try:
        datos = json.loads(linea.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ErrorProtocolo(INVALIDO, "json inválido")
    if not isinstance(datos, dict):
        raise ErrorProtocolo(INVALIDO, "se esperaba un objeto json")
    pedido_id = _id_valido(datos.get("id"))
    if pedido_id is None:
        raise ErrorProtocolo(INVALIDO, "id inválido")
    op = datos.get("op")
    if not isinstance(op, str) or op not in OPERACIONES:
        raise ErrorProtocolo(INVALIDO, "operación inválida", pedido_id)
    args = datos.get("args", {})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ErrorProtocolo(INVALIDO, "args inválido", pedido_id)
    return pedido_id, op, args


def respuesta_ok(id: int, res: dict) -> dict:
    return {"id": id, "ok": True, "res": res}


def respuesta_error(id: int, codigo: str, mensaje: str) -> dict:
    return {"id": id, "ok": False, "error": {"codigo": codigo, "mensaje": mensaje}}


def leer_mensaje(linea: bytes) -> dict:
    if not linea.endswith(b"\n"):
        raise ErrorProtocolo(INVALIDO, "falta fin de línea")
    if len(linea) > MAX_LINEA:
        raise ErrorProtocolo(INVALIDO, "línea demasiado grande")
    try:
        datos = json.loads(linea.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ErrorProtocolo(INVALIDO, "json inválido")
    if not isinstance(datos, dict):
        raise ErrorProtocolo(INVALIDO, "se esperaba un objeto json")
    return datos
