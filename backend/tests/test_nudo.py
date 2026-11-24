from __future__ import annotations

import asyncio
import re

import pytest

from orquestador.nudo import (
    NudoError,
    NudoStore,
    nombre_sesion,
    validar_args,
    validar_respuesta,
    validar_texto,
)

MUESTRA = {
    "foto": 7,
    "ventana": {"titulo": "Editor", "proceso": "editor.exe"},
    "monitor": "0,0 1920x1080",
    "controles": [{"n": 1, "tipo": "boton", "nombre": "Guardar"}],
}


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Banco:
    def __init__(self, **kw):
        self.reloj = Reloj()
        self.ofrecidos = []
        self.contador = 0

        def token():
            self.contador += 1
            return f"tok{self.contador}"

        self.store = NudoStore(lambda cola, ev: self.ofrecidos.append((cola, ev)),
                               clock=self.reloj, token=token, **kw)

    def ultimo(self):
        return self.ofrecidos[-1][1][1]

    async def pedir_y_responder(self, sesion, nombre, op, args, resultado, device="dev"):
        tarea = asyncio.ensure_future(self.store.pedir(sesion, nombre, op, args))
        await asyncio.sleep(0)
        ev = self.ultimo()
        assert self.store.resolver(ev["id"], device, ev["token"], resultado)
        return await tarea


def banco(**kw):
    b = Banco(**kw)
    b.store.pc_conectada("dev", "q1")
    return b


def correr(coro):
    return asyncio.run(coro)


def test_sin_pc_conectada_falla_sin_pc():
    async def go():
        b = Banco()
        with pytest.raises(NudoError) as e:
            await b.store.pedir("g1:p1", "A", "controles", {})
        assert e.value.codigo == "sin_pc"
    correr(go())


def test_pedido_se_ofrece_solo_a_la_pc_mas_reciente():
    async def go():
        b = Banco()
        b.store.pc_conectada("devA", "q1")
        b.store.pc_conectada("devB", "q2")
        b.ofrecidos.clear()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        assert [c for c, _ in b.ofrecidos] == ["q2"]
        assert b.ofrecidos[0][1][0] == "nudo"
        assert b.ofrecidos[0][1][1]["op"] == "controles"
        assert b.ofrecidos[0][1][1]["sesion"] == "A"
        t.cancel()
    correr(go())


def test_resolver_con_token_correcto_devuelve_datos_sin_foto():
    async def go():
        b = banco()
        datos = await b.pedir_y_responder("g1:p1", "A", "controles", {}, MUESTRA)
        assert "foto" not in datos
        assert datos["controles"][0] == {"n": 1, "tipo": "boton", "nombre": "Guardar"}
        assert datos["monitor"] == "0,0 1920x1080"
    correr(go())


def test_id_del_pedido_es_urlsafe():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        assert re.fullmatch(r"[A-Za-z0-9_-]{8,64}", b.ultimo()["id"])
        t.cancel()
    correr(go())


def test_token_de_un_solo_uso():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        ev = b.ultimo()
        assert b.store.resolver(ev["id"], "dev", ev["token"], MUESTRA) is True
        assert b.store.resolver(ev["id"], "dev", ev["token"], MUESTRA) is False
        await t
    correr(go())


def test_resolver_con_otro_device_o_token_se_rechaza():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        ev = b.ultimo()
        assert b.store.resolver(ev["id"], "otro", ev["token"], MUESTRA) is False
        assert b.store.resolver(ev["id"], "dev", "x", MUESTRA) is False
        assert b.store.resolver("nada", "dev", ev["token"], MUESTRA) is False
        assert b.store.resolver(ev["id"], "dev", ev["token"], MUESTRA) is True
        await t
    correr(go())


def test_pedido_vence_sin_respuesta():
    async def go():
        b = banco(vence_s=0.05)
        with pytest.raises(NudoError) as e:
            await b.store.pedir("g1:p1", "A", "estado", {})
        assert e.value.codigo == "vencido"
    correr(go())


