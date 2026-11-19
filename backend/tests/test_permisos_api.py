import asyncio
import copy
import json

import pytest

from conftest import PIN, SID
from orquestador.permisos import AuditoriaPermisos
from permisos_support import (
    FakeConexion,
    cliente,
    cliente_logueado_sin_origin,
    cliente_sin_login,
    enlazar_al_cambiar,
    pedido,
    pr,
)


def test_sin_sesion_401_y_sin_csrf_403(cliente_sin_login, cliente_logueado_sin_origin):
    assert (
        cliente_sin_login.post("/api/permisos/x/decidir", json={"accion": "permitir"}).status_code
        == 401
    )
    assert cliente_sin_login.get("/api/permisos").status_code == 401
    assert cliente_sin_login.get("/api/permisos/registro").status_code == 401
    assert cliente_sin_login.get("/api/permisos/observacion").status_code == 404
    assert (
        cliente_logueado_sin_origin.post(
            "/api/permisos/x/decidir",
            json={"accion": "permitir"},
            headers={"Origin": "https://evil", "Sec-Fetch-Site": "cross-site"},
        ).status_code
        == 403
    )


def test_permitir_y_rechazar_sin_pin(cliente, pedido):
    p, c = pedido()
    r = cliente.post(f"/api/permisos/{p.id}/decidir", json={"accion": "permitir"})
    assert r.status_code == 200 and r.json()["estado"] == "permitido"
    assert c.respuestas == [{"v": 1, "decision": "allow"}]
    assert (
        cliente.post(f"/api/permisos/{p.id}/decidir", json={"accion": "permitir"}).status_code
        == 409
    )

    p2, c2 = pedido(msg=pr(tool_use_id="t2"))
    r2 = cliente.post(
        f"/api/permisos/{p2.id}/decidir",
        json={"accion": "rechazar", "motivo": "no gracias"},
    )
    assert r2.status_code == 200
    assert c2.respuestas == [{"v": 1, "decision": "deny", "mensaje": "no gracias"}]


def test_siempre_exige_pin_y_no_consume(cliente, pedido):
    p, c = pedido()
    body = {"accion": "siempre", "huella_regla": p.regla.huella()}
    assert cliente.post(f"/api/permisos/{p.id}/decidir", json=body).status_code == 401
    assert (
        cliente.post(f"/api/permisos/{p.id}/decidir", json={**body, "pin": "00000000"}).status_code
        == 401
    )
    assert p.estado == "abierto" and c.respuestas == []
    r = cliente.post(f"/api/permisos/{p.id}/decidir", json={**body, "pin": PIN})
    assert r.status_code == 200 and c.respuestas[0]["reglas"] == [
        {"toolName": "Bash", "ruleContent": "touch:*"}
    ]


def test_lockout_de_pin_compartido(cliente, pedido):
    p, _ = pedido()
    body = {"accion": "siempre", "huella_regla": p.regla.huella(), "pin": "00000000"}
    codigos = [
        cliente.post(f"/api/permisos/{p.id}/decidir", json=body).status_code for _ in range(12)
    ]
    assert 429 in codigos and p.estado == "abierto"


def test_body_con_suggestions_o_regla_propia_se_ignora(cliente, pedido):
    p, c = pedido()
    body = {
        "accion": "siempre",
        "huella_regla": p.regla.huella(),
        "pin": PIN,
        "reglas": [{"toolName": "Bash", "ruleContent": "*"}],
        "permission_suggestions": [{"type": "setMode", "mode": "acceptEdits"}],
    }
    assert cliente.post(f"/api/permisos/{p.id}/decidir", json=body).status_code == 200
    salida = json.dumps(c.respuestas)
    assert "setMode" not in salida and "addDirectories" not in salida and '"*"' not in salida


