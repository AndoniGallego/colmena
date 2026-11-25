import asyncio
import json
import sys
from datetime import datetime, timezone

import pytest

from biblioteca_support import Env
from orquestador import cli
from orquestador.telemetria import Telemetria
from orquestador.telemetria_resumen import PropuestasStore, ResumenSemanal, generar_resumen, metrica_de

AHORA = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def lunes(a, m, d, h, mi):
    return datetime(a, m, d, h, mi).astimezone()


def lineas(d):
    return [json.loads(l) for f in sorted(d.glob("*.jsonl")) for l in f.read_text().splitlines()]


async def fut():
    return None


class Reloj:
    def __init__(self, ahora=None):
        self.ahora = ahora

    def __call__(self):
        return self.ahora


def semanal(tmp_path, reloj, corridas, dias=(0,), hora="09:00"):
    def ejecutar(semana):
        corridas.append(semana)
        return fut()
    return ResumenSemanal(tmp_path, lambda: hora, lambda: list(dias), ejecutar, now=reloj)


def test_tick_corre_una_vez_por_semana(tmp_path):
    corridas, reloj = [], Reloj(lunes(2026, 11, 30, 9, 1))
    r = semanal(tmp_path, reloj, corridas)
    assert asyncio.run(r.tick()) is True and corridas == ["2026-W48"]
    assert asyncio.run(r.tick()) is False and corridas == ["2026-W48"]
    assert json.loads((tmp_path / "resumen-semanal.json").read_text()) == {"ultima_semana": "2026-W48"}


def test_no_corre_antes_de_la_hora(tmp_path):
    corridas = []
    assert asyncio.run(semanal(tmp_path, Reloj(lunes(2026, 11, 30, 8, 59)), corridas).tick()) is False
    assert corridas == []


def test_se_pone_al_dia_tras_lunes_apagado(tmp_path):
    corridas, reloj = [], Reloj(lunes(2026, 12, 2, 10, 0))
    r = semanal(tmp_path, reloj, corridas)
    assert asyncio.run(r.tick()) is True and corridas == ["2026-W48"]
    reloj.ahora = lunes(2026, 12, 3, 10, 0)
    assert asyncio.run(r.tick()) is False


def test_semana_nueva_vuelve_a_correr(tmp_path):
    corridas, reloj = [], Reloj(lunes(2026, 11, 30, 9, 1))
    r = semanal(tmp_path, reloj, corridas)
    asyncio.run(r.tick())
    reloj.ahora = lunes(2026, 12, 7, 9, 1)
    assert asyncio.run(r.tick()) is True and corridas == ["2026-W48", "2026-W49"]


class FakeBiblioteca:
    def __init__(self):
        self.agregados, self.quitados = [], []

    def agregar_resumen(self, datos):
        self.agregados.append(datos)
        return "abc123"

    def quitar_resumenes_viejos(self, ahora=None, dias=90):
        self.quitados.append(ahora)
        return 0


class FakePush:
    def __init__(self):
        self.llamadas = []

    async def dispatch_simple(self, kind, message, pref, endpoint=None, **registro):
        self.llamadas.append((kind, message, pref))
        return 0


class FakeHandler:
    flushed = False

    def flush(self):
        self.flushed = True


def error_back(n):
    return {"v": 1, "ts": "2026-11-18T10:00:00+00:00", "ev": "error_back", "fuente": "back", "nivel": "ERROR",
            "logger": "orquestador.x", "plantilla": "fallo raro", "tipo_exc": "ValueError", "n": n,
            "primera": "2026-11-18T10:00:00+00:00", "ultima": "2026-11-18T11:00:00+00:00"}


def montar(tmp_path, con_errores=False):
    tel = Telemetria(tmp_path / "tel")
    if con_errores:
        tel.directorio.mkdir(parents=True)
        (tel.directorio / "2026-11.jsonl").write_text(json.dumps(error_back(30)) + "\n")
    store = PropuestasStore(tmp_path / "propuestas.json", wall=lambda: AHORA)
    return tel, store, FakeBiblioteca(), FakePush(), FakeHandler()