def test_vencimientos_por_operacion():
    b = banco()
    s = b.store
    assert s._vence_de("controles", {}) == 15.0
    assert s._vence_de("senalar", {"n": 1, "texto": "x", "esperar": 30}) == 45.0
    assert s._vence_de("senalar", {"n": 1, "texto": "x", "esperar": None}) == 10.0
    assert s._vence_de("marcar", {}) == 10.0


def test_senalar_usa_la_foto_de_la_sesion():
    async def go():
        b = banco()
        await b.pedir_y_responder("g1:p1", "A", "controles", {}, MUESTRA)
        r = await b.pedir_y_responder("g1:p1", "A", "senalar", {"n": 1, "texto": "x", "esperar": None},
                                      {"resultado": "ok"})
        assert r == {"resultado": "ok"}
        ev = [e for _, e in b.ofrecidos if e[1]["op"] == "senalar"][0][1]
        assert ev["args"]["foto"] == 7
        assert ev["args"]["n"] == 1
    correr(go())


def test_senalar_sin_controles_previos_es_foto_vieja_sin_ir_a_la_pc():
    async def go():
        b = banco()
        b.ofrecidos.clear()
        with pytest.raises(NudoError) as e:
            await b.store.pedir("g1:p1", "A", "senalar", {"n": 1, "texto": "x", "esperar": None})
        assert e.value.codigo == "foto_vieja"
        assert b.ofrecidos == []
    correr(go())


def test_marcar_lleva_la_foto():
    async def go():
        b = banco()
        await b.pedir_y_responder("g1:p1", "A", "controles", {}, MUESTRA)
        r = await b.pedir_y_responder("g1:p1", "A", "marcar", {"marcas": [{"n": 1, "etiqueta": "a"}]}, "ok")
        assert r == {"resultado": "ok"}
        assert b.ultimo()["args"]["foto"] == 7
        assert b.store.dueno() == ("g1:p1", "A")
    correr(go())


async def _duena(b):
    await b.pedir_y_responder("g1:p1", "Sesión A", "controles", {}, MUESTRA)
    await b.pedir_y_responder("g1:p1", "Sesión A", "senalar", {"n": 1, "texto": "x", "esperar": None}, "ok")


def test_otra_sesion_recibe_ocupado_con_nombre():
    async def go():
        b = banco()
        await _duena(b)
        with pytest.raises(NudoError) as e:
            await b.store.pedir("g1:p2", "Sesión B", "controles", {})
        assert e.value.codigo == "ocupado"
        assert "Sesión A" in e.value.mensaje
    correr(go())


def test_estado_anda_aunque_haya_duena():
    async def go():
        b = banco()
        await _duena(b)
        r = await b.pedir_y_responder("g1:p2", "B", "estado", {}, {"prendido": True, "se_ve_al_compartir": False})
        assert r == {"prendido": True, "se_ve_al_compartir": False}
    correr(go())


def test_limpiar_de_otra_sesion_no_borra_y_no_llega_a_la_pc():
    async def go():
        b = banco()
        await _duena(b)
        antes = len(b.ofrecidos)
        r = await b.store.pedir("g1:p2", "B", "limpiar", {})
        assert r == {"resultado": "ok", "nada": True}
        assert len(b.ofrecidos) == antes
        assert b.store.dueno() == ("g1:p1", "Sesión A")
    correr(go())


def test_limpiar_de_la_duena_libera():
    async def go():
        b = banco()
        await _duena(b)
        r = await b.pedir_y_responder("g1:p1", "Sesión A", "limpiar", {}, "ok")
        assert r == {"resultado": "ok"}
        assert b.store.dueno() is None
    correr(go())


def test_salir_libera_al_dueno():
    async def go():
        b = banco()
        await _duena(b)
        b.store.salir("dev")
        assert b.store.dueno() is None
    correr(go())


