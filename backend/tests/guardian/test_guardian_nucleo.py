import asyncio
import json
import os
import signal
import uuid
from pathlib import Path

import pytest

from orquestador.guardian.lanzador import AjustesGuardian, escribir_hooks
from orquestador.guardian.nucleo import Guardian
from orquestador.guardian.protocolo import INVALIDO, NO_EXISTE, ErrorProtocolo
from orquestador.guardian.registro import Registro

pytestmark = pytest.mark.pty

FALSO = Path(__file__).resolve().parents[1] / "fixtures" / "falso_claude.py"


def _ajustes() -> AjustesGuardian:
    return AjustesGuardian(
        claude_bin=str(FALSO.resolve()),
        shell="/bin/sh",
        path=os.environ["PATH"],
        columnas=80,
        filas=24,
    )


def _guardian(tmp_path: Path, registro: Registro | None = None, **kw) -> Guardian:
    reg = registro or Registro(tmp_path / "registro.json")
    settings = escribir_hooks(tmp_path / "settings", 130)
    confiable = kw.pop("cwd_confiable", lambda c: True)
    entorno = kw.pop(
        "entorno",
        {"HOME": str(tmp_path), "HERDR_PANE_ID": "w1:p1", "CLAUDECODE": "1", "PATH": os.environ["PATH"]},
    )
    defaults = dict(
        demora_confianza=0.4,
        ventana_confianza=15.0,
        vida_minima=1.0,
        espera_listo=10.0,
    )
    defaults.update(kw)
    return Guardian(reg, _ajustes(), settings, entorno=entorno, cwd_confiable=confiable, **defaults)


class _EsperaEvento:
    def __init__(self) -> None:
        self._q: asyncio.Queue[dict] = asyncio.Queue()
        self._esc = None

    def _cb(self, ev: dict) -> None:
        self._q.put_nowait(ev)

    def enganchar(self, g: Guardian, salida: set[str] | None = None) -> None:
        self._esc = g.escuchar(self._cb, salida=salida or ())

    def cerrar(self) -> None:
        if self._esc:
            self._esc.cerrar()

    async def uno(self, evento: str, *, sesion: str | None = None, timeout: float = 8.0) -> dict:
        async def _match() -> dict:
            while True:
                ev = await self._q.get()
                if ev.get("evento") != evento:
                    continue
                if sesion is not None and ev.get("sesion") != sesion:
                    continue
                return ev

        return await asyncio.wait_for(_match(), timeout)

    async def hasta_leer(self, g: Guardian, sid: str, texto: str, timeout: float = 8.0) -> None:
        async def _poll() -> None:
            while texto not in g.leer(sid):
                await asyncio.sleep(0.05)

        await asyncio.wait_for(_poll(), timeout)


async def _shell_hola(g: Guardian, tmp_path: Path) -> tuple[str, int | None]:
    ev = _EsperaEvento()
    ev.enganchar(g)
    try:
        creado = await g.crear_espacio("demo", str(tmp_path))
        sid = creado["sesion_id"]
        await ev.uno("tablero")
        g.ejecutar(sid, "echo hola")
        await ev.hasta_leer(g, sid, "hola")
        proc = g.proceso(sid)
        pid = proc["shell_pid"]
        await g.cerrar(creado["linea_id"])
        return sid, pid
    finally:
        await g.apagar_ordenado(espera=2)
        ev.cerrar()


def test_shell_crear_ejecutar_cerrar(tmp_path):
    _, pid = asyncio.run(_shell_hola(g := _guardian(tmp_path), tmp_path))
    if pid is not None:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


async def _claude_nuevo(g: Guardian, tmp_path: Path) -> None:
    ev = _EsperaEvento()
    ev.enganchar(g)
    try:
        esp = await g.crear_espacio("e", str(tmp_path))
        res = await g.crear_linea(esp["espacio_id"], "claude", str(tmp_path), programa="claude")
        sid = res["sesion_id"]
        await asyncio.wait_for(g._sesiones[sid].listo.wait(), 8.0)
        args = json.loads((tmp_path / ".falso_args.json").read_text())
        assert args["colmena"] == sid
        assert args["herdr"] is False
        assert args["claudecode"] is False
        assert "--session-id" in args["argv"]
        uid = args["argv"][args["argv"].index("--session-id") + 1]
        uuid.UUID(uid)
        reg = g._registro.sesiones[sid]
        assert reg.claude_session_id == uid
        assert "--permission-mode" in args["argv"] and "auto" in args["argv"]
    finally:
        await g.apagar_ordenado(espera=2)
        ev.cerrar()


