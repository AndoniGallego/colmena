"""«Pedirle a la sesión que actualice el MR»: mensaje fijo, solo si la sesión espera, sin contenido del usuario."""
import pytest

from orquestador.mrs import Gitlab, GitlabError, MrsService

from conftest import ORIGIN
from test_mrs import (FakeGit, FakeGlab, SID_A, SID_B, _ajustes_mrs, enchufe, glab, mclient, claude, repo, run,  # noqa: F401
                      svc)

TEXTO = "Actualizá el MR !1 con los últimos cambios de la rama: push y descripción si hace falta. Avisame antes del push."


def _board(*agentes):
    return {"workspaces": [{"workspace_id": "w1", "tabs": [{"tab_id": "t1", "agents": list(agentes)}]}]}


def _agente(sid, pane="w1:p1", status="idle"):
    return {"session_id": sid, "pane_id": pane, "status": status, "cwd": "/sin/repo"}


class Enviados:
    def __init__(self):
        self.items = []

    async def __call__(self, pane_id, texto, ident):
        self.items.append((pane_id, texto, ident))


@pytest.fixture
def listo(svc):
    run(svc.refresh())
    svc.estado["creados"]["7:1"] = SID_A
    svc.enviar = Enviados()
    return svc


def test_manda_el_texto_fijo_a_la_sesion_que_espera(listo):
    listo.board = lambda: _board(_agente(SID_A, "w1:p4", "idle"))
    out = run(listo.pedir_actualizacion(7, 1))
    assert out == {"ok": True}
    [(pane, texto, ident)] = listo.enviar.items
    assert (pane, texto) == ("w1:p4", TEXTO)
    assert 8 <= len(ident) <= 64


def test_sesion_hecha_tambien_espera(listo):
    listo.board = lambda: _board(_agente(SID_A, "w1:p4", "done"))
    run(listo.pedir_actualizacion(7, 1))
    assert len(listo.enviar.items) == 1


@pytest.mark.parametrize("status,texto", [("working", "trabajando"), ("blocked", "aprobación"), ("unknown", "esperando")])
def test_si_la_sesion_no_espera_da_409_y_no_manda(listo, status, texto):
    listo.board = lambda: _board(_agente(SID_A, "w1:p4", status))
    with pytest.raises(GitlabError) as exc:
        run(listo.pedir_actualizacion(7, 1))
    assert exc.value.status == 409 and texto in exc.value.detail
    assert listo.enviar.items == []


def test_sin_sesion_asociada_da_404(listo):
    listo.board = lambda: _board()
    with pytest.raises(GitlabError) as exc:
        run(listo.pedir_actualizacion(7, 1))
    assert exc.value.status == 404
    assert listo.enviar.items == []


def test_mr_fuera_de_la_lista_da_404(listo):
    listo.board = lambda: _board(_agente(SID_A))
    with pytest.raises(GitlabError) as exc:
        run(listo.pedir_actualizacion(7, 99))
    assert exc.value.status == 404
    assert listo.enviar.items == []


def test_elige_la_que_espera_si_el_creador_esta_ocupado(listo):
    listo.board = lambda: _board(_agente(SID_A, "w1:p1", "working"), _agente(SID_B, "w1:p2", "idle"))
    listo.estado["creados"].pop("7:1")
    listo.sesiones = _sesiones_fijas({SID_A: "7:1", SID_B: "7:1"})
    run(listo.pedir_actualizacion(7, 1))
    assert listo.enviar.items[0][0] == "w1:p2"


def _sesiones_fijas(valor):
    async def f():
        return valor
    return f


def test_no_repite_el_pedido_enseguida(listo):
    t = [100.0]
    listo.clock = lambda: t[0]
    listo.board = lambda: _board(_agente(SID_A, "w1:p4", "idle"))
    run(listo.pedir_actualizacion(7, 1))
    with pytest.raises(GitlabError) as exc:
        run(listo.pedir_actualizacion(7, 1))
    assert exc.value.status == 409 and len(listo.enviar.items) == 1
    t[0] += 60
    run(listo.pedir_actualizacion(7, 1))
    assert len(listo.enviar.items) == 2


def test_api_manda_a_la_terminal(mclient, svc, enchufe):
    run(svc.refresh())
    svc.estado["creados"]["7:1"] = SID_A
    svc.board = lambda: _board(_agente(SID_A, "w1:p1", "idle"))
    res = mclient.post("/api/mrs/7/1/pedir-actualizar", json={})
    assert res.status_code == 200 and res.json() == {"ok": True}
    assert [c for c in enchufe.calls if c[0] == "mandar_prompt"] == [("mandar_prompt", "w1:p1", TEXTO)]


def test_api_rechaza_origen_ajeno(mclient, svc, enchufe):
    run(svc.refresh())
    svc.estado["creados"]["7:1"] = SID_A
    svc.board = lambda: _board(_agente(SID_A, "w1:p1", "idle"))
    res = mclient.post("/api/mrs/7/1/pedir-actualizar", json={}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403
    assert [c for c in enchufe.calls if c[0] == "mandar_prompt"] == []


def test_api_no_acepta_texto_del_usuario(mclient, svc, enchufe):
    run(svc.refresh())
    svc.estado["creados"]["7:1"] = SID_A
    svc.board = lambda: _board(_agente(SID_A, "w1:p1", "idle"))
    res = mclient.post("/api/mrs/7/1/pedir-actualizar", json={"texto": "rm -rf"})
    assert res.status_code == 422
    assert [c for c in enchufe.calls if c[0] == "mandar_prompt"] == []


def test_api_estado_de_la_sesion_da_409(mclient, svc):
    run(svc.refresh())
    svc.estado["creados"]["7:1"] = SID_A
    svc.board = lambda: _board(_agente(SID_A, "w1:p1", "working"))
    res = mclient.post("/api/mrs/7/1/pedir-actualizar", json={})
    assert res.status_code == 409 and "trabajando" in res.json()["detail"]


def test_api_requiere_sesion(client):
    assert client.post("/api/mrs/7/1/pedir-actualizar", json={}).status_code in (401, 403)
