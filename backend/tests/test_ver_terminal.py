from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from orquestador.guardian.protocolo import VERSION
from orquestador.guardian.servidor import ServidorGuardian
from orquestador.ver_terminal import (
    _enganchar,
    _tablero_remoto,
    buscar_indice,
    filas_de_tablero,
    imprimir_listado,
    ruta_guardian_socket,
)
from orquestador.ver_terminal import _ESCAPE_SALIR
from tests.guardian.test_guardian_servidor import GuardianFalso

pytestmark = pytest.mark.unix


def test_ruta_guardian_socket():
    assert ruta_guardian_socket({"XDG_RUNTIME_DIR": "/run/u"}) == Path("/run/u/colmena-guardian/guardian.sock")
    assert ruta_guardian_socket({}) is None


def test_filas_de_tablero_sintetico():
    tab = {
        "espacios": [{"id": "g1", "nombre": "Tienda"}],
        "lineas": [{"id": "g1:l1", "espacio_id": "g1", "nombre": "API"}],
        "sesiones": [
            {
                "id": "g1:p1",
                "linea_id": "g1:l1",
                "espacio_id": "g1",
                "programa": "claude",
                "cwd": "/tmp/proyecto",
            }
        ],
    }
    filas = filas_de_tablero(tab)
    assert len(filas) == 1
    assert filas[0]["tarjeta"] == "Tienda"
    assert filas[0]["pestana"] == "API"
    assert filas[0]["tipo"] == "claude"


def test_buscar_indice_numero_y_nombre():
    filas = [{"pestana": "API", "sesion_id": "g1:p9"}]
    assert buscar_indice(filas, "1") == 0
    assert buscar_indice(filas, "API") == 0
    assert buscar_indice(filas, "g1:p9") == 0
    assert buscar_indice(filas, "nope") is None


def test_buscar_indice_id_exacto_gana_sobre_un_nombre_igual():
    filas = [{"pestana": "g1:p7", "sesion_id": "g1:p2"}, {"pestana": "otra", "sesion_id": "g1:p7"}]
    assert buscar_indice(filas, "g1:p7") == 1
    assert buscar_indice(filas, "otra") == 1


def test_buscar_indice_id_inexistente_cae_al_nombre():
    filas = [{"pestana": "g1:p7", "sesion_id": "g1:p2"}]
    assert buscar_indice(filas, "g1:p7") == 0


def test_ctrl_corchete_es_escape():
    assert _ESCAPE_SALIR == "\x1d"


def test_imprimir_listado(capsys):
    imprimir_listado(
        [
            {
                "tarjeta": "T",
                "pestana": "API",
                "tipo": "claude",
                "carpeta": "/home/usuario/proyecto",
                "sesion_id": "g1:p1",
            }
        ]
    )
    out = capsys.readouterr().out
    assert "T / API" in out and "claude" in out
    # El id es el que acepta [colmena-pestana] {"accion":"cerrar","terminal":...}.
    assert "g1:p1" in out


def test_tablero_por_socket_falso():
    g = GuardianFalso()
    tmp = Path(tempfile.mkdtemp(prefix="ver-test-", dir="/tmp"))
    ruta = tmp / "g.sock"
    srv = ServidorGuardian(g, "test", lambda: None)
    tab = {
        "revision": 1,
        "espacios": [{"id": "g1", "nombre": "Demo"}],
        "lineas": [{"id": "g1:l1", "espacio_id": "g1", "nombre": "Shell"}],
        "sesiones": [
            {
                "id": "g1:p1",
                "linea_id": "g1:l1",
                "espacio_id": "g1",
                "programa": "shell",
                "cwd": "/tmp",
            }
        ],
    }
    g.tablero = lambda: tab  # type: ignore[method-assign]

    async def run() -> dict:
        await srv.abrir(ruta)
        try:
            return await _tablero_remoto(ruta)
        finally:
            await srv.cerrar()

    try:
        data = asyncio.run(run())
    except PermissionError:
        pytest.skip("sandbox sin unix socket")
    assert data.get("revision") == 1
    filas = filas_de_tablero(data)
    assert filas[0]["sesion_id"] == "g1:p1"


