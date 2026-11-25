import stat
from datetime import datetime, timedelta, timezone

import pytest

import json

from orquestador.telemetria_resumen import PropuestasStore, candidatas, metrica_de, semana_iso

T0 = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def vacio() -> dict:
    return {"errores": {"top": [], "ya_no": []},
            "pedidos": {"por_tipo": {}, "por_origen": {}, "por_motivo": {}, "mediana_s": None},
            "respuesta": {"asks": {"celu": {"mediana_s": None, "p90_s": None, "n": 0},
                                   "en_app": {"mediana_s": None, "p90_s": None, "n": 0}},
                          "blocked": {"celu": {"mediana_s": None, "p90_s": None, "n": 0},
                                      "en_app": {"mediana_s": None, "p90_s": None, "n": 0}},
                          "sin_respuesta": 0},
            "trabas": {"por_tipo": {}, "mediana_s": None, "por_fin": {}},
            "comandos": {"corridos": 0, "fallos": {}, "no": 0},
            "cierres": {"frenados": 0, "resueltos_pct": None},
            "app": {"errores": {}, "tuneles_fallidos": 0, "desconexiones": 0}}


def error(n, plantilla="enrutador no pudo manejar <txt>: <txt>", tipo="AttributeError"):
    return {"plantilla": plantilla, "logger": "orquestador.enrutador", "tipo_exc": tipo, "n": n,
            "delta": 0, "primera": None, "ultima": None, "hace": "hace 1 h"}


def res_con_error(n):
    r = vacio()
    r["errores"]["top"] = [error(n)]
    return r


def res_vencidos(n):
    r = vacio()
    r["pedidos"]["por_motivo"] = {"vencido": {"sin_motivo": n}}
    return r


def res_descartados(n):
    r = vacio()
    r["pedidos"]["por_motivo"] = {"descartado": {"cooldown": n}}
    return r


def res_lenta(mediana, n):
    r = vacio()
    r["respuesta"]["asks"]["celu"] = {"mediana_s": mediana, "p90_s": mediana, "n": n}
    return r


def res_trabas(n):
    r = vacio()
    r["trabas"]["por_tipo"] = {"herramienta": n}
    return r


def res_comandos(n):
    r = vacio()
    r["comandos"]["fallos"] = {"sesion_ocupada": n}
    return r


def res_cierres(frenados, pct):
    r = vacio()
    r["cierres"] = {"frenados": frenados, "resueltos_pct": pct}
    return r


def res_app(n):
    r = vacio()
    r["app"]["errores"] = {"tunel/ssh_rechazado": n}
    return r


def reglas(r):
    return [c["regla"] for c in candidatas(r)]


@pytest.mark.parametrize("res,esperado", [
    (res_con_error(19), []), (res_con_error(20), ["error_repetido"]),
    (res_vencidos(2), []), (res_vencidos(3), ["pedidos_vencen"]),
    (res_descartados(4), []), (res_descartados(5), ["pedidos_descartados"]),
    (res_lenta(1800, 5), []), (res_lenta(1801, 4), []), (res_lenta(1801, 5), ["respuesta_lenta"]),
    (res_trabas(4), []), (res_trabas(5), ["trabas_tipo"]),
    (res_comandos(2), []), (res_comandos(3), ["comandos_fallan"]),
    (res_cierres(9, 80), []), (res_cierres(10, 100), ["cierres_frenados"]),
    (res_cierres(5, 79), ["cierres_frenados"]), (res_cierres(0, None), []),
    (res_app(4), []), (res_app(5), ["app_error"]),
])
def test_umbrales(res, esperado):
    assert reglas(res) == esperado


def test_pedidos_descartados_exige_mismo_motivo():
    r = vacio()
    r["pedidos"]["por_motivo"] = {"descartado": {"cooldown": 3, "otro": 3}}
    assert reglas(r) == []


def test_id_estable_entre_semanas():
    a, b = candidatas(res_con_error(30))[0], candidatas(res_con_error(50))[0]
    assert a["id"] == b["id"] and len(a["id"]) == 12


def test_texto_trae_el_dato_y_no_contenido():
    r = res_con_error(262)
    c = candidatas(r)[0]
    assert "262" in c["texto"] and "CANARIO" not in c["texto"]
    assert c["metrica"] == {"nombre": "veces_por_semana", "valor": 262}
    assert c["peso"] == pytest.approx(262 / 20)


def test_peso_cierres_con_pct():
    assert candidatas(res_cierres(5, 40))[0]["peso"] == pytest.approx(2.0)


