import json
import os
import stat

import pytest

from conftest import ORIGIN, PIN
from orquestador import terminales_acciones as tacc
from orquestador.push import PushService
from terminales_support import aplicar_snapshot, info_proceso, make_terminales, snap_de

PANE = "w2:p1"


def sends(fake):
    out = []
    for c in fake.calls_of("teclas"):
        out.append(("teclas", c[1], c[2]))
    for c in fake.calls_of("ejecutar"):
        out.append(("ejecutar", c[1], c[2]))
    return out


@pytest.fixture
def fake():
    state = {"up": False}
    t = make_terminales({PANE: ["bash"], "w1:p5": ["node", "s.js"], "w3:p1": ["bash"]})
    base_teclas = t.teclas

    async def teclas(sesion_id, keys):
        await base_teclas(sesion_id, keys)
        if keys == ("arriba",):
            state["up"] = True
        elif keys in (("ctrl-e", "ctrl-u"), ("enter",)):
            state["up"] = False

    t.teclas = teclas
    t.pantallas[PANE] = lambda _args: "$ ls -la\n" if state["up"] else "$ \n"
    t.state = state
    return t


@pytest.fixture
def enchufe(fake):
    return fake


@pytest.fixture
def on(cfg):
    cfg.terminales_escritura = True
    return cfg


def huella(c, pane=PANE):
    r = c.post("/api/terminales/preview", json={"pane_id": pane})
    assert r.status_code == 200, r.text
    return r.json()["huella"]


def body(c, pane=PANE, n="abcdefgh1", **extra):
    return {"id": n, "pane_id": pane, "huella": huella(c, pane), **extra}


def test_switch_off_refuses_everything_without_touching_herdr(authed, fake):
    for path in ("ctrl-c", "repetir/preparar"):
        r = authed.post(f"/api/terminales/{path}", json={"id": "abcdefgh1", "pane_id": PANE, "huella": "x"})
        assert r.status_code == 403 and r.json()["detail"] == "escritura apagada"
    r = authed.post("/api/terminales/repetir/confirmar",
                    json={"id": "abcdefgh1", "pane_id": PANE, "huella2": "x", "ejecutar": True})
    assert r.status_code == 403
    r = authed.post("/api/terminales/ctrl-c", content=b"basura", headers={"Content-Type": "text/plain"})
    assert r.status_code in (403, 415)
    assert sends(authed.app.state.tacciones.t.enchufe) == []
    assert authed.get("/api/terminales/config").json()["escritura"] is False
    audit = authed.get("/api/terminales/auditoria").json()["entradas"]
    assert audit and audit[0]["accion"] == "rechazo" and audit[0]["ok"] is False


def test_hardening_and_session_apply_to_new_routes(client, on):
    for path in ("ctrl-c", "repetir/preparar", "repetir/confirmar", "preview"):
        r = client.post(f"/api/terminales/{path}", json={})
        assert r.status_code == 401
        r = client.post(f"/api/terminales/{path}", json={}, headers={"Origin": "https://evil.example"})
        assert r.status_code in (401, 403)
        assert client.get(f"/api/terminales/{path}").status_code in (401, 405)