class GuardianRegistro(GuardianFalso):
    def __init__(self) -> None:
        super().__init__()
        self.ops: list[tuple[str, dict]] = []

    def redimensionar(self, sesion_id: str, columnas: int, filas: int) -> None:
        self.ops.append(
            ("redimensionar", {"sesion_id": sesion_id, "columnas": columnas, "filas": filas})
        )

    def escribir(self, sesion_id: str, texto: str) -> None:
        self.ops.append(("escribir", {"sesion_id": sesion_id, "texto": texto}))


async def _enganchar_con_teclas(ruta: Path, teclas: bytes, *, capstdout: list[str] | None = None):
    import os
    import pty

    g = GuardianRegistro()
    srv = ServidorGuardian(g, "test", lambda: None)
    await srv.abrir(ruta)
    master, slave = pty.openpty()
    stdin = os.fdopen(slave, "rb", buffering=0)
    tarea = asyncio.create_task(_enganchar(ruta, "g1:p1", stdin=stdin))

    for _ in range(40):
        await asyncio.sleep(0.02)
        if any(op[0] == "escribir" for op in g.ops):
            break

    if teclas:
        os.write(master, teclas)
    if b"\x1d" not in teclas:
        await asyncio.sleep(0.05)
        os.write(master, b"\x1d")

    try:
        cod = await asyncio.wait_for(tarea, 2.0)
    finally:
        stdin.close()
        os.close(master)
        await srv.cerrar()
    return g, cod


def test_enganchar_no_redimensiona_ni_avisa_redim(capsys):
    tmp = Path(tempfile.mkdtemp(prefix="ver-attach-", dir="/tmp"))
    ruta = tmp / "g.sock"

    async def run():
        return await _enganchar_con_teclas(ruta, b"")

    try:
        g, _ = asyncio.run(run())
    except PermissionError:
        pytest.skip("sandbox sin unix socket")

    assert not any(op[0] == "redimensionar" for op in g.ops)
    err = capsys.readouterr()
    assert "tamaño local no aplicado" not in err.out


def test_enganchar_aviso_tamano_colmena(capsys):
    tmp = Path(tempfile.mkdtemp(prefix="ver-attach-", dir="/tmp"))
    ruta = tmp / "g.sock"

    async def run():
        return await _enganchar_con_teclas(ruta, b"")

    try:
        asyncio.run(run())
    except PermissionError:
        pytest.skip("sandbox sin unix socket")

    out = capsys.readouterr().out
    assert "Ctrl+] para salir" in out
    assert "Colmena (80x24)" in out


def test_enganchar_ctrl_corchete_en_bloque_solo_manda_anterior():
    tmp = Path(tempfile.mkdtemp(prefix="ver-attach-", dir="/tmp"))
    ruta = tmp / "g.sock"

    async def run():
        return await _enganchar_con_teclas(ruta, b"ab\x1dxy")

    try:
        g, _ = asyncio.run(run())
    except PermissionError:
        pytest.skip("sandbox sin unix socket")

    escritos = [op[1]["texto"] for op in g.ops if op[0] == "escribir"]
    assert escritos == ["ab"]


def test_enganchar_varias_teclas_un_solo_escribir():
    tmp = Path(tempfile.mkdtemp(prefix="ver-attach-", dir="/tmp"))
    ruta = tmp / "g.sock"

    async def run():
        return await _enganchar_con_teclas(ruta, b"abc\x1d")

    try:
        g, _ = asyncio.run(run())
    except PermissionError:
        pytest.skip("sandbox sin unix socket")

    escritos = [op[1]["texto"] for op in g.ops if op[0] == "escribir"]
    assert escritos == ["abc"]
