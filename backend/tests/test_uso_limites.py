import builtins
import json
import os
import time
from datetime import datetime
from pathlib import Path

from orquestador.uso_claude import read_limits

NOW = 1_900_000_000.0


def _rl(five=23.5, seven=41):
    return {"five_hour": {"used_percentage": five, "resets_at": NOW + 3600},
            "seven_day": {"used_percentage": seven, "resets_at": NOW - 10}}


def _plan(state, rl, ts=NOW - 90, sid="p"):
    state.mkdir(parents=True, exist_ok=True)
    (state / "plan-limites.json").write_text(json.dumps({"rate_limits": rl, "ts": ts, "session_id": sid}), encoding="utf-8")


def test_read_limits_prefiere_plan_limites_json(tmp_path):
    ctx = tmp_path / "state" / "ctx"
    ctx.mkdir(parents=True)
    (ctx / "a.json").write_text(json.dumps({"session_id": "a", "ts": NOW - 5, "rate_limits": _rl(five=99, seven=99)}), encoding="utf-8")
    _plan(tmp_path / "state", _rl())
    lim = read_limits(ctx, NOW)
    assert lim["five_hour"]["pct"] == 23.5 and lim["seven_day"]["pct"] == 41
    assert lim["five_hour"]["vencido"] is False and lim["seven_day"]["vencido"] is True
    assert lim["edad_s"] == 90
    assert datetime.fromisoformat(lim["actualizado"]).timestamp() == NOW - 90


def test_read_limits_cae_a_snapshots(tmp_path):
    ctx = tmp_path / "state" / "ctx"
    ctx.mkdir(parents=True)
    (ctx / "a.json").write_text(json.dumps({"session_id": "a", "ts": NOW - 30, "rate_limits": _rl(five=10, seven=20)}), encoding="utf-8")
    (tmp_path / "state" / "plan-limites.json").write_text("{no es json", encoding="utf-8")
    lim = read_limits(ctx, NOW)
    assert lim["five_hour"]["pct"] == 10 and lim["edad_s"] == 30
    _plan(tmp_path / "state", {"five_hour": {"used_percentage": "x"}})
    assert read_limits(ctx, NOW)["five_hour"]["pct"] == 10


def test_read_limits_solo_plan_limites_sin_ctx(tmp_path):
    _plan(tmp_path / "state", _rl())
    assert read_limits(tmp_path / "state" / "ctx", NOW)["five_hour"]["pct"] == 23.5


def test_endpoint_uso_limites_formato_y_no_store(authed, tmp_path, monkeypatch):
    state = tmp_path / "estado"
    monkeypatch.setenv("ORQ_CTX_DIR", str(state / "ctx"))
    _plan(state, _rl(), ts=time.time() - 60)
    r = authed.get("/api/uso/limites")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert set(body) == {"five_hour", "seven_day", "actualizado", "edad_s"}
    assert set(body["five_hour"]) == {"pct", "resets_at", "vencido"}
    assert body["five_hour"]["pct"] == 23.5 and 55 <= body["edad_s"] <= 70


def test_endpoint_sin_datos(authed, tmp_path, monkeypatch):
    monkeypatch.setenv("ORQ_CTX_DIR", str(tmp_path / "vacio" / "ctx"))
    assert authed.get("/api/uso/limites").json() == {"sin_datos": True}


def test_endpoint_sin_sesion(client):
    assert client.get("/api/uso/limites").status_code == 401


def test_no_lee_credentials(authed, tmp_path, monkeypatch):
    home = Path(tmp_path / "hogar")
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ORQ_CTX_DIR", raising=False)
    _plan(home / ".local" / "state" / "andokit", _rl(), ts=time.time())
    abiertos = []
    real_open = builtins.open

    def espia(file, *a, **k):
        abiertos.append(str(file))
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", espia)
    for nombre in ("read_text", "read_bytes", "open"):
        monkeypatch.setattr(Path, nombre, _espia_path(abiertos, nombre))
    real_os_open = os.open

    def espia_os(path, *a, **k):
        abiertos.append(os.fsdecode(path))
        return real_os_open(path, *a, **k)

    monkeypatch.setattr(os, "open", espia_os)
    assert authed.get("/api/uso/limites").status_code == 200
    assert not [p for p in abiertos if ".credentials" in p]
    assert any("plan-limites.json" in p for p in abiertos)


def _espia_path(abiertos, nombre):
    real = getattr(Path, nombre)

    def metodo(self, *a, **k):
        abiertos.append(str(self))
        return real(self, *a, **k)
    return metodo
