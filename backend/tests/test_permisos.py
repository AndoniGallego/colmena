import ast
import asyncio
import inspect
import json
from pathlib import Path

import pytest

import orquestador

from orquestador.ganchos.mensaje import Ids, MensajeGancho
from orquestador.locks import PaneLocks
from orquestador.permisos import AuditoriaPermisos, PermisoError, PermisosService
from orquestador.permisos_regla import regla_acotada


class FakeConexion:
    def __init__(self, ok=True, bloquear=None):
        self.cerrada, self.respuestas, self.ok, self.bloquear = (
            asyncio.Event(),
            [],
            ok,
            bloquear,
        )

    async def responder(self, r):
        if self.bloquear:
            await self.bloquear.wait()
        if self.cerrada.is_set() or not self.ok:
            return False
        self.respuestas.append(r)
        self.cerrada.set()
        return True

    def cerrar(self):
        self.cerrada.set()


def pr(tool="Bash", tool_use_id="t1", cmd="touch foo", sid="s1"):
    return MensajeGancho(
        "PermissionRequest",
        "global",
        Ids(None, "w1:p1", None, None, sid),
        {
            "tool_name": tool,
            "tool_use_id": tool_use_id,
            "tool_input": {"command": cmd},
            "cwd": "/home/u/p",
        },
    )


@pytest.fixture
def svc(tmp_path):
    cambios = []
    cambio = asyncio.Event()

    def al_cambiar():
        cambios.append(1)
        cambio.set()

    s = PermisosService(
        AuditoriaPermisos(tmp_path / "permisos.jsonl"),
        PaneLocks(),
        espera=lambda: 120.0,
        desde_app=lambda: True,
        al_cambiar=al_cambiar,
        realpath=lambda p: p,
    )
    s.cambios = cambios
    s.cambio = cambio
    return s


def auditoria(tmp_path):
    path = tmp_path / "permisos.jsonl"
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text().splitlines()]


def test_pedido_no_conserva_la_entrada_sin_redactar(svc):
    secreto = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(cmd=f"curl -H 'Authorization: token {secreto}' x"), "w1:p1", c)
        assert secreto not in repr(vars(p))
        assert secreto not in json.dumps(p.publico(), default=str)

    asyncio.run(esc())


def test_doble_toque_concurrente_una_sola_escritura(svc):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        res = await asyncio.gather(
            svc.decidir(p.id, "permitir"),
            svc.decidir(p.id, "rechazar"),
            return_exceptions=True,
        )
        assert len(c.respuestas) == 1 and c.respuestas[0]["decision"] == "allow"
        assert isinstance(res[1], PermisoError) and res[1].status == 409

    asyncio.run(esc())


def test_orden_invertido_gana_el_primero(svc):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        res = await asyncio.gather(
            svc.decidir(p.id, "rechazar", "no"),
            svc.decidir(p.id, "permitir"),
            return_exceptions=True,
        )
        assert c.respuestas == [{"v": 1, "decision": "deny", "mensaje": "no"}] and res[
            1
        ].status == 409

    asyncio.run(esc())


@pytest.mark.parametrize(
    "motivo,esperado",
    [
        ("usá otra cosa", "usá otra cosa"),
        ("", "Rechazado desde Colmena"),
        (None, "Rechazado desde Colmena"),
        ("a\x00b\x1bc", "abc"),
        ("m" * 900, "m" * 500),
    ],
)
def test_rechazo_con_motivo(svc, motivo, esperado):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        await svc.decidir(p.id, "rechazar", motivo)
        assert c.respuestas == [{"v": 1, "decision": "deny", "mensaje": esperado}]

    asyncio.run(esc())


def test_siempre_usa_regla_del_servidor_y_huella(svc):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        with pytest.raises(PermisoError) as e:
            await svc.decidir(p.id, "siempre", huella_regla="otra")
        assert e.value.status == 409 and p.estado == "abierto"
        await svc.decidir(p.id, "siempre", huella_regla=p.regla.huella())
        assert c.respuestas == [
            {
                "v": 1,
                "decision": "siempre",
                "reglas": [{"toolName": "Bash", "ruleContent": "touch:*"}],
            }
        ]

    asyncio.run(esc())


