from orquestador.push import EN_APP
from orquestador.telemetria_respuesta import SeguidorRespuestas


def armar():
    anotadas = []
    reloj = [1000]
    s = SeguidorRespuestas(lambda ev, **c: anotadas.append((ev, c)), wall=lambda: reloj[0])
    return s, anotadas, reloj


def aviso(kind="asks", sid="s1", ts=1000, motivo="", prueba=False, pane="w1:p1"):
    return {"kind": kind, "session_id": sid, "ts": ts, "motivo": motivo, "prueba": prueba, "pane_id": pane}


def test_asks_luego_prompt():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso()); reloj[0] = 1090; s.al_prompt("s1", "w1:p1")
    assert anotadas == [("respuesta", {"aviso": "asks", "resultado": "respondio", "segundos": 90, "via": "prompt", "en_app": False})]


def test_segundo_aviso_no_pisa_al_primero():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso(ts=1000)); s.al_aviso(aviso(ts=1050)); reloj[0] = 1100; s.al_prompt("s1", None)
    assert anotadas[0][1]["segundos"] == 100


def test_prompt_de_colmena_no_cuenta():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso()); reloj[0] = 1100; s.escribio_colmena("w1:p1"); reloj[0] = 1105; s.al_prompt("s1", "w1:p1")
    assert anotadas == []
    reloj[0] = 1200; s.al_prompt("s1", "w1:p1")
    assert anotadas[0][1]["segundos"] == 200


def test_prompt_de_colmena_con_orden_real_durante_el_envio():
    # Colmena marca el pane antes de enviar; el hook (al_prompt) llega mientras el envío sigue en curso.
    s, anotadas, reloj = armar()
    s.al_aviso(aviso()); reloj[0] = 1100
    s.escribio_colmena("w1:p1")
    reloj[0] = 1102; s.al_prompt("s1", "w1:p1")
    assert anotadas == []


def test_blocked_con_permiso_y_en_app():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso(kind="blocked", motivo=EN_APP)); reloj[0] = 1030; s.al_permiso("s1")
    assert anotadas[0][1] == {"aviso": "blocked", "resultado": "respondio", "segundos": 30, "via": "permiso", "en_app": True}


def test_sesion_que_sale_del_tablero_da_sin_respuesta():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso()); s.revisar({"otra"})
    assert anotadas[0][1]["resultado"] == "sin_respuesta" and anotadas[0][1]["segundos"] is None


def test_24h_da_sin_respuesta():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso()); reloj[0] = 1000 + 24 * 3600 + 1; s.revisar({"s1"})
    assert anotadas[0][1]["resultado"] == "sin_respuesta"


def test_prueba_y_otros_kinds_se_ignoran():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso(prueba=True)); s.al_aviso(aviso(kind="done")); s.al_prompt("s1", None)
    assert anotadas == []


def test_prompt_sin_aviso_no_anota():
    s, anotadas, reloj = armar()
    s.al_prompt("s1", None); assert anotadas == []


def test_lo_anotado_no_lleva_sid_ni_pane():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso()); reloj[0] = 1010; s.al_prompt("s1", None)
    assert "s1" not in str(anotadas) and "w1:p1" not in str(anotadas)


def test_anotar_que_falla_no_rompe():
    def mal(ev, **c):
        raise RuntimeError("x")
    s = SeguidorRespuestas(mal, wall=lambda: 1010)
    s.al_aviso(aviso()); s.al_prompt("s1", None); s.revisar(set())


def test_una_respuesta_consume_el_pendiente():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso()); reloj[0] = 1010; s.al_prompt("s1", None); s.al_prompt("s1", None)
    assert len(anotadas) == 1


def test_revisar_consume_el_pendiente():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso()); s.revisar(set()); s.revisar(set())
    assert len(anotadas) == 1


def test_aviso_sin_session_id_se_ignora():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso(sid=None)); s.al_aviso(aviso(sid=""))
    reloj[0] = 1010; s.al_prompt("", None); s.al_prompt(None, None); s.revisar(set())
    assert anotadas == []


def test_el_ts_del_entry_manda():
    s, anotadas, reloj = armar()
    reloj[0] = 1050; s.al_aviso(aviso(ts=1000)); reloj[0] = 1090; s.al_prompt("s1", None)
    assert anotadas[0][1]["segundos"] == 90


def test_prompt_sin_pane_en_ventana_de_colmena_no_cuenta():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso()); reloj[0] = 1100; s.escribio_colmena("w1:p1"); reloj[0] = 1105
    s.al_prompt("s1", None)
    assert anotadas == []


def test_permiso_en_ventana_de_colmena_si_cuenta():
    s, anotadas, reloj = armar()
    s.al_aviso(aviso(kind="blocked")); reloj[0] = 1100; s.escribio_colmena("w1:p1"); reloj[0] = 1105
    s.al_permiso("s1")
    assert anotadas[0][1]["via"] == "permiso" and anotadas[0][1]["segundos"] == 105


def test_pane_del_gancho_es_el_mismo_que_el_de_mandar_prompt():
    from orquestador.estado_sesiones import Ids, dueno_de
    board = {"workspaces": [{"tabs": [{"agents": [{"pane_id": "w1:p2", "session_id": "s1"}]}]}]}
    pane_gancho = dueno_de(Ids(None, None, None, None, "s1"), board)
    assert pane_gancho == "w1:p2"
    s, anotadas, reloj = armar()
    s.al_aviso(aviso(pane="w1:p2")); reloj[0] = 1100
    s.escribio_colmena("w1:p2"); reloj[0] = 1103
    s.al_prompt("s1", pane_gancho)
    assert anotadas == []
