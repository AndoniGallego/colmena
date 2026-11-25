"""ReunionStore: charla, líneas detectadas, límites, diario en disco y caída de la PC."""
import asyncio
import json
import os
import stat
import time
from pathlib import Path

import pytest

from orquestador import reunion as R
from orquestador.mostrar import Imagen
from orquestador.reunion import (
    AjustesReunion, ReunionError, ReunionStore, ajustes_reunion, es_repetida, normalizar_linea,
)

AJ = AjustesReunion(cada_s=20, tope_detecciones=180, modelo="haiku", modelo_resumen="haiku")


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Prog:
    def __init__(self, delay, fn):
        self.delay, self.fn, self.cancelado = delay, fn, False

    def cancel(self):
        self.cancelado = True

    def activo(self):
        return not self.cancelado


class Detector:
    def __init__(self):
        self.respuestas = []
        self.llamadas = []
        self.resumenes = []
        self.temas = []
        self.temas_resumen = []
        self.resumen = {"titulo": "Plan de reembolsos", "resumen": ["a"], "pendientes": ["b"]}
        self.falla_resumen = False

    async def detectar(self, tramo, previas, tema=""):
        self.llamadas.append((tramo, list(previas)))
        self.temas.append(tema)
        return self.respuestas.pop(0) if self.respuestas else []

    async def resumir(self, charla, tocadas, tema=""):
        self.resumenes.append((charla, tocadas))
        self.temas_resumen.append(tema)
        if self.falla_resumen:
            raise RuntimeError("sin modelo")
        return self.resumen


class Puente:
    def __init__(self):
        self.pane = "w1:p1"
        self.abiertos = []
        self.preguntas = []
        self.cerrados = []
        self.falla = False
        self.falla_captura = False
        self.capturas = []
        self.borrados = []
        self.alg_en_guardar = None
        self.bloque = {"texto": "Sí, en el módulo X", "archivos": ["a.php"]}
        self.temas = []

    async def abrir(self, rid, repos, todos, tema=""):
        self.abiertos.append((rid, repos, todos))
        self.temas.append(tema)
        return self.pane

    async def preguntar(self, pane_id, msg_id, texto):
        if self.falla:
            raise RuntimeError("no entró")
        self.preguntas.append((pane_id, msg_id, texto))

    async def cerrar(self, pane_id):
        self.cerrados.append(pane_id)

    def borrar_archivos(self, *rutas):
        self.borrados.extend(rutas)

    async def guardar_captura(self, imagen, ext, controles):
        if self.falla_captura:
            raise OSError("disco")
        if self.alg_en_guardar:
            await self.alg_en_guardar()
        self.capturas.append((imagen, ext, controles))
        return Path("/cap/cap-1." + ext), (Path("/cap/cap-1.controles.txt") if controles else None)

    @staticmethod
    def texto_controles(controles):
        return "\n".join(f"{c['n']}. {c['tipo']}: {c['nombre']}" for c in controles)

    @staticmethod
    def armar_mostrar(linea_id, pregunta, charla, ventana, captura, controles, cantidad, ancho, alto):
        return f"MOSTRAR<{linea_id}>|{pregunta}|{charla}|{ventana['titulo']}|{captura}|{cantidad}|{ancho}x{alto}"

    def armar_pregunta(self, linea, tramo, repos):
        return f"PREGUNTA<{linea}>|{tramo}|{','.join(repos)}"

    def leer_respuesta(self, texto, linea_id):
        return self.bloque if "```copiloto" in texto else None


class Biblioteca:
    def __init__(self):
        self.guardados = []

    def guardar(self, datos, charla):
        self.guardados.append((datos, charla))
        return f"bib-{len(self.guardados)}"


class Notas:
    def __init__(self):
        self.creadas = []
        self.falla = None

    def crear(self, tipo, texto, origen=None):
        if self.falla:
            raise self.falla
        nota = {"id": f"n_{len(self.creadas) + 1}", "tipo": tipo, "texto": texto, "origen": origen}
        self.creadas.append(nota)
        return dict(nota)


class Memoria:
    def __init__(self):
        self.guardados = []
        self.falla = None

    def __call__(self, titulo, contenido):
        if self.falla:
            raise self.falla
        self.guardados.append((titulo, contenido))


class H:
    def __init__(self, tmp_path, ajustes=AJ):
        self.memoria = Memoria()
        self.eventos, self.progs, self.pend, self.vigias = [], [], [], []
        self.reloj, self.detector, self.puente, self.bib = Reloj(), Detector(), Puente(), Biblioteca()
        self.dir = tmp_path / "reuniones"
        self.fotos = []
        self.notas = Notas()
        self.store = ReunionStore(
            emitir=lambda e, d: self.eventos.append((e, d)), programar=self._programar,
            lanzar=self.pend.append, clock=self.reloj, detector=self.detector, puente=self.puente,
            biblioteca=self.bib, journal_dir=self.dir, ajustes=ajustes,
            registrar_foto=lambda *a: self.fotos.append(a), notas=self.notas,
            guardar_memoria=self.memoria)

    def _programar(self, delay, fn):
        p = Prog(delay, fn)
        (self.vigias if delay == R.SIN_TEXTO_S else self.progs).append(p)
        return p

    def drenar(self):
        async def todo():
            while self.pend:
                await self.pend.pop(0)
        asyncio.run(todo())

    def activos(self):
        return [p for p in self.progs if p.activo()]

    def disparar(self, p):
        p.cancelado = True
        p.fn()
        self.drenar()

    def evs(self, nombre):
        return [d for e, d in self.eventos if e == nombre]

    def empezar(self, device="pc1", repos=("repo-a",), todos=False, tema=None):
        extra = {} if tema is None else {"tema": tema}
        r = asyncio.run(self.store.empezar(device, list(repos), todos, **extra))
        self.drenar()
        return r["reunion"]

    def jfile(self, rid):
        return self.dir / f"{rid}.jsonl"


@pytest.fixture
def h(tmp_path):
    return H(tmp_path)


def go(coro):
    return asyncio.run(coro)


def test_texto_programa_una_sola_deteccion_a_cada_s(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "hola a todos")
    h.store.texto(rid, "pc1", "seguimos con el tema")
    assert len(h.activos()) == 1
    assert h.activos()[0].delay == 20


def test_sin_texto_nuevo_no_programa_deteccion(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "hola a todos")
    h.disparar(h.activos()[0])
    assert h.activos() == []
    h.store.texto(rid, "pc1", "más charla")
    assert len(h.activos()) == 1


def test_texto_mientras_detecta_reprograma_al_terminar(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "hola a todos")
    p = h.activos()[0]
    p.cancelado = True
    p.fn()  # arranca la detección: queda la corrutina sin correr
    h.store.texto(rid, "pc1", "llegó texto mientras detecta")
    assert h.activos() == []
    h.drenar()
    assert len(h.activos()) == 1


def test_texto_de_otro_device_es_409(h):
    rid = h.empezar()
    with pytest.raises(ReunionError) as e:
        h.store.texto(rid, "otra", "hola")
    assert e.value.status == 409


