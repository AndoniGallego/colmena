import os
from pathlib import Path

import pytest

from conftest import ORIGIN, PIN, make_snapshot
from orquestador.enchufe.fake import FakeTerminales
from orquestador.enchufe.modelo import Espacio, Linea, Sesion, Tablero
from orquestador.enchufe.mux import Mux
from orquestador.nueva_terminal import enumerar_carpetas, grupos_desde_tablero, validar_carpeta

ID1 = "abcdefgh1"


@pytest.fixture
def mux_enchufe():
    g = FakeTerminales(nombre="guardian")
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    return Mux([h, g], nuevas_en="guardian"), g, h


@pytest.fixture
def app_mux(app, mux_enchufe):
    mux, _, _ = mux_enchufe
    app.state.hub.enchufe = mux
    app.state.tacciones.enchufe = mux
    return app


@pytest.fixture
def authed_mux(app_mux):
    with __import__("fastapi").testclient.TestClient(
        app_mux, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)
    ) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def _roots(tmp_path, monkeypatch, cfg):
    base = tmp_path / "Proyectos"
    base.mkdir()
    (base / "orq").mkdir()
    (base / ".oculta").mkdir()
    afuera = tmp_path / "afuera"
    afuera.mkdir()
    (base / "link").symlink_to(afuera)
    cfg.plan_cwds = [str(base) + "/*"]
    return base


def test_enumerar_glob_sin_ocultas_ni_symlinks(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    base = tmp_path / "P"
    (base / "real").mkdir(parents=True)
    (base / ".oculta").mkdir()
    (base / "link").symlink_to(tmp_path)
    out = enumerar_carpetas([str(base) + "/*"])
    reals = {os.path.realpath(str(base / "real"))}
    assert {c["nombre"] for c in out} == {"real"}
    assert len(out) == 1
    assert os.path.realpath(os.path.expanduser(out[0]["ruta"])) in reals


def test_carpeta_fuera_lista_400(authed_mux, tmp_path, cfg):
    otro = tmp_path / "otro"
    otro.mkdir()
    cfg.plan_cwds = [str(otro)]
    r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(tmp_path / "nada"), "tipo": "shell", "id": ID1})
    assert r.status_code == 400 and r.json()["detail"] == "Esa carpeta no está permitida"


def test_puntos_suspensivos_escapan_400(authed_mux, tmp_path, cfg):
    base = tmp_path / "base"
    base.mkdir()
    otro = tmp_path / "otro"
    otro.mkdir()
    cfg.plan_cwds = [str(base)]
    r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base / ".." / "otro"), "tipo": "shell", "id": ID1})
    assert r.status_code == 400 and r.json()["detail"] == "Esa carpeta no está permitida"


def test_symlink_afuera_400(authed_mux, tmp_path, cfg):
    base = tmp_path / "base"
    base.mkdir()
    afuera = tmp_path / "afuera"
    afuera.mkdir()
    (base / "atajo").symlink_to(afuera)
    cfg.plan_cwds = [str(base)]
    r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base / "atajo"), "tipo": "shell", "id": ID1})
    assert r.status_code == 400 and r.json()["detail"] == "Esa carpeta no está permitida"


def test_tope_seis_por_hora_429(authed_mux, tmp_path, cfg, mux_enchufe):
    _, g, h = mux_enchufe
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    for i in range(6):
        rid = f"abcdefgh{i}"
        r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base), "tipo": "shell", "id": rid})
        assert r.status_code == 200, r.text
    r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base), "tipo": "shell", "id": "abcdefgh9"})
    assert r.status_code == 429
    assert "retry" in r.json()["detail"].lower() or r.headers.get("Retry-After")
    assert len(g.calls_of("crear_espacio")) == 6
    assert len(h.calls_of("crear_espacio")) == 0


def test_mismo_id_idempotente(authed_mux, tmp_path, cfg, mux_enchufe):
    _, g, _ = mux_enchufe
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    body = {"carpeta": str(base), "tipo": "shell", "id": ID1}
    a = authed_mux.post("/api/terminales/nueva", json=body).json()
    b = authed_mux.post("/api/terminales/nueva", json=body).json()
    assert a == b
    assert len(g.calls_of("crear_espacio")) == 1


