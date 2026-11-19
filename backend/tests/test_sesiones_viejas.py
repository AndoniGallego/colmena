import json
import time
import uuid
from pathlib import Path

import pytest
from conftest import ORIGIN, PIN, make_snapshot
from orquestador.enchufe.fake import FakeTerminales
from orquestador.enchufe.modelo import Espacio, Linea, Lanzamiento, Sesion, Tablero
from orquestador.enchufe.mux import Mux
from orquestador.nueva_terminal import validar_carpeta
from orquestador.sesiones_viejas import SesionesViejas
from orquestador.uso_claude import project_key

from test_mudanza import FakeGuardian

ID1 = "abcdefgh1"
SID = "6f1c1e0b-4a55-4e1d-9d33-1f3c2a7d9e10"
SID2 = "7a2d2f1c-5b66-4f2e-8e44-2a4d3b8e0f21"
SID_VIEJO = "8b3e3a2d-6c77-4a3f-9f55-3b5e4c9f1a32"


def _jsonl(path: Path, *, cwd: str, titulo_summary: str | None = None, primer_user: str = "hola",
           ultima: str = "última frase", ts: str = "2026-01-15T12:00:00Z"):
    lines = []
    if titulo_summary:
        lines.append({"type": "summary", "summary": titulo_summary})
    lines.append({"type": "user", "message": {"content": primer_user}, "cwd": cwd, "timestamp": ts})
    lines.append({"type": "assistant", "message": {"content": [{"type": "text", "text": ultima}]},
                  "cwd": cwd, "timestamp": "2026-01-15T12:01:00Z"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def _svc(tmp_path, cfg, projects, data_dir, abiertas=None, excluir_sid=None):
    base = tmp_path / "proj"
    base.mkdir(exist_ok=True)
    cfg.plan_cwds = [str(base)]
    # Nombre de carpeta bajo projects_dir sin prefijo -tmp- (DIR_EXCLUIDO en producción).
    folder = "home-cc-proj"
    p1 = projects / folder / f"{SID}.jsonl"
    _jsonl(p1, cwd=str(base), titulo_summary="Desde summary")
    p2 = projects / folder / f"{SID2}.jsonl"
    _jsonl(p2, cwd=str(base), primer_user="primer mensaje largo", ultima="respuesta claude")
    fuera = tmp_path / "afuera"
    fuera.mkdir()
    _jsonl(projects / "-otro" / f"{SID_VIEJO}.jsonl", cwd=str(fuera))
    ctx_key = project_key(data_dir / "context")
    _jsonl(projects / ctx_key / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl", cwd=str(base))
    now = time.time()
    viejo_path = projects / folder / "11111111-2222-3333-4444-555555555555.jsonl"
    _jsonl(viejo_path, cwd=str(base))
    old_ts = now - 31 * 86400
    for path in (viejo_path,):
        import os
        os.utime(path, (old_ts, old_ts))
    excl = set()
    if excluir_sid:
        excl.add(excluir_sid)
    return SesionesViejas(
        projects,
        plan_cwds=lambda: cfg.plan_cwds,
        excluir_carpetas=(project_key(data_dir / "context"), project_key(data_dir / "mrs-claude")),
        sesiones_excluir=lambda: excl,
        abiertas=abiertas or (lambda: set()),
        clock=lambda: now,
    )


@pytest.fixture
def mux_guardian():
    tab = Tablero(
        (Espacio("g1", "Uno", ("g1:t1",)),),
        (Linea("g1:t1", "g1", "Uno", ("g1:p1",)),),
        (Sesion("g1:p1", "g1:t1", "g1", "claude", "idle", "guardian", SID, "/x", None, "a", None, "guardian"),),
        0,
    )
    g = FakeGuardian(tab)
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    return Mux([h, g], nuevas_en="guardian"), g


@pytest.fixture
def app_mux(app, mux_guardian):
    mux, _ = mux_guardian
    app.state.hub.enchufe = mux
    app.state.tacciones.enchufe = mux
    return app


@pytest.fixture
def authed_mux(app_mux):
    from fastapi.testclient import TestClient
    with TestClient(app_mux, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def test_lista_solo_30_dias(tmp_path, cfg, projects):
    svc = _svc(tmp_path, cfg, projects, tmp_path)
    out = svc.listar()
    ids = {r["session_id"] for r in out}
    assert SID in ids and SID2 in ids
    assert "11111111-2222-3333-4444-555555555555" not in ids


def test_excluye_carpeta_no_permitida(tmp_path, cfg, projects):
    svc = _svc(tmp_path, cfg, projects, tmp_path)
    assert SID_VIEJO not in {r["session_id"] for r in svc.listar()}


def test_excluye_colmena_carpeta(tmp_path, cfg, projects):
    svc = _svc(tmp_path, cfg, projects, tmp_path)
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" not in {r["session_id"] for r in svc.listar()}


def test_excluye_abiertas(tmp_path, cfg, projects):
    svc = _svc(tmp_path, cfg, projects, tmp_path, abiertas=lambda: {SID})
    assert SID not in {r["session_id"] for r in svc.listar()}


def test_filtro_q(tmp_path, cfg, projects):
    svc = _svc(tmp_path, cfg, projects, tmp_path)
    assert svc.listar("summary")[0]["session_id"] == SID
    assert not svc.listar("zzz-inexistente")


def test_titulo_summary_o_primer_mensaje(tmp_path, cfg, projects):
    svc = _svc(tmp_path, cfg, projects, tmp_path)
    by = {r["session_id"]: r for r in svc.listar()}
    assert by[SID]["titulo"] == "Desde summary"
    assert "primer" in by[SID2]["titulo"].casefold()


def test_get_api(authed_mux, tmp_path, cfg, projects):
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    _jsonl(projects / "home-cc-proj" / f"{SID}.jsonl", cwd=str(base), titulo_summary="API")
    r = authed_mux.get("/api/sesiones/viejas")
    assert r.status_code == 200
    assert any(x["session_id"] == SID for x in r.json())


def test_retomar_grupo_existente(authed_mux, tmp_path, cfg, projects, mux_guardian):
    _, g = mux_guardian
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    _jsonl(projects / "home-cc-proj" / f"{SID2}.jsonl", cwd=str(base))
    body = {"id": ID1, "session_id": SID2, "nombre": "Retomada", "grupo": "g1"}
    r = authed_mux.post("/api/sesiones/viejas/retomar", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    calls = g.calls_of("crear_linea")
    assert calls and calls[-1][4] == "claude" and calls[-1][5] == SID2


def test_retomar_tarjeta_nueva(authed_mux, tmp_path, cfg, projects, mux_guardian):
    _, g = mux_guardian
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    _jsonl(projects / "home-cc-proj" / f"{SID2}.jsonl", cwd=str(base))
    body = {"id": "abcdefgh2", "session_id": SID2, "nombre": "Pestaña", "nombre_tarjeta": "Tarjeta X"}
    r = authed_mux.post("/api/sesiones/viejas/retomar", json=body)
    assert r.status_code == 200
    assert g.calls_of("arrancar_claude")[-1][3] == SID2


def test_409_ya_abierta(authed_mux, tmp_path, cfg, projects, mux_guardian):
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    _jsonl(projects / "home-cc-proj" / f"{SID}.jsonl", cwd=str(base))
    body = {"id": "abcdefgh3", "session_id": SID, "nombre": "x", "grupo": "g1"}
    r = authed_mux.post("/api/sesiones/viejas/retomar", json=body)
    assert r.status_code == 409
    assert "abierta" in r.json()["detail"].casefold()


def test_429_tope(authed_mux, tmp_path, cfg, projects, mux_guardian):
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    _jsonl(projects / "home-cc-proj" / f"{SID2}.jsonl", cwd=str(base))
    for i in range(6):
        rid = f"abcdefg{i}"
        authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base), "tipo": "shell", "id": rid})
    body = {"id": "abcdefgh8", "session_id": SID2, "nombre": "x", "grupo": "g1"}
    r = authed_mux.post("/api/sesiones/viejas/retomar", json=body)
    assert r.status_code == 429


def test_404_inexistente(authed_mux, tmp_path, cfg, projects):
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee01"
    r = authed_mux.post("/api/sesiones/viejas/retomar",
                        json={"id": "abcdefgh4", "session_id": sid, "nombre": "x", "grupo": "g1"})
    assert r.status_code == 404


def test_400_carpeta_no_permitida_retomar(authed_mux, tmp_path, cfg, projects):
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    afuera = tmp_path / "afuera"
    afuera.mkdir()
    sid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    _jsonl(projects / "home-cc-proj" / f"{sid}.jsonl", cwd=str(afuera))
    r = authed_mux.post("/api/sesiones/viejas/retomar",
                        json={"id": "abcdefgh5", "session_id": sid, "nombre": "x", "grupo": "g1"})
    assert r.status_code in (400, 404)


def test_uuid_invalido_422(authed_mux):
    r = authed_mux.post("/api/sesiones/viejas/retomar",
                        json={"id": ID1, "session_id": "no-es-uuid", "nombre": "x", "grupo": "g1"})
    assert r.status_code == 422
