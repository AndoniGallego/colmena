from unittest.mock import AsyncMock

import pytest
from conftest import ORIGIN, PIN, make_snapshot

from orquestador.enchufe.fake import FakeTerminales
from orquestador.enchufe.mux import Mux
from orquestador.nueva_tarea import mensaje_ticket, nombre_ticket, validar_ticket
from orquestador.traspaso import TraspasoError

from test_nueva_tarea import _git, repo  # noqa: F401  (fixture de repo temporal)

IDT = "ticket001"


@pytest.mark.parametrize("raw,esperada", [("abc-123", "ABC-123"), ("  FRONT-9 ", "FRONT-9"), ("LRUN-100000", "LRUN-100000")])
def test_validar_ticket_normaliza(raw, esperada):
    assert validar_ticket(raw) == esperada


@pytest.mark.parametrize("malo", ["SITE-0", "S-1", "ABC-1234567", "SITE-12; rm -rf /", "", "SITE", "-1", "SITE-01",
                                  "SITE-1\nX", "ABCDEFGHIJK-1"])
def test_validar_ticket_rechaza(malo):
    with pytest.raises(TraspasoError) as exc:
        validar_ticket(malo)
    assert exc.value.status == 400


def test_mensaje_ticket_exacto_con_y_sin_nota():
    base = ("Arrancá el ticket ABC-123. Primero leelo con el agente analista de tickets (nunca la API de Jira directo) y "
            "después seguí /flujo-tickets desde el principio, con sus aprobaciones. Estás en una copia del repo solo "
            "para esta tarea, en la rama feature/ABC-123.")
    assert mensaje_ticket("ABC-123", "feature/ABC-123", "") == base
    assert mensaje_ticket("ABC-123", "feature/ABC-123", "  \n ") == base
    assert mensaje_ticket("ABC-123", "feature/ABC-123", "ojo con\nel carrito") == \
        base + " Nota de Ando: ojo con ⏎ el carrito"


def test_mensaje_ticket_nota_larga_se_rechaza_en_vez_de_recortar():
    from orquestador.mensaje import MAX_TEXT
    largo = len(mensaje_ticket("ABC-123", "feature/ABC-123", ""))
    justo = "x" * (MAX_TEXT - largo - len(" Nota de Ando: "))
    assert len(mensaje_ticket("ABC-123", "feature/ABC-123", justo)) == MAX_TEXT
    with pytest.raises(TraspasoError) as exc:
        mensaje_ticket("ABC-123", "feature/ABC-123", justo + "y")
    assert exc.value.status == 400 and str(len(justo)) in exc.value.detail
    with pytest.raises(TraspasoError):
        mensaje_ticket("ABC-123", "feature/ABC-123", "z" * 4000)


def test_nombre_ticket():
    assert nombre_ticket("ABC-123", "") == "ABC-123"
    assert nombre_ticket("ABC-123", "arreglar el carrito roto ahora mismo por favor gracias") == \
        "ABC-123 · arreglar el carrito roto ahora mismo"
    assert len(nombre_ticket("ABC-123", "x" * 200)) <= 60


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
    cuerpo = {"id": IDT, "repo": str(repo), "tarea": ""}
    cuerpo.update(kw)
    return c.post("/api/terminales/nueva-tarea", json=cuerpo)


