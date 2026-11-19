"""Recarga de plugins en sesiones Claude del guardián tras actualizar el kit de trabajo."""
from __future__ import annotations

import asyncio
import errno
import json
import socket
from pathlib import Path

import logging

import pytest

from orquestador.enchufe.base import NoTomado
from orquestador.ganchos import canal
pytestmark = pytest.mark.unix

from orquestador.recarga import (
    ESPERA_MAX_S,
    RecargaService,
    ServidorRecarga,
    SesionInfo,
    TEXTO_RECARGA,
    cliente_recargar,
    ruta_socket,
    sesiones_desde_board,
)


def _svc(
    sesiones,
    *,
    mandar=None,
    marcas=None,
    clock=None,
    self_pane=None,
    protected=None,
):
    envios: list[tuple[str, str]] = []
    marcas = [] if marcas is None else marcas
    t = [1000.0] if clock is None else clock

    async def _mandar(pane, texto):
        envios.append((pane, texto))

    svc = RecargaService(
        sesiones=sesiones,
        mandar=mandar or _mandar,
        marcar_silencio=lambda: marcas.append(t[0]),
        clock=lambda: t[0],
        self_pane=self_pane or (lambda: None),
        protected_panes=protected or (lambda: set()),
    )
    return svc, envios, marcas, t


def _sesiones(*items):
    return [SesionInfo(**x) if isinstance(x, dict) else x for x in items]


def _skip_sandbox(exc: BaseException) -> None:
    if isinstance(exc, PermissionError):
        pytest.skip(str(exc))
    if isinstance(exc, OSError) and exc.errno in (errno.EPERM, errno.EACCES):
        pytest.skip(str(exc))
    raise exc


CATALOGO = _sesiones(
    {"pane_id": "g1:p1", "kind": "claude", "estado": "idle"},
    {"pane_id": "g1:p2", "kind": "claude", "estado": "done"},
    {"pane_id": "g1:p3", "kind": "claude", "estado": "working"},
    {"pane_id": "g1:p4", "kind": "claude", "estado": "blocked"},
    {"pane_id": "g1:p5", "kind": "claude", "estado": "done", "asks_user": True},
    {"pane_id": "g1:p6", "kind": "claude", "estado": "perdida"},
    {"pane_id": "w1:p1", "kind": "claude", "estado": "idle"},
    {"pane_id": "g1:p7", "kind": "shell", "estado": "idle"},
)


def test_pedir_idle_done_y_cuenta_ocupadas():
    estado = {"lista": list(CATALOGO)}

    async def run():
        svc, envios, marcas, _t = _svc(lambda: estado["lista"])
        n, m = await svc.pedir()
        assert n == 2
        assert m == 3
        await svc.esperar_envios()
        assert envios == [("g1:p1", TEXTO_RECARGA), ("g1:p2", TEXTO_RECARGA)]
        assert len(marcas) == 3  # una al inicio + una antes de cada envío

    asyncio.run(run())


def test_pendiente_pasa_a_done_se_recarga():
    estado = {
        "lista": _sesiones(
            {"pane_id": "g1:p3", "kind": "claude", "estado": "working"},
        )
    }

    async def run():
        svc, envios, marcas, _t = _svc(lambda: estado["lista"])
        assert await svc.pedir() == (0, 1)
        assert envios == []
        estado["lista"] = _sesiones({"pane_id": "g1:p3", "kind": "claude", "estado": "done"})
        await svc.al_cambio("g1:p3")
        await svc.esperar_envios()
        assert envios == [("g1:p3", TEXTO_RECARGA)]
        assert "g1:p3" not in svc.pendientes

    asyncio.run(run())


def test_pendiente_pasa_a_working_no_manda():
    estado = {
        "lista": _sesiones({"pane_id": "g1:p3", "kind": "claude", "estado": "working"}),
    }

    async def run():
        svc, envios, _, _t = _svc(lambda: estado["lista"])
        await svc.pedir()
        estado["lista"] = _sesiones({"pane_id": "g1:p3", "kind": "claude", "estado": "working"})
        await svc.al_cambio("g1:p3")
        assert envios == []

    asyncio.run(run())


def test_pendiente_vencida_se_descarta():
    estado = {
        "lista": _sesiones({"pane_id": "g1:p3", "kind": "claude", "estado": "working"}),
    }

    async def run():
        svc, envios, _, t = _svc(lambda: estado["lista"])
        await svc.pedir()
        t[0] += ESPERA_MAX_S + 1
        estado["lista"] = _sesiones({"pane_id": "g1:p3", "kind": "claude", "estado": "idle"})
        await svc.al_cambio("g1:p3")
        assert envios == []
        assert "g1:p3" not in svc.pendientes

    asyncio.run(run())


