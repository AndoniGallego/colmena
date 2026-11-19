"""Ventana de silencio que abre el actualizador del kit de trabajo antes de mandar `/reload-plugins` a todas las sesiones."""
import math
import os
import time
from pathlib import Path
from typing import Optional

MARCA = "silencio-recarga"
VENTANA = 60.0
# Tolera relojes apenas adelantados; una marca muy en el futuro se ignora para no silenciar para siempre.
ADELANTO = 5.0

_marca: Optional[Path] = None


def configurar(path: Optional[Path]) -> None:
    global _marca
    _marca = path


def marcar(now: Optional[float] = None, path: Optional[Path] = None) -> None:
    target = path or _marca
    if target is None:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() if now is None else now)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, f"{ts}\n".encode())
    finally:
        os.close(fd)
    os.replace(tmp, target)


def vigente(path: Optional[Path] = None, now: Optional[float] = None) -> bool:
    """La marca guarda la hora (epoch, segundos) en que se escribió; vale 60 s. Ausente o ilegible: sin silencio."""
    target = path or _marca
    if target is None:
        return False
    try:
        with open(target, "r", encoding="utf-8") as fh:
            escrito = float(fh.read(64).strip())
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    if not math.isfinite(escrito):
        return False
    edad = (time.time() if now is None else now) - escrito
    return -ADELANTO <= edad <= VENTANA
