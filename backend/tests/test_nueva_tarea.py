import pytest

from orquestador.nueva_tarea import nombre_pestana, rama_para, slug_de, ticket_de


def test_slug_kebab_sin_acentos_ni_simbolos():
    assert slug_de("Arreglar el botón de «Enviar» en móvil!") == "arreglar-el-boton-de-enviar-en-movil"


def test_slug_largo_corta_en_40_sin_guion_final():
    s = slug_de("una tarea con muchísimas palabras largas largas largas largas largas")
    assert 0 < len(s) <= 40 and not s.endswith("-") and not s.startswith("-")


def test_slug_vacio_o_solo_simbolos_cae_a_tarea():
    assert slug_de("¡¡¡???") == "tarea"


def test_ticket_se_detecta():
    assert ticket_de("Resolver ABC-123 del checkout") == "ABC-123"
    assert ticket_de("sin ticket acá") is None
    assert ticket_de("ABC-1234567 no") is None


def test_nombre_pestana_primeras_palabras():
    assert nombre_pestana("Arreglar el botón de enviar en el celu cuando se rota la pantalla") == "Arreglar el botón de enviar en"
    assert nombre_pestana("  \n  ") == "Tarea"


@pytest.mark.parametrize("repo,tarea,esperada", [
    ("orquestador", "Mejorar la hoja", "feature/kit-mejorar-la-hoja"),
    ("andokit", "Mejorar la hoja", "feature/mejorar-la-hoja"),
    ("tienda", "Mejorar la hoja", "feature/mejorar-la-hoja"),
    ("tienda", "Arreglar SITE-42 ya", "feature/SITE-42"),
    ("orquestador", "Arreglar SITE-42 ya", "feature/SITE-42"),
])
def test_rama_para(repo, tarea, esperada):
    assert rama_para(repo, tarea) == esperada


def test_repos_kit_solo_orquestador():
    from orquestador import nueva_tarea
    assert nueva_tarea.REPOS_KIT == frozenset({"orquestador"})


# ---------- git real en repos temporales ----------
import os
import subprocess
from pathlib import Path

from orquestador.nueva_tarea import (base_por_defecto, crear_worktree, es_raiz_repo, quitar_recien_creado,
                                     ruta_libre, validar_rama)
from orquestador.traspaso import TraspasoError


def _git(cwd, *args):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    r = tmp_path / "proy"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "a.txt").write_text("a")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "uno")
    return r


@pytest.mark.parametrize("malo", ["", "-x", "feature/../x", "a b", "feature/x;rm", "feature//x", "feature/x.lock",
                                  "feature/.x", "x" * 81, "feature/x/", "feature/x\n", "@", "a..b"])
def test_validar_rama_rechaza(malo):
    with pytest.raises(TraspasoError) as e:
        validar_rama(malo)
    assert e.value.status == 400


@pytest.mark.parametrize("bueno", ["feature/kit-x", "feature/SITE-42", "fix/a_b.c"])
def test_validar_rama_acepta(bueno):
    assert validar_rama(bueno) == bueno


def test_es_raiz_repo(repo, tmp_path):
    assert es_raiz_repo(str(repo))
    (repo / "sub").mkdir()
    assert not es_raiz_repo(str(repo / "sub"))
    assert not es_raiz_repo(str(tmp_path))


def test_base_cae_a_main_sin_origin(repo):
    assert base_por_defecto(str(repo)) == "main"


def test_base_usa_origin_head(repo, tmp_path):
    otro = tmp_path / "remoto"
    _git(tmp_path, "clone", "-q", str(repo), str(otro))
    assert base_por_defecto(str(otro)) == "origin/main"


def test_base_master_si_no_hay_main(tmp_path):
    r = tmp_path / "m"
    r.mkdir()
    _git(r, "init", "-q", "-b", "master")
    (r / "a").write_text("a")
    _git(r, "add", ".")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x")
    assert base_por_defecto(str(r)) == "master"


def test_ruta_libre_hermana_y_sufijo(repo):
    assert ruta_libre(str(repo), "mi-tarea") == str(repo.parent / "proy-mi-tarea")
    (repo.parent / "proy-mi-tarea").mkdir()
    assert ruta_libre(str(repo), "mi-tarea") == str(repo.parent / "proy-mi-tarea-2")
    (repo.parent / "proy-mi-tarea-2").mkdir()
    assert ruta_libre(str(repo), "mi-tarea") == str(repo.parent / "proy-mi-tarea-3")


