"""GuiaStore: ayudante, PC dueña, turnos y tiempos de la guía por atajo."""
import asyncio
import json
import shutil
from pathlib import Path

import pytest

from orquestador.guia import (
    APAGADO_S, ARRANQUE_S, INACTIVA, NO_ARRANCO, PASO_S, POR_REUNION, SIN_RESPUESTA, TOPE, GuiaError, GuiaStore, acotar,
)
from orquestador.mostrar import Imagen
from orquestador.traspaso import TraspasoError

PANE = "w9:p1"
FOTO = {"foto": 42, "ventana": {"titulo": "Bloc de notas", "proceso": "notepad.exe"}, "controles": []}
IMAGEN = Imagen(b"\x89PNG\r\n\x1a\nfalsa", "png", 1568, 980)


class Prog:
    def __init__(self, delay, fn):
        self.delay, self.fn, self.cancelado = delay, fn, False

    def cancel(self):
        self.cancelado = True


class Puente:
    """Puente falso con la interfaz de PuenteGuia; los mensajes llevan el turno en JSON."""

    def __init__(self, base: Path):
        self.base = base
        self.pane = PANE
        self.abiertos, self.preguntas, self.cerrados, self.orden = [], [], [], []
        self.cerrados_sin_limpiar = []
        self.falla_abrir = None
        self.falla_tras_puerta = None
        self.falla_preguntar = False
        self.puerta = None
        self.n = 0

    async def abrir(self, mensaje, al_pane):
        self.abiertos.append(mensaje)
        if self.falla_abrir is not None:
            raise self.falla_abrir
        pane, puerta = self.pane, self.puerta
        al_pane(pane)
        if puerta is not None:
            await puerta
        if self.falla_tras_puerta is not None:
            raise self.falla_tras_puerta
        return pane

    async def preguntar(self, pane_id, mensaje):
        if self.falla_preguntar:
            raise RuntimeError("el pane no existe")
        self.preguntas.append((pane_id, mensaje))

    async def cerrar(self, pane_id):
        self.cerrados.append(pane_id)
        self.borrar_capturas()

    async def cerrar_pane(self, pane_id):
        self.cerrados_sin_limpiar.append(pane_id)

    async def guardar_captura(self, imagen, ext, controles):
        carpeta = self.base / "capturas"
        carpeta.mkdir(exist_ok=True)
        self.n += 1
        ruta = carpeta / f"cap-{self.n}.{ext}"
        ruta.write_bytes(imagen)
        return ruta, None

    def borrar_capturas(self):
        shutil.rmtree(self.base / "capturas", ignore_errors=True)

    def borrar_transcripts(self):
        pass

    @staticmethod
    def armar_pedido(turno, pregunta, ventana, captura, controles, cantidad, ancho, alto, nueva):
        cabeza = "Tarea nueva: olvidá la guía anterior.\n" if nueva else ""
        return cabeza + json.dumps({"guia": turno, "pregunta": pregunta, "captura": str(captura)})

    @staticmethod
    def armar_siguiente(turno, paso_hecho, ventana, captura, controles, cantidad, ancho, alto):
        cabeza = f"Ando hizo el paso {paso_hecho}\n" if paso_hecho else "Volvé a mirar la ventana\n"
        return cabeza + json.dumps({"guia": turno, "captura": str(captura)})

    @staticmethod
    def leer_bloque(texto):
        return json.loads(texto) if texto else None

    @staticmethod
    def texto_controles(controles):
        return "\n".join(f"{c['n']}. {c['tipo']}: {c['nombre']}" for c in controles)


def bloque(turno, paso=1, total=3, texto="Tocá Archivo", fin=False):
    return json.dumps({"guia": turno, "paso": paso, "total": total, "texto": texto, "fin": fin})