def test_texto_largo_o_con_control_se_rechaza(h):
    rid = h.empezar()
    with pytest.raises(ReunionError) as e:
        h.store.texto(rid, "pc1", "x" * 2001)
    assert e.value.status == 422
    h.store.texto(rid, "pc1", "hola\x00 mundo\nchau")
    assert h.store.snapshot()["charla_chars"] == len("hola mundo chau")
    h.store.texto(rid, "pc1", "x" * 2000)


def test_texto_de_reunion_desconocida_es_404(h):
    with pytest.raises(ReunionError) as e:
        h.store.texto("rX", "pc1", "hola")
    assert e.value.status == 404


def _linea_n(i):
    return {"tipo": "pregunta", "texto": f"tema{i} alfa{i} beta{i} gamma{i}"}


def test_tope_por_minuto_y_dedup_de_lineas(h):
    rid = h.empezar()
    h.detector.respuestas = [[_linea_n(i) for i in range(0, 3)], [_linea_n(i) for i in range(3, 6)],
                             [_linea_n(i) for i in range(6, 9)], [_linea_n(9)]]
    for i in range(4):
        h.store.texto(rid, "pc1", f"texto numero {i}")
        h.disparar(h.activos()[0])
        h.reloj.t += 10
    assert len(h.evs("reunion-linea")) == 6

    h2 = H(h.dir.parent / "otro")
    rid = h2.empezar()
    h2.detector.respuestas = [[{"tipo": "pregunta", "texto": "¿Tenemos reembolsos parciales?"},
                               {"tipo": "pregunta", "texto": "tenemos reembolsos parciales"},
                               {"tipo": "requerimiento", "texto": "x" * 200}]]
    h2.store.texto(rid, "pc1", "hola")
    h2.disparar(h2.activos()[0])
    lineas = h2.evs("reunion-linea")
    assert len(lineas) == 2
    assert len(lineas[1]["texto"]) == 90


def test_linea_por_minuto_se_libera_pasado_el_minuto(h):
    rid = h.empezar()
    h.detector.respuestas = [[_linea_n(i) for i in range(3)], [_linea_n(i) for i in range(3, 6)],
                             [_linea_n(6)]]
    for _ in range(3):
        h.store.texto(rid, "pc1", "algo")
        h.disparar(h.activos()[0])
    assert len(h.evs("reunion-linea")) == 6
    h.reloj.t += 61
    h.detector.respuestas = [[_linea_n(7)]]
    h.store.texto(rid, "pc1", "algo más")
    h.disparar(h.activos()[0])
    assert len(h.evs("reunion-linea")) == 7


def test_lineas_max_200(h, monkeypatch):
    monkeypatch.setattr(R, "LINEAS_POR_MIN", 10_000)
    monkeypatch.setattr(R, "ITEMS_POR_LLAMADA", 100)
    rid = h.empezar()
    h.detector.respuestas = [[_linea_n(i) for i in range(j, j + 50)] for j in range(0, 250, 50)]
    for _ in range(5):
        h.store.texto(rid, "pc1", "algo")
        h.disparar(h.activos()[0])
    assert len(h.evs("reunion-linea")) == 200


def test_charla_llena_pasa_a_llena_y_no_detecta(h, monkeypatch):
    monkeypatch.setattr(R, "CHARLA_MAX", 100)
    rid = h.empezar()
    h.store.texto(rid, "pc1", "a" * 80)
    h.store.texto(rid, "pc1", "b" * 80)
    snap = h.store.snapshot()
    assert snap["estado"] == "llena"
    assert snap["charla_chars"] == 100
    assert h.activos() == []
    assert h.evs("reunion-estado")[-1]["estado"] == "llena"
    h.store.texto(rid, "pc1", "c" * 10)
    assert h.store.snapshot()["charla_chars"] == 100
    assert h.activos() == []
    go(h.store.terminar(rid))
    assert h.bib.guardados[0][0]["motivo"] == "llena"


def test_tramo_es_lo_nuevo_mas_600_de_contexto(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "a" * 1000)
    h.disparar(h.activos()[0])
    h.store.texto(rid, "pc1", "b" * 100)
    h.disparar(h.activos()[0])
    primero, segundo = h.detector.llamadas[0][0], h.detector.llamadas[1][0]
    assert primero == "a" * 1000
    assert segundo.endswith("b" * 100)
    assert segundo.count("a") == 600
    assert len(segundo) <= 600 + 101


def test_tramo_largo_se_corta_a_3000_y_sigue_con_lo_que_queda(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "a" * 2000)
    h.store.texto(rid, "pc1", "b" * 2000)
    h.disparar(h.activos()[0])
    assert len(h.detector.llamadas[0][0]) == 3000
    assert len(h.activos()) == 1  # quedó texto sin ver


def _con_linea(h, texto="¿Hay reembolsos parciales?"):
    rid = h.empezar()
    h.detector.respuestas = [[{"tipo": "pregunta", "texto": texto}]]
    h.store.texto(rid, "pc1", "x" * 2000)
    h.disparar(h.activos()[0])
    return rid, h.evs("reunion-linea")[-1]["id"]


def test_tocar_pregunta_al_copiloto_con_contexto(h):
    rid, lid = _con_linea(h)
    assert go(h.store.tocar(rid, lid)) == "buscando"
    pane, msg_id, texto = h.puente.preguntas[0]
    assert (pane, msg_id) == ("w1:p1", lid)
    assert texto.startswith("PREGUNTA<¿Hay reembolsos parciales?>|")
    assert texto.endswith("|repo-a")
    tramo = texto.split("|")[1]
    assert 0 < len(tramo) <= 1500
    assert h.evs("reunion-respuesta")[-1] == {"reunion": rid, "linea": lid, "estado": "buscando",
                                              "texto": "", "archivos": []}


def test_tocar_con_una_en_curso_queda_en_cola(h):
    rid, l1 = _con_linea(h)
    h.detector.respuestas = [[{"tipo": "pregunta", "texto": "otra cosa totalmente distinta"}]]
    h.store.texto(rid, "pc1", "más")
    h.disparar(h.activos()[0])
    l2 = h.evs("reunion-linea")[-1]["id"]
    assert go(h.store.tocar(rid, l1)) == "buscando"
    assert go(h.store.tocar(rid, l2)) == "en_cola"
    assert len(h.puente.preguntas) == 1
    assert h.evs("reunion-respuesta")[-1]["estado"] == "en_cola"
    assert go(h.store.tocar(rid, l2)) == "en_cola"
    assert len(h.puente.preguntas) == 1


