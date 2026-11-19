"""Botón "Ir a PC": abre una terminal de la notebook enganchada a la sesión viva. Nunca abre ventanas reales."""
import sys

import pytest

from conftest import SID
from orquestador import ir_a_pc


class Lanzador:
    def __init__(self, error=None):
        self.llamadas = []
        self.envs = []
        self.error = error

    async def __call__(self, argv, env=None):
        self.llamadas.append(list(argv))
        self.envs.append(env)
        if self.error:
            raise self.error


class Systemctl:
    def __init__(self, salida=""):
        self.salida = salida
        self.llamadas = 0

    async def __call__(self):
        self.llamadas += 1
        return self.salida


@pytest.fixture
def systemctl(app):
    sc = Systemctl()
    app.state.ir_a_pc.systemctl = sc
    return sc


@pytest.fixture
def lanzador(app, monkeypatch, systemctl, tmp_path):
    lz = Lanzador()
    app.state.ir_a_pc.lanzador = lz
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(ir_a_pc.shutil, "which", lambda n: "/usr/bin/gnome-terminal")
    return lz


@pytest.fixture
def en_guardian(app, monkeypatch):
    """El tablero que ve el hub trae la sesión en una terminal del guardián (los ids g1:pN)."""

    def poner(pane="g1:p1", titulo="Título terminal"):
        board = {"workspaces": [{"tabs": [{"agents": [{
            "pane_id": pane, "kind": "claude", "status": "idle", "session_id": SID,
            "cwd": "/tmp", "title": titulo, "doing": titulo,
        }]}]}]}
        async def current():
            return board
        monkeypatch.setattr(app.state.hub, "current", current)

    return poner


def test_argv_exacto(authed, en_guardian, lanzador):
    en_guardian()
    r = authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert lanzador.llamadas == [
        ["gnome-terminal", "--title=Título terminal", "--", sys.executable, "-m", "orquestador.cli", "ver", "g1:p1"]
    ]


def test_exige_login(client, lanzador):
    assert client.post(f"/api/sesiones/{SID}/ir-a-pc").status_code in (401, 403)
    assert lanzador.llamadas == []


def test_sid_invalido(authed, lanzador):
    assert authed.post("/api/sesiones/a$b/ir-a-pc").status_code == 400
    assert lanzador.llamadas == []


def test_sesion_fuera_del_guardian_409(authed, lanzador):
    r = authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    assert r.status_code == 409
    assert r.json()["detail"] == "Esta sesión no corre en una terminal de Colmena"
    assert lanzador.llamadas == []


def _sin_pantalla(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)


def test_sin_display_503(authed, en_guardian, lanzador, monkeypatch):
    en_guardian()
    _sin_pantalla(monkeypatch)
    r = authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    assert r.status_code == 503 and r.json()["detail"] == "La notebook no tiene la pantalla activa"
    assert lanzador.llamadas == []


def test_con_display_x11_alcanza(authed, en_guardian, lanzador, monkeypatch):
    en_guardian()
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 200


def test_sin_gnome_terminal_503(authed, en_guardian, lanzador, monkeypatch):
    en_guardian()
    monkeypatch.setattr(ir_a_pc.shutil, "which", lambda n: None)
    r = authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    assert r.status_code == 503 and r.json()["detail"] == "No encontré una terminal en la notebook"
    assert lanzador.llamadas == []


def test_segunda_llamada_en_3_s_429(authed, en_guardian, lanzador):
    en_guardian()
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 200
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 429
    assert len(lanzador.llamadas) == 1


def test_pasados_3_s_vuelve_a_lanzar(authed, app, en_guardian, lanzador):
    en_guardian()
    t = [100.0]
    app.state.ir_a_pc.reloj = lambda: t[0]
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 200
    t[0] += 3.1
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 200
    assert len(lanzador.llamadas) == 2


def test_falla_al_arrancar_503(authed, app, en_guardian, lanzador, caplog):
    en_guardian()
    lanzador.error = OSError("secreto-no-loguear")
    r = authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    assert r.status_code == 503
    assert "secreto" not in r.text and "secreto" not in caplog.text


def test_titulo_saneado(authed, en_guardian, lanzador):
    en_guardian(titulo="a\x00b\x1b[31m\nc\td" + "x" * 200)
    authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    titulo = lanzador.llamadas[0][1]
    assert titulo.startswith("--title=")
    t = titulo[len("--title="):]
    assert len(t) <= 80
    assert not any(ord(c) < 32 or ord(c) == 127 for c in t)