def test_dueno_se_libera_tras_120s_sin_actividad_y_limpia_la_pc():
    async def go():
        b = banco()
        await _duena(b)
        antes = len(b.ofrecidos)
        b.reloj.t += 119.0
        assert b.store.dueno() is not None
        b.reloj.t += 1.1
        assert b.store.dueno() is None
        assert len(b.ofrecidos) == antes + 1
        cola, ev = b.ofrecidos[-1]
        assert cola == "q1" and ev[0] == "nudo" and ev[1]["op"] == "limpiar"
        assert b.store.dueno() is None
        assert len(b.ofrecidos) == antes + 1
    correr(go())


def test_la_guia_activa_no_expira_por_inactividad():
    async def go():
        b = banco(es_guia=lambda s: s == "g1:p1")
        await _duena(b)
        assert b.store.dueno() == ("g1:p1", "Sesión A")
        b.reloj.t += 600
        assert b.store.dueno() == ("g1:p1", "Sesión A")
        b.store.soltar(limpiar=True)
        assert b.store.dueno() is None
        assert b.ofrecidos[-1][1][1]["op"] == "limpiar"
    correr(go())


def test_pedido_pendiente_de_la_duena_cuenta_como_actividad():
    async def go():
        b = banco()
        await _duena(b)
        t = asyncio.ensure_future(
            b.store.pedir("g1:p1", "Sesión A", "senalar", {"n": 1, "texto": "x", "esperar": 300}))
        await asyncio.sleep(0)
        b.reloj.t += 200
        assert b.store.dueno() is not None
        ev = b.ultimo()
        b.store.resolver(ev["id"], "dev", ev["token"], "listo")
        assert await t == {"resultado": "listo"}
        b.reloj.t += 100
        assert b.store.dueno() is not None
        b.reloj.t += 21
        assert b.store.dueno() is None
    correr(go())


def test_un_pedido_a_la_vez_de_la_misma_sesion_da_en_curso():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        with pytest.raises(NudoError) as e:
            await b.store.pedir("g1:p1", "A", "controles", {})
        assert e.value.codigo == "en_curso"
        t.cancel()
    correr(go())


def test_pedido_en_curso_de_otra_sesion_da_ocupado_con_nombre():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "Sesión A", "controles", {}))
        await asyncio.sleep(0)
        with pytest.raises(NudoError) as e:
            await b.store.pedir("g1:p2", "B", "controles", {})
        assert e.value.codigo == "ocupado"
        assert e.value.mensaje == "Ocupado por Sesión A."
        t.cancel()
    correr(go())


def test_estado_anda_aunque_haya_pedido_en_curso_de_otra_sesion():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        t2 = asyncio.ensure_future(b.store.pedir("g1:p2", "B", "estado", {}))
        await asyncio.sleep(0)
        ev = b.ultimo()
        assert ev["op"] == "estado"
        assert b.store.resolver(ev["id"], "dev", ev["token"], {"prendido": True, "se_ve_al_compartir": False})
        assert await t2 == {"prendido": True, "se_ve_al_compartir": False}
        t.cancel()
    correr(go())


def test_pc_conectada_sin_duena_ni_pedido_manda_limpiar_a_la_pc():
    b = Banco()
    b.store.pc_conectada("dev", "q1")
    assert len(b.ofrecidos) == 1
    cola, (canal, ev) = b.ofrecidos[0]
    assert cola == "q1" and canal == "nudo"
    assert ev["op"] == "limpiar" and ev["sesion"] == ""


def test_pc_conectada_con_duena_no_manda_limpiar():
    async def go():
        b = banco()
        await _duena(b)
        antes = len(b.ofrecidos)
        b.store.pc_conectada("dev", "q2")
        assert len(b.ofrecidos) == antes
    correr(go())


def test_pc_conectada_con_pedido_en_curso_no_manda_limpiar():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        antes = len(b.ofrecidos)
        b.store.pc_conectada("dev", "q2")
        assert len(b.ofrecidos) == antes
        t.cancel()
    correr(go())


def test_nombre_de_respaldo_se_recorta_a_60():
    largo = "a" * 80
    assert nombre_sesion(None, largo) == "a" * 60


