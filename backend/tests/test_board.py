import json
import asyncio

import pytest

from conftest import SID, make_snapshot
from orquestador.board import BoardHub, build_board, find_session_agent
from orquestador.digest import DigestService
from orquestador.enchufe import Evento, FakeTerminales, NoDisponible
from orquestador.enchufe.herdr import tablero_de_snapshot


def test_agent_lleva_fondo_vacio_sin_tareas(projects):
    from orquestador.fondo import FondoService
    digests = DigestService(projects)
    agent = build_board(make_snapshot("idle"), digests, fondo=FondoService(digests.find))["workspaces"][0]["tabs"][0]["agents"][0]
    assert agent["fondo"] == []


def test_build_board(projects):
    board = build_board(make_snapshot("working"), DigestService(projects), self_pane_id="w2:p9")
    assert board["focused_tab_id"] == "w1:t1"
    assert board["self_pane_id"] == "w2:p9"
    assert [w["number"] for w in board["workspaces"]] == [1, 2]
    ws1, ws2 = board["workspaces"]
    agent = ws1["tabs"][0]["agents"][0]
    assert agent["status"] == "working"
    assert agent["doing"] == "Título nuevo"
    assert agent["pending"] == "¿Seguimos con esto?"
    # Trabajando sin un mensaje nuevo después de la pregunta (comando local): la pregunta sigue en pie.
    assert agent["asks_user"] is True
    assert agent["turno_local"] is False
    assert agent["session_id"] == SID
    assert agent["last_activity"]
    assert ws1["status"] == "working"
    assert [t["agents"] for t in ws2["tabs"]] == [[], []]


def test_agent_without_transcript_falls_back_to_terminal_title(projects):
    board = build_board(make_snapshot(), DigestService(projects), self_pane_id=None)
    agent = board["workspaces"][1]["tabs"][1]["agents"][0]
    assert agent["doing"] == "Propio"
    assert agent["status"] == "unknown"
    assert agent["pending"] == "" and agent["asks_user"] is False


def test_hub_emits_only_on_change(projects):
    async def scenario():
        fake = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
        hub = BoardHub(fake, DigestService(projects))
        queue = hub.subscribe()
        first = await asyncio.wait_for(queue.get(), 2)
        assert first["workspaces"][0]["status"] == "idle"
        await asyncio.sleep(0.1)
        assert queue.empty()
        fake.tablero_actual = tablero_de_snapshot(make_snapshot("working"), fake.tablero_actual.revision + 1)
        fake.emitir(Evento("tablero", fake.nombre))
        second = await asyncio.wait_for(queue.get(), 2)
        assert second["workspaces"][0]["status"] == "working"
        hub.unsubscribe(queue)
        assert hub._task is None
    asyncio.run(scenario())


def test_hub_resuscribe_si_aclose_de_suscripcion_falla(projects):
    class _SubRota:
        def __init__(self, sub, hub, contador):
            self._sub = sub
            self._hub = hub
            self._contador = contador

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._contador[0] == 0:
                raise RuntimeError("suscripción rota")
            self._contador[0] -= 1
            return await self._sub.__anext__()

        async def aclose(self):
            raise RuntimeError("aclose roto")

    class EnchufeSubRota:
        def __init__(self, inner):
            self._inner = inner
            self._contador = [2]

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def suscribir(self):
            return _SubRota(self._inner.suscribir(), self, self._contador)

    async def escenario():
        inner = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.02)
        hub = BoardHub(EnchufeSubRota(inner), DigestService(projects), debounce=0.02)
        q = hub.subscribe()
        primero = await asyncio.wait_for(q.get(), 1)
        assert primero["terminales"] == "ok"
        inner.tablero_actual = tablero_de_snapshot(
            make_snapshot("working"), inner.tablero_actual.revision + 1)
        inner.emitir(Evento("tablero", inner.nombre))
        segundo = await asyncio.wait_for(q.get(), 2)
        assert segundo["workspaces"][0]["status"] == "working"
        hub.unsubscribe(q)

    asyncio.run(escenario())


