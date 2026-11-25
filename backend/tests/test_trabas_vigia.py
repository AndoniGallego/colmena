import asyncio
import json
import os

from orquestador.trabas_vigia import VigiaTrabas
from test_trabas import ep, iso, llamada, prompt


def _escribir(path, lineas, m):
    path.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    os.utime(path, (ep(m), ep(m)))


class Mundo:
    def __init__(self, tmp_path):
        self.path = tmp_path / "s1.jsonl"
        self.ahora = ep(0)
        self.working = True
        self.silenciadas = set()
        self.avisos = []
        self.cambios = 0
        self.fondo = []
        self.subagentes = False

    def vigia(self):
        async def avisar(sesion, traba):
            self.avisos.append((sesion["session_id"], traba.tipo))

        def cambio():
            self.cambios += 1

        return VigiaTrabas(
            sesiones=lambda: [{"session_id": "s1", "pane_id": "w1:p1", "title": "T",
                               "status": "working" if self.working else "done"}],
            ruta=lambda sid: self.path,
            fondo=lambda sid: self.fondo,
            subagentes_activos=lambda sid: self.subagentes,
            avisar=avisar,
            silenciada=lambda sid: sid in self.silenciadas,
            al_cambiar=cambio,
            wall=lambda: self.ahora,
        )

    def grep_x4(self, extra=0):
        ls = [prompt()]
        for i in range(4 + extra):
            ls += llamada("Grep", {"pattern": "foo"}, i, m=0)
        return ls


def correr(coro):
    return asyncio.run(coro)


def test_avisa_una_sola_vez_por_episodio(tmp_path):
    w = Mundo(tmp_path)
    _escribir(w.path, w.grep_x4(), 0)
    v = w.vigia()
    correr(v.revisar())
    correr(v.revisar())
    _escribir(w.path, w.grep_x4(extra=2), 0.1)
    correr(v.revisar())
    assert w.avisos == [("s1", "repetida")]
    assert v.traba_de("s1")["tipo"] == "repetida"


def test_se_rearma_despues_de_un_prompt_del_usuario(tmp_path):
    w = Mundo(tmp_path)
    _escribir(w.path, w.grep_x4(), 0)
    v = w.vigia()
    correr(v.revisar())
    v.rearmar("s1")
    assert v.traba_de("s1") is None
    correr(v.revisar())
    assert len(w.avisos) == 1
    _escribir(w.path, w.grep_x4() + w.grep_x4(), 0.2)
    correr(v.revisar())
    assert len(w.avisos) == 2


def test_condicion_que_desaparece_rearma_y_saca_el_chip(tmp_path):
    w = Mundo(tmp_path)
    _escribir(w.path, w.grep_x4(), 0)
    v = w.vigia()
    correr(v.revisar())
    _escribir(w.path, w.grep_x4() + [prompt("otro", m=1)], 1)
    w.ahora = ep(1)
    correr(v.revisar())
    assert v.traba_de("s1") is None
    assert w.cambios >= 2
    _escribir(w.path, w.grep_x4(), 2)
    w.ahora = ep(2)
    correr(v.revisar())
    assert len(w.avisos) == 2


def test_sesion_silenciada_no_avisa(tmp_path):
    w = Mundo(tmp_path)
    w.silenciadas.add("s1")
    _escribir(w.path, w.grep_x4(), 0)
    v = w.vigia()
    correr(v.revisar())
    assert w.avisos == []


def test_fuera_de_working_no_evalua_ni_deja_chip(tmp_path):
    w = Mundo(tmp_path)
    _escribir(w.path, w.grep_x4(), 0)
    v = w.vigia()
    correr(v.revisar())
    assert v.traba_de("s1") is not None
    w.working = False
    correr(v.revisar())
    assert v.traba_de("s1") is None


def test_quieta_por_tiempo_avisa_al_correr_el_reloj(tmp_path):
    w = Mundo(tmp_path)
    _escribir(w.path, [prompt(), *llamada("Read", {"file_path": "/a"}, 1, m=0)], 0)
    v = w.vigia()
    correr(v.revisar())
    assert w.avisos == []
    w.ahora = ep(11)
    correr(v.revisar())
    assert w.avisos == [("s1", "quieta")]


def test_lectura_incremental_acumula_lineas(tmp_path):
    w = Mundo(tmp_path)
    ls = w.grep_x4()
    _escribir(w.path, ls[:5], 0)
    v = w.vigia()
    correr(v.revisar())
    assert w.avisos == []
    _escribir(w.path, ls, 0.1)
    correr(v.revisar())
    assert w.avisos == [("s1", "repetida")]


def test_sin_transcript_no_falla(tmp_path):
    w = Mundo(tmp_path)
    v = w.vigia()
    correr(v.revisar())
    assert w.avisos == []


def test_primera_lectura_arranca_por_la_cola_del_transcript(tmp_path, monkeypatch):
    # Un transcript de cientos de MB no se lee entero en el loop: alcanza con la cola.
    from orquestador import trabas_vigia
    monkeypatch.setattr(trabas_vigia, "LECTURA_INICIAL", 4096)
    w = Mundo(tmp_path)
    viejas = w.grep_x4()
    relleno = json.dumps({"type": "assistant", "timestamp": iso(1),
                          "message": {"content": [{"type": "text", "text": "x" * 8192}]}})
    nuevas = []
    for i in range(4):
        nuevas += llamada("Grep", {"pattern": "bar"}, 10 + i, m=5)
    _escribir(w.path, [*viejas, relleno, *nuevas], 5)
    w.ahora = ep(5)
    v = w.vigia()
    correr(v.revisar())
    assert v.traba_de("s1")["desde"] == ep(5)
    assert all("foo" not in linea for linea in v._cache["s1"]["lineas"])