def test_pc_desconectada_resuelve_pendiente_con_sin_pc():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        b.store.pc_desconectada("dev", "q1")
        with pytest.raises(NudoError) as e:
            await t
        assert e.value.codigo == "sin_pc"
        assert b.store.pc_objetivo() is None
    correr(go())


def test_reconexion_del_mismo_device_no_pierde_la_pc():
    async def go():
        b = banco()
        b.store.pc_conectada("dev", "q2")
        b.store.pc_desconectada("dev", "q1")
        assert b.store.pc_objetivo() == "dev"
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        assert b.ofrecidos[-1][0] == "q2"
        ev = b.ultimo()
        b.store.resolver(ev["id"], "dev", ev["token"], MUESTRA)
        await t
    correr(go())


def test_pc_desconectada_de_otro_device_no_toca_el_pendiente():
    async def go():
        b = banco()
        b.store.pc_conectada("otra", "q9")
        b.store.pc_conectada("dev", "q2")
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        b.store.pc_desconectada("otra", "q9")
        ev = b.ultimo()
        assert b.store.resolver(ev["id"], "dev", ev["token"], MUESTRA)
        await t
    correr(go())


def test_cancelar_libera_el_pedido():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        b.store.cancelar(b.ultimo()["id"])
        with pytest.raises(NudoError):
            await t
        d = await b.pedir_y_responder("g1:p1", "A", "controles", {}, MUESTRA)
        assert d["controles"]
    correr(go())


def test_error_de_la_pc_se_propaga():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        ev = b.ultimo()
        b.store.resolver(ev["id"], "dev", ev["token"], {"error": "apagado"})
        with pytest.raises(NudoError) as e:
            await t
        assert e.value.codigo == "apagado"
    correr(go())


def test_respuesta_invalida_de_la_pc_es_fallo_pc():
    async def go():
        b = banco()
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "controles", {}))
        await asyncio.sleep(0)
        ev = b.ultimo()
        assert b.store.resolver(ev["id"], "dev", ev["token"], {"basura": 1}) is True
        with pytest.raises(NudoError) as e:
            await t
        assert e.value.codigo == "fallo_pc"
    correr(go())


def test_error_de_senalar_no_deja_dueno():
    async def go():
        b = banco()
        await b.pedir_y_responder("g1:p1", "A", "controles", {}, MUESTRA)
        t = asyncio.ensure_future(
            b.store.pedir("g1:p1", "A", "senalar", {"n": 9, "texto": "x", "esperar": None}))
        await asyncio.sleep(0)
        ev = b.ultimo()
        b.store.resolver(ev["id"], "dev", ev["token"], {"error": "sin_control"})
        with pytest.raises(NudoError):
            await t
        assert b.store.dueno() is None
    correr(go())


def test_resultado_salir_libera_al_dueno():
    async def go():
        b = banco()
        await _duena(b)
        t = asyncio.ensure_future(
            b.store.pedir("g1:p1", "Sesión A", "senalar", {"n": 1, "texto": "x", "esperar": 30}))
        await asyncio.sleep(0)
        ev = b.ultimo()
        b.store.resolver(ev["id"], "dev", ev["token"], "salir")
        assert await t == {"resultado": "salir"}
        assert b.store.dueno() is None
    correr(go())


def test_texto_con_salto_de_linea_se_rechaza():
    with pytest.raises(ValueError, match="una sola línea"):
        validar_texto("a\nb", 120)


def test_texto_largo_se_rechaza():
    assert validar_texto("á" * 120, 120) == "á" * 120
    with pytest.raises(ValueError):
        validar_texto("á" * 121, 120)
    with pytest.raises(ValueError):
        validar_texto("", 120)
    with pytest.raises(ValueError):
        validar_texto(5, 120)


