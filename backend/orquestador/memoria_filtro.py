"""Filtro MCP por stdio entre Claude y Engram para la guía y el Copiloto.

Lee JSON-RPC delimitado por líneas de stdin, lo reenvía al proceso hijo (argv después de `--`) y devuelve lo que el
hijo conteste. Engram acepta `project` en cada llamada (`--project` es solo el default): este filtro es lo que
garantiza que el ayudante escriba solo en su memoria y lea la suya y, si está configurada, la de trabajo.

Uso: python -m orquestador.memoria_filtro --propio X [--trabajo Y] -- <argv del hijo>
"""
import argparse
import json
import re
import subprocess
import sys
import threading

ALIAS_TRABAJO = "trabajo"
_PROYECTO_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
PASAN = ("mem_get_observation",)

_lock_salida = threading.Lock()


def _error(id_, texto: str) -> bytes:
    cuerpo = {"jsonrpc": "2.0", "id": id_,
              "result": {"isError": True, "content": [{"type": "text", "text": texto}]}}
    return (json.dumps(cuerpo, ensure_ascii=False) + "\n").encode()


def decidir(linea: bytes, propio: str, trabajo: str | None) -> tuple[bytes | None, bytes | None]:
    """Devuelve (lo que se reenvía al hijo, la respuesta de error para el cliente); a lo sumo uno viene."""
    try:
        msg = json.loads(linea)
    except ValueError:
        return None, None
    if not isinstance(msg, dict):
        return None, None
    if msg.get("method") != "tools/call":
        return linea, None
    id_ = msg.get("id")
    params = msg.get("params")
    if not isinstance(params, dict):
        return None, (_error(id_, "llamada inválida") if "id" in msg else None)
    nombre = params.get("name")
    args = params.get("arguments")
    args = dict(args) if isinstance(args, dict) else {}
    # `scope: personal` guarda y busca fuera del proyecto: se queda siempre en el del proyecto.
    if nombre in ("mem_save", "mem_search"):
        args.pop("scope", None)
    if nombre == "mem_save":
        args["project"] = propio
    elif nombre == "mem_search":
        args.pop("all_projects", None)
        destino = args.get("project")
        if destino in (None, propio):
            args["project"] = propio
        elif destino == ALIAS_TRABAJO:
            if not trabajo:
                return None, _error(id_, "no hay memoria de trabajo configurada")
            args["project"] = trabajo
        else:
            return None, _error(id_, "solo podés buscar en tu memoria o en la de trabajo")
    elif nombre not in PASAN:
        return None, (_error(id_, f"herramienta no permitida: {nombre}") if "id" in msg else None)
    else:
        return linea, None
    params["arguments"] = args
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode(), None


def _escribir_stdout(datos: bytes) -> None:
    with _lock_salida:
        sys.stdout.buffer.write(datos)
        sys.stdout.buffer.flush()


def _leer_stdin(hijo: subprocess.Popen, propio: str, trabajo: str | None) -> None:
    try:
        for linea in sys.stdin.buffer:
            if not linea.strip():
                continue
            reenviar, error = decidir(linea, propio, trabajo)
            if error:
                _escribir_stdout(error)
            if reenviar:
                hijo.stdin.write(reenviar if reenviar.endswith(b"\n") else reenviar + b"\n")
                hijo.stdin.flush()
    except (OSError, ValueError):
        pass
    finally:
        try:
            hijo.stdin.close()
        except OSError:
            pass


def _proyecto(valor: str) -> str:
    if not _PROYECTO_RE.fullmatch(valor):
        raise argparse.ArgumentTypeError(f"nombre de proyecto inválido: {valor!r}")
    return valor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memoria_filtro")
    parser.add_argument("--propio", required=True, type=_proyecto)
    parser.add_argument("--trabajo", type=_proyecto, default=None)
    parser.add_argument("hijo", nargs=argparse.REMAINDER)
    ns = parser.parse_args(argv)
    cmd = ns.hijo[1:] if ns.hijo[:1] == ["--"] else ns.hijo
    if not cmd:
        parser.error("falta el comando del hijo después de --")
    try:
        hijo = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, shell=False)
    except OSError as exc:
        print(f"memoria_filtro: no pude lanzar el hijo: {exc}", file=sys.stderr)
        return 1
    threading.Thread(target=_leer_stdin, args=(hijo, ns.propio, ns.trabajo), daemon=True).start()
    for linea in hijo.stdout:
        _escribir_stdout(linea)
    return hijo.wait()


if __name__ == "__main__":
    sys.exit(main())