def test_claude_falso_nuevo(tmp_path):
    asyncio.run(_claude_nuevo(_guardian(tmp_path), tmp_path))


async def _confianza(g: Guardian, tmp_path: Path, *, con_dialogo: bool) -> str:
    if con_dialogo:
        (tmp_path / ".falso_confianza").write_text("0.2")
    ev = _EsperaEvento()
    ev.enganchar(g)
    try:
        esp = await g.crear_espacio("e", str(tmp_path))
        res = await g.crear_linea(esp["espacio_id"], "c", str(tmp_path), programa="claude")
        sid = res["sesion_id"]
        if g._cwd_confiable(str(tmp_path)):
            await asyncio.wait_for(g._sesiones[sid].listo.wait(), 8.0)
            assert g._sesiones[sid].estado == "idle"
        else:
            ev_est = await ev.uno("estado", sesion=sid)
            assert ev_est["estado"] == "blocked"
            assert g.proceso(sid)["es_claude"]
        return sid
    finally:
        await g.apagar_ordenado(espera=2)
        ev.cerrar()


def test_confianza_cwd_confiable(tmp_path):
    asyncio.run(_confianza(_guardian(tmp_path), tmp_path, con_dialogo=True))


def test_confianza_cwd_no_confiable(tmp_path):
    asyncio.run(
        _confianza(_guardian(tmp_path, cwd_confiable=lambda c: False), tmp_path, con_dialogo=True)
    )


async def _mandar_prompt(g: Guardian, tmp_path: Path) -> None:
    ev = _EsperaEvento()
    ev.enganchar(g)
    try:
        esp = await g.crear_espacio("e", str(tmp_path))
        res = await g.crear_linea(esp["espacio_id"], "c", str(tmp_path), programa="claude")
        sid = res["sesion_id"]
        await asyncio.wait_for(g._sesiones[sid].listo.wait(), 8.0)
        await g.mandar_prompt(sid, "hola mundo")
        await ev.hasta_leer(g, sid, "● respuesta a: hola mundo")
    finally:
        await g.apagar_ordenado(espera=2)
        ev.cerrar()


def test_mandar_prompt(tmp_path):
    asyncio.run(_mandar_prompt(_guardian(tmp_path), tmp_path))


async def _retomar(g1: Guardian, tmp_path: Path, reg: Registro) -> None:
    import shutil

    esp = await g1.crear_espacio("e", str(tmp_path))
    res_c = await g1.crear_linea(esp["espacio_id"], "c", str(tmp_path), programa="claude")
    sid_claude = res_c["sesion_id"]
    await asyncio.wait_for(g1._sesiones[sid_claude].listo.wait(), 8.0)
    uuid_claude = g1._registro.sesiones[sid_claude].claude_session_id

    borrado = tmp_path / "borrado"
    borrado.mkdir()
    res_p = await g1.crear_linea(esp["espacio_id"], "perd", str(borrado), programa="claude")
    sid_p = res_p["sesion_id"]
    await asyncio.wait_for(g1._sesiones[sid_p].listo.wait(), 8.0)

    await g1.apagar_ordenado(espera=2)

    g2 = _guardian(tmp_path, registro=reg)
    await g2.retomar()
    await asyncio.wait_for(g2._sesiones[sid_claude].listo.wait(), 10.0)
    args = json.loads((tmp_path / ".falso_args.json").read_text())
    assert "--resume" in args["argv"]
    assert uuid_claude in args["argv"]
    assert sid_claude in g2._sesiones
    await g2.apagar_ordenado(espera=2)

    shutil.rmtree(borrado)
    g3 = _guardian(tmp_path, registro=reg)
    await g3.retomar()
    assert g3._sesiones[sid_p].estado == "perdida"
    await g3.apagar_ordenado(espera=2)

    (tmp_path / ".falso_muere").write_text("1")
    g4 = _guardian(tmp_path, registro=reg)
    ev = _EsperaEvento()
    ev.enganchar(g4)
    await g4.retomar()
    await ev.uno("termino", sesion=sid_claude, timeout=8.0)
    assert g4._sesiones[sid_claude].estado == "perdida"
    await g4.apagar_ordenado(espera=2)
    ev.cerrar()


