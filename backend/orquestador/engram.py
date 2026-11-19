import json
import os
import selectors
import subprocess
import time
from typing import Optional

# Las únicas cuatro de lectura. Doble llave: Engram las filtra con --tools y este cliente rechaza el resto.
HERRAMIENTAS = ("mem_search", "mem_get_observation", "mem_context", "mem_timeline")
# La única de escritura: solo la usa el servidor para la tarjeta ```engram; nunca va a las herramientas MCP.
ESCRITURA = ("mem_save",)
TIMEOUT = 8.0
MAX_LINEA = 4 * 1024 * 1024


class EngramError(RuntimeError):
    pass


def argv_docker(docker_bin: str, contenedor: str, proyecto: str) -> list:
    if not contenedor or not proyecto:
        raise ValueError("Engram requiere contenedor y proyecto")
    # Siempre `engram mcp` por stdio: los subcomandos de la CLI intentan salir a internet a buscar versiones.
    return [docker_bin, "exec", "-i", contenedor, "engram", "mcp", "--tools=" + ",".join(HERRAMIENTAS),
            "--project", proyecto]


def argv_docker_guardar(docker_bin: str, contenedor: str, proyecto: str) -> list:
    if not contenedor or not proyecto:
        raise ValueError("Engram requiere contenedor y proyecto")
    return [docker_bin, "exec", "-i", contenedor, "engram", "mcp", "--tools=" + ",".join(ESCRITURA), "--project", proyecto]


class EngramCliente:
    """Cliente MCP por stdio, de un solo proceso por vida del objeto."""

    def __init__(self, argv: list, timeout: float = TIMEOUT, permitidas: tuple = HERRAMIENTAS):
        self.argv = argv
        self.permitidas = permitidas
        self.timeout = timeout
        self._proc: Optional[subprocess.Popen] = None
        self._buf = b""
        self._next_id = 0
        self.caido = False

    def _arrancar(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        if self.caido:
            raise EngramError("Engram no está disponible")
        try:
            self._proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, shell=False)
            self._buf = b""
            self._pedir("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                       "clientInfo": {"name": "orquestador-memoria", "version": "1"}})
            self._enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except (OSError, EngramError):
            self.caido = True
            self.cerrar()
            raise EngramError("Engram no está disponible")

    def _enviar(self, msg: dict) -> None:
        try:
            self._proc.stdin.write((json.dumps(msg) + "\n").encode())
            self._proc.stdin.flush()
        except (OSError, ValueError):
            raise EngramError("Engram no está disponible")

    def _linea(self, limite: float) -> bytes:
        fd = self._proc.stdout.fileno()
        with selectors.DefaultSelector() as sel:
            sel.register(fd, selectors.EVENT_READ)
            while b"\n" not in self._buf:
                restante = limite - time.monotonic()
                if restante <= 0 or not sel.select(restante):
                    raise EngramError("Engram no respondió a tiempo")
                chunk = os.read(fd, 65536)
                if not chunk:
                    raise EngramError("Engram no está disponible")
                self._buf += chunk
                if len(self._buf) > MAX_LINEA:
                    raise EngramError("respuesta de Engram demasiado grande")
        linea, _, self._buf = self._buf.partition(b"\n")
        return linea

    def _pedir(self, method: str, params: dict) -> dict:
        self._next_id += 1
        ident = self._next_id
        self._enviar({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        limite = time.monotonic() + self.timeout
        while True:
            try:
                msg = json.loads(self._linea(limite))
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("id") == ident:
                if "error" in msg:
                    raise EngramError("Engram devolvió un error")
                result = msg.get("result")
                return result if isinstance(result, dict) else {}

    def herramientas(self) -> list:
        self._arrancar()
        tools = self._pedir("tools/list", {}).get("tools")
        return [t.get("name") for t in tools if isinstance(t, dict)] if isinstance(tools, list) else []

    def llamar(self, nombre: str, argumentos: dict) -> str:
        if nombre not in self.permitidas:
            raise EngramError("herramienta no permitida")
        self._arrancar()
        try:
            result = self._pedir("tools/call", {"name": nombre, "arguments": argumentos})
        except EngramError:
            self.cerrar()
            raise
        partes = [c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict) and c.get("type") == "text"]
        texto = "\n".join(p for p in partes if isinstance(p, str))
        if result.get("isError"):
            raise EngramError("Engram no pudo responder")
        try:
            obj = json.loads(texto)
        except ValueError:
            return texto
        return obj["result"] if isinstance(obj, dict) and isinstance(obj.get("result"), str) else texto

    def cerrar(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()