def test_titulo_vacio_usa_el_selector(authed, en_guardian, lanzador):
    en_guardian(titulo="\x01\x02")
    authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    assert lanzador.llamadas[0][1] == "--title=g1:p1"


@pytest.mark.parametrize("sel", ["g1:p1", "g12:p3"])
def test_selector_valido(sel):
    assert ir_a_pc.selector_valido(sel)


@pytest.mark.parametrize("sel", ["", "--help", "w1:p1", "g1; ls", "g1:p1\n", "1", "-g1", "g12", "g1:t3", "g1:p"])
def test_selector_invalido(sel):
    assert not ir_a_pc.selector_valido(sel)


def test_el_modulo_del_cli_arranca_con_dash_m(tmp_path):
    import subprocess

    env = {"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": str(tmp_path), "HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, "-m", ir_a_pc.MODULO_CLI, "ver", "g1:p1"], env=env, cwd=str(
        __import__("pathlib").Path(ir_a_pc.__file__).parent.parent), capture_output=True, text=True, timeout=30)
    assert "socket del guardián" in r.stderr


# ---- Ronda 1 ----

def test_completa_la_pantalla_desde_systemctl(authed, en_guardian, lanzador, systemctl, monkeypatch):
    en_guardian()
    _sin_pantalla(monkeypatch)
    systemctl.salida = "FOO=1\nWAYLAND_DISPLAY=wayland-7\nDISPLAY=:9\n"
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 200
    env = lanzador.envs[0]
    assert env["WAYLAND_DISPLAY"] == "wayland-7" and env["DISPLAY"] == ":9"
    assert "FOO" not in env


def test_no_consulta_systemctl_si_ya_hay_pantalla(authed, en_guardian, lanzador, systemctl):
    en_guardian()
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 200
    assert systemctl.llamadas == 0


def test_systemctl_sin_pantalla_503(authed, en_guardian, lanzador, systemctl, monkeypatch):
    en_guardian()
    _sin_pantalla(monkeypatch)
    systemctl.salida = "PATH=/usr/bin\n"
    r = authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    assert r.status_code == 503 and r.json()["detail"] == "La notebook no tiene la pantalla activa"


def test_lista_blanca_de_entorno(authed, en_guardian, lanzador, monkeypatch):
    en_guardian()
    monkeypatch.setenv("FOO_SECRET", "no-pasar")
    monkeypatch.setenv("ORQ_VAPID_SUB", "mailto:x")
    monkeypatch.setenv("LC_TIME", "es_AR.UTF-8")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 200
    env = lanzador.envs[0]
    assert "FOO_SECRET" not in env and "ORQ_VAPID_SUB" not in env
    assert env["LC_TIME"] == "es_AR.UTF-8" and env["XDG_SESSION_TYPE"] == "wayland"
    assert env["WAYLAND_DISPLAY"] == "wayland-0"
    assert set(env) <= set(ir_a_pc.ENTORNO_PERMITIDO) | {k for k in env if k.startswith("LC_")}


def test_dbus_por_defecto_si_existe_el_socket(authed, en_guardian, lanzador, monkeypatch, tmp_path):
    en_guardian()
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    (tmp_path / "bus").write_text("")
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 200
    assert lanzador.envs[0]["DBUS_SESSION_BUS_ADDRESS"] == f"unix:path={tmp_path}/bus"


def test_sin_dbus_503(authed, en_guardian, lanzador, monkeypatch):
    en_guardian()
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    r = authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    assert r.status_code == 503 and r.json()["detail"] == "La notebook no tiene la sesión gráfica disponible"
    assert lanzador.llamadas == []


def test_reintento_tras_fallo_no_da_429(authed, en_guardian, lanzador):
    en_guardian()
    lanzador.error = OSError("x")
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 503
    lanzador.error = None
    assert authed.post(f"/api/sesiones/{SID}/ir-a-pc").status_code == 200


