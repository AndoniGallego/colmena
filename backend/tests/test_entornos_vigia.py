import asyncio
import json

import pytest

from orquestador.entornos_vigia import VigiaEntornos


def linea_evento(
    accion,
    cid="cid1",
    proyecto="hybrid-search",
    servicio="hs-api",
    exit_code=None,
    sin_compose=False,
):
    attrs = {"name": f"{proyecto}-{servicio}-1", "com.docker.compose.service": servicio}
    if not sin_compose:
        attrs["com.docker.compose.project"] = proyecto
    if exit_code is not None:
        attrs["exitCode"] = str(exit_code)
    return json.dumps(
        {"Action": accion, "status": accion, "id": cid, "Actor": {"ID": cid, "Attributes": attrs}},
    )


class Avisos:
    def __init__(self):
        self.items = []

    async def __call__(self, titulo, cuerpo, ref):
        self.items.append({"titulo": titulo, "cuerpo": cuerpo, "ref": ref})
        return 1


class Reloj:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def vigia(avisar, now=None, abrir=None, sleep=None):
    return VigiaEntornos(
        "/usr/bin/docker",
        avisar,
        abrir=abrir,
        sleep=sleep or asyncio.sleep,
        now=now or Reloj(),
    )


async def procesar_varias(v, lineas):
    for ln in lineas:
        await v.procesar(ln)


def test_die_sin_stop_avisa_con_codigo():
    avisos = Avisos()
    v = vigia(avisos)
    asyncio.run(v.procesar(linea_evento("die", exit_code=137)))
    assert len(avisos.items) == 1
    assert avisos.items[0]["titulo"] == "Entornos"
    assert avisos.items[0]["cuerpo"] == "Se cayó hs-api (hybrid-search), código 137"
    assert avisos.items[0]["ref"] == "hybrid-search:hs-api"


def test_stop_luego_die_sin_aviso():
    avisos = Avisos()
    reloj = Reloj()
    v = vigia(avisos, now=reloj)
    asyncio.run(procesar_varias(v, [linea_evento("stop"), linea_evento("die")]))
    assert avisos.items == []


def test_kill_hace_40s_luego_die_avisa():
    avisos = Avisos()
    reloj = Reloj()
    v = vigia(avisos, now=reloj)
    asyncio.run(v.procesar(linea_evento("kill")))
    reloj.t = 40
    asyncio.run(v.procesar(linea_evento("die")))
    assert len(avisos.items) == 1
    assert avisos.items[0]["cuerpo"] == "Se cayó hs-api (hybrid-search)"


def test_dos_die_mismo_servicio_100s_un_aviso():
    avisos = Avisos()
    reloj = Reloj()
    v = vigia(avisos, now=reloj)
    asyncio.run(v.procesar(linea_evento("die")))
    reloj.t = 100
    asyncio.run(v.procesar(linea_evento("die")))
    assert len(avisos.items) == 1


def test_dos_die_mismo_servicio_700s_dos_avisos():
    avisos = Avisos()
    reloj = Reloj()
    v = vigia(avisos, now=reloj)
    asyncio.run(v.procesar(linea_evento("die")))
    reloj.t = 700
    asyncio.run(v.procesar(linea_evento("die")))
    assert len(avisos.items) == 2


def test_health_unhealthy_avisa():
    avisos = Avisos()
    v = vigia(avisos)
    asyncio.run(v.procesar(linea_evento("health_status: unhealthy")))
    assert len(avisos.items) == 1
    assert avisos.items[0]["cuerpo"] == "hs-api está enfermo (hybrid-search)"


def test_sin_etiqueta_compose_ignora():
    avisos = Avisos()
    v = vigia(avisos)
    asyncio.run(v.procesar(linea_evento("die", sin_compose=True)))
    assert avisos.items == []


