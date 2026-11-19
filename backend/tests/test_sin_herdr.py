import os
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN
from orquestador.app import create_app
from orquestador.enchufe import FakeTerminales, Mux, crear_terminales
from orquestador.enchufe import guardian as guardian_mod
from orquestador.enchufe.herdr import herdr_instalado
from orquestador.state import StateStore
from orquestador.traspaso import MESSAGE


class GuardianFalso(FakeTerminales):
    """Como el guardián real: la línea pasa a ser un agente Claude al arrancarlo."""

    async def arrancar_claude(self, sesion_id, nombre, resume=None):
        await super().arrancar_claude(sesion_id, nombre, resume)
        sesiones = tuple(
            replace(s, programa="claude", agente="claude", es_agente=True, nombre_agente=nombre,
                    backend="guardian", estado_fuente="guardian") if s.id == sesion_id else s
            for s in self.tablero_actual.sesiones)
        self.cambiar(sesiones=sesiones)


@pytest.fixture
def guardian_falso(monkeypatch):
    creados: list[FakeTerminales] = []

    def fabrica(ruta, *a, **kw):
        g = GuardianFalso(nombre="guardian", poll=0.01)
        g.proximos_ids = [("g1", "g1:t1", "g1:p1")]
        creados.append(g)
        return g

    monkeypatch.setattr(guardian_mod, "ClienteGuardian", fabrica)
    return creados


def test_herdr_instalado_sin_binario(cfg):
    assert herdr_instalado(cfg) is None
    cfg.herdr_bin = "/nonexistent/herdr"
    assert herdr_instalado(cfg) is None


def test_sin_herdr_solo_guardian(cfg, guardian_falso):
    m = crear_terminales(cfg)
    assert isinstance(m, Mux)
    assert [b.nombre for b in m.backends] == ["guardian"]
    assert m.nuevas_en == "guardian"


def test_backends_sin_herdr_por_config(cfg, guardian_falso, herdr):
    cfg.terminales = {"backends": ["guardian"]}
    m = crear_terminales(cfg, cliente=herdr)
    assert [b.nombre for b in m.backends] == ["guardian"] and m.nuevas_en == "guardian"


def test_backends_invalidos_sin_herdr_igual_arranca(cfg, guardian_falso):
    cfg.terminales = {"backends": ["herdr"], "nuevas_en": "herdr"}
    m = crear_terminales(cfg)
    assert [b.nombre for b in m.backends] == ["guardian"] and m.nuevas_en == "guardian"


def test_con_herdr_inyectado_sigue_igual(cfg, herdr):
    m = crear_terminales(cfg, cliente=herdr)
    assert [b.nombre for b in m.backends] == ["herdr"] and m.nuevas_en == "herdr"


def test_app_arranca_y_anda_sin_herdr(cfg, tmp_path, handoffs, guardian_falso, anti_herdr):
    app = create_app(cfg, b"secret", StateStore(tmp_path), dist=tmp_path / "nodist",
                     handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads")
    brief = handoffs / "2026-11-03-x.md"
    brief.write_text("# Traspaso")
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        r = c.get("/api/board")
        assert r.status_code == 200
        assert "herdr" not in r.text.lower()

        r = c.post("/api/traspaso/execute", json={
            "origen": "Uno", "destino": "Nuevo", "por_que": "x", "resumen_brief": "y",
            "destino_tipo": "workspace_nuevo", "workspace_id": None, "label": "Nuevo", "cwd": os.environ["HOME"],
            "agent_name": "nuevo", "brief_path": str(brief)})
        assert r.status_code == 200, r.text
        assert r.json()["pane_id"] == "g1:p1"

        r = c.post("/api/mensaje/execute", json={
            "id": "0b6f1c1e-4a55-4e1d-9d33-1f3c2a7d9e10", "pane_id": "g1:p1", "texto": "hola",
            "origen": "manual", "destino": "Nuevo (g1:p1)", "por_que": "x"})
        assert r.status_code == 200, r.text

    g = guardian_falso[0]
    assert g.calls_of("crear_espacio") == [("crear_espacio", "Nuevo", os.path.realpath(os.environ["HOME"]))]
    assert ("mandar_prompt", "g1:p1", MESSAGE.format(path=str(brief))) in g.calls
    assert ("mandar_prompt", "g1:p1", "hola") in g.calls
    assert anti_herdr == []
