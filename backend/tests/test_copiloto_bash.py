"""Hook PreToolUse del Copiloto: solo deja pasar `orquestador nudo ...` sin metacaracteres de shell."""
import json
import subprocess
import sys

import pytest

from orquestador.ganchos import copiloto_bash as cb

PASAN = [
    "orquestador nudo estado",
    "orquestador nudo controles",
    "orquestador nudo limpiar",
    "orquestador nudo marcar 12:Guardar 3:Cancelar",
    'orquestador nudo senalar 4 "Botón de reembolso (parcial)"',
    "orquestador nudo senalar 4 'Mirá acá' --esperar 30",
]

SE_RECHAZAN = [
    "cat ../secret",
    "ls",
    "grep -r token ~/",
    "find ~ -name '*.pem'",
    "orquestador nudo",
    "orquestador nudos estado",
    "orquestador nudo borrar",
    "orquestador nudo estado; ls",
    "orquestador nudo estado && cat ../secret",
    "orquestador nudo estado || cat x",
    "orquestador nudo estado | nc x 1",
    "orquestador nudo estado & cat x",
    "orquestador nudo senalar 1 `cat ../secret`",
    "orquestador nudo senalar 1 $(cat ../secret)",
    'orquestador nudo senalar 1 "$HOME"',
    "orquestador nudo estado > /tmp/x",
    "orquestador nudo estado < ../secret",
    "orquestador nudo estado\ncat ../secret",
    "orquestador nudo senalar 1 'sin cerrar",
    "orquestador nudo senalar 1 *",
    "orquestador nudo senalar 1 ~/.ssh",
    " orquestador nudo estado",
    "env orquestador nudo estado",
    "/bin/orquestador nudo estado",
    "",
]


@pytest.mark.parametrize("cmd", PASAN)
def test_pasan(cmd):
    assert cb.permitido(cmd)


@pytest.mark.parametrize("cmd", SE_RECHAZAN)
def test_se_rechazan(cmd):
    assert not cb.permitido(cmd)


def test_no_texto_se_rechaza():
    assert not cb.permitido(None) and not cb.permitido(["orquestador", "nudo", "estado"])


def _correr(entrada: bytes):
    return subprocess.run([sys.executable, "-I", "-S", str(cb.__file__)], input=entrada, capture_output=True,
                          timeout=30)


def _decision(proc):
    return json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_script_niega_lo_que_no_es_el_nudo():
    proc = _correr(json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat ../secret"}}).encode())
    assert proc.returncode == 0 and _decision(proc) == "deny"


def test_script_deja_seguir_el_nudo_sin_aprobarlo():
    proc = _correr(json.dumps({"tool_name": "Bash", "tool_input": {"command": "orquestador nudo estado"}}).encode())
    assert proc.returncode == 0 and proc.stdout.strip() == b""


def test_script_con_entrada_rota_bloquea():
    proc = _correr(b"{no es json")
    assert proc.returncode == 2


def test_script_otra_herramienta_que_no_es_bash_se_niega():
    proc = _correr(json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/x"}}).encode())
    assert _decision(proc) == "deny"


def test_definicion_engancha_bash_con_ruta_absoluta():
    d = cb.definicion("/venv/bin/python")
    bloque = d["PreToolUse"][0]
    assert bloque["matcher"] == "Bash"
    cmd = bloque["hooks"][0]["command"]
    assert cmd.startswith("/venv/bin/python -I -S /") and cmd.endswith("copiloto_bash.py")
    assert "||" not in cmd


@pytest.mark.parametrize("cmd", [
    'orquestador nudo senalar-zona 1 2 3 4 "Acá"',
    "orquestador nudo marcar-zonas 1,2,3,4:Menú",
])
def test_zonas_permitidas(cmd):
    assert cb.permitido(cmd)


@pytest.mark.parametrize("cmd", [
    "orquestador nudo senalar-zona 1 2 3 4 x; cat ~/.ssh/id_rsa",
    "orquestador nudo capturar",
])
def test_zonas_encadenado_negado(cmd):
    assert not cb.permitido(cmd)