def test_shell_solo_crear_espacio(authed_mux, tmp_path, cfg, mux_enchufe):
    _, g, h = mux_enchufe
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base), "tipo": "shell", "id": ID1})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert g.calls_of("crear_espacio") and not g.calls_of("arrancar_claude")
    assert not h.calls_of("crear_espacio")


def test_claude_crea_y_arranca(authed_mux, tmp_path, cfg, mux_enchufe):
    _, g, h = mux_enchufe
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base), "tipo": "claude", "nombre": "Mi Proy", "id": ID1})
    assert r.status_code == 200
    assert len(g.calls_of("crear_espacio")) == 1
    assert len(g.calls_of("arrancar_claude")) == 1
    assert not h.calls_of("crear_espacio")
    assert g.calls_of("arrancar_claude")[0][3] is None
    assert g.calls_of("arrancar_claude")[0][2] == "mi-proy"


def test_guardian_caido_503_sin_herdr(authed_mux, tmp_path, cfg, mux_enchufe):
    _, g, h = mux_enchufe
    g.caer()
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base), "tipo": "shell", "id": ID1})
    assert r.status_code == 503
    assert r.json()["detail"] == "Las terminales propias no responden: no abrí nada"
    assert not h.calls_of("crear_espacio")


def test_nombre_control_o_largo(authed_mux, tmp_path, cfg):
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base), "tipo": "shell", "nombre": "a" * 61, "id": ID1})
    assert r.status_code in (400, 422)
    r2 = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base), "tipo": "shell", "nombre": "hola\x00", "id": "abcdefgh2"})
    assert r2.status_code in (400, 422)


def test_get_carpetas(authed_mux, tmp_path, cfg):
    base = _roots(tmp_path, None, cfg)
    r = authed_mux.get("/api/terminales/carpetas")
    assert r.status_code == 200
    nombres = {c["nombre"] for c in r.json()["carpetas"]}
    assert nombres == {"orq"}
    assert ".oculta" not in nombres and "link" not in nombres


def test_hardening_sin_sesion(client):
    assert client.get("/api/terminales/carpetas").status_code == 401
    assert client.post("/api/terminales/nueva", json={}).status_code == 401


def test_nueva_sin_escritura_apagada(authed_mux, tmp_path, cfg):
    cfg.terminales_escritura = False
    base = tmp_path / "p"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base), "tipo": "shell", "id": ID1})
    assert r.status_code == 200


def test_validar_carpeta_resuelve_tilde(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    proj = home / "Proyectos" / "x"
    proj.mkdir(parents=True)
    cfg_roots = [str(home / "Proyectos") + "/*"]
    real = validar_carpeta("~/Proyectos/x", cfg_roots)
    assert real == os.path.realpath(proj)


def test_claude_no_arranca_avisa_que_la_terminal_quedo(authed_mux, tmp_path, cfg, mux_enchufe):
    from orquestador.enchufe import TerminalesError

    _, g, _ = mux_enchufe
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]

    async def falla(*_a, **_k):
        raise TerminalesError("no arrancó")

    g.arrancar_claude = falla
    r = authed_mux.post("/api/terminales/nueva", json={"carpeta": str(base), "tipo": "claude", "id": ID1})
    assert r.status_code == 503
    assert r.json()["detail"] == "Abrí la terminal pero Claude no arrancó: podés arrancarlo desde ahí"
    assert len(g.calls_of("crear_espacio")) == 1


def _tablero_g(*partes):
    espacios, lineas, sesiones = [], [], []
    for eid, nombre, cwd in partes:
        lid, sid = f"{eid}:t1", f"{eid}:p1"
        espacios.append(Espacio(eid, nombre, (lid,)))
        lineas.append(Linea(lid, eid, nombre, (sid,)))
        sesiones.append(
            Sesion(sid, lid, eid, "shell", "idle", "guardian", None, cwd, None, "", None, "guardian")
        )
    return Tablero(tuple(espacios), tuple(lineas), tuple(sesiones), 0)


