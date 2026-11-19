import asyncio
import logging

log = logging.getLogger("orquestador.tareas")


def vigilar(task: asyncio.Task, nombre: str) -> asyncio.Task:
    def _done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            log.error("Falló la tarea de fondo %s", nombre, exc_info=exc)

    task.add_done_callback(_done)
    return task