class H:
    def __init__(self, tmp_path):
        self.puente = Puente(tmp_path)
        self.eventos, self.progs, self.tareas = [], [], []
        self.fotos, self.soltados = [], []
        self.objetivo, self.reunion = "pc1", False
        self.store = GuiaStore(
            puente=self.puente, ofrecer=lambda q, ev: self.eventos.append((q, ev)), programar=self._programar,
            lanzar=self._lanzar, pc_objetivo=lambda: self.objetivo, reunion_activa=lambda: self.reunion,
            registrar_foto=lambda *a: self.fotos.append(a), soltar_nudo=self.soltados.append)
        self.q = object()
        self.store.pc_conectada("pc1", self.q)

    def _programar(self, delay, fn):
        p = Prog(delay, fn)
        self.progs.append(p)
        return p

    def _lanzar(self, coro):
        self.tareas.append(asyncio.ensure_future(coro))

    async def drenar(self):
        for _ in range(20):
            await asyncio.sleep(0)

    def activos(self, delay):
        return [p for p in self.progs if p.delay == delay and not p.cancelado]

    async def disparar(self, delay):
        p = self.activos(delay)[-1]
        p.cancelado = True
        p.fn()
        await self.drenar()

    def guia(self, cola=None):
        cola = self.q if cola is None else cola
        return [ev for q, (nombre, ev) in self.eventos if q is cola and nombre == "guia"]

    def estados(self):
        return [ev["estado"] for ev in self.guia()]

    async def pedir(self, pregunta="¿Cómo guardo como PDF?", device="pc1"):
        r = await self.store.pedir(device, pregunta, FOTO, IMAGEN)
        await self.drenar()
        return r

    async def con_ayudante_listo(self):
        """Primera guía (1.1) arrancada y respondida con el paso 1 de 3."""
        await self.pedir()
        self.store.al_stop(PANE, bloque("1.1"))


def corre(fn):
    def test(tmp_path):
        asyncio.run(fn(H(tmp_path)))
    test.__name__ = fn.__name__
    return test


@corre
async def test_primer_pedido_prepara_y_pega_el_pedido_como_mensaje_inicial(h):
    h.puente.puerta = asyncio.get_running_loop().create_future()
    r = await h.pedir()
    assert r == {"guia": 1, "estado": "preparando"}
    assert '"guia": "1.1"' in h.puente.abiertos[0]
    assert not h.puente.abiertos[0].startswith("Tarea nueva")
    assert h.fotos == [(PANE, 42, 1568, 980)]
    assert h.estados() == ["preparando"]
    h.puente.puerta.set_result(None)
    await h.drenar()
    assert h.estados() == ["preparando", "mirando"]
    assert h.store.snapshot()["ayudante"] == "listo"
    assert h.activos(PASO_S) and not h.activos(ARRANQUE_S)


@corre
async def test_segunda_guia_no_prepara(h):
    await h.con_ayudante_listo()
    r = await h.pedir("¿Y para imprimir?")
    assert r == {"guia": 2, "estado": "mirando"}
    assert len(h.puente.abiertos) == 1
    pane, msg = h.puente.preguntas[-1]
    assert pane == PANE and msg.startswith("Tarea nueva")
    assert '"guia": "2.1"' in msg
    assert h.estados()[-1] == "mirando"
    assert h.fotos[-1] == (PANE, 42, 1568, 980)


@corre
async def test_pedir_con_reunion_es_409(h):
    h.reunion = True
    with pytest.raises(GuiaError) as e:
        await h.pedir()
    assert (e.value.status, e.value.codigo) == (409, "reunion")
    assert e.value.mensaje == "Hay una reunión en curso: usá Mostrame del notch"
    assert not h.puente.abiertos


@corre
async def test_pedir_desde_otra_pc_es_409(h):
    with pytest.raises(GuiaError) as e:
        await h.pedir(device="celu")
    assert (e.value.status, e.value.codigo, e.value.mensaje) == (409, "otra_pc", "La guía está en otra PC")
    await h.pedir()
    h.objetivo = "pc2"
    h.store.pc_conectada("pc2", object())
    with pytest.raises(GuiaError) as e:
        await h.pedir(device="pc2")
    assert e.value.codigo == "otra_pc"


@corre
async def test_pregunta_vacia_es_422(h):
    with pytest.raises(GuiaError) as e:
        await h.pedir(" \n\x07 ")
    assert (e.value.status, e.value.codigo, e.value.mensaje) == (422, "sin_pregunta", "Escribí qué querés hacer")
    assert h.store.snapshot()["guia"] is None