def test_siempre_sin_regla_409(svc):
    async def esc():
        p = await svc.atender(pr(cmd="ls | sh"), "w1:p1", FakeConexion())
        assert p.regla is None and p.publico()["regla"] is None
        with pytest.raises(PermisoError) as e:
            await svc.decidir(p.id, "siempre", huella_regla="x")
        assert e.value.status == 409

    asyncio.run(esc())


def test_publico_incluye_creado_iso(svc):
    from datetime import datetime, timezone

    t = datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc)
    svc._wall = lambda: t

    async def esc():
        p = await svc.atender(pr(cmd="ls"), "w1:p1", FakeConexion())
        assert p.publico()["creado"] == t.isoformat()

    asyncio.run(esc())


def test_auditoria_una_linea_por_decision_sin_pin_y_redactada(svc, tmp_path):
    async def esc():
        p = await svc.atender(
            pr(cmd="curl -H 'Authorization: Bearer abcdef0123456789abcdef' x"),
            "w1:p1",
            FakeConexion(),
        )
        await svc.decidir(p.id, "permitir")
        tipos = [l["tipo"] for l in auditoria(tmp_path)]
        assert tipos == ["pedido", "app-allow"]
        texto = (tmp_path / "permisos.jsonl").read_text()
        assert "abcdef0123456789abcdef" not in texto and "pin" not in texto.lower()
        assert "abcdef0123456789abcdef" not in json.dumps(p.publico())

    asyncio.run(esc())


def test_auditoria_falla_al_crear_no_decide(svc, tmp_path):
    async def esc():
        (tmp_path / "permisos.jsonl").mkdir()
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        assert c.cerrada.is_set() and c.respuestas == [] and p is None
        assert svc.abierto_para("s1") is None

    asyncio.run(esc())


def test_auditoria_falla_al_decidir_503_y_al_dialogo(svc, tmp_path):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        (tmp_path / "permisos.jsonl").rename(tmp_path / "x")
        (tmp_path / "permisos.jsonl").mkdir()
        with pytest.raises(PermisoError) as e:
            await svc.decidir(p.id, "permitir")
        assert e.value.status == 503 and c.respuestas == [] and p.estado == "dialogo"

    asyncio.run(esc())


def test_ask_user_question_y_desde_app_false_no_crean_pedido(svc, tmp_path):
    async def esc():
        c = FakeConexion()
        assert await svc.atender(pr(tool="AskUserQuestion"), "w1:p1", c) is None and c.cerrada.is_set()
        svc.desde_app = lambda: False
        c2 = FakeConexion()
        assert await svc.atender(pr(tool_use_id="t9"), "w1:p1", c2) is None and c2.cerrada.is_set()
        assert svc.listar() == []

    asyncio.run(esc())


def test_sin_dueno(svc, tmp_path):
    async def esc():
        c = FakeConexion()
        assert await svc.atender(pr(), None, c) is None and c.cerrada.is_set()
        assert auditoria(tmp_path)[-1]["tipo"] == "sin-dueno" and svc.listar() == []

    asyncio.run(esc())


def test_decidir_con_desde_app_apagado_409(svc):
    async def esc():
        p = await svc.atender(pr(), "w1:p1", FakeConexion())
        svc.desde_app = lambda: False
        with pytest.raises(PermisoError) as e:
            await svc.decidir(p.id, "permitir")
        assert e.value.status == 409

    asyncio.run(esc())


def test_dedup_misma_clave_cierra_segunda_conexion(svc):
    async def esc():
        c1, c2 = FakeConexion(), FakeConexion()
        p1 = await svc.atender(pr(), "w1:p1", c1)
        p2 = await svc.atender(pr(), "w1:p1", c2)
        assert p1 is p2 and c2.cerrada.is_set() and not c1.cerrada.is_set()

    asyncio.run(esc())


