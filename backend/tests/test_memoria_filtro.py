import json
import subprocess
import sys
import textwrap

import pytest

from orquestador import memoria_filtro as mf

HIJO = textwrap.dedent("""
    import json, sys
    log = open(sys.argv[1], "a")
    for linea in sys.stdin:
        log.write(linea if linea.endswith("\\n") else linea + "\\n")
        log.flush()
        try:
            msg = json.loads(linea)
        except ValueError:
            continue
        if isinstance(msg, dict) and "id" in msg:
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"ok": True}}), flush=True)
""")


def _llamada(nombre, argumentos, id_=1):
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": "tools/call",
                       "params": {"name": nombre, "arguments": argumentos}})


def _correr(tmp_path, lineas, trabajo=None):
    hijo = tmp_path / "hijo.py"
    hijo.write_text(HIJO)
    log = tmp_path / "log.txt"
    cmd = [sys.executable, "-m", "orquestador.memoria_filtro", "--propio", "colmena-guia"]
    if trabajo:
        cmd += ["--trabajo", trabajo]
    cmd += ["--", sys.executable, str(hijo), str(log)]
    r = subprocess.run(cmd, input="\n".join(lineas) + "\n", capture_output=True, text=True, timeout=20)
    recibido = [json.loads(x) for x in log.read_text().splitlines() if x.strip()] if log.exists() else []
    salida = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
    return recibido, salida


def test_mem_save_fuerza_el_proyecto_propio(tmp_path):
    recibido, salida = _correr(tmp_path, [_llamada("mem_save", {"title": "t", "project": "otro"})], "mi-trabajo")
    assert recibido[0]["params"]["arguments"] == {"title": "t", "project": "colmena-guia"}
    assert salida[0]["result"] == {"ok": True}


def test_mem_save_sin_project_usa_el_propio(tmp_path):
    recibido, _ = _correr(tmp_path, [_llamada("mem_save", {"title": "t"})])
    assert recibido[0]["params"]["arguments"]["project"] == "colmena-guia"


def test_mem_search_quita_all_projects_y_usa_propio(tmp_path):
    recibido, _ = _correr(tmp_path, [_llamada("mem_search", {"query": "q", "all_projects": True})])
    assert recibido[0]["params"]["arguments"] == {"query": "q", "project": "colmena-guia"}


def test_mem_search_trabajo_traduce_el_alias(tmp_path):
    recibido, _ = _correr(tmp_path, [_llamada("mem_search", {"query": "q", "project": "trabajo"})], "mi-trabajo")
    assert recibido[0]["params"]["arguments"]["project"] == "mi-trabajo"


def test_mem_search_propio_explicito_pasa(tmp_path):
    recibido, _ = _correr(tmp_path, [_llamada("mem_search", {"query": "q", "project": "colmena-guia"})], "mi-trabajo")
    assert recibido[0]["params"]["arguments"]["project"] == "colmena-guia"


def test_mem_search_trabajo_sin_configurar_es_error(tmp_path):
    recibido, salida = _correr(tmp_path, [_llamada("mem_search", {"query": "q", "project": "trabajo"}, 7)])
    assert recibido == []
    assert salida[0]["id"] == 7 and salida[0]["result"]["isError"] is True
    assert "no hay memoria de trabajo configurada" in salida[0]["result"]["content"][0]["text"]


def test_mem_search_otro_proyecto_es_error(tmp_path):
    recibido, salida = _correr(tmp_path, [_llamada("mem_search", {"query": "q", "project": "secreto"}, 3)], "mi-trabajo")
    assert recibido == []
    assert salida[0]["result"]["isError"] is True
    assert "solo podés buscar en tu memoria o en la de trabajo" in salida[0]["result"]["content"][0]["text"]


def test_mem_get_observation_pasa_tal_cual(tmp_path):
    linea = _llamada("mem_get_observation", {"id": 5})
    recibido, _ = _correr(tmp_path, [linea])
    assert recibido == [json.loads(linea)]


def test_otra_tool_es_error_sin_reenviar(tmp_path):
    recibido, salida = _correr(tmp_path, [_llamada("mem_delete", {"id": 1}, 9)])
    assert recibido == [] and salida[0]["id"] == 9 and salida[0]["result"]["isError"] is True


def test_protocolo_y_notificaciones_pasan(tmp_path):
    lineas = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
              json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
              json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})]
    recibido, salida = _correr(tmp_path, lineas)
    assert [m.get("method") for m in recibido] == ["initialize", "notifications/initialized", "tools/list"]
    assert sorted(m["id"] for m in salida) == [1, 2]


def test_linea_no_json_no_se_reenvia(tmp_path):
    recibido, salida = _correr(tmp_path, ["esto no es json", _llamada("mem_get_observation", {"id": 1}, 4)])
    assert len(recibido) == 1 and recibido[0]["id"] == 4
    assert [m["id"] for m in salida] == [4]


def test_batch_json_no_se_reenvia(tmp_path):
    recibido, _ = _correr(tmp_path, ["[" + _llamada("mem_save", {"project": "x"}) + "]"])
    assert recibido == []


def test_termina_si_el_hijo_no_existe():
    r = subprocess.run([sys.executable, "-m", "orquestador.memoria_filtro", "--propio", "p", "--",
                        "/no/existe/nada"], input="", capture_output=True, text=True, timeout=20)
    assert r.returncode != 0


@pytest.mark.parametrize("nombre", ["Mayus", "-x", "a b", ""])
def test_trabajo_invalido_se_rechaza(nombre):
    with pytest.raises(SystemExit):
        mf.main(["--propio", "p", "--trabajo", nombre, "--", "true"])


@pytest.mark.parametrize("nombre", ["mem_save", "mem_search"])
def test_scope_se_quita_para_no_salir_del_proyecto(tmp_path, nombre):
    recibido, _ = _correr(tmp_path, [_llamada(nombre, {"query": "q", "title": "t", "scope": "personal"})])
    assert "scope" not in recibido[0]["params"]["arguments"]