def test_pedir_idle_sacar_de_pendientes_tras_working():
    """Si quedó pendiente y pasa a idle, pedir() recarga y no deja fantasma en pendientes."""
    estado = {
        "lista": _sesiones({"pane_id": "g1:p3", "kind": "claude", "estado": "working"}),
    }

    async def run():
        svc, envios, _, _t = _svc(lambda: estado["lista"])
        assert await svc.pedir() == (0, 1)
        assert "g1:p3" in svc.pendientes
        estado["lista"] = _sesiones({"pane_id": "g1:p3", "kind": "claude", "estado": "idle"})
        assert await svc.pedir() == (1, 0)
        await svc.esperar_envios()
        assert envios == [("g1:p3", TEXTO_RECARGA)]
        assert "g1:p3" not in svc.pendientes
        await svc.al_cambio("g1:p3")
        await svc.esperar_envios()
        assert envios == [("g1:p3", TEXTO_RECARGA)]

    asyncio.run(run())


def test_pedir_dos_veces_no_duplica_pendientes():
    estado = {"lista": list(CATALOGO)}

    async def run():
        svc, _, _, _t = _svc(lambda: estado["lista"])
        await svc.pedir()
        assert len(svc.pendientes) == 3
        await svc.pedir()
        assert len(svc.pendientes) == 3

    asyncio.run(run())


def test_marca_silencio_antes_de_cada_envio():
    ultima: list[str] = []
    enviados: list[str] = []

    async def mandar(pane, texto):
        assert ultima == ["marca"], "marca de silencio debe preceder cada envío"
        ultima.clear()
        enviados.append(pane)

    def marcar():
        ultima.clear()
        ultima.append("marca")

    estado = {
        "lista": _sesiones(
            {"pane_id": "g1:p1", "kind": "claude", "estado": "idle"},
            {"pane_id": "g1:p2", "kind": "claude", "estado": "done"},
        )
    }

    async def run():
        svc = RecargaService(
            sesiones=lambda: estado["lista"],
            mandar=mandar,
            marcar_silencio=marcar,
        )
        await svc.pedir()
        assert ultima == ["marca"]  # marca al clasificar en pedir()
        await svc.esperar_envios()
        assert sorted(enviados) == ["g1:p1", "g1:p2"]

    asyncio.run(run())


async def _pedir_socket(ruta: Path, linea: bytes) -> dict:
    reader, writer = await asyncio.open_unix_connection(str(ruta))
    writer.write(linea)
    await writer.drain()
    raw = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return json.loads(raw)


def test_servidor_recarga_ok_y_op_desconocida(tmp_path):
    async def run():
        hecho = {"n": 0, "m": 0}

        async def pedir():
            hecho["n"] += 1
            return 2, 3

        srv = ServidorRecarga(pedir, verificar=lambda w: True)
        ruta = tmp_path / "colmena" / "recarga.sock"
        try:
            await srv.abrir(ruta)
        except (PermissionError, OSError) as exc:
            _skip_sandbox(exc)
        try:
            ok = await _pedir_socket(ruta, b'{"op":"recargar"}\n')
            assert ok == {"ok": True, "recargadas": 2, "esperando": 3}
            mal = await _pedir_socket(ruta, b'{"op":"otra"}\n')
            assert mal["ok"] is False and mal.get("error")
        finally:
            await srv.cerrar()

    asyncio.run(run())


def test_servidor_recarga_usa_mismo_uid_por_defecto():
    srv = ServidorRecarga(lambda: (0, 0))
    assert srv._verificar is canal.mismo_uid


def test_cliente_socket_inexistente(tmp_path):
    ok, data = cliente_recargar(tmp_path / "no.sock")
    assert ok is False and data.get("offline") is True


def test_cli_sin_socket(capsys, monkeypatch):
    from orquestador.cli import recargar_sesiones

    monkeypatch.setattr("orquestador.recarga.ruta_socket", lambda _env=None: Path("/no/existe/recarga.sock"))
    assert recargar_sesiones() == 0
    assert "no está andando" in capsys.readouterr().out


def test_cli_con_servidor(tmp_path, capsys, monkeypatch):
    from orquestador.cli import recargar_sesiones

    async def main():
        async def pedir():
            return 4, 1

        srv = ServidorRecarga(pedir, verificar=lambda w: True)
        ruta = tmp_path / "colmena" / "recarga.sock"
        try:
            await srv.abrir(ruta)
        except (PermissionError, OSError) as exc:
            _skip_sandbox(exc)
        monkeypatch.setattr("orquestador.recarga.ruta_socket", lambda _env=None: ruta)
        try:
            return await asyncio.to_thread(recargar_sesiones)
        finally:
            await srv.cerrar()

    code = asyncio.run(main())
    out = capsys.readouterr().out
    assert code == 0
    assert "4 sesiones recargadas" in out and "1 se recargan cuando terminen" in out


def test_ruta_socket():
    assert ruta_socket({"XDG_RUNTIME_DIR": "/run/user/1000"}) == Path("/run/user/1000/colmena/recarga.sock")
    assert ruta_socket({}) is None


