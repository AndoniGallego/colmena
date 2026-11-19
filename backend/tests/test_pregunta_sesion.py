import json

import pytest

from conftest import SID, make_snapshot
from orquestador.opciones import preguntas_de, signature
from terminales_support import aplicar_snapshot

ID = "0b6f1c1e-4a55-4e1d-9d33-1f3c2a7d9e10"
UNA = '¿Cómo seguimos?\n\n```opciones\n{"pregunta": "Uno", "opciones": [{"label": "A", "detalle": "da", "recomendada": true}, {"label": "B"}]}\n```'
DOS = UNA + '\n\n```opciones\n{"pregunta": "Dos", "opciones": [{"label": "C"}]}\n```'
URL = f"/api/sessions/{SID}/pregunta"


def decir(projects, text):
    path = projects / "-proj" / f"{SID}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}) + "\n")


def body(sig, **over):
    out = {"id": ID, "sig": sig, "texto": "1. A"}
    out.update(over)
    return out


def sig_de(text):
    return signature(SID, preguntas_de(text))


def prompts(enchufe):
    return enchufe.calls_of("mandar_prompt")


def test_get_devuelve_la_pregunta_vigente(authed, projects):
    decir(projects, UNA)
    r = authed.get(URL)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    data = r.json()
    assert data["sig"] == sig_de(UNA) and data["session_id"] == SID and data["pane_id"] == "w1:p1"
    assert data["nombre"] == "Uno"
    assert data["preguntas"] == [{"pregunta": "Uno", "opciones": [
        {"label": "A", "detalle": "da", "recomendada": True}, {"label": "B", "detalle": "", "recomendada": False}]}]


def test_la_firma_es_estable_entre_lecturas(authed, projects):
    decir(projects, UNA)
    assert authed.get(URL).json()["sig"] == authed.get(URL).json()["sig"]


def test_get_sin_tarjetas_es_404_sin_pregunta(authed):
    r = authed.get(URL)
    assert r.status_code == 404 and r.json()["detail"] == "SIN_PREGUNTA"


def test_get_sesion_desconocida_es_404(authed):
    assert authed.get("/api/sessions/otra-sesion/pregunta").json()["detail"] == "SIN_PREGUNTA"


@pytest.mark.parametrize("estado", ["working", "blocked"])
def test_get_trabajando_o_bloqueada_es_404(authed, projects, enchufe, estado):
    decir(projects, UNA)
    aplicar_snapshot(enchufe, make_snapshot(estado))
    assert authed.get(URL).status_code == 404


def test_get_workspace_protegido_es_404(authed, projects, enchufe):
    decir(projects, UNA)
    snap = make_snapshot()
    snap["workspaces"][1]["label"] = "Orquestador"
    aplicar_snapshot(enchufe, snap)
    authed.app.state.pregunta_sesion.protected = {"orquestador"}
    assert authed.get(URL).status_code == 404


def test_rutas_exigen_sesion(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL + "/responder", json=body("x")).status_code == 401


def test_responder_delega_en_mensaje_con_el_pane_del_board(authed, projects, enchufe):
    decir(projects, UNA)
    r = authed.post(URL + "/responder", json=body(sig_de(UNA), texto="1. A", pane_id="w9:p9"))
    assert r.status_code == 200 and r.json()["ok"] is True
    assert prompts(enchufe) == [("mandar_prompt", "w1:p1", "1. A")]
    assert authed.app.state.state.mensajes()[-1]["destino"] == "Uno"


def test_responder_con_firma_vieja_es_409_ya_contestada(authed, projects, enchufe):
    decir(projects, UNA)
    r = authed.post(URL + "/responder", json=body("otra:firma"))
    assert r.status_code == 409 and r.json()["detail"] == "YA_CONTESTADA" and not prompts(enchufe)


def test_responder_sin_pregunta_es_409_ya_contestada(authed, enchufe):
    r = authed.post(URL + "/responder", json=body("x"))
    assert r.status_code == 409 and r.json()["detail"] == "YA_CONTESTADA" and not prompts(enchufe)


def test_responder_si_cambio_la_pregunta_es_409(authed, projects, enchufe):
    decir(projects, UNA)
    firma = sig_de(UNA)
    decir(projects, DOS)
    assert authed.post(URL + "/responder", json=body(firma)).status_code == 409
    assert not prompts(enchufe)


@pytest.mark.parametrize("estado", ["working", "blocked"])
def test_responder_trabajando_o_bloqueada_es_409(authed, projects, enchufe, estado):
    decir(projects, UNA)
    aplicar_snapshot(enchufe, make_snapshot(estado))
    r = authed.post(URL + "/responder", json=body(sig_de(UNA)))
    assert r.status_code == 409 and not prompts(enchufe)


def test_responder_workspace_protegido_es_400(authed, projects, enchufe):
    decir(projects, UNA)
    snap = make_snapshot()
    snap["workspaces"][1]["label"] = "Orquestador"
    aplicar_snapshot(enchufe, snap)
    authed.app.state.pregunta_sesion.protected = {"orquestador"}
    r = authed.post(URL + "/responder", json=body(sig_de(UNA)))
    assert r.status_code == 400 and not prompts(enchufe)


