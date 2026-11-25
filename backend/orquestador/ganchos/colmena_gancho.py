"""Armado del mensaje JSON del gancho Colmena (stdlib; sin imports de orquestador)."""

import json
import os
import re
import socket
import sys

VERSION = 1
MAX_MENSAJE = 65536
TOPE_HERRAMIENTA = 4096
TOPE_PERMISO = 49152
TOPE_MENSAJE_FINAL = 8192
TIMEOUT_CONEXION = 0.2
ESPERA_DEFAULT = 125.0

EVENTOS = frozenset({
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "Notification",
    "Stop",
})

_HERRAMIENTAS = frozenset({"PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest"})
_SIN_ESPERA = frozenset({"AskUserQuestion"})
_TOPE_NOTIFICACION = 512
_CAMPOS_RECORTABLES = (
    "cwd",
    "transcript_path",
    "last_assistant_message",
    "message",
    "source",
    "error",
)
_HERRAMIENTAS_SIEMPRE = frozenset({"Bash", "Edit", "Write"})
_JSON_KW = {"ensure_ascii": False, "separators": (",", ":")}


def ruta_socket(environ: dict) -> str | None:
    base = environ.get("XDG_RUNTIME_DIR")
    if not base:
        return None
    return f"{base}/colmena/ganchos.sock"


def recortar_texto(texto: str, tope: int) -> tuple[str, bool]:
    raw = texto.encode("utf-8")
    if len(raw) <= tope:
        return texto, False
    chunk = raw[:tope]
    while chunk:
        try:
            return chunk.decode("utf-8"), True
        except UnicodeDecodeError:
            chunk = chunk[:-1]
    return "", True


def recortar_json(valor: object, tope: int) -> tuple[object, bool]:
    serializado = json.dumps(valor, ensure_ascii=False)
    if len(serializado.encode("utf-8")) <= tope:
        return valor, False
    texto, _ = recortar_texto(serializado, tope)
    return texto, True


def ids_de(entrada: dict, environ: dict) -> dict:
    colmena = environ.get("COLMENA_SESION") or None
    session = entrada.get("session_id")
    if colmena:
        return {
            "colmena": colmena,
            "herdr_pane": None,
            "herdr_tab": None,
            "herdr_workspace": None,
            "claude": session,
        }
    return {
        "colmena": None,
        "herdr_pane": environ.get("HERDR_PANE_ID"),
        "herdr_tab": environ.get("HERDR_TAB_ID"),
        "herdr_workspace": environ.get("HERDR_WORKSPACE_ID"),
        "claude": session,
    }


def _tamano_linea(mensaje: dict) -> int:
    return len((json.dumps(mensaje, **_JSON_KW) + "\n").encode("utf-8"))


def _serializar_linea(mensaje: dict) -> bytes:
    return (json.dumps(mensaje, **_JSON_KW) + "\n").encode("utf-8")


def _tope_tool_input(evento: str) -> int | None:
    if evento == "PermissionRequest":
        return TOPE_PERMISO
    if evento in _HERRAMIENTAS:
        return TOPE_HERRAMIENTA
    return None


def _encajar_en_max(mensaje: dict, tool_input_original: object) -> dict | None:
    datos = mensaje["datos"]
    recortado = bool(datos.get("recortado"))
    evento = mensaje["evento"]
    tope = _tope_tool_input(evento)

    while _tamano_linea(mensaje) > MAX_MENSAJE:
        progreso = False
        for key in _CAMPOS_RECORTABLES:
            val = datos.get(key)
            if not isinstance(val, str) or not val:
                continue
            limite = max(0, len(val.encode("utf-8")) - 512)
            nuevo, rec = recortar_texto(val, limite)
            datos[key] = nuevo
            recortado = recortado or rec
            progreso = True
            if _tamano_linea(mensaje) <= MAX_MENSAJE:
                break
        if not progreso:
            break

    if tope is not None and tool_input_original is not None:
        while _tamano_linea(mensaje) > MAX_MENSAJE:
            tope = max(0, tope - 512)
            ti, rec = recortar_json(tool_input_original, tope)
            datos["tool_input"] = ti
            recortado = recortado or rec
            if tope == 0:
                break

    if _tamano_linea(mensaje) > MAX_MENSAJE:
        if "tool_input" in datos:
            datos["tool_input"] = ""
            recortado = True
        for key in _CAMPOS_RECORTABLES:
            if key in datos:
                datos[key] = ""
        claude = mensaje.get("ids", {}).get("claude")
        if isinstance(claude, str) and claude:
            mensaje["ids"]["claude"], rec = recortar_texto(claude, 256)
            recortado = recortado or rec

    if _tamano_linea(mensaje) > MAX_MENSAJE:
        return None

    if recortado:
        datos["recortado"] = True
    else:
        datos.pop("recortado", None)
    return mensaje


