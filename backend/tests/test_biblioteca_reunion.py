import json
import time

import pytest

from biblioteca_support import Env
from conftest import PIN
from orquestador import biblioteca as bib
from orquestador.config import hash_pin

INICIO = 1_700_000_000.0


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    e.cfg.pin = hash_pin(PIN)
    return e


def datos(rid="r1", **over):
    d = {"v": 1, "reunion": rid, "inicio": INICIO, "fin": INICIO + 600, "duracion_s": 600, "repos": ["a"],
         "motivo": "terminada", "titulo": "Planificación", "resumen": ["Se definió el alcance", "Segundo punto"],
         "pendientes": ["Mandar el mail"], "tocadas": [], "lineas": 3, "charla_chars": 20, "recortada": False}
    d.update(over)
    return d


def test_agregar_reunion_queda_listada_y_filtrable_por_tipo(env):
    lib = env.lib
    avisos = []
    lib.listeners.append(avisos.append)
    ident = lib.agregar_reunion(datos(), "Ana: hola\nBeto: chau")
    assert avisos == [[ident]]
    assert ident == bib.item_id("reunion-r1", "r1", 0)
    res = lib.listing(tipo="reunion")
    assert [i["id"] for i in res["items"]] == [ident]
    v = res["items"][0]
    assert v["kind"] == "reunion" and v["project"] == "Reunión" and v["source"] == "reunion"
    assert v["title"].startswith("Reunión ") and v["title"].endswith("· Planificación")
    assert v["description"] == "Se definió el alcance"
    assert v["exists"] is True and v["servible"] is False and v["src"] == ""
    assert v["tiene_charla"] is True and json.loads(v["reunion_raw"])["pendientes"] == ["Mandar el mail"]
    assert lib.listing(tipo="pdf")["items"] == []


def test_charla_se_lee_y_se_borra_con_quitar(env):
    lib = env.lib
    ident = lib.agregar_reunion(datos(), "Ana: hola")
    assert lib.charla_de(ident) == "Ana: hola"
    assert lib.charla_de("0" * 32) is None
    assert lib.quitar([ident]) == 1
    assert lib.charla_de(ident) is None
    assert not list((env.data / "biblioteca" / "blobs").iterdir())


def test_reunion_sobrevive_a_recargar_e_index_all(env):
    ident = env.lib.agregar_reunion(datos(), "Ana: hola")
    lib = env.reload()
    lib.index_all()
    assert ident in lib.items and lib.charla_de(ident) == "Ana: hola"
    assert lib.view_of(lib.items[ident])["tiene_charla"] is True


def test_purge_a_los_90_dias_borra_la_charla_y_deja_el_resumen(env):
    lib = env.lib
    ident = lib.agregar_reunion(datos(), "Ana: hola")
    lib.items[ident]["copied_at"] = time.time() - 91 * 86400
    lib.purge()
    v = lib.view_of(lib.items[ident])
    assert lib.charla_de(ident) is None and v["tiene_charla"] is False
    assert json.loads(v["reunion_raw"])["titulo"] == "Planificación"


def test_charla_sin_presupuesto_guarda_igual_el_resumen(env, monkeypatch):
    def falla(*a, **k):
        raise OSError("sin presupuesto de copias")
    monkeypatch.setattr(env.lib, "_store_bytes", falla)
    ident = env.lib.agregar_reunion(datos(), "Ana: hola")
    v = env.lib.view_of(env.lib.items[ident])
    assert v["tiene_charla"] is False and env.lib.charla_de(ident) is None
    assert json.loads(v["reunion_raw"])["resumen"][0] == "Se definió el alcance"


def test_kind_reunion_en_listado_y_conteos(env):
    lib = env.lib
    assert "reunion" in bib.KINDS
    lib.agregar_reunion(datos("r1"), "a")
    lib.agregar_reunion(datos("r2", titulo="Otra"), "b")
    res = lib.listing()
    assert res["total"] == 2 and {i["kind"] for i in res["items"]} == {"reunion"}
    assert len(lib.listing(tipo="reunion")["items"]) == 2
    assert lib.view_of(lib.items[bib.item_id("reunion-r1", "r1", 0)])["ts"].endswith("Z")


def test_agregar_reunion_espera_el_lock_del_indexador(env):
    import threading
    lib = env.lib
    hecho = threading.Event()
    lib._index_lock.acquire()
    try:
        t = threading.Thread(target=lambda: (lib.agregar_reunion(datos(), "x"), hecho.set()))
        t.start()
        assert not hecho.wait(0.2)
    finally:
        lib._index_lock.release()
    assert hecho.wait(5)
    t.join(5)
    assert lib.listing(tipo="reunion")["total"] == 1


def test_reunion_raw_nunca_pasa_el_tope_y_sigue_siendo_json(env):
    largo = "ñ" * 5000
    tocadas = [{"texto": f"t{i}", "tipo": "x", "respuesta": largo, "archivos": []} for i in range(150)]
    d = datos(titulo=largo, resumen=[largo] * 8, pendientes=[largo] * 8, tocadas=tocadas)
    ident = env.lib.agregar_reunion(d, "x")
    raw = env.lib.items[ident]["reunion_raw"]
    assert len(raw.encode()) <= bib.MAX_REUNION_RAW_BYTES
    obj = json.loads(raw)
    assert obj["inicio"] == INICIO and obj["fin"] == INICIO + 600
    assert 0 < len(obj["tocadas"]) < 150 and obj["tocadas"][-1]["texto"] == "t149"
    assert len(obj["titulo"]) < 5000 and env.lib.items[ident]["size"] == len(raw.encode())


def test_agregar_reunion_sin_id_lanza_value_error(env):
    for malo in ("", None):
        with pytest.raises(ValueError):
            env.lib.agregar_reunion(datos(reunion=malo), "x")
    d = datos()
    del d["reunion"]
    with pytest.raises(ValueError):
        env.lib.agregar_reunion(d, "x")