def test_grupos_desde_tablero_carpeta_solo_si_permitida(tmp_path, cfg):
    base = tmp_path / "proj"
    base.mkdir()
    afuera = tmp_path / "afuera"
    afuera.mkdir()
    tab = _tablero_g(("g1", "Alpha", str(base)), ("g2", "Beta", str(afuera)))
    gs = grupos_desde_tablero(tab, [str(base)])
    assert [g["id"] for g in gs] == ["g1", "g2"]
    assert gs[0]["carpeta"] is not None
    assert os.path.realpath(os.path.expanduser(gs[0]["carpeta"])) == os.path.realpath(base)
    assert gs[1]["carpeta"] is None


def test_get_carpetas_incluye_grupos_solo_guardian(authed_mux, tmp_path, cfg, mux_enchufe):
    _, g, h = mux_enchufe
    base = _roots(tmp_path, None, cfg)
    cwd_ok = str(base / "orq")
    g.tablero_actual = _tablero_g(("g1", "Grupo A", cwd_ok), ("g2", "Grupo B", str(tmp_path / "x")))
    r = authed_mux.get("/api/terminales/carpetas")
    assert r.status_code == 200
    data = r.json()
    assert {c["nombre"] for c in data["carpetas"]} == {"orq"}
    from orquestador.nueva_terminal import _display_path

    esperado_carpeta = _display_path(os.path.realpath(cwd_ok))
    assert data["grupos"] == [
        {"id": "g1", "nombre": "Grupo A", "carpeta": esperado_carpeta},
        {"id": "g2", "nombre": "Grupo B", "carpeta": None},
    ]
    assert not any(x["id"].startswith("w") for x in data["grupos"])
    assert h.tablero_actual.espacios and all(e.id.startswith("w") for e in h.tablero_actual.espacios)


def test_get_carpetas_guardian_caido_grupos_vacios(authed_mux, tmp_path, cfg, mux_enchufe):
    _, g, _ = mux_enchufe
    g.caer()
    base = _roots(tmp_path, None, cfg)
    r = authed_mux.get("/api/terminales/carpetas")
    assert r.status_code == 200
    assert r.json()["grupos"] == []
    assert {c["nombre"] for c in r.json()["carpetas"]} == {"orq"}


def test_nueva_en_grupo_existente_crea_linea(authed_mux, tmp_path, cfg, mux_enchufe):
    _, g, h = mux_enchufe
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    g.tablero_actual = _tablero_g(("g1", "Ya", str(base)))
    r = authed_mux.post(
        "/api/terminales/nueva",
        json={"carpeta": str(base), "tipo": "shell", "id": ID1, "grupo": "g1"},
    )
    assert r.status_code == 200 and r.json()["espacio_id"] == "g1"
    assert g.calls_of("crear_linea") == [("crear_linea", "g1", "proj", str(base),)]
    assert not g.calls_of("crear_espacio")
    assert not h.calls_of("crear_espacio") and not h.calls_of("crear_linea")


def test_nueva_en_grupo_claude_arranca(authed_mux, tmp_path, cfg, mux_enchufe):
    _, g, _ = mux_enchufe
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    g.tablero_actual = _tablero_g(("g3", "Cosas", str(base)))
    r = authed_mux.post(
        "/api/terminales/nueva",
        json={"carpeta": str(base), "tipo": "claude", "nombre": "Mi Proy", "id": "abcdefgh3", "grupo": "g3"},
    )
    assert r.status_code == 200
    assert len(g.calls_of("crear_linea")) == 1 and not g.calls_of("crear_espacio")
    assert len(g.calls_of("arrancar_claude")) == 1


def test_nueva_grupo_inexistente_409(authed_mux, tmp_path, cfg, mux_enchufe):
    _, g, h = mux_enchufe
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    r = authed_mux.post(
        "/api/terminales/nueva",
        json={"carpeta": str(base), "tipo": "shell", "id": ID1, "grupo": "g9"},
    )
    assert r.status_code == 409 and r.json()["detail"] == "Ese grupo ya no está: no abrí nada"
    assert not g.calls_of("crear_linea") and not g.calls_of("crear_espacio")
    assert not h.calls_of("crear_espacio")


