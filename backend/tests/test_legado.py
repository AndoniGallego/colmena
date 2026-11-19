"""Mensajes y Biblioteca guardados con el formato anterior se leen como diagrama."""
import json
import os

import pytest

from biblioteca_support import SID, Env, text_msg
from orquestador import biblioteca as bib
from orquestador.digest import sin_bloques
from orquestador.legado import LEGACY_FENCE, diagrama_legado, migrar_items

VIEJO_RAW = f"{LEGACY_FENCE}_raw"


def viejo(data) -> str:
    return f"```{LEGACY_FENCE}\n{json.dumps(data, ensure_ascii=False)}\n```"


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def test_diagrama_legado_infiere_el_tipo_como_antes():
    assert diagrama_legado({"actores": [{"id": "a"}], "pasos": [{"de": "a", "texto": "x"}]})["tipo"] == "secuencia"
    assert diagrama_legado({"actores": [{"id": " "}], "pasos": [{"texto": "x"}]})["tipo"] == "proceso"
    assert diagrama_legado({"pasos": [{"texto": "x"}]})["tipo"] == "proceso"
    con_tipo = {"tipo": "secuencia", "pasos": []}
    assert diagrama_legado(con_tipo) is con_tipo
    assert diagrama_legado({"nodos": [{"id": "a"}]}) is None
    assert diagrama_legado(None) is None


def test_fence_viejo_se_indexa_como_diagrama_con_tipo(env):
    sin_tipo = viejo({"titulo": "Login", "pasos": [{"texto": "uno"}]})
    con_tipo = viejo({"titulo": "Charla", "tipo": "secuencia", "actores": [{"id": "a"}], "pasos": [{"de": "a", "texto": "x"}]})
    env.append([text_msg(sin_tipo + "\n\n" + con_tipo, "m1"), text_msg(viejo({"nada": 1}), "m2")])
    env.lib.index_all()
    its = sorted(env.lib.items.values(), key=lambda i: i["title"])
    assert [(i["kind"], i["source"], i["title"]) for i in its] == [("diagrama", "diagrama", "Charla"),
                                                                    ("diagrama", "diagrama", "Login")]
    assert json.loads(its[1]["diagrama_raw"])["tipo"] == "proceso"
    assert json.loads(its[0]["diagrama_raw"])["tipo"] == "secuencia"
    assert len(env.lib.lib_ids_for_diagramas(SID, "m1", 0, 2)) == 2


def test_avisos_nombran_el_fence_viejo_como_diagrama():
    assert sin_bloques("Mirá\n" + viejo({"titulo": "Cocinar", "pasos": [{"texto": "x"}]})) == "Mirá\nDiagrama: Cocinar."
    assert sin_bloques(viejo({"pasos": []})) == "Diagrama."


def _item(letra, kind, source, title, raw):
    return {"id": letra * 32, "kind": kind, "source": source, "session_id": SID, "project": "-proj",
            "subagent": False, "tool_use_id": "m1", "ts": "2026-11-01T10:00:00Z", "title": title,
            "description": "", "caption": "", "path": "", "exists": True, "size": 1, "mime": "application/json",
            "url": "", "version": 0, "versions": [], "assets": {}, VIEJO_RAW: raw, "allowed": True, "motivo": "",
            "copia": False, "keys": []}


def _items_viejos():
    seq = {"titulo": "S", "actores": [{"id": "a"}], "pasos": [{"de": "a", "texto": "x"}]}
    return {i["id"]: i for i in (
        _item("a", LEGACY_FENCE, LEGACY_FENCE, "S", json.dumps(seq)),
        _item("b", "diagrama", "diagrama", "D", '{"nodos": [{"id": "a"}]}'),
        _item("c", "html", "artifact", "H", None),
        _item("d", LEGACY_FENCE, LEGACY_FENCE, "Roto", "{no es json"),
    )}


def test_migrar_items_convierte_e_idempotente():
    items = _items_viejos()
    assert migrar_items(items) is True
    a, b, c, d = (items[k * 32] for k in "abcd")
    assert all(VIEJO_RAW not in i for i in items.values())
    assert (a["kind"], a["source"]) == ("diagrama", "diagrama")
    assert json.loads(a["diagrama_raw"])["tipo"] == "secuencia" and a["size"] == len(a["diagrama_raw"])
    assert b["diagrama_raw"] == '{"nodos": [{"id": "a"}]}'
    assert c["diagrama_raw"] is None and c["kind"] == "html"
    assert d["kind"] == "diagrama" and d["diagrama_raw"] == "{no es json"
    copia = json.dumps(items, sort_keys=True)
    assert migrar_items(items) is False
    assert json.dumps(items, sort_keys=True) == copia


def test_biblioteca_migra_al_cargar_y_reescribe_atomico(env):
    path = env.data / "biblioteca.json"
    path.write_text(json.dumps({"v": 1, "files": {}, "items": _items_viejos(), "sessions": {}, "quitados": []}),
                    encoding="utf-8")
    lib = env.reload()
    assert {i["kind"] for i in lib.items.values()} == {"diagrama", "html"}
    guardado = json.loads(path.read_text(encoding="utf-8"))
    assert LEGACY_FENCE not in {i["kind"] for i in guardado["items"].values()}
    assert all(VIEJO_RAW not in i for i in guardado["items"].values())
    assert not path.with_name(path.name + ".tmp").exists()
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    vista = lib.view_of(lib.items["a" * 32])
    assert vista["kind"] == "diagrama" and json.loads(vista["diagrama_raw"])["tipo"] == "secuencia"
    assert len(lib.filtered(tipo="diagrama")) == 3

    antes = (path.read_bytes(), path.stat().st_mtime_ns)
    env.reload()
    assert (path.read_bytes(), path.stat().st_mtime_ns) == antes


def test_sin_formato_viejo_no_reescribe(env):
    path = env.data / "biblioteca.json"
    path.write_text(json.dumps({"v": 1, "files": {}, "items": {}, "sessions": {}, "quitados": []}), encoding="utf-8")
    antes = path.stat().st_mtime_ns
    env.reload()
    assert path.stat().st_mtime_ns == antes


def test_kinds_ya_no_incluye_el_nombre_viejo():
    assert LEGACY_FENCE not in bib.KINDS and "diagrama" in bib.KINDS
