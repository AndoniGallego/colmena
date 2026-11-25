"""`pid_claude` y `modo` en el tablero del guardián, y compatibilidad del cliente con guardianes viejos."""
import os
from pathlib import Path

from orquestador.enchufe.guardian import _tablero_de_res
from orquestador.guardian.lanzador import AjustesGuardian, escribir_hooks
from orquestador.guardian.nucleo import Guardian
from orquestador.guardian.registro import Registro


class _ProcFalso:
    def __init__(self, pid: int, fp: int | None):
        self.pid = pid
        self.vivo = True
        self._fp = fp

    def primer_plano(self) -> dict:
        return {"pid": self._fp, "cwd": "/tmp"} if self._fp else {}


def _guardian(tmp_path: Path) -> tuple[Guardian, Registro]:
    reg = Registro(tmp_path / "registro.json")
    ajustes = AjustesGuardian(claude_bin="/bin/true", shell="/bin/sh", path=os.environ["PATH"], columnas=80, filas=24)
    g = Guardian(reg, ajustes, escribir_hooks(tmp_path / "settings", 130), entorno={}, cwd_confiable=lambda c: True)
    return g, reg


def _sesion(g: Guardian, reg: Registro, programa: str, proc: _ProcFalso | None, modo: str | None = None) -> str:
    esp = reg.nuevo_espacio("e", "/tmp")
    lin = reg.nueva_linea(esp.id, "l")
    ses = reg.nueva_sesion(lin.id, "n", "/tmp", programa, None)
    if modo:
        reg.actualizar_sesion(ses.id, modo_permisos=modo)
    rt = g._nueva_runtime(reg.sesiones[ses.id])
    rt.proceso = proc
    return ses.id


def _fila(g: Guardian, sid: str) -> dict:
    return next(s for s in g.tablero()["sesiones"] if s["id"] == sid)


def test_pid_claude_es_el_proceso_lanzado_aunque_haya_primer_plano(tmp_path):
    g, reg = _guardian(tmp_path)
    sid = _sesion(g, reg, "claude", _ProcFalso(400, fp=550))
    fila = _fila(g, sid)
    assert fila["pid"] == 550
    assert fila["pid_claude"] == 400


def test_pid_claude_sin_primer_plano_coincide_con_pid(tmp_path):
    g, reg = _guardian(tmp_path)
    sid = _sesion(g, reg, "claude", _ProcFalso(400, fp=None))
    fila = _fila(g, sid)
    assert fila["pid"] == 400 and fila["pid_claude"] == 400


def test_shell_y_sesion_sin_proceso_no_tienen_pid_claude(tmp_path):
    g, reg = _guardian(tmp_path)
    shell = _sesion(g, reg, "shell", _ProcFalso(401, fp=None))
    muerta = _sesion(g, reg, "claude", None)
    assert _fila(g, shell)["pid_claude"] is None
    assert _fila(g, muerta)["pid_claude"] is None


def test_tablero_expone_el_modo_interno(tmp_path):
    g, reg = _guardian(tmp_path)
    sid = _sesion(g, reg, "claude", _ProcFalso(402, fp=None), modo="copiloto")
    normal = _sesion(g, reg, "claude", _ProcFalso(403, fp=None))
    assert _fila(g, sid)["modo"] == "copiloto"
    assert _fila(g, normal)["modo"] is None


def _res(**extra) -> dict:
    ses = {"id": "g1:p2", "linea_id": "g1:t1", "espacio_id": "g1", "programa": "claude", "estado": "idle",
           "claude_session_id": None, "cwd": "/tmp", "titulo": "", "pid": 5, **extra}
    return {"espacios": [], "lineas": [], "sesiones": [ses]}


def test_cliente_lee_pid_claude_y_modo_si_vienen():
    s = _tablero_de_res(_res(pid_claude=400, modo="guia"), None).sesiones[0]
    assert s.pid_claude == 400 and s.modo == "guia"


def test_cliente_tolera_un_guardian_viejo_sin_los_campos_nuevos():
    s = _tablero_de_res(_res(), None).sesiones[0]
    assert s.pid_claude is None and s.modo is None
    s = _tablero_de_res(_res(pid_claude="400", modo=7), None).sesiones[0]
    assert s.pid_claude is None and s.modo is None
    s = _tablero_de_res(_res(pid_claude=True), None).sesiones[0]
    assert s.pid_claude is None