def test_accion_invalida_422(svc):
    async def esc():
        p = await svc.atender(pr(), "w1:p1", FakeConexion())
        with pytest.raises(PermisoError) as e:
            await svc.decidir(p.id, "foo")
        assert e.value.status == 422

    asyncio.run(esc())


def test_pedido_inexistente_404(svc):
    async def esc():
        with pytest.raises(PermisoError) as e:
            await svc.decidir("no-existe", "permitir")
        assert e.value.status == 404

    asyncio.run(esc())


def test_responder_false_deja_terminal_y_409(svc):
    async def esc():
        c = FakeConexion(ok=False)
        p = await svc.atender(pr(), "w1:p1", c)
        with pytest.raises(PermisoError) as e:
            await svc.decidir(p.id, "permitir")
        assert e.value.status == 409 and p.estado == "terminal"

    asyncio.run(esc())


def test_al_cambiar_al_crear_y_al_decidir(svc):
    async def esc():
        svc.cambios.clear()
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        assert len(svc.cambios) == 1
        await svc.decidir(p.id, "permitir")
        assert len(svc.cambios) == 2

    asyncio.run(esc())


def test_tool_input_no_dict_cierra_sin_pedido(svc):
    async def esc():
        msg = MensajeGancho(
            "PermissionRequest",
            "global",
            Ids(None, "w1:p1", None, None, "s1"),
            {
                "tool_name": "Bash",
                "tool_use_id": "t1",
                "tool_input": "not-a-dict",
                "cwd": "/home/u/p",
            },
        )
        c = FakeConexion()
        assert await svc.atender(msg, "w1:p1", c) is None and c.cerrada.is_set()

    asyncio.run(esc())


def test_por_id_evicta_cerrados_mas_alla_de_veinte(svc):
    async def esc():
        ids_creados = []
        for i in range(25):
            c = FakeConexion()
            p = await svc.atender(pr(tool_use_id=f"t{i}"), "w1:p1", c)
            ids_creados.append(p.id)
            await svc.decidir(p.id, "permitir")
        assert len(svc._por_id) == 20
        primero = ids_creados[0]
        assert svc.ver(primero) is None
        with pytest.raises(PermisoError) as e:
            await svc.decidir(primero, "permitir")
        assert e.value.status == 404

    asyncio.run(esc())


def test_decidir_cancelado_durante_responder_limpia_enviando(svc):
    class ConexionEsperando(FakeConexion):
        def __init__(self):
            super().__init__(bloquear=asyncio.Event())
            self.en_responder = asyncio.Event()

        async def responder(self, r):
            self.en_responder.set()
            return await super().responder(r)

    async def esc():
        c = ConexionEsperando()
        p = await svc.atender(pr(), "w1:p1", c)
        tarea = asyncio.create_task(svc.decidir(p.id, "permitir"))
        await c.en_responder.wait()
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea
        assert p.estado == "terminal"
        assert c.cerrada.is_set()
        abiertos = [x for x in svc.listar() if x["estado"] in ("abierto", "enviando")]
        assert abiertos == []

    asyncio.run(esc())


@pytest.fixture
def svc_timeout(tmp_path):
    cambios = []
    s = PermisosService(
        AuditoriaPermisos(tmp_path / "permisos.jsonl"),
        PaneLocks(),
        espera=lambda: 120.0,
        desde_app=lambda: True,
        al_cambiar=lambda: cambios.append(1),
        realpath=lambda p: p,
        responder_timeout=0.01,
    )
    return s


def test_responder_timeout_libera_lock_y_terminal(svc_timeout):
    async def esc():
        bloquear = asyncio.Event()
        c = FakeConexion(bloquear=bloquear)
        p = await svc_timeout.atender(pr(), "w1:p1", c)
        lock = svc_timeout.locks.get("w1:p1")
        with pytest.raises(PermisoError) as e:
            await svc_timeout.decidir(p.id, "permitir")
        assert e.value.status == 409 and p.estado == "terminal"
        assert not lock.locked()

    asyncio.run(esc())


