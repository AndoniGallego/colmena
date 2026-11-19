import asyncio
import errno
import json
import logging
import os
import shutil
import socket
import stat
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.ganchos import canal
from orquestador.state import StateStore
from tests.conftest import ORIGIN

pytestmark = pytest.mark.unix


@pytest.fixture
def corto():
    d = Path(tempfile.mkdtemp(prefix="cg", dir="/tmp"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _skip_sandbox(exc: BaseException) -> None:
    if isinstance(exc, PermissionError):
        pytest.skip(str(exc))
    if isinstance(exc, OSError) and exc.errno in (errno.EPERM, errno.EACCES):
        pytest.skip(str(exc))
    raise exc


def test_permisos_y_huerfano(corto):
    async def esc():
        dir_ = corto / "colmena"
        dir_.mkdir(mode=0o755)
        ruta = dir_ / "ganchos.sock"
        try:
            viejo = socket.socket(socket.AF_UNIX)
            viejo.bind(str(ruta))
            viejo.close()
        except (PermissionError, OSError) as e:
            _skip_sandbox(e)
        vistos = []

        async def manejar(msg, c):
            vistos.append(msg.evento)
            c.cerrar()

        s = canal.ServidorGanchos(manejar)
        try:
            await s.abrir(ruta)
        except (PermissionError, OSError) as e:
            _skip_sandbox(e)
        assert stat.S_IMODE(dir_.stat().st_mode) == 0o700
        assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
        assert all(sock.family == socket.AF_UNIX for sock in s._server.sockets)
        try:
            r, w = await asyncio.open_unix_connection(str(ruta))
        except (PermissionError, OSError) as e:
            _skip_sandbox(e)
        w.write(
            json.dumps(
                {
                    "v": 1,
                    "evento": "Stop",
                    "origen": "global",
                    "ids": {
                        "colmena": None,
                        "herdr_pane": None,
                        "herdr_tab": None,
                        "herdr_workspace": None,
                        "claude": "s1",
                    },
                    "datos": {},
                }
            ).encode()
            + b"\n"
        )
        await w.drain()
        assert await asyncio.wait_for(r.read(), 1) == b""
        assert vistos == ["Stop"]
        await s.cerrar()

    asyncio.run(esc())


def test_directorio_symlink_se_rehusa(corto):
    (corto / "real").mkdir()
    (corto / "colmena").symlink_to(corto / "real")
    with pytest.raises(PermissionError):
        canal.preparar_directorio(corto / "colmena")


def test_preparar_directorio_archivo_regular_enotdir(corto):
    archivo = corto / "no-dir"
    archivo.write_text("x")
    with pytest.raises(OSError) as ei:
        canal.preparar_directorio(archivo)
    assert ei.value.errno == errno.ENOTDIR


def test_preparar_directorio_otro_uid(corto, monkeypatch):
    dir_ = corto / "colmena"
    dir_.mkdir(mode=0o700)
    uid_real = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: uid_real + 1)
    with pytest.raises(PermissionError):
        canal.preparar_directorio(dir_)


def test_directorio_0755_propio_queda_0700(corto):
    dir_ = corto / "colmena"
    dir_.mkdir(mode=0o755)
    canal.preparar_directorio(dir_)
    assert stat.S_IMODE(dir_.stat().st_mode) == 0o700


def test_archivo_en_ruta_socket_no_se_borra(corto):
    async def esc():
        dir_ = corto / "colmena"
        dir_.mkdir(mode=0o700)
        ruta = dir_ / "ganchos.sock"
        ruta.write_text("no soy socket")
        s = canal.ServidorGanchos(lambda m, c: None)
        with pytest.raises(OSError) as ei:
            await s.abrir(ruta)
        assert ei.value.errno == errno.EEXIST
        assert ruta.is_file() and ruta.read_text() == "no soy socket"

    asyncio.run(esc())


def test_cerrar_con_cliente_inactivo_rapido(corto):
    async def esc():
        ruta = corto / "colmena" / "ganchos.sock"
        s = canal.ServidorGanchos(lambda m, c: None)
        try:
            await s.abrir(ruta)
        except (PermissionError, OSError) as e:
            _skip_sandbox(e)
        try:
            r, w = await asyncio.open_unix_connection(str(ruta))
        except (PermissionError, OSError) as e:
            _skip_sandbox(e)
        t0 = time.monotonic()
        await asyncio.wait_for(s.cerrar(), 2)
        assert time.monotonic() - t0 < 1.0
        w.close()
        await asyncio.wait_for(r.read(), 2)

    asyncio.run(esc())


def test_linea_demasiado_larga_descartada_siguiente_ok(corto):
    async def esc():
        ruta = corto / "colmena" / "ganchos.sock"
        vistos = []
        listo = asyncio.Event()

        async def manejar(msg, c):
            vistos.append(msg.evento)
            c.cerrar()
            listo.set()

        s = canal.ServidorGanchos(manejar)
        try:
            await s.abrir(ruta)
        except (PermissionError, OSError) as e:
            _skip_sandbox(e)
        base = {
            "v": 1,
            "evento": "Stop",
            "origen": "global",
            "ids": {
                "colmena": None,
                "herdr_pane": None,
                "herdr_tab": None,
                "herdr_workspace": None,
                "claude": "s1",
            },
            "datos": {},
        }
        larga = b"x" * (canal.MAX_LINEA + 2) + b"\n"
        try:
            r1, w1 = await asyncio.open_unix_connection(str(ruta))
        except (PermissionError, OSError) as e:
            _skip_sandbox(e)
        try:
            w1.write(larga)
            await w1.drain()
            w1.close()
            assert await asyncio.wait_for(r1.read(), 2) == b""
            try:
                _, w2 = await asyncio.open_unix_connection(str(ruta))
            except (PermissionError, OSError) as e:
                _skip_sandbox(e)
            w2.write(json.dumps(base).encode() + b"\n")
            await w2.drain()
            await asyncio.wait_for(listo.wait(), 2)
            assert vistos == ["Stop"] and s.descartados == 1
        finally:
            await s.cerrar()

    asyncio.run(esc())


def test_create_app_abrir_falla_sigue_sin_canal(cfg, tmp_path, handoffs, enchufe, caplog):
    bloqueado = tmp_path / "colmena"
    bloqueado.write_text("soy archivo, no directorio")
    socket_ruta = bloqueado / "ganchos.sock"
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    app = create_app(
        cfg,
        b"secret",
        StateStore(tmp_path),
        hub=hub,
        digests=digests,
        dist=tmp_path / "nodist",
        handoffs_dir=handoffs,
        uploads_dir=tmp_path / "uploads",
        enchufe=enchufe,
        ganchos_socket=socket_ruta,
    )
    with caplog.at_level(logging.ERROR):
        with TestClient(app, base_url="https://testserver", headers=ORIGIN) as c:
            assert c.get("/api/board").status_code in (401, 403)
    assert app.state.ganchos is not None
    assert app.state.ganchos._server is None
    assert any("ganchos" in r.message.lower() for r in caplog.records)
