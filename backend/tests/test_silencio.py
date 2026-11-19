"""La marca del actualizador del kit de trabajo abre 60 s de silencio: sin "terminó", sin "Nueva respuesta", sin cadenas."""
import time

import pytest

from orquestador import silencio
from orquestador.digest import fin_de_turno
from orquestador.push import PushService
from test_push import Clock as PushClock, Recorder
from test_recargas import pboard, rboard, tracker  # noqa: F401
from conftest import SID


@pytest.fixture
def marca(tmp_path, monkeypatch):
    path = tmp_path / silencio.MARCA
    monkeypatch.setattr(silencio, "_marca", path)
    return path


def escribir(path, valor):
    path.write_text(str(valor), encoding="utf-8")


def test_vigente_segun_la_hora(marca):
    now = 1_000_000.0
    escribir(marca, now - 10)
    assert silencio.vigente(now=now)
    escribir(marca, now - 60)
    assert silencio.vigente(now=now)
    escribir(marca, now - 61)
    assert not silencio.vigente(now=now)
    escribir(marca, now + 2)
    assert silencio.vigente(now=now)
    escribir(marca, now + 3600)
    assert not silencio.vigente(now=now)


@pytest.mark.parametrize("contenido", ["", "mañana", "nan", "inf", "12 34", "\x00\x01"])
def test_marca_corrupta_no_silencia(marca, contenido):
    escribir(marca, contenido)
    assert not silencio.vigente()


def test_marca_ausente_o_sin_configurar(marca, monkeypatch):
    assert not silencio.vigente()
    monkeypatch.setattr(silencio, "_marca", None)
    assert not silencio.vigente()


def test_marca_con_salto_de_linea_como_la_escribe_date(marca):
    escribir(marca, f"{int(time.time())}\n")
    assert silencio.vigente()


def test_fin_de_turno_respeta_la_ventana(marca):
    escribir(marca, time.time())
    assert not fin_de_turno({"status": "working"}, {"status": "idle"})
    escribir(marca, time.time() - 120)
    assert fin_de_turno({"status": "working"}, {"status": "idle"})
    escribir(marca, "basura")
    assert fin_de_turno({"status": "working"}, {"status": "idle"})
    marca.unlink()
    assert fin_de_turno({"status": "working"}, {"status": "idle"})


def test_push_no_avisa_terminó_con_marca(tmp_path, marca):
    svc = PushService(tmp_path, sender=Recorder(), clock=PushClock())
    escribir(marca, time.time())
    assert svc.observe(pboard("working"), pboard("done")) == []
    # Un bloqueo sigue avisando: la marca solo calla los fines de turno.
    assert [e["kind"] for e in svc.observe(pboard("working"), pboard("blocked"))] == ["blocked"]


def test_push_vuelve_a_avisar_con_marca_vencida(tmp_path, marca):
    svc = PushService(tmp_path, sender=Recorder(), clock=PushClock())
    escribir(marca, time.time() - 300)
    assert [e["kind"] for e in svc.observe(pboard("working"), pboard("done"))] == ["done"]


def test_sin_nueva_respuesta_con_marca(tmp_path, marca):
    t, _ = tracker(tmp_path)
    escribir(marca, time.time())
    t.observe(rboard("working"), rboard("done"))
    assert not t.is_unread(SID)
    marca.unlink()
    t.observe(rboard("working"), rboard("done"))
    assert t.is_unread(SID)
