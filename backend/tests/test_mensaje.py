import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from conftest import make_snapshot
from orquestador.enchufe import FakeTerminales, NoTomado
from terminales_support import aplicar_snapshot

ID = "0b6f1c1e-4a55-4e1d-9d33-1f3c2a7d9e10"


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


def payload(**over):
    body = {"id": ID, "pane_id": "w1:p1", "texto": "Sí, juntalo y publicalo", "origen": "manual",
            "destino": "Uno (w1:p1)", "por_que": "pregunta pendiente"}
    body.update(over)
    return body


def post(authed, body):
    return authed.post("/api/mensaje/execute", json=body)


def prompts(enchufe):
    return enchufe.calls_of("mandar_prompt")


def test_idle_prompts_directly(authed, enchufe):
    r = post(authed, payload())
    assert r.status_code == 200 and r.json() == {"ok": True, "pane_id": "w1:p1"}
    assert enchufe.calls == [("mandar_prompt", "w1:p1", "Sí, juntalo y publicalo")]


def test_working_prompts_without_waiting(authed, enchufe):
    aplicar_snapshot(enchufe, make_snapshot("working"))
    assert post(authed, payload()).status_code == 200
    assert [c[0] for c in enchufe.calls] == ["mandar_prompt"]


def test_concurrent_sends_to_one_pane_arrive_in_order(app, enchufe):
    aplicar_snapshot(enchufe, make_snapshot("working"))
    active, order = [], []
    orig = enchufe.mandar_prompt

    async def slow(sesion_id, texto, **kw):
        active.append(1)
        assert len(active) == 1
        await asyncio.sleep(0.02 if texto == "uno" else 0)
        order.append(texto)
        active.pop()
        return await orig(sesion_id, texto, **kw)

    enchufe.mandar_prompt = slow

    async def go():
        async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 5000)),
                               base_url="https://t", headers={"Origin": "https://t"}) as c:
            assert (await c.post("/api/login", json={"pin": "43215678"})).status_code == 200
            tasks = []
            for i, t in enumerate(["uno", "dos", "tres"]):
                tasks.append(asyncio.create_task(c.post("/api/mensaje/execute",
                                                        json=payload(id=f"orden-id-{i}", texto=t))))
                await asyncio.sleep(0.001)
            return [r.status_code for r in await asyncio.gather(*tasks)]

    assert asyncio.run(go()) == [200, 200, 200]
    assert order == ["uno", "dos", "tres"]


def test_blocked_409_without_calls(authed, enchufe):
    aplicar_snapshot(enchufe, make_snapshot("blocked"))
    r = post(authed, payload())
    assert r.status_code == 409 and "aprobación" in r.json()["detail"] and enchufe.calls == []
    assert "ya se mand" not in r.json()["detail"].lower()


def test_unknown_pane_404(authed, enchufe):
    assert post(authed, payload(pane_id="w9:p9")).status_code == 404
    assert enchufe.calls == []


def test_own_pane_400(authed, enchufe):
    assert post(authed, payload(pane_id="w2:p9")).status_code == 400
    assert enchufe.calls == []


@pytest.mark.parametrize("texto", ["", "   \n ", "x" * 4001, "a\x1bb", "a\x00b", "a\x85b"])
def test_invalid_text_400(authed, enchufe, texto):
    assert post(authed, payload(texto=texto)).status_code == 400
    assert enchufe.calls == []


def test_text_limit_boundary_and_tabs_ok(authed, enchufe):
    assert post(authed, payload(texto="x" * 4000)).status_code == 200
    assert post(authed, payload(id="otro-id-123", texto="a\tb")).status_code == 200


def test_leading_dash_gets_space(authed, enchufe):
    assert post(authed, payload(texto="--force y listo")).status_code == 200
    assert prompts(enchufe)[0][2] == " --force y listo"


def test_normalizes_and_flattens_newlines(authed, enchufe):
    assert post(authed, payload(texto="  uno\r\ndos\n\ntres  ")).status_code == 200
    assert prompts(enchufe)[0][2] == "uno dos tres"


@pytest.mark.parametrize("over", [{"id": "corto"}, {"id": "con espacio 123"}, {"origen": "otro"},
                                  {"destino": "x" * 201}, {"por_que": "x" * 2001}, {"pane_id": "-x"}])
def test_bad_fields_400(authed, enchufe, over):
    assert post(authed, payload(**over)).status_code == 400
    assert enchufe.calls == []


def test_idempotent_409_after_success(authed, enchufe):
    assert post(authed, payload()).status_code == 200
    n = len(enchufe.calls)
    again = post(authed, payload())
    assert again.status_code == 409 and again.json()["detail"] == "Ya se mandó ese mensaje"
    assert len(enchufe.calls) == n