@pytest.mark.parametrize("grupo", ["w1", "gx", "g", "g1234567", "g1:t1"])
def test_nueva_grupo_mal_formado_422(authed_mux, tmp_path, cfg, grupo):
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    r = authed_mux.post(
        "/api/terminales/nueva",
        json={"carpeta": str(base), "tipo": "shell", "id": ID1, "grupo": grupo},
    )
    assert r.status_code == 400 and r.json()["detail"] == "cuerpo inválido"


def test_mismo_id_en_paralelo_abre_una_sola(app_mux, tmp_path, cfg, mux_enchufe):
    import asyncio

    from orquestador import terminales_acciones as tacc

    _, g, _ = mux_enchufe
    base = tmp_path / "proj"
    base.mkdir()
    cfg.plan_cwds = [str(base)]
    original = g.crear_espacio

    async def lento(nombre, cwd):
        await asyncio.sleep(0.01)
        return await original(nombre, cwd)

    g.crear_espacio = lento
    acc = app_mux.state.tacciones
    body = tacc.NuevaBody(id=ID1, carpeta=str(base), tipo="shell")

    async def dos():
        return await asyncio.gather(acc.nueva(tacc.Ctx(), body), acc.nueva(tacc.Ctx(), body),
                                    return_exceptions=True)

    res = asyncio.run(dos())
    assert len(g.calls_of("crear_espacio")) == 1
    assert sum(1 for x in res if isinstance(x, dict)) == 1
    assert any(isinstance(x, tacc.TraspasoError) and x.status == 409 for x in res)


def _repo_falso(tmp_path):
    raiz = tmp_path / "colmena"
    (raiz / ".git" / "worktrees" / "wt1").mkdir(parents=True)
    (raiz / "backend").mkdir()
    wt = tmp_path / "colmena-a"
    (wt / "backend" / "x").mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {raiz / '.git' / 'worktrees' / 'wt1'}\n")
    return raiz, wt


def test_es_repo_colmena_raiz_subcarpeta_y_worktree(tmp_path, monkeypatch):
    from orquestador import config
    from orquestador.nueva_terminal import es_repo_colmena

    raiz, wt = _repo_falso(tmp_path)
    monkeypatch.setattr(config, "REPO_ROOT", raiz)
    assert es_repo_colmena(str(raiz))
    assert es_repo_colmena(str(raiz / "backend"))
    assert es_repo_colmena(str(wt))
    assert es_repo_colmena(str(wt / "backend" / "x"))
    # Desde un worktree de Colmena (REPO_ROOT es el worktree) la raíz principal también cuenta.
    monkeypatch.setattr(config, "REPO_ROOT", wt)
    assert es_repo_colmena(str(raiz / "backend"))
    assert es_repo_colmena(str(wt))


def test_no_es_repo_colmena_otro_repo(tmp_path, monkeypatch):
    from orquestador import config
    from orquestador.nueva_terminal import es_repo_colmena

    raiz, _ = _repo_falso(tmp_path)
    monkeypatch.setattr(config, "REPO_ROOT", raiz)
    otro = tmp_path / "otro"
    (otro / ".git" / "worktrees" / "w").mkdir(parents=True)
    otro_wt = tmp_path / "otro-wt"
    otro_wt.mkdir()
    (otro_wt / ".git").write_text(f"gitdir: {otro / '.git' / 'worktrees' / 'w'}\n")
    engano = tmp_path / "colmena-engano"
    engano.mkdir()
    (engano / ".git").write_text(f"gitdir: {tmp_path / 'colmena-x' / '.git' / 'worktrees' / 'w'}\n")
    assert not es_repo_colmena(str(otro))
    assert not es_repo_colmena(str(otro_wt))
    assert not es_repo_colmena(str(engano))
    assert not es_repo_colmena(str(tmp_path))
