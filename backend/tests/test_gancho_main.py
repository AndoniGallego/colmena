import ast
import io
import json
import subprocess
from pathlib import Path

import pytest

from orquestador.ganchos import colmena_gancho as g

PR = {
    "hook_event_name": "PermissionRequest",
    "session_id": "s1",
    "tool_name": "Bash",
    "tool_use_id": "t1",
    "tool_input": {"command": "touch a"},
    "cwd": "/tmp",
}
ENV = {"XDG_RUNTIME_DIR": "/run/x", "COLMENA_GANCHO_ORIGEN": "global"}
ALLOW = {
    "hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": {"behavior": "allow"},
    }
}


class Salida(Exception):
    pass


def salir(code):
    raise Salida(code)


class Sock:
    def __init__(self, respuesta=b"", error=None):
        self.respuesta, self.error, self.enviado, self.esperas = respuesta, error, b"", []

    def settimeout(self, t):
        self.esperas.append(t)

    def sendall(self, b):
        self.enviado += b

    def recv(self, n):
        if self.error:
            raise self.error
        out, self.respuesta = self.respuesta[:n], self.respuesta[n:]
        return out

    def close(self):
        pass


def correr(entrada, sock=None, conectar_error=None, env=ENV, stdout=None, conectar=None):
    out = stdout or io.StringIO()

    def _conectar(ruta, timeout):
        if conectar_error:
            raise conectar_error
        return sock

    with pytest.raises(Salida) as e:
        g.main(
            stdin=io.StringIO(entrada if isinstance(entrada, str) else json.dumps(entrada)),
            stdout=out,
            environ=env,
            conectar=conectar or _conectar,
            salir=salir,
        )
    assert e.value.args == (0,)
    return out.getvalue()


@pytest.mark.parametrize(
    "caso",
    [
        dict(conectar_error=FileNotFoundError()),
        dict(conectar_error=ConnectionRefusedError()),
        dict(sock=Sock(error=TimeoutError())),
        dict(sock=Sock(b"")),
        dict(sock=Sock(b"basura\n")),
        dict(sock=Sock(b"{}\n")),
        dict(sock=Sock(b'{"v":1,"decision":"maybe"}\n')),
        dict(sock=Sock(b'{"v":2,"decision":"allow"}\n')),
    ],
)
def test_fail_open(caso):
    assert correr(PR, **caso) == ""


@pytest.mark.parametrize("respuesta", [b'{"v":1,"decision":"allow"', b"\xff\xfe\n", b"x" * 70000])
def test_respuestas_rotas_no_imprimen(respuesta):
    assert correr(PR, sock=Sock(respuesta)) == ""


@pytest.mark.parametrize("entrada", ["", "no json", "[]", "null"])
def test_stdin_invalido(entrada):
    assert correr(entrada, sock=Sock(b'{"v":1,"decision":"allow"}\n')) == ""


def test_excepcion_en_cada_etapa_sale_0(monkeypatch):
    for nombre in ("armar_mensaje", "ruta_socket", "salida_de"):
        with monkeypatch.context() as mp:
            mp.setattr(g, nombre, lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
            assert correr(PR, sock=Sock(b'{"v":1,"decision":"allow"}\n')) == ""


def test_broken_pipe_en_stdout():
    class Rota(io.StringIO):
        def write(self, s):
            raise BrokenPipeError()

    correr(PR, sock=Sock(b'{"v":1,"decision":"allow"}\n'), stdout=Rota())


def test_salidas_exactas():
    assert json.loads(g.salida_de({"v": 1, "decision": "allow"})) == ALLOW
    assert json.loads(g.salida_de({"v": 1, "decision": "deny", "mensaje": "no\x07 así"})) == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny", "message": "no así"},
        }
    }
    assert (
        json.loads(g.salida_de({"v": 1, "decision": "deny", "mensaje": ""}))["hookSpecificOutput"]["decision"][
            "message"
        ]
        == "Rechazado desde Colmena"
    )
    assert (
        len(
            json.loads(g.salida_de({"v": 1, "decision": "deny", "mensaje": "m" * 900}))["hookSpecificOutput"][
                "decision"
            ]["message"]
        )
        == 500
    )
    assert json.loads(
        g.salida_de(
            {
                "v": 1,
                "decision": "siempre",
                "reglas": [{"toolName": "Bash", "ruleContent": "touch:*"}],
            }
        )
    ) == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": "allow",
                "updatedPermissions": [
                    {
                        "type": "addRules",
                        "rules": [{"toolName": "Bash", "ruleContent": "touch:*"}],
                        "behavior": "allow",
                        "destination": "localSettings",
                    }
                ],
            },
        }
    }


