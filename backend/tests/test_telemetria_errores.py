import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from orquestador.telemetria import Telemetria, TelemetriaHandler, normalizar_plantilla

T = datetime(2026, 11, 25, 14, 3, 11, tzinfo=timezone(timedelta(hours=-3)))


def lineas(d):
    return [json.loads(l) for f in sorted(d.glob("*.jsonl")) for l in f.read_text().splitlines()]


@pytest.mark.parametrize("entrada,salida", [
    ("enrutador no pudo manejar %s: %s", "enrutador no pudo manejar %s: %s"),
    ("falló el pane 12 tras 3 intentos", "falló el pane 0 tras 0 intentos"),
    ("no pude leer /home/x/data/a.json", "no pude leer <ruta>"),
    ("sesión 3f2a9c1e-1111-2222-3333-444455556666 rota", "sesión <id> rota"),
    ("comando 'git push --force' rechazado", "comando <txt> rechazado"),
    ('dijo "hola /etc/passwd" y cortó', "dijo <txt> y cortó"),
    ("commit deadbeef12 falló", "commit <id> falló"),
    ("a/b\nc\x00d", "a b c d"),
])
def test_normalizar_plantilla(entrada, salida):
    assert normalizar_plantilla(entrada) == salida


def test_recorte_a_120():
    assert len(normalizar_plantilla("x" * 300)) == 120


def test_plantilla_normalizada_cumple_el_esquema(tmp_path):
    from orquestador.telemetria import _PLANTILLA
    for msg in ("ruta /a/b c", "x/y", "t\x07", "'a/b'"):
        assert _PLANTILLA.match(normalizar_plantilla(msg))


def hacer_logger(tmp_path, reloj):
    tel = Telemetria(tmp_path, wall=lambda: reloj[0])
    h = TelemetriaHandler(tel)
    lg = logging.getLogger("orquestador.prueba_tel"); lg.handlers = [h]; lg.propagate = False
    return lg, h


def registro(lg, nivel, msg, args, creado, exc_info=None):
    # logging usa time.time_ns() según la versión: fijar `created` a mano, no parchear time
    r = lg.makeRecord(lg.name, nivel, __file__, 1, msg, args, exc_info)
    r.created = creado
    return r


def test_tramo_agrupa_en_una_linea_al_cambiar_de_hora(tmp_path):
    lg, h = hacer_logger(tmp_path, [T])
    for s in (0, 10, 20):
        h.handle(registro(lg, logging.WARNING, "observer del board falló: %s", ("x",), T.timestamp() + s))
    h.handle(registro(lg, logging.WARNING, "otro", (), T.timestamp() + 3600))
    (linea,) = [l for l in lineas(tmp_path) if l["ev"] == "error_back"]
    assert linea["n"] == 3 and linea["nivel"] == "WARNING" and linea["logger"] == "orquestador.prueba_tel"
    assert linea["plantilla"] == "observer del board falló: %s" and linea["tipo_exc"] is None
    assert linea["primera"] < linea["ultima"]


def test_flush_vuelca_tramo_en_curso(tmp_path):
    lg, h = hacer_logger(tmp_path, [T]); lg.error("a"); h.flush()
    assert [l["n"] for l in lineas(tmp_path)] == [1]


def test_exc_info_da_tipo_exc_y_no_guarda_traceback(tmp_path):
    lg, h = hacer_logger(tmp_path, [T])
    try:
        raise AttributeError("CANARIO-123")
    except AttributeError:
        lg.warning("falló %s", "x", exc_info=True)
    h.flush()
    assert lineas(tmp_path)[0]["tipo_exc"] == "AttributeError"
    assert "CANARIO" not in (tmp_path / "2026-11.jsonl").read_text()


def test_sin_recursion(tmp_path):
    tel = Telemetria(tmp_path, wall=lambda: T)
    h = TelemetriaHandler(tel); raiz = logging.getLogger("orquestador"); raiz.addHandler(h)
    try:
        logging.getLogger("orquestador.telemetria").warning("no pude escribir")
        h.flush()
        assert not list(tmp_path.glob("*.jsonl"))
    finally:
        raiz.removeHandler(h)


def test_info_no_cuenta(tmp_path):
    lg, h = hacer_logger(tmp_path, [T]); lg.info("hola"); h.flush()
    assert not list(tmp_path.glob("*.jsonl"))


def test_errores_internos_salen_como_error_back(tmp_path):
    tel = Telemetria(tmp_path, wall=lambda: T); h = TelemetriaHandler(tel)
    tel.anotar("traba", fase="inicio", tipo="colgada", avisada=True, nada=1)
    h.flush()
    assert any(l["ev"] == "error_back" and l["plantilla"] == "telemetria_campo_invalido" for l in lineas(tmp_path))


def test_el_texto_libre_no_se_cuela(tmp_path):
    lg, h = hacer_logger(tmp_path, [T])
    lg.warning("no pude leer /home/ando/secreto.txt con 'clave' 42")
    h.flush()
    (linea,) = [l for l in lineas(tmp_path) if l["ev"] == "error_back"]
    assert linea["plantilla"] == "no pude leer <ruta> con <txt> 0"


def test_emit_nunca_lanza(tmp_path):
    lg, h = hacer_logger(tmp_path, [T])
    class Malo:
        def __str__(self): raise RuntimeError("x")
    lg.warning(Malo())
    h.flush()
