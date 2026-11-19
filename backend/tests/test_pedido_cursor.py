"""Pedido de trabajador Cursor: `[colmena-pestana] {"accion":"cursor",…}` → pedido pendiente → Ando aprueba."""
from __future__ import annotations

import pytest
from conftest import SID
from test_pedidos_pestana import (APPLE, KEYS, _json_cmd, _msg_bash, apagada_app, enchufe,  # noqa: F401
                                  sender, wall)

from orquestador.colmena_pestana import pedido_desde_comando_bash
from orquestador.traspaso import TraspasoError


def test_parsea_accion_cursor_valida():
    cmd = _json_cmd(accion="cursor", carpeta="/tmp/repo", nombre="Renombrar helpers",
                    pedido="Renombrá  foo a bar\nen a.py")
    assert pedido_desde_comando_bash(cmd) == {"accion": "cursor", "carpeta": "/tmp/repo",
                                              "nombre": "Renombrar helpers", "pedido": "Renombrá foo a bar en a.py"}
    con_modelo = _json_cmd(accion="cursor", carpeta="/tmp/repo", nombre="X", pedido="y", modelo="gpt-5.2[high]")
    assert pedido_desde_comando_bash(con_modelo)["modelo"] == "gpt-5.2[high]"
    assert len(pedido_desde_comando_bash(_json_cmd(accion="cursor", carpeta="/tmp", nombre="X",
                                                   pedido="p" * 4000))["pedido"]) == 4000


@pytest.mark.parametrize("kw", [
    {"nombre": "", "pedido": "x"},
    {"pedido": "x"},
    {"nombre": "X", "pedido": ""},
    {"nombre": "X"},
    {"nombre": "X", "pedido": "p" * 4001},
    {"nombre": "n" * 61, "pedido": "x"},
    {"nombre": "X", "pedido": "x", "carpeta": ""},
    {"nombre": "X", "pedido": "x", "carpeta": 3},
])
def test_rechaza_cursor_sin_nombre_o_pedido_largo(kw):
    datos = {"accion": "cursor", "carpeta": "/tmp/repo", **kw}
    assert pedido_desde_comando_bash(_json_cmd(**datos)) is None


@pytest.mark.parametrize("modelo", ["--yolo", "a b", "x;rm", "m" * 81, "", 3, "gpt/5"])
def test_rechaza_modelo_raro(modelo):
    cmd = _json_cmd(accion="cursor", carpeta="/tmp/repo", nombre="X", pedido="y", modelo=modelo)
    assert pedido_desde_comando_bash(cmd) is None


def test_hook_crea_pedido_cursor_con_carpeta_permitida(apagada_app, tmp_path):
    c, app, push, sender, _ = apagada_app
    repo = tmp_path / "repo"
    repo.mkdir()
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cursor", carpeta=str(repo), nombre="Renombrar",
                                                          pedido="Hacé X", modelo="composer-2.5-fast")), "w1:p1")
    pendientes = c.get("/api/pedidos-pestana").json()
    assert len(pendientes) == 1
    p = pendientes[0]
    assert p["accion"] == "cursor" and p["carpeta"] == str(repo) and p["nombre"] == "Renombrar"
    assert p["mensaje"] == "Hacé X" and p["cursor"] == {"modelo": "composer-2.5-fast"}
    aviso = [e for e in push.avisos.items if e["kind"] == "pestana"][0]
    assert aviso["titulo"] == "Pedido de trabajador Cursor"
    assert aviso["cuerpo"].endswith("quiere que Cursor haga: Renombrar")


def test_hook_ignora_carpeta_no_permitida(apagada_app):
    c, app, push, sender, _ = apagada_app
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cursor", carpeta="/etc", nombre="X",
                                                          pedido="y")), "w1:p1")
    assert c.get("/api/pedidos-pestana").json() == [] and not push.avisos.items


def test_hook_cursor_en_repo_colmena_descarta_con_aviso(apagada_app, tmp_path, monkeypatch):
    from orquestador import config

    c, app, push, _, _ = apagada_app
    raiz = tmp_path / "colmena"
    (raiz / ".git").mkdir(parents=True)
    monkeypatch.setattr(config, "REPO_ROOT", raiz)
    descartes = []
    app.state.pedidos_pestana.on_descarte(lambda o, m: descartes.append(m))
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cursor", carpeta=str(raiz), nombre="X",
                                                          pedido="y")), "w1:p1")
    assert c.get("/api/pedidos-pestana").json() == [] and descartes == ["carpeta_colmena"]


class RunnerFalso:
    MAX_SIMULTANEOS = 2

    def __init__(self, error: TraspasoError | None = None):
        self.error = error
        self.llamadas = []

    async def lanzar(self, **kw):
        self.llamadas.append(kw)
        if self.error:
            raise self.error
        return {"id": "a" * 32, "nombre": kw["nombre"], "estado": "corriendo", "ruta": "/r", "rama": "cursor/x-0000",
                "base": "0" * 40, "inicio": 1, "origen": kw["origen"]}


def _pedido(c, app, tmp_path, **extra):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    app.state.pestana_desde_bash(_msg_bash(SID, _json_cmd(accion="cursor", carpeta=str(repo), nombre="Renombrar",
                                                          pedido="Hacé X", **extra)), "w1:p1")
    return c.get("/api/pedidos-pestana").json()[0]["id"], repo