def test_tarjeta_muestra_regla_y_archivo(cliente, pedido):
    p, _ = pedido()
    (item,) = cliente.get("/api/permisos").json()["pedidos"]
    assert item["regla"] == {
        "herramienta": "Bash",
        "contenido": "touch:*",
        "archivo": "/home/u/p/.claude/settings.local.json",
        "huella": p.regla.huella(),
    }


def test_desde_app_false_decidir_409(cliente, pedido, cfg):
    p, _ = pedido()
    cfg.permisos = {"desde_app": False}
    assert (
        cliente.post(f"/api/permisos/{p.id}/decidir", json={"accion": "permitir"}).status_code
        == 409
    )


def test_observer_herdr_pane_desaparecido_y_sin_conexion(cliente, app):
    async def esc():
        permisos, hub = app.state.permisos, app.state.hub
        if hub.board is None:
            await hub.refresh()
        cambio, restaurar = enlazar_al_cambiar(permisos)
        try:
            c = FakeConexion()
            p = await permisos.atender(pr(tool_use_id="t_obs1"), "w1:p1", c)
            assert p.estado == "abierto"

            board_sin_pane = copy.deepcopy(hub.board)
            for ws in board_sin_pane.get("workspaces", []):
                for tab in ws.get("tabs", []):
                    tab["agents"] = [
                        a for a in tab.get("agents", []) if a.get("pane_id") != "w1:p1"
                    ]
            cambio.clear()
            hub._publicar(board_sin_pane)
            await asyncio.wait_for(cambio.wait(), 1)
            assert p.estado == "terminal"

            await hub.refresh()
            c2 = FakeConexion()
            p2 = await permisos.atender(pr(tool_use_id="t_obs2"), "w1:p1", c2)
            assert p2.estado == "abierto"
            board_off = copy.deepcopy(hub.board)
            board_off["terminales"] = "sin_conexion"
            hub._publicar(board_off)
            assert p2.estado == "abierto"
        finally:
            restaurar()

    cliente.portal.call(esc)


def _clasificado(hora, categoria="auto", **extra):
    base = {
        "tipo": "clasificado",
        "hora": hora,
        "quien": "politica",
        "session_id": SID,
        "tool_use_id": "t",
        "herramienta": "Bash",
        "entrada": {"command": "ls"},
        "categoria": categoria,
        "regla_politica": "regla",
        "motivo_politica": "motivo",
        "resultado": "usuario",
        "pane_id": "w1:p1",
    }
    base.update(extra)
    return base


def _permisos_jsonl(app):
    return app.state.permisos.auditoria.path


def test_registro_archivo_inexistente(cliente, app):
    cliente.get("/api/board")
    assert cliente.get("/api/permisos/registro").json() == {"items": []}


def test_registro_filtra_y_ordena(cliente, app):
    cliente.get("/api/board")
    path = _permisos_jsonl(app)
    lineas = [
        {"tipo": "pedido", "hora": "2026-01-01T00:00:00+00:00"},
        {"tipo": "permitido", "hora": "2026-01-01T00:00:01+00:00"},
        _clasificado("2026-01-01T00:00:02+00:00", categoria="auto"),
        _clasificado("2026-01-01T00:00:03+00:00", categoria="gris"),
        _clasificado("2026-01-01T00:00:04+00:00", categoria="usuario", secreto="no"),
        "basura\n",
        _clasificado("2026-01-01T00:00:05+00:00", categoria="rara"),
    ]
    with path.open("w", encoding="utf-8") as f:
        for item in lineas:
            if isinstance(item, str):
                f.write(item)
            else:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    r = cliente.get("/api/permisos/registro")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["hora"] for i in items] == [
        "2026-01-01T00:00:04+00:00",
        "2026-01-01T00:00:03+00:00",
        "2026-01-01T00:00:02+00:00",
    ]
    permitidas = {
        "hora",
        "categoria",
        "regla_politica",
        "motivo_politica",
        "herramienta",
        "entrada",
        "pane_id",
        "session_id",
        "tool_use_id",
        "sesion",
        "quien",
        "motivo_centinela",
        "encargo_id",
        "objecion",
        "subido",
        "decision",
    }
    for item in items:
        assert set(item.keys()) <= permitidas
        assert "secreto" not in item
    assert items[0]["sesion"] == "1 · Uno"