def generar(tmp_path, tel, store, bib, push, handler, **kw):
    return asyncio.run(generar_resumen(directorio=tel.directorio, semana="2026-W47", propuestas=store,
                                       biblioteca=bib, push=push, handler=handler, telemetria=tel,
                                       ahora=AHORA, **kw))


def test_generar_resumen_guarda_avisa_y_anota(tmp_path):
    tel, store, bib, push, handler = montar(tmp_path, con_errores=True)
    d = generar(tmp_path, tel, store, bib, push, handler)
    datos = bib.agregados[0]
    assert datos["semana"] == "2026-W47" and (datos["desde"], datos["hasta"]) == ("2026-11-16", "2026-11-22")
    assert datos["resumen"] == d["resumen"] and datos["propuestas"] == d["propuestas"]
    assert datos["generado"] == AHORA.timestamp()
    kind, mensaje, pref = push.llamadas[0]
    assert (kind, pref) == ("resumen", "resumen")
    assert mensaje["url"] == "/?biblioteca=abc123" and mensaje["kind"] == "resumen" and mensaje["session_id"] == ""
    assert mensaje["body"] == "1 propuesta · 30 errores"
    assert handler.flushed and bib.quitados == [AHORA]
    assert [l["propuestas"] for l in lineas(tel.directorio) if l["ev"] == "resumen"] == [1]


def test_generar_registra_las_propuestas_en_el_store(tmp_path):
    tel, store, bib, push, handler = montar(tmp_path, con_errores=True)
    d = generar(tmp_path, tel, store, bib, push, handler)
    pid = d["propuestas"]["nuevas"][0]["id"]
    e = store.cargar()[pid]
    assert (e["estado"], e["seguimiento"], e["regla"]) == ("propuesta", [], "error_repetido")
    assert e["metrica"] == {"nombre": "veces_por_semana"} and e["actualizada"] == AHORA.isoformat()


def test_registrar_no_toca_las_que_ya_estan(tmp_path):
    store = PropuestasStore(tmp_path / "p.json", wall=lambda: AHORA)
    cand = {"id": "a" * 12, "regla": "r", "clave": "c", "metrica": {"nombre": "n", "valor": 1}}
    store.decidir("a" * 12, "hacer", "2026-W47", 3.0, cand)
    antes = store.cargar()
    store.registrar([cand, {**cand, "id": "b" * 12}])
    despues = store.cargar()
    assert despues["a" * 12] == antes["a" * 12] and despues["b" * 12]["estado"] == "propuesta"


def test_generar_sin_aviso_no_guarda_ni_avisa(tmp_path):
    tel, store, bib, push, handler = montar(tmp_path)
    generar(tmp_path, tel, store, bib, push, handler, avisar=False, guardar=False)
    assert bib.agregados == [] and push.llamadas == []
    assert not [l for l in lineas(tel.directorio) if l["ev"] == "resumen"]


def test_biblioteca_real_guarda_el_resumen_que_lee_metrica_de(tmp_path):
    env = Env(tmp_path)
    tel, store, _, push, handler = montar(tmp_path, con_errores=True)
    d = generar(tmp_path, tel, store, env.lib, push, handler)
    with env.lib._lock:
        item = next(i for i in env.lib.items.values() if i["kind"] == "resumen")
    assert json.loads(item["resumen_raw"])["resumen"] == d["resumen"]
    pid = d["propuestas"]["nuevas"][0]["id"]
    e = store.cargar()[pid]
    assert metrica_de(json.loads(item["resumen_raw"])["resumen"], e["regla"], e["clave"]) == 30


