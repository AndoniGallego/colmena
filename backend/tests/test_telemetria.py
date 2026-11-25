import json
from datetime import date, datetime, timedelta, timezone

import pytest

from orquestador.config import Config
from orquestador.telemetria import Telemetria, proyecto_de, token

T = datetime(2026, 11, 25, 14, 3, 11, tzinfo=timezone(timedelta(hours=-3)))


def lineas(d):
    return [json.loads(l) for f in sorted(d.glob("*.jsonl")) for l in f.read_text().splitlines()]


def test_anotar_escribe_sobre_y_campos(tmp_path):
    t = Telemetria(tmp_path / "tel", wall=lambda: T, estricto=True)
    assert t.anotar("traba", fase="inicio", tipo="colgada", avisada=True) is True
    assert lineas(tmp_path / "tel") == [{"v": 1, "ts": "2026-11-25T14:03:11-03:00", "ev": "traba",
                                          "fuente": "back", "fase": "inicio", "tipo": "colgada", "avisada": True}]
    assert (tmp_path / "tel" / "2026-11.jsonl").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "tel").stat().st_mode & 0o777 == 0o700


def test_campo_desconocido_se_descarta_y_estricto_falla(tmp_path):
    t = Telemetria(tmp_path, wall=lambda: T)
    t.anotar("traba", fase="inicio", tipo="colgada", avisada=False, detalle="git push --force")
    assert "detalle" not in lineas(tmp_path)[0]
    assert t.tomar_errores_internos() == {"telemetria_campo_invalido": 1}
    with pytest.raises(AssertionError):
        Telemetria(tmp_path, wall=lambda: T, estricto=True).anotar("traba", fase="fin", tipo="x", nada=1)


def test_tipo_equivocado_se_descarta(tmp_path):
    t = Telemetria(tmp_path, wall=lambda: T)
    t.anotar("pedido", tipo="pestana", origen="marca", creado=True, estado="abierto", segundos="12")
    assert "segundos" not in lineas(tmp_path)[0]


def test_bool_no_vale_como_int(tmp_path):
    t = Telemetria(tmp_path, wall=lambda: T)
    t.anotar("resumen", semana="2026-W48", propuestas=True)
    assert "propuestas" not in lineas(tmp_path)[0]


def test_enum_fuera_de_lista_pasa_a_otro(tmp_path):
    t = Telemetria(tmp_path, wall=lambda: T, estricto=True)
    t.anotar("traba", fase="fin", tipo="x", fin="raro", segundos=3)
    linea = lineas(tmp_path)[0]
    assert linea["tipo"] == "otro" and linea["fin"] == "otro"


def test_token_de_esquema_y_proyecto(tmp_path):
    t = Telemetria(tmp_path, wall=lambda: T)
    t.anotar("pedido", tipo=None, origen="mcp", creado=False, estado="descartado",
             motivo="Carpeta No", proyecto="con espacio")
    linea = lineas(tmp_path)[0]
    assert linea["motivo"] == "otro" and linea["proyecto"] is None and linea["tipo"] is None


def test_token_invalido_pasa_a_otro():
    assert token("cooldown") == "cooldown" and token("Cool Down") == "otro" and token("a" * 41) == "otro"
    assert token(None) == "otro"


def test_proyecto_solo_basename():
    assert proyecto_de("/home/x/Proyectos/orquestador") == "orquestador"
    assert proyecto_de("/tmp/con espacio") is None and proyecto_de("") is None and proyecto_de(None) is None


def test_evento_desconocido_no_escribe(tmp_path):
    assert Telemetria(tmp_path, wall=lambda: T).anotar("cualquiera", a=1) is False
    assert not list(tmp_path.glob("*.jsonl"))


def test_apagada_no_escribe(tmp_path):
    assert Telemetria(tmp_path, wall=lambda: T, activa=lambda: False).anotar("resumen", semana="2026-W48", propuestas=0) is False


