import asyncio
import errno
import json
import os
import shutil
import socket
import stat
import tempfile
from pathlib import Path

import pytest

from orquestador.guardian.servidor import ServidorGuardian
from tests.guardian.test_guardian_servidor import GuardianFalso

pytestmark = pytest.mark.unix


def _skip_sandbox(exc: BaseException) -> None:
    if isinstance(exc, PermissionError):
        pytest.skip(str(exc))
    if isinstance(exc, OSError) and exc.errno in (errno.EPERM, errno.EACCES):
        pytest.skip(str(exc))
    raise exc


def test_socket_hola():
    g = GuardianFalso()
    tmp = Path(tempfile.mkdtemp(prefix="colmena-guardian-test-", dir="/tmp"))
    ruta = tmp / "guardian.sock"
    srv = ServidorGuardian(g, "test", lambda: None)

    async def run():
        try:
            await srv.abrir(ruta)
        except (PermissionError, OSError) as exc:
            _skip_sandbox(exc)
        assert stat.S_IMODE(tmp.stat().st_mode) == 0o700
        assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
        try:
            reader, writer = await asyncio.open_unix_connection(str(ruta))
        except (PermissionError, OSError) as exc:
            _skip_sandbox(exc)
        try:
            linea = json.dumps({"id": 1, "op": "hola", "args": {}}) + "\n"
            writer.write(linea.encode())
            await writer.drain()
            resp = await reader.readline()
            datos = json.loads(resp)
            assert datos["ok"] is True
            assert datos["res"]["guardian"] == "test"
        finally:
            writer.close()
            await writer.wait_closed()
        await srv.cerrar()

    try:
        asyncio.run(run())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
