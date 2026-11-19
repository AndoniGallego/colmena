import json
import logging
import os
from pathlib import Path

log = logging.getLogger("orquestador.jsonl")


def append_privado(path: Path, entrada: dict) -> bool:
    fd = None
    try:
        linea = json.dumps(entrada, ensure_ascii=False) + "\n"
        payload = linea.encode("utf-8")
        fd = os.open(
            path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
        )
        os.fchmod(fd, 0o600)
        os.write(fd, payload)
        return True
    except (OSError, TypeError, ValueError) as exc:
        log.warning("No se pudo escribir en %s: %s", path, exc)
        return False
    finally:
        if fd is not None:
            os.close(fd)
