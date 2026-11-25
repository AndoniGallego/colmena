from orquestador.ganchos.mensaje import Ids, MensajeGancho
from orquestador.telemetria_cierres import SeguidorCierres

BLOQUE_OK = 'listo\n```estado\n{"hizo": "x"}\n```'


def stop(sid, texto, activo=False, **extra):
    datos = {"last_assistant_message": texto, "stop_hook_active": activo, **extra}
    return MensajeGancho("Stop", "global", Ids(None, None, None, None, sid), datos)


def nuevo():
    anotadas = []
    return SeguidorCierres(lambda tipo, **c: anotadas.append((tipo, c))), anotadas


def test_frenado_por_estado_y_resuelto():
    s, anotadas = nuevo()
    s.al_stop(stop("s1", "sin bloque")); s.al_stop(stop("s1", BLOQUE_OK, activo=True))
    assert anotadas == [("cierre_frenado", {"motivo": "estado", "resuelto": True})]


def test_frenado_por_otro_y_no_resuelto():
    s, anotadas = nuevo()
    s.al_stop(stop("s1", BLOQUE_OK)); s.al_stop(stop("s1", "sin bloque", activo=True))
    assert anotadas == [("cierre_frenado", {"motivo": "otro", "resuelto": False})]


def test_stop_recortado_usa_tiene_estado():
    s, anotadas = nuevo()
    s.al_stop(stop("s1", "x" * 10, recortado=True, tiene_estado=False))
    s.al_stop(stop("s1", "y", activo=True, recortado=True, tiene_estado=True))
    assert anotadas == [("cierre_frenado", {"motivo": "estado", "resuelto": True})]


def test_stop_normal_no_anota():
    s, anotadas = nuevo()
    s.al_stop(stop("s1", "a")); s.al_stop(stop("s1", "b"))
    assert anotadas == []


def test_activo_sin_previo_no_anota():
    s, anotadas = nuevo()
    s.al_stop(stop("s1", "a", activo=True))
    assert anotadas == []


def test_sesiones_independientes_y_tope():
    s, anotadas = nuevo()
    s.al_stop(stop("s1", "sin bloque"))
    s.al_stop(stop("s2", BLOQUE_OK, activo=True))
    assert anotadas == []
    for i in range(600):
        s.al_stop(stop(f"x{i}", "a"))
    assert len(s._previos) <= 500
    s.al_stop(stop("s1", BLOQUE_OK, activo=True))
    assert anotadas == []


def test_no_guarda_texto_ni_lanza_sin_sid():
    s, anotadas = nuevo()
    s.al_stop(stop(None, "a", activo=True))
    s.al_stop(stop("s1", "secreto"))
    assert "secreto" not in repr(s._previos)
    assert anotadas == []