def test_validar_args_marcar():
    ok = validar_args("marcar", {"marcas": [{"n": 1, "etiqueta": "a"}]})
    assert ok == {"marcas": [{"n": 1, "etiqueta": "a"}]}
    with pytest.raises(ValueError):
        validar_args("marcar", {"marcas": [{"n": i + 1, "etiqueta": "a"} for i in range(9)]})
    with pytest.raises(ValueError):
        validar_args("marcar", {"marcas": [{"n": 1, "etiqueta": "x" * 41}]})
    with pytest.raises(ValueError):
        validar_args("marcar", {"marcas": [{"n": 0, "etiqueta": "a"}]})
    with pytest.raises(ValueError):
        validar_args("marcar", {"marcas": []})


def test_validar_args_esperar():
    assert validar_args("senalar", {"n": 3, "texto": "x", "esperar": 0})["esperar"] == 120
    assert validar_args("senalar", {"n": 3, "texto": "x"})["esperar"] is None
    assert validar_args("senalar", {"n": 3, "texto": "x", "esperar": 600})["esperar"] == 600
    with pytest.raises(ValueError):
        validar_args("senalar", {"n": 3, "texto": "x", "esperar": 601})
    with pytest.raises(ValueError):
        validar_args("senalar", {"n": 0, "texto": "x"})
    with pytest.raises(ValueError):
        validar_args("senalar", {"n": 1, "texto": "a\nb"})


def test_validar_args_sin_args_y_op_desconocida():
    assert validar_args("controles", {}) == {}
    with pytest.raises(ValueError):
        validar_args("borrar", {})


def test_valida_lista_de_controles():
    r = validar_respuesta("controles", MUESTRA)
    assert r["foto"] == 7
    malo = dict(MUESTRA)
    for c in (
        [{"n": i + 1, "tipo": "boton", "nombre": "a"} for i in range(151)],
        [{"n": 1, "tipo": "imagen", "nombre": "a"}],
        [{"n": 1, "tipo": "boton", "nombre": "a", "valor": "secreto"}],
    ):
        with pytest.raises(ValueError):
            validar_respuesta("controles", {**malo, "controles": c})


def test_resultado_de_senalar_solo_valores_conocidos():
    for v in ("ok", "listo", "usado", "salir", "vencido"):
        assert validar_respuesta("senalar", v) == {"resultado": v}
    with pytest.raises(ValueError):
        validar_respuesta("senalar", "otro")
    with pytest.raises(ValueError):
        validar_respuesta("senalar", {"error": "raro"})
    assert validar_respuesta("senalar", {"error": "apagado"}) == {"error": "apagado"}


def test_nombre_sesion_del_tablero():
    board = {"workspaces": [{"tabs": [{"agents": [{"pane_id": "w1:p1", "title": "Mi sesión"}]}]}]}
    assert nombre_sesion(board, "w1:p1") == "Mi sesión"
    assert nombre_sesion(None, "w1:p1") == "w1:p1"
    assert nombre_sesion(board, "w9:p9") == "w9:p9"


def test_nombre_sesion_limpia_controles_y_trunca():
    board = {"workspaces": [{"tabs": [{"agents": [
        {"pane_id": "a", "title": "x\x07y\nz" + "w" * 100},
        {"pane_id": "b", "title": "\x07\n"},
    ]}]}]}
    n = nombre_sesion(board, "a")
    assert len(n) == 60 and "\x07" not in n and "\n" not in n
    assert nombre_sesion(board, "b") == "b"


def test_nombres_de_la_pc_con_marcas_invisibles_se_limpian():
    m = {**MUESTRA, "ventana": {"titulo": "Ed\u200eitor\u200f", "proceso": "e.exe"},
         "controles": [{"n": 1, "tipo": "boton", "nombre": "\u200eGuardar\u200f todo"}]}
    r = validar_respuesta("controles", m)
    assert r["controles"][0]["nombre"] == "Guardar todo"
    assert r["ventana"]["titulo"] == "Ed itor"