def test_registro_incluye_decisiones_del_usuario(pedido, cliente, app):
    p, _ = pedido()
    r = cliente.post(f"/api/permisos/{p.id}/decidir", json={"accion": "rechazar"})
    assert r.status_code == 200
    items = cliente.get("/api/permisos/registro").json()["items"]
    assert items[0]["decision"] == "rechazar" and items[0]["quien"] == "usuario"
    assert items[0]["herramienta"] == p.herramienta


def test_registro_decision_no_duplica_fila_clasificada(cliente, app):
    cliente.get("/api/board")
    filas = [
        _clasificado("2026-11-01T10:00:00", "gris", tool_use_id="g1"),
        {
            "tipo": "app-allow",
            "hora": "2026-11-01T10:00:05",
            "quien": "app",
            "session_id": SID,
            "tool_use_id": "g1",
            "herramienta": "Bash",
        },
        {
            "tipo": "app-siempre",
            "hora": "2026-11-01T11:00:00",
            "quien": "app",
            "session_id": SID,
            "tool_use_id": "s1",
            "herramienta": "Edit",
            "entrada": {"file_path": "/x"},
        },
    ]
    _permisos_jsonl(app).write_text("\n".join(json.dumps(f) for f in filas) + "\n")
    items = cliente.get("/api/permisos/registro").json()["items"]
    assert [(i["tool_use_id"], i["decision"]) for i in items] == [("s1", "siempre"), ("g1", "permitir")]


def test_registro_decision_recorta_y_descarta_no_str(cliente, app):
    cliente.get("/api/board")
    filas = [
        {
            "tipo": "app-allow",
            "hora": 123,
            "quien": "app",
            "session_id": SID,
            "tool_use_id": "t1",
            "herramienta": "B" * 500,
            "pane_id": ["x"],
        },
    ]
    _permisos_jsonl(app).write_text("\n".join(json.dumps(f) for f in filas) + "\n")
    (item,) = cliente.get("/api/permisos/registro").json()["items"]
    assert len(item["herramienta"]) == 200
    assert "hora" not in item
    assert "pane_id" not in item


def test_registro_decision_repetida_misma_clave_no_duplica(cliente, app):
    cliente.get("/api/board")
    base = {"quien": "app", "session_id": SID, "tool_use_id": "r1", "herramienta": "Bash"}
    filas = [
        {**base, "tipo": "app-allow", "hora": "2026-11-01T10:00:00"},
        {**base, "tipo": "app-deny", "hora": "2026-11-01T10:00:05"},
    ]
    _permisos_jsonl(app).write_text("\n".join(json.dumps(f) for f in filas) + "\n")
    items = cliente.get("/api/permisos/registro").json()["items"]
    assert [(i["tool_use_id"], i["decision"]) for i in items] == [("r1", "rechazar")]