@corre
async def test_al_stop_emite_paso_acotado(h):
    await h.pedir()
    h.store.al_stop(PANE, bloque("1.1", paso=99, total=3, texto="x" * 200))
    ev = h.guia()[-1]
    assert ev == {"guia": 1, "estado": "paso", "paso": 15, "total": 15, "texto": "x" * 120}
    s = h.store.snapshot()
    assert (s["mirando"], s["paso"], s["total"]) == (False, 15, 15)
    assert not h.activos(PASO_S)


def test_acotar_limpia_controles_y_respeta_el_fin():
    assert acotar({"guia": "1.1", "paso": 2, "total": 1, "texto": "a\x07b\nc", "fin": True}) == {
        "estado": "fin", "paso": 2, "total": 2, "texto": "ab c"}
    assert acotar({"guia": "1.1", "paso": -3, "total": 0, "texto": "no está", "fin": False})["estado"] == "no_encontrado"


@corre
async def test_no_encontrado_no_marca_paso(h):
    await h.pedir()
    h.store.al_stop(PANE, bloque("1.1", paso=0, total=4, texto="No encontré Guardar"))
    ev = h.guia()[-1]
    assert ev == {"guia": 1, "estado": "no_encontrado", "paso": 0, "total": 0, "texto": "No encontré Guardar"}


@corre
async def test_respuesta_de_turno_viejo_se_descarta(h):
    await h.pedir()
    await h.pedir("Otra cosa")
    assert h.store.snapshot()["turno"] == "2.1"
    antes = list(h.eventos)
    h.store.al_stop(PANE, bloque("1.1", paso=1))
    assert h.eventos == antes
    assert h.store.snapshot()["mirando"] is True
    h.store.al_stop(PANE, "")
    assert h.eventos == antes and h.store.snapshot()["mirando"] is True
    h.store.al_stop("w5:p5", bloque("2.1"))
    assert h.eventos == antes


@corre
async def test_siguiente_mientras_mira_es_409(h):
    await h.pedir()
    with pytest.raises(GuiaError) as e:
        await h.store.siguiente("pc1", FOTO, IMAGEN)
    assert (e.value.status, e.value.codigo, e.value.mensaje) == (409, "mirando", "Todavía estoy mirando")
    assert h.puente.n == 1


@corre
async def test_siguiente_sin_guia_o_en_fin_es_409(h):
    with pytest.raises(GuiaError) as e:
        await h.store.siguiente("pc1", FOTO, IMAGEN)
    assert (e.value.status, e.value.codigo, e.value.mensaje) == (409, "sin_guia", "No hay una guía en curso")
    await h.pedir()
    h.store.al_stop(PANE, bloque("1.1", paso=3, total=3, fin=True))
    assert h.guia()[-1]["estado"] == "fin"
    with pytest.raises(GuiaError) as e:
        await h.store.siguiente("pc1", FOTO, IMAGEN)
    assert e.value.codigo == "sin_guia"


@corre
async def test_siguiente_de_otra_pc_es_409(h):
    await h.con_ayudante_listo()
    with pytest.raises(GuiaError) as e:
        await h.store.siguiente("celu", FOTO, IMAGEN)
    assert e.value.codigo == "otra_pc"


@corre
async def test_siguiente_dice_el_paso_hecho_y_registra_foto(h):
    await h.pedir()
    h.store.al_stop(PANE, bloque("1.1", paso=2, total=4))
    h.fotos.clear()
    r = await h.store.siguiente("pc1", FOTO, IMAGEN)
    assert r == {"guia": 1, "estado": "mirando"}
    pane, msg = h.puente.preguntas[-1]
    assert pane == PANE and "Ando hizo el paso 2" in msg and '"guia": "1.2"' in msg
    assert h.fotos == [(PANE, 42, 1568, 980)]
    assert h.estados()[-1] == "mirando"
    assert h.store.snapshot()["turno"] == "1.2" and h.activos(PASO_S)


