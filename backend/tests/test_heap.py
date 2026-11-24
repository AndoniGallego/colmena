import asyncio

from orquestador.heap import devolver_periodicamente


def test_devuelve_la_memoria_en_cada_vuelta():
    llamadas, esperas = [], []

    async def dormir(segundos):
        esperas.append(segundos)

    asyncio.run(devolver_periodicamente(intervalo=600, trim=lambda: llamadas.append(1), sleep=dormir, vueltas=3))
    assert llamadas == [1, 1, 1]
    assert esperas == [600, 600, 600]


def test_un_error_al_devolver_no_corta_el_ciclo():
    llamadas = []

    async def dormir(_):
        pass

    def trim():
        llamadas.append(1)
        raise OSError("sin libc")

    asyncio.run(devolver_periodicamente(intervalo=1, trim=trim, sleep=dormir, vueltas=2))
    assert len(llamadas) == 2