def siete():
    r = vacio()
    r["errores"]["top"] = [error(20 + i, plantilla=f"p{i}") for i in range(5)]
    r["pedidos"]["por_motivo"] = {"vencido": {"sin_motivo": 9}}
    r["trabas"]["por_tipo"] = {"herramienta": 5}
    return r


def store(tmp_path, reloj):
    return PropuestasStore(tmp_path / "propuestas.json", lambda: reloj[0])


def test_orden_por_peso_y_maximo_cinco(tmp_path):
    s = store(tmp_path, [T0])
    nuevas = s.elegir(candidatas(siete()), "2026-W48")["nuevas"]
    assert len(nuevas) == 5
    pesos = [c["peso"] for c in nuevas]
    assert pesos == sorted(pesos, reverse=True)


def test_nunca_rellena(tmp_path):
    s = store(tmp_path, [T0])
    assert len(s.elegir(candidatas(res_con_error(30)), "2026-W48")["nuevas"]) == 1


def test_ignorar_silencia_30_dias(tmp_path):
    reloj = [T0]
    s = store(tmp_path, reloj)
    c = candidatas(res_con_error(30))
    s.decidir(c[0]["id"], "ignorar", "2026-W48", 30)
    assert s.elegir(c, "2026-W48")["nuevas"] == []
    reloj[0] = T0 + timedelta(days=31)
    assert [x["id"] for x in s.elegir(c, "2026-W52")["nuevas"]] == [c[0]["id"]]


def test_mas_adelante_va_al_pie(tmp_path):
    s = store(tmp_path, [T0])
    c = candidatas(res_con_error(30))
    s.decidir(c[0]["id"], "mas_adelante", "2026-W48", 30)
    r = s.elegir(c, "2026-W48")
    assert r["nuevas"] == [] and [x["id"] for x in r["mas_adelante"]] == [c[0]["id"]]


def test_hacer_seguimiento_y_volvio(tmp_path):
    s = store(tmp_path, [T0])
    pid = candidatas(res_con_error(100))[0]["id"]
    s.decidir(pid, "hacer", "2026-W47", 100)
    r = s.elegir(candidatas(res_con_error(95)), "2026-W48")
    assert r["nuevas"] == [] and r["volvio"] == []
    seg = r["seguimiento"][0]
    assert (seg["id"], seg["base"], seg["valor"], seg["tendencia"]) == (pid, 100, 95, "igual")
    r = s.elegir(candidatas(res_con_error(80)), "2026-W49")
    assert [c["id"] for c in r["nuevas"]] == [pid]
    assert r["nuevas"][0]["volvio"] is True and r["seguimiento"] == []
    r = s.elegir(candidatas(res_con_error(60)) or [], "2026-W49")
    assert r["nuevas"] == []


def test_tendencia_bajo_y_subio(tmp_path):
    s = store(tmp_path, [T0])
    pid = candidatas(res_con_error(100))[0]["id"]
    s.decidir(pid, "hacer", "2026-W47", 100)
    assert s.elegir(candidatas(res_con_error(90)), "2026-W48")["seguimiento"][0]["tendencia"] == "bajo"
    assert s.elegir(candidatas(res_con_error(110)), "2026-W48")["seguimiento"][0]["tendencia"] == "subio"


def test_podar_180_dias(tmp_path):
    reloj = [T0]
    s = store(tmp_path, reloj)
    s.decidir("abcdef012345", "hacer", "2026-W47", 10)
    reloj[0] = T0 + timedelta(days=181)
    assert s.podar() == 1 and s.cargar() == {}


def test_no_poda_lo_reciente(tmp_path):
    reloj = [T0]
    s = store(tmp_path, reloj)
    s.decidir("abcdef012345", "hacer", "2026-W47", 10)
    reloj[0] = T0 + timedelta(days=179)
    assert s.podar() == 0


def test_archivo_0600(tmp_path):
    s = store(tmp_path, [T0])
    s.decidir("abcdef012345", "ignorar", "2026-W48", None)
    assert stat.S_IMODE((tmp_path / "propuestas.json").stat().st_mode) == 0o600


def test_hacer_cumplida_sale_de_seguimiento(tmp_path):
    s = store(tmp_path, [T0])
    c = candidatas(res_con_error(100))[0]
    s.decidir(c["id"], "hacer", "2026-W47", 100, cand=c)
    assert len(s.elegir(candidatas(res_con_error(90)), "2026-W48")["seguimiento"]) == 1
    r = s.elegir(candidatas(res_con_error(60)), "2026-W49")
    assert r["seguimiento"] == [] and r["nuevas"] == []
    assert s.cargar()[c["id"]]["estado"] == "cumplida"
    r = s.elegir(candidatas(res_con_error(60)), "2026-W50")
    assert r["seguimiento"] == []


