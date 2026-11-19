import json
from conftest import SID
from orquestador.digest import DigestService, parse_transcript


def test_parse_filters_and_orders(projects):
    d = parse_transcript(projects / "-proj" / f"{SID}.jsonl")
    assert d.title == "Título nuevo"
    assert d.last_prompt == "segundo"
    assert d.turns == [
        {"role": "user", "text": "hola uno"},
        {"role": "claude", "text": "respuesta uno"},
        {"role": "user", "text": "segundo"},
        {"role": "claude", "text": "¿Seguimos con esto?"},
    ]


def test_summary_limits_turns_and_rejects_bad_ids(projects):
    svc = DigestService(projects)
    assert len(svc.summary(SID, turns=2)["turns"]) == 2
    assert svc.summary("../x") is None
    assert svc.summary("inexistente") is None


def test_cache_invalidated_by_mtime(projects):
    svc = DigestService(projects)
    first = svc.get(SID)
    assert svc.get(SID) is first
    path = projects / "-proj" / f"{SID}.jsonl"
    path.write_text(path.read_text() + '{"type":"ai-title","aiTitle":"Otro"}\n')
    assert svc.get(SID).title == "Otro"


def test_clip(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"type":"user","message":{"content":"' + "a" * 13000 + '"}}\n')
    assert parse_transcript(p).turns[0]["text"].endswith("…[recortado]")


def test_summary_keeps_last_turn_whole(tmp_path):
    proj = tmp_path / "-proj"
    proj.mkdir()
    long = "b" * 3000
    lines = [
        '{"type":"user","message":{"content":"' + long + '"}}',
        '{"type":"assistant","message":{"content":[{"type":"text","text":"' + long + '"}]}}',
    ]
    (proj / f"{SID}.jsonl").write_text("\n".join(lines) + "\n")
    turns = DigestService(tmp_path).summary(SID)["turns"]
    assert turns[0]["text"].endswith("…[recortado]")
    assert turns[-1]["text"] == long


def test_compact_summary_is_not_a_user_turn(tmp_path):
    import json
    from orquestador.digest import parse_transcript

    path = tmp_path / "s.jsonl"
    rows = [{"type": "user", "message": {"content": "hola"}},
            {"type": "user", "isCompactSummary": True, "message": {"content": "Resumen largo"}}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert [t["text"] for t in parse_transcript(path).turns] == ["hola"]


def test_last_message_ignores_metadata_and_system_entries(tmp_path):
    from orquestador.digest import parse_transcript
    lines = [
        {"type": "user", "timestamp": "2026-10-30T10:00:00Z", "message": {"content": "hola"}},
        {"type": "assistant", "timestamp": "2026-10-30T10:01:00Z", "message": {"content": [{"type": "text", "text": "chau"}]}},
        {"type": "user", "timestamp": "2026-11-01T09:00:00Z", "promptSource": "system", "message": {"content": "<task-notification>"}},
        {"type": "user", "timestamp": "2026-11-01T09:00:00Z", "isMeta": True, "message": {"content": "meta"}},
        {"type": "ai-title", "aiTitle": "Nuevo"},
    ]
    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    digest = parse_transcript(path)
    assert digest.last_message == "2026-10-30T10:01:00Z"


def _bloque(cuerpo):
    return "```estado\n" + cuerpo + "\n```"


def test_parse_estado_toma_el_ultimo_bloque_y_recorta():
    from orquestador.digest import parse_estado
    texto = ("Listo.\n\n" + _bloque('{"hizo": "viejo"}') + "\n\nY además:\n\n"
             + _bloque('{"hizo": "Saqué el mapa", "falta": "Elegir el diseño", "pide": "¿Cuál preferís?", "otro": 3}'))
    assert parse_estado(texto) == {"hizo": "Saqué el mapa", "falta": "Elegir el diseño", "pide": "¿Cuál preferís?"}
    largo = parse_estado(_bloque('{"hizo": "' + "palabra " * 30 + '"}'))
    assert len(largo["hizo"]) <= 121 and largo["hizo"].endswith("…")


def test_parse_estado_invalido_o_vacio_es_none():
    from orquestador.digest import parse_estado
    assert parse_estado("sin bloque") is None
    assert parse_estado(_bloque("{no es json")) is None
    assert parse_estado(_bloque("[1, 2]")) is None
    assert parse_estado(_bloque('{"hizo": 4, "falta": "  ", "x": "y"}')) is None
    assert parse_estado(_bloque('{"hizo": "a"}') + "\n" + _bloque("{roto")) is None
    assert parse_estado(_bloque('{"falta": "Algo",}')) == {"falta": "Algo"}


def test_quitar_estado_y_sin_bloques_no_dejan_el_bloque():
    from orquestador.digest import quitar_estado, sin_bloques
    texto = "Terminé.\n\n" + _bloque('{"hizo": "x"}')
    assert quitar_estado(texto) == "Terminé."
    assert sin_bloques(texto) == "Terminé."
    assert quitar_estado("```php\necho 1;\n```") == "```php\necho 1;\n```"


def test_clip_frase_corta_en_el_final_de_la_ultima_frase():
    from orquestador.digest import clip_frase
    assert clip_frase("Corto.", 50) == "Corto."
    texto = "Primera frase completa. Segunda frase que no entra del todo en el tope."
    assert clip_frase(texto, 40) == "Primera frase completa."
    assert clip_frase("Hola. " + "palabra " * 30, 60).endswith("…")
    assert clip_frase("Ver 3.5 de la lib y " + "palabra " * 30, 60).endswith("…")


def test_estado_dentro_de_un_fence_mas_largo_no_cuenta():
    from orquestador.digest import estados_todos_validos, parse_estado, quitar_estado
    texto = '````pruebas\n{"titulo": "T"}\n```estado\n{"hizo": "X"}\n```\n````\n'
    assert estados_todos_validos(texto) is False
    assert parse_estado(texto) is None
    assert quitar_estado(texto) == texto
    ejemplo = '````markdown\n```estado\n{"hizo": "X"}\n```\n````\n\n```estado\n{"hizo": "Real"}\n```'
    assert parse_estado(ejemplo) == {"hizo": "Real"}
    assert estados_todos_validos(ejemplo) is True