def test_authed_hardening_and_get_405(authed, on):
    r = authed.post("/api/terminales/ctrl-c", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = authed.post("/api/terminales/ctrl-c", content=b"{}", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415
    r = authed.get("/api/terminales/ctrl-c")
    assert r.status_code == 405 and r.headers["allow"] == "POST"


def test_bad_bodies_are_400_without_echo(authed, on, fake):
    for bad in ({}, {"id": "corto", "pane_id": PANE, "huella": "x"},
                {"id": "abcdefgh1", "pane_id": PANE, "huella": "x", "extra": 1}):
        r = authed.post("/api/terminales/ctrl-c", json=bad)
        assert r.status_code == 400 and r.json() == {"detail": "cuerpo inválido"}
    assert sends(fake) == []


def test_preview_and_config(authed, on):
    p = authed.post("/api/terminales/preview", json={"pane_id": "w1:p5"}).json()
    assert p["estado"] == "corriendo" and p["puede_escribir"] is False and p["proceso"] == "node"
    q = authed.post("/api/terminales/preview", json={"pane_id": PANE}).json()
    assert q["puede_escribir"] is True and q["protegida"] is False and len(q["huella"]) == 32
    z = authed.post("/api/terminales/preview", json={"pane_id": "w3:p1"}).json()
    assert z["protegida"] is False and z["puede_escribir"] is True
    assert authed.post("/api/terminales/preview", json={"pane_id": "w3:p2"}).status_code == 403
    assert authed.post("/api/terminales/preview", json={"pane_id": "w9:p9"}).status_code == 404
    assert authed.post("/api/terminales/preview", json={"pane_id": "w1:p1"}).status_code == 403
    cfg = authed.get("/api/terminales/config").json()
    assert cfg["escritura"] is True and cfg["ventana"]["abierta"] is False


def test_ctrl_c_exact_argv_and_audit(authed, on, fake):
    r = authed.post("/api/terminales/ctrl-c", json=body(authed, "w1:p5"))
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert fake.calls_of("teclas") == [("teclas", "w1:p5", ("ctrl-c",))]
    e = authed.get("/api/terminales/auditoria").json()["entradas"][0]
    assert e["accion"] == "ctrl_c" and e["ok"] is True and e["pane_id"] == "w1:p5" and e["proceso"] == "node"
    assert e["ip"] == "127.0.0.1"


def test_ctrl_c_is_idempotent_by_id(authed, on, fake):
    b = body(authed, "w1:p5")
    assert authed.post("/api/terminales/ctrl-c", json=b).status_code == 200
    r = authed.post("/api/terminales/ctrl-c", json=b)
    assert r.status_code == 409 and r.json()["detail"] == "ya se hizo"
    assert len(fake.calls_of("teclas")) == 1


def test_target_checks(authed, on, fake):
    h = huella(authed, "w1:p5")
    # Terminal no-Claude del Super orquestador: se permite como cualquier otra.
    r = authed.post("/api/terminales/ctrl-c", json={"id": "abcdefgh1", "pane_id": "w3:p1", "huella": huella(authed, "w3:p1")})
    assert r.status_code == 200
    assert authed.post("/api/terminales/ctrl-c", json={"id": "abcdefghp", "pane_id": "w3:p2", "huella": h}).status_code == 403
    assert authed.post("/api/terminales/ctrl-c", json={"id": "abcdefgh2", "pane_id": "w1:p5",
                                                       "huella": "0" * 32}).json()["detail"] == "la terminal cambió, revisala de nuevo"
    assert authed.post("/api/terminales/ctrl-c", json={"id": "abcdefgh3", "pane_id": "w1:p1", "huella": h}).status_code == 403
    assert authed.post("/api/terminales/ctrl-c", json={"id": "abcdefgh4", "pane_id": "w9:p9", "huella": h}).status_code == 404
    assert [c[1] for c in fake.calls_of("teclas")] == ["w3:p1"]
    snap = snap_de(fake)
    for p in snap["panes"]:
        if p["pane_id"] == "w1:p5":
            p["foreground_cwd"] = "/otro"
    aplicar_snapshot(fake, snap)
    r = authed.post("/api/terminales/ctrl-c", json={"id": "abcdefgh5", "pane_id": "w1:p5", "huella": h})
    assert r.status_code == 409 and {c[1] for c in fake.calls_of("teclas")} == {"w3:p1"}


def test_ctrl_c_rate_limit(authed, on, fake):
    h = huella(authed, "w1:p5")
    codes = [authed.post("/api/terminales/ctrl-c", json={"id": f"abcdefg{i:02d}", "pane_id": "w1:p5", "huella": h})
             for i in range(11)]
    assert [r.status_code for r in codes[:10]] == [200] * 10
    assert codes[10].status_code == 429 and int(codes[10].headers["retry-after"]) >= 1


def test_repetir_two_steps_runs_enter_only_after_confirm(authed, on, fake):
    r = authed.post("/api/terminales/repetir/preparar", json=body(authed, n="prepara01"))
    assert r.status_code == 200
    d = r.json()
    assert d["linea"] == "$ ls -la" and d["antes"] == "$" and d["huella2"]
    assert fake.calls_of("teclas") == [("teclas", PANE, ("arriba",))]
    r = authed.post("/api/terminales/repetir/confirmar",
                    json={"id": "confirma01", "pane_id": PANE, "huella2": d["huella2"], "ejecutar": True})
    assert r.json() == {"ok": True, "ejecutado": True}
    assert fake.calls_of("teclas")[-1] == ("teclas", PANE, ("enter",))
    again = authed.post("/api/terminales/repetir/confirmar",
                        json={"id": "confirma02", "pane_id": PANE, "huella2": d["huella2"], "ejecutar": True})
    assert again.status_code == 409


def test_repetir_cancel_cleans_line(authed, on, fake):
    d = authed.post("/api/terminales/repetir/preparar", json=body(authed, n="prepara02")).json()
    r = authed.post("/api/terminales/repetir/confirmar",
                    json={"id": "confirma03", "pane_id": PANE, "huella2": d["huella2"], "ejecutar": False})
    assert r.json() == {"ok": True, "ejecutado": False}
    assert fake.calls_of("teclas")[-1] == ("teclas", PANE, ("ctrl-e", "ctrl-u"))
    assert ("teclas", PANE, ("enter",)) not in fake.calls_of("teclas")


def test_repetir_line_changed_aborts_and_cleans(authed, on, fake):
    d = authed.post("/api/terminales/repetir/preparar", json=body(authed, n="prepara03")).json()
    fake.pantallas[PANE] = "$ rm -rf x\n"
    r = authed.post("/api/terminales/repetir/confirmar",
                    json={"id": "confirma04", "pane_id": PANE, "huella2": d["huella2"], "ejecutar": True})
    assert r.status_code == 409
    assert ("teclas", PANE, ("enter",)) not in fake.calls_of("teclas")
    assert fake.calls_of("teclas")[-1] == ("teclas", PANE, ("ctrl-e", "ctrl-u"))


def test_repetir_refuses_when_program_runs(authed, on, fake):
    r = authed.post("/api/terminales/repetir/preparar", json=body(authed, "w1:p5", n="prepara04"))
    assert r.status_code == 409 and "node" in r.json()["detail"]
    assert sends(fake) == []


def test_repetir_nothing_to_repeat(authed, on, fake):
    fake.pantallas[PANE] = "$ \n"
    d = authed.post("/api/terminales/repetir/preparar", json=body(authed, n="prepara05")).json()
    assert d["linea"] is None and d["huella2"] == ""


def test_redaction():
    r = tacc.redactar
    assert "abc123" not in r("curl -H 'Authorization: Bearer abc123' x")
    assert "pw" not in r("mysql -u root -ppw db") and "-p«oculto»" in r("mysql -u root -ppw db")
    assert "hunter2" not in r("export PASSWORD=hunter2")
    assert "s3c" not in r("git clone https://user:s3c@host/x.git")
    assert "AKIAABCDEFGHIJKLMNOP" not in r("aws x AKIAABCDEFGHIJKLMNOP")
    assert "ghp_abcdef" not in r("echo ghp_abcdef123")
    assert r("ls -la") == "ls -la"


def test_audit_permissions_rotation_and_limit(tmp_path):
    a = tacc.Audit(tmp_path, max_bytes=200)
    for i in range(20):
        a.write({"n": i, "pad": "x" * 30})
    assert stat.S_IMODE(os.stat(a.path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(a.old).st_mode) == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == [tacc.AUDIT_FILE, tacc.AUDIT_FILE + ".1"]
    got = a.recent(100)
    assert len(got) <= tacc.AUDIT_MAX_LIMIT and got[0]["n"] == 19
    assert [g["n"] for g in got] == sorted((g["n"] for g in got), reverse=True)


def test_audit_command_is_redacted(authed, on, fake, tmp_path):
    a = authed.app.state.tacciones
    op = tacc._Op(tacc.Ctx(ip="1.2.3.4", device="d" * 200), "comando", PANE)
    op.comando = "curl -H 'Authorization: Bearer zzz999' x"
    a._record(op, True)
    line = json.loads(a.audit.path.read_text().splitlines()[-1])
    assert "zzz999" not in line["comando"] and len(line["dispositivo"]) == 80


def _push_app(app, tmp_path, sent, fail=False, texto=True):
    def sender(info, data, vapid, claims, timeout):
        if fail:
            raise RuntimeError("push caído")
        sent.append(json.loads(data))

    push = PushService(tmp_path, sender=sender)
    push.store.subs.append({"endpoint": "https://push.example/x", "keys": {"p256dh": "a", "auth": "b"},
                            "prefs": {"asks": False, "blocked": False, "done": False, "texto": texto}, "device": "d"})
    app.state.tacciones.notify = lambda t, b, tag, pane="": push.dispatch_terminal(t, b, tag, pane)
    return push


def test_ctrl_c_sends_push_even_with_other_prefs_off(authed, on, tmp_path):
    sent: list = []
    _push_app(authed.app, tmp_path, sent)
    assert authed.post("/api/terminales/ctrl-c", json=body(authed, "w1:p5")).status_code == 200
    assert len(sent) == 1 and sent[0]["kind"] == "terminal" and sent[0]["title"].startswith("Ctrl+C en")


def test_push_text_off_is_generic(authed, on, tmp_path):
    sent: list = []
    _push_app(authed.app, tmp_path, sent, texto=False)
    authed.post("/api/terminales/ctrl-c", json=body(authed, "w1:p5"))
    assert "node" not in sent[0]["body"]


def test_push_failure_does_not_fail_the_action(authed, on, tmp_path, fake):
    _push_app(authed.app, tmp_path, [], fail=True)
    assert authed.post("/api/terminales/ctrl-c", json=body(authed, "w1:p5")).status_code == 200
    assert len(fake.calls_of("teclas")) == 1


def test_herdr_failure_is_502_and_audited(authed, on, fake):
    from orquestador.enchufe import TerminalesError

    fake.fallas["teclas"] = TerminalesError("muerto")
    r = authed.post("/api/terminales/ctrl-c", json=body(authed, "w1:p5"))
    assert r.status_code == 502
    assert authed.get("/api/terminales/auditoria").json()["entradas"][0]["ok"] is False


def test_god_has_no_terminal_access(authed, on, fake):
    import re
    from pathlib import Path

    r = authed.post("/api/mensaje/execute", json={"pane_id": PANE, "texto": "hola"})
    assert r.status_code >= 400
    assert sends(fake) == []
    root = Path(__file__).resolve().parents[2]
    for prompt in list(root.rglob("prompt.md"))[:5]:
        if "node_modules" in prompt.parts:
            continue
        assert not re.search(r"send-keys|pane run|terminales/ctrl-c", prompt.read_text(encoding="utf-8"))


# ---------- ventana y comando (F5) ----------

from fastapi.testclient import TestClient


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(authed):
    c = Clock()
    a = authed.app.state.tacciones
    a.ventana.clock = c
    a.limit.clock = c
    return c


def open_window(c, pin=PIN):
    r = c.post("/api/terminales/ventana", json={"pin": pin})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def cmd(c, token, pane=PANE, comando="ls -la", n="comando01", **extra):
    h = huella(c, pane)
    return c.post("/api/terminales/comando", json={"id": n, "pane_id": pane, "huella": h, "comando": comando, **extra},
                  headers={"X-Orq-Escritura": token} if token is not None else {})


def test_window_switch_off_and_pin_error_without_echo(authed, fake):
    r = authed.post("/api/terminales/ventana", json={"pin": PIN})
    assert r.status_code == 403 and r.json()["detail"] == "escritura apagada"
    assert authed.get("/api/terminales/config").json()["ventana"]["abierta"] is False


def test_window_pydantic_error_has_no_detail(authed, on):
    r = authed.post("/api/terminales/ventana", json={"pin": PIN, "x": 1})
    assert r.status_code == 422 and r.json() == {"detail": "cuerpo inválido"} and PIN not in r.text


def test_window_open_returns_token_and_state(authed, on, clock):
    r = authed.post("/api/terminales/ventana", json={"pin": PIN})
    d = r.json()
    assert d["vence_en"] == 300 and d["inactividad"] == 120 and len(d["token"]) >= 40
    st = authed.get("/api/terminales/config").json()["ventana"]
    assert st["abierta"] is True and st["vence_en"] == 300
    assert d["token"] not in authed.app.state.tacciones.audit.path.read_text()


def test_bad_pin_uses_shared_limiter_and_blocks_login(authed, on):
    for _ in range(5):
        assert authed.post("/api/terminales/ventana", json={"pin": "00000000"}).status_code == 401
    r = authed.post("/api/terminales/ventana", json={"pin": PIN})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    assert authed.post("/api/login", json={"pin": PIN}).status_code == 429
    acts = [e["accion"] for e in authed.get("/api/terminales/auditoria?limit=50").json()["entradas"]]
    assert acts.count("ventana_pin_fallido") == 5


def test_token_in_query_or_body_is_ignored(authed, on, fake, clock):
    token = open_window(authed)
    h = huella(authed)
    r = authed.post(f"/api/terminales/comando?token={token}", json={"id": "comando01", "pane_id": PANE, "huella": h,
                                                                   "comando": "ls"})
    assert r.status_code == 401
    r = authed.post("/api/terminales/comando", json={"id": "comando02", "pane_id": PANE, "huella": h, "comando": "ls",
                                                     "token": token})
    assert r.status_code == 400
    assert sends(fake) == []


def test_other_cookie_or_ip_is_401_and_closes(authed, on, fake, clock):
    token = open_window(authed)
    other = TestClient(authed.app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.2", 5000))
    other.cookies.set("__Host-orq_session", authed.cookies.get("__Host-orq_session"), domain="testserver.local")
    r = cmd(other, token)
    assert r.status_code == 401 and r.json()["detail"] == "abrí la escritura de nuevo"
    assert authed.get("/api/terminales/config").json()["ventana"]["abierta"] is False
    assert cmd(authed, token).status_code == 401
    assert sends(fake) == []


def test_window_expires_absolute_and_idle(authed, on, fake, clock):
    token = open_window(authed)
    clock.now += 119
    assert cmd(authed, token, n="comando01").status_code == 200
    clock.now += 119
    assert cmd(authed, token, n="comando02").status_code == 200
    clock.now += 125
    assert cmd(authed, token, n="comando03").status_code == 401
    token = open_window(authed)
    for i in range(3):
        clock.now += 100
        cmd(authed, token, n=f"comando1{i}")
    clock.now += 60
    assert authed.get("/api/terminales/config").json()["ventana"]["abierta"] is False
    acts = [e["accion"] for e in authed.get("/api/terminales/auditoria?limit=50").json()["entradas"]]
    assert "ventana_vencida" in acts


def test_second_window_invalidates_first(authed, on, clock):
    first = open_window(authed)
    second = open_window(authed)
    assert cmd(authed, first).status_code == 401
    assert cmd(authed, second).status_code == 401


def test_logout_and_revoke_all_close_window(authed, on, clock):
    open_window(authed)
    assert authed.app.state.tacciones.ventana.abierta()
    authed.post("/api/sessions/revoke-all")
    assert not authed.app.state.tacciones.ventana.abierta()
    assert authed.post("/api/login", json={"pin": PIN}).status_code == 200
    open_window(authed)
    authed.post("/api/logout")
    assert not authed.app.state.tacciones.ventana.abierta()


def test_close_endpoint_is_idempotent(authed, on, clock):
    assert authed.post("/api/terminales/ventana/cerrar").json() == {"ok": True}
    open_window(authed)
    assert authed.post("/api/terminales/ventana/cerrar").json() == {"ok": True}
    assert authed.post("/api/terminales/ventana/cerrar").json() == {"ok": True}
    assert not authed.app.state.tacciones.ventana.abierta()


def test_window_open_rate_limit_10_per_hour(authed, on, clock):
    for _ in range(10):
        open_window(authed)
    r = authed.post("/api/terminales/ventana", json={"pin": PIN})
    assert r.status_code == 429


@pytest.mark.parametrize("bad", ["a\nb", "a\rb", "a\tb", "a\x1bb", "a\x9bb", "a‮b", "a​b", "a b", "",
                                 "x" * 501, " ls", "ls ", "-rf /", "rm\u00a0-rf", "ls\u3000x", "a\u2029b",
                                 "a\u3164b", "a\u2800b", "a\ue000b", "a\U000e0041b", "a\u2066b"])
def test_command_validation_rejects(authed, on, fake, clock, bad):
    token = open_window(authed)
    r = cmd(authed, token, comando=bad)
    assert r.status_code == 400
    assert sends(fake) == []


def test_command_exact_argv_and_idempotency(authed, on, fake, clock):
    token = open_window(authed)
    assert cmd(authed, token, comando="git status").json() == {"ok": True}
    assert fake.calls_of("teclas") == [("teclas", PANE, ("ctrl-e", "ctrl-u"))]
    assert fake.calls_of("ejecutar") == [("ejecutar", PANE, "git status")]
    assert [c[0] for c in fake.calls if c[0] in ("teclas", "ejecutar")] == ["teclas", "ejecutar"]
    r = cmd(authed, token, comando="git status")
    assert r.status_code == 409 and r.json()["detail"] == "ya se hizo"
    assert len(fake.calls_of("teclas")) == 1 and len(fake.calls_of("ejecutar")) == 1


def test_limpiar_linea_manda_teclas_neutrales(authed, on, fake, clock):
    token = open_window(authed)
    cmd(authed, token, pane="w3:p1", comando="ls")
    assert fake.calls_of("teclas")[0] == ("teclas", "w3:p1", ("ctrl-e", "ctrl-u"))
    assert fake.calls_of("ejecutar") == [("ejecutar", "w3:p1", "ls")]


def test_command_accepts_unicode_nfc_and_500_chars(authed, on, fake, clock):
    token = open_window(authed)
    assert cmd(authed, token, comando="echo ñ" + "a" * 494).status_code == 200
    assert fake.calls_of("ejecutar")[-1] == ("ejecutar", PANE, "echo ñ" + "a" * 494)
    assert cmd(authed, token, comando="echo ñ", n="comando02").status_code == 200
    assert fake.calls_of("ejecutar")[-1] == ("ejecutar", PANE, "echo ñ")


def test_command_target_checks(authed, on, fake, clock):
    token = open_window(authed)
    h = huella(authed)
    ok = {"id": "comando01", "pane_id": PANE, "comando": "ls"}
    hd = {"X-Orq-Escritura": token}
    assert authed.post("/api/terminales/comando", json={**ok, "huella": "0" * 32}, headers=hd).status_code == 409
    assert authed.post("/api/terminales/comando", json={**ok, "id": "comando02", "pane_id": "w1:p1", "huella": h},
                       headers=hd).status_code == 403
    pr = huella(authed, "w3:p1")
    r = authed.post("/api/terminales/comando", json={**ok, "id": "comando03", "pane_id": "w3:p1", "huella": pr}, headers=hd)
    assert r.status_code == 200
    r = authed.post("/api/terminales/comando", json={**ok, "id": "comando0c", "pane_id": "w3:p2", "huella": pr}, headers=hd)
    assert r.status_code == 403
    hn = huella(authed, "w1:p5")
    r = authed.post("/api/terminales/comando", json={**ok, "id": "comando04", "pane_id": "w1:p5", "huella": hn}, headers=hd)
    assert r.status_code == 409 and "node" in r.json()["detail"]
    assert {c[1] for c in fake.calls_of("ejecutar")} == {"w3:p1"}


def test_command_rapido_uses_config_text(authed, on, fake, clock):
    a = authed.app.state.tacciones
    a.rapidos = ["docker compose ps", "git status"]
    token = open_window(authed)
    r = cmd(authed, token, comando="git status", rapido=1)
    assert r.status_code == 200
    assert fake.calls_of("ejecutar")[-1] == ("ejecutar", PANE, "git status")
    e = authed.get("/api/terminales/auditoria").json()["entradas"][0]
    assert e["rapido"] is True and e["comando"] == "git status"
    assert cmd(authed, token, n="comando02", comando="git status", rapido=5).status_code == 400


def test_command_rapido_must_match_what_was_confirmed(authed, on, fake, clock):
    """Si la lista cambió entre la confirmación y el envío, el índice ya no apunta a lo que se vio."""
    a = authed.app.state.tacciones
    a.rapidos = ["docker compose ps", "git status"]
    token = open_window(authed)
    assert cmd(authed, token, n="comando01", comando="rm -rf /tmp/x", rapido=1).status_code == 409
    assert cmd(authed, token, n="comando02", comando="docker compose ps", rapido=1).status_code == 409
    r = authed.post("/api/terminales/comando", json={"id": "comando03", "pane_id": PANE, "huella": huella(authed),
                                                      "rapido": 1}, headers={"X-Orq-Escritura": token})
    assert r.status_code == 409
    assert sends(fake) == []


def test_rapidos_config_is_validated_and_capped():
    got = tacc.rapidos_validos(["ls", "bad\ncmd", "-x", 5, " pad", *[f"c{i}" for i in range(20)]])
    assert got[0] == "ls" and len(got) == 12 and "bad\ncmd" not in got


def test_command_rate_limit_6_per_minute(authed, on, fake, clock):
    token = open_window(authed)
    codes = [cmd(authed, token, n=f"comando{i:02d}").status_code for i in range(7)]
    assert codes == [200] * 6 + [429]
    clock.now += 61
    token = open_window(authed)
    assert cmd(authed, token, n="comando90").status_code == 200


def test_command_audit_and_push_redacted(authed, on, fake, clock, tmp_path):
    sent: list = []
    _push_app(authed.app, tmp_path, sent)
    token = open_window(authed)
    cmd(authed, token, comando="export API_TOKEN=abc123secret")
    line = json.loads(authed.app.state.tacciones.audit.path.read_text().splitlines()[-1])
    assert line["accion"] == "comando" and "abc123secret" not in line["comando"]
    assert any("abc123secret" in json.dumps(m) for m in sent) is False
    assert [m["title"] for m in sent][0] == "Se abrió la escritura de terminales"
    assert any(m["title"].startswith("Comando en") for m in sent)
    assert PIN not in authed.app.state.tacciones.audit.path.read_text()


def test_bad_pin_push(authed, on, tmp_path):
    sent: list = []
    _push_app(authed.app, tmp_path, sent)
    authed.post("/api/terminales/ventana", json={"pin": "00000000"})
    assert sent[0]["title"] == "PIN incorrecto al abrir la escritura"


def test_new_routes_hardening(authed, on):
    for path in ("ventana", "ventana/cerrar", "comando"):
        assert authed.post(f"/api/terminales/{path}", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
        assert authed.post(f"/api/terminales/{path}", content=b"{}", headers={"Content-Type": "text/plain"}).status_code == 415
        assert authed.get(f"/api/terminales/{path}").status_code == 405
        assert authed.post(f"/api/terminales/{path}", json={}, headers={"Sec-Fetch-Site": "same-site"}).status_code == 403


# ---------- revisión de seguridad F7 ----------


@pytest.mark.parametrize("valor", ["true", "false", 1, "yes"])
def test_switch_only_accepts_toml_true(authed, cfg, fake, valor):
    cfg.terminales_escritura = valor
    r = authed.post("/api/terminales/ctrl-c", json={"id": "abcdefgh1", "pane_id": PANE, "huella": "x"})
    assert r.status_code == 403 and r.json()["detail"] == "escritura apagada"
    assert authed.post("/api/terminales/ventana", json={"pin": PIN}).status_code == 403
    assert authed.get("/api/terminales/config").json()["escritura"] is False
    assert sends(fake) == []


def test_fingerprint_covers_foreground_process(authed, on, fake):
    """Lo que se confirmó (node) no puede terminar yendo a otro programa (ssh) que arrancó en el medio."""
    b = body(authed, "w1:p5")
    fake.procesos["w1:p5"] = info_proceso(["/usr/bin/ssh", "prod"])
    r = authed.post("/api/terminales/ctrl-c", json=b)
    assert r.status_code == 409 and r.json()["detail"] == "la terminal cambió, revisala de nuevo"
    assert sends(fake) == []


def test_claude_process_without_agent_mark_is_refused(authed, on, fake):
    b = body(authed, "w1:p5")
    fake.procesos["w1:p5"] = info_proceso(["claude", "--resume"])
    r = authed.post("/api/terminales/ctrl-c", json=b)
    assert r.status_code == 403 and r.json()["detail"] == "es una sesión de agente"
    assert sends(fake) == []


def test_id_is_spent_once_keys_were_sent_even_if_herdr_fails(authed, on, fake, clock):
    """Un `pane run` que vence por tiempo pudo haber corrido: reintentar con el mismo id no lo repite."""
    from orquestador.enchufe import TerminalesError

    fake.fallas["ejecutar"] = TerminalesError("herdr no respondió a tiempo")
    token = open_window(authed)
    assert cmd(authed, token, comando="make deploy").status_code == 502
    r = cmd(authed, token, comando="make deploy")
    assert r.status_code == 409 and r.json()["detail"] == "ya se hizo"
    assert len(fake.calls_of("ejecutar")) == 1


def test_id_is_not_spent_by_a_rejection_before_any_key(authed, on, fake, clock):
    token = open_window(authed)
    assert cmd(authed, token, comando="ls\tx").status_code == 400
    assert cmd(authed, token, comando="ls").status_code == 200


def test_repetir_confirm_refuses_when_a_program_took_over(authed, on, fake):
    b = body(authed)
    prep = authed.post("/api/terminales/repetir/preparar", json=b).json()
    fake.procesos[PANE] = info_proceso(["vim"])
    r = authed.post("/api/terminales/repetir/confirmar",
                    json={"id": "abcdefgh9", "pane_id": PANE, "huella2": prep["huella2"], "ejecutar": True})
    assert r.status_code == 409
    assert ("teclas", PANE, ("enter",)) not in fake.calls_of("teclas")
    assert ("teclas", PANE, ("ctrl-e", "ctrl-u")) not in fake.calls_of("teclas")


def test_audit_error_is_redacted(authed, on, fake):
    from orquestador.enchufe import TerminalesError

    fake.fallas["teclas"] = TerminalesError("error: unexpected argument 'TOKEN=supersecreto1'")
    assert authed.post("/api/terminales/ctrl-c", json=body(authed, "w1:p5")).status_code == 502
    raw = authed.app.state.tacciones.audit.path.read_text()
    assert "supersecreto1" not in raw


def test_board_title_is_redacted_and_has_no_output(authed, fake):
    snap = snap_de(fake)
    next(p for p in snap["panes"] if p["pane_id"] == "w1:p5")["terminal_title_stripped"] = (
        "curl -H Authorization: Bearer abcdefsecret https://u:pw1234@x")
    aplicar_snapshot(fake, snap)
    board = json.dumps(authed.get("/api/board").json())
    assert "abcdefsecret" not in board and "pw1234" not in board
    assert "listo" not in board and "segunda" not in board


def test_redaction_extra_patterns():
    assert "hunter22" not in tacc.redactar("sshpass -p hunter22 ssh x")
    assert "hunter22" not in tacc.redactar("curl -u admin:hunter22 https://x")
    assert "hunter22" not in tacc.redactar("curl --user=admin:hunter22 https://x")


def test_concurrent_wrong_pins_cannot_outrun_the_limiter(authed, on):
    """Muchos PIN en paralelo: el limitador compartido corta a los 5, no después de que todos pasaron el chequeo."""
    import asyncio
    import time as _time

    a = authed.app.state.tacciones
    checked: list = []

    def slow_verify(pin, stored):
        checked.append(pin)
        _time.sleep(0.01)
        return False

    a.verify = slow_verify
    a.notify = None

    async def many():
        ctx = tacc.Ctx(ip="100.64.0.9", cookie="c")
        return await asyncio.gather(*(a.abrir_ventana(ctx, tacc.VentanaBody(pin=f"{i:08d}")) for i in range(30)),
                                    return_exceptions=True)

    results = asyncio.run(many())
    assert len(checked) == 5
    assert sorted({r.status for r in results}) == [401, 429]


def test_lone_surrogate_from_json_escape_is_rejected(authed, on, fake, clock):
    token = open_window(authed)
    raw = ('{"id":"comando01","pane_id":"%s","huella":"%s","comando":"ls \\ud800"}' % (PANE, huella(authed))).encode()
    r = authed.post("/api/terminales/comando", content=raw,
                    headers={"Content-Type": "application/json", "X-Orq-Escritura": token})
    assert r.status_code == 400
    assert sends(fake) == []


def test_push_carries_the_pane_so_the_tap_opens_that_terminal(authed, on, tmp_path, fake):
    sent: list = []
    _push_app(authed.app, tmp_path, sent)
    assert authed.post("/api/terminales/ctrl-c", json=body(authed, "w1:p5")).status_code == 200
    assert sent[-1]["kind"] == "terminal" and sent[-1]["pane_id"] == "w1:p5"


def test_preview_is_rate_limited(authed, fake, clock):
    codes = [authed.post("/api/terminales/preview", json={"pane_id": PANE}).status_code for _ in range(61)]
    assert codes[:60] == [200] * 60 and codes[60] == 429


def test_salida_expone_motivo_de_escritura(authed, on):
    ok = authed.get(f"/api/terminales/{PANE}/salida").json()
    assert ok["puede_escribir"] is True and ok["motivo"] is None
    assert authed.get(f"/api/terminales/{PANE}/salida", params={"rev": ok["revision"]}).json()["motivo"] is None
    busy = authed.get("/api/terminales/w1:p5/salida").json()
    assert busy["puede_escribir"] is False and busy["motivo"] == "ocupada"
    sup = authed.get("/api/terminales/w3:p1/salida").json()
    assert sup["puede_escribir"] is True and sup["motivo"] is None
    assert "s.js" not in json.dumps(busy)


def test_salida_motivo_apagada(authed, fake):
    r = authed.get(f"/api/terminales/{PANE}/salida").json()
    assert r["puede_escribir"] is False and r["motivo"] == "apagada"


@pytest.mark.parametrize("argv", [["claude", "--resume"], ["node", "/home/u/.npm/bin/claude"],
                                  ["/home/u/.local/share/claude/versions/2.1.316"],
                                  ["npx", "@anthropic-ai/claude-code"]])
def test_claude_without_agent_mark_is_refused_in_preview_and_actions(authed, on, fake, argv):
    """Un Claude que Herdr todavía no marcó como agente (también vía node/npx o el binario versionado) da 403 en preview y acciones (el visor sí la deja ver: es una consola)."""
    h = huella(authed, "w3:p1")
    proc = info_proceso(argv)
    for pane in ("w3:p1", PANE):
        fake.procesos[pane] = proc
        r = authed.post("/api/terminales/preview", json={"pane_id": pane})
        assert r.status_code == 403 and r.json()["detail"] == "es una sesión de agente"
    r = authed.post("/api/terminales/ctrl-c", json={"id": "abcdefghz", "pane_id": "w3:p1", "huella": h})
    assert r.status_code == 403 and sends(fake) == []
    assert fake.calls_of("leer") == []


def test_abrir_pedido_dos_claude_crea_antes_y_espera_en_paralelo(tmp_path):
    import asyncio

    from conftest import make_snapshot
    from orquestador import terminales_acciones as tacc
    from orquestador.enchufe import FakeTerminales
    from orquestador.enchufe.mux import Mux
    from orquestador.terminales import ProcessInfoCache, Terminales

    g = FakeTerminales(nombre="guardian")
    g.proximos_ids = [("g1", None, "g1:p1"), ("g1", None, "g1:p2")]
    h = FakeTerminales.desde_snapshot(make_snapshot(), nombre="herdr")
    mux = Mux([h, g], nuevas_en="guardian")

    orden: list[tuple] = []
    esperas_activas = 0
    max_concurrente = 0

    orig_espacio = g.crear_espacio

    async def crear_espacio_tr(*a, **kw):
        orden.append(("crear_espacio",))
        return await orig_espacio(*a, **kw)

    g.crear_espacio = crear_espacio_tr  # type: ignore[method-assign]

    orig_linea = g.crear_linea

    async def crear_linea_tr(*a, **kw):
        orden.append(("crear_linea",))
        return await orig_linea(*a, **kw)

    g.crear_linea = crear_linea_tr  # type: ignore[method-assign]

    async def esperar_tr(sesion_id, timeout):
        nonlocal esperas_activas, max_concurrente
        orden.append(("esperar", sesion_id))
        esperas_activas += 1
        max_concurrente = max(max_concurrente, esperas_activas)
        await asyncio.sleep(0.05)
        esperas_activas -= 1
        return "guardian"

    mux.esperar_listo = esperar_tr  # type: ignore[method-assign]

    terminales = Terminales(mux, ProcessInfoCache(mux), lambda: set(), writes=lambda: True)
    ta = tacc.TerminalActions(
        terminales,
        mux,
        {},
        tacc.Audit(tmp_path),
        lambda: True,
        plan_cwds=lambda: ["/tmp"],
    )
    item = {
        "carpeta": "/tmp",
        "tarjeta": "W",
        "pestanas": [
            {"nombre": "A", "tipo": "claude", "mensaje": "uno", "carpeta": "/tmp"},
            {"nombre": "B", "tipo": "claude", "mensaje": "dos", "carpeta": "/tmp"},
        ],
    }

    asyncio.run(
        ta.abrir_desde_pedido_pestana(tacc.Ctx(), item, idempotencia="abrirpar01", grupo=None)
    )

    idx_espacio = orden.index(("crear_espacio",))
    idx_linea = orden.index(("crear_linea",))
    idx_esperar1 = next(i for i, e in enumerate(orden) if e[0] == "esperar")
    assert idx_espacio < idx_esperar1 and idx_linea < idx_esperar1
    assert max_concurrente == 2


def _abrir_pedido_un_claude(tmp_path, esperar_listo, estados=None):
    import asyncio

    from orquestador import terminales_acciones as tacc
    from orquestador.enchufe import FakeTerminales
    from orquestador.enchufe.mux import Mux
    from orquestador.terminales import ProcessInfoCache, Terminales

    g = FakeTerminales(nombre="guardian")
    g.proximos_ids = [("g1", None, "g1:p1")]
    mux = Mux([g], nuevas_en="guardian")
    mux.esperar_listo = esperar_listo  # type: ignore[method-assign]
    terminales = Terminales(mux, ProcessInfoCache(mux), lambda: set(), writes=lambda: True)
    ta = tacc.TerminalActions(
        terminales, mux, {}, tacc.Audit(tmp_path), lambda: True,
        plan_cwds=lambda: ["/tmp"], estados=estados,
    )
    item = {"carpeta": "/tmp", "pestanas": [{"nombre": "A", "tipo": "claude", "mensaje": "uno", "carpeta": "/tmp"}]}
    out = asyncio.run(ta.abrir_desde_pedido_pestana(tacc.Ctx(), item, idempotencia="abrirlisto1", grupo=None))
    return out["detalle"][0]


def test_abrir_pedido_espera_listo_no_idle(tmp_path, caplog):
    from orquestador.enchufe.base import Tiempo

    llamadas: list[tuple] = []

    async def vence(sesion_id, timeout):
        llamadas.append((sesion_id, timeout))
        raise Tiempo("no quedó listo")

    with caplog.at_level("WARNING", logger="orquestador.terminales"):
        fila = _abrir_pedido_un_claude(tmp_path, vence)
    assert llamadas == [("g1:p1", 90.0)]
    assert fila["pegado"] is False
    assert "g1:p1 no quedó listo" in caplog.text
    assert "uno" not in caplog.text


def test_abrir_pedido_listo_vencido_con_ganchos_pega_igual(tmp_path):
    from orquestador.enchufe.base import Tiempo
    from orquestador.estado_sesiones import EstadoSesiones
    from orquestador.ganchos.mensaje import Ids, MensajeGancho

    estados = EstadoSesiones()
    estados.recibir(MensajeGancho("SessionStart", "g", Ids("g1:p1", None, None, None, "s"), {}), "g1:p1")

    async def vence(sesion_id, timeout):
        raise Tiempo("no quedó listo")

    assert _abrir_pedido_un_claude(tmp_path, vence, estados)["pegado"] is True


def test_abrir_pedido_listo_vencido_con_guardian_nuevo_no_pega_aunque_haya_ganchos(tmp_path, caplog):
    from orquestador.enchufe.base import Tiempo
    from orquestador.estado_sesiones import EstadoSesiones
    from orquestador.ganchos.mensaje import Ids, MensajeGancho

    estados = EstadoSesiones()
    estados.recibir(MensajeGancho("SessionStart", "g", Ids("g1:p1", None, None, None, "s"), {}), "g1:p1")

    async def vence(sesion_id, timeout):
        raise Tiempo("no quedó listo", listo_conocido=True)

    with caplog.at_level("WARNING", logger="orquestador.terminales"):
        assert _abrir_pedido_un_claude(tmp_path, vence, estados)["pegado"] is False
    assert "g1:p1 no quedó listo" in caplog.text


@pytest.mark.parametrize("exc_name", ["NoDisponible", "NoExiste", "TerminalesError"])
def test_abrir_pedido_listo_no_disponible_no_pega(tmp_path, exc_name):
    from orquestador.enchufe import base
    from orquestador.estado_sesiones import EstadoSesiones
    from orquestador.ganchos.mensaje import Ids, MensajeGancho

    estados = EstadoSesiones()
    estados.recibir(MensajeGancho("SessionStart", "g", Ids("g1:p1", None, None, None, "s"), {}), "g1:p1")

    async def falla(sesion_id, timeout):
        raise getattr(base, exc_name)("x")

    assert _abrir_pedido_un_claude(tmp_path, falla, estados)["pegado"] is False


def test_abrir_pedido_listo_pega(tmp_path):
    async def listo(sesion_id, timeout):
        return "guardian"

    assert _abrir_pedido_un_claude(tmp_path, listo)["pegado"] is True


def _ta_un_claude(tmp_path, esperar_listo):
    from orquestador import terminales_acciones as tacc
    from orquestador.enchufe import FakeTerminales
    from orquestador.enchufe.mux import Mux
    from orquestador.terminales import ProcessInfoCache, Terminales

    g = FakeTerminales(nombre="guardian")
    g.proximos_ids = [("g1", None, "g1:p1")]
    mux = Mux([g], nuevas_en="guardian")
    mux.esperar_listo = esperar_listo  # type: ignore[method-assign]
    terminales = Terminales(mux, ProcessInfoCache(mux), lambda: set(), writes=lambda: True)
    ta = tacc.TerminalActions(
        terminales, mux, {}, tacc.Audit(tmp_path), lambda: True, plan_cwds=lambda: ["/tmp"],
    )
    item = {"carpeta": "/tmp", "pestanas": [{"nombre": "A", "tipo": "claude", "mensaje": "uno", "carpeta": "/tmp"}]}
    return tacc, ta, item


def test_abrir_marca_abierto_antes_de_pegar(tmp_path):
    import asyncio

    soltar = asyncio.Event()
    llamadas: list[str] = []

    async def esperar(sesion_id, timeout):
        llamadas.append("esperar")
        await soltar.wait()
        return "guardian"

    tacc, ta, item = _ta_un_claude(tmp_path, esperar)

    def al_crear():
        llamadas.append("al_crear")

    async def correr():
        tarea = asyncio.create_task(
            ta.abrir_desde_pedido_pestana(tacc.Ctx(), item, idempotencia="abrirtemp1", grupo=None, al_crear=al_crear)
        )
        for _ in range(50):
            await asyncio.sleep(0)
            if "esperar" in llamadas:
                break
        assert llamadas.count("al_crear") == 1
        assert not tarea.done()
        soltar.set()
        return await tarea

    out = asyncio.run(correr())
    assert llamadas.count("al_crear") == 1
    assert llamadas.index("al_crear") < llamadas.index("esperar")
    assert out["detalle"][0]["pegado"] is True


def test_abrir_al_crear_que_falla_no_tumba_la_apertura(tmp_path, caplog):
    import asyncio

    async def esperar(sesion_id, timeout):
        return "guardian"

    tacc, ta, item = _ta_un_claude(tmp_path, esperar)

    def al_crear():
        raise RuntimeError("boom")

    with caplog.at_level("WARNING", logger="orquestador.terminales"):
        out = asyncio.run(
            ta.abrir_desde_pedido_pestana(tacc.Ctx(), item, idempotencia="abrirtemp2", grupo=None, al_crear=al_crear)
        )
    assert out["detalle"][0]["pegado"] is True
    assert any("al_crear" in r.getMessage() for r in caplog.records)


def _ta_guardian(tmp_path):
    from orquestador import terminales_acciones as tacc
    from orquestador.enchufe import FakeTerminales
    from orquestador.enchufe.mux import Mux
    from orquestador.terminales import ProcessInfoCache, Terminales

    g = FakeTerminales(nombre="guardian")
    mux = Mux([g], nuevas_en="guardian")

    async def listo(sesion_id, timeout):
        return "guardian"

    mux.esperar_listo = listo  # type: ignore[method-assign]
    terminales = Terminales(mux, ProcessInfoCache(mux), lambda: set(), writes=lambda: True)
    ta = tacc.TerminalActions(terminales, mux, {}, tacc.Audit(tmp_path), lambda: True, plan_cwds=lambda: ["/tmp"])
    return ta, g, tacc


def _item_dos_claude():
    return {
        "carpeta": "/tmp",
        "tarjeta": "W",
        "pestanas": [
            {"nombre": "A", "tipo": "claude", "mensaje": "uno", "carpeta": "/tmp"},
            {"nombre": "B", "tipo": "claude", "mensaje": "dos", "carpeta": "/tmp"},
        ],
    }


def test_abrir_pedido_con_permiso_arranca_cada_claude_en_ese_modo(tmp_path):
    import asyncio

    ta, g, tacc = _ta_guardian(tmp_path)
    out = asyncio.run(ta.abrir_desde_pedido_pestana(tacc.Ctx(), _item_dos_claude(), idempotencia="permiso01",
                                                    grupo=None, permiso="default"))
    llamadas = g.calls_of("arrancar_claude")
    assert len(llamadas) == 2
    assert all(c[-1] == "default" and len(c) == 5 for c in llamadas)
    assert sorted(c[1] for c in llamadas) == sorted(out["pane_ids"])


def test_abrir_pedido_sin_permiso_sigue_igual(tmp_path):
    import asyncio

    ta, g, tacc = _ta_guardian(tmp_path)
    asyncio.run(ta.abrir_desde_pedido_pestana(tacc.Ctx(), _item_dos_claude(), idempotencia="permiso02", grupo=None))
    assert all(len(c) == 4 for c in g.calls_of("arrancar_claude"))


def test_abrir_pedido_permiso_que_relaja_no_abre_nada(tmp_path):
    import asyncio

    import pytest

    ta, g, tacc = _ta_guardian(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(ta.abrir_desde_pedido_pestana(tacc.Ctx(), _item_dos_claude(), idempotencia="permiso03",
                                                  grupo=None, permiso="auto"))
    assert not g.calls_of("crear_espacio")


def test_abrir_pedido_revalida_el_comando_antes_de_escribir(tmp_path):
    import asyncio

    import pytest

    from orquestador.traspaso import TraspasoError

    ta, g, tacc = _ta_guardian(tmp_path)
    item = {"carpeta": "/tmp", "pestanas": [{"nombre": "T", "tipo": "terminal", "carpeta": "/tmp",
                                             "comando": "ls ‮-la"}]}
    with pytest.raises(TraspasoError):
        asyncio.run(ta.abrir_desde_pedido_pestana(tacc.Ctx(), item, idempotencia="cmdmalo1", grupo=None))
    assert not g.calls_of("escribir")