def test_cola_llena_es_429(h, monkeypatch):
    monkeypatch.setattr(R, "LINEAS_POR_MIN", 10_000)
    monkeypatch.setattr(R, "ITEMS_POR_LLAMADA", 100)
    rid = h.empezar()
    h.detector.respuestas = [[_linea_n(i) for i in range(8)]]
    h.store.texto(rid, "pc1", "algo")
    h.disparar(h.activos()[0])
    ids = [d["id"] for d in h.evs("reunion-linea")]
    for lid in ids[:6]:
        go(h.store.tocar(rid, lid))  # 1 en curso + 5 en cola
    with pytest.raises(ReunionError) as e:
        go(h.store.tocar(rid, ids[6]))
    assert e.value.status == 429


def test_al_stop_resuelve_y_pasa_a_la_siguiente(h):
    rid, l1 = _con_linea(h)
    h.detector.respuestas = [[{"tipo": "pregunta", "texto": "otra cosa totalmente distinta"}]]
    h.store.texto(rid, "pc1", "más")
    h.disparar(h.activos()[0])
    l2 = h.evs("reunion-linea")[-1]["id"]
    go(h.store.tocar(rid, l1))
    go(h.store.tocar(rid, l2))
    h.store.al_stop("w1:p1", "listo\n```copiloto\n{}\n```")
    h.drenar()
    listo = [d for d in h.evs("reunion-respuesta") if d["estado"] == "lista"][0]
    assert listo["linea"] == l1 and listo["texto"] == "Sí, en el módulo X" and listo["archivos"] == ["a.php"]
    assert [p[1] for p in h.puente.preguntas] == [l1, l2]
    assert h.evs("reunion-respuesta")[-1]["estado"] == "buscando"
    assert h.evs("reunion-respuesta")[-1]["linea"] == l2


def test_al_stop_de_otro_pane_o_sin_pendiente_se_ignora(h):
    rid, lid = _con_linea(h)
    n = len(h.eventos)
    h.store.al_stop("w1:p1", "```copiloto\n{}\n```")  # nada en curso
    go(h.store.tocar(rid, lid))
    n = len(h.eventos)
    h.store.al_stop("w9:p9", "```copiloto\n{}\n```")
    h.drenar()
    assert len(h.eventos) == n


def test_al_stop_sin_bloque_valido_es_error(h):
    rid, lid = _con_linea(h)
    go(h.store.tocar(rid, lid))
    h.store.al_stop("w1:p1", "no hay bloque")
    h.drenar()
    assert h.evs("reunion-respuesta")[-1]["estado"] == "error"
    h.store.al_stop("w1:p1", "```copiloto\n{}\n```")  # ya no hay pendiente
    assert h.evs("reunion-respuesta")[-1]["estado"] == "error"


def test_preguntar_fallido_marca_error_y_reabre_en_el_proximo_toque(h):
    rid, lid = _con_linea(h)
    h.puente.falla = True
    assert go(h.store.tocar(rid, lid)) == "error"
    assert h.evs("reunion-respuesta")[-1]["estado"] == "error"
    h.puente.falla = False
    assert go(h.store.tocar(rid, lid)) == "buscando"
    assert len(h.puente.preguntas) == 1


def test_tocar_sin_copiloto_es_409(h):
    h.puente.pane = None
    rid, lid = _con_linea(h)
    with pytest.raises(ReunionError) as e:
        go(h.store.tocar(rid, lid))
    assert e.value.status == 409


def test_preguntar_ultimo_crea_linea_manual(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "z" * 2000)
    lid = go(h.store.preguntar_ultimo(rid))
    lin = h.evs("reunion-linea")[-1]
    assert lin["id"] == lid and lin["tipo"] == "manual"
    tramo = h.puente.preguntas[0][2].split("|")[1]
    assert tramo == "z" * 1500


def test_preguntar_ultimo_sin_charla_es_422(h):
    rid = h.empezar()
    with pytest.raises(ReunionError) as e:
        go(h.store.preguntar_ultimo(rid))
    assert e.value.status == 422


def test_pc_caida_pausa_y_abandono_guarda_sin_pc(h):
    rid = h.empezar()
    h.store.pc_volvio("pc1", "q1")
    h.store.texto(rid, "pc1", "hola")
    det = h.activos()[0]
    h.store.pc_caida("pc1", "q1")
    assert h.store.snapshot()["estado"] == "sin_pc"
    assert h.evs("reunion-estado")[-1]["estado"] == "sin_pc"
    assert det.cancelado
    abandono = h.activos()[0]
    assert abandono.delay == 1800
    h.store.pc_volvio("pc1", "q2")
    assert abandono.cancelado
    assert h.store.snapshot()["estado"] == "escuchando"
    h.store.pc_caida("pc1", "q2")
    h.disparar(h.activos()[-1])
    assert h.bib.guardados[-1][0]["motivo"] == "sin_pc"


def test_pc_caida_cuenta_conexiones(h):
    rid = h.empezar()
    h.store.pc_volvio("pc1", "q1")
    h.store.pc_volvio("pc1", "q2")
    h.store.pc_caida("pc1", "q1")
    assert h.store.snapshot()["estado"] == "escuchando"
    h.store.pc_caida("pc1", "q2")
    assert h.store.snapshot()["estado"] == "sin_pc"


def test_pc_volvio_con_texto_pendiente_reprograma(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "hola")
    h.store.pc_caida("pc1", "q1")
    h.store.pc_volvio("pc1", "q1")
    assert [p.delay for p in h.activos()] == [20]


def test_pc_caida_de_otro_device_no_afecta(h):
    h.empezar()
    h.store.pc_volvio("otra", "q9")
    h.store.pc_caida("otra", "q9")
    assert h.store.snapshot()["estado"] == "escuchando"
    assert h.activos() == []


def test_una_reunion_a_la_vez_409(h):
    h.empezar()
    with pytest.raises(ReunionError) as e:
        go(h.store.empezar("pc2", [], True))
    assert e.value.status == 409


def test_pausar_y_seguir(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "hola")
    det = h.activos()[0]
    h.store.pausar(rid)
    assert det.cancelado and h.store.snapshot()["estado"] == "pausada"
    h.store.seguir(rid)
    assert h.store.snapshot()["estado"] == "escuchando"
    assert [p.delay for p in h.activos()] == [20]


def test_diario_y_terminar_borran_journal(h):
    rid = h.empezar()
    assert h.dir.stat().st_mode & 0o777 == 0o700
    assert stat.S_IMODE(os.stat(h.jfile(rid)).st_mode) == 0o600
    h.store.texto(rid, "pc1", "hola a todos")
    tipos = [json.loads(x)["e"] for x in h.jfile(rid).read_text().splitlines()]
    assert tipos == ["inicio", "copiloto", "texto"]
    assert go(h.store.terminar(rid)) == "bib-1"
    assert not h.jfile(rid).exists()
    assert h.evs("reunion-guardada") == [{"reunion": rid, "biblioteca": "bib-1"}]
    assert h.store.snapshot() == {}