def test_linea_basura_no_tira():
    avisos = Avisos()
    v = vigia(avisos)
    asyncio.run(v.procesar("no es json {{{"))
    assert avisos.items == []


def test_run_docker_bin_none_retorna():
    avisos = Avisos()
    v = VigiaEntornos(None, avisos)
    asyncio.run(v.run())


def test_run_reconexion_backoff_y_aviso():
    avisos = Avisos()
    reloj = Reloj()
    sleeps = []
    llamadas_abrir = [0]

    async def sleep(seg):
        if len(sleeps) >= 2:
            raise asyncio.CancelledError()
        sleeps.append(seg)

    async def abrir_factory():
        llamadas_abrir[0] += 1
        n = llamadas_abrir[0]

        async def gen():
            if n == 1:
                raise RuntimeError("corte")
            if n == 2:
                yield linea_evento("die")
                return

        return gen()

    v = VigiaEntornos("/usr/bin/docker", avisos, abrir=abrir_factory, sleep=sleep, now=reloj)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(v.run())

    assert sleeps == [5, 5]
    assert len(avisos.items) == 1


class AvisarFallaPrimera:
    def __init__(self):
        self.n = 0
        self.items = []

    async def __call__(self, titulo, cuerpo, ref):
        self.n += 1
        if self.n == 1:
            raise RuntimeError("push caído")
        self.items.append({"titulo": titulo, "cuerpo": cuerpo, "ref": ref})
        return 1


def test_avisar_falla_no_bloquea_segundo_die():
    avisos = AvisarFallaPrimera()
    reloj = Reloj()
    v = vigia(avisos, now=reloj)
    asyncio.run(v.procesar(linea_evento("die")))
    reloj.t = 5
    asyncio.run(v.procesar(linea_evento("die")))
    assert len(avisos.items) == 1


def test_unhealthy_y_die_mismo_servicio_dos_avisos():
    avisos = Avisos()
    reloj = Reloj()
    v = vigia(avisos, now=reloj)
    asyncio.run(v.procesar(linea_evento("health_status: unhealthy")))
    reloj.t = 60
    asyncio.run(v.procesar(linea_evento("die")))
    assert len(avisos.items) == 2


def test_argv_events_sin_y_con_since():
    v = vigia(Avisos())
    assert v.argv_events() == [
        "/usr/bin/docker",
        "events",
        "--format",
        "{{json .}}",
        "--filter",
        "type=container",
    ]
    asyncio.run(v.procesar(json.dumps({"time": 1700000000, "Action": "start"})))
    assert v.argv_events()[-2:] == ["--since", "1700000000"]


def test_run_cierra_fuente_antes_del_backoff():
    avisos = Avisos()
    reloj = Reloj()
    sleeps = []
    cerrado = {"ok": False}

    async def sleep(seg):
        sleeps.append(seg)
        raise asyncio.CancelledError()

    async def abrir_factory():
        async def gen():
            try:
                yield linea_evento("die")
            finally:
                cerrado["ok"] = True

        return gen()

    v = VigiaEntornos("/usr/bin/docker", avisos, abrir=abrir_factory, sleep=sleep, now=reloj)

    async def procesar_tira(_linea):
        raise RuntimeError("procesar falló")

    v.procesar = procesar_tira

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(v.run())

    assert cerrado["ok"] is True
    assert sleeps == [5]


def test_ref_sanea_caracteres_fuera_del_tag():
    from orquestador.entornos_vigia import ref_aviso
    assert ref_aviso("hybrid-search", "hs-api") == "hybrid-search:hs-api"
    assert ref_aviso("p", "a/b c") == "p:a-b-c"
    assert len(ref_aviso("p", "x" * 300)) <= 100


def test_die_con_codigo_cero_no_es_caida():
    avisos = Avisos()
    v = vigia(avisos)
    asyncio.run(procesar_varias(v, [linea_evento("die", servicio="migrate", exit_code=0)]))
    assert avisos.items == []
