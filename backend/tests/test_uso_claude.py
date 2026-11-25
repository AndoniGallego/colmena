import json
import os

import pytest
from datetime import datetime, timedelta, timezone

from orquestador.uso import UsoStore
from orquestador.uso_claude import ClaudeUso, nombres_herdr, project_key, read_limits

NOW = datetime(2026, 5, 10, 15, 0, tzinfo=timezone.utc)
S1 = "aaaaaaaa-0000-0000-0000-000000000001"
S2 = "bbbbbbbb-0000-0000-0000-000000000002"


def ts(days_back=0, hour=12):
    return (NOW - timedelta(days=days_back)).replace(hour=hour).isoformat().replace("+00:00", "Z")


def asst(mid, inp=0, out=0, cw=0, cr=0, model="claude-opus-5-5", when=None, sid=S1, cwd="/home/x/proyA", side=False, cw1h=None):
    entry = {"type": "assistant", "isSidechain": side, "sessionId": sid, "cwd": cwd, "timestamp": when or ts(),
            "requestId": "req-" + mid,
            "message": {"id": mid, "model": model, "usage": {"input_tokens": inp, "output_tokens": out,
                                                             "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}}}
    if cw1h is not None:
        entry["message"]["usage"]["cache_creation"] = {"ephemeral_1h_input_tokens": cw1h, "ephemeral_5m_input_tokens": cw - cw1h}
    return entry


def write(path, entries, extra=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries) + extra, encoding="utf-8")


def svc(tmp_path, **kw):
    return ClaudeUso(tmp_path / "projects", tmp_path / "data", now=lambda: NOW, clock=lambda: 0.0, **kw)


def main_file(tmp_path, sid=S1, proj="-home-x-proyA"):
    return tmp_path / "projects" / proj / f"{sid}.jsonl"


def test_dedupe_mismo_mensaje_en_varias_entradas(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [
        asst("m1", inp=10, out=1, cr=100),
        asst("m1", inp=10, out=5, cr=100),
        asst("m1", inp=10, out=5, cr=100),
        asst("m2", inp=3, out=2),
    ])
    s = svc(tmp_path).summary()
    hoy = s["totales"]["hoy"]
    assert hoy["input"] == 13 and hoy["output"] == 7 and hoy["cache_read"] == 100 and hoy["mensajes"] == 2
    assert hoy["total"] == 120


def test_subagentes_cuentan_en_la_sesion_padre(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [{"type": "ai-title", "aiTitle": "Arreglar login"}, asst("m1", inp=10)])
    write(tmp_path / "projects" / "-home-x-proyA" / S1 / "subagents" / "agent-a1.jsonl",
          [asst("s1", inp=5, side=True, model="claude-haiku-5-5")])
    write(tmp_path / "projects" / "-home-x-proyA" / "agent-legacy.jsonl", [asst("s2", inp=7, side=True)])
    s = svc(tmp_path).summary()
    ses = s["desglose"]["hoy"]["sesiones"]
    assert len(ses) == 1 and ses[0]["id"] == S1 and ses[0]["total"] == 22 and ses[0]["nombre"] == "Arreglar login"
    assert ses[0]["detalle"] == "proyA"
    modelos = {m["nombre"]: m["total"] for m in s["desglose"]["hoy"]["modelos"]}
    assert modelos == {"Opus 5.5": 17, "Haiku 5.5": 5}


def test_dias_rangos_y_retencion(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [
        asst("a", inp=1, when=ts(0)),
        asst("b", inp=10, when=ts(3)),
        asst("c", inp=100, when=ts(20)),
        asst("d", inp=1000, when=ts(40)),
    ])
    s = svc(tmp_path).summary()
    t = s["totales"]
    assert (t["hoy"]["total"], t["7d"]["total"], t["30d"]["total"]) == (1, 11, 111)
    assert len(s["historial"]) == 30 and s["historial"][-1]["fecha"] == NOW.astimezone().date().isoformat()
    assert s["historial"][-1]["total"] == 1
    assert len(s["desglose"]["7d"]["sesiones"]) == 1 and s["desglose"]["30d"]["proyectos"][0]["total"] == 111


def test_cache_incremental_lee_solo_lo_nuevo(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    path = main_file(tmp_path)
    write(path, [asst("m1", inp=10, out=1)], extra=json.dumps(asst("m2", inp=99))[:30])
    u = svc(tmp_path)
    assert u.summary()["totales"]["hoy"]["total"] == 11
    offset = u.files[str(path)]["offset"]
    assert offset < path.stat().st_size

    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(asst("m1", inp=10, out=1)) + "\n" + json.dumps(asst("m1", inp=10, out=4)) + "\n"
                 + json.dumps(asst("m2", inp=99)) + "\n")
    assert u.scan(force=True)
    assert u.summary()["totales"]["hoy"]["total"] == 10 + 4 + 99

    reads = []
    real_open = type(path).open
    monkeypatch.setattr(type(path), "open", lambda self, *a, **k: (self.suffix == ".jsonl" and reads.append(self)) or real_open(self, *a, **k))
    assert not u.scan(force=True)
    assert reads == []

    again = svc(tmp_path)
    assert again.files and again.summary()["totales"]["hoy"]["total"] == 113
    assert reads == []


def test_archivo_corrupto_y_lineas_basura(tmp_path):
    (tmp_path / "data").mkdir()
    path = main_file(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'\xff\xfe{"type":"assistant", roto\n' + json.dumps(asst("m1", inp=5)).encode() + b"\n[1,2]\nnull\n"
                     + b'{"type":"assistant","message":{"usage":"x"}}\n'
                     + json.dumps({**asst("m3", inp=4), "timestamp": "mal"}).encode() + b"\n")
    (tmp_path / "data" / "uso-claude.json").write_text("{no es json", encoding="utf-8")
    assert svc(tmp_path).summary()["totales"]["hoy"]["total"] == 5


def test_uso_claude_sin_fila_centinela(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [asst("m1", inp=1000)])
    s = svc(tmp_path).summary()
    assert s["totales"]["hoy"]["total"] == 1000
    for grupo in s["desglose"]["hoy"].values():
        assert all(f["nombre"] != "CENTINELA" and f["tipo"] != "centinela" for f in grupo)
        assert all(f["nombre"].lower() != "centinela" for f in grupo)


def test_uso_json_con_dios_carga_sin_error_y_no_lo_muestra(tmp_path):
    hoy = NOW.astimezone().date().isoformat()
    (tmp_path / "uso.json").write_text(json.dumps({"days": {hoy: {"dios": {"input": 5, "mensajes": 1}, "mrs": {"input": 3, "mensajes": 1}}}}))
    uso = UsoStore(tmp_path, now=lambda: NOW.astimezone())
    assert "dios" not in uso.day() and uso.total_today() == 3


def test_nombre_de_herdr_y_top_con_otras(tmp_path):
    (tmp_path / "data").mkdir()
    for i in range(20):
        sid = f"cccccccc-0000-0000-0000-{i:012d}"
        write(main_file(tmp_path, sid=sid, proj=f"-p{i}"), [asst(f"m{i}", inp=100 + i, sid=sid, cwd=f"/w/p{i}")])
    board = {"workspaces": [{"label": "Acme", "tabs": [{"label": "login", "agents": [
        {"session_id": "cccccccc-0000-0000-0000-000000000019"}]}]}]}
    s = svc(tmp_path).summary(nombres_herdr(board))
    ses = s["desglose"]["hoy"]["sesiones"]
    assert ses[0]["nombre"] == "login · Acme"
    assert len(ses) == 14 and ses[-1]["tipo"] == "otras" and ses[-1]["nombre"] == "Otras 7"
    assert sum(f["total"] for f in ses) == s["totales"]["hoy"]["total"]


def test_limites_del_plan_solo_si_vienen(tmp_path):
    d = tmp_path / "ctx"
    d.mkdir()
    (d / "a.json").write_text(json.dumps({"session_id": "a", "ts": 100}), encoding="utf-8")
    assert read_limits(d, NOW.timestamp()) is None
    assert read_limits(tmp_path / "nada", NOW.timestamp()) is None
    reset = NOW.timestamp() + 3600
    (d / "b.json").write_text(json.dumps({"session_id": "b", "ts": 200, "rate_limits": {
        "five_hour": {"used_percentage": 42.25, "resets_at": reset},
        "seven_day": {"used_percentage": 12, "resets_at": NOW.timestamp() - 10}}}), encoding="utf-8")
    (d / "c.json").write_text(json.dumps({"session_id": "c", "ts": 150, "rate_limits": {
        "five_hour": {"used_percentage": 99}}}), encoding="utf-8")
    lim = read_limits(d, NOW.timestamp())
    assert lim["five_hour"]["pct"] == 42.2 or lim["five_hour"]["pct"] == 42.3
    assert lim["five_hour"]["vencido"] is False and lim["seven_day"]["vencido"] is True
    assert datetime.fromisoformat(lim["five_hour"]["resets_at"]).timestamp() == reset


def test_archivos_viejos_no_se_leen(tmp_path):
    (tmp_path / "data").mkdir()
    path = main_file(tmp_path)
    write(path, [asst("m1", inp=5, when=ts(0))])
    old = (NOW - timedelta(days=40)).timestamp()
    os.utime(path, (old, old))
    u = svc(tmp_path)
    assert u.summary()["totales"]["30d"]["total"] == 0 and not u.files


def test_endpoint_requiere_sesion_y_responde(authed, client):
    r = authed.get("/api/uso/claude")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"totales", "historial", "desglose", "limites"} and body["limites"] is None
    assert set(body["desglose"]) == {"hoy", "7d", "30d"}


def test_endpoint_sin_sesion(client):
    assert client.get("/api/uso/claude").status_code == 401


def test_tokens_de_hoy_por_sesion(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [asst("m1", inp=10, out=2, cw=1, cr=3)])
    write(tmp_path / "projects" / "-home-x-proyA" / S1 / "subagents" / "agent-a1.jsonl",
          [asst("s1", inp=5, side=True)])
    u = svc(tmp_path)
    assert u.tokens_de_hoy("") == 0
    assert u.tokens_de_hoy(S2) == 0
    assert u.tokens_de_hoy(S1) == 10 + 2 + 1 + 3 + 5


M = 1_000_000


def test_costo_usa_precio_1h_para_cache_write(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [asst("m1", inp=M, out=M, cw=2 * M, cw1h=3 * M // 2, cr=10 * M)])
    s = svc(tmp_path).summary()
    # Opus 5.5: entrada 4, escritura 5m 5, escritura 1h 8, lectura 0.20, salida 20 (USD por millón)
    assert s["totales"]["hoy"]["usd"] == pytest.approx(4 + 0.5 * 5 + 1.5 * 8 + 10 * 0.2 + 20)
    assert s["desglose"]["hoy"]["sesiones"][0]["usd"] == pytest.approx(40.5)
    assert s["desglose"]["hoy"]["modelos"][0]["usd"] == pytest.approx(40.5)
    assert s["historial"][-1]["usd"] == pytest.approx(40.5)


def test_cache_write_sin_desglose_cuenta_como_5m(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [asst("m1", cw=M)])
    assert svc(tmp_path).summary()["totales"]["hoy"]["usd"] == pytest.approx(5)


def test_modelo_desconocido_usd_none(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [asst("m1", inp=M, model="claude-nuevo-9")])
    write(main_file(tmp_path, sid=S2), [asst("m2", inp=M, sid=S2)])
    s = svc(tmp_path).summary()
    modelos = {m["id"]: m["usd"] for m in s["desglose"]["hoy"]["modelos"]}
    assert modelos == {"claude-nuevo-9": None, "claude-opus-5-5": pytest.approx(4)}
    assert s["totales"]["hoy"]["usd"] == pytest.approx(4) and s["totales"]["hoy"]["usd_parcial"] is True
    ses = {f["id"]: f["usd"] for f in s["desglose"]["hoy"]["sesiones"]}
    assert ses[S1] is None and ses[S2] == pytest.approx(4)


def test_synthetic_cuesta_cero(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [asst("m1", inp=M, model="<synthetic>")])
    s = svc(tmp_path).summary()
    assert s["totales"]["hoy"]["usd"] == 0 and s["totales"]["hoy"]["usd_parcial"] is False


def test_cache_v1_se_descarta_y_relee(tmp_path):
    (tmp_path / "data").mkdir()
    path = main_file(tmp_path)
    write(path, [asst("m1", inp=M, cw=M, cw1h=M)])
    hoy = NOW.astimezone().date().isoformat()
    st = path.stat()
    viejo = {"v": 1, "files": {str(path): {"inode": st.st_ino, "size": st.st_size, "mtime_ns": st.st_mtime_ns,
                                           "offset": st.st_size, "session": S1, "sub": False, "cwd": "/home/x/proyA", "title": "",
                                           "days": {hoy: {"claude-opus-5-5": [1, 1, 0, 0, 1]}}, "tail": {}}}}
    (tmp_path / "data" / "uso-claude.json").write_text(json.dumps(viejo), encoding="utf-8")
    u = svc(tmp_path)
    assert u.files == {}
    tot = u.summary()["totales"]["hoy"]
    assert tot["input"] == M and tot["usd"] == pytest.approx(4 + 8)
    assert json.loads((tmp_path / "data" / "uso-claude.json").read_text())["v"] == 2


def test_precio_nuevo_es_retroactivo(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [asst("m1", inp=M)])
    u = svc(tmp_path)
    assert u.summary()["totales"]["hoy"]["usd"] == pytest.approx(4)
    u.precios.modelos["claude-opus-5-5"]["input"] = 10.0
    assert u.summary()["totales"]["hoy"]["usd"] == pytest.approx(10)


def test_override_de_precio_y_alias(tmp_path):
    from orquestador.precios import Precios
    base = {"input": 1, "output": 1, "cache_write_5m": 1, "cache_write_1h": 1, "cache_read": 1}
    p = Precios(override={"claude-opus-5-5": base})
    assert p.usd("claude-opus-5-5", [M, 0, 0, 0, 1, 0]) == pytest.approx(1)
    assert Precios().usd("opus", [M, 0, 0, 0, 1, 0]) == pytest.approx(4)
    assert Precios().usd("claude-opus-5-5-20261001", [M, 0, 0, 0, 1, 0]) == pytest.approx(4)
    assert Precios().usd("otro", [M, 0, 0, 0, 1, 0]) is None


def test_por_sesion_hoy(tmp_path):
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [asst("m1", inp=M, out=1), asst("m0", inp=5, when=ts(3))])
    write(tmp_path / "projects" / "-home-x-proyA" / S1 / "subagents" / "agent-a1.jsonl",
          [asst("s1", inp=M, side=True, model="claude-sonnet-5-5")])
    write(main_file(tmp_path, sid=S2), [asst("x", inp=7, sid=S2, model="claude-nuevo-9")])
    u = svc(tmp_path)
    r = u.por_sesion_hoy()
    assert r[S1]["total"] == 2 * M + 1 and r[S1]["usd"] == pytest.approx(4 + 2 + 20 / M)
    assert r[S2] == {"total": 7, "usd": None}
    assert "otra" not in r


def test_por_sesion_hoy_sin_escanear_no_lee_ni_espera(tmp_path):
    # El tablero lo pide en cada armado: no escanea (lo hace un loop aparte) ni espera a un escaneo en curso.
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [asst("m1", inp=10)])
    u = svc(tmp_path)
    assert u.por_sesion_hoy(escanear=False) == {}
    u.scan(force=True)
    antes = u.por_sesion_hoy(escanear=False)
    assert antes[S1]["total"] == 10
    write(main_file(tmp_path, sid=S2), [asst("x", inp=7, sid=S2)])
    with u._lock:
        assert u.por_sesion_hoy(escanear=False) == antes


def test_worktree_se_agrupa_bajo_repo(tmp_path):
    repo = tmp_path / "repos" / "colmena"
    gitdir = repo / ".git" / "worktrees" / "wt1"
    gitdir.mkdir(parents=True)
    (gitdir / "commondir").write_text("../..\n")
    wt = tmp_path / "repos" / "colmena" / ".claude" / "worktrees" / "wt1"
    wt.mkdir(parents=True)
    (wt / ".git").write_text(f"gitdir: {gitdir}\n")
    otro = tmp_path / "otro" / "wt-fuera"
    otro.mkdir(parents=True)
    (otro / ".git").write_text(f"gitdir: {gitdir}\n")
    (tmp_path / "data").mkdir()
    write(main_file(tmp_path), [asst("m1", inp=10, cwd=str(repo))])
    write(main_file(tmp_path, sid=S2, proj="-wt"), [asst("m2", inp=5, sid=S2, cwd=str(wt))])
    sid3 = "cccccccc-0000-0000-0000-000000000003"
    write(main_file(tmp_path, sid=sid3, proj="-fuera"), [asst("m3", inp=2, sid=sid3, cwd=str(otro))])
    proy = {f["id"]: f["total"] for f in svc(tmp_path).summary()["desglose"]["hoy"]["proyectos"]}
    assert proy == {"colmena": 17}