def test_failure_recorded_and_same_id_retry_is_not_resent(authed, enchufe):
    enchufe.fallas["mandar_prompt"] = NoTomado("boom")
    r = post(authed, payload())
    assert r.status_code == 502
    entry = authed.app.state.state.mensajes()[-1]
    assert entry["ok"] is False and "boom" in entry["error"] and entry["incierto"] is True
    enchufe.fallas.clear()
    n = len(prompts(enchufe))
    again = post(authed, payload())
    assert again.status_code == 409 and "ya haya llegado" in again.json()["detail"]
    assert len(prompts(enchufe)) == n
    assert post(authed, payload(id="otro-intento-1")).status_code == 200
    assert [m["ok"] for m in authed.app.state.state.mensajes()] == [False, True]


def test_record_has_truncated_text(authed):
    post(authed, payload(texto="y" * 500))
    entry = authed.app.state.state.mensajes()[-1]
    assert entry["id"] == ID and entry["origen"] == "manual" and len(entry["texto"]) == 200
    assert set(entry) >= {"pane_id", "destino", "ts", "ok"}


def test_event_only_for_jefe(authed):
    manual = post(authed, payload())
    assert "event" not in manual.json()
    assert authed.app.state.state.messages() == []
    jefe = post(authed, payload(id="otro-id-123", origen="jefe"))
    event = jefe.json()["event"]
    assert event["role"] == "event" and event["text"] == "Mensaje enviado a Uno (w1:p1)"
    assert authed.app.state.state.messages() == []


def test_requires_auth(client):
    assert post(client, payload()).status_code == 401


def attach(authed, name="a.png", data=b"\x89PNG\r\n\x1a\n0000"):
    return authed.post("/api/uploads", files={"file": (name, data)}).json()["id"]


def test_attachments_build_server_paths(authed, enchufe, tmp_path):
    a, b = attach(authed), attach(authed, "n.txt", b"hola")
    assert post(authed, payload(adjuntos=[a, b])).status_code == 200
    base = (tmp_path / "uploads").resolve()
    assert prompts(enchufe)[0][2] == f"Sí, juntalo y publicalo (Adjunto: {base / a}) (Adjunto: {base / b})"


def test_attachment_only_text(authed, enchufe, tmp_path):
    a = attach(authed)
    assert post(authed, payload(texto="  ", adjuntos=[a])).status_code == 200
    assert prompts(enchufe)[0][2] == f"Te paso {(tmp_path / 'uploads').resolve() / a}"
    assert post(authed, payload(id="otro-id-123", texto="")).status_code == 400


def test_attachment_recorded_text_has_path(authed):
    a = attach(authed)
    post(authed, payload(adjuntos=[a]))
    assert "(Adjunto: " in authed.app.state.state.mensajes()[-1]["texto"]


@pytest.mark.parametrize("bad", ["20250101-000000-nope.png", "../state.json", "/etc/passwd", "x" * 90])
def test_attachment_unknown_or_invalid_400(authed, enchufe, bad):
    assert post(authed, payload(adjuntos=[bad])).status_code == 400
    assert enchufe.calls == []


def test_more_than_five_attachments_400(authed, enchufe):
    ids = [attach(authed, f"n{i}.txt", b"x") for i in range(6)]
    assert post(authed, payload(adjuntos=ids)).status_code == 400
    assert post(authed, payload(adjuntos=ids[:5])).status_code == 200


def test_client_paths_never_used(authed, enchufe):
    r = post(authed, payload(adjuntos=["/tmp/x.png"]))
    assert r.status_code == 400 and enchufe.calls == []


def test_mensaje_queda_en_el_registro_de_enviados(authed):
    post(authed, payload(id="otro-id-123", origen="jefe"))
    assert [m["id"] for m in authed.app.state.state.mensajes()] == ["otro-id-123"]


def test_origen_usuario_centinela_ya_no_existe(authed):
    assert post(authed, payload(origen="usuario_centinela")).status_code == 400


def stop(authed, pane="w1:p1"):
    return authed.post("/api/sessions/stop", json={"pane_id": pane})


def test_stop_sends_esc_only(authed, enchufe):
    aplicar_snapshot(enchufe, make_snapshot("working"))
    r = stop(authed)
    assert r.status_code == 200 and r.json() == {"ok": True, "pane_id": "w1:p1"}
    assert enchufe.calls == [("interrumpir", "w1:p1")]