def test_terminar_arma_datos_y_cierra_copiloto(h):
    rid, lid = _con_linea(h)
    go(h.store.tocar(rid, lid))
    h.store.al_stop("w1:p1", "```copiloto\n{}\n```")
    h.drenar()
    go(h.store.terminar(rid))
    datos, charla = h.bib.guardados[0]
    assert datos["v"] == 1 and datos["reunion"] == rid and datos["motivo"] == "terminada"
    assert datos["repos"] == ["repo-a"]
    assert datos["titulo"] == "Plan de reembolsos" and datos["resumen"] == ["a"] and datos["pendientes"] == ["b"]
    assert datos["tocadas"] == [{"texto": "¿Hay reembolsos parciales?", "tipo": "pregunta",
                                 "respuesta": "Sí, en el módulo X", "archivos": ["a.php"]}]
    assert datos["lineas"] == 1 and datos["charla_chars"] == 2000 and datos["recortada"] is False
    assert "x" * 2000 in charla and charla.startswith("[")
    assert h.puente.cerrados == ["w1:p1"]
    assert h.evs("reunion-estado")[-1]["estado"] == "guardada"


def test_terminar_sin_resumen_y_charla_larga_recortada(h, monkeypatch):
    monkeypatch.setattr(R, "RESUMEN_CHARS", 100)
    monkeypatch.setattr(R, "RESUMEN_INICIO_CHARS", 20)
    h.detector.falla_resumen = True
    rid = h.empezar()
    h.store.texto(rid, "pc1", "a" * 200)
    go(h.store.terminar(rid))
    datos, _ = h.bib.guardados[0]
    assert datos["titulo"] == "Reunión sin resumen" and datos["resumen"] == []
    enviada = h.detector.resumenes[0][0]
    assert "[…]" in enviada and len(enviada) < 200
    assert datos["recortada"] is True


def test_terminar_con_biblioteca_caida_conserva_diario_y_deja_reintentar(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "hola")

    def falla(datos, charla):
        raise OSError("disco")
    h.bib.guardar = falla
    with pytest.raises(ReunionError) as e:
        go(h.store.terminar(rid))
    assert e.value.status == 500
    assert h.jfile(rid).exists()
    assert h.store.snapshot()["estado"] == "escuchando"
    assert h.puente.cerrados == []


def test_terminar_cierra_copiloto_tambien_con_sin_pc(h):
    rid = h.empezar()
    go(h.store.terminar(rid, "sin_pc"))
    assert h.puente.cerrados == ["w1:p1"]


def test_recuperar_journal_guarda_interrumpida(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "primera tanda")
    h.reloj.t += 5
    h.store.texto(rid, "pc1", "segunda tanda")
    ruta = h.jfile(rid)
    with open(ruta, "a") as f:
        f.write('{"e":"texto","ts":1,"texto":"cort')  # última línea cortada
    h2 = H(h.dir.parent)
    h2.dir = h.dir
    ids = h2.store.recuperar()
    h2.drenar()
    assert ids == ["bib-1"]
    datos, charla = h2.bib.guardados[0]
    assert datos["motivo"] == "interrumpida" and datos["reunion"] == rid and datos["v"] == 1
    assert "primera tanda" in charla and "segunda tanda" in charla and "cort" not in charla
    assert not ruta.exists()
    assert h2.store.snapshot() == {}


def test_ajustes_reunion_recorta():
    a = ajustes_reunion({"cada_s": 3, "tope_detecciones": -1, "modelo": "opus", "modelo_resumen": "sonnet"})
    assert (a.cada_s, a.tope_detecciones, a.modelo, a.modelo_resumen) == (10, 0, "haiku", "sonnet")
    a = ajustes_reunion({"cada_s": 999, "tope_detecciones": 99999})
    assert (a.cada_s, a.tope_detecciones) == (120, 2000)
    a = ajustes_reunion({})
    assert (a.cada_s, a.tope_detecciones, a.modelo, a.modelo_resumen) == (20, 180, "haiku", "haiku")
    assert ajustes_reunion({"cada_s": "x", "tope_detecciones": True}).cada_s == 20


def test_normalizar_y_repetida():
    assert normalizar_linea("¿Tenemos  Reembolsos, parciales?") == "tenemos reembolsos parciales"
    assert es_repetida("tenemos reembolsos parciales", ["¿Tenemos reembolsos parciales?"])
    assert es_repetida("a b c d e f g h i j", ["a b c d e f g h i k"])  # 9/11 palabras
    assert not es_repetida("cómo está el deploy", ["¿Tenemos reembolsos parciales?"])
    assert not es_repetida("hola", [])
    previas = ["igual a"] + [f"otra {i} cosa{i}" for i in range(30)]
    assert not es_repetida("igual a", previas)  # solo cuentan las últimas 30


def _bib_falla(h):
    def falla(datos, charla):
        raise OSError("disco")
    h.bib.guardar = falla


def test_abandono_con_biblioteca_caida_no_deja_trabada_la_reunion(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "hola")
    h.store.pc_caida("pc1", "q1")
    _bib_falla(h)
    h.disparar(h.activos()[-1])  # abandono: terminar falla
    assert h.store.snapshot()["estado"] == "sin_pc"
    assert [p.delay for p in h.activos()] == [1800]  # reprogramado
    h.store.pc_volvio("pc1", "q2")
    assert h.store.snapshot()["estado"] == "escuchando"
    assert [p.delay for p in h.activos()] == [20]  # detección retomada, sin abandono


def test_terminar_manual_desde_sin_pc_que_falla_reprograma_abandono(h):
    rid = h.empezar()
    h.store.pc_caida("pc1", "q1")
    _bib_falla(h)
    with pytest.raises(ReunionError):
        go(h.store.terminar(rid))
    assert h.store.snapshot()["estado"] == "sin_pc"
    assert [p.delay for p in h.activos()] == [1800]


def test_charla_a_un_caracter_del_tope_pasa_a_llena(h, monkeypatch):
    monkeypatch.setattr(R, "CHARLA_MAX", 100)
    rid = h.empezar()
    h.store.texto(rid, "pc1", "a" * 99)
    assert h.store.snapshot()["estado"] == "escuchando"
    h.store.texto(rid, "pc1", "b")
    assert h.store.snapshot()["estado"] == "llena"
    assert h.activos() == []


def test_recuperar_saltea_un_diario_roto_y_recupera_los_demas(h, caplog):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "lo que vale")
    roto = h.dir / "aaaa-roto.jsonl"
    roto.write_text('{"e":"inicio","device":"pc1","ts":"no-es-numero","repos":[],"todos":true}\n'
                    '{"e":"texto","ts":1,"texto":"secreto de la charla"}\n')
    h2 = H(h.dir.parent)
    h2.dir = h.dir
    with caplog.at_level("WARNING"):
        ids = h2.store.recuperar()
    h2.drenar()
    assert ids == ["bib-1"]
    assert "lo que vale" in h2.bib.guardados[0][1]
    assert roto.exists()
    assert any("aaaa-roto.jsonl" in r.getMessage() for r in caplog.records)
    assert not any("secreto" in r.getMessage() for r in caplog.records)