def test_al_cambio_concurrente_un_solo_envio():
    estado = {
        "lista": _sesiones({"pane_id": "g1:p1", "kind": "claude", "estado": "working"}),
    }
    n_envios = [0]

    async def mandar(pane, texto):
        n_envios[0] += 1
        await asyncio.sleep(0)

    async def run():
        svc, _, _, _t = _svc(lambda: estado["lista"], mandar=mandar)
        await svc.pedir()
        estado["lista"] = _sesiones({"pane_id": "g1:p1", "kind": "claude", "estado": "idle"})
        await asyncio.gather(svc.al_cambio("g1:p1"), svc.al_cambio(None))
        await svc.esperar_envios()
        assert n_envios[0] == 1

    asyncio.run(run())


def test_pedir_concurrente_al_cambio_un_solo_envio():
    estado = {
        "lista": _sesiones({"pane_id": "g1:p1", "kind": "claude", "estado": "working"}),
    }
    n_envios = [0]

    async def mandar(pane, texto):
        n_envios[0] += 1
        await asyncio.sleep(0)

    async def run():
        svc, _, _, _t = _svc(lambda: estado["lista"], mandar=mandar)
        await svc.pedir()
        estado["lista"] = _sesiones({"pane_id": "g1:p1", "kind": "claude", "estado": "idle"})
        await asyncio.gather(svc.pedir(), svc.al_cambio("g1:p1"))
        await svc.esperar_envios()
        assert n_envios[0] == 1

    asyncio.run(run())


def test_board_centinela_no_entra_en_recarga():
    board = {
        "centinela": {
            "pane_id": "g1:centinela",
            "kind": "claude",
            "status": "idle",
        },
        "workspaces": [],
    }
    estado = {"lista": sesiones_desde_board(board)}
    assert estado["lista"] == []

    async def run():
        svc, envios, _, _t = _svc(lambda: estado["lista"])
        await svc.pedir()
        assert envios == []

    asyncio.run(run())


def test_no_manda_a_centinela_ni_protegida():
    estado = {
        "lista": _sesiones(
            {"pane_id": "g1:p1", "kind": "claude", "estado": "idle"},
            {"pane_id": "g1:p9", "kind": "claude", "estado": "idle"},
        )
    }

    async def run():
        svc, envios, _, _t = _svc(
            lambda: estado["lista"],
            self_pane=lambda: "g1:p9",
            protected=lambda: {"g1:p9"},
        )
        await svc.pedir()
        await svc.esperar_envios()
        assert envios == [("g1:p1", TEXTO_RECARGA)]

    asyncio.run(run())


def test_no_tomado_cuenta_como_recargada(caplog):
    estado = {
        "lista": _sesiones({"pane_id": "g1:p1", "kind": "claude", "estado": "idle"}),
    }
    envios: list[tuple[str, str]] = []

    async def mandar(pane, texto):
        envios.append((pane, texto))
        raise NoTomado("el prompt quedó en la entrada")

    async def run():
        svc, _, _, _t = _svc(lambda: estado["lista"], mandar=mandar)
        with caplog.at_level(logging.INFO):
            n, m = await svc.pedir()
            assert n == 1 and m == 0
            await svc.esperar_envios()
        assert envios == [("g1:p1", TEXTO_RECARGA)]
        assert not any(r.levelno >= logging.ERROR for r in caplog.records)
        assert any("sin confirmación de toma" in r.message for r in caplog.records)

    asyncio.run(run())


def test_pedir_responde_antes_de_mandar_lento():
    estado = {
        "lista": _sesiones(
            {"pane_id": "g1:p1", "kind": "claude", "estado": "idle"},
            {"pane_id": "g1:p2", "kind": "claude", "estado": "done"},
        )
    }
    bloqueo = asyncio.Event()
    envios: list[str] = []

    async def mandar(pane, _texto):
        await bloqueo.wait()
        envios.append(pane)

    async def run():
        svc = RecargaService(
            sesiones=lambda: estado["lista"],
            mandar=mandar,
            marcar_silencio=lambda: None,
        )
        n, m = await svc.pedir()
        assert n == 2 and m == 0
        assert envios == []
        bloqueo.set()
        await svc.esperar_envios()
        assert sorted(envios) == ["g1:p1", "g1:p2"]

    asyncio.run(run())


def test_dos_pedir_no_duplica_envio_mientras_lento():
    estado = {
        "lista": _sesiones({"pane_id": "g1:p1", "kind": "claude", "estado": "idle"}),
    }
    bloqueo = asyncio.Event()
    envios: list[str] = []

    async def mandar(pane, _texto):
        await bloqueo.wait()
        envios.append(pane)

    async def run():
        svc = RecargaService(
            sesiones=lambda: estado["lista"],
            mandar=mandar,
            marcar_silencio=lambda: None,
        )
        n1, _ = await svc.pedir()
        n2, _ = await svc.pedir()
        assert n1 == 1 and n2 == 0
        bloqueo.set()
        await svc.esperar_envios()
        assert envios == ["g1:p1"]

    asyncio.run(run())
