import asyncio

import pytest

from conftest import make_snapshot
from orquestador.enchufe import FakeTerminales, NoTomado, Tiempo
from orquestador.mensaje import MensajeBody, MensajeService, StopBody
from orquestador.state import StateStore
from orquestador.traspaso import FALLO_TERMINAL, TraspasoError


def svc(tmp_path, t):
    return MensajeService(t, StateStore(tmp_path))


def test_prompt_va_al_enchufe_con_el_mismo_id(tmp_path):
    t = FakeTerminales.desde_snapshot(make_snapshot())
    asyncio.run(
        svc(tmp_path, t).execute(
            MensajeBody(id="m" * 8, pane_id="w1:p1", texto="hola", origen="bandeja")
        )
    )
    assert t.calls_of("mandar_prompt") == [("mandar_prompt", "w1:p1", "hola")]


@pytest.mark.parametrize("error", [NoTomado("boom"), Tiempo("herdr no respondió a tiempo")])
def test_falla_queda_incierta_con_el_mensaje_de_hoy(tmp_path, error):
    t = FakeTerminales.desde_snapshot(make_snapshot())
    t.fallas["mandar_prompt"] = error
    s = svc(tmp_path, t)
    with pytest.raises(TraspasoError) as info:
        asyncio.run(
            s.execute(MensajeBody(id="m" * 8, pane_id="w1:p1", texto="hola", origen="bandeja"))
        )
    assert info.value.status == 502 and info.value.detail == f"{FALLO_TERMINAL}: {error}"
    assert s.state.mensajes()[-1]["incierto"] is True


def test_stop_interrumpe(tmp_path):
    snap = make_snapshot("working")
    t = FakeTerminales.desde_snapshot(snap)
    asyncio.run(svc(tmp_path, t).stop(StopBody(pane_id="w1:p1")))
    assert t.calls_of("interrumpir") == [("interrumpir", "w1:p1")]
