import asyncio
import logging

import pytest

from orquestador.tareas import vigilar


async def _falla():
    raise RuntimeError("x")


async def _ok():
    return None


def test_vigilar_loguea_excepcion(caplog):
    caplog.set_level(logging.ERROR, logger="orquestador.tareas")

    async def run():
        task = asyncio.create_task(_falla())
        vigilar(task, "prueba-falla")
        await task

    with pytest.raises(RuntimeError, match="x"):
        asyncio.run(run())

    assert any("Falló la tarea de fondo prueba-falla" in r.message for r in caplog.records)
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_vigilar_cancelada_no_loguea(caplog):
    caplog.set_level(logging.ERROR, logger="orquestador.tareas")

    async def run():
        task = asyncio.create_task(asyncio.sleep(3600))
        vigilar(task, "prueba-cancel")
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert not [r for r in caplog.records if "Falló la tarea de fondo" in r.message]


def test_vigilar_exitosa_no_loguea(caplog):
    caplog.set_level(logging.ERROR, logger="orquestador.tareas")

    async def run():
        task = asyncio.create_task(_ok())
        vigilar(task, "prueba-ok")
        await task

    asyncio.run(run())
    assert not [r for r in caplog.records if "Falló la tarea de fondo" in r.message]
