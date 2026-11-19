import re
import time
from typing import Callable, Optional

TTL = 120.0
DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_CLIENTS = 64


class Presencia:
    """Quién está mirando la app: visible según lo que reporta el front y con el SSE todavía conectado."""

    def __init__(self, clock: Callable = time.monotonic):
        self.clock = clock
        self.visible: dict = {}
        self.streams: dict = {}
        self.sesiones: dict = {}
        self.escritorio: set[str] = set()

    def report(self, device: str, visible: bool, mirando: Optional[str] = None,
               escritorio: Optional[bool] = None) -> None:
        if escritorio is True:
            if device not in self.escritorio and len(self.escritorio) >= MAX_CLIENTS:
                for d in list(self.escritorio):
                    if d not in self.streams:
                        self.escritorio.discard(d)
            if device in self.escritorio or len(self.escritorio) < MAX_CLIENTS:
                self.escritorio.add(device)
        elif escritorio is False:
            self.escritorio.discard(device)
        if not visible:
            self.visible.pop(device, None)
            self.sesiones.pop(device, None)
        elif device in self.visible or len(self.visible) < MAX_CLIENTS:
            self.visible[device] = self.clock()
            if mirando:
                self.sesiones[device] = mirando
            else:
                self.sesiones.pop(device, None)

    def hay_escritorio(self) -> bool:
        return any(device in self.streams for device in self.escritorio)

    def connect(self, device: str) -> None:
        self.streams[device] = self.streams.get(device, 0) + 1

    def disconnect(self, device: str) -> None:
        left = self.streams.get(device, 0) - 1
        if left > 0:
            self.streams[device] = left
            return
        self.streams.pop(device, None)
        self.visible.pop(device, None)
        self.sesiones.pop(device, None)

    def _vigentes(self) -> list:
        limit = self.clock() - TTL
        for device in [d for d, at in self.visible.items() if at < limit]:
            del self.visible[device]
            self.sesiones.pop(device, None)
        return [d for d in self.visible if d in self.streams]

    def present(self) -> bool:
        return bool(self._vigentes())

    def mirando(self, session_id: str) -> bool:
        return bool(session_id) and any(self.sesiones.get(d) == session_id for d in self._vigentes())
