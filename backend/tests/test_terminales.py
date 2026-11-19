import asyncio
import json

import pytest

from conftest import SID, make_snapshot
from orquestador.board import build_board
from orquestador.digest import DigestService
from orquestador.enchufe import TerminalesError
from orquestador.enchufe.herdr import info_de_process_json
from orquestador.terminales import cortar, huella_de, parse_process, short_cwd
from terminales_support import ANSI, aplicar_snapshot, info_proceso, make_terminales, process_info, snap_de


@pytest.fixture
def fake():
    return make_terminales({"w1:p5": ["node", "server.js", "--token", "SECRETO"], "w2:p1": ["/bin/bash"],
                            "w3:p1": ["-zsh"]})


@pytest.fixture
def enchufe(fake):
    return fake


def refresh(app):
    return asyncio.run(app.state.hub.refresh())


def tab_of(board, tab_id):
    return next(t for ws in board["workspaces"] for t in ws["tabs"] if t["id"] == tab_id)


def test_board_lists_terminals_in_shared_and_own_tab(app):
    board = refresh(app)
    shared = tab_of(board, "w1:t1")
    assert [a["pane_id"] for a in shared["agents"]] == ["w1:p1"]
    assert shared["terminales"] == [{
        "pane_id": "w1:p5", "terminal_id": "term-w1:p5", "titulo": "dev server", "cwd": "/tmp/proyecto",
        "proceso": "node", "estado": "corriendo", "protegida": False}]
    own = tab_of(board, "w2:t1")["terminales"]
    assert [(t["pane_id"], t["proceso"], t["estado"]) for t in own] == [("w2:p1", "bash", "prompt")]


def test_board_excludes_agents_self_and_env_pane(app):
    hub = app.state.hub
    hub.env_pane = "w2:p1"
    board = refresh(app)
    listed = {t["pane_id"] for ws in board["workspaces"] for tab in ws["tabs"] for t in tab["terminales"]}
    assert listed == {"w1:p5", "w3:p1"}
    hub.self_pane_id = "w1:p5"
    board = refresh(app)
    assert {t["pane_id"] for ws in board["workspaces"] for tab in ws["tabs"] for t in tab["terminales"]} == {"w3:p1"}


def test_board_super_orquestador_terminal_is_not_protected_and_strips_login_dash(app):
    protegida = tab_of(refresh(app), "w3:t1")["terminales"][0]
    assert protegida["protegida"] is False and protegida["proceso"] == "zsh" and protegida["estado"] == "prompt"


def test_board_never_carries_process_arguments(app):
    text = json.dumps(refresh(app))
    assert "SECRETO" not in text and "server.js" not in text and "--token" not in text


def test_failed_process_info_is_desconocido_and_does_not_break(app, fake):
    fake.fallas["proceso"] = TerminalesError("no")
    board = refresh(app)
    terminal = tab_of(board, "w1:t1")["terminales"][0]
    assert terminal["estado"] == "desconocido" and terminal["proceso"] == ""
    fake.fallas.pop("proceso", None)
    fake.procesos["w1:p5"] = info_de_process_json("no es json")
    assert tab_of(refresh(app), "w1:t1")["terminales"][0]["estado"] == "desconocido"


def test_process_info_cache_by_revision(app, fake):
    refresh(app)
    first = len(fake.calls_of("proceso"))
    assert first == 3
    refresh(app)
    assert len(fake.calls_of("proceso")) == first
    snap = snap_de(fake)
    snap["panes"][-2]["revision"] = 5
    aplicar_snapshot(fake, snap)
    refresh(app)
    assert len(fake.calls_of("proceso")) == first + 1


def test_title_and_cwd_are_cleaned(app, fake):
    snap = snap_de(fake)
    snap["panes"][-3].update(terminal_title_stripped="x\x1b[31m‮evil" + "a" * 300,
                               foreground_cwd="/home/usuario/" + "d" * 300)
    aplicar_snapshot(fake, snap)
    t = tab_of(refresh(app), "w1:t1")["terminales"][0]
    assert "\x1b" not in t["titulo"] and "\u202e" not in t["titulo"] and len(t["titulo"]) <= 120
    assert t["cwd"].startswith("…") and len(t["cwd"]) == 200


def test_short_cwd_abbreviates_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert short_cwd(str(tmp_path / "x" / "y")) == "~/x/y"
    assert short_cwd(str(tmp_path)) == "~"
    assert short_cwd(str(tmp_path) + "extra") == str(tmp_path) + "extra"


def test_parse_process_prefers_group_leader_and_basename():
    raw = json.dumps({"result": {"process_info": {"foreground_process_group_id": 7, "foreground_processes": [
        {"argv": ["/usr/bin/npm", "run", "dev"], "pid": 6, "name": "npm"}, {"argv": ["node", "x"], "pid": 7, "name": "node"}]}}})
    assert parse_process(info_de_process_json(raw)) == {"proceso": "node", "estado": "corriendo"}
    assert parse_process(info_proceso(["/usr/bin/fish"]))["estado"] == "prompt"
    assert parse_process(info_de_process_json("{}")) == {"proceso": None, "estado": "desconocido"}