def test_responder_pane_oculto_es_400(authed, projects, enchufe):
    decir(projects, UNA)
    authed.app.state.pregunta_sesion.protected_panes = lambda: {"w1:p1"}
    r = authed.post(URL + "/responder", json=body(sig_de(UNA)))
    assert r.status_code == 400 and not prompts(enchufe)


def test_responder_respeta_la_validacion_de_texto(authed, projects, enchufe):
    decir(projects, UNA)
    assert authed.post(URL + "/responder", json=body(sig_de(UNA), texto="  ")).status_code == 400
    assert authed.post(URL + "/responder", json=body(sig_de(UNA), texto="a\x07b")).status_code == 400
    assert not prompts(enchufe)


def test_responder_id_repetido_es_409(authed, projects, enchufe):
    decir(projects, UNA)
    assert authed.post(URL + "/responder", json=body(sig_de(UNA))).status_code == 200
    assert authed.post(URL + "/responder", json=body(sig_de(UNA))).status_code == 409
    assert len(prompts(enchufe)) == 1


def test_responder_cuerpo_invalido_es_400(authed):
    assert authed.post(URL + "/responder", json={"id": "x"}).status_code == 400


def test_segundo_envio_de_la_misma_pregunta_con_otro_id_es_409(authed, projects, enchufe):
    decir(projects, UNA)
    assert authed.post(URL + "/responder", json=body(sig_de(UNA))).status_code == 200
    r = authed.post(URL + "/responder", json=body(sig_de(UNA), id="otro-id-distinto-1"))
    assert r.status_code == 409 and r.json()["detail"] == "YA_CONTESTADA"
    assert len(prompts(enchufe)) == 1


def test_get_de_una_pregunta_ya_contestada_es_404(authed, projects):
    decir(projects, UNA)
    assert authed.post(URL + "/responder", json=body(sig_de(UNA))).status_code == 200
    assert authed.get(URL).json()["detail"] == "SIN_PREGUNTA"


def test_pregunta_nueva_despues_de_contestar_vuelve_a_estar_vigente(authed, projects):
    decir(projects, UNA)
    assert authed.post(URL + "/responder", json=body(sig_de(UNA))).status_code == 200
    decir(projects, DOS)
    assert authed.get(URL).status_code == 200


def test_responder_revalida_contra_un_board_fresco(authed, projects, enchufe):
    decir(projects, UNA)
    assert authed.get(URL).status_code == 200
    aplicar_snapshot(enchufe, make_snapshot("working"))
    r = authed.post(URL + "/responder", json=body(sig_de(UNA)))
    assert r.status_code == 409 and not prompts(enchufe)


def test_get_redacta_pregunta_opciones_y_detalle(authed, projects):
    texto = ('```opciones\n{"pregunta": "Usar token=abc123secreto?", "opciones": '
             '[{"label": "password=hunter2xx", "detalle": "Bearer abcdefgh"}]}\n```')
    decir(projects, texto)
    data = authed.get(URL).json()
    q = data["preguntas"][0]
    assert "abc123secreto" not in q["pregunta"] and "hunter2xx" not in q["opciones"][0]["label"]
    assert "abcdefgh" not in q["opciones"][0]["detalle"]
    assert data["sig"] == sig_de(texto)


def test_texto_vacio_es_cuerpo_invalido(authed, projects):
    decir(projects, UNA)
    assert authed.post(URL + "/responder", json=body(sig_de(UNA), texto="   ")).status_code == 400


def test_agente_que_no_es_claude_es_409(authed, projects, enchufe):
    decir(projects, UNA)
    snap = make_snapshot()
    snap["agents"][0]["agent"] = "codex"
    aplicar_snapshot(enchufe, snap)
    r = authed.post(URL + "/responder", json=body(sig_de(UNA)))
    assert r.status_code == 409 and not prompts(enchufe)


def test_sid_invalido_es_400(authed):
    assert authed.get("/api/sessions/mal sid!/pregunta").status_code == 400
    assert authed.post("/api/sessions/mal$sid/pregunta/responder", json=body("x")).status_code == 400


def test_id_invalido_o_texto_enorme_es_4xx(authed, projects, enchufe):
    decir(projects, UNA)
    assert authed.post(URL + "/responder", json=body(sig_de(UNA), id="corto")).status_code == 400
    assert authed.post(URL + "/responder", json=body(sig_de(UNA), texto="a" * 20001)).status_code == 400
    assert not prompts(enchufe)


def test_status_done_funciona_como_idle(authed, projects, enchufe):
    decir(projects, UNA)
    aplicar_snapshot(enchufe, make_snapshot("done"))
    assert authed.get(URL).status_code == 200
    assert authed.post(URL + "/responder", json=body(sig_de(UNA))).status_code == 200


def test_marcada_leida_sigue_vigente_para_contestar(authed, projects, enchufe):
    decir(projects, UNA)
    assert authed.get(URL).status_code == 200
    assert authed.post(f"/api/sessions/{SID}/pregunta-vista").status_code == 204
    r = authed.get(URL)
    assert r.status_code == 200 and r.json()["sig"] == sig_de(UNA)
    r = authed.post(URL + "/responder", json=body(sig_de(UNA)))
    assert r.status_code == 200
    assert len(prompts(enchufe)) == 1
