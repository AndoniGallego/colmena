"""Identidad del canal MCP: SO_PEERCRED + ancestros hasta el `pid_claude` de una sesión del tablero."""
import os
from pathlib import Path

import pytest

from orquestador import mcp_canal

UID = os.getuid()


def _proc(base: Path, padres: dict[int, int], comm: str = "node") -> Path:
    """/proc falso: `padres` es pid -> ppid. El comm puede traer espacios y paréntesis."""
    raiz = base / "proc"
    for pid, ppid in padres.items():
        d = raiz / str(pid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "stat").write_text(f"{pid} ({comm}) S {ppid} {pid} {pid} 0 -1 4194304 0 0 0 0\n")
    return raiz


def _ses(sid: str, pid_claude: int | None, *, modo: str | None = None, estado: str = "idle", pid: int | None = None):
    return {"id": sid, "nombre": f"Sesión {sid}", "estado": estado, "claude_session_id": f"c-{sid}",
            "pid_claude": pid_claude, "pid": pid if pid is not None else pid_claude, "modo": modo, "cwd": "/tmp"}


def test_ancestro_directo_resuelve_la_sesion(tmp_path):
    proc = _proc(tmp_path, {500: 400, 400: 300, 300: 1})
    ident, err = mcp_canal.resolver_identidad(500, [_ses("g1:p1", 400)], proc=proc, uid=UID)
    assert err is None
    assert ident == {"sesion_id": "g1:p1", "pane_id": "g1:p1", "nombre": "Sesión g1:p1",
                     "claude_session_id": "c-g1:p1", "modo": None}


def test_comm_con_espacios_y_parentesis_no_confunde_el_ppid(tmp_path):
    proc = _proc(tmp_path, {500: 400, 400: 1}, comm="a) S 999 (b")
    ident, err = mcp_canal.resolver_identidad(500, [_ses("g1:p1", 400), _ses("g2:p1", 999)], proc=proc, uid=UID)
    assert err is None and ident["sesion_id"] == "g1:p1"


def test_varios_saltos_dentro_del_tope_resuelven(tmp_path):
    padres = {1000 + i: 1000 + i + 1 for i in range(31)}
    padres[1031] = 1
    proc = _proc(tmp_path, padres)
    ident, err = mcp_canal.resolver_identidad(1000, [_ses("g1:p1", 1031)], proc=proc, uid=UID)
    assert err is None and ident["sesion_id"] == "g1:p1"


def test_mas_de_32_saltos_no_resuelve(tmp_path):
    padres = {1000 + i: 1000 + i + 1 for i in range(40)}
    padres[1040] = 1
    proc = _proc(tmp_path, padres)
    ident, err = mcp_canal.resolver_identidad(1000, [_ses("g1:p1", 1040)], proc=proc, uid=UID)
    assert ident is None and err == "sesion_no_identificada"


def test_sin_ancestro_en_el_tablero_no_resuelve(tmp_path):
    proc = _proc(tmp_path, {500: 400, 400: 1})
    ident, err = mcp_canal.resolver_identidad(500, [_ses("g1:p1", 777)], proc=proc, uid=UID)
    assert ident is None and err == "sesion_no_identificada"


def test_ciclo_no_resuelve(tmp_path):
    proc = _proc(tmp_path, {500: 400, 400: 500})
    ident, err = mcp_canal.resolver_identidad(500, [_ses("g1:p1", 777)], proc=proc, uid=UID)
    assert ident is None and err == "sesion_no_identificada"


def test_error_de_lectura_en_el_camino_no_resuelve(tmp_path):
    proc = _proc(tmp_path, {500: 400})  # 400 no existe en /proc
    ident, err = mcp_canal.resolver_identidad(500, [_ses("g1:p1", 300)], proc=proc, uid=UID)
    assert ident is None and err == "sesion_no_identificada"


def test_ancestro_de_otro_uid_corta_la_cadena(tmp_path):
    proc = _proc(tmp_path, {500: 400, 400: 1})
    ident, err = mcp_canal.resolver_identidad(500, [_ses("g1:p1", 400)], proc=proc, uid=UID + 1)
    assert ident is None and err == "sesion_no_identificada"


def test_se_compara_contra_pid_claude_y_no_contra_el_pid_de_primer_plano(tmp_path):
    # El tablero muestra como `pid` el primer plano (un Bash hijo); la identidad sale de `pid_claude`.
    proc = _proc(tmp_path, {600: 550, 550: 400, 400: 1})
    sesiones = [_ses("g1:p1", 400, pid=550)]
    ident, err = mcp_canal.resolver_identidad(600, sesiones, proc=proc, uid=UID)
    assert err is None and ident["sesion_id"] == "g1:p1"
    # Una sesión cuyo `pid` (primer plano) es ancestro pero sin `pid_claude` no resuelve.
    ident, err = mcp_canal.resolver_identidad(600, [_ses("g1:p1", None, pid=550)], proc=proc, uid=UID)
    assert ident is None and err == "sesion_no_identificada"


def test_sesion_terminada_no_resuelve(tmp_path):
    proc = _proc(tmp_path, {500: 400, 400: 1})
    ident, err = mcp_canal.resolver_identidad(500, [_ses("g1:p1", 400, estado="terminada")], proc=proc, uid=UID)
    assert ident is None and err == "sesion_no_identificada"


@pytest.mark.parametrize("modo", ["copiloto", "guia"])
def test_copiloto_y_guia_no_estan_permitidos(tmp_path, modo):
    proc = _proc(tmp_path, {500: 400, 400: 1})
    ident, err = mcp_canal.resolver_identidad(500, [_ses("g1:p1", 400, modo=modo)], proc=proc, uid=UID)
    assert ident is None and err == "sesion_no_permitida"


def test_el_ancestro_mas_cercano_gana(tmp_path):
    proc = _proc(tmp_path, {500: 400, 400: 300, 300: 1})
    ident, _ = mcp_canal.resolver_identidad(500, [_ses("lejos", 300), _ses("cerca", 400)], proc=proc, uid=UID)
    assert ident["sesion_id"] == "cerca"


def test_pid_invalido_no_resuelve(tmp_path):
    proc = _proc(tmp_path, {})
    for pid in (0, 1, -5):
        ident, err = mcp_canal.resolver_identidad(pid, [_ses("g1:p1", 1)], proc=proc, uid=UID)
        assert ident is None and err == "sesion_no_identificada"