@corre
async def test_paso_sin_respuesta_a_los_90s(h):
    await h.con_ayudante_listo()
    await h.store.siguiente("pc1", FOTO, IMAGEN)
    await h.disparar(PASO_S)
    ev = h.guia()[-1]
    assert (ev["estado"], ev["texto"]) == ("error", SIN_RESPUESTA)
    assert h.store.snapshot()["mirando"] is False
    # La respuesta tardía del turno vencido ya no pisa nada.
    antes = list(h.eventos)
    h.store.al_stop(PANE, bloque("1.2", paso=2))
    assert h.eventos == antes
    await h.store.siguiente("pc1", FOTO, IMAGEN)
    assert h.store.snapshot()["turno"] == "1.3"


@corre
async def test_arranque_que_no_llega_a_60s(h):
    h.puente.puerta = asyncio.get_running_loop().create_future()
    await h.pedir()
    await h.disparar(ARRANQUE_S)
    ev = h.guia()[-1]
    assert (ev["estado"], ev["texto"]) == ("error", NO_ARRANCO)
    s = h.store.snapshot()
    assert (s["ayudante"], s["guia"], s["dueno"]) == ("apagado", None, None)
    h.puente.puerta.set_result(None)
    await h.drenar()
    assert h.puente.cerrados_sin_limpiar == [PANE] and h.puente.cerrados == []
    assert h.store.snapshot()["ayudante"] == "apagado"
    assert h.estados().count("mirando") == 0


@corre
async def test_arranque_vencido_que_despues_falla_cierra_el_pane(h):
    h.puente.puerta = asyncio.get_running_loop().create_future()
    await h.pedir()
    assert h.store.snapshot()["pane"] == PANE
    await h.disparar(ARRANQUE_S)
    h.puente.falla_tras_puerta = RuntimeError("no pegó")
    h.puente.puerta.set_result(None)
    await h.drenar()
    assert h.puente.cerrados_sin_limpiar == [PANE]
    assert h.puente.cerrados == []
    assert [ev["texto"] for ev in h.guia() if ev["estado"] == "error"] == [NO_ARRANCO]


@corre
async def test_tope_que_llega_tarde_cierra_el_pane(h):
    h.puente.puerta = asyncio.get_running_loop().create_future()
    await h.pedir()
    await h.disparar(ARRANQUE_S)
    h.puente.falla_tras_puerta = TraspasoError(429, "demasiadas pestañas nuevas")
    h.puente.puerta.set_result(None)
    await h.drenar()
    assert h.puente.cerrados_sin_limpiar == [PANE]


@corre
async def test_apagar_mientras_arranca_y_despues_falla_no_deja_el_pane(h):
    h.puente.puerta = asyncio.get_running_loop().create_future()
    await h.pedir()
    await h.store.apagar()
    h.puente.falla_tras_puerta = RuntimeError("no pegó")
    h.puente.puerta.set_result(None)
    await h.drenar()
    assert PANE in h.puente.cerrados + h.puente.cerrados_sin_limpiar
    assert h.store.snapshot()["ayudante"] == "apagado"


@corre
async def test_pane_viejo_que_vuelve_tarde_no_borra_la_captura_nueva(h):
    vieja = asyncio.get_running_loop().create_future()
    h.puente.puerta = vieja
    await h.pedir()
    await h.disparar(ARRANQUE_S)
    h.puente.puerta = asyncio.get_running_loop().create_future()
    h.puente.pane = "w9:p2"
    r = await h.pedir("Otra vez")
    assert r == {"guia": 2, "estado": "preparando"}
    nueva = h.puente.base / "capturas" / "cap-2.png"
    assert nueva.exists()
    vieja.set_result(None)
    await h.drenar()
    assert h.puente.cerrados_sin_limpiar == [PANE] and h.puente.cerrados == []
    assert nueva.exists()
    assert h.store.snapshot()["ayudante"] == "arrancando"


@corre
async def test_arranque_que_falla_avisa(h):
    h.puente.falla_abrir = RuntimeError("no pegó")
    await h.pedir()
    ev = h.guia()[-1]
    assert (ev["estado"], ev["texto"]) == ("error", NO_ARRANCO)
    assert h.store.snapshot()["ayudante"] == "apagado"
    assert not h.activos(ARRANQUE_S)