def test_oserror_no_lanza_y_avisa_una_vez_por_hora(tmp_path, caplog):
    bloqueada = tmp_path / "ro"
    bloqueada.mkdir(mode=0o500)
    reloj = [T]
    t = Telemetria(bloqueada / "tel", wall=lambda: reloj[0])
    assert t.anotar("resumen", semana="2026-W48", propuestas=1) is False
    t.anotar("resumen", semana="2026-W48", propuestas=1)
    reloj[0] = T + timedelta(minutes=61)
    t.anotar("resumen", semana="2026-W48", propuestas=1)
    assert len([r for r in caplog.records if r.name == "orquestador.telemetria"]) == 2


def test_tope_de_mes_deja_de_escribir(tmp_path):
    t = Telemetria(tmp_path, wall=lambda: T, tope_bytes=200)
    for _ in range(10):
        t.anotar("resumen", semana="2026-W48", propuestas=1)
    texto = (tmp_path / "2026-11.jsonl").read_text()
    largo_linea = len(texto.splitlines()[0]) + 1
    assert len(texto.encode()) <= 200 + largo_linea  # la línea que cruza el tope puede entrar; después, ninguna más
    assert t.tomar_errores_internos() == {"telemetria_tope": 1}


def test_cambio_de_mes_escribe_en_archivo_nuevo(tmp_path):
    reloj = [T]
    t = Telemetria(tmp_path, wall=lambda: reloj[0])
    t.anotar("resumen", semana="2026-W48", propuestas=1)
    reloj[0] = datetime(2026, 12, 1, 0, 0, 1, tzinfo=T.tzinfo)
    t.anotar("resumen", semana="2026-W49", propuestas=1)
    assert sorted(p.name for p in tmp_path.glob("*.jsonl")) == ["2026-11.jsonl", "2026-12.jsonl"]


def test_ts_de_windows_solo_con_fuente_windows(tmp_path):
    t = Telemetria(tmp_path, wall=lambda: T)
    t.anotar("app", fuente="windows", ts="2026-11-25T10:00:00-03:00", origen="app", evento="arranque", ok=True)
    t.anotar("app", ts="1999-01-01T00:00:00", origen="app", evento="arranque", ok=True)
    a, b = lineas(tmp_path)
    assert a["ts"] == "2026-11-25T10:00:00-03:00" and a["fuente"] == "windows"
    assert b["ts"] == "2026-11-25T14:03:11-03:00" and b["fuente"] == "back"


def test_carpeta_no_se_crea_en_init(tmp_path):
    Telemetria(tmp_path / "tel", wall=lambda: T)
    assert not (tmp_path / "tel").exists()


