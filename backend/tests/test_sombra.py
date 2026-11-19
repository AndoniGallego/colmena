import json
from datetime import datetime, timezone

from orquestador.estado_sesiones import EstadoSesiones
from orquestador.ganchos.mensaje import Ids, MensajeGancho
from orquestador.sombra import Sombra


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def board(status):
    return {
        "workspaces": [
            {"tabs": [{"agents": [{"pane_id": "w1:p1", "session_id": "s1", "status": status}]}]}
        ]
    }


def preparar(tmp_path):
    r = Reloj()
    e = EstadoSesiones(clock=r)
    s = Sombra(tmp_path, clock=r, wall=lambda: datetime(2026, 11, 3, tzinfo=timezone.utc))
    return r, e, s


def evento(e, nombre, **datos):
    e.recibir(
        MensajeGancho(nombre, "global", Ids(None, "w1:p1", None, None, "s1"), datos),
        "w1:p1",
    )


def lineas(tmp_path):
    p = tmp_path / "ganchos-sombra.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.is_file() else []


def test_umbral_2s(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "PermissionRequest", tool_use_id="t1", tool_name="Bash", tool_input={"command": "cat SECRETO"})
    s.observar(board("working"), e)
    r.t = 1.9
    s.observar(board("blocked"), e)
    assert lineas(tmp_path) == []
    s.observar(board("working"), e)
    r.t = 4.5
    s.observar(board("blocked"), e)
    (l,) = lineas(tmp_path)
    assert l["herdr"] == "working" and l["ganchos"] == "blocked" and l["solo_done_idle"] is False
    assert l["duracion"] == 2.6


def test_sin_contenido(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "UserPromptSubmit", prompt="PROMPT_SECRETO")
    evento(e, "PreToolUse", tool_use_id="t1", tool_name="Bash", tool_input={"command": "TOOL_SECRETO"})
    s.observar(board("idle"), e)
    r.t = 5
    s.cerrar()
    texto = (tmp_path / "ganchos-sombra.jsonl").read_text()
    assert "SECRETO" not in texto and "command" not in texto


def test_done_idle_aparte_y_resumen(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "Stop")
    s.observar(board("idle"), e)
    r.t = 12
    s.observar(board("done"), e)
    assert lineas(tmp_path)[0]["solo_done_idle"] is True
    assert s.resumen(7) == [
        {"dia": "2026-11-03", "discrepancias": 1, "mayores_10s": 1, "solo_done_idle": 1}
    ]


def test_idle_prompt_ignorado(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "Notification", notification_type="idle_prompt")
    s.observar(board("idle"), e)
    assert any(l.get("evento") == "idle_prompt" and l["ignorado"] for l in lineas(tmp_path))
    assert list(e.ignorados) == []


def test_archivo_no_escribible_no_rompe(tmp_path):
    r, e, s = preparar(tmp_path)
    bloqueado = tmp_path / "ganchos-sombra.jsonl"
    bloqueado.mkdir()
    evento(e, "Stop")
    s.observar(board("working"), e)
    r.t = 5
    s.observar(board("done"), e)
    s.cerrar()
    assert bloqueado.is_dir()
    assert not any(bloqueado.iterdir())
    assert s.resumen(7) == []


def test_observar_idempotente(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "PermissionRequest", tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"})
    s.observar(board("working"), e)
    r.t = 3.0
    s.observar(board("working"), e)
    r.t = 5.0
    s.observar(board("blocked"), e)
    assert len(lineas(tmp_path)) == 1
    assert lineas(tmp_path)[0]["duracion"] == 5.0


def test_observar_estados_none(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "Notification", notification_type="idle_prompt")
    s.observar(board("idle"), None)
    assert lineas(tmp_path) == []
    assert list(e.ignorados) == ["idle_prompt"]


def test_resumen_salta_corrupta(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "Stop")
    s.observar(board("idle"), e)
    r.t = 12
    s.observar(board("done"), e)
    p = tmp_path / "ganchos-sombra.jsonl"
    with p.open("a") as f:
        f.write("}{ corrupto\n")
        f.write('{"evento": "idle_prompt", "ignorado": true, "hora": "2026-11-03T00:00:00+00:00"}\n')
    assert s.resumen(7) == [
        {"dia": "2026-11-03", "discrepancias": 1, "mayores_10s": 1, "solo_done_idle": 1}
    ]


def test_endpoint_resumen(authed):
    r = authed.get("/api/ganchos/sombra?dias=7")
    assert r.status_code == 200 and r.json() == {"dias": []}
    assert authed.get("/api/ganchos/sombra?dias=99").status_code == 422


def test_endpoint_sin_auth(client):
    assert client.get("/api/ganchos/sombra?dias=7").status_code == 401


def escribir_linea(tmp_path, obj):
    p = tmp_path / "ganchos-sombra.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")