def test_stop_unknown_pane_404(authed, enchufe):
    assert stop(authed, "w9:p9").status_code == 404
    assert enchufe.calls == []


def test_stop_own_pane_400(authed, enchufe):
    assert stop(authed, "w2:p9").status_code == 400
    assert enchufe.calls == []


@pytest.mark.parametrize("status", ["idle", "blocked", "done"])
def test_stop_not_working_409(authed, enchufe, status):
    aplicar_snapshot(enchufe, make_snapshot(status))
    r = stop(authed)
    assert r.status_code == 409 and r.json()["detail"] == "La sesión no está trabajando"
    assert enchufe.calls == []


def test_stop_herdr_error_502(authed, enchufe):
    aplicar_snapshot(enchufe, make_snapshot("working"))
    enchufe.fallas["interrumpir"] = NoTomado("boom")
    assert stop(authed).status_code == 502


def test_stop_bad_body_and_auth(authed, client):
    assert authed.post("/api/sessions/stop", json={"pane_id": "-x"}).status_code == 400
    assert authed.post("/api/sessions/stop", json={}).status_code == 400
    client.cookies.clear()
    assert client.post("/api/sessions/stop", json={"pane_id": "w1:p1"}).status_code == 401


def _proteger_uno(enchufe):
    snap = make_snapshot()
    next(w for w in snap["workspaces"] if w["workspace_id"] == "w1")["label"] = "Super orquestador"
    aplicar_snapshot(enchufe, snap)


@pytest.mark.parametrize("origen", ["manual", "jefe"])
def test_lo_que_mandas_o_confirmas_llega_al_workspace_protegido(authed, enchufe, origen):
    _proteger_uno(enchufe)
    assert post(authed, payload(origen=origen)).status_code == 200
    assert len(prompts(enchufe)) == 1


def test_origen_copiloto_valido():
    from orquestador.mensaje import MensajeBody

    b = MensajeBody(id="cop-12345678", pane_id="w1:p1", texto="hola", origen="copiloto")
    assert b.origen == "copiloto"


def _servicio(enchufe, tmp_path, llamadas):
    from orquestador.mensaje import MensajeService
    from orquestador.state import StateStore
    return MensajeService(enchufe, StateStore(tmp_path), al_escribir=llamadas.append)


def _cuerpo(origen, ident="abcdefgh"):
    from orquestador.mensaje import MensajeBody
    return MensajeBody(id=ident, pane_id="w1:p1", texto="hola", origen=origen, destino="Uno")


def test_send_avisa_al_escribir_con_el_pane(enchufe, tmp_path):
    llamadas = []
    s = _servicio(enchufe, tmp_path, llamadas)
    asyncio.run(s.execute(_cuerpo("mr-job")))
    assert llamadas == ["w1:p1"]


def test_send_que_falla_igual_marcaba_antes(enchufe, tmp_path):
    from orquestador.enchufe import TerminalesError
    llamadas = []
    s = _servicio(enchufe, tmp_path, llamadas)

    async def roto(*a, **k):
        raise TerminalesError("caído")

    enchufe.mandar_prompt = roto
    with pytest.raises(Exception):
        asyncio.run(s.execute(_cuerpo("mr-job")))
    assert llamadas == ["w1:p1"]


def test_send_de_ando_no_avisa_al_escribir(enchufe, tmp_path):
    llamadas = []
    s = _servicio(enchufe, tmp_path, llamadas)
    asyncio.run(s.execute(_cuerpo("manual")))
    assert llamadas == []


def test_send_sigue_si_al_escribir_falla(enchufe, tmp_path):
    from orquestador.mensaje import MensajeService
    from orquestador.state import StateStore

    def roto(pane):
        raise RuntimeError("x")

    s = MensajeService(enchufe, StateStore(tmp_path), al_escribir=roto)
    assert asyncio.run(s.execute(_cuerpo("mr-job")))["ok"] is True


def test_send_de_comentario_diff_no_avisa_al_escribir(enchufe, tmp_path):
    llamadas = []
    s = _servicio(enchufe, tmp_path, llamadas)
    asyncio.run(s.execute(_cuerpo("comentario-diff")))
    assert llamadas == []


def test_send_marca_el_pane_antes_de_mandar_el_prompt(enchufe, tmp_path):
    orden = []
    s = _servicio(enchufe, tmp_path, orden)
    original = enchufe.mandar_prompt

    async def espiado(*a, **k):
        orden.append("mandar")
        return await original(*a, **k)
    enchufe.mandar_prompt = espiado
    asyncio.run(s.execute(_cuerpo("mr-job")))
    assert orden == ["w1:p1", "mandar"]