def test_rechazo_motivo_redactado_en_auditoria(svc, tmp_path):
    async def esc():
        token = "abcdef0123456789abcdef"
        motivo = f"Bearer {token}"
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        await svc.decidir(p.id, "rechazar", motivo)
        texto = (tmp_path / "permisos.jsonl").read_text()
        assert token not in texto

    asyncio.run(esc())


@pytest.mark.parametrize(
    "evento,tool_use_id",
    [
        ("PostToolUse", "t1"),
        ("Stop", None),
        ("UserPromptSubmit", None),
    ],
)
def test_senal_resuelve_en_terminal(svc, evento, tool_use_id):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        svc.cambio.clear()
        await asyncio.wait_for(svc.senal("s1", evento, tool_use_id), 1)
        await asyncio.wait_for(svc.cambio.wait(), 1)
        assert p.estado == "terminal" and c.cerrada.is_set() and c.respuestas == []
        with pytest.raises(PermisoError) as e:
            await svc.decidir(p.id, "permitir")
        assert e.value.status == 409 and svc.abierto_para("s1") is None

    asyncio.run(esc())


def test_senal_otro_tool_use_misma_sesion_deja_abierto(svc):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(tool_use_id="t1"), "w1:p1", c)
        await svc.senal("s1", "PreToolUse", "t2")
        assert p.estado == "abierto"
        await svc.senal("s1", "PostToolUse", "t2")
        assert p.estado == "abierto"
        svc.cambio.clear()
        await svc.senal("s1", "PostToolUse", "t1")
        await asyncio.wait_for(svc.cambio.wait(), 1)
        assert p.estado == "terminal"

    asyncio.run(esc())


def test_atender_espera_lock_del_pane(svc):
    async def esc():
        lock = svc.locks.get("w1:p1")
        await lock.acquire()
        try:
            t = asyncio.create_task(svc.atender(pr(), "w1:p1", FakeConexion()))
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(t), 0.2)
        finally:
            lock.release()
        p = await asyncio.wait_for(t, 1)
        assert p is not None and p.estado == "abierto"

    asyncio.run(esc())


def test_senal_de_otra_sesion_no_resuelve(svc):
    async def esc():
        p = await svc.atender(pr(), "w1:p1", FakeConexion())
        await svc.senal("otra", "Stop", None)
        await svc.senal("s1", "PreToolUse", "t1")
        assert p.estado == "abierto"

    asyncio.run(esc())


def test_pane_blocked_al_crear_resuelve_cuando_herdr_pasa_a_working(tmp_path):
    cambio = asyncio.Event()

    async def esc():
        s = PermisosService(
            AuditoriaPermisos(tmp_path / "permisos.jsonl"),
            PaneLocks(),
            espera=lambda: 120.0,
            desde_app=lambda: True,
            al_cambiar=cambio.set,
            realpath=lambda p: p,
            estado_pane=lambda pane: "blocked" if pane == "w1:p1" else None,
        )
        p = await s.atender(pr(), "w1:p1", FakeConexion())
        assert p.visto_bloqueado is True
        cambio.clear()
        await s.observar_herdr("w1:p1", "working")
        await asyncio.wait_for(cambio.wait(), 1)
        assert p.estado == "terminal"

    asyncio.run(esc())


def test_write_largo_recorta_publico_y_auditoria_sin_cambiar_huella(tmp_path):
    cambio = asyncio.Event()
    contenido = "a" * 20000
    cwd = "/home/u/p"

    async def esc():
        s = PermisosService(
            AuditoriaPermisos(tmp_path / "permisos.jsonl"),
            PaneLocks(),
            espera=lambda: 120.0,
            desde_app=lambda: True,
            al_cambiar=cambio.set,
            realpath=lambda p: p,
        )
        msg = MensajeGancho(
            "PermissionRequest",
            "global",
            Ids(None, "w1:p1", None, None, "s1"),
            {
                "tool_name": "Write",
                "tool_use_id": "t_big",
                "tool_input": {"file_path": f"{cwd}/src/x.txt", "content": contenido},
                "cwd": cwd,
            },
        )
        p = await s.atender(msg, "w1:p1", FakeConexion())
        regla_completa = regla_acotada(
            "Write",
            {"file_path": f"{cwd}/src/x.txt", "content": contenido},
            cwd,
            realpath=lambda path: path,
        )
        assert p.regla.huella() == regla_completa.huella()
        pub = p.publico()["entrada"]["content"]
        assert len(pub) == 8000 + len("…[recortado 12000 caracteres]")
        assert pub.endswith("…[recortado 12000 caracteres]")
        linea = auditoria(tmp_path)[0]
        assert linea["entrada"]["content"] == pub

    asyncio.run(esc())


