import json
import time
from collections.abc import Callable
from pathlib import Path

MARCA = "andokit-stop-bloques"
TTL_S = 60.0


def settings_de_claude() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _tiene_hook(path: Path) -> bool:
    try:
        datos = json.loads(path.read_text(encoding="utf-8"))
        grupos = datos["hooks"]["Stop"]
        for grupo in grupos:
            for gancho in grupo.get("hooks", []):
                if MARCA in str(gancho.get("command", "")):
                    return True
    except Exception:
        return False
    return False


class DetectorHookAndokit:
    """¿Está instalado el hook Stop de andokit? Solo lectura del settings.json, con cache de TTL."""

    def __init__(self, path_fn: Callable[[], Path] = settings_de_claude, ttl: float = TTL_S, clock=time.monotonic):
        self._path_fn = path_fn
        self._ttl = ttl
        self._clock = clock
        self._valor = False
        self._hasta = float("-inf")

    def __call__(self) -> bool:
        ahora = self._clock()
        if ahora >= self._hasta:
            self._valor = _tiene_hook(self._path_fn())
            self._hasta = ahora + self._ttl
        return self._valor
