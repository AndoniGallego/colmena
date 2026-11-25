import argparse
import asyncio
import contextlib
import logging
import getpass
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import data_dir, load_config, load_secret, save_config


def set_pin() -> int:
    from .instalador import aplicar_pin

    os.umask(0o077)
    directory = data_dir()
    cfg = load_config(directory)
    pin = getpass.getpass("PIN nuevo: ")
    repetir = getpass.getpass("Repetí el PIN: ") if sys.stdin.isatty() else pin
    err = aplicar_pin(cfg, pin, repetir)
    if err:
        print(err, file=sys.stderr)
        return 1
    save_config(cfg, directory)
    print(f"PIN guardado en {directory / 'config.toml'}")
    return 0


def servidores(app, viewer_app, cfg):
    import uvicorn

    from .entrada import listeners, pila_para, pila_visor_para

    ls = listeners(cfg)
    out: list = []
    first_app = True
    for lst in ls:
        if lst.rol == "app":
            wrapped = pila_para(lst.modo, cfg)(app)
            log_level = "info" if first_app else "warning"
            lifespan = "on" if first_app else "off"
            first_app = False
        else:
            wrapped = pila_visor_para(lst.modo, cfg)(viewer_app)
            log_level = "warning"
            lifespan = "off"
        srv = uvicorn.Server(
            uvicorn.Config(
                wrapped,
                host=lst.host,
                port=lst.puerto,
                log_level=log_level,
                lifespan=lifespan,
                proxy_headers=False,
                forwarded_allow_ips="",
                ws_max_size=65536,
            )
        )
        if out:
            srv.capture_signals = contextlib.nullcontext
        out.append(srv)
    return out


async def _run(app, cfg) -> None:
    from .biblioteca_viewer import create_viewer_app
    from .entrada import listeners

    log = logging.getLogger("orquestador")
    ls = listeners(cfg)
    viewer_app = None
    if any(lst.rol == "visor" for lst in ls):
        viewer_app = create_viewer_app(app.state.library, app.state.secret, app.state.epoch, cfg)

    servers = servidores(app, viewer_app, cfg)
    tasks: list = []

    async def run_secondary(srv, puerto: int):
        try:
            await srv.serve()
        except SystemExit:
            log.error("no se pudo abrir el puerto %s", puerto)

    for srv, lst in zip(servers[1:], ls[1:]):
        tasks.append(asyncio.create_task(run_secondary(srv, lst.puerto)))

    await servers[0].serve()
    for srv, task in zip(servers[1:], tasks):
        srv.should_exit = True
        await task


def descargar_modelo() -> int:
    from .voz import download_model

    directory = data_dir()
    cfg = load_config(directory)
    print(f"Descargando el modelo {cfg.voz_modelo} (única salida a internet de la voz)...")
    print(download_model(cfg.voz_modelo, directory / "models"))
    return 0


def _imprimir_resultado_ganchos(r) -> None:
    partes = [r.mensaje, str(r.settings)]
    if r.respaldo is not None:
        partes.append(f"respaldo: {r.respaldo}")
    print(", ".join(partes))


def ganchos(accion: str | None, settings: Path | None, si: bool) -> int:
    from .ganchos import ajustes
    from .ganchos.definiciones import SCRIPT
    from .ganchos.instalador import SettingsInvalido, desinstalar, instalar

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    if accion not in ("instalar", "desinstalar"):
        print("Acción requerida: instalar o desinstalar", file=sys.stderr)
        return 1

    destino = settings if settings is not None else Path.home() / ".claude" / "settings.json"

    if not si:
        print(f"{accion} hooks de Colmena en {destino}")
        print("Agregá --si para confirmar")
        return 1

    respaldos = data_dir() / "ganchos-respaldos"

    try:
        if accion == "instalar":
            destino.parent.mkdir(parents=True, exist_ok=True)
            try:
                espera = ajustes.permisos_espera(load_config(data_dir()))
            except tomllib.TOMLDecodeError as exc:
                print(f"config.toml inválido: {exc}", file=sys.stderr)
                return 2
            r = instalar(
                destino,
                respaldos,
                script=SCRIPT,
                espera=espera,
                ahora=lambda: datetime.now(timezone.utc),
            )
        else:
            r = desinstalar(destino, respaldos)
    except SettingsInvalido as exc:
        print(exc)
        return 2

    _imprimir_resultado_ganchos(r)
    return 0


