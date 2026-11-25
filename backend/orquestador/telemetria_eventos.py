"""Funciones puras que arman los campos de cada evento de telemetría. Nunca reciben ni devuelven contenido."""
from __future__ import annotations

from .comando_sesion import CARPETA_DISTINTA, NO_PREPARADO, TRABAJANDO, YA_CORRIDO
from .telemetria import proyecto_de, token


def _tipo_pedido(item: dict | None) -> str | None:
    if item is None:
        return None
    if item.get("accion"):
        return item["accion"]
    if item.get("tarjeta") or item.get("pestanas"):
        return "tarjeta"
    return "pestana"


def campos_pedido(item: dict | None, origen: dict, estado: str, motivo: str | None, ahora: float) -> dict:
    ts = item.get("ts") if item else None
    return {
        "tipo": _tipo_pedido(item),
        "origen": "mcp" if (origen or {}).get("via") == "mcp" else "marca",
        "creado": item is not None,
        "estado": estado,
        "motivo": None if estado == "abierto" or motivo is None else token(motivo),
        "segundos": int(ahora - ts) if isinstance(ts, (int, float)) else None,
        "leyo_otra_sesion": bool(item and item.get("leyo_otra_sesion")),
        "proyecto": proyecto_de(item.get("carpeta")) if item else None,
    }


_CODIGOS_TRASPASO = {
    YA_CORRIDO: "ya_corrido", TRABAJANDO: "trabajando", NO_PREPARADO: "no_preparado",
    CARPETA_DISTINTA: "carpeta_distinta",
    "Esa sesión ya no está abierta": "sesion_cerrada",
    "Esa sesión no admite comandos desde acá": "protegida",
    "escritura apagada": "escritura_apagada",
    "demasiadas acciones seguidas": "limite",
    "No encontré la conversación de esa sesión": "sin_conversacion",
    "No encontré ese pedido en la conversación": "sin_conversacion",
    "Ese pedido quedó viejo: la conversación siguió": "sin_conversacion",
    "El comando cambió: recargá la conversación": "comando_cambio",
    "La sesión espera una aprobación tuya en la terminal": "esperando_aprobacion",
    "La sesión no está lista para recibir un comando": "no_lista",
    "La sesión cambió de lugar: probá de nuevo": "cambio_lugar",
}


def codigo_traspaso(detail: object) -> str:
    """Token del motivo de un TraspasoError; nunca el texto, que puede traer mensajes de las terminales."""
    if not isinstance(detail, str):
        return "otro"
    if detail.startswith(("Las terminales no responden", "Las terminales no respondieron")):
        return "terminales_caidas"
    return _CODIGOS_TRASPASO.get(detail, "otro")