def test_dialogo_desaparece_segun_herdr(svc):
    async def esc():
        p = await svc.atender(pr(), "w1:p1", FakeConexion())
        await svc.observar_herdr("w1:p1", "working")
        assert p.estado == "abierto"
        await svc.observar_herdr("w1:p1", "blocked")
        svc.cambio.clear()
        await svc.observar_herdr("w1:p1", "working")
        await asyncio.wait_for(svc.cambio.wait(), 1)
        assert p.estado == "terminal"

    asyncio.run(esc())


def test_conexion_del_gancho_cerrada_resuelve(svc):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        svc.cambio.clear()
        c.cerrada.set()
        await asyncio.wait_for(svc.cambio.wait(), 1)
        assert p.estado == "terminal"

    asyncio.run(esc())


def test_pane_desaparece_conexion_cerrada_resuelve(svc):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        svc.cambio.clear()
        await svc.observar_herdr("w1:p1", None)
        await asyncio.wait_for(svc.cambio.wait(), 1)
        assert p.estado == "terminal" and svc.abierto_para("s1") is None

    asyncio.run(esc())


def test_vencimiento_sale_sin_decision_y_tardio_409(tmp_path):
    cambio = asyncio.Event()

    async def esc():
        s = PermisosService(
            AuditoriaPermisos(tmp_path / "permisos.jsonl"),
            PaneLocks(),
            espera=lambda: 0.05,
            desde_app=lambda: True,
            al_cambiar=cambio.set,
            realpath=lambda p: p,
        )
        c = FakeConexion()
        p = await s.atender(pr(), "w1:p1", c)
        cambio.clear()
        await asyncio.wait_for(cambio.wait(), 1)
        assert p.estado == "vencido" and c.cerrada.is_set()
        assert c.respuestas == [] and s.abierto_para("s1") is None
        with pytest.raises(PermisoError) as e:
            await s.decidir(p.id, "permitir")
        assert e.value.status == 409
        assert auditoria(tmp_path)[-1]["tipo"] == "vencido"

    asyncio.run(esc())


def test_reinicio_cierra_y_no_pierde_auditoria(svc, tmp_path):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        await svc.cerrar_todo()
        assert p.estado == "dialogo"
        assert c.cerrada.is_set() and c.respuestas == [] and svc.abierto_para("s1") is None
        assert svc._vigilancias == set() and svc._por_clave == {}
        tipos = [l["tipo"] for l in auditoria(tmp_path)]
        assert tipos[0] == "pedido" and "reinicio" in tipos
        assert not any(t.endswith("-allow") for t in tipos)
        assert all(l.get("quien") != "centinela" for l in auditoria(tmp_path))

    asyncio.run(esc())


def test_respuesta_tardia_a_gancho_ido(svc):
    async def esc():
        c = FakeConexion(ok=False)
        p = await svc.atender(pr(), "w1:p1", c)
        with pytest.raises(PermisoError) as e:
            await svc.decidir(p.id, "permitir")
        assert e.value.status == 409 and p.estado == "terminal" and svc.abierto_para("s1") is None

    asyncio.run(esc())


def test_vigilar_no_pisa_pedido_permitido(svc, tmp_path):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        await svc.decidir(p.id, "permitir")
        assert p.estado == "permitido"
        if svc._vigilancias:
            await asyncio.wait_for(
                asyncio.gather(*svc._vigilancias, return_exceptions=True),
                1,
            )
        assert p.estado == "permitido"
        assert svc._vigilancias == set()
        tipos = [l["tipo"] for l in auditoria(tmp_path)]
        assert "terminal" not in tipos and "vencido" not in tipos

    asyncio.run(esc())