def test_recuperar_saltea_un_diario_con_un_numero_enorme(h, caplog):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "lo que vale")
    roto = h.dir / "aaaa-enorme.jsonl"
    roto.write_text('{"e":"inicio","device":"pc1","ts":1,"repos":[],"todos":true}\n'
                    '{"e":"linea","id":"l1","texto":"x","tipo":"dato","ts":1,"fin_chars":1e400}\n')
    h2 = H(h.dir.parent)
    h2.dir = h.dir
    with caplog.at_level("WARNING"):
        ids = h2.store.recuperar()
    h2.drenar()
    assert ids == ["bib-1"]
    assert roto.exists()
    assert any("aaaa-enorme.jsonl" in r.getMessage() for r in caplog.records)


def test_recuperar_cierra_el_copiloto_del_diario(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "hola")
    h2 = H(h.dir.parent)
    h2.store.recuperar()
    h2.drenar()
    assert h2.puente.cerrados == ["w1:p1"]


def test_detectar_recorta_a_3_items_por_llamada(h):
    rid = h.empezar()
    h.detector.respuestas = [[_linea_n(i) for i in range(5)]]
    h.store.texto(rid, "pc1", "hola")
    h.disparar(h.activos()[0])
    assert len(h.evs("reunion-linea")) == 3


def test_empezar_abre_el_copiloto_en_segundo_plano(h):
    r = go(h.store.empezar("pc1", ["repo-a"], False))
    assert h.puente.abiertos == [] and len(h.pend) == 1
    assert h.evs("reunion-estado")[-1]["copiloto"] == "abriendo"
    assert h.store.snapshot()["copiloto"] == "abriendo"
    h.drenar()
    assert h.puente.abiertos == [(r["reunion"], ["repo-a"], False)]
    assert h.evs("reunion-estado")[-1]["copiloto"] == "listo"


def test_copiloto_que_no_abre_queda_sin_copiloto(h):
    async def falla(rid, repos, todos):
        raise RuntimeError("no abrió")
    h.puente.abrir = falla
    h.empezar()
    assert h.evs("reunion-estado")[-1]["copiloto"] == "sin_copiloto"


def test_copiloto_que_abre_tras_terminar_se_cierra(h):
    r = go(h.store.empezar("pc1", [], True))
    abrir = h.pend.pop(0)
    go(h.store.terminar(r["reunion"]))
    go(abrir)
    assert h.puente.cerrados == ["w1:p1"]
    assert h.store.snapshot() == {}


# ---- Mostrame

FOTO = {"foto": 42, "ventana": {"titulo": "Pedidos - Chrome", "proceso": "chrome.exe"},
        "controles": [{"n": 1, "tipo": "boton", "nombre": "Guardar"}]}
IMG = Imagen(b"\x89PNG-falso", "png", 1568, 980)


def _listo(h, device="pc1"):
    return h.empezar(device)


def _mostrar(h, rid, pregunta="¿cómo exporto esto?", device="pc1", foto=FOTO, imagen=IMG):
    return go(h.store.mostrar(rid, device, pregunta, foto, imagen))


def test_mostrar_crea_linea_y_pregunta(h):
    rid = _listo(h)
    r = _mostrar(h, rid)
    assert r == {"linea": "l1", "estado": "buscando"}
    assert h.evs("reunion-linea")[-1] == {"reunion": rid, "id": "l1", "texto": "¿cómo exporto esto?",
                                          "tipo": "mostrar"}
    assert h.fotos == [("w1:p1", 42, 1568, 980)]
    assert h.puente.capturas == [(IMG.datos, "png", "1. boton: Guardar")]
    pane, msg_id, texto = h.puente.preguntas[-1]
    assert (pane, msg_id) == ("w1:p1", "l1") and texto.startswith("MOSTRAR<l1>|¿cómo exporto esto?|")
    assert h.evs("reunion-respuesta")[-1]["estado"] == "buscando"


def test_mostrar_sin_pregunta_usa_la_charla(h):
    rid = _listo(h)
    h.store.texto(rid, "pc1", "primero. Lo último que se dijo")
    r = _mostrar(h, rid, pregunta="")
    assert h.evs("reunion-linea")[-1]["texto"] == "Mostrame"
    assert "Lo último que se dijo" in h.puente.preguntas[-1][2]
    assert r["linea"] == "l1"


def test_mostrar_ocupado_es_409(h):
    rid = _listo(h)
    _mostrar(h, rid)
    with pytest.raises(ReunionError) as e:
        _mostrar(h, rid)
    assert e.value.status == 409 and e.value.mensaje == "El Copiloto está ocupado."
    assert len(h.fotos) == 1


def test_mostrar_con_pregunta_en_curso_es_409(h):
    rid, lid = _con_linea(h)
    go(h.store.tocar(rid, lid))
    with pytest.raises(ReunionError) as e:
        _mostrar(h, rid)
    assert e.value.status == 409


def test_mostrar_device_ajeno_o_sin_copiloto_es_409(h):
    rid = _listo(h)
    with pytest.raises(ReunionError) as e:
        _mostrar(h, rid, device="otra")
    assert e.value.status == 409
    h2 = H(h.dir.parent / "otro")
    h2.puente.pane = ""
    rid2 = h2.empezar()
    with pytest.raises(ReunionError) as e:
        go(h2.store.mostrar(rid2, "pc1", "hola", FOTO, IMG))
    assert e.value.status == 409 and e.value.mensaje == "El Copiloto no está listo."


def test_mostrar_sin_pregunta_ni_charla_es_422(h):
    rid = _listo(h)
    with pytest.raises(ReunionError) as e:
        _mostrar(h, rid, pregunta="  ")
    assert e.value.status == 422 and h.evs("reunion-linea") == [] and h.fotos == []


def test_mostrar_reunion_terminada_es_409(h):
    rid = _listo(h)
    go(h.store.terminar(rid))
    with pytest.raises(ReunionError):
        _mostrar(h, rid)


def test_mostrar_falla_al_guardar_deja_la_linea_en_error(h):
    rid = _listo(h)
    h.puente.falla_captura = True
    assert _mostrar(h, rid)["estado"] == "error"
    assert h.evs("reunion-respuesta")[-1]["estado"] == "error"
    h.puente.falla_captura = False
    assert _mostrar(h, rid)["estado"] == "buscando"


def test_mostrar_borra_la_captura_si_la_reunion_termina_mientras_se_guarda(h):
    rid = _listo(h)
    h.puente.alg_en_guardar = lambda: h.store.terminar(rid)
    _mostrar(h, rid)
    assert h.puente.borrados == [Path("/cap/cap-1.png"), Path("/cap/cap-1.controles.txt")]
    assert not any(p[2].startswith("MOSTRAR") for p in h.puente.preguntas)


def test_mostrar_falla_al_preguntar_deja_la_linea_en_error(h):
    rid = _listo(h)
    h.puente.falla = True
    assert _mostrar(h, rid)["estado"] == "error"
    h.puente.falla = False
    assert _mostrar(h, rid)["estado"] == "buscando"