def test_nueva_tarea_con_ticket_fija_rama_y_mensaje(authed_mux, app, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    r = _post(authed_mux, repo, ticket="abc-123", tarea="ojo con el carrito")
    assert r.status_code == 200, r.text
    ruta = str(repo.parent / "proy-abc-123")
    assert r.json()["ruta"] == ruta and r.json()["rama"] == "feature/ABC-123"
    assert _git(ruta, "rev-parse", "--abbrev-ref", "HEAD") == "feature/ABC-123"
    assert g.calls_of("crear_espacio")[0][1] == "ABC-123 · ojo con el carrito"
    texto = app.state.mensajes.execute.await_args[0][0].texto
    assert texto == mensaje_ticket("ABC-123", "feature/ABC-123", "ojo con el carrito")


def test_nueva_tarea_con_ticket_sin_nota_es_valida(authed_mux, app, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    r = _post(authed_mux, repo, ticket="ABC-123")
    assert r.status_code == 200, r.text
    assert app.state.mensajes.execute.await_args[0][0].texto == mensaje_ticket("ABC-123", "feature/ABC-123", "")


def test_ticket_invalido_400_no_crea(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    assert _post(authed_mux, repo, ticket="SITE-12; rm -rf /").status_code == 400
    assert _post(authed_mux, repo, ticket="SITE-0").status_code == 400
    assert _post(authed_mux, repo, ticket="X" * 21).status_code in (400, 422)
    assert not list(repo.parent.glob("proy-*"))


def test_ticket_y_rama_distinta_400(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    r = _post(authed_mux, repo, ticket="ABC-123", rama="feature/otra")
    assert r.status_code == 400 and "feature/ABC-123" in r.json()["detail"]
    assert not list(repo.parent.glob("proy-*"))
    assert _post(authed_mux, repo, id="ticket002", ticket="ABC-123", rama="feature/ABC-123").status_code == 200


def test_rama_de_ticket_existente_409_no_crea_carpeta(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    _git(repo, "branch", "feature/ABC-123")
    r = _post(authed_mux, repo, ticket="ABC-123")
    assert r.status_code == 409 and "Ya hay una rama feature/ABC-123" in r.json()["detail"]
    assert not list(repo.parent.glob("proy-*"))


def test_sin_ticket_y_sin_tarea_sigue_400(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    assert _post(authed_mux, repo, tarea="  ").status_code == 400


# ---------- preparar la copia (setup) ----------
import asyncio
import json
import os
import stat

from orquestador.enchufe import TerminalesError
from orquestador.terminales_acciones import Ctx

SECRETO = "TOKEN=super-secreto-123\n"
CMD_SETUP = "sh -c 'set -a; . ./.colmena/env; set +a; exec ./scripts/setup.sh'"
IDS = "ticketset1"


def _con_setup(repo, toml='copiar = [".env"]\nscript = "scripts/setup.sh"\npuertos = 10\n', gitignore=".env\n.colmena/env\n",
               extra=None):
    (repo / ".gitignore").write_text(gitignore)
    (repo / ".colmena").mkdir(exist_ok=True)
    (repo / ".colmena" / "setup.toml").write_text(toml)
    (repo / "scripts").mkdir(exist_ok=True)
    (repo / "scripts" / "setup.sh").write_text("#!/bin/sh\necho preparando\n")
    (repo / "scripts" / "setup.sh").chmod(0o755)
    for nombre, texto in (extra or {}).items():
        (repo / nombre).write_text(texto)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    (repo / ".env").write_text(SECRETO)


def _confiar(c, repo, payload):
    return c.post("/api/terminales/nueva-tarea/confiar", json={
        "repo": str(repo), "setup_sha256": payload["setup_sha256"], "script_sha256": payload["script_sha256"]})


def _pedir_409(c, repo, **kw):
    r = _post(c, repo, ticket="abc-123", id=IDS, **kw)
    assert r.status_code == 409, r.text
    return r.json()


def _sin_copia(repo, app):
    assert not list(repo.parent.glob("proy-*"))
    assert app.state.tacciones.worktrees.todas() == []
    assert _git(repo, "branch", "--list", "feature/ABC-123") == ""


def test_ticket_con_setup_sin_confianza_409_no_crea(authed_mux, app, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo)
    cuerpo = _pedir_409(authed_mux, repo)
    assert cuerpo["codigo"] == "requiere_confianza"
    conf = cuerpo["confianza"]
    assert conf["repo"] == str(repo) and conf["origen"] == "repo" and conf["base"] == "main"
    assert 'script = "scripts/setup.sh"' in conf["setup_toml"] and "echo preparando" in conf["script_contenido"]
    assert len(conf["setup_sha256"]) == 64 and len(conf["script_sha256"]) == 64
    assert conf["copiar"] == [".env"] and conf["puertos"] == 10 and conf["docker"] is None
    assert SECRETO.strip() not in json.dumps(cuerpo)
    _sin_copia(repo, app)


def test_confiar_y_reintentar_crea_y_abre_dos_pestanas(authed_mux, app, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo)
    conf = _pedir_409(authed_mux, repo)["confianza"]
    assert _confiar(authed_mux, repo, conf).json() == {"ok": True}
    r = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    assert r.status_code == 200, r.text
    ruta = str(repo.parent / "proy-abc-123")
    prep = r.json()["preparar"]
    assert prep["puerto"] == 41000 and prep["puertos"] == 10 and prep["copiados"] == [".env"]
    assert prep["omitidos"] == [] and prep["puertos_fijos"] is False and prep["setup_pane_id"]
    assert r.json()["ruta"] == ruta
    assert open(os.path.join(ruta, ".env")).read() == SECRETO
    assert stat.S_IMODE(os.stat(os.path.join(ruta, ".env")).st_mode) == 0o600
    assert open(os.path.join(ruta, ".colmena", "env")).read() == "COLMENA_PORT=41000\nCOLMENA_PORT_COUNT=10\n"
    nombres = [c[0] for c in g.calls]
    assert nombres.index("crear_espacio") < nombres.index("crear_linea") < nombres.index("ejecutar")
    assert g.calls_of("escribir") == []
    ejecutar = g.calls_of("ejecutar")
    assert len(ejecutar) == 1 and ejecutar[0][2] == CMD_SETUP and ejecutar[0][1] == prep["setup_pane_id"]
    assert g.calls_of("crear_linea")[0][2] == "setup"
    texto = app.state.mensajes.execute.await_args[0][0].texto
    assert "COLMENA_PORT=41000 (10 puertos)" in texto and "«setup»" in texto and "scripts/setup.sh" in texto
    assert texto.startswith(mensaje_ticket("ABC-123", "feature/ABC-123", ""))
    assert app.state.tacciones.worktrees.get(ruta)["puerto"] == 41000


def test_script_cambiado_en_la_base_vuelve_a_pedir_confianza(authed_mux, app, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo)
    conf = _pedir_409(authed_mux, repo)["confianza"]
    assert _confiar(authed_mux, repo, conf).status_code == 200
    (repo / "scripts" / "setup.sh").write_text("#!/bin/sh\necho otra cosa\n")
    _git(repo, "commit", "-qam", "cambia")
    nuevo = _pedir_409(authed_mux, repo)["confianza"]
    assert nuevo["script_sha256"] != conf["script_sha256"] and nuevo["setup_sha256"] == conf["setup_sha256"]
    _sin_copia(repo, app)


def test_confiar_hash_viejo_409_con_payload_nuevo(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo)
    conf = _pedir_409(authed_mux, repo)["confianza"]
    r = authed_mux.post("/api/terminales/nueva-tarea/confiar", json={
        "repo": str(repo), "setup_sha256": "0" * 64, "script_sha256": conf["script_sha256"]})
    assert r.status_code == 409 and r.json()["codigo"] == "requiere_confianza"
    assert r.json()["confianza"]["setup_sha256"] == conf["setup_sha256"]
    assert _post(authed_mux, repo, ticket="abc-123", id="otro-id-01").status_code == 409


def test_confiar_repo_fuera_de_plan_cwds_400(authed_mux, cfg, repo, tmp_path):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo)
    otro = tmp_path / "otro"
    otro.mkdir()
    r = authed_mux.post("/api/terminales/nueva-tarea/confiar", json={
        "repo": str(otro), "setup_sha256": "0" * 64, "script_sha256": None})
    assert r.status_code == 400
    r = authed_mux.post("/api/terminales/nueva-tarea/confiar", json={
        "repo": str(repo), "setup_sha256": "xx", "script_sha256": None})
    assert r.status_code in (400, 422)
    r = authed_mux.post("/api/terminales/nueva-tarea/confiar", json={
        "repo": str(repo), "setup_sha256": "0" * 64, "script_sha256": None, "extra": 1})
    assert r.status_code in (400, 422)
    assert authed_mux.get("/api/terminales/nueva-tarea/confiar").status_code == 405


def test_confiar_sin_setup_400(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    r = authed_mux.post("/api/terminales/nueva-tarea/confiar", json={
        "repo": str(repo), "setup_sha256": "0" * 64, "script_sha256": None})
    assert r.status_code == 400


def _confiado(c, repo):
    conf = _pedir_409(c, repo)["confianza"]
    assert _confiar(c, repo, conf).status_code == 200


def test_setup_falla_tras_claude_no_borra_copia(authed_mux, app, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo)
    _confiado(authed_mux, repo)
    g.fallas["ejecutar"] = TerminalesError("se cayó")
    r = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    assert r.status_code == 503 and "setup" in r.json()["detail"] and "a mano" in r.json()["detail"]
    ruta = str(repo.parent / "proy-abc-123")
    assert os.path.isdir(ruta) and app.state.tacciones.worktrees.get(ruta)["puerto"] == 41000
    assert _git(repo, "branch", "--list", "feature/ABC-123") != ""
    app.state.mensajes.execute.assert_not_awaited()


def test_sin_setup_flujo_identico(authed_mux, app, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    r = _post(authed_mux, repo, ticket="abc-123", tarea="ojo")
    assert r.status_code == 200 and "preparar" not in r.json()
    assert g.calls_of("crear_linea") == [] and g.calls_of("ejecutar") == []
    assert app.state.mensajes.execute.await_args[0][0].texto == mensaje_ticket("ABC-123", "feature/ABC-123", "ojo")
    assert not (repo.parent / "proy-abc-123" / ".colmena").exists()
    assert "puerto" not in app.state.tacciones.worktrees.get(str(repo.parent / "proy-abc-123"))


def test_sin_ticket_ignora_setup(authed_mux, app, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo)
    r = _post(authed_mux, repo, tarea="mejorar la hoja")
    assert r.status_code == 200, r.text
    assert "preparar" not in r.json()
    ruta = r.json()["ruta"]
    assert not os.path.exists(os.path.join(ruta, ".env")) and g.calls_of("ejecutar") == []


def test_setup_solo_copiar_sin_script_abre_una_pestana(authed_mux, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo, toml='copiar = [".env"]\n')
    _confiado(authed_mux, repo)
    r = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    assert r.status_code == 200, r.text
    assert r.json()["preparar"]["setup_pane_id"] is None and r.json()["preparar"]["puerto"] is None
    assert g.calls_of("ejecutar") == [] and g.calls_of("crear_linea") == []
    assert open(os.path.join(r.json()["ruta"], ".env")).read() == SECRETO


def test_compose_sin_declarar_puertos_fijos(authed_mux, app, cfg, repo, mux_enchufe):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo, extra={"docker-compose.yml": "services: {}\n"})
    _confiado(authed_mux, repo)
    r = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    assert r.status_code == 200, r.text
    prep = r.json()["preparar"]
    assert prep["puertos_fijos"] is True and prep["puerto"] is None and prep["puertos"] is None
    assert open(os.path.join(r.json()["ruta"], ".colmena", "env")).read() == "COMPOSE_PROJECT_NAME=proy-abc-123\n"
    assert "puertos son fijos" in app.state.mensajes.execute.await_args[0][0].texto
    assert "puerto" not in app.state.tacciones.worktrees.get(r.json()["ruta"])


def test_compose_con_puertos_variables_reserva(authed_mux, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo, toml='script = "scripts/setup.sh"\npuertos = 2\ndocker = "puertos-variables"\n',
               extra={"compose.yaml": "services: {}\n"})
    _confiado(authed_mux, repo)
    r = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    assert r.status_code == 200, r.text
    assert r.json()["preparar"]["puerto"] == 41000 and r.json()["preparar"]["puertos_fijos"] is False
    texto = open(os.path.join(r.json()["ruta"], ".colmena", "env")).read()
    assert texto == "COLMENA_PORT=41000\nCOLMENA_PORT_COUNT=2\nCOMPOSE_PROJECT_NAME=proy-abc-123\n"


def test_borrar_copia_libera_el_bloque_y_se_reasigna(authed_mux, app, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo)
    _confiado(authed_mux, repo)
    r1 = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    r2 = _post(authed_mux, repo, ticket="abc-124", id="ticketset2")
    assert r1.json()["preparar"]["puerto"] == 41000 and r2.json()["preparar"]["puerto"] == 41010
    # integrar la rama de la primera para que sea borrable
    ruta1 = r1.json()["ruta"]
    assert authed_mux.post("/api/terminales/nueva-tarea/borrar-copia", json={"ruta": ruta1}).status_code == 200
    r3 = _post(authed_mux, repo, ticket="abc-125", id="ticketset3")
    assert r3.status_code == 200 and r3.json()["preparar"]["puerto"] == 41000


def test_env_colmena_no_ignorado_rollback_400(authed_mux, app, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo, gitignore=".env\n")
    _confiado(authed_mux, repo)
    r = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    assert r.status_code == 400 and ".colmena/env" in r.json()["detail"]
    _sin_copia(repo, app)


def test_base_movida_entre_verificacion_y_creacion_rollback_409(authed_mux, app, cfg, repo, monkeypatch):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo)
    _confiado(authed_mux, repo)
    monkeypatch.setattr("orquestador.terminales_acciones.coincide_en_copia", lambda copia, setup: False)
    r = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    assert r.status_code == 409 and r.json()["codigo"] == "requiere_confianza"
    _sin_copia(repo, app)


def test_copiar_trackeado_o_con_symlink_400_sin_crear_nada(authed_mux, app, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo, toml='copiar = ["x.txt"]\n', extra={"x.txt": "publico\n"})
    _confiado(authed_mux, repo)
    r = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    assert r.status_code == 400 and "versionado" in r.json()["detail"]
    _sin_copia(repo, app)


def test_override_de_config_reemplaza_y_pide_confianza(authed_mux, app, cfg, repo):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo, toml='puertos = 3\n')
    cfg.preparar = {str(repo): {"copiar": [".env"], "puertos": 5}}
    conf = _pedir_409(authed_mux, repo)["confianza"]
    assert conf["origen"] == "config" and conf["setup_toml"] == '{"copiar":[".env"],"puertos":5}'
    assert conf["script"] is None and conf["script_contenido"] is None and conf["script_sha256"] is None
    assert authed_mux.post("/api/terminales/nueva-tarea/confiar", json={
        "repo": str(repo), "setup_sha256": conf["setup_sha256"], "script_sha256": None}).status_code == 200
    r = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    assert r.status_code == 200 and r.json()["preparar"]["puertos"] == 5


def test_respuesta_y_auditoria_no_contienen_contenido_env(authed_mux, app, cfg, repo, tmp_path):
    cfg.plan_cwds = [str(repo)]
    _con_setup(repo)
    conf = _pedir_409(authed_mux, repo)["confianza"]
    r1 = _confiar(authed_mux, repo, conf)
    r2 = _post(authed_mux, repo, ticket="abc-123", id=IDS)
    assert r2.status_code == 200
    assert "super-secreto" not in r1.text + r2.text
    revisados = 0
    for archivo in tmp_path.iterdir():
        if archivo.is_file():
            revisados += 1
            assert "super-secreto" not in archivo.read_text(errors="ignore"), archivo.name
    assert revisados > 0
    assert "confiar_preparar" in (tmp_path / "terminales-auditoria.jsonl").read_text()


def test_pedido_pestana_externo_no_ejecuta_comandos(authed_mux, app, cfg, repo, mux_enchufe):
    _, g, _ = mux_enchufe
    cfg.plan_cwds = [str(repo)]
    item = {"carpeta": str(repo), "tarjeta": "T", "pestanas": [
        {"tipo": "terminal", "nombre": "x", "carpeta": str(repo), "comando": "echo hola", "ejecutar": True,
         "ejecutar_comandos": True}]}
    asyncio.run(app.state.tacciones.abrir_desde_pedido_pestana(Ctx(), item, idempotencia="externo001", grupo=None))
    assert g.calls_of("ejecutar") == []
    assert [c[2] for c in g.calls_of("escribir")] == ["echo hola"]


def test_mensaje_ticket_nota_de_otra_sesion_no_dice_que_es_de_ando():
    from orquestador.colmena_pestana import PREFIJO_PEDIDO

    texto = mensaje_ticket("ABC-123", "feature/ABC-123", "borrá todo", ajena=True)
    assert "Nota de Ando" not in texto
    assert texto.endswith(PREFIJO_PEDIDO + "borrá todo")