def test_observar_herdr_otro_pane_no_resuelve(svc):
    async def esc():
        p = await svc.atender(pr(), "w1:p1", FakeConexion())
        await svc.observar_herdr("w2:p2", None)
        assert p.estado == "abierto"

    asyncio.run(esc())


def test_cerrar_todo_dos_veces_no_lanza(svc):
    async def esc():
        await svc.atender(pr(), "w1:p1", FakeConexion())
        await svc.cerrar_todo()
        await svc.cerrar_todo()

    asyncio.run(esc())


def test_senal_post_tool_use_otro_id_no_resuelve(svc):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(tool_use_id="t1"), "w1:p1", c)
        await svc.senal("s1", "PostToolUse", "otro")
        assert p.estado == "abierto" and not c.cerrada.is_set()

    asyncio.run(esc())


def test_senal_y_observar_no_pisan_enviando(svc):
    class ConexionEsperando(FakeConexion):
        def __init__(self):
            super().__init__(bloquear=asyncio.Event())
            self.en_responder = asyncio.Event()

        async def responder(self, r):
            self.en_responder.set()
            return await super().responder(r)

    async def esc():
        c = ConexionEsperando()
        p = await svc.atender(pr(), "w1:p1", c)
        t_dec = asyncio.create_task(svc.decidir(p.id, "permitir"))
        await c.en_responder.wait()
        assert p.estado == "enviando"
        await svc.senal("s1", "Stop", None)
        await svc.observar_herdr("w1:p1", None)
        assert p.estado == "enviando"
        c.bloquear.set()
        await t_dec
        assert p.estado == "permitido"

    asyncio.run(esc())


def test_senal_stop_dos_pedidos_abiertos_misma_sesion(tmp_path):
    cambio = asyncio.Event()

    async def esc():
        s = PermisosService(
            AuditoriaPermisos(tmp_path / "permisos.jsonl"),
            PaneLocks(),
            espera=lambda: 120.0,
            desde_app=lambda: True,
            al_cambiar=cambio.set,
            realpath=lambda p: p,
        )
        c1, c2 = FakeConexion(), FakeConexion()
        p1 = await s.atender(pr(tool_use_id="t1"), "w1:p1", c1)
        p2 = await s.atender(pr(tool_use_id="t2"), "w1:p1", c2)
        cambio.clear()
        await s.senal("s1", "Stop", None)
        await asyncio.wait_for(cambio.wait(), 1)
        assert p1.estado == "terminal" and p2.estado == "terminal"
        assert c1.cerrada.is_set() and c2.cerrada.is_set()

    asyncio.run(esc())


def test_carrera_decidir_senal_y_vencimiento_gana_decidir(tmp_path):
    cambio = asyncio.Event()

    async def esc():
        bloquear = asyncio.Event()
        s = PermisosService(
            AuditoriaPermisos(tmp_path / "permisos.jsonl"),
            PaneLocks(),
            espera=lambda: 0.01,
            desde_app=lambda: True,
            al_cambiar=cambio.set,
            realpath=lambda p: p,
        )
        c = FakeConexion(bloquear=bloquear)
        p = await s.atender(pr(), "w1:p1", c)
        en_responder = asyncio.Event()

        async def responder_bloqueado(r):
            en_responder.set()
            return await FakeConexion.responder(c, r)

        c.responder = responder_bloqueado

        t_dec = asyncio.create_task(s.decidir(p.id, "permitir"))
        await en_responder.wait()
        assert p.estado == "enviando"
        t_sen = asyncio.create_task(s.senal("s1", "Stop", None))
        await asyncio.wait_for(asyncio.gather(t_sen, return_exceptions=True), 1)
        bloquear.set()
        await t_dec
        assert p.estado == "permitido"
        assert len(c.respuestas) == 1
        tipos = [l["tipo"] for l in auditoria(tmp_path)]
        assert "terminal" not in tipos and "vencido" not in tipos

    asyncio.run(esc())