def test_mostrar_al_stop_responde_la_linea(h):
    rid = _listo(h)
    _mostrar(h, rid)
    h.store.al_stop("w1:p1", '```copiloto\n{"linea": "l1", "texto": "Tocá Guardar", "archivos": []}\n```')
    assert h.evs("reunion-respuesta")[-1] == {"reunion": rid, "linea": "l1", "estado": "lista",
                                              "texto": "Sí, en el módulo X", "archivos": ["a.php"]}
    assert _mostrar(h, rid)["estado"] == "buscando"


def test_resumen_no_lleva_captura(h):
    rid = _listo(h)
    _mostrar(h, rid)
    h.puente.bloque = {"texto": "ok", "archivos": ["/data/reunion-copiloto/capturas/cap-1.png", "a.php"]}
    h.store.al_stop("w1:p1", '```copiloto\n{"linea": "l1", "texto": "ok", "archivos": []}\n```')
    assert "capturas/" not in json.dumps(h.evs("reunion-respuesta")[-1])
    assert h.evs("reunion-respuesta")[-1]["archivos"] == ["a.php"]
    diario = h.jfile(rid).read_text()
    assert "capturas/" not in diario and ".png" not in diario
    datos = h.store._datos(h.store._r, "terminada", {"titulo": "t", "resumen": [], "pendientes": []}, False, 2000.0)
    assert "capturas/" not in json.dumps(datos) and ".png" not in json.dumps(datos)


def test_tocar_linea_mostrar_es_409(h):
    rid = _listo(h)
    _mostrar(h, rid)
    h.store.al_stop("w1:p1", "sin bloque")
    with pytest.raises(ReunionError) as e:
        go(h.store.tocar(rid, "l1"))
    assert e.value.status == 409 and e.value.mensaje == "Volvé a tocar Mostrame."


def test_estado_informa_ocupado(h):
    rid = _listo(h)
    assert h.evs("reunion-estado")[-1]["ocupado"] is False
    _mostrar(h, rid)
    assert h.evs("reunion-estado")[-1]["ocupado"] is True
    h.store.al_stop("w1:p1", "sin bloque")
    assert h.evs("reunion-estado")[-1]["ocupado"] is False
    assert h.store.snapshot()["ocupado"] is False


# ---- descartar y anotar

def _dos_lineas(h):
    rid, l1 = _con_linea(h)
    h.detector.respuestas = [[{"tipo": "requerimiento", "texto": "Mandar el informe a Marta"}]]
    h.store.texto(rid, "pc1", "más")
    h.disparar(h.activos()[0])
    return rid, l1, h.evs("reunion-linea")[-1]["id"]


def test_descartar_saca_la_linea_del_snapshot_y_avisa(h):
    rid, l1, l2 = _dos_lineas(h)
    assert go(h.store.descartar(rid, l1)) == "descartada"
    assert [x["id"] for x in h.store.snapshot()["lineas"]] == [l2]
    assert h.evs("reunion-descartada") == [{"reunion": rid, "linea": l1}]


def test_descartar_es_idempotente(h):
    rid, l1 = _con_linea(h)
    go(h.store.descartar(rid, l1))
    assert go(h.store.descartar(rid, l1)) == "descartada"
    assert len(h.evs("reunion-descartada")) == 1


def test_descartar_linea_inexistente_es_404(h):
    rid, _ = _con_linea(h)
    with pytest.raises(ReunionError) as e:
        go(h.store.descartar(rid, "l99"))
    assert e.value.status == 404


def test_descartar_linea_buscando_es_409(h):
    rid, l1 = _con_linea(h)
    go(h.store.tocar(rid, l1))
    with pytest.raises(ReunionError) as e:
        go(h.store.descartar(rid, l1))
    assert e.value.status == 409 and "buscando" in e.value.mensaje
    assert [x["id"] for x in h.store.snapshot()["lineas"]] == [l1]


def test_descartar_linea_en_cola_la_saca_de_la_cola(h):
    rid, l1, l2 = _dos_lineas(h)
    go(h.store.tocar(rid, l1))
    assert go(h.store.tocar(rid, l2)) == "en_cola"
    go(h.store.descartar(rid, l2))
    assert list(h.store._r.cola) == []
    h.store.al_stop("w1:p1", '```copiloto\n{"linea": "%s", "texto": "ok", "archivos": []}\n```' % l1)
    h.drenar()
    assert len(h.puente.preguntas) == 1


def test_descartar_linea_descartada_no_se_puede_tocar(h):
    rid, l1 = _con_linea(h)
    go(h.store.descartar(rid, l1))
    with pytest.raises(ReunionError) as e:
        go(h.store.tocar(rid, l1))
    assert e.value.status == 409


def test_descartada_no_entra_en_el_resumen(h):
    rid, l1, l2 = _dos_lineas(h)
    go(h.store.tocar(rid, l1))
    h.store.al_stop("w1:p1", '```copiloto\n{"linea": "%s", "texto": "ok", "archivos": []}\n```' % l1)
    go(h.store.descartar(rid, l1))
    assert h.store._tocadas(h.store._r) == []
    go(h.store.terminar(rid))
    assert h.bib.guardados[0][0]["tocadas"] == []


def test_descartar_se_recupera_del_diario(h):
    rid, l1, l2 = _dos_lineas(h)
    go(h.store.descartar(rid, l1))
    r = h.store._leer_diario(h.jfile(rid))
    assert next(x for x in r.lineas if x.id == l1).descartada is True
    assert next(x for x in r.lineas if x.id == l2).descartada is False


def test_anotar_pregunta_crea_apunte_con_origen(h):
    rid, l1 = _con_linea(h)
    assert go(h.store.anotar(rid, l1)) == {"nota": "n_1"}
    nota = h.notas.creadas[0]
    assert nota["tipo"] == "apunte" and nota["texto"] == "¿Hay reembolsos parciales?"
    assert nota["origen"]["nombre"].startswith("Reunión de las ")
    assert h.evs("reunion-anotada") == [{"reunion": rid, "linea": l1, "nota": "n_1"}]
    assert h.store.snapshot()["lineas"][0]["nota"] == "n_1"
    assert h.puente.preguntas == []


def test_anotar_requerimiento_crea_recordatorio(h):
    rid, l1, l2 = _dos_lineas(h)
    go(h.store.anotar(rid, l2))
    assert h.notas.creadas[0]["tipo"] == "recordatorio"


def _con_clave(h):
    rid, l1 = _con_linea(h)
    h.detector.respuestas = [[{"tipo": "clave", "texto": "McDonald's tiene más de 36.000 locales"}]]
    h.store.texto(rid, "pc1", "más")
    h.disparar(h.activos()[0])
    return rid, h.evs("reunion-linea")[-1]


def test_detecta_linea_clave(h):
    rid, lin = _con_clave(h)
    assert lin["tipo"] == "clave" and lin["texto"] == "McDonald's tiene más de 36.000 locales"


def _detectar_items(h, items):
    rid = h.empezar()
    h.detector.respuestas = [items]
    h.store.texto(rid, "pc1", "x" * 2000)
    h.disparar(h.activos()[0])
    return [(x["tipo"], x["texto"]) for x in h.evs("reunion-linea")]


