"""Ocultar el espacio Herdr vacío por defecto (~) en el tablero mux."""

import os

from orquestador.enchufe.modelo import Espacio, Linea, Sesion, Tablero
from orquestador.enchufe.mux import _sin_espacio_herdr_vacio

HOME = "/home/usuario-test"


def _shell(
    ses_id: str,
    line_id: str,
    esp_id: str,
    cwd: str,
    *,
    backend: str = "herdr",
    cwd_fg: str | None = None,
    programa: str = "shell",
    es_agente: bool = False,
    claude_session_id: str | None = None,
    agente: str | None = None,
    nombre_agente: str | None = None,
) -> Sesion:
    return Sesion(
        ses_id,
        line_id,
        esp_id,
        programa,  # type: ignore[arg-type]
        "idle",
        "herdr",
        claude_session_id,
        cwd,
        cwd_fg,
        "",
        None,
        backend,  # type: ignore[arg-type]
        agente=agente,
        es_agente=es_agente,
        nombre_agente=nombre_agente,
    )


def _tablero_un_espacio(
    esp_id: str,
    nombre: str,
    ses: Sesion,
    *,
    linea_enfocada: str | None = None,
    extra_espacios: tuple[Espacio, ...] = (),
    extra_lineas: tuple[Linea, ...] = (),
    extra_sesiones: tuple[Sesion, ...] = (),
) -> Tablero:
    line_id = f"{esp_id}:t1"
    esp = Espacio(esp_id, nombre, (line_id,))
    line = Linea(line_id, esp_id, nombre, (ses.id,))
    return Tablero(
        (esp,) + extra_espacios,
        (line,) + extra_lineas,
        (ses,) + extra_sesiones,
        3,
        linea_enfocada,
        ("conf-1",),
        ("caido-x",),
    )


def test_oculta_shell_herdr_sola_en_home_y_limpia_foco():
    esp_id = "w1"
    line_id = "w1:t1"
    ses = _shell("w1:p1", line_id, esp_id, HOME)
    tab = _tablero_un_espacio(esp_id, "~", ses, linea_enfocada=line_id)

    out = _sin_espacio_herdr_vacio(tab, HOME)

    assert out.espacios == ()
    assert out.lineas == ()
    assert out.sesiones == ()
    assert out.linea_enfocada is None
    assert out.revision == 3
    assert out.conflictos == ("conf-1",)
    assert out.caidos == ("caido-x",)


def test_mantiene_shell_herdr_fuera_de_home():
    ses = _shell("w1:p1", "w1:t1", "w1", "/tmp/proyecto")
    tab = _tablero_un_espacio("w1", "~", ses)

    out = _sin_espacio_herdr_vacio(tab, HOME)

    assert out == tab


def test_mantiene_claude_o_agente_en_home():
    ses_claude = _shell(
        "w1:p1",
        "w1:t1",
        "w1",
        HOME,
        programa="claude",
        claude_session_id="sid-1",
    )
    tab_claude = _tablero_un_espacio("w1", "~", ses_claude)
    assert _sin_espacio_herdr_vacio(tab_claude, HOME) == tab_claude

    ses_agente = _shell("w2:p1", "w2:t1", "w2", HOME, es_agente=True, agente="claude")
    tab_agente = _tablero_un_espacio("w2", "~", ses_agente)
    assert _sin_espacio_herdr_vacio(tab_agente, HOME) == tab_agente


def test_mantiene_dos_lineas_o_dos_sesiones_en_home():
    esp_id = "w1"
    l1, l2 = "w1:t1", "w1:t2"
    s1 = _shell("w1:p1", l1, esp_id, HOME)
    s2 = _shell("w1:p2", l2, esp_id, HOME)
    esp = Espacio(esp_id, "~", (l1, l2))
    tab_dos_lineas = Tablero(
        (esp,),
        (Linea(l1, esp_id, "a", (s1.id,)), Linea(l2, esp_id, "b", (s2.id,))),
        (s1, s2),
        0,
    )
    assert _sin_espacio_herdr_vacio(tab_dos_lineas, HOME) == tab_dos_lineas

    line_id = "w3:t1"
    s_a = _shell("w3:p1", line_id, "w3", HOME)
    s_b = _shell("w3:p2", line_id, "w3", HOME)
    tab_dos_ses = Tablero(
        (Espacio("w3", "~", (line_id,)),),
        (Linea(line_id, "w3", "~", (s_a.id, s_b.id)),),
        (s_a, s_b),
        0,
    )
    assert _sin_espacio_herdr_vacio(tab_dos_ses, HOME) == tab_dos_ses


def test_mantiene_espacio_guardian_shell_en_home():
    ses = _shell("g1:p1", "g1:t1", "g1", HOME, backend="guardian")
    tab = _tablero_un_espacio("g1", "proyecto", ses)
    assert _sin_espacio_herdr_vacio(tab, HOME) == tab


def test_no_toca_otros_espacios_del_tablero():
    vacio = _shell("w1:p1", "w1:t1", "w1", HOME)
    otro = _shell("w2:p1", "w2:t1", "w2", "/var/www")
    esp_vacio = Espacio("w1", "~", ("w1:t1",))
    esp_otro = Espacio("w2", "repo", ("w2:t1",))
    line_vacio = Linea("w1:t1", "w1", "~", ("w1:p1",))
    line_otro = Linea("w2:t1", "w2", "repo", ("w2:p1",))
    tab = Tablero((esp_vacio, esp_otro), (line_vacio, line_otro), (vacio, otro), 5)

    out = _sin_espacio_herdr_vacio(tab, HOME)

    assert out.espacios == (esp_otro,)
    assert out.lineas == (line_otro,)
    assert out.sesiones == (otro,)
    assert out.revision == 5


def test_home_con_barra_final_en_cwd():
    home = HOME
    ses = _shell("w1:p1", "w1:t1", "w1", home + os.sep)
    tab = _tablero_un_espacio("w1", "~", ses)
    out = _sin_espacio_herdr_vacio(tab, home)
    assert out.sesiones == ()