@corre
async def test_tope_por_hora_avisa(h):
    h.puente.falla_abrir = TraspasoError(429, "demasiadas pestañas nuevas")
    await h.pedir()
    ev = h.guia()[-1]
    assert (ev["estado"], ev["texto"]) == ("error", TOPE)
    assert h.store.snapshot()["ayudante"] == "apagado"


@corre
async def test_pane_muerto_relanza_en_el_mismo_pedido(h):
    await h.con_ayudante_listo()
    h.puente.falla_preguntar = True
    h.puente.pane = "w9:p2"
    r = await h.pedir("¿Y para imprimir?")
    assert r == {"guia": 2, "estado": "preparando"}
    assert len(h.puente.abiertos) == 2
    assert '"guia": "2.1"' in h.puente.abiertos[1]
    assert h.estados()[-2:] == ["preparando", "mirando"]
    assert h.store.snapshot()["pane"] == "w9:p2"
    assert h.puente.cerrados == []


@corre
async def test_pane_muerto_en_siguiente_relanza_con_la_pregunta_y_los_pasos_hechos(h):
    await h.pedir()
    h.store.al_stop(PANE, bloque("1.1", paso=2, total=4))
    h.puente.falla_preguntar = True
    h.puente.pane = "w9:p2"
    r = await h.store.siguiente("pc1", FOTO, IMAGEN)
    await h.drenar()
    assert r == {"guia": 1, "estado": "preparando"}
    msg = h.puente.abiertos[-1]
    assert not msg.startswith("Tarea nueva") and "Ando hizo el paso" not in msg
    datos = json.loads(msg)
    assert datos["guia"] == "1.2" and datos["captura"].endswith("cap-2.png")
    assert "¿Cómo guardo como PDF?" in datos["pregunta"]
    assert "pasos 1 a 2" in datos["pregunta"] and "paso 3" in datos["pregunta"]
    assert h.estados()[-2:] == ["preparando", "mirando"]
    assert h.store.snapshot()["pane"] == "w9:p2"


@corre
async def test_pane_muerto_en_siguiente_respeta_el_tope_de_la_pregunta(h):
    larga = "a" * 300
    await h.pedir(larga)
    h.store.al_stop(PANE, bloque("1.1", paso=1, total=4))
    h.puente.falla_preguntar = True
    await h.store.siguiente("pc1", FOTO, IMAGEN)
    await h.drenar()
    pregunta = json.loads(h.puente.abiertos[-1])["pregunta"]
    assert len(pregunta) <= 300
    assert "paso 1" in pregunta and "paso 2" in pregunta and pregunta.endswith("aaa")


@corre
async def test_pane_muerto_que_no_vuelve_avisa(h):
    await h.con_ayudante_listo()
    h.puente.falla_preguntar = True
    h.puente.falla_abrir = RuntimeError("no arrancó")
    await h.pedir("¿Y para imprimir?")
    assert len(h.puente.abiertos) == 2
    ev = h.guia()[-1]
    assert (ev["estado"], ev["texto"]) == ("error", NO_ARRANCO)


@corre
async def test_pedido_reemplazado_borra_la_captura_vieja(h):
    h.puente.puerta = asyncio.get_running_loop().create_future()
    await h.pedir()
    primera = h.puente.base / "capturas" / "cap-1.png"
    assert primera.exists()
    r = await h.pedir("Mejor otra cosa")
    assert r == {"guia": 2, "estado": "preparando"}
    assert not primera.exists()
    assert (h.puente.base / "capturas" / "cap-2.png").exists()
    assert len(h.puente.abiertos) == 1
    h.puente.puerta.set_result(None)
    await h.drenar()
    pane, msg = h.puente.preguntas[-1]
    assert pane == PANE and msg.startswith("Tarea nueva") and '"guia": "2.1"' in msg
    assert h.fotos[-1] == (PANE, 42, 1568, 980)
    assert h.guia()[-1] == {"guia": 2, "estado": "mirando", "paso": 0, "total": 0, "texto": ""}


