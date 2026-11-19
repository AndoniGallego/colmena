import asyncio
import os
import signal
from pathlib import Path

import pytest

from orquestador.guardian.lanzador import AjustesGuardian
from orquestador.guardian.proceso import ProcesoPty

pytestmark = pytest.mark.pty

FALSO = Path(__file__).resolve().parents[1] / "fixtures" / "falso_claude.py"


async def _run_shell_echo(tmp_path: Path) -> int | None:
    salida: list[bytes] = []
    codigo: list[int | None] = [None]

    def al_leer(d: bytes) -> None:
        salida.append(d)

    def al_salir(c: int) -> None:
        codigo[0] = c

    proc = await ProcesoPty.lanzar(
        ["/bin/sh", "-c", "echo pty_ok"],
        str(tmp_path),
        {**os.environ, "TERM": "xterm-256color", "PATH": os.environ["PATH"]},
        80,
        24,
        al_leer,
        al_salir,
    )
    try:
        await asyncio.wait_for(proc.tarea_espera, 5.0)
    finally:
        if proc.vivo:
            await proc.terminar()
    blob = b"".join(salida).decode("utf-8", errors="replace")
    assert "pty_ok" in blob
    return codigo[0]


def test_lanzar_lee_y_termina(tmp_path):
    codigo = asyncio.run(_run_shell_echo(tmp_path))
    assert codigo == 0


async def _redimensionar(tmp_path: Path) -> None:
    proc = await ProcesoPty.lanzar(
        ["/bin/sh", "-c", "sleep 2"],
        str(tmp_path),
        {**os.environ, "TERM": "xterm-256color", "PATH": os.environ["PATH"]},
        80,
        24,
        lambda _: None,
        lambda _: None,
    )
    try:
        proc.redimensionar(100, 30)
        proc.senal(signal.SIGINT)
        await asyncio.wait_for(proc.tarea_espera, 5.0)
    finally:
        if proc.vivo:
            await proc.terminar()


def test_redimensionar_y_senal(tmp_path):
    asyncio.run(_redimensionar(tmp_path))


def _proceso_falso(grupo: int, monkeypatch, primer_plano: int | None):
    proc = ProcesoPty.__new__(ProcesoPty)
    proc._proc = type("P", (), {"pid": grupo})()
    proc._master = 99
    proc._cerrado = False
    proc._codigo = None
    enviadas: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "tcgetpgrp", lambda fd: primer_plano if primer_plano is not None else (_ for _ in ()).throw(OSError()))
    return proc, enviadas


def test_senal_alcanza_tambien_al_grupo_en_primer_plano(monkeypatch):
    proc, enviadas = _proceso_falso(100, monkeypatch, 250)
    monkeypatch.setattr(os, "killpg", lambda g, s: enviadas.append((g, s)))
    proc.senal(signal.SIGTERM)
    assert (100, signal.SIGTERM) in enviadas and (250, signal.SIGTERM) in enviadas
    assert len(enviadas) == 2


def test_senal_no_repite_si_el_primer_plano_es_el_shell(monkeypatch):
    proc, enviadas = _proceso_falso(100, monkeypatch, 100)
    monkeypatch.setattr(os, "killpg", lambda g, s: enviadas.append((g, s)))
    proc.senal(signal.SIGHUP)
    assert enviadas == [(100, signal.SIGHUP)]


def test_senal_sigue_si_el_grupo_en_primer_plano_ya_no_existe(monkeypatch):
    proc, enviadas = _proceso_falso(100, monkeypatch, 250)

    def killpg(g, s):
        enviadas.append((g, s))
        if g == 250:
            raise ProcessLookupError

    monkeypatch.setattr(os, "killpg", killpg)
    proc.senal(signal.SIGTERM)
    assert (100, signal.SIGTERM) in enviadas


def test_terminar_manda_la_senal_al_primer_plano_con_fakes(monkeypatch):
    async def corre():
        proc, enviadas = _proceso_falso(100, monkeypatch, 250)
        hecho = asyncio.get_running_loop().create_future()
        proc._tarea_espera = hecho

        def killpg(g, s):
            enviadas.append((g, s))
            if g == 100 and not hecho.done():
                hecho.set_result(None)
                proc._codigo = 0

        monkeypatch.setattr(os, "killpg", killpg)
        await proc.terminar(((signal.SIGHUP, 1.0),))
        return enviadas

    assert sorted(asyncio.run(corre())) == [(100, signal.SIGHUP), (250, signal.SIGHUP)]


@pytest.mark.parametrize("primero", [0, 1, 4242])
def test_senal_ignora_primer_plano_invalido_o_propio(monkeypatch, primero):
    proc, enviadas = _proceso_falso(100, monkeypatch, primero)
    monkeypatch.setattr(os, "getpgrp", lambda: 4242)
    monkeypatch.setattr(os, "killpg", lambda g, s: enviadas.append((g, s)))
    proc.senal(signal.SIGTERM)
    assert enviadas == [(100, signal.SIGTERM)]