def test_como_mucho_dos_clave_por_llamada(h):
    got = _detectar_items(h, [{"tipo": "clave", "texto": t} for t in ("uno alfa", "dos beta", "tres gamma")])
    assert got == [("clave", "uno alfa"), ("clave", "dos beta")]


def test_las_preguntas_van_antes_que_los_clave(h):
    got = _detectar_items(h, [{"tipo": "clave", "texto": "dato uno"}, {"tipo": "clave", "texto": "dato dos"},
                              {"tipo": "pregunta", "texto": "¿Dónde se calcula el precio?"}])
    assert got[0] == ("pregunta", "¿Dónde se calcula el precio?") and len(got) == 3


def test_clave_no_usa_las_ultimas_plazas_del_minuto(h):
    rid = h.empezar()
    h.store._r.recientes.extend([h.store._clock()] * (R.LINEAS_POR_MIN - R.PLAZAS_RESERVADAS))
    h.detector.respuestas = [[{"tipo": "clave", "texto": "dato"}, {"tipo": "pregunta", "texto": "¿Y el stock?"}]]
    h.store.texto(rid, "pc1", "x" * 2000)
    h.disparar(h.activos()[0])
    assert [x["tipo"] for x in h.evs("reunion-linea")] == ["pregunta"]


def test_clave_tiene_tope_por_reunion(h):
    rid = h.empezar()
    for i in range(R.CLAVE_MAX):
        h.store._crear_linea(h.store._r, f"dato número {i} distinto", "clave")
    h.detector.respuestas = [[{"tipo": "clave", "texto": "otro dato nuevo"}, {"tipo": "pregunta", "texto": "¿Y el stock?"}]]
    h.store.texto(rid, "pc1", "x" * 2000)
    h.disparar(h.activos()[0])
    assert h.evs("reunion-linea")[-1]["tipo"] == "pregunta"
    assert sum(1 for x in h.store._r.lineas if x.tipo == "clave") == R.CLAVE_MAX


def test_tocar_linea_clave_es_409_y_no_pregunta(h):
    rid, lin = _con_clave(h)
    with pytest.raises(ReunionError) as e:
        go(h.store.tocar(rid, lin["id"]))
    assert e.value.status == 409 and e.value.mensaje == "Un punto clave no se le pregunta al Copiloto."
    assert h.puente.preguntas == []


def test_anotar_clave_crea_apunte(h):
    rid, lin = _con_clave(h)
    go(h.store.anotar(rid, lin["id"]))
    assert h.notas.creadas[0]["tipo"] == "apunte"


def test_clave_se_recupera_del_diario(h):
    rid, lin = _con_clave(h)
    r = h.store._leer_diario(h.jfile(rid))
    assert next(x for x in r.lineas if x.id == lin["id"]).tipo == "clave"


def test_anotar_dos_veces_no_duplica(h):
    rid, l1 = _con_linea(h)
    go(h.store.anotar(rid, l1))
    assert go(h.store.anotar(rid, l1)) == {"nota": "n_1"}
    assert len(h.notas.creadas) == 1 and len(h.evs("reunion-anotada")) == 1


def test_anotar_se_recupera_del_diario_y_la_linea_sigue(h):
    rid, l1 = _con_linea(h)
    go(h.store.anotar(rid, l1))
    r = h.store._leer_diario(h.jfile(rid))
    assert r.lineas[0].nota_id == "n_1" and r.lineas[0].descartada is False


def test_anotar_linea_mostrar_es_409(h):
    rid = _listo(h)
    _mostrar(h, rid)
    with pytest.raises(ReunionError) as e:
        go(h.store.anotar(rid, "l1"))
    assert e.value.status == 409


def test_anotar_descartada_es_409(h):
    rid, l1 = _con_linea(h)
    go(h.store.descartar(rid, l1))
    with pytest.raises(ReunionError) as e:
        go(h.store.anotar(rid, l1))
    assert e.value.status == 409


def test_anotar_con_notas_caidas_es_503(h):
    from orquestador.notas import NotasNoDisponibles
    rid, l1 = _con_linea(h)
    h.notas.falla = NotasNoDisponibles()
    with pytest.raises(ReunionError) as e:
        go(h.store.anotar(rid, l1))
    assert e.value.status == 503
    assert h.store.snapshot()["lineas"][0].get("nota") is None


# ---- guardar en la memoria de trabajo

def _anotada(h):
    rid, l1 = _con_linea(h)
    go(h.store.anotar(rid, l1))
    return rid, l1


def test_memoria_guarda_la_linea_anotada_como_dicha_sin_verificar(h):
    rid, l1 = _anotada(h)
    assert go(h.store.guardar_en_memoria(rid, l1)) == {"memoria": True}
    titulo, contenido = h.memoria.guardados[0]
    assert titulo.startswith("Reunión ") and "¿Hay reembolsos parciales?" in titulo
    assert contenido.startswith("Dicho en la reunión de las ")
    assert "(sin verificar): ¿Hay reembolsos parciales?" in contenido
    assert h.evs("reunion-memoria") == [{"reunion": rid, "linea": l1}]
    assert h.store.snapshot()["lineas"][0]["memoria"] is True


def test_memoria_incluye_la_respuesta_del_copiloto_marcada(h):
    rid, l1 = _con_linea(h)
    go(h.store.tocar(rid, l1))
    h.store.al_stop("w1:p1", '```copiloto\n{"linea": "%s", "texto": "Sí, hay parciales", "archivos": []}\n```' % l1)
    go(h.store.anotar(rid, l1))
    go(h.store.guardar_en_memoria(rid, l1))
    assert "\nRespuesta del Copiloto (sin verificar): " in h.memoria.guardados[0][1]


def test_memoria_dos_veces_guarda_una_sola(h):
    rid, l1 = _anotada(h)
    go(h.store.guardar_en_memoria(rid, l1))
    assert go(h.store.guardar_en_memoria(rid, l1)) == {"memoria": True}
    assert len(h.memoria.guardados) == 1 and len(h.evs("reunion-memoria")) == 1


def test_memoria_sin_nota_es_409(h):
    rid, l1 = _con_linea(h)
    with pytest.raises(ReunionError) as e:
        go(h.store.guardar_en_memoria(rid, l1))
    assert e.value.status == 409 and h.memoria.guardados == []


def test_memoria_descartada_es_409(h):
    rid, l1 = _anotada(h)
    go(h.store.descartar(rid, l1))
    with pytest.raises(ReunionError) as e:
        go(h.store.guardar_en_memoria(rid, l1))
    assert e.value.status == 409


def test_memoria_si_engram_falla_es_502_y_no_marca(h):
    rid, l1 = _anotada(h)
    h.memoria.falla = RuntimeError("boom")
    with pytest.raises(ReunionError) as e:
        go(h.store.guardar_en_memoria(rid, l1))
    assert e.value.status == 502 and "boom" not in e.value.mensaje
    assert h.store.snapshot()["lineas"][0]["memoria"] is False and h.evs("reunion-memoria") == []
    h.memoria.falla = None
    go(h.store.guardar_en_memoria(rid, l1))
    assert len(h.memoria.guardados) == 1