def test_caido_conserva_sesiones_y_volvio_limpia(projects):
    async def escenario():
        t = FakeTerminales.desde_snapshot(make_snapshot(), poll=60)
        hub = BoardHub(t, DigestService(projects))
        q = hub.subscribe()
        primero = await asyncio.wait_for(q.get(), 1)
        assert primero["terminales"] == "ok"
        t.caer()
        with pytest.raises(NoDisponible):
            await t.tablero()
        caido = await asyncio.wait_for(q.get(), 1)
        assert caido["terminales"] == "sin_conexion" and caido["workspaces"] == primero["workspaces"]
        t.volver()
        await t.tablero()
        vuelto = await asyncio.wait_for(q.get(), 1)
        assert vuelto["terminales"] == "ok"
        hub.unsubscribe(q)
    asyncio.run(escenario())


def test_conflicto_de_ids_aparece_en_el_board(projects):
    snap = make_snapshot()
    snap["tabs"].append({"tab_id": "g7:t1", "workspace_id": "w1", "label": "raro"})
    hub = BoardHub(FakeTerminales.desde_snapshot(snap), DigestService(projects))
    assert asyncio.run(hub.refresh())["conflictos"] == ["g7:t1"]


def test_asks_user_only_when_not_working(projects):
    agent = build_board(make_snapshot("done"), DigestService(projects))["workspaces"][0]["tabs"][0]["agents"][0]
    assert agent["asks_user"] is True


def test_pinned_workspace_by_label(projects):
    snap = make_snapshot()
    for ws in snap["workspaces"]:
        ws["label"] = "Super Orquestador "
    board = build_board(snap, DigestService(projects), pinned=frozenset({"super orquestador"}))
    assert all(ws["pinned"] for ws in board["workspaces"])
    assert not any(ws["pinned"] for ws in build_board(snap, DigestService(projects))["workspaces"])


def test_sin_bloques_never_leaves_raw_json():
    from orquestador.digest import sin_bloques
    proceso = 'Mirá:\n\n```diagrama\n{"titulo": "Cómo te llega un aviso", "tipo": "proceso", "pasos": [{"texto": "x"}]}\n```\n\nListo.'
    assert sin_bloques(proceso) == "Mirá:\n\nDiagrama: Cómo te llega un aviso.\n\nListo."
    assert sin_bloques('```diagrama\n{"nodos": [{"id": "a"}]}\n```') == "Diagrama."
    assert sin_bloques('Elegí\n```opciones\n{"pregunta": "¿Qué hacemos?", "opciones": []}\n```') == "Elegí\n¿Qué hacemos?"
    assert sin_bloques('Va\n```diagrama\n{"titulo": "A \\"b\\"", "nodos": [') == 'Va\nDiagrama: A "b".'
    assert sin_bloques("```php\necho 1;\n```") == "```php\necho 1;\n```"
    assert "{" not in sin_bloques('```diagrama\n{"tipo": "secuencia", "pasos": [{"texto": "x"}]}\n```')


def test_pending_hides_blocks(projects):
    path = next(projects.glob("*/*.jsonl"))
    line = {"type": "assistant", "message": {"content": [{"type": "text", "text":
            'Te lo dibujo\n```diagrama\n{"titulo": "Mapa", "nodos": [{"id": "a"}]}\n```'}]}}
    path.write_text(path.read_text(encoding="utf-8") + json.dumps(line) + "\n", encoding="utf-8")
    board = build_board(make_snapshot("idle"), DigestService(projects), self_pane_id="w2:p9")
    assert board["workspaces"][0]["tabs"][0]["agents"][0]["pending"] == "Te lo dibujo\nDiagrama: Mapa."


def _append_assistant(projects, text):
    path = projects / "-proj" / f"{SID}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}) + "\n")