def test_foto_vence_a_los_5_minutos_y_se_poda():
    async def go():
        b = banco()
        await b.pedir_y_responder("g1:p1", "A", "controles", {}, MUESTRA)
        b.reloj.t += 301
        with pytest.raises(NudoError) as e:
            await b.store.pedir("g1:p1", "A", "senalar", {"n": 1, "texto": "x", "esperar": None})
        assert e.value.codigo == "foto_vieja"
        assert b.store._fotos == {}
    correr(go())


def test_sin_pc_se_libera_el_dueno():
    async def go():
        b = banco()
        await _duena(b)
        b.store.pc_desconectada("dev", "q1")
        assert b.store.dueno() is None
        assert b.store._fotos == {}
    correr(go())


def test_cliente_que_corta_un_senalar_deja_a_la_sesion_como_duena():
    async def run():
        b = banco()
        await b.pedir_y_responder("g1:p1", "A", "controles", {}, MUESTRA)
        t = asyncio.ensure_future(b.store.pedir("g1:p1", "A", "senalar", {"n": 1, "texto": "x", "esperar": 60}))
        await asyncio.sleep(0)
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)
        assert b.store.dueno() == ("g1:p1", "A")
        n = len(b.ofrecidos)
        b.reloj.t += 130
        assert b.store.dueno() is None
        assert b.ofrecidos[n][1][1]["op"] == "limpiar"

    asyncio.run(run())


def test_validar_args_zonas():
    z = {"x": 1, "y": 2, "ancho": 3, "alto": 4}
    assert validar_args("senalar_zona", {"zona": z, "texto": " Acá "}) == {"zona": z, "texto": "Acá"}
    assert validar_args("marcar_zonas", {"zonas": [dict(z, etiqueta="Menú")]}) == {
        "zonas": [dict(z, etiqueta="Menú")]}
    malos = [dict(z, x=-1), dict(z, y=-1), dict(z, ancho=0), dict(z, alto=0), dict(z, x=True), dict(z, ancho=1.5),
             {"x": 1, "y": 2, "ancho": 3}]
    for m in malos:
        with pytest.raises(ValueError):
            validar_args("senalar_zona", {"zona": m, "texto": "a"})
    with pytest.raises(ValueError):
        validar_args("senalar_zona", {"zona": z, "texto": "x" * 121})
    with pytest.raises(ValueError):
        validar_args("senalar_zona", {"zona": z, "texto": "a\nb"})
    with pytest.raises(ValueError):
        validar_args("marcar_zonas", {"zonas": [dict(z, etiqueta="e")] * 9})
    with pytest.raises(ValueError):
        validar_args("marcar_zonas", {"zonas": []})
    with pytest.raises(ValueError):
        validar_args("marcar_zonas", {"zonas": [dict(z, etiqueta="e" * 41)]})
    with pytest.raises(ValueError):
        validar_args("marcar_zonas", {"zonas": [dict(z, ancho=0, etiqueta="e")]})


ZONA = {"x": 10, "y": 20, "ancho": 200, "alto": 40}


def test_registrar_foto_habilita_senalar_por_numero_y_zona():
    async def go():
        b = banco()
        b.store.registrar_foto("w1:p1", 42, 1568, 980)
        await b.pedir_y_responder("w1:p1", "A", "senalar", {"n": 1, "texto": "x", "esperar": None},
                                  {"resultado": "ok"})
        assert b.ultimo()["args"]["foto"] == 42
        await b.pedir_y_responder("w1:p1", "A", "senalar_zona", {"zona": ZONA, "texto": "x"}, "ok")
        assert b.ultimo()["args"]["foto"] == 42
        assert b.ultimo()["args"]["zona"] == ZONA
        assert b.store.dueno() == ("w1:p1", "A")
    correr(go())


def test_registrar_foto_invalida():
    b = banco()
    for args in [("", 1, 1, 1), ("w1:p1", -1, 1, 1), ("w1:p1", True, 1, 1), ("w1:p1", 1, 0, 1), ("w1:p1", 1, 1, 0),
                 ("w 1", 1, 1, 1)]:
        with pytest.raises(ValueError):
            b.store.registrar_foto(*args)