def test_borrar_viejos_por_ultimo_dia_del_mes(tmp_path):
    for n in ("2026-07.jsonl", "2026-08.jsonl", "2026-09.jsonl", "2026-11.jsonl", "otro.txt"):
        (tmp_path / n).write_text("")
    t = Telemetria(tmp_path, wall=lambda: T)
    # hoy − 90 = 2026-08-27: julio (termina el 31/07) se borra; agosto (termina el 31/08) se queda
    assert t.borrar_viejos(date(2026, 11, 25)) == ["2026-07.jsonl"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-08.jsonl", "2026-09.jsonl", "2026-11.jsonl", "otro.txt"]


def test_borrar_viejos_sin_carpeta(tmp_path):
    assert Telemetria(tmp_path / "nada", wall=lambda: T).borrar_viejos(date(2026, 11, 25)) == []


def test_config_telemetria_por_defecto():
    c = Config()
    assert c.telemetria_activa is True and c.telemetria_resumen_hora == "09:00" and c.telemetria_resumen_dias == [0]


LIBRE = "No se pudo abrir /home/x: permiso"


def test_texto_libre_no_entra_en_campos_str(tmp_path):
    t = Telemetria(tmp_path, wall=lambda: T)
    t.anotar("error_back", nivel="ERROR", logger=LIBRE, plantilla=LIBRE, tipo_exc=LIBRE, n=1,
             primera=LIBRE, ultima=LIBRE)
    t.anotar("resumen", semana=LIBRE, propuestas=1)
    t.anotar("app", origen="app", evento="arranque", ok=True, version=LIBRE)
    assert "/home/x" not in "".join(f.read_text() for f in tmp_path.glob("*.jsonl"))
    assert "permiso" not in "".join(f.read_text() for f in tmp_path.glob("*.jsonl"))


def test_campos_str_validos_pasan(tmp_path):
    t = Telemetria(tmp_path, wall=lambda: T, estricto=True)
    t.anotar("error_back", nivel="ERROR", logger="orquestador.ganchos.enrutador",
             plantilla="enrutador no pudo manejar <txt>: <txt>", tipo_exc="AttributeError", n=3,
             primera="2026-11-25T14:00:00-03:00", ultima="2026-11-25T14:30:00-03:00")
    t.anotar("resumen", semana="2026-W48", propuestas=1)
    t.anotar("app", origen="app", evento="arranque", ok=True, version="0.12.3-beta")
    for l in lineas(tmp_path):
        assert "otro" not in l.values()


def test_no_estricto_nunca_lanza_con_assertion(tmp_path):
    t = Telemetria(tmp_path, wall=lambda: T)
    t._escribir = lambda *a: (_ for _ in ()).throw(AssertionError("x"))
    assert t.anotar("resumen", semana="2026-W48", propuestas=1) is False


def test_wall_que_lanza_no_escapa(tmp_path):
    def mala():
        raise RuntimeError("reloj")
    t = Telemetria(tmp_path, wall=mala)
    assert t.anotar("resumen", semana="2026-W48", propuestas=1) is False
    bloqueada = tmp_path / "ro"
    bloqueada.mkdir(mode=0o500)
    llamadas = [0]

    def reloj():
        llamadas[0] += 1
        if llamadas[0] > 1:
            raise RuntimeError("reloj")
        return T
    assert Telemetria(bloqueada / "x", wall=reloj).anotar("resumen", semana="2026-W48", propuestas=1) is False


def test_create_app_expone_telemetria_y_borra_viejos(cfg, tmp_path, handoffs, enchufe):
    from fastapi.testclient import TestClient

    from orquestador.app import create_app
    from orquestador.state import StateStore
    from orquestador.telemetria import Telemetria

    (tmp_path / "telemetria").mkdir()
    (tmp_path / "telemetria" / "2020-01.jsonl").write_text("")
    app = create_app(cfg, b"secret", StateStore(tmp_path), dist=tmp_path / "nodist", handoffs_dir=handoffs,
                     uploads_dir=tmp_path / "uploads", enchufe=enchufe)
    with TestClient(app):
        assert isinstance(app.state.telemetria, Telemetria)
        assert not (tmp_path / "telemetria" / "2020-01.jsonl").exists()


def test_shutdown_hace_flush_del_handler(cfg, tmp_path, handoffs, enchufe):
    from fastapi.testclient import TestClient

    from orquestador.app import create_app
    from orquestador.state import StateStore

    llamadas = []

    class H:
        def flush(self):
            llamadas.append(1)

    app = create_app(cfg, b"secret", StateStore(tmp_path), dist=tmp_path / "nodist", handoffs_dir=handoffs,
                     uploads_dir=tmp_path / "uploads", enchufe=enchufe, telemetria_handler=H())
    with TestClient(app):
        assert app.state.telemetria_handler is not None
    assert llamadas


def test_el_aviso_de_fallo_se_loguea_sin_el_lock_tomado(tmp_path):
    import logging
    bloqueada = tmp_path / "ro"
    bloqueada.mkdir(mode=0o500)
    t = Telemetria(bloqueada / "tel", wall=lambda: T)
    pudo = []

    class Sonda(logging.Handler):
        def emit(self, record):
            if t._lock.acquire(blocking=False):
                pudo.append(True)
                t._lock.release()
            else:
                pudo.append(False)

    log = logging.getLogger("orquestador.telemetria")
    sonda = Sonda()
    log.addHandler(sonda)
    try:
        t.anotar("resumen", semana="2026-W48", propuestas=1)
    finally:
        log.removeHandler(sonda)
    assert pudo == [True]