def test_cli_semana_vieja_no_marca(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ORQ_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["orquestador", "telemetria", "resumen", "--semana", "2026-W40",
                                      "--json", "--sin-aviso"])
    with pytest.raises(SystemExit) as salida:
        cli.main()
    assert salida.value.code == 0
    assert "resumen" in json.loads(capsys.readouterr().out)
    assert not (tmp_path / "resumen-semanal.json").exists()


def test_cli_sin_semana_marca_la_anterior(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ORQ_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["orquestador", "telemetria", "resumen"])
    with pytest.raises(SystemExit) as salida:
        cli.main()
    assert salida.value.code == 0
    assert "semana" in capsys.readouterr().out.lower()
    assert "ultima_semana" in json.loads((tmp_path / "resumen-semanal.json").read_text())


def test_cli_sin_aviso_no_marca_aunque_sea_la_anterior(tmp_path, monkeypatch):
    monkeypatch.setenv("ORQ_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["orquestador", "telemetria", "resumen", "--sin-aviso"])
    with pytest.raises(SystemExit):
        cli.main()
    assert not (tmp_path / "resumen-semanal.json").exists()


def test_endpoint_de_marcas_usa_la_semana_local(tmp_path, monkeypatch):
    import time
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from orquestador.telemetria_api import build_router
    monkeypatch.setenv("TZ", "America/Argentina/Buenos_Aires")
    time.tzset()
    try:
        domingo_local = datetime(2026, 11, 23, 2, 30, tzinfo=timezone.utc)  # domingo 22, 23:30 en Buenos Aires
        store = PropuestasStore(tmp_path / "p.json", wall=lambda: domingo_local)
        store.path.write_text(json.dumps({"0123456789ab": {"regla": "r", "clave": "c", "metrica": {"nombre": "n"},
                                                           "seguimiento": []}}))
        app = FastAPI()
        app.include_router(build_router(Telemetria(tmp_path / "t"), propuestas=store), prefix="/api")
        r = TestClient(app).post("/api/telemetria/propuestas/0123456789ab", json={"decision": "hacer"})
        assert r.status_code == 200
        assert store.cargar()["0123456789ab"]["metrica"]["semana_base"] == "2026-W47"
    finally:
        monkeypatch.undo()
        time.tzset()


def test_app_atrapa_el_fallo_del_resumen_y_el_loop_sigue(app, monkeypatch):
    from orquestador import telemetria_resumen

    async def falla(**kw):
        raise TypeError("datos raros")

    monkeypatch.setattr(telemetria_resumen, "generar_resumen", falla)
    r = app.state.resumen_semanal
    assert asyncio.run(r.ejecutar("2026-W47")) is None


def test_app_lee_hora_y_dias_de_las_perillas_de_telemetria(app, cfg):
    cfg.telemetria_resumen_hora, cfg.telemetria_resumen_dias = "07:15", [2]
    r = app.state.resumen_semanal
    assert (r.hora(), r.dias()) == ("07:15", [2])
    assert not hasattr(cfg, "resumen_hora")


def test_run_con_despertar_temprano_no_pierde_la_semana(tmp_path):
    corridas = []
    reloj = Reloj(lunes(2026, 11, 30, 8, 0))
    esperas = []

    class Corte(Exception):
        pass

    async def dormir(s):
        esperas.append(s)
        if len(esperas) == 1:
            reloj.ahora = lunes(2026, 11, 30, 8, 59) + (lunes(2026, 11, 30, 9, 0) - lunes(2026, 11, 30, 8, 59)) * 0.999
        elif len(esperas) == 2:
            reloj.ahora = lunes(2026, 11, 30, 9, 0, )
        else:
            raise Corte

    def ejecutar(semana):
        corridas.append(semana)
        return fut()

    r = ResumenSemanal(tmp_path, lambda: "09:00", lambda: [0], ejecutar, now=reloj, sleep=dormir)
    with pytest.raises(Corte):
        asyncio.run(r.run())
    assert corridas == ["2026-W48"] and esperas[1] < 5