def test_crear_worktree_crea_rama_y_carpeta_sin_upstream(repo):
    ruta = str(repo.parent / "proy-x")
    crear_worktree(str(repo), "feature/x", ruta, "main")
    assert (Path(ruta) / "a.txt").exists()
    assert _git(ruta, "rev-parse", "--abbrev-ref", "HEAD") == "feature/x"
    assert subprocess.run(["git", "config", "branch.feature/x.merge"], cwd=repo, capture_output=True).returncode != 0


def test_crear_worktree_rama_existente_409(repo):
    _git(repo, "branch", "feature/x")
    with pytest.raises(TraspasoError) as e:
        crear_worktree(str(repo), "feature/x", str(repo.parent / "proy-x"), "main")
    assert e.value.status == 409
    assert not (repo.parent / "proy-x").exists()


def test_quitar_recien_creado_borra_carpeta_y_rama(repo):
    ruta = str(repo.parent / "proy-x")
    crear_worktree(str(repo), "feature/x", ruta, "main")
    quitar_recien_creado(str(repo), "feature/x", ruta, "main")
    assert not Path(ruta).exists()
    assert "feature/x" not in _git(repo, "branch", "--list")


# ---------- registro y limpieza ----------
import json

from orquestador.nueva_tarea import Worktrees, borrar_copia, estado_copia


def _tarea(repo, rama="feature/x", base="main"):
    ruta = str(repo.parent / "proy-x")
    crear_worktree(str(repo), rama, ruta, base)
    return {"ruta": ruta, "repo": str(repo), "rama": rama, "base": base}


def test_registro_persiste_y_es_privado(tmp_path):
    w = Worktrees(tmp_path)
    w.agregar({"ruta": "/a/b", "repo": "/a", "rama": "feature/x", "base": "main"})
    w2 = Worktrees(tmp_path)
    assert w2.rutas() == ["/a/b"]
    assert w2.get("/a/b")["rama"] == "feature/x"
    archivo = next(tmp_path.glob("*.json"))
    assert oct(archivo.stat().st_mode & 0o777) == "0o600"
    w2.quitar("/a/b")
    assert Worktrees(tmp_path).rutas() == []


def test_registro_tolera_archivo_roto(tmp_path):
    (tmp_path / "nueva-tarea-worktrees.json").write_text("{no json")
    w = Worktrees(tmp_path)
    assert w.rutas() == []
    w.agregar({"ruta": "/a/b", "repo": "/a", "rama": "r", "base": "main"})
    assert w.rutas() == ["/a/b"]


def test_copia_sin_cambios_y_sin_commits_propios_es_borrable(repo):
    e = _tarea(repo)
    assert estado_copia(e) == {"borrable": True, "motivo": ""}


def test_copia_con_cambios_sin_guardar_no_borrable(repo):
    e = _tarea(repo)
    (Path(e["ruta"]) / "nuevo.txt").write_text("x")
    est = estado_copia(e)
    assert est["borrable"] is False and "cambios sin guardar" in est["motivo"]


def test_copia_con_commit_sin_mergear_no_borrable(repo):
    e = _tarea(repo)
    (Path(e["ruta"]) / "b.txt").write_text("b")
    _git(e["ruta"], "add", ".")
    _git(e["ruta"], "commit", "-q", "-m", "dos")
    est = estado_copia(e)
    assert est["borrable"] is False and "no está mergeada" in est["motivo"]


def test_copia_con_rama_mergeada_es_borrable(repo):
    e = _tarea(repo)
    (Path(e["ruta"]) / "b.txt").write_text("b")
    _git(e["ruta"], "add", ".")
    _git(e["ruta"], "commit", "-q", "-m", "dos")
    _git(repo, "merge", "-q", "--ff-only", "feature/x")
    assert estado_copia(e)["borrable"] is True


def test_borrar_copia_quita_carpeta_pero_deja_la_rama(repo):
    e = _tarea(repo)
    borrar_copia(e)
    assert not Path(e["ruta"]).exists()
    assert "feature/x" in _git(repo, "branch", "--list")


def test_borrar_copia_no_borra_si_hay_cambios(repo):
    e = _tarea(repo)
    (Path(e["ruta"]) / "nuevo.txt").write_text("x")
    with pytest.raises(TraspasoError) as err:
        borrar_copia(e)
    assert err.value.status == 409
    assert (Path(e["ruta"]) / "nuevo.txt").exists()


def test_copia_ya_borrada_no_es_borrable_con_motivo(repo):
    e = _tarea(repo)
    borrar_copia(e)
    est = estado_copia(e)
    assert est["borrable"] is False and "ya no está" in est["motivo"]


