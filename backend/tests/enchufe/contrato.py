import asyncio

import pytest
from orquestador.enchufe.base import NoDisponible, NoExiste, NoTomado, Tiempo


async def caso_ids_intactos(a):
    t = await a.t.tablero()
    assert {s.id for s in t.sesiones} == {"w1:p1", "w2:p1", "w2:p9"}
    assert {l.id for l in t.lineas} == {"w1:t1", "w2:t1", "w2:t2"} and {e.id for e in t.espacios} == {"w1", "w2"}


async def caso_crear_linea_y_leer(a):
    c = await a.t.crear_linea("w1", "nueva", "/tmp")
    assert c.sesion_id in {s.id for s in (await a.t.tablero()).sesiones}
    assert isinstance(await a.t.leer(c.sesion_id), str)


async def caso_crear_espacio(a):
    c = await a.t.crear_espacio("Nuevo", "/tmp")
    assert c.espacio_id in {e.id for e in (await a.t.tablero()).espacios}


async def caso_prompt_confirmado(a):
    toma = await a.t.mandar_prompt("w1:p1", "hola")
    assert toma.tomado
    assert toma.via == "herdr"


async def caso_prompt_no_tomado(a):
    a.no_tomar("w1:p1")
    with pytest.raises(NoTomado):
        await a.t.mandar_prompt("w1:p1", "hola")


async def caso_interrumpir(a):
    await a.t.interrumpir("w1:p1")


async def caso_cerrar_linea(a):
    await a.t.cerrar("w2:t1")
    assert "w2:t1" not in {l.id for l in (await a.t.tablero()).lineas}


async def caso_cerrar_sesion(a):
    await a.t.cerrar("w2:p1")
    t = await a.t.tablero()
    assert "w2:p1" not in {s.id for s in t.sesiones}
    # El último panel se lleva su pestaña, como en herdr.
    assert "w2:t1" not in {l.id for l in t.lineas}
    assert "w2:p9" in {s.id for s in t.sesiones}
    with pytest.raises(NoExiste):
        await a.t.cerrar("w9:p9")


async def caso_no_existe(a):
    with pytest.raises(NoExiste):
        await a.t.cerrar("w9:t9")
    with pytest.raises(NoExiste):
        await a.t.mandar_prompt("w9:p9", "x")


async def caso_tiempo(a):
    a.vencer("w1:p1")
    with pytest.raises(Tiempo):
        await a.t.esperar("w1:p1", frozenset({"idle", "done"}), 1.0)


async def caso_tecla_invalida(a):
    with pytest.raises(ValueError):
        await a.t.teclas("w1:p1", ["f5"])


async def caso_teclas_vacio(a):
    with pytest.raises(ValueError):
        await a.t.teclas("w1:p1", [])


async def caso_arrancar_claude(a):
    await a.t.arrancar_claude("w1:p1", "claude")
    with pytest.raises(NoExiste):
        await a.t.arrancar_claude("w9:p9", "claude")
    with pytest.raises(NoDisponible, match="retoma con resume no disponible en adaptador herdr"):
        await a.t.arrancar_claude("w1:p1", "claude", resume="sess-1")


async def caso_renombrar_linea(a):
    await a.t.renombrar("w1:t1", "renombrada")
    with pytest.raises(NoExiste):
        await a.t.renombrar("w9:t9", "x")


async def caso_enfocar_linea(a):
    await a.t.enfocar("w1:t1")
    with pytest.raises(NoExiste):
        await a.t.enfocar("w9:t9")


async def caso_caido_y_volvio(a):
    it = a.t.suscribir()
    a.caer()
    with pytest.raises(NoDisponible):
        await a.t.tablero()
    assert await _hasta(it, "caido")
    a.volver()
    await a.t.tablero()
    assert await _hasta(it, "volvio")
    await it.aclose()


async def caso_suscribir_estando_caido(a):
    a.caer()
    it = a.t.suscribir()
    with pytest.raises(NoDisponible):
        await a.t.tablero()
    assert await _hasta(it, "caido")
    await it.aclose()


async def _hasta(it, tipo):
    while True:
        ev = await asyncio.wait_for(it.__anext__(), 1)
        if ev.tipo == tipo:
            return ev