@corre
async def test_salir_borra_capturas(h):
    await h.con_ayudante_listo()
    assert any((h.puente.base / "capturas").iterdir())
    await h.store.salir("pc1")
    assert not (h.puente.base / "capturas").exists() or not any((h.puente.base / "capturas").iterdir())
    s = h.store.snapshot()
    assert (s["ayudante"], s["guia"], s["dueno"], s["pane"]) == ("listo", None, None, PANE)
    assert h.soltados == [PANE]
    assert h.puente.cerrados == []
    await h.store.salir("pc1")


@corre
async def test_salir_de_otra_pc_es_409(h):
    await h.con_ayudante_listo()
    with pytest.raises(GuiaError) as e:
        await h.store.salir("celu")
    assert e.value.codigo == "otra_pc"
    assert h.store.snapshot()["guia"] == 1


@corre
async def test_apagado_a_los_10_min_cierra_y_borra(h):
    await h.pedir()
    await h.disparar(APAGADO_S)
    assert h.puente.cerrados == []
    assert h.activos(APAGADO_S)
    h.store.al_stop(PANE, bloque("1.1"))
    await h.disparar(APAGADO_S)
    assert h.puente.cerrados == [PANE]
    s = h.store.snapshot()
    assert (s["ayudante"], s["pane"], s["guia"]) == ("apagado", None, None)
    assert not (h.puente.base / "capturas").exists()


@corre
async def test_por_reunion_termina_apaga_y_suelta_nudo(h):
    await h.con_ayudante_listo()
    await h.store.por_reunion()
    ev = h.guia()[-1]
    assert (ev["estado"], ev["texto"]) == ("error", POR_REUNION)
    assert h.soltados == [PANE]
    assert h.puente.cerrados == [PANE]
    s = h.store.snapshot()
    assert (s["ayudante"], s["guia"]) == ("apagado", None)


@corre
async def test_solo_emite_a_la_pc_duena(h):
    otra = object()
    h.store.pc_conectada("pc2", otra)
    await h.con_ayudante_listo()
    assert h.guia()
    assert h.guia(otra) == []


@corre
async def test_pc_duena_que_se_va_termina_la_guia(h):
    await h.con_ayudante_listo()
    n = len(h.eventos)
    h.store.pc_desconectada("pc1", h.q)
    assert h.store.snapshot()["guia"] is None
    assert len(h.eventos) == n
    assert h.soltados == [PANE]


@corre
async def test_es_guia_solo_el_pane_actual(h):
    assert not h.store.es_guia(PANE)
    await h.con_ayudante_listo()
    assert h.store.es_guia(PANE)
    assert not h.store.es_guia("w1:p1")
    await h.store.apagar()
    assert not h.store.es_guia(PANE)


@corre
async def test_error_dice_si_la_guia_sigue(h):
    await h.con_ayudante_listo()
    await h.store.siguiente("pc1", FOTO, IMAGEN)
    await h.disparar(PASO_S)
    assert h.guia()[-1]["sigue"] is True
    await h.store.por_reunion()
    ev = h.guia()[-1]
    assert (ev["texto"], ev["sigue"]) == (POR_REUNION, False)


@corre
async def test_errores_de_arranque_no_siguen(h):
    h.puente.puerta = asyncio.get_running_loop().create_future()
    await h.pedir()
    await h.disparar(ARRANQUE_S)
    ev = h.guia()[-1]
    assert (ev["texto"], ev["sigue"]) == (NO_ARRANCO, False)


@corre
async def test_los_eventos_que_no_son_error_no_llevan_sigue(h):
    await h.con_ayudante_listo()
    assert all("sigue" not in ev for ev in h.guia() if ev["estado"] != "error")


@corre
async def test_apagado_avisa_con_error_y_suelta_el_nudo(h):
    await h.con_ayudante_listo()
    await h.disparar(APAGADO_S)
    ev = h.guia()[-1]
    assert (ev["estado"], ev["texto"], ev["sigue"]) == ("error", INACTIVA, False)
    assert h.soltados == [PANE]
    assert h.store.snapshot()["ayudante"] == "apagado"