def test_resumen_salta_duracion_no_numerica(tmp_path):
    _, _, s = preparar(tmp_path)
    escribir_linea(tmp_path, {"duracion": "x", "hora": "2026-11-03T00:00:00+00:00"})
    assert s.resumen(7) == []


def test_resumen_salta_hora_invalida(tmp_path):
    _, _, s = preparar(tmp_path)
    escribir_linea(tmp_path, {"duracion": 5.0, "hora": "no-es-fecha"})
    assert s.resumen(7) == []


def test_resumen_salta_fecha_futura(tmp_path):
    _, _, s = preparar(tmp_path)
    escribir_linea(tmp_path, {"duracion": 5.0, "hora": "2026-11-04T00:00:00+00:00"})
    assert s.resumen(7) == []


def test_endpoint_resumen_duracion_no_numerica_no_500(authed, tmp_path):
    (tmp_path / "ganchos-sombra.jsonl").write_text(
        '{"duracion":"x","hora":"2026-11-03T00:00:00+00:00"}\n',
        encoding="utf-8",
    )
    r = authed.get("/api/ganchos/sombra?dias=7")
    assert r.status_code == 200
    assert r.json() == {"dias": []}


def test_cierre_estados_coinciden(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "PermissionRequest", tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"})
    s.observar(board("working"), e)
    r.t = 5.0
    s.observar(board("blocked"), e)
    assert len(lineas(tmp_path)) == 1
    s.observar(board("blocked"), e)
    assert len(lineas(tmp_path)) == 1
    r.t = 8.0
    s.observar(board("blocked"), e)
    assert len(lineas(tmp_path)) == 1


def test_cierre_pane_desaparece(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "PermissionRequest", tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"})
    s.observar(board("working"), e)
    r.t = 5.0
    s.observar({"workspaces": [{"tabs": [{"agents": []}]}]}, e)
    assert len(lineas(tmp_path)) == 1
    assert lineas(tmp_path)[0]["duracion"] == 5.0


def test_cambio_par_discrepancia_cierra_y_abre(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "PermissionRequest", tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"})
    s.observar(board("working"), e)
    r.t = 3.0
    s.observar(board("idle"), e)
    ls = lineas(tmp_path)
    assert len(ls) == 1
    assert ls[0]["herdr"] == "working" and ls[0]["ganchos"] == "blocked"
    assert ls[0]["duracion"] == 3.0
    assert s._abiertas["w1:p1"]["herdr"] == "idle" and s._abiertas["w1:p1"]["ganchos"] == "blocked"


def test_estado_none_cierra_discrepancia_abierta(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "PermissionRequest", tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"})
    s.observar(board("working"), e)
    r.t = 5.0
    del e._registros["w1:p1"]
    s.observar(board("working"), e)
    assert len(lineas(tmp_path)) == 1
    assert lineas(tmp_path)[0]["duracion"] == 5.0
    assert "w1:p1" not in s._abiertas


def test_resumen_filtro_dias(tmp_path):
    _, _, s = preparar(tmp_path)
    escribir_linea(tmp_path, {"duracion": 12.0, "hora": "2026-10-27T12:00:00+00:00", "solo_done_idle": False})
    escribir_linea(tmp_path, {"duracion": 12.0, "hora": "2026-11-01T12:00:00+00:00", "solo_done_idle": False})
    assert s.resumen(7) == [
        {"dia": "2026-11-01", "discrepancias": 1, "mayores_10s": 1, "solo_done_idle": 0}
    ]


def test_cerrar_escribe_mayor_umbral(tmp_path):
    r, e, s = preparar(tmp_path)
    evento(e, "PermissionRequest", tool_use_id="t1", tool_name="Bash", tool_input={"command": "ls"})
    s.observar(board("working"), e)
    r.t = 5.0
    s.cerrar()
    assert len(lineas(tmp_path)) == 1
    assert lineas(tmp_path)[0]["duracion"] == 5.0
    assert "w1:p1" not in s._abiertas