def test_memoria_desactivada_es_503_y_el_snapshot_lo_dice(h):
    rid, l1 = _anotada(h)
    h.store._guardar_memoria = None
    assert h.store.snapshot()["memoria_trabajo"] is False
    with pytest.raises(ReunionError) as e:
        go(h.store.guardar_en_memoria(rid, l1))
    assert e.value.status == 503


def test_memoria_se_recupera_del_diario(h):
    rid, l1 = _anotada(h)
    go(h.store.guardar_en_memoria(rid, l1))
    r = h.store._leer_diario(h.jfile(rid))
    assert r.lineas[0].memoria is True


def test_memoria_usa_la_hora_en_que_se_dijo_la_linea(h):
    rid, l1 = _anotada(h)
    r = h.store._r
    r.inicio = time.mktime((2026, 11, 24, 10, 0, 0, 0, 0, -1))
    r.lineas[0].ts = time.mktime((2026, 11, 24, 11, 42, 0, 0, 0, -1))
    go(h.store.guardar_en_memoria(rid, l1))
    titulo, contenido = h.memoria.guardados[0]
    assert contenido.startswith("Dicho en la reunión de las 11:42 ")
    assert titulo.startswith("Reunión 11:42: ")


def _vigia(h):
    return h.vigias


def test_sin_texto_a_los_2_minutos_avisa_y_el_primer_texto_lo_baja(h):
    rid = h.empezar()
    assert h.store.snapshot()["sin_texto"] is False
    assert len(_vigia(h)) == 1
    h.disparar(_vigia(h)[0])
    assert h.evs("reunion-estado")[-1]["sin_texto"] is True
    assert h.store.snapshot()["sin_texto"] is True
    h.store.texto(rid, "pc1", "hola a todos")
    assert h.evs("reunion-estado")[-1]["sin_texto"] is False


def test_sin_texto_no_avisa_si_ya_llego_texto(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "hola a todos")
    h.disparar(_vigia(h)[0])
    assert h.store.snapshot()["sin_texto"] is False


def test_sin_texto_no_avisa_si_la_reunion_ya_no_esta_escuchando(h):
    h.empezar()
    h.store._r.estado = "pausada"
    h.disparar(_vigia(h)[0])
    assert h.store.snapshot()["sin_texto"] is False


def test_terminar_cancela_la_vigia_de_sin_texto(h):
    rid = h.empezar()
    v = _vigia(h)[0]
    go(h.store.terminar(rid))
    assert v.cancelado


def test_limpiar_tema():
    assert R.limpiar_tema("  Plux\n en\tps9 \x07 ") == "Plux en ps9"
    assert R.limpiar_tema(" \n\x01 ") == ""


def _hasta_resumen(h, rid):
    h.store.texto(rid, "pc1", "hablamos del gateway")
    h.disparar(h.activos()[0])
    go(h.store.terminar(rid))
    h.drenar()


def test_empezar_guarda_tema_y_lo_pasa(h):
    rid = h.empezar(tema="  Plux\n en ps9 ")
    assert h.puente.temas == ["Plux en ps9"]
    _hasta_resumen(h, rid)
    assert h.detector.temas == ["Plux en ps9"] and h.detector.temas_resumen == ["Plux en ps9"]
    assert h.bib.guardados[0][0]["tema"] == "Plux en ps9"


def test_empezar_sin_tema(h):
    rid = h.empezar()
    assert h.puente.temas == [""]
    _hasta_resumen(h, rid)
    assert h.bib.guardados[0][0]["tema"] == ""


def test_tema_largo_se_recorta_en_el_store(h):
    h.empezar(tema="x" * 300)
    assert h.puente.temas == ["x" * R.TEMA_MAX]


def test_recupera_tema_del_diario(h):
    rid = h.empezar(tema="Plux")
    h.store.texto(rid, "pc1", "una tanda")
    h2 = H(h.dir.parent)
    h2.dir = h.dir
    h2.store.recuperar()
    h2.drenar()
    assert h2.bib.guardados[0][0]["tema"] == "Plux"


def test_recupera_diario_viejo_sin_tema(h):
    rid = h.empezar()
    ruta = h.jfile(rid)
    lineas = ruta.read_text().splitlines()
    ini = json.loads(lineas[0])
    ini.pop("tema", None)
    ruta.write_text("\n".join([json.dumps(ini)] + lineas[1:]) + "\n")
    h2 = H(h.dir.parent)
    h2.dir = h.dir
    h2.store.recuperar()
    h2.drenar()
    assert h2.bib.guardados[0][0]["tema"] == ""


def test_cortar_en_oracion():
    assert R.cortar_en_oracion("Hola. Hoy vemos reembolsos. Y despu") == 27
    assert R.cortar_en_oracion("sin puntos acá") == 14
    assert R.cortar_en_oracion("A. " + "x" * 50) == 53


def test_tramo_se_corta_en_la_ultima_oracion(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "Primero esto. Después aque")
    h.disparar(h.activos()[0])
    assert h.detector.llamadas[-1][0].endswith("esto.")
    assert h.store._r.ultimo_chars == len("Primero esto.")
    assert h.store._r.hay_nuevo is True


def test_el_resto_sin_punto_sale_en_la_vuelta_siguiente(h):
    rid = h.empezar()
    h.store.texto(rid, "pc1", "Primero esto. Después aque")
    h.disparar(h.activos()[0])
    h.disparar(h.activos()[0])
    assert h.detector.llamadas[-1][0].endswith("Después aque")
    assert h.store._r.hay_nuevo is False


def test_clave_parecida_a_otra_clave_se_descarta(h):
    got = _detectar_items(h, [{"tipo": "clave", "texto": "El precio subió 20 por ciento en marzo"},
                              {"tipo": "clave", "texto": "En marzo el precio aumentó un 20 por ciento"}])
    assert got == [("clave", "El precio subió 20 por ciento en marzo")]


def test_claves_con_otra_decision_no_se_descartan(h):
    got = _detectar_items(h, [{"tipo": "clave", "texto": "Se decidió usar Redis para la cache"},
                              {"tipo": "clave", "texto": "Se decidió usar Postgres para la base"}])
    assert len(got) == 2


def test_clave_con_otro_numero_no_se_descarta(h):
    got = _detectar_items(h, [{"tipo": "clave", "texto": "La entrega es el 5 de marzo"},
                              {"tipo": "clave", "texto": "La entrega es el 12 de marzo"}])
    assert len(got) == 2


def test_pregunta_parecida_a_una_clave_no_se_descarta(h):
    got = _detectar_items(h, [{"tipo": "clave", "texto": "El precio subió 20 por ciento en marzo"},
                              {"tipo": "pregunta", "texto": "¿Por qué subió el precio en marzo?"}])
    assert len(got) == 2