def test_podar_aunque_se_llame_elegir_cada_semana(tmp_path):
    reloj = [T0]
    s = store(tmp_path, reloj)
    inicial = vacio()
    inicial["pedidos"]["por_motivo"] = {"descartado": {"cooldown": 5}}
    c = candidatas(inicial)[0]
    s.decidir(c["id"], "hacer", semana_iso(T0.date()), 5, cand=c)
    bajo = vacio()
    bajo["pedidos"]["por_motivo"] = {"descartado": {"cooldown": 4}}
    for semanas in range(1, 28):
        reloj[0] = T0 + timedelta(days=7 * semanas)
        s.elegir([], semana_iso(reloj[0].date()), bajo)
    assert s.podar() == 1


def test_texto_y_archivo_sin_contenido(tmp_path):
    r = res_con_error(30)
    r["errores"]["top"][0]["plantilla"] = "fallo en /home/zyxusuario/CANARIO <txt>"
    r["errores"]["top"][0]["session_id"] = "CANARIO-sid"
    r["pedidos"]["por_motivo"] = {"descartado": {"/home/zyxusuario/CANARIO": 9}}
    r["comandos"]["fallos"] = {"CANARIO con espacios": 4}
    r["app"]["errores"] = {"x/C:\\Users\\zyxusuario\\CANARIO": 6}
    cands = candidatas(r)
    s = store(tmp_path, [T0])
    for c in cands:
        s.decidir(c["id"], "hacer", "2026-W48", c["metrica"]["valor"], cand=c)
    s.elegir(cands, "2026-W49", r)
    todo = " ".join(c["texto"] for c in cands) + (tmp_path / "propuestas.json").read_text()
    for prohibido in ("CANARIO", "/home/", "zyxusuario"):
        assert prohibido not in todo


def test_volvio_con_valor_real_bajo_el_umbral(tmp_path):
    s = store(tmp_path, [T0])
    c = candidatas(res_con_error(25))[0]
    s.decidir(c["id"], "hacer", "2026-W47", 25, cand=c)
    r = s.elegir([], "2026-W49", res_con_error(19))
    assert [x["id"] for x in r["nuevas"]] == [c["id"]]
    assert r["nuevas"][0]["volvio"] is True and r["nuevas"][0]["metrica"]["valor"] == 19


def test_sin_resumen_valor_none_no_cierra_ni_vuelve(tmp_path):
    s = store(tmp_path, [T0])
    c = candidatas(res_con_error(25))[0]
    s.decidir(c["id"], "hacer", "2026-W47", 25, cand=c)
    for semana in ("2026-W48", "2026-W49", "2026-W50"):
        r = s.elegir([], semana)
    assert r["nuevas"] == [] and len(r["seguimiento"]) == 1
    seg = r["seguimiento"][0]
    assert seg["valor"] is None and "bajo el umbral" in seg["texto"]
    assert s.cargar()[c["id"]]["estado"] == "hacer"


def test_metrica_de():
    assert metrica_de(res_con_error(19), "error_repetido", candidatas(res_con_error(20))[0]["clave"]) == 19
    assert metrica_de(res_vencidos(7), "pedidos_vencen", "vencidos") == 7
    assert metrica_de(vacio(), "pedidos_descartados", "cooldown") == 0
    assert metrica_de(vacio(), "error_repetido", "otra|x|y") is None
    assert metrica_de(vacio(), "respuesta_lenta", "asks_celu") is None
    assert metrica_de(res_cierres(4, 50), "cierres_frenados", "frenados") == 4


def test_base_none_se_completa_con_el_primer_valor_conocido(tmp_path):
    s = store(tmp_path, [T0])
    c = candidatas(res_con_error(40))[0]
    s.decidir(c["id"], "hacer", "2026-W47", None, cand=c)
    s.elegir(candidatas(res_con_error(40)), "2026-W48")
    assert s.cargar()[c["id"]]["metrica"]["base"] == 40
    r = s.elegir(candidatas(res_con_error(20)), "2026-W50")
    assert r["seguimiento"] == [] and s.cargar()[c["id"]]["estado"] == "cumplida"


def test_cierres_sin_pct_no_dice_cero_sin_arreglar():
    texto = candidatas(res_cierres(12, None))[0]["texto"]
    assert "12" in texto and "no se arreglaron" not in texto