def armar_mensaje(entrada: dict, environ: dict) -> dict | None:
    evento = entrada.get("hook_event_name")
    if evento not in EVENTOS:
        return None

    origen = environ.get("COLMENA_GANCHO_ORIGEN", "global")
    if origen == "global" and environ.get("COLMENA_SESION"):
        return None

    datos: dict = {}
    recortado = False
    tool_input_original = None

    for key in ("cwd", "transcript_path"):
        if key in entrada:
            datos[key] = entrada[key]

    if evento in _HERRAMIENTAS:
        for key in ("tool_name", "tool_use_id"):
            if key in entrada:
                datos[key] = entrada[key]
        if "tool_input" in entrada:
            tool_input_original = entrada["tool_input"]
            limite = TOPE_PERMISO if evento == "PermissionRequest" else TOPE_HERRAMIENTA
            ti, rec = recortar_json(tool_input_original, limite)
            datos["tool_input"] = ti
            recortado = recortado or rec
        if evento == "PostToolUseFailure":
            if "error" in entrada:
                err, rec = recortar_texto(str(entrada["error"]), _TOPE_NOTIFICACION)
                datos["error"] = err
                recortado = recortado or rec
            if isinstance(entrada.get("is_interrupt"), bool):
                datos["is_interrupt"] = entrada["is_interrupt"]
    elif evento == "SessionStart":
        if "source" in entrada:
            datos["source"] = entrada["source"]
    elif evento == "Notification":
        if "notification_type" in entrada:
            datos["notification_type"] = entrada["notification_type"]
        if "message" in entrada:
            msg, rec = recortar_texto(str(entrada["message"]), _TOPE_NOTIFICACION)
            datos["message"] = msg
            recortado = recortado or rec
    elif evento == "Stop":
        datos["stop_hook_active"] = entrada.get("stop_hook_active") is True
        datos["tiene_estado"] = bool(re.search(r"^```estado\s*$", str(entrada.get("last_assistant_message") or ""), re.M))
        if "last_assistant_message" in entrada:
            msg, rec = recortar_texto(str(entrada["last_assistant_message"]), TOPE_MENSAJE_FINAL)
            datos["last_assistant_message"] = msg
            recortado = recortado or rec

    if recortado:
        datos["recortado"] = True

    mensaje = {
        "v": VERSION,
        "evento": evento,
        "origen": origen,
        "ids": ids_de(entrada, environ),
        "datos": datos,
    }
    return _encajar_en_max(mensaje, tool_input_original)


def espera_respuesta(mensaje: dict) -> bool:
    if mensaje.get("evento") != "PermissionRequest":
        return False
    tool = mensaje.get("datos", {}).get("tool_name")
    return tool not in _SIN_ESPERA


_DENY_DESCARTAR = frozenset({"\x7f", "\u2028", "\u2029"})


def _sanea_mensaje_deny(mensaje: str) -> str:
    limpio = "".join(ch for ch in mensaje if ch >= " " and ch not in _DENY_DESCARTAR)
    limpio = limpio[:500]
    return limpio or "Rechazado desde Colmena"


def _regla_siempre_valida(regla: object) -> dict | None:
    if not isinstance(regla, dict):
        return None
    if set(regla.keys()) != {"toolName", "ruleContent"}:
        return None
    tool = regla["toolName"]
    content = regla["ruleContent"]
    if tool not in _HERRAMIENTAS_SIEMPRE:
        return None
    if not isinstance(content, str) or not content or "\n" in content or content == "*":
        return None
    return {"toolName": tool, "ruleContent": content}


def salida_de(respuesta: object) -> str | None:
    if not isinstance(respuesta, dict):
        return None
    v = respuesta.get("v")
    if type(v) is not int or v != 1:
        return None
    decision = respuesta.get("decision")
    if decision == "allow":
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            }
        }
    elif decision == "deny":
        mensaje = respuesta.get("mensaje", "")
        if not isinstance(mensaje, str):
            return None
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "deny",
                    "message": _sanea_mensaje_deny(mensaje),
                },
            }
        }
    elif decision == "siempre":
        reglas = respuesta.get("reglas")
        if not isinstance(reglas, list) or not reglas:
            return None
        validas = []
        for regla in reglas:
            ok = _regla_siempre_valida(regla)
            if ok is None:
                return None
            validas.append(ok)
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "allow",
                    "updatedPermissions": [
                        {
                            "type": "addRules",
                            "rules": validas,
                            "behavior": "allow",
                            "destination": "localSettings",
                        }
                    ],
                },
            }
        }
    else:
        return None
    return json.dumps(payload, ensure_ascii=False)


def _conectar_default(ruta: str, timeout: float):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(ruta)
    return sock


def main(stdin=None, stdout=None, environ=None, conectar=None, salir=os._exit) -> None:
    sock = None
    try:
        stdin = stdin if stdin is not None else sys.stdin
        stdout = stdout if stdout is not None else sys.stdout
        environ = environ if environ is not None else os.environ
        conectar = conectar if conectar is not None else _conectar_default

        raw = stdin.read()
        try:
            entrada = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(entrada, dict):
            return

        msg = armar_mensaje(entrada, environ)
        if msg is None:
            return

        ruta = ruta_socket(environ)
        if ruta is None:
            return

        sock = conectar(ruta, TIMEOUT_CONEXION)
        sock.settimeout(TIMEOUT_CONEXION)
        sock.sendall(_serializar_linea(msg))

        if not espera_respuesta(msg):
            return

        espera = float(environ.get("COLMENA_GANCHO_ESPERA", ESPERA_DEFAULT))
        sock.settimeout(espera)
        buf = b""
        while len(buf) < MAX_MENSAJE:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                buf = buf.split(b"\n", 1)[0] + b"\n"
                break

        if len(buf) >= MAX_MENSAJE or b"\n" not in buf:
            return

        linea = buf[:-1]
        try:
            respuesta = json.loads(linea.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        salida = salida_de(respuesta)
        if salida is None:
            return
        stdout.write(salida)
        stdout.flush()
    except BaseException:
        pass
    finally:
        if sock is not None:
            try:
                sock.close()
            except BaseException:
                pass
        salir(0)


if __name__ == "__main__":
    main()
