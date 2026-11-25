"""Cuenta los cierres que frena el control del bloque `estado` (solo bools, sin contenido)."""
from typing import Callable

from . import digest

TOPE_SESIONES = 500


class SeguidorCierres:
    def __init__(self, anotar: Callable[..., object]):
        self._anotar = anotar
        self._previos: dict[str, bool] = {}

    def al_stop(self, msg) -> None:
        sid = msg.ids.claude
        if not sid:
            return
        datos = msg.datos
        if not datos.get("recortado"):
            valido = digest.parse_estado(datos.get("last_assistant_message") or "") is not None
        else:
            valido = datos.get("tiene_estado") is True
        previo = self._previos.pop(sid, None)
        if datos.get("stop_hook_active") is True and previo is not None:
            self._anotar("cierre_frenado", motivo="otro" if previo else "estado", resuelto=valido)
        self._previos[sid] = valido
        while len(self._previos) > TOPE_SESIONES:
            del self._previos[next(iter(self._previos))]