def test_abrir_pedido_cursor_llama_runner_lanzar(apagada_app, tmp_path):
    c, app, _, _, _ = apagada_app
    pid, repo = _pedido(c, app, tmp_path, modelo="composer-2.5-fast")
    runner = RunnerFalso()
    app.state.cursor_runner = runner
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["trabajador"]["id"] == "a" * 32
    kw = runner.llamadas[0]
    assert kw["carpeta"] == str(repo) and kw["pedido"] == "Hacé X" and kw["nombre"] == "Renombrar"
    assert kw["base"] == "head" and kw["modelo"] == "composer-2.5-fast"
    assert kw["origen"]["tipo"] == "claude" and kw["origen"]["pane_id"] == "w1:p1"
    assert kw["origen"]["session_id"] == SID
    assert app.state.pedidos_pestana.get(pid)["estado"] == "abierto"


def test_abrir_cursor_sin_binario_503_y_rechaza(apagada_app, tmp_path):
    c, app, _, _, _ = apagada_app
    pid, _ = _pedido(c, app, tmp_path)
    app.state.cursor_runner = RunnerFalso(TraspasoError(503, "No encuentro cursor-agent en la notebook"))
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 503 and r.json()["detail"] == "No encuentro cursor-agent en la notebook"
    assert app.state.pedidos_pestana.get(pid)["estado"] == "rechazado"


def test_abrir_cursor_con_tope_429_queda_pendiente(apagada_app, tmp_path):
    c, app, _, _, _ = apagada_app
    pid, _ = _pedido(c, app, tmp_path)
    app.state.cursor_runner = RunnerFalso(TraspasoError(429, "tope", {"retry_after": 60}))
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 429 and r.headers["retry-after"] == "60"
    assert app.state.pedidos_pestana.get(pid)["estado"] == "pendiente"


def test_app_arma_cursor_runner_real(apagada_app):
    from orquestador.cursor_runner import CursorRunner

    c, app, _, _, _ = apagada_app
    assert isinstance(app.state.cursor_runner, CursorRunner)


def _endpoint(app, path):
    """Busca la función de una ruta, también dentro de routers incluidos."""
    pila = list(app.router.routes)
    while pila:
        r = pila.pop()
        if getattr(r, "path", None) and str(r.path).endswith(path) and hasattr(r, "endpoint"):
            return r.endpoint
        sub = getattr(r, "router", None) or getattr(r, "original_router", None)
        pila.extend(getattr(sub, "routes", None) or getattr(r, "routes", None) or [])
    raise LookupError(path)


class RunnerConPausa(RunnerFalso):
    """En medio del lanzamiento corre `durante` (otra aprobación, un rechazo) en el mismo loop y guarda qué dio."""

    def __init__(self, durante):
        super().__init__()
        self.durante = durante
        self.respuestas = []

    async def lanzar(self, **kw):
        from fastapi import HTTPException

        try:
            self.respuestas.append(await self.durante())
        except HTTPException as exc:
            self.respuestas.append(exc.status_code)
        return await super().lanzar(**kw)


def test_dos_aprobaciones_a_la_vez_lanzan_un_solo_trabajador(apagada_app, tmp_path):
    from types import SimpleNamespace

    c, app, _, _, _ = apagada_app
    pid, _ = _pedido(c, app, tmp_path)
    abrir = _endpoint(app, "/pedidos-pestana/{pedido_id}/abrir")
    runner = RunnerConPausa(lambda: abrir(pid, SimpleNamespace(app=app)))
    app.state.cursor_runner = runner
    r = c.post(f"/api/pedidos-pestana/{pid}/abrir")
    assert r.status_code == 200
    assert len(runner.llamadas) == 1 and runner.respuestas == [409]
    assert app.state.pedidos_pestana.get(pid)["estado"] == "abierto"


def test_rechazar_mientras_se_lanza_da_409(apagada_app, tmp_path):
    c, app, _, _, _ = apagada_app
    pid, _ = _pedido(c, app, tmp_path)
    rechazar = _endpoint(app, "/pedidos-pestana/{pedido_id}/rechazar")
    runner = RunnerConPausa(lambda: rechazar(pid))
    app.state.cursor_runner = runner
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 200
    assert runner.respuestas == [409]
    assert app.state.pedidos_pestana.get(pid)["estado"] == "abierto"


def test_si_vence_mientras_se_lanza_no_avisa_vencido(apagada_app, tmp_path):
    c, app, _, _, _ = apagada_app
    pid, _ = _pedido(c, app, tmp_path)
    store = app.state.pedidos_pestana
    descartes = []
    store.on_descarte(lambda o, m: descartes.append(m))

    async def vencer():
        store._items[pid]["vence"] = store.wall() - 1
        return store.listar_pendientes()

    app.state.cursor_runner = RunnerConPausa(vencer)
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 200
    assert descartes == [] and store.get(pid)["estado"] == "abierto"


def test_tope_durante_el_lanzamiento_vuelve_a_pendiente(apagada_app, tmp_path):
    c, app, _, _, _ = apagada_app
    pid, _ = _pedido(c, app, tmp_path)
    app.state.cursor_runner = RunnerFalso(TraspasoError(429, "tope", {"retry_after": 60}))
    assert c.post(f"/api/pedidos-pestana/{pid}/abrir").status_code == 429
    assert c.post(f"/api/pedidos-pestana/{pid}/rechazar").status_code == 200