def test_registro_lee_filas_viejas(cliente, app):
    cliente.get("/api/board")
    filas = [
        _clasificado("2026-11-01T10:00:00", "gris", tool_use_id="g1"),
        {
            "tipo": "centinela-allow",
            "hora": "2026-11-01T10:00:05",
            "quien": "centinela",
            "session_id": SID,
            "tool_use_id": "g1",
        },
        _clasificado("2026-11-01T11:00:00", "gris", tool_use_id="g2"),
        {
            "tipo": "gris-subido",
            "hora": "2026-11-01T11:00:05",
            "quien": "centinela",
            "session_id": SID,
            "tool_use_id": "g2",
        },
        _clasificado("2026-11-01T12:00:00", "auto", tool_use_id="a1"),
        {
            "tipo": "politica-allow",
            "hora": "2026-11-01T12:00:01",
            "quien": "politica",
            "session_id": SID,
            "tool_use_id": "a1",
        },
        {"tipo": "interruptor", "hora": "2026-11-01T12:30:00", "activo": True},
        {
            "tipo": "objecion",
            "hora": "2026-11-01T13:00:00",
            "session_id": SID,
            "tool_use_id": "a1",
            "motivo": "no",
        },
    ]
    _permisos_jsonl(app).write_text("\n".join(json.dumps(f) for f in filas) + "\n")
    items = cliente.get("/api/permisos/registro").json()["items"]
    por_id = {i["tool_use_id"]: i for i in items}
    assert por_id["g1"]["quien"] == "centinela"
    assert por_id["g2"]["quien"] == "usuario" and por_id["g2"].get("subido") is True
    assert por_id["a1"]["quien"] == "politica"
    assert por_id["a1"]["objecion"]["nota"] == "no"


def test_registro_limite_200(cliente, app):
    cliente.get("/api/board")
    path = _permisos_jsonl(app)
    with path.open("w", encoding="utf-8") as f:
        for i in range(205):
            f.write(
                json.dumps(
                    _clasificado(f"2026-01-01T00:{i:02d}:00+00:00", categoria="auto"),
                    ensure_ascii=False,
                )
                + "\n"
            )
    items = cliente.get("/api/permisos/registro").json()["items"]
    assert len(items) == 200
    assert items[0]["hora"] == "2026-01-01T00:204:00+00:00"


def test_leer_clasificados_cola_descarta_parcial(tmp_path):
    aud = AuditoriaPermisos(tmp_path / "permisos.jsonl")
    line1 = json.dumps(_clasificado("2026-01-01T00:00:00+00:00"), ensure_ascii=False) + "\n"
    valid = _clasificado("2026-01-02T12:00:00+00:00")
    line2 = json.dumps(valid, ensure_ascii=False) + "\n"
    aud.path.write_text(line1 + line2, encoding="utf-8")
    items = aud.leer_clasificados(limite=10, max_bytes=len(line2) + 15)
    assert len(items) == 1
    assert items[0]["hora"] == valid["hora"]


def test_pedido_nuevo_queda_abierto_sin_clasificar(pedido, app):
    p, c = pedido()
    assert p.estado == "abierto" and c.respuestas == []
    tipos = [
        json.loads(linea)["tipo"]
        for linea in _permisos_jsonl(app).read_text().splitlines()
    ]
    assert tipos == ["pedido"]
    assert not hasattr(app.state, "interruptor_centinela")


@pytest.mark.parametrize(
    "metodo,ruta",
    [
        ("GET", "/api/permisos/interruptor"),
        ("POST", "/api/permisos/interruptor"),
        ("GET", "/api/permisos/observacion"),
        ("POST", "/api/permisos/objecion"),
    ],
)
def test_rutas_de_centinela_en_permisos_404(cliente, metodo, ruta):
    assert cliente.request(metodo, ruta, json={}).status_code == 404


@pytest.mark.parametrize("ruta", ["/api/permisos", "/api/permisos/registro"])
def test_rutas_que_quedan_siguen_pidiendo_sesion(cliente_sin_login, ruta):
    assert cliente_sin_login.get(ruta).status_code == 401


def test_catch_all_deja_la_ruta_viva_y_absorbe_metodo_no_soportado(cliente):
    assert cliente.get("/api/permisos").status_code == 200
    r = cliente.delete("/api/permisos")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}


def test_decidir_inexistente_da_el_error_propio_y_no_el_del_catch_all(cliente):
    r = cliente.post("/api/permisos/no-existe/decidir", json={"accion": "permitir"})
    assert r.status_code in (404, 409)
    assert r.json() != {"detail": "Not Found"}
    assert cliente.post("/api/permisos/interruptor", json={}).json() == {"detail": "Not Found"}