# ---------- endpoint POST /api/terminales/nueva-tarea ----------
from unittest.mock import AsyncMock

from conftest import ORIGIN, PIN, make_snapshot
from orquestador.enchufe import TerminalesError
from orquestador.enchufe.fake import FakeTerminales
from orquestador.enchufe.mux import Mux
from orquestador.nueva_terminal import NUEVA_LIMIT

IDT = "tarea0001"


@pytest.fixture
def mux_enchufe():
    g = FakeTerminales(nombre="guardian")
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    return Mux([h, g], nuevas_en="guardian"), g, h


@pytest.fixture
def authed_mux(app, mux_enchufe):
    mux, _, _ = mux_enchufe
    app.state.hub.enchufe = mux
    app.state.tacciones.enchufe = mux
    app.state.mensajes.execute = AsyncMock(return_value={"ok": True})
    with __import__("fastapi").testclient.TestClient(
        app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)
    ) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def _post(c, repo, **kw):
    cuerpo = {"id": IDT, "repo": str(repo), "tarea": "Arreglar el login"}
    cuerpo.update(kw)
    return c.post("/api/terminales/nueva-tarea", json=cuerpo)


def test_nueva_tarea_crea_copia_rama_y_abre_claude(authed_mux, app, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    r = _post(authed_mux, repo)
    assert r.status_code == 200, r.text
    ruta = str(repo.parent / "proy-arreglar-el-login")
    assert r.json()["ruta"] == ruta and r.json()["rama"] == "feature/arreglar-el-login"
    assert _git(ruta, "rev-parse", "--abbrev-ref", "HEAD") == "feature/arreglar-el-login"
    assert g.calls_of("crear_espacio")[0][2] == ruta
    assert len(g.calls_of("arrancar_claude")) == 1
    texto = app.state.mensajes.execute.await_args[0][0]
    assert texto.texto == "Arreglar el login" and texto.pane_id == r.json()["pane_id"]
    assert app.state.tacciones.worktrees.get(ruta)["rama"] == "feature/arreglar-el-login"


def test_nueva_tarea_usa_nombre_y_rama_editados(authed_mux, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    r = _post(authed_mux, repo, nombre="Login", rama="feature/mi-rama")
    assert r.status_code == 200 and r.json()["rama"] == "feature/mi-rama"
    assert g.calls_of("crear_espacio")[0][1] == "Login"


def test_nueva_tarea_repo_fuera_de_permitidas_400(authed_mux, cfg, repo, tmp_path):
    cfg.plan_cwds = [str(tmp_path / "otra")]
    assert _post(authed_mux, repo).status_code == 400
    assert not (repo.parent / "proy-arreglar-el-login").exists()


def test_nueva_tarea_carpeta_que_no_es_repo_400(authed_mux, cfg, repo):
    sub = repo / "sub"
    sub.mkdir()
    cfg.plan_cwds = [str(repo)]
    r = _post(authed_mux, sub)
    assert r.status_code == 400 and "repo" in r.json()["detail"].lower()


def test_nueva_tarea_rama_invalida_400(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    assert _post(authed_mux, repo, rama="feature/../x").status_code == 400
    assert _post(authed_mux, repo, rama="-x").status_code == 400


def test_nueva_tarea_vacia_400(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    assert _post(authed_mux, repo, tarea="   ").status_code == 400


def test_nueva_tarea_si_la_sesion_falla_quita_la_copia(authed_mux, app, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    g.fallas["crear_espacio"] = TerminalesError("caído")
    r = _post(authed_mux, repo)
    assert r.status_code == 503
    assert not (repo.parent / "proy-arreglar-el-login").exists()
    assert "feature/arreglar-el-login" not in _git(repo, "branch", "--list")
    assert app.state.tacciones.worktrees.rutas() == []


def test_nueva_tarea_mismo_id_idempotente(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    r1 = _post(authed_mux, repo)
    r2 = _post(authed_mux, repo)
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    assert not (repo.parent / "proy-arreglar-el-login-2").exists()


def test_nueva_tarea_comparte_tope_de_nuevas_y_no_deja_copia(authed_mux, app, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    app.state.tacciones.limit.consumir("nueva", 6, NUEVA_LIMIT)
    r = _post(authed_mux, repo)
    assert r.status_code == 429
    assert not (repo.parent / "proy-arreglar-el-login").exists()


def test_nueva_tarea_requiere_sesion(client):
    assert client.post("/api/terminales/nueva-tarea", json={}).status_code == 401
    assert client.get("/api/terminales/nueva-tarea").status_code in (401, 405)


def test_carpetas_marca_cuales_son_repo(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo), str(repo.parent / "nada-aca")]
    items = authed_mux.get("/api/terminales/carpetas").json()["carpetas"]
    assert [c.get("repo") for c in items] == [True]


# ---------- limpieza al cerrar ----------
from terminales_support import aplicar_snapshot


def _cierre_de_copia(authed, app, enchufe, e):
    app.state.tacciones.worktrees.agregar(e)
    snap = make_snapshot()
    snap["agents"][0]["cwd"] = e["ruta"]
    aplicar_snapshot(enchufe, snap)
    h = authed.post("/api/close/preview", json={"tipo": "workspace", "target_id": "w1"}).json()["huella"]
    return authed.post("/api/close/execute", json={
        "id": "6f1c1e0b-4a55-4e1d-9d33-1f3c2a7d9e10", "tipo": "workspace", "target_id": "w1", "huella": h,
        "origen": "manual", "destino": "Uno", "por_que": "", "sin_guardar": True})


def test_cerrar_ofrece_borrar_copia_si_esta_limpia(authed, app, enchufe, repo):
    e = _tarea(repo)
    r = _cierre_de_copia(authed, app, enchufe, e)
    assert r.status_code == 200, r.text
    assert r.json()["copias"] == [{"ruta": e["ruta"], "rama": "feature/x", "borrable": True, "motivo": ""}]


def test_cerrar_avisa_por_que_no_se_puede_borrar(authed, app, enchufe, repo):
    e = _tarea(repo)
    (Path(e["ruta"]) / "nuevo.txt").write_text("x")
    r = _cierre_de_copia(authed, app, enchufe, e)
    copia = r.json()["copias"][0]
    assert copia["borrable"] is False and copia["motivo"] == "Tiene cambios sin guardar"


def test_cerrar_sesion_comun_no_trae_copias(authed, enchufe):
    h = authed.post("/api/close/preview", json={"tipo": "workspace", "target_id": "w1"}).json()["huella"]
    r = authed.post("/api/close/execute", json={
        "id": "6f1c1e0b-4a55-4e1d-9d33-1f3c2a7d9e10", "tipo": "workspace", "target_id": "w1", "huella": h,
        "origen": "manual", "destino": "Uno", "por_que": "", "sin_guardar": True})
    assert r.status_code == 200 and "copias" not in r.json()


def test_borrar_copia_endpoint_borra_y_desregistra(authed, app, repo):
    e = _tarea(repo)
    app.state.tacciones.worktrees.agregar(e)
    r = authed.post("/api/terminales/nueva-tarea/borrar-copia", json={"ruta": e["ruta"]})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert not Path(e["ruta"]).exists()
    assert app.state.tacciones.worktrees.rutas() == []


def test_borrar_copia_endpoint_con_cambios_409_y_no_borra(authed, app, repo):
    e = _tarea(repo)
    app.state.tacciones.worktrees.agregar(e)
    (Path(e["ruta"]) / "nuevo.txt").write_text("x")
    r = authed.post("/api/terminales/nueva-tarea/borrar-copia", json={"ruta": e["ruta"]})
    assert r.status_code == 409 and r.json()["detail"] == "Tiene cambios sin guardar"
    assert (Path(e["ruta"]) / "nuevo.txt").exists()
    assert app.state.tacciones.worktrees.rutas() == [e["ruta"]]


def test_borrar_copia_endpoint_rechaza_ruta_no_registrada(authed, repo):
    r = authed.post("/api/terminales/nueva-tarea/borrar-copia", json={"ruta": str(repo)})
    assert r.status_code == 404
    assert repo.exists()


def test_nueva_tarea_manual_sigue_modo_global(authed_mux, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    assert _post(authed_mux, repo).status_code == 200
    assert [len(c) for c in g.calls_of("arrancar_claude")] == [4]


def test_nueva_tarea_con_permiso_arranca_en_ese_modo(app, cfg, repo, mux_enchufe):
    import asyncio

    from orquestador import terminales_acciones as tacc

    mux, g, _ = mux_enchufe
    app.state.tacciones.enchufe = mux
    cfg.plan_cwds = [str(repo)]
    body = tacc.NuevaTareaBody(id="tareaxx1", repo=str(repo), tarea="Revisar logs")
    out = asyncio.run(app.state.tacciones.nueva_tarea(tacc.Ctx(), body, permiso="default"))
    assert out["rama"]
    assert [c[-1] for c in g.calls_of("arrancar_claude")] == ["default"]