@pytest.mark.parametrize(
    "reglas",
    [
        [],
        [{"toolName": "Bash", "ruleContent": "*"}],
        [{"toolName": "Bash"}],
        [{"toolName": "Bash", "ruleContent": "a\nb"}],
        [{"type": "setMode", "mode": "acceptEdits"}],
        [{"toolName": "Bash", "ruleContent": "ls:*", "extra": 1}],
        "x",
    ],
)
def test_siempre_con_reglas_invalidas_no_imprime(reglas):
    assert g.salida_de({"v": 1, "decision": "siempre", "reglas": reglas}) is None


def test_no_decisorios_no_esperan_y_pr_si():
    pre = Sock(b'{"v":1,"decision":"allow"}\n')
    assert correr({**PR, "hook_event_name": "PreToolUse"}, sock=pre) == "" and pre.esperas == [g.TIMEOUT_CONEXION]
    ask = Sock(b'{"v":1,"decision":"allow"}\n')
    assert correr({**PR, "tool_name": "AskUserQuestion"}, sock=ask) == ""
    pr = Sock(b'{"v":1,"decision":"allow"}\n')
    assert json.loads(correr(PR, sock=pr)) == ALLOW
    assert pr.esperas[-1] == g.ESPERA_DEFAULT and pr.enviado.endswith(b"\n")


def test_espera_de_env():
    pr = Sock(b'{"v":1,"decision":"allow"}\n')
    correr(PR, sock=pr, env={**ENV, "COLMENA_GANCHO_ESPERA": "135"})
    assert pr.esperas[-1] == 135.0


def test_sin_xdg_no_conecta():
    llamadas = []

    def conectar(ruta, timeout):
        llamadas.append((ruta, timeout))
        raise AssertionError("no debía conectar")

    out = io.StringIO()
    with pytest.raises(Salida) as e:
        g.main(
            stdin=io.StringIO(json.dumps(PR)),
            stdout=out,
            environ={},
            conectar=conectar,
            salir=salir,
        )
    assert e.value.args == (0,)
    assert out.getvalue() == ""
    assert llamadas == []


def test_solo_stdlib():
    arbol = ast.parse(Path(g.__file__).read_text())
    mods = {a.name.split(".")[0] for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    mods |= {
        n.module.split(".")[0]
        for n in ast.walk(arbol)
        if isinstance(n, ast.ImportFrom) and n.module
    }
    assert mods <= {"json", "os", "re", "socket", "sys"}


def test_main_no_conecta_si_mensaje_no_entra():
    llamadas = []

    def conectar(ruta, timeout):
        llamadas.append((ruta, timeout))
        return Sock(b"")

    entrada = {
        "hook_event_name": "Stop",
        "session_id": "s1",
        "cwd": "/tmp",
    }
    env = {
        "XDG_RUNTIME_DIR": "/run/x",
        "COLMENA_GANCHO_ORIGEN": "global",
        "HERDR_PANE_ID": "w" * 80_000,
        "HERDR_TAB_ID": "t" * 80_000,
        "HERDR_WORKSPACE_ID": "x" * 80_000,
    }
    out = io.StringIO()
    with pytest.raises(Salida) as e:
        g.main(
            stdin=io.StringIO(json.dumps(entrada)),
            stdout=out,
            environ=env,
            conectar=conectar,
            salir=salir,
        )
    assert e.value.args == (0,)
    assert out.getvalue() == ""
    assert llamadas == []


def test_enviado_respeta_max_mensaje_y_nueva_linea():
    casos = [
        PR,
        {**PR, "hook_event_name": "PreToolUse"},
        {
            **PR,
            "tool_input": {"command": ('\\"' * 24000)[:48000]},
        },
    ]
    for entrada in casos:
        sock = Sock(b'{"v":1,"decision":"allow"}\n')
        correr(entrada, sock=sock)
        assert len(sock.enviado) <= g.MAX_MENSAJE
        assert sock.enviado.endswith(b"\n")


@pytest.mark.parametrize("respuesta", [b'{"v":true,"decision":"allow"}\n', b'{"v":1.0,"decision":"allow"}\n'])
def test_v_debe_ser_entero_exacto(respuesta):
    assert correr(PR, sock=Sock(respuesta)) == ""


def test_deny_descarta_7f_y_separadores_unicode():
    raw = "a\x7fb\u2028c\u2029d"
    salida = g.salida_de({"v": 1, "decision": "deny", "mensaje": raw})
    msg = json.loads(salida)["hookSpecificOutput"]["decision"]["message"]
    assert msg == "abcd"
    assert "\x7f" not in msg and "\u2028" not in msg and "\u2029" not in msg


def test_arranca_con_I_S_sin_socket(tmp_path):
    r = subprocess.run(
        ["python3", "-I", "-S", g.__file__],
        input=json.dumps(PR).encode(),
        env={"XDG_RUNTIME_DIR": str(tmp_path)},
        capture_output=True,
        timeout=10,
    )
    assert (r.returncode, r.stdout) == (0, b"")