def test_asks_user_when_last_block_is_opciones(projects):
    _append_assistant(projects, 'Te dejo dos:\n\n```opciones\n{"pregunta": "Uno", "opciones": [{"label": "A"}]}\n```\n\n'
                                '```opciones\n{"pregunta": "Dos", "opciones": [{"label": "B"}]}\n```')
    agent = build_board(make_snapshot("idle"), DigestService(projects))["workspaces"][0]["tabs"][0]["agents"][0]
    assert agent["asks_user"] is True and agent["preguntas"] == 2


def test_opciones_followed_by_prose_is_not_a_question(projects):
    _append_assistant(projects, '```opciones\n{"opciones": [{"label": "A"}]}\n```\nYa lo resolví solo.')
    agent = build_board(make_snapshot("idle"), DigestService(projects))["workspaces"][0]["tabs"][0]["agents"][0]
    assert agent["asks_user"] is False and agent["preguntas"] == 0


def test_question_without_cards_counts_zero_cards(projects):
    agent = build_board(make_snapshot("done"), DigestService(projects))["workspaces"][0]["tabs"][0]["agents"][0]
    assert agent["asks_user"] is True and agent["preguntas"] == 0 and agent["pregunta_real"] is False


def _agent(projects, status="idle"):
    return build_board(make_snapshot(status), DigestService(projects))["workspaces"][0]["tabs"][0]["agents"][0]


def test_estado_se_expone_y_no_aparece_en_pending(projects):
    _append_assistant(projects, 'Listo, quedó andando.\n\n```estado\n{"hizo": "Saqué el mapa", "falta": "Elegir el diseño"}\n```')
    agent = _agent(projects)
    assert agent["estado"] == {"hizo": "Saqué el mapa", "falta": "Elegir el diseño"}
    assert agent["pending"] == "Listo, quedó andando."
    assert agent["asks_user"] is False


def test_sin_bloque_estado_es_none(projects):
    assert _agent(projects)["estado"] is None


def test_estado_con_pide_hace_que_pregunte(projects):
    _append_assistant(projects, 'Hecho.\n\n```estado\n{"hizo": "x", "pide": "¿Cuál preferís?"}\n```')
    assert _agent(projects, "done")["asks_user"] is True
    assert _agent(projects, "blocked")["asks_user"] is False


def test_estado_pide_se_anula_si_ya_esta_trabajando_en_otra_cosa(projects):
    _append_assistant(projects, 'Hecho.\n\n```estado\n{"pide": "¿Cuál?"}\n```')
    assert _agent(projects, "working")["asks_user"] is True
    path = projects / "-proj" / f"{SID}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user", "message": {"content": "dale, la A"}}) + "\n")
    assert _agent(projects, "working")["asks_user"] is False


def test_estado_despues_de_opciones_no_rompe_la_tarjeta(projects):
    _append_assistant(projects, 'Elegí:\n\n```opciones\n{"pregunta": "Uno", "opciones": [{"label": "A"}]}\n```\n\n'
                                '```estado\n{"hizo": "x"}\n```')
    agent = _agent(projects)
    assert agent["asks_user"] is True and agent["preguntas"] == 1 and agent["estado"] == {"hizo": "x"}


def test_pending_corta_en_la_ultima_frase_completa(projects):
    _append_assistant(projects, "Esta es la primera frase del resumen, bastante larga para ocupar lugar. "
                                "Esta es la segunda frase, que también ocupa lugar y casi llena el tope. "
                                "Y esta tercera ya no entra en el recorte de la tarjeta.")
    pending = _agent(projects)["pending"]
    assert pending.endswith("tope.") and "tercera" not in pending


def test_find_session_agent_ignora_la_clave_centinela_vieja(projects):
    board = build_board(make_snapshot(), DigestService(projects), self_pane_id="w2:p9")
    board["centinela"] = {"session_id": "nope", "pane_id": "w2:p9"}
    assert find_session_agent(board, SID)["pane_id"] == "w1:p1"
    assert find_session_agent(board, "nope") is None