def test_cerrar_todo_con_enviando_al_liberar_queda_permitido(svc):
    class ConexionEsperando(FakeConexion):
        def __init__(self):
            super().__init__(bloquear=asyncio.Event())
            self.en_responder = asyncio.Event()

        async def responder(self, r):
            self.en_responder.set()
            return await super().responder(r)

    async def esc():
        c = ConexionEsperando()
        p = await svc.atender(pr(), "w1:p1", c)
        t_dec = asyncio.create_task(svc.decidir(p.id, "permitir"))
        await c.en_responder.wait()
        await svc.cerrar_todo()
        c.bloquear.set()
        await t_dec
        assert p.estado == "permitido"
        assert len(c.respuestas) == 1

    asyncio.run(esc())


def test_publico_no_recorta_command_y_recorta_listas_anidadas():
    from orquestador.permisos import _entrada_publica

    largo = "x" * 9000
    entrada = {
        "command": largo,
        "description": largo,
        "todos": [{"content": largo, "status": "pending"}],
        "edits": [{"old_string": largo, "new_string": "b"}],
    }
    pub = _entrada_publica(entrada)
    assert pub["command"] == largo
    assert pub["description"] == largo
    assert pub["todos"][0]["content"].endswith("…[recortado 1000 caracteres]")
    assert pub["todos"][0]["status"] == "pending"
    assert pub["edits"][0]["old_string"].endswith("…[recortado 1000 caracteres]")
    assert pub["edits"][0]["new_string"] == "b"
    assert entrada["todos"][0]["content"] == largo


def test_auditoria_registrar_fallido_deja_log(tmp_path, caplog, monkeypatch):
    from orquestador import permisos

    aud = permisos.AuditoriaPermisos(tmp_path / "permisos.jsonl")

    def boom(*a, **k):
        raise RuntimeError("disco roto")

    monkeypatch.setattr(permisos, "append_privado", boom)
    with caplog.at_level("WARNING", logger="orquestador.permisos"):
        assert aud.registrar("decision", None) is False
    assert any("disco roto" in r.getMessage() for r in caplog.records)


def test_servicio_sin_caminos_automaticos():
    params = set(inspect.signature(PermisosService.__init__).parameters)
    assert not params & {
        "decisor",
        "decisor_timeout",
        "aprobar_activo",
        "al_gris",
        "al_aprobar",
        "demora_gris",
    }
    for m in (
        "reclasificar",
        "subir",
        "objetar",
        "_clasificar",
        "_observar",
        "_programar_aviso_gris",
    ):
        assert not hasattr(PermisosService, m)


PROHIBIDOS_CENTINELA = {
    "interruptor",
    "decisor",
    "politica_permisos",
    "aprobador_gris",
    "transcripts_gris",
    "observacion_permisos",
}


def _modulos_importados(src):
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[-1])
            mods.update(a.name.split(".")[-1] for a in n.names)
        elif isinstance(n, ast.Import):
            mods.update(a.name.split(".")[-1] for a in n.names)
    return mods


def test_modulos_importados_cubre_import_y_from_punto():
    src = "from . import interruptor\nimport orquestador.decisor\nfrom .x import y"
    assert {"interruptor", "decisor"} <= _modulos_importados(src)


def test_app_y_permisos_no_importan_modulos_de_centinela():
    raiz = Path(orquestador.__file__).parent
    for nombre in ("app.py", "permisos.py"):
        mods = _modulos_importados((raiz / nombre).read_text())
        assert not mods & PROHIBIDOS_CENTINELA, nombre


@pytest.mark.parametrize("quien", ["politica", "centinela"])
def test_decidir_automatico_rechazado_sin_auditoria(svc, tmp_path, quien):
    async def esc():
        c = FakeConexion()
        p = await svc.atender(pr(), "w1:p1", c)
        antes = auditoria(tmp_path)
        with pytest.raises(PermisoError) as e:
            await svc.decidir(p.id, "permitir", quien=quien)
        assert e.value.status == 400
        assert p.estado == "abierto" and c.respuestas == []
        assert auditoria(tmp_path) == antes

    asyncio.run(esc())
