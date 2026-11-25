import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from orquestador.telemetria_resumen import (
    calcular, hace, leer_eventos, mediana, p90, rango_semana, semana_anterior, semana_iso,
)

AHORA = datetime(2026, 11, 25, 14, 0, 0, tzinfo=timezone(timedelta(hours=-3)))
FIXTURES = Path(__file__).parent / "fixtures" / "telemetria"


def _todos():
    return [json.loads(l) for f in sorted(FIXTURES.glob("*.jsonl")) for l in f.read_text().splitlines()]


def _entre(desde, hasta):
    return [e for e in _todos() if desde <= e["ts"][:10] <= hasta]


def _semanas():
    return _entre("2026-11-16", "2026-11-22"), _entre("2026-11-09", "2026-11-15"), _todos()


def ev_resp(aviso, segundos, en_app, resultado="respondio"):
    return {"v": 1, "ts": "2026-11-18T10:00:00-03:00", "ev": "respuesta", "fuente": "back", "aviso": aviso,
            "resultado": resultado, "segundos": segundos, "via": "prompt", "en_app": en_app}


def test_semana_iso_y_rango():
    assert semana_iso(date(2026, 11, 25)) == "2026-W48"
    d, h = rango_semana("2026-W47")
    assert (d.date(), h.date()) == (date(2026, 11, 16), date(2026, 11, 22))
    assert (d.hour, d.minute, h.hour, h.minute, h.second) == (0, 0, 23, 59, 59)
    assert semana_anterior(date(2026, 11, 30)) == "2026-W48"


def test_mediana_p90():
    assert mediana([]) is None and mediana([1, 3, 2]) == 2 and mediana([1, 2, 3, 4]) == 2.5
    assert p90([]) is None and p90(list(range(1, 11))) == 9


def test_hace():
    ts = "2026-11-25T13:58:00-03:00"
    assert hace(ts, AHORA) == "hace 2 min"
    assert hace("2026-11-25T12:00:00-03:00", AHORA) == "hace 2 h"
    assert hace("2026-11-13T12:00:00-03:00", AHORA) == "hace 12 días"
    assert hace("2026-11-24T10:00:00-03:00", AHORA) == "hace 1 día"


def test_top_errores_con_primera_ultima_y_ya_no():
    r = calcular(*_semanas(), AHORA)
    top = r["errores"]["top"]
    assert [e["n"] for e in top] == sorted([e["n"] for e in top], reverse=True) and len(top) <= 5
    assert top[0] == {"plantilla": "enrutador no pudo manejar %s: %s", "logger": "orquestador.ganchos.enrutador",
                      "tipo_exc": "AttributeError", "n": 262, "delta": 250, "primera": "2026-11-02T10:00:00-03:00",
                      "ultima": "2026-11-22T23:00:00-03:00", "hace": "hace 2 días"}
    assert [e["plantilla"] for e in top[1:]] == ["fallo de ejemplo uno", "fallo de ejemplo dos",
                                                   "fallo de ejemplo tres", "fallo de ejemplo cuatro"]
    assert r["errores"]["ya_no"] == ["observer del board falló: %s"]


def test_respuesta_separa_app_y_celu():
    r = calcular([ev_resp("asks", 60, False), ev_resp("asks", 600, False), ev_resp("asks", 30, True),
                  ev_resp("asks", None, False, "sin_respuesta")], [], [], AHORA)
    assert r["respuesta"]["asks"]["celu"] == {"mediana_s": 330, "p90_s": 600, "n": 2}
    assert r["respuesta"]["asks"]["en_app"]["n"] == 1 and r["respuesta"]["sin_respuesta"] == 1
    assert r["respuesta"]["blocked"]["celu"] == {"mediana_s": None, "p90_s": None, "n": 0}


def test_pedidos_trabas_comandos_cierres_app():
    r = calcular(*_semanas(), AHORA)
    assert r["pedidos"] == {
        "por_tipo": {"pestana": 2, "cerrar": 1, "tarea": 1},
        "por_origen": {"mcp": 3, "marca": 1},
        "por_motivo": {"rechazado": {"carpeta": 1}, "vencido": {"vencio": 1}, "descartado": {"reemplazado": 1}},
        "mediana_s": 40}
    assert r["respuesta"] == {
        "asks": {"en_app": {"mediana_s": 30, "p90_s": 30, "n": 1},
                 "celu": {"mediana_s": 330, "p90_s": 600, "n": 2}},
        "blocked": {"en_app": {"mediana_s": None, "p90_s": None, "n": 0},
                    "celu": {"mediana_s": 120, "p90_s": 120, "n": 1}},
        "sin_respuesta": 1}
    assert r["trabas"] == {"por_tipo": {"colgada": 1, "quieta": 1}, "mediana_s": 200,
                           "por_fin": {"prompt": 1, "dejo_de_trabajar": 1}}
    assert r["comandos"] == {"corridos": 2, "fallos": {"exit_1": 1}, "no": 1}
    assert r["cierres"] == {"frenados": 3, "resueltos_pct": 67}
    assert r["app"] == {"errores": {"tuneles/ssh_rechazado": 1, "atajos/sin_codigo": 1},
                        "tuneles_fallidos": 1, "desconexiones": 1}


def test_semana_vacia_no_inventa_nada():
    r = calcular([], [], [], AHORA)
    assert r["errores"] == {"top": [], "ya_no": []}
    assert r["pedidos"]["mediana_s"] is None and r["cierres"] == {"frenados": 0, "resueltos_pct": None}


def test_leer_eventos_ignora_lineas_rotas_y_otros_meses(tmp_path):
    (tmp_path / "2026-11.jsonl").write_text('{"v":1,"ts":"2026-11-20T10:00:00-03:00","ev":"resumen","fuente":"back","semana":"x","propuestas":0}\nroto\n')
    (tmp_path / "2026-09.jsonl").write_text("...")
    assert len(leer_eventos(tmp_path, *rango_semana("2026-W47"))) == 1


def test_leer_eventos_filtra_por_rango_y_directorio_ausente(tmp_path):
    (tmp_path / "2026-11.jsonl").write_text(
        '{"v":1,"ts":"2026-11-05T10:00:00-03:00","ev":"resumen","fuente":"back","semana":"a","propuestas":0}\n'
        '{"v":1,"ts":"2026-11-20T10:00:00-03:00","ev":"resumen","fuente":"back","semana":"b","propuestas":0}\n')
    r = leer_eventos(tmp_path, *rango_semana("2026-W47"))
    assert [e["semana"] for e in r] == ["b"]
    assert leer_eventos(tmp_path / "nada", *rango_semana("2026-W47")) == []
