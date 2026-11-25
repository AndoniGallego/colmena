import json
from datetime import datetime, timedelta, timezone

import pytest

from biblioteca_support import Env
from conftest import PIN
from orquestador import biblioteca as bib
from orquestador.config import hash_pin

AHORA = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    e.cfg.pin = hash_pin(PIN)
    return e


def datos(semana="2026-W47", ts=None, **over):
    d = {"semana": semana, "desde": "2026-11-16", "hasta": "2026-11-22", "resumen": {"sesiones": 4},
         "propuestas": [{"id": "p1"}]}
    if ts is not None:
        d["generado"] = ts.timestamp()
    d.update(over)
    return d


def datos_reunion(fin):
    return {"v": 1, "reunion": "r1", "inicio": fin - 600, "fin": fin, "duracion_s": 600, "repos": [],
            "motivo": "terminada", "titulo": "Plan", "resumen": ["x"], "pendientes": [], "tocadas": []}


def test_agregar_resumen_queda_listado_y_avisa(env):
    lib = env.lib
    avisados = []
    lib.listeners.append(avisados.append)
    ident = lib.agregar_resumen(datos("2026-W47"))
    res = lib.listing(tipo="resumen")
    assert [i["id"] for i in res["items"]] == [ident]
    v = res["items"][0]
    assert ident == bib.item_id("resumen-2026-W47", "2026-W47", 0)
    assert v["title"] == "Semana del 16/11 al 22/11"
    assert v["kind"] == "resumen" and v["source"] == "resumen" and v["project"] == "Colmena"
    assert v["exists"] is True and v["servible"] is False and v["src"] == ""
    assert json.loads(v["resumen_raw"])["semana"] == "2026-W47"
    assert avisados == [[ident]]


def test_misma_semana_reemplaza(env):
    lib = env.lib
    a = lib.agregar_resumen(datos("2026-W47"))
    b = lib.agregar_resumen(datos("2026-W47", resumen={"sesiones": 9}))
    items = lib.listing(tipo="resumen")["items"]
    assert a == b and len(items) == 1
    assert json.loads(items[0]["resumen_raw"])["resumen"] == {"sesiones": 9}


def test_resumen_raw_solo_en_resumenes(env):
    lib = env.lib
    lib.agregar_resumen(datos())
    reu = lib.agregar_reunion(datos_reunion(AHORA.timestamp()), "x")
    assert lib.view_of(lib.items[reu]).get("resumen_raw") is None


def test_resumen_sobrevive_a_recargar_y_se_busca(env):
    ident = env.lib.agregar_resumen(datos())
    lib = env.reload()
    lib.index_all()
    assert ident in lib.items
    assert [i["id"] for i in lib.listing(q="semana del 16")["items"]] == [ident]
    assert lib.quitar([ident]) == 1


def test_quitar_resumenes_viejos(env):
    lib = env.lib
    viejo = lib.agregar_resumen(datos("2026-W30", ts=AHORA - timedelta(days=91)))
    nuevo = lib.agregar_resumen(datos("2026-W35", ts=AHORA - timedelta(days=89)))
    reu = lib.agregar_reunion(datos_reunion((AHORA - timedelta(days=200)).timestamp()), "x")
    assert lib.quitar_resumenes_viejos(AHORA) == 1
    ids = {i["id"] for i in lib.listing()["items"]}
    assert viejo not in ids and nuevo in ids and reu in ids