def recargar_sesiones() -> int:
    from .recarga import cliente_recargar, ruta_socket

    ruta = ruta_socket()
    if ruta is None:
        print("Colmena no está andando; no hay sesiones para recargar")
        return 0
    ok, data = cliente_recargar(ruta)
    if not ok and data.get("offline"):
        print("Colmena no está andando; no hay sesiones para recargar")
        return 0
    if not data.get("ok"):
        print(data.get("error", "error al recargar sesiones"), file=sys.stderr)
        return 1
    print(
        f"Colmena: {data['recargadas']} sesiones recargadas, "
        f"{data['esperando']} se recargan cuando terminen"
    )
    return 0


def serve() -> int:
    import logging

    from .app import create_app
    from .entrada import EntradaInvalida, avisos, listeners, modos, origenes_principales
    from .state import StateStore

    os.umask(0o077)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
    log = logging.getLogger("orquestador")
    directory = data_dir()
    cfg = load_config(directory)
    if not cfg.pin:
        print("Falta el PIN. Corré `uv run orquestador set-pin` y volvé a arrancar.", file=sys.stderr)
        return 1
    if not cfg.pin.startswith("pbkdf2$"):
        print("El PIN de config.toml no está hasheado. Corré `uv run orquestador set-pin`.", file=sys.stderr)
        return 1
    try:
        listeners(cfg)
    except EntradaInvalida as exc:
        print(f"Config de entrada inválida: {exc}", file=sys.stderr)
        return 1
    if "tailscale" in modos(cfg) and not cfg.app_origin:
        print(
            "Config de entrada inválida: falta app_origin (ORQ_APP_ORIGIN) para el modo tailscale",
            file=sys.stderr,
        )
        return 1
    cfg.app_origin, cfg.viewer_origin = origenes_principales(cfg)
    for aviso in avisos(cfg):
        log.warning(aviso)
    from .ganchos import colmena_gancho

    ruta_ganchos = colmena_gancho.ruta_socket(os.environ)
    ganchos_socket = None
    if ruta_ganchos is None:
        log.warning("XDG_RUNTIME_DIR no definido; canal de ganchos desactivado")
    else:
        ganchos_socket = Path(ruta_ganchos)
    from .recarga import ruta_socket as ruta_recarga

    recarga_socket = ruta_recarga()
    if recarga_socket is None:
        log.warning("XDG_RUNTIME_DIR no definido; socket de recarga desactivado")
    from .nudo import ruta_socket as ruta_nudo

    nudo_socket = ruta_nudo()
    if nudo_socket is None:
        log.warning("XDG_RUNTIME_DIR no definido; socket del nudo desactivado")
    from .mcp_canal import ruta_socket as ruta_mcp

    mcp_socket = ruta_mcp(os.environ)
    if mcp_socket is None:
        log.warning("XDG_RUNTIME_DIR no definido; canal del MCP desactivado")
    from .telemetria import Telemetria, TelemetriaHandler

    telemetria = Telemetria(directory / "telemetria", activa=lambda: cfg.telemetria_activa)
    telemetria_handler = None
    if cfg.telemetria_activa:
        telemetria_handler = TelemetriaHandler(telemetria)
        log.addHandler(telemetria_handler)
    app = create_app(
        cfg,
        load_secret(directory),
        StateStore(directory),
        telemetria=telemetria,
        telemetria_handler=telemetria_handler,
        entrada_interna=False,
        ganchos_socket=ganchos_socket,
        recarga_socket=recarga_socket,
        nudo_socket=nudo_socket,
        mcp_socket=mcp_socket,
    )
    asyncio.run(_run(app, cfg))
    return 0


def kit(accion: str | None, dry_run: bool, check: bool) -> int:
    from . import kit_instalador as ki

    try:
        return _kit(ki, accion, dry_run, check)
    except ki.KitInvalido as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def _kit(ki, accion: str | None, dry_run: bool, check: bool) -> int:
    import subprocess

    if accion not in ("instalar", "desinstalar"):
        print("Acción requerida: instalar o desinstalar", file=sys.stderr)
        return 1
    d = ki.destinos(os.environ, Path.home(), ki.KIT_DIR)
    if accion == "desinstalar":
        if dry_run or check:
            print("desinstalar no acepta --dry-run ni --check", file=sys.stderr)
            return 2
        return ki.desinstalar_kit(ki.KIT_DIR, d, print)
    modo = "check" if check else "ensayo" if dry_run else "instalar"
    correr = lambda cmd: subprocess.run(cmd, check=False).returncode  # noqa: E731
    return ki.instalar_kit(ki.KIT_DIR, ki.REPO_ROOT / "deploy", d, modo, print, correr, datetime.now)


class _SinEfectos:
    def flush(self) -> None:
        pass

    def quitar_resumenes_viejos(self, ahora=None, dias: int = 90) -> int:
        return 0


