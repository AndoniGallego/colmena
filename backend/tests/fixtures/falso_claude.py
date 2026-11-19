#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import tty


def _escribir_args(cwd: str) -> None:
    datos = {
        "argv": sys.argv[1:],
        "colmena": os.environ.get("COLMENA_SESION"),
        "herdr": any(k.startswith("HERDR_") for k in os.environ),
        "claudecode": "CLAUDECODE" in os.environ,
        "term": os.environ.get("TERM"),
    }
    with open(os.path.join(cwd, ".falso_args.json"), "w", encoding="utf-8") as f:
        json.dump(datos, f)


def _ventana_confianza(cwd: str) -> float | None:
    ruta = os.path.join(cwd, ".falso_confianza")
    if not os.path.isfile(ruta):
        return None
    try:
        return float(open(ruta, encoding="utf-8").read().strip() or "2.0")
    except ValueError:
        return 2.0


def _dialogo_confianza(ventana: float) -> bool:
    import select

    msg = (
        "Do you trust the files in this folder?\r\n"
        " ❯ 1. Yes, I trust this folder\r\n"
        "   2. No, exit\r\n"
    )
    out = sys.stdout.buffer
    out.write(msg.encode())
    out.flush()
    inicio = time.monotonic()
    visto_abajo = False
    while True:
        r, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not r:
            continue
        ch = os.read(sys.stdin.fileno(), 1)
        if not ch:
            return False
        if ch in (b"\r", b"\n"):
            if time.monotonic() - inicio < ventana or not visto_abajo:
                raise SystemExit(1)
            out.write(b"\x1b[2J\x1b[H")
            out.flush()
            return True
        if ch == b"\x1b":
            r2, _, _ = select.select([sys.stdin], [], [], 0.1)
            if r2:
                if os.read(sys.stdin.fileno(), 1) == b"[":
                    r3, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if r3 and os.read(sys.stdin.fileno(), 1) == b"B":
                        visto_abajo = True


def main() -> int:
    cwd = os.getcwd()
    _escribir_args(cwd)

    if "--resume" in sys.argv and os.path.isfile(os.path.join(cwd, ".falso_muere")):
        return 2

    tty.setraw(0)
    out = sys.stdout.buffer
    out.write("\x1b]0;✳ Falso\x07".encode())
    out.flush()

    ventana = _ventana_confianza(cwd)
    if ventana is not None:
        _dialogo_confianza(ventana)

    out.write("\r\n❯ ".encode())
    out.flush()
    linea = b""
    while True:
        ch = os.read(sys.stdin.fileno(), 1)
        if not ch:
            return 0
        if ch in (b"\r", b"\n"):
            texto = linea.decode("utf-8", errors="replace")
            if texto.strip() == "/exit":
                return 0
            out.write(f"\r\n\u25cf respuesta a: {texto}\r\n\u276f ".encode())
            out.flush()
            linea = b""
            continue
        if ch == b"\x1b":
            out.write(b"\r\n Interrumpido\r\n\xe2\x9d\xaf ")
            out.flush()
            linea = b""
            continue
        out.write(ch)
        out.flush()
        linea += ch


if __name__ == "__main__":
    raise SystemExit(main())
