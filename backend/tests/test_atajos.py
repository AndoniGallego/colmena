import pytest
from orquestador.atajos import ORIGINALES, validar_atajos
from orquestador.state import StateStore


def test_state_atajos_vacio_y_guarda(tmp_path):
    s = StateStore(tmp_path)
    assert s.atajos() == {}
    s.set_atajos({"buscador": "mod+j"})
    s.flush()
    assert StateStore(tmp_path).atajos() == {"buscador": "mod+j"}


def test_get_vacio(authed):
    assert authed.get("/api/atajos").json() == {"atajos": {}}


def test_put_y_get(authed):
    r = authed.put("/api/atajos", json={"atajos": {"buscador": "mod+j", "minimizar-preguntas": "n"}})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert authed.get("/api/atajos").json() == {"atajos": {"buscador": "mod+j", "minimizar-preguntas": "n"}}


def test_put_descarta_lo_igual_al_original(authed):
    authed.put("/api/atajos", json={"atajos": {"buscador": "mod+k", "dictar": "mod+alt+d"}})
    assert authed.get("/api/atajos").json() == {"atajos": {"dictar": "mod+alt+d"}}


def test_volver_al_original_es_mapa_vacio(authed):
    authed.put("/api/atajos", json={"atajos": {"dictar": "mod+alt+d"}})
    authed.put("/api/atajos", json={"atajos": {}})
    assert authed.get("/api/atajos").json() == {"atajos": {}}


@pytest.mark.parametrize(
    "atajos",
    [
        {"inexistente": "mod+j"},
        {"buscador": "mod+"},
        {"buscador": "MOD+J"},
        {"buscador": "mod+shift"},
        {"buscador": "j"},
        {"buscador": "shift+j"},
        {"buscador": 5},
        {"buscador": "mod+shift+space"},
        {"dictar": "mod+k"},
        {"buscador": "mod+j", "dictar": "mod+j"},
        {"crear-terminal": "mod+k"},
    ],
)
def test_put_invalidos_422(authed, atajos):
    assert authed.put("/api/atajos", json={"atajos": atajos}).status_code == 422
    assert authed.get("/api/atajos").json() == {"atajos": {}}


def test_mismo_original_en_contextos_distintos_es_valido():
    assert ORIGINALES["crear-terminal"] == ORIGINALES["comentar"] == "mod+enter"
    assert validar_atajos({}) == {}


def test_minimizar_no_pisa_teclas_de_te_pregunta():
    for k in ['1', '6', 'enter', 'tab', 'space']:
        with pytest.raises(ValueError):
            validar_atajos({'minimizar-preguntas': k})
    assert validar_atajos({'minimizar-preguntas': '7'}) == {'minimizar-preguntas': '7'}


def test_letra_sola_solo_en_minimizar():
    assert validar_atajos({"minimizar-preguntas": "x"}) == {"minimizar-preguntas": "x"}
    with pytest.raises(ValueError):
        validar_atajos({"crear-terminal": "x"})
