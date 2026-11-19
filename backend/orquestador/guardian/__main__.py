from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from orquestador.guardian.lanzador import ConfigInvalida, ajustes_de, escribir_hooks
from orquestador.guardian.nucleo import Guardian
from orquestador.guardian.registro import Registro
from orquestador.guardian.servidor import ServidorGuardian

log = logging.getLogger(__name__)


def _cargar_config():
    from orquestador.config import data_dir, load_config
    from orquestador.ganchos.ajustes import permisos_espera
    from orquestador.nueva_terminal import plan_roots

    cfg = load_config(data_dir())
    raw = getattr(cfg, "guardian", {}) or {}
    ajustes = ajustes_de(raw, os.environ)
    roots = plan_roots(cfg.plan_cwds_con_self())

    def cwd_confiable(cwd: str) -> bool:
        real = os.path.realpath(cwd)
        return any(real == root or real.startswith(root + os.sep) for root in roots)

    espera = permisos_espera(cfg)
    return ajustes, cwd_confiable, espera


def _socket_default() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base:
        raise RuntimeError("XDG_RUNTIME_DIR no está definido")
    return Path(base) / "colmena-guardian" / "guardian.sock"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="colmena-guardian")
    parser.add_argument(
        "--socket",
        type=Path,
        default=None,
        help="ruta del socket unix (default: $XDG_RUNTIME_DIR/colmena-guardian/guardian.sock)",
    )
    parser.add_argument(
        "--registro",
        type=Path,
        default=Path("~/.local/state/colmena-guardian/registro.json").expanduser(),
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        socket_path = args.socket if args.socket is not None else _socket_default()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    try:
        ajustes, cwd_confiable, espera = _cargar_config()
    except ConfigInvalida as exc:
        log.error("%s", exc)
        raise SystemExit(2) from exc

    try:
        asyncio.run(_correr(socket_path, args.registro, ajustes, cwd_confiable, espera))
    except KeyboardInterrupt:
        pass
    sys.exit(0)


async def _correr(
    socket_path: Path,
    registro_path: Path,
    ajustes,
    cwd_confiable,
    espera: int,
) -> None:
    from importlib.metadata import version

    settings = escribir_hooks(socket_path.parent, espera)
    registro = Registro(registro_path)
    guardian = Guardian(
        registro,
        ajustes,
        settings,
        entorno=os.environ,
        cwd_confiable=cwd_confiable,
    )
    await guardian.retomar()

    loop = asyncio.get_running_loop()
    apagando = asyncio.Event()

    def pedir_apagado() -> None:
        apagando.set()

    ver = version("orquestador")
    servidor = ServidorGuardian(guardian, ver, pedir_apagado)
    await servidor.abrir(socket_path)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, pedir_apagado)

    await apagando.wait()
    await servidor.cerrar()
    await guardian.apagar_ordenado()


if __name__ == "__main__":
    main()