def test_retomar(tmp_path):
    reg = Registro(tmp_path / "registro.json")

    async def run():
        g1 = _guardian(tmp_path, registro=reg)
        await _retomar(g1, tmp_path, reg)

    asyncio.run(run())


async def _apagar_sin_vivos(g: Guardian, tmp_path: Path) -> None:
    esp = await g.crear_espacio("e", str(tmp_path))
    sid = esp["sesion_id"]
    pid = g.proceso(sid)["shell_pid"]
    await g.apagar_ordenado(espera=2)
    if pid:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_apagar_ordenado(tmp_path):
    asyncio.run(_apagar_sin_vivos(_guardian(tmp_path), tmp_path))


def test_teclas_invalido_y_no_existe(tmp_path):
    async def run():
        g = _guardian(tmp_path)
        try:
            esp = await g.crear_espacio("e", str(tmp_path))
            sid = esp["sesion_id"]
            await asyncio.wait_for(g._sesiones[sid].listo.wait(), 2.0)
        except Exception:
            pass
        with pytest.raises(ErrorProtocolo) as exc:
            g.teclas("g999:p999", ["enter"])
        assert exc.value.codigo == NO_EXISTE
        esp = await g.crear_espacio("e2", str(tmp_path))
        sid = esp["sesion_id"]
        with pytest.raises(ErrorProtocolo) as exc2:
            g.teclas(sid, ["f2"])
        assert exc2.value.codigo == INVALIDO
        await g.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_foto_no_existe(tmp_path):
    g = _guardian(tmp_path)
    with pytest.raises(ErrorProtocolo) as exc:
        g.foto("g999:p999")
    assert exc.value.codigo == NO_EXISTE
    asyncio.run(g.apagar_ordenado(espera=2))


async def _tablero_listo(g: Guardian, tmp_path: Path) -> None:
    ev = _EsperaEvento()
    ev.enganchar(g)
    try:
        esp = await g.crear_espacio("e", str(tmp_path))
        res = await g.crear_linea(esp["espacio_id"], "claude", str(tmp_path), programa="claude")
        sid = res["sesion_id"]

        def _ses() -> dict:
            return next(s for s in g.tablero()["sesiones"] if s["id"] == sid)

        assert _ses()["listo"] is False
        await asyncio.wait_for(g._sesiones[sid].listo.wait(), 8.0)
        assert _ses()["listo"] is True
        ev_est = await ev.uno("estado", sesion=sid)
        assert ev_est["estado"] == g._sesiones[sid].estado
    finally:
        await g.apagar_ordenado(espera=2)
        ev.cerrar()


def test_tablero_expone_listo(tmp_path):
    asyncio.run(_tablero_listo(_guardian(tmp_path), tmp_path))


def _modo_en(argv: list[str]) -> str:
    return argv[argv.index("--permission-mode") + 1]


