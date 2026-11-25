"""Canario transversal: ningún enganche de telemetría escribe contenido en disco."""
import ast
import asyncio
import logging
from pathlib import Path
import uuid

from orquestador import trabas_vigia
from orquestador.ganchos.mensaje import Ids, MensajeGancho
from orquestador.telemetria import Telemetria, TelemetriaHandler
from orquestador.telemetria_cierres import SeguidorCierres
from orquestador.telemetria_eventos import campos_pedido, codigo_traspaso
from orquestador.telemetria_respuesta import SeguidorRespuestas
from orquestador.trabas import Traba
from orquestador.trabas_vigia import VigiaTrabas

PROHIBIDOS = ("CANARIO", "glpat-", "4821", "/home/", "zyxusuario")
RUTA = "/home/zyxusuario/CANARIO-ruta-larga/proyecto"


def _stop(sid, texto, activo=False):
    return MensajeGancho("Stop", "global", Ids(None, None, None, None, sid),
                         {"last_assistant_message": texto, "stop_hook_active": activo})


def test_ningun_enganche_escribe_contenido(tmp_path, monkeypatch):
    tel = Telemetria(tmp_path / "tel", estricto=True)

    item = {"ts": 100.0, "carpeta": RUTA, "mensaje": "CANARIO glpat-CANARIOxxxxxxxxxxxx PIN-4821",
            "nombre": "CANARIO", "pestanas": [{"nombre": "CANARIO", "mensaje": "PIN-4821"}]}
    origen = {"via": "mcp", "nombre": "CANARIO glpat-CANARIOxxxxxxxxxxxx"}
    tel.anotar("pedido", **campos_pedido(item, origen, "rechazado", "CANARIO raro", 130.0))
    tel.anotar("comando_sesion", resultado="fallo", codigo=codigo_traspaso("CANARIO"), proyecto=None)

    reloj = [1000.0]
    seguidor = SeguidorRespuestas(tel.anotar, wall=lambda: reloj[0])
    seguidor.al_aviso({"kind": "asks", "session_id": "CANARIO-sid", "pane_id": "w9:CANARIO", "ts": 1000.0})
    reloj[0] = 1030.0
    seguidor.al_prompt("CANARIO-sid", "w9:CANARIO")
    seguidor.al_aviso({"kind": "blocked", "session_id": "CANARIO-sid2", "pane_id": "w9:CANARIO", "ts": 1000.0})
    seguidor.revisar(set())

    transcript = tmp_path / "s1.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(trabas_vigia, "detectar",
                        lambda *a, **k: [Traba("fallando", "CANARIO", 0.0, "CANARIO falló")])
    estado = {"status": "working"}
    vigia = VigiaTrabas(
        sesiones=lambda: [{"session_id": "CANARIO-sid", "pane_id": "w9:CANARIO", "title": "CANARIO",
                           "status": estado["status"]}],
        ruta=lambda sid: transcript, fondo=lambda sid: [], subagentes_activos=lambda sid: False,
        avisar=lambda sesion, traba: None, wall=lambda: 1000.0,
        al_traba=lambda ev: tel.anotar("traba", **ev),
    )
    asyncio.run(vigia.revisar())
    estado["status"] = "done"
    asyncio.run(vigia.revisar())

    cierres = SeguidorCierres(tel.anotar)
    cierres.al_stop(_stop("CANARIO-sid", "CANARIO sin bloque"))
    cierres.al_stop(_stop("CANARIO-sid", "CANARIO otra vez", activo=True))

    logger = logging.getLogger("orquestador.canario")
    handler = TelemetriaHandler(tel)
    logger.addHandler(handler)
    try:
        try:
            raise ValueError("CANARIO")
        except ValueError:
            logger.warning("falló %s en %s %s", "CANARIO", "/home/zyxusuario/CANARIO", uuid.uuid4(), exc_info=True)
        handler.flush()
    finally:
        logger.removeHandler(handler)

    archivos = [p for p in (tmp_path / "tel").rglob("*") if p.is_file()]
    assert archivos
    eventos = "".join(p.read_text(encoding="utf-8") for p in archivos)
    for evento in ("pedido", "comando_sesion", "respuesta", "traba", "cierre_frenado", "error_back"):
        assert f'"ev":"{evento}"' in eventos, evento
    for p in tmp_path.rglob("*"):
        if p.is_file():
            texto = p.read_text(encoding="utf-8", errors="replace")
            for prohibido in PROHIBIDOS:
                assert prohibido not in texto, (p.name, prohibido)


NIVELES = {"warning", "error", "exception", "critical"}
RAIZ = Path(__file__).resolve().parent.parent / "orquestador"


def _logs_con_fstring(directorio: Path) -> list[str]:
    hallazgos = []
    for ruta in sorted(directorio.rglob("*.py")):
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr in NIVELES and nodo.args and isinstance(nodo.args[0], ast.JoinedStr)):
                hallazgos.append(f"{ruta}:{nodo.lineno}")
    return hallazgos


def test_guardia_sin_fstring_en_logs_del_back():
    hallazgos = _logs_con_fstring(RAIZ)
    assert not hallazgos, "usá estilo %: la telemetría guarda la plantilla. Con f-string: " + ", ".join(hallazgos)


def test_guardia_detecta_fstring(tmp_path):
    (tmp_path / "malo.py").write_text('log.warning(f"falló {x}")\nlog.warning("ok %s", x)\n', encoding="utf-8")
    assert _logs_con_fstring(tmp_path) == [f"{tmp_path / 'malo.py'}:1"]