def test_titulo_prefiere_el_nombre_a_la_actividad(authed, app, monkeypatch, lanzador):
    board = {"workspaces": [{"tabs": [{"agents": [{
        "pane_id": "g1:p1", "kind": "claude", "status": "idle", "session_id": SID,
        "cwd": "/tmp", "title": "Mi sesión", "doing": "editando cosas",
    }]}]}]}

    async def current():
        return board

    monkeypatch.setattr(app.state.hub, "current", current)
    authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    assert lanzador.llamadas[0][1] == "--title=Mi sesión"


def test_titulo_sin_nombre_usa_la_actividad(authed, app, monkeypatch, lanzador):
    board = {"workspaces": [{"tabs": [{"agents": [{
        "pane_id": "g1:p1", "kind": "claude", "status": "idle", "session_id": SID,
        "cwd": "/tmp", "title": "", "doing": "editando cosas",
    }]}]}]}

    async def current():
        return board

    monkeypatch.setattr(app.state.hub, "current", current)
    authed.post(f"/api/sesiones/{SID}/ir-a-pc")
    assert lanzador.llamadas[0][1] == "--title=editando cosas"


def test_tope_global_de_5_por_minuto(lanzador, monkeypatch, tmp_path):
    import asyncio

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    t = [0.0]
    ir = ir_a_pc.IrAPc(lanzador=lanzador, reloj=lambda: t[0], systemctl=Systemctl())

    async def abrir(sid):
        await ir.abrir(sid, "g1:p1", "x")

    for i in range(5):
        asyncio.run(abrir(f"s{i}"))
        t[0] += 4
    with pytest.raises(ir_a_pc.IrAPcError) as e:
        asyncio.run(abrir("s9"))
    assert e.value.status == 429
    t[0] += 40
    asyncio.run(abrir("s9"))
    assert len(lanzador.llamadas) == 6


def test_systemctl_real_tolera_que_no_exista(monkeypatch):
    import asyncio

    async def falla(*a, **k):
        raise FileNotFoundError("systemctl")

    monkeypatch.setattr(ir_a_pc.asyncio, "create_subprocess_exec", falla)
    assert asyncio.run(ir_a_pc.leer_systemctl()) == ""


# ---- Ronda 2 ----

class LanzadorBloqueado:
    def __init__(self, error=None):
        import asyncio

        self.liberar = asyncio.Event()
        self.llamadas = []
        self.error = error

    async def __call__(self, argv, env=None):
        self.llamadas.append(argv)
        await self.liberar.wait()
        if self.error:
            raise self.error


def _rafaga(sids, lz, t=None):
    import asyncio

    ir = ir_a_pc.IrAPc(lanzador=lz, reloj=lambda: 0.0, systemctl=Systemctl())

    async def uno(sid):
        try:
            await ir.abrir(sid, "g1:p1", "x")
            return 200
        except ir_a_pc.IrAPcError as e:
            return e.status

    async def main():
        tareas = [asyncio.ensure_future(uno(s)) for s in sids]
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        lz.liberar.set()
        return await asyncio.gather(*tareas), ir

    return asyncio.run(main())


def test_dos_pedidos_concurrentes_a_la_misma_sesion(lanzador):
    lz = LanzadorBloqueado()
    res, _ = _rafaga(["s1", "s1"], lz)
    assert sorted(res) == [200, 429] and len(lz.llamadas) == 1


def test_seis_sesiones_concurrentes_dan_cinco_lanzamientos(lanzador):
    lz = LanzadorBloqueado()
    res, _ = _rafaga([f"s{i}" for i in range(6)], lz)
    assert sorted(res) == [200] * 5 + [429] and len(lz.llamadas) == 5


def test_fallo_devuelve_el_cupo(lanzador):
    lz = LanzadorBloqueado(error=OSError("x"))
    res, ir = _rafaga(["s1"], lz)
    assert res == [503]
    assert ir._ultimo == {} and ir._lanzados == []


def test_systemctl_con_timeout_espera_al_proceso(monkeypatch):
    import asyncio

    eventos = []

    class P:
        async def communicate(self):
            await asyncio.sleep(10)

        def kill(self):
            eventos.append("kill")

        async def wait(self):
            eventos.append("wait")

    async def fake(*a, **k):
        return P()

    monkeypatch.setattr(ir_a_pc.asyncio, "create_subprocess_exec", fake)
    monkeypatch.setattr(ir_a_pc, "TIMEOUT_SYSTEMCTL", 0.01)
    assert asyncio.run(ir_a_pc.leer_systemctl()) == ""
    assert eventos == ["kill", "wait"]