@pytest.mark.parametrize("argv,esperado", [(["bash"], ("bash", "prompt")), (["node", "/x/claude"], ("claude", "corriendo")),
                                           (["-zsh"], ("zsh", "prompt"))])
def test_parse_process_sobre_info_proceso(argv, esperado):
    r = parse_process(info_proceso(argv))
    assert (r["proceso"], r["estado"]) == esperado


# ---- salida ----

def salida(authed, pane="w1:p5", **params):
    return authed.get(f"/api/terminales/{pane}/salida", params=params)


def test_salida_returns_ansi_and_meta(authed, fake):
    r = salida(authed)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["ansi"] == ANSI and body["truncado"] is False and body["pane_id"] == "w1:p5"
    assert body["proceso"] == "node" and body["estado"] == "corriendo" and body["cwd"] == "/tmp/proyecto"
    assert fake.calls_of("leer") == [("leer", "w1:p5", "reciente", "ansi", 500)]


def test_salida_same_rev_is_sin_cambios_and_cached_read(authed, fake):
    rev = salida(authed).json()["revision"]
    again = salida(authed, rev=rev).json()
    assert again["sin_cambios"] is True and again["revision"] == rev and "ansi" not in again
    assert len(fake.calls_of("leer")) == 1  # la caché de 1 s no vuelve a leer
    fake.pantallas["w1:p5"] = "otra cosa"
    app_terminales = authed.app.state.terminales
    app_terminales._reads.clear()
    assert salida(authed, rev=rev).json()["ansi"] == "otra cosa"


def test_cortar_drops_lines_and_bytes_from_the_top():
    text = "\n".join(f"l{i}" for i in range(600))
    out, truncated = cortar(text)
    assert truncated and out.split("\n")[0] == "l100" and out.split("\n")[-1] == "l599"
    big = "\n".join("x" * 1000 for _ in range(400))
    out, truncated = cortar(big)
    assert truncated and len(out.encode()) <= 256 * 1024
    assert cortar("a\nb") == ("a\nb", False)
    huge, flag = cortar("y" * 300_000)
    assert flag and len(huge.encode()) <= 256 * 1024


def test_salida_rejects_agent_self_unknown_and_bad_ids(authed, fake):
    assert salida(authed, pane="w1:p1").status_code == 403
    assert salida(authed, pane="w2:p9").status_code == 403
    assert salida(authed, pane="w9:p9").status_code == 404
    assert salida(authed, pane="bad id").status_code in (400, 404)
    assert salida(authed, pane="-x").status_code == 400
    assert salida(authed, rev="x" * 70).status_code == 400
    assert fake.calls_of("leer") == []


def test_salida_shell_with_claude_in_foreground_is_viewable(authed, fake):
    # Una consola (programa shell) donde Ando corrió `claude` a mano se puede abrir: el 403 es solo para panes de agente.
    fake.procesos["w1:p5"] = info_proceso(["claude", "--resume", "x"])
    r = salida(authed)
    assert r.status_code == 200 and r.json()["proceso"] == "claude"
    assert salida(authed, pane="w1:p1").status_code == 403


def test_salida_allows_super_orquestador_terminals(authed):
    assert salida(authed, pane="w3:p1").status_code == 200


def test_salida_429_when_reads_in_flight_are_full(authed):
    authed.app.state.terminales._sem = asyncio.Semaphore(0)
    r = salida(authed)
    assert r.status_code == 429 and r.headers["retry-after"] == "1"


def test_salida_429_after_rate_limit(authed):
    for _ in range(120):
        assert salida(authed).status_code == 200
    r = salida(authed)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_salida_502_when_herdr_fails(authed, fake):
    fake.fallas["leer"] = TerminalesError("caído")
    assert salida(authed).status_code == 502


def test_hub_never_reads_panes_without_a_viewer(app, fake):
    refresh(app)
    refresh(app)
    assert fake.calls_of("leer") == []


# ---- hardening de las rutas GET ----

def test_salida_hardening(client, authed):
    assert authed.get("/api/terminales/w1:p5/salida", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert authed.get("/api/terminales/w1:p5/salida", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert authed.get("/api/terminales/w1:p5/salida", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_salida_requires_session(client):
    assert client.get("/api/terminales/w1:p5/salida").status_code == 401


def test_huella_changes_with_terminal_identity():
    pane = {"pane_id": "a", "terminal_id": "t", "workspace_id": "w", "foreground_cwd": "/x"}
    assert huella_de(pane) == huella_de(dict(pane)) and len(huella_de(pane)) == 32
    assert huella_de({**pane, "terminal_id": "otro"}) != huella_de(pane)
    assert huella_de({**pane, "foreground_cwd": "/y"}) != huella_de(pane)


def test_parse_process_detects_claude_launched_without_its_name():
    for argv in (["node", "/usr/lib/node_modules/@anthropic-ai/claude-code/cli.js"],
                 ["/home/u/.local/share/claude/versions/2.1.316", "--resume"], ["npx", "claude"]):
        assert parse_process(info_proceso(argv)) == {"proceso": "claude", "estado": "corriendo"}
    assert parse_process(info_proceso(["node", "server.js"]))["proceso"] == "node"
    assert parse_process(info_proceso(["vim", "notas.md"]))["proceso"] == "vim"