def test_arrancar_claude_con_modo_lo_persiste_y_lo_usa_al_retomar(tmp_path):
    reg = Registro(tmp_path / "registro.json")

    async def run():
        g1 = _guardian(tmp_path, registro=reg)
        esp = await g1.crear_espacio("e", str(tmp_path))
        sid = esp["sesion_id"]
        res = await g1.arrancar_claude(sid, "pedida", modo="default")
        assert res["modo"] == "default"
        args = json.loads((tmp_path / ".falso_args.json").read_text())
        assert _modo_en(args["argv"]) == "default"
        assert reg.sesiones[sid].modo_permisos == "default"
        await g1.apagar_ordenado(espera=2)

        g2 = _guardian(tmp_path, registro=reg)
        await g2.retomar()
        await asyncio.wait_for(g2._sesiones[sid].listo.wait(), 10.0)
        args = json.loads((tmp_path / ".falso_args.json").read_text())
        assert "--resume" in args["argv"]
        assert _modo_en(args["argv"]) == "default"
        await g2.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_arrancar_claude_modo_invalido_no_lanza(tmp_path):
    async def run():
        g = _guardian(tmp_path)
        esp = await g.crear_espacio("e", str(tmp_path))
        sid = esp["sesion_id"]
        with pytest.raises(ErrorProtocolo) as exc:
            await g.arrancar_claude(sid, "x", modo="auto")
        assert exc.value.codigo == INVALIDO
        assert g._registro.sesiones[sid].programa == "shell"
        await g.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_arrancar_claude_sin_modo_usa_el_global(tmp_path):
    async def run():
        g = _guardian(tmp_path)
        esp = await g.crear_espacio("e", str(tmp_path))
        res = await g.arrancar_claude(esp["sesion_id"], "manual")
        assert res["modo"] is None
        args = json.loads((tmp_path / ".falso_args.json").read_text())
        assert _modo_en(args["argv"]) == "auto"
        await g.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_modo_endurecido_sigue_a_la_conversacion_al_retomarla_en_otra_sesion(tmp_path):
    """Retomar o mudar una conversación que nació de un pedido ajeno no la devuelve al modo global."""
    reg = Registro(tmp_path / "registro.json")

    async def run():
        g = _guardian(tmp_path, registro=reg)
        esp = await g.crear_espacio("e", str(tmp_path))
        sid = esp["sesion_id"]
        await g.arrancar_claude(sid, "pedida", modo="plan")
        uid = reg.sesiones[sid].claude_session_id
        await g.apagar_ordenado(espera=2)

        reg2 = Registro(tmp_path / "registro.json")
        reg2.cargar()
        reg2.sesiones.clear()  # sin la sesión original: solo queda la conversación
        g2 = _guardian(tmp_path, registro=reg2)
        esp2 = await g2.crear_espacio("otra", str(tmp_path))
        res = await g2.crear_linea(esp2["espacio_id"], "retomada", str(tmp_path), programa="claude", resume=uid)
        await asyncio.wait_for(g2._sesiones[res["sesion_id"]].listo.wait(), 10.0)
        args = json.loads((tmp_path / ".falso_args.json").read_text())
        assert "--resume" in args["argv"] and _modo_en(args["argv"]) == "plan"
        assert g2._registro.sesiones[res["sesion_id"]].modo_permisos == "plan"

        esp3 = await g2.crear_espacio("mudada", str(tmp_path))
        out = await g2.arrancar_claude(esp3["sesion_id"], "mudada", resume=uid)
        args = json.loads((tmp_path / ".falso_args.json").read_text())
        assert _modo_en(args["argv"]) == "plan" and out["modo"] == "plan"

        esp4 = await g2.crear_espacio("ajena", str(tmp_path))
        await g2.arrancar_claude(esp4["sesion_id"], "ajena", resume=str(uuid.uuid4()))
        args = json.loads((tmp_path / ".falso_args.json").read_text())
        assert _modo_en(args["argv"]) == "auto"
        await g2.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_copiloto_fuera_de_su_carpeta_no_lanza(tmp_path, monkeypatch):
    from orquestador.guardian import lanzador as lz

    monkeypatch.setattr(lz, "CARPETA_COPILOTO", tmp_path / "reunion-copiloto")

    async def run():
        g = _guardian(tmp_path)
        esp = await g.crear_espacio("e", str(tmp_path))
        sid = esp["sesion_id"]
        with pytest.raises(ErrorProtocolo) as exc:
            await g.arrancar_claude(sid, "x", modo="copiloto")
        assert exc.value.codigo == INVALIDO
        assert g._registro.sesiones[sid].programa == "shell"
        await g.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_copiloto_en_su_carpeta_lanza_con_args_de_solo_lectura_y_los_conserva_al_retomar(tmp_path, monkeypatch):
    from orquestador.guardian import lanzador as lz

    destino = tmp_path / "reunion-copiloto"
    destino.mkdir()
    monkeypatch.setattr(lz, "CARPETA_COPILOTO", destino)
    reg = Registro(tmp_path / "registro.json")

    async def run():
        g1 = _guardian(tmp_path, registro=reg)
        esp = await g1.crear_espacio("e", str(destino))
        sid = esp["sesion_id"]
        res = await g1.arrancar_claude(sid, "copiloto", modo="copiloto")
        assert res["modo"] == "copiloto"
        args = json.loads((destino / ".falso_args.json").read_text())["argv"]
        assert args[args.index("--permission-mode") + 1] == "dontAsk"
        assert args[args.index("--tools") + 1] == "Read,Grep,Glob,Bash"
        await g1.apagar_ordenado(espera=2)
        g2 = _guardian(tmp_path, registro=reg)
        await g2.retomar()
        await asyncio.wait_for(g2._sesiones[sid].listo.wait(), 10.0)
        args = json.loads((destino / ".falso_args.json").read_text())["argv"]
        assert "--resume" in args and "--tools" in args
        await g2.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_resume_de_copiloto_en_otra_carpeta_cae_a_default(tmp_path, monkeypatch):
    from orquestador.guardian import lanzador as lz

    monkeypatch.setattr(lz, "CARPETA_COPILOTO", tmp_path / "reunion-copiloto")
    reg = Registro(tmp_path / "registro.json")

    async def run():
        g = _guardian(tmp_path, registro=reg)
        esp = await g.crear_espacio("e", str(tmp_path))
        sid = esp["sesion_id"]
        reg.actualizar_sesion(sid, modo_permisos="copiloto")
        await g.arrancar_claude(sid, "x", modo=None)
        args = json.loads((tmp_path / ".falso_args.json").read_text())["argv"]
        assert "--tools" not in args and args[args.index("--permission-mode") + 1] == "default"
        await g.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_copiloto_lanza_con_add_dir_y_lo_conserva_al_retomar(tmp_path, monkeypatch):
    from orquestador.guardian import lanzador as lz

    destino = tmp_path / "reunion-copiloto"
    destino.mkdir()
    repo = tmp_path / "repo-elegido"
    repo.mkdir()
    monkeypatch.setattr(lz, "CARPETA_COPILOTO", destino)
    reg = Registro(tmp_path / "registro.json")

    async def run():
        g1 = _guardian(tmp_path, registro=reg)
        esp = await g1.crear_espacio("e", str(destino))
        sid = esp["sesion_id"]
        await g1.arrancar_claude(sid, "copiloto", modo="copiloto", dirs_extra=[str(repo), "relativa"])
        args = json.loads((destino / ".falso_args.json").read_text())["argv"]
        assert args[args.index("--add-dir") + 1] == os.path.realpath(repo)
        assert args.count("--add-dir") == 1
        await g1.apagar_ordenado(espera=2)
        g2 = _guardian(tmp_path, registro=reg)
        await g2.retomar()
        await asyncio.wait_for(g2._sesiones[sid].listo.wait(), 10.0)
        args = json.loads((destino / ".falso_args.json").read_text())["argv"]
        assert "--resume" in args and args[args.index("--add-dir") + 1] == os.path.realpath(repo)
        await g2.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_dirs_extra_con_otro_modo_se_rechaza(tmp_path):
    async def run():
        g = _guardian(tmp_path)
        esp = await g.crear_espacio("e", str(tmp_path))
        with pytest.raises(ErrorProtocolo) as exc:
            await g.arrancar_claude(esp["sesion_id"], "x", modo="default", dirs_extra=[str(tmp_path)])
        assert exc.value.codigo == INVALIDO
        await g.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_modo_guia_fuera_de_su_carpeta_se_rechaza(tmp_path, monkeypatch):
    from orquestador.guardian import lanzador as lz

    cop = tmp_path / "reunion-copiloto"
    cop.mkdir()
    monkeypatch.setattr(lz, "CARPETA_COPILOTO", cop)
    monkeypatch.setattr(lz, "CARPETA_GUIA", tmp_path / "guia")

    async def run():
        g = _guardian(tmp_path)
        esp = await g.crear_espacio("e", str(cop))
        sid = esp["sesion_id"]
        with pytest.raises(ErrorProtocolo) as exc:
            await g.arrancar_claude(sid, "x", modo="guia")
        assert exc.value.codigo == INVALIDO and "modo inválido" in str(exc.value)
        assert g._registro.sesiones[sid].programa == "shell"
        await g.apagar_ordenado(espera=2)

    asyncio.run(run())


def test_modo_guia_en_su_carpeta_arranca_sin_dirs_extra(tmp_path, monkeypatch):
    from orquestador.guardian import lanzador as lz

    destino = tmp_path / "guia"
    destino.mkdir()
    monkeypatch.setattr(lz, "CARPETA_GUIA", destino)

    async def run():
        g = _guardian(tmp_path)
        esp = await g.crear_espacio("e", str(destino))
        sid = esp["sesion_id"]
        with pytest.raises(ErrorProtocolo):
            await g.arrancar_claude(sid, "g", modo="guia", dirs_extra=[str(tmp_path)])
        res = await g.arrancar_claude(sid, "guia", modo="guia")
        assert res["modo"] == "guia"
        args = json.loads((destino / ".falso_args.json").read_text())["argv"]
        assert args[args.index("--tools") + 1] == "Read,Grep,Glob,Bash"
        assert "--add-dir" not in args
        await g.apagar_ordenado(espera=2)

    asyncio.run(run())