def telemetria_resumen(semana: str | None, sin_aviso: bool, como_json: bool) -> int:
    from .biblioteca import Library
    from .push import PushService
    from .telemetria import Telemetria
    from .telemetria_resumen import PropuestasStore, ResumenSemanal, generar_resumen, semana_anterior

    os.umask(0o077)
    directory = data_dir()
    cfg = load_config(directory)
    ahora = datetime.now().astimezone()
    objetivo = semana or semana_anterior(ahora.date())
    tel = Telemetria(directory / "telemetria", activa=lambda: cfg.telemetria_activa)
    store = PropuestasStore(directory / "telemetria" / "propuestas.json", wall=lambda: datetime.now(timezone.utc))
    if sin_aviso:
        biblioteca, push, handler = _SinEfectos(), None, _SinEfectos()
    else:
        biblioteca, push, handler = Library(cfg, directory, load_secret(directory)), PushService(directory), _SinEfectos()
        push.avisos.registrar_kind("resumen")
    try:
        datos = asyncio.run(generar_resumen(directorio=tel.directorio, semana=objetivo, propuestas=store,
                                            biblioteca=biblioteca, push=push, handler=handler, telemetria=tel,
                                            ahora=ahora, avisar=not sin_aviso, guardar=not sin_aviso))
    except ValueError:
        print("Semana inválida: usá el formato AAAA-Wnn, por ejemplo 2026-W47", file=sys.stderr)
        return 2
    if semana is None and not sin_aviso:
        ResumenSemanal(directory, lambda: "", lambda: [], lambda s: None).marcar(objetivo)
    if como_json:
        print(json.dumps(datos, ensure_ascii=False))
        return 0
    nuevas = datos["propuestas"]["nuevas"]
    print(f"Semana {objetivo}: {len(nuevas)} propuestas nuevas")
    for c in nuevas:
        print(f"- {c['texto']}")
    return 0


def main() -> None:
    if sys.argv[1:2] == ["nudo"]:
        from .nudo_cli import main_nudo

        sys.exit(main_nudo(sys.argv[2:]))
    parser = argparse.ArgumentParser(prog="orquestador")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["serve", "set-pin", "descargar-modelo", "ganchos", "instalar", "exportar", "recargar-sesiones", "ver", "kit", "telemetria"],
        default="serve",
    )
    parser.add_argument("accion", nargs="?")
    parser.add_argument("destino", nargs="?", help="carpeta destino (exportar)")
    parser.add_argument("--settings", type=Path, default=None)
    parser.add_argument("--si", action="store_true")
    parser.add_argument("--ensayo", action="store_true")
    parser.add_argument("--sin-servicios", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--permitir-hallazgos", action="store_true")
    parser.add_argument("--semana", default=None, help="semana ISO a resumir (telemetria resumen)")
    parser.add_argument("--sin-aviso", action="store_true", help="no guarda en la Biblioteca ni avisa")
    parser.add_argument("--json", dest="como_json", action="store_true")
    grupo_kit = parser.add_mutually_exclusive_group()
    grupo_kit.add_argument("--con-kit", dest="kit", action="store_const", const=True, default=None)
    grupo_kit.add_argument("--sin-kit", dest="kit", action="store_const", const=False)
    args = parser.parse_args()
    if args.command == "ganchos":
        sys.exit(ganchos(args.accion, args.settings, args.si))
    if args.command == "instalar":
        from .instalador import instalar

        sys.exit(instalar(ensayo=args.ensayo, sin_servicios=args.sin_servicios, kit=args.kit))
    if args.command == "exportar":
        destino = args.destino or args.accion
        if not destino:
            print("Falta la carpeta destino. Ejemplo: uv run orquestador exportar ~/colmena-para-compartir", file=sys.stderr)
            sys.exit(1)
        from .exportar import exportar

        sys.exit(exportar(destino, args.permitir_hallazgos))
    if args.command == "kit":
        sys.exit(kit(args.accion, args.dry_run, args.check))
    if args.command == "telemetria":
        if args.accion != "resumen":
            print("Acción requerida: resumen", file=sys.stderr)
            sys.exit(1)
        sys.exit(telemetria_resumen(args.semana, args.sin_aviso, args.como_json))
    if args.command == "recargar-sesiones":
        sys.exit(recargar_sesiones())
    if args.command == "ver":
        from .ver_terminal import ver_terminal

        sys.exit(ver_terminal(args.accion))
    commands = {"set-pin": set_pin, "descargar-modelo": descargar_modelo}
    sys.exit(commands.get(args.command, serve)())


if __name__ == "__main__":
    main()