def test_zona_sin_captura_es_foto_vieja():
    async def go():
        b = banco()
        await b.pedir_y_responder("w1:p1", "A", "controles", {}, MUESTRA)
        b.ofrecidos.clear()
        with pytest.raises(NudoError) as e:
            await b.store.pedir("w1:p1", "A", "senalar_zona", {"zona": ZONA, "texto": "x"})
        assert e.value.codigo == "foto_vieja"
        assert b.ofrecidos == []
    correr(go())


def test_zona_fuera_de_la_captura_es_invalida():
    async def go():
        b = banco()
        b.store.registrar_foto("w1:p1", 42, 1568, 980)
        with pytest.raises(NudoError) as e:
            await b.store.pedir("w1:p1", "A", "senalar_zona",
                                {"zona": {"x": 1368, "y": 0, "ancho": 201, "alto": 5}, "texto": "x"})
        assert e.value.codigo == "invalido"
        assert "1568x980" in e.value.mensaje
        with pytest.raises(NudoError) as e:
            await b.store.pedir("w1:p1", "A", "marcar_zonas",
                                {"zonas": [dict(ZONA, etiqueta="a"), {"x": 0, "y": 976, "ancho": 5, "alto": 5,
                                                                      "etiqueta": "b"}]})
        assert e.value.codigo == "invalido"
        await b.pedir_y_responder("w1:p1", "A", "senalar_zona",
                                  {"zona": {"x": 1368, "y": 0, "ancho": 200, "alto": 980}, "texto": "x"}, "ok")
    correr(go())


def test_foto_registrada_vence_a_los_300s():
    async def go():
        b = banco()
        b.store.registrar_foto("w1:p1", 42, 1568, 980)
        b.reloj.t += 301
        with pytest.raises(NudoError) as e:
            await b.store.pedir("w1:p1", "A", "senalar_zona", {"zona": ZONA, "texto": "x"})
        assert e.value.codigo == "foto_vieja"
    correr(go())


def test_controles_exitoso_descarta_la_imagen():
    async def go():
        b = banco()
        b.store.registrar_foto("w1:p1", 42, 1568, 980)
        await b.pedir_y_responder("w1:p1", "A", "controles", {}, MUESTRA)
        with pytest.raises(NudoError) as e:
            await b.store.pedir("w1:p1", "A", "senalar_zona", {"zona": ZONA, "texto": "x"})
        assert e.value.codigo == "foto_vieja"
    correr(go())


def test_respuesta_zona_solo_ok():
    for op in ("senalar_zona", "marcar_zonas"):
        assert validar_respuesta(op, "ok") == {"resultado": "ok"}
        assert validar_respuesta(op, {"resultado": "ok"}) == {"resultado": "ok"}
        for malo in ("listo", "salir", 3, {"resultado": "usado"}):
            with pytest.raises(ValueError):
                validar_respuesta(op, malo)


def test_orden_de_la_guia_lleva_guia_true():
    async def go():
        b = banco(es_guia=lambda s: s == "w9:p1")
        b.store.registrar_foto("w9:p1", 42, 1568, 980)
        z = {"x": 1, "y": 1, "ancho": 10, "alto": 10}
        await b.pedir_y_responder("w9:p1", "G", "senalar_zona", {"zona": z, "texto": "x"}, {"resultado": "ok"})
        assert b.ultimo()["guia"] is True
    correr(go())


def test_orden_de_otra_sesion_no_lleva_guia():
    async def go():
        b = banco(es_guia=lambda s: False)
        b.store.registrar_foto("w9:p1", 42, 1568, 980)
        z = {"x": 1, "y": 1, "ancho": 10, "alto": 10}
        await b.pedir_y_responder("w9:p1", "G", "senalar_zona", {"zona": z, "texto": "x"}, {"resultado": "ok"})
        assert "guia" not in b.ultimo()
        c = banco(es_guia=lambda s: True)
        await c.pedir_y_responder("w9:p1", "G", "controles", {}, MUESTRA)
        assert "guia" not in c.ultimo()
    correr(go())
