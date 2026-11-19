import asyncio
import hashlib
import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field

from .cierre import CierreBody, PreviewBody
from .config import private_write
from .enchufe import TerminalesError
from .enchufe.ids import PANE_RE, es_guardian, valido
from .enchufe.modelo import Lanzamiento, Tablero
from .locks import PaneLocks
from .terminales import AGENT_PROCS, _CLAUDE_ARG
from .traspaso import TraspasoError, _now
from .uso_claude import project_key

log = logging.getLogger(__name__)

MUDANZA_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_MUDANZAS = 200
# "cerrando" que sobrevive a un reinicio: no se sabe si llegó a cerrar, se resuelve con Volver a abrir.
PENDIENTES = ("pendiente", "sin_confirmar", "cerrando")


class MudanzaBody(BaseModel):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    pane_id: str = Field(..., max_length=64)
    confirmado: Literal[True]


class MudarTodasBody(BaseModel):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    pane_ids: list[str] = Field(..., min_length=1, max_length=30)
    confirmado: Literal[True]


class RetomarBody(BaseModel):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    mudanza_id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    confirmado: Literal[True]


_REMAPEO_KEYS = frozenset({"pane_id", "pane", "desde", "hacia"})


def remapear_en(obj, viejo: str, nuevo: str) -> int:
    n = 0
    if isinstance(obj, dict):
        if "sesiones" in obj and isinstance(obj["sesiones"], list):
            for i, v in enumerate(obj["sesiones"]):
                if v == viejo:
                    obj["sesiones"][i] = nuevo
                    n += 1
        if "panes" in obj and isinstance(obj["panes"], dict):
            if viejo in obj["panes"]:
                obj["panes"][nuevo] = obj["panes"].pop(viejo)
                n += 1
        for k, v in list(obj.items()):
            if k in _REMAPEO_KEYS and v == viejo:
                obj[k] = nuevo
                n += 1
            elif k not in ("sesiones", "panes"):
                n += remapear_en(v, viejo, nuevo)
    elif isinstance(obj, list):
        for item in obj:
            n += remapear_en(item, viejo, nuevo)
    return n


def pid_vivo_proc(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return False
    parts = stat.split()
    if len(parts) < 3:
        return False
    return parts[2] != "Z"


class MudanzaStore:
    def __init__(self, path: Path, clock: Callable[[], float] = time.time):
        self.path = path
        self.clock = clock
        self._items: list[dict] = []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._items = [
                    i for i in data
                    if isinstance(i, dict) and MUDANZA_ID_RE.match(str(i.get("id", "")))
                ]
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        del self._items[:-MAX_MUDANZAS]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        private_write(self.path, json.dumps(self._items, ensure_ascii=False, indent=1))

    def get(self, ident: str) -> dict | None:
        for i in self._items:
            if i.get("id") == ident:
                return dict(i)
        return None

    def guardar(self, entry: dict) -> None:
        ident = entry.get("id")
        for idx, i in enumerate(self._items):
            if i.get("id") == ident:
                self._items[idx] = dict(entry)
                self._save()
                return
        self._items.append(dict(entry))
        self._save()

    def pendientes(self) -> list[dict]:
        return [dict(i) for i in self._items if i.get("estado") in PENDIENTES]

    def _tiene_lote(self, lote_id: str) -> bool:
        return any(i.get("lote_id") == lote_id for i in self._items)


def _linea(tablero: Tablero, linea_id: str):
    return next((l for l in tablero.lineas if l.id == linea_id), None)


def _espacio(tablero: Tablero, espacio_id: str):
    return next((e for e in tablero.espacios if e.id == espacio_id), None)


def _nombre_sesion(tablero: Tablero, sesion) -> str:
    linea = _linea(tablero, sesion.linea_id)
    if linea and (linea.nombre or "").strip():
        return linea.nombre.strip()
    for attr in ("nombre_agente", "titulo"):
        val = getattr(sesion, attr, None) or ""
        if str(val).strip():
            return str(val).strip()
    return "Claude"


def _workspace_nombre(tablero: Tablero, sesion) -> str:
    esp = _espacio(tablero, sesion.espacio_id)
    return ((esp.nombre if esp else "") or "").strip() or "Herdr"


def _elegible(tablero: Tablero, sesion, estado_ganchos: Callable[[str], str | None]) -> str:
    if sesion.programa != "claude":
        return "No es una sesión de Claude"
    if not sesion.claude_session_id:
        return "No sé qué conversación tiene abierta"
    if sesion.estado not in ("idle", "done") or estado_ganchos(sesion.id) in ("working", "blocked"):
        return "Está trabajando o esperando una respuesta"
    linea = _linea(tablero, sesion.linea_id)
    if linea is None or len(linea.sesiones) != 1 or linea.declaradas not in (None, 1):
        return "Comparte el tab con otras terminales: cerralas primero"
    return ""


def _claude_pids_y_cwd(info) -> tuple[list[int], str | None]:
    pids: list[int] = []
    cwd: str | None = None
    for proc in info.procesos:
        name = str(proc.nombre or "").rsplit("/", 1)[-1].casefold()
        argv = proc.argv or ()
        es = name in AGENT_PROCS or any(
            isinstance(a, str) and _CLAUDE_ARG.search(a) for a in argv[:3]
        )
        if es and proc.pid:
            pids.append(proc.pid)
            if cwd is None and proc.cwd:
                cwd = proc.cwd
    if not pids and info.es_claude and info.pid:
        pids = [info.pid]
        cwd = cwd or info.cwd
    if cwd is None:
        cwd = info.cwd
    return pids, cwd


def _abierta_en(tablero: Tablero, sid: str) -> bool:
    return any(s.claude_session_id == sid and s.estado not in ("terminada", "perdida") for s in tablero.sesiones)


def _cierre_id(mudanza_id: str) -> str:
    return f"mud{hashlib.sha1(mudanza_id.encode()).hexdigest()[:20]}"


class MudanzaService:
    def __init__(
        self,
        *,
        herdr,
        guardian,
        cierre,
        locks: PaneLocks,
        store: MudanzaStore,
        estado_ganchos,
        transcript,
        pid_vivo,
        remapeos=(),
        al_mudar=None,
        sleep=asyncio.sleep,
        confirmar_timeout=8.0,
        paso=0.25,
        arranque_espera=3.0,
    ):
        self.herdr = herdr
        self.guardian = guardian
        self.cierre = cierre
        self.locks = locks
        self.store = store
        self.estado_ganchos = estado_ganchos
        self.transcript = transcript
        self.pid_vivo = pid_vivo
        self.remapeos = list(remapeos)
        self.al_mudar = al_mudar
        self.sleep = sleep
        self.confirmar_timeout = confirmar_timeout
        self.paso = paso
        self.arranque_espera = arranque_espera
        self._inflight: set[str] = set()
        self._retomar_inflight: set[str] = set()

    def _pendientes(self) -> list[dict]:
        return [e for e in self.store.pendientes() if e.get("id") not in self._inflight]

    async def _tablero_guardian(self, g) -> Tablero:
        try:
            return await g.tablero()
        except (TerminalesError, OSError):
            raise TraspasoError(503, "La terminal propia no responde: no toqué nada")

    async def _guardian_disponible(self, sin_tocar: bool = False) -> object:
        g = self.guardian()
        if g is None:
            msg = "No hay terminal propia configurada"
            if sin_tocar:
                msg += ": no toqué nada"
            raise TraspasoError(503, msg)
        try:
            await g.tablero()
        except (TerminalesError, OSError):
            msg = "La terminal propia no responde"
            if sin_tocar:
                msg += ": no toqué nada"
            raise TraspasoError(503, msg)
        return g

    async def candidatas(self) -> dict:
        g = self.guardian()
        if g is None:
            return {"disponible": False, "motivo": "No hay terminal propia configurada",
                    "sesiones": [], "pendientes": self._pendientes()}
        try:
            await g.tablero()
        except (TerminalesError, OSError):
            return {"disponible": False, "motivo": "La terminal propia no responde",
                    "sesiones": [], "pendientes": self._pendientes()}
        sesiones_out: list[dict] = []
        try:
            tab = await self.herdr.tablero()
        except (TerminalesError, OSError):
            tab = None
        if tab is not None:
            for ses in tab.sesiones:
                if es_guardian(ses.id) or ses.programa != "claude":
                    continue
                motivo = _elegible(tab, ses, self.estado_ganchos)
                sesiones_out.append({
                    "pane_id": ses.id,
                    "session_id": ses.claude_session_id,
                    "nombre": _nombre_sesion(tab, ses),
                    "workspace": _workspace_nombre(tab, ses),
                    "puede": not motivo,
                    "motivo": motivo,
                })
        return {"disponible": True, "motivo": "", "sesiones": sesiones_out,
                "pendientes": self._pendientes()}

    async def _pane_en_herdr(self, pane: str) -> bool | None:
        try:
            tab = await self.herdr.tablero()
        except (TerminalesError, OSError):
            return None
        return any(s.id == pane for s in tab.sesiones)

    async def _confirmar_cierre(self, pane: str, pids: list[int]) -> bool:
        intentos = max(1, math.ceil(self.confirmar_timeout / self.paso))
        for _ in range(intentos):
            try:
                tab = await self.herdr.tablero()
                pane_gone = not any(s.id == pane for s in tab.sesiones)
            except (TerminalesError, OSError):
                pane_gone = False
            pids_muertos = all(not self.pid_vivo(pid) for pid in pids)
            if pane_gone and pids_muertos:
                return True
            await self.sleep(self.paso)
        return False

    async def _arrancar(self, g, entry: dict) -> str:
        ws_nombre = entry["workspace"]
        nombre = entry["nombre"]
        cwd = entry["cwd"]
        sid = entry["session_id"]
        gtab = await g.tablero()
        espacio = next(
            (e for e in gtab.espacios
             if e.nombre.strip().casefold() == ws_nombre.strip().casefold()),
            None,
        )
        if espacio is not None:
            creado = await g.crear_linea(espacio.id, nombre, cwd, Lanzamiento("claude", resume=sid))
            await self._verificar_arranque(g, creado.sesion_id, creado.linea_id)
            return creado.sesion_id
        creado = await g.crear_espacio(ws_nombre, cwd)
        nuevo = creado.sesion_id
        try:
            await g.arrancar_claude(nuevo, nombre, resume=sid)
        except Exception:
            try:
                if creado.espacio_id:
                    await g.cerrar(creado.espacio_id)
            except Exception:
                log.warning("Mudanza: no se pudo cerrar el espacio creado", exc_info=True)
            raise
        if creado.linea_id and nombre.strip().casefold() != ws_nombre.strip().casefold():
            try:
                await g.renombrar(creado.linea_id, nombre)
            except Exception:
                log.warning("Mudanza: no se pudo renombrar la línea", exc_info=True)
        await self._verificar_arranque(g, nuevo, creado.espacio_id)
        return nuevo

    async def _verificar_arranque(self, g, sesion_id: str, cerrar_id: str | None) -> None:
        # claude --resume que no encuentra la conversación sale enseguida: la mudanza no está hecha.
        intentos = max(1, math.ceil(self.arranque_espera / self.paso))
        for _ in range(intentos):
            try:
                tab = await g.tablero()
            except (TerminalesError, OSError):
                await self.sleep(self.paso)
                continue
            ses = next((s for s in tab.sesiones if s.id == sesion_id), None)
            if ses is None or ses.estado in ("terminada", "perdida"):
                if cerrar_id:
                    try:
                        await g.cerrar(cerrar_id)
                    except Exception:
                        log.warning("Mudanza: no se pudo cerrar la terminal que no arrancó", exc_info=True)
                raise TerminalesError("Claude no pudo retomar la conversación en la terminal propia")
            await self.sleep(self.paso)

    def _finalizar_ok(self, entry: dict, pane_viejo: str, nuevo: str) -> dict:
        entry["pane_nuevo"] = nuevo
        entry["estado"] = "ok"
        entry.pop("error", None)
        entry.setdefault("remapeos", {})
        for nombre, fn in self.remapeos:
            try:
                entry["remapeos"][nombre] = fn(pane_viejo, nuevo)
            except Exception as exc:
                log.warning("remapeo %s falló: %s", nombre, exc)
                entry["remapeos"][nombre] = "error"
        self.store.guardar(entry)
        if self.al_mudar:
            try:
                self.al_mudar(dict(entry))
            except Exception as exc:
                log.warning("al_mudar falló: %s", exc)
        log.info("mudanza ok %s → %s", pane_viejo, nuevo)
        return {"ok": True, "mudanza": dict(entry)}

    async def mudar(self, body: MudanzaBody, lote_id: str = "") -> dict:
        pane = body.pane_id
        if es_guardian(pane):
            raise TraspasoError(400, "Esa sesión ya está en la terminal propia")
        if not valido(PANE_RE, pane):
            raise TraspasoError(400, "Sesión inválida")
        if body.id in self._inflight or self.store.get(body.id) is not None:
            raise TraspasoError(409, "Esa mudanza ya se hizo")
        self._inflight.add(body.id)
        try:
            g = await self._guardian_disponible(sin_tocar=True)
            async with self.locks.structure:
                async with self.locks.get(pane):
                    return await self._mudar_locked(body, pane, lote_id, g)
        finally:
            self._inflight.discard(body.id)

    async def _mudar_locked(self, body: MudanzaBody, pane: str, lote_id: str, g) -> dict:
        try:
            tab = await self.herdr.tablero()
        except (TerminalesError, OSError):
            raise TraspasoError(502, "Herdr no responde: no toqué nada")
        ses = next((s for s in tab.sesiones if s.id == pane), None)
        if ses is None:
            raise TraspasoError(404, "Esa sesión ya no está abierta")
        motivo = _elegible(tab, ses, self.estado_ganchos)
        if motivo:
            raise TraspasoError(409, motivo)
        sid = ses.claude_session_id
        nombre = _nombre_sesion(tab, ses)
        ws_nombre = _workspace_nombre(tab, ses)
        gtab = await self._tablero_guardian(g)
        if _abierta_en(gtab, sid):
            raise TraspasoError(409, "Esa conversación ya está abierta en la terminal propia")
        try:
            info = await self.herdr.proceso(pane)
        except (TerminalesError, OSError):
            raise TraspasoError(409, "No pude ver el proceso de Claude: no toqué nada")
        pids, cwd_proc = _claude_pids_y_cwd(info)
        if not pids:
            raise TraspasoError(409, "No pude ver el proceso de Claude: no toqué nada")
        cwd = cwd_proc or ses.cwd_primer_plano or ses.cwd
        p = self.transcript(sid)
        if p is None:
            raise TraspasoError(409, "No encuentro la conversación guardada: no la muevo")
        if p.parent.name != project_key(Path(cwd)):
            raise TraspasoError(409, "La conversación está guardada en otra carpeta: no la muevo")
        if self.estado_ganchos(pane) in ("working", "blocked"):
            raise TraspasoError(409, "Se puso a trabajar: no toqué nada")
        prev = await self.cierre.preview(PreviewBody(tipo="tab", target_id=ses.linea_id))
        if prev["bloqueantes"]:
            raise TraspasoError(409, "Se puso a trabajar: no toqué nada")
        if [p["pane_id"] for p in prev["panes"]] != [pane]:
            raise TraspasoError(409, "Comparte el tab con otras terminales: cerralas primero")
        entry: dict = {
            "id": body.id,
            "ts": _now(),
            "pane_viejo": pane,
            "pane_nuevo": None,
            "session_id": sid,
            "nombre": nombre,
            "workspace": ws_nombre,
            "cwd": cwd,
            "pids": pids,
            "estado": "cerrando",
            "remapeos": {},
        }
        if lote_id:
            entry["lote_id"] = lote_id
        self.store.guardar(entry)
        cbody = CierreBody(
            id=_cierre_id(body.id),
            tipo="tab",
            target_id=ses.linea_id,
            huella=prev["huella"],
            origen="manual",
            por_que="Pasa a la terminal propia",
            confirmado_por="usuario",
            sin_guardar=True,
        )
        try:
            await self.cierre._close(cbody, {pane})
        except TraspasoError as exc:
            still = await self._pane_en_herdr(pane)
            if still is True:
                entry["estado"] = "abortada"
                entry["error"] = str(exc.detail)[:300]
                self.store.guardar(entry)
                raise
        if not await self._confirmar_cierre(pane, pids):
            entry["estado"] = "sin_confirmar"
            entry["error"] = "No pude confirmar que Claude terminó en Herdr"
            self.store.guardar(entry)
            raise TraspasoError(
                502,
                f"Cerré la sesión en Herdr pero no pude confirmar que terminó, así que no la abrí "
                f"en la terminal propia. La conversación está guardada ({sid}); revisá Herdr y después "
                f"usá Volver a abrir.",
            )
        try:
            nuevo = await self._arrancar(g, entry)
        except Exception as exc:
            entry["estado"] = "pendiente"
            entry["error"] = str(exc)[:300]
            self.store.guardar(entry)
            log.warning("arranque en guardián falló: %s", exc)
            raise TraspasoError(
                502,
                f"Cerré la sesión en Herdr pero la terminal propia no pudo retomarla. "
                f"La conversación no se perdió ({sid}): usá Volver a abrir cuando la terminal propia ande.",
            )
        return self._finalizar_ok(entry, pane, nuevo)

    async def mudar_todas(self, body: MudarTodasBody) -> dict:
        if body.id in self._inflight or self.store._tiene_lote(body.id):
            raise TraspasoError(409, "Esa mudanza ya se hizo")
        await self._guardian_disponible(sin_tocar=True)
        panes = list(dict.fromkeys(body.pane_ids))
        mudadas: list[dict] = []
        saltadas: list[dict] = []
        fallidas: list[dict] = []
        frenado = False
        for i, pane in enumerate(panes, start=1):
            if frenado:
                saltadas.append({"pane_id": pane, "motivo": "Frené: la terminal propia falló con la anterior"})
                continue
            sub_id = f"{body.id[:56]}-{i:02d}"
            try:
                out = await self.mudar(MudanzaBody(id=sub_id, pane_id=pane, confirmado=True), lote_id=body.id)
                mudadas.append(out["mudanza"])
            except TraspasoError as exc:
                if 400 <= exc.status < 500:
                    saltadas.append({"pane_id": pane, "motivo": exc.detail})
                else:
                    fallidas.append({"pane_id": pane, "motivo": exc.detail})
                    frenado = True
        return {"ok": not fallidas, "mudadas": mudadas, "saltadas": saltadas, "fallidas": fallidas}

    async def retomar(self, body: RetomarBody) -> dict:
        if body.id in self._retomar_inflight:
            raise TraspasoError(409, "Esa mudanza ya se hizo")
        entry = self.store.get(body.mudanza_id)
        if entry is None:
            raise TraspasoError(404, "No encuentro esa mudanza")
        if entry.get("retomado_por") == body.id:
            raise TraspasoError(409, "Esa mudanza ya se hizo")
        if entry.get("estado") not in PENDIENTES or body.mudanza_id in self._inflight:
            raise TraspasoError(409, "Esa mudanza no está pendiente")
        self._retomar_inflight.add(body.id)
        try:
            g = await self._guardian_disponible(sin_tocar=True)
            pane_viejo = entry["pane_viejo"]
            sid = entry["session_id"]
            async with self.locks.structure:
                async with self.locks.get(pane_viejo):
                    return await self._retomar_locked(body, entry, g, pane_viejo, sid)
        finally:
            self._retomar_inflight.discard(body.id)

    async def _retomar_locked(self, body: RetomarBody, entry: dict, g, pane_viejo: str, sid: str) -> dict:
        entry = self.store.get(body.mudanza_id) or entry
        if entry.get("estado") not in PENDIENTES:
            raise TraspasoError(409, "Esa mudanza no está pendiente")
        try:
            tab = await self.herdr.tablero()
        except (TerminalesError, OSError):
            raise TraspasoError(502, "Herdr no responde: no abrí nada")
        if any(s.claude_session_id == sid for s in tab.sesiones if s.claude_session_id):
            raise TraspasoError(409, "Esa conversación sigue abierta en Herdr: no la abro de nuevo")
        if any(s.id == pane_viejo for s in tab.sesiones):
            raise TraspasoError(409, "Esa conversación sigue abierta en Herdr: no la abro de nuevo")
        for pid in entry.get("pids") or ():
            if self.pid_vivo(pid):
                raise TraspasoError(409, "Claude todavía no terminó en Herdr: no la abro de nuevo")
        gtab = await self._tablero_guardian(g)
        if _abierta_en(gtab, sid):
            raise TraspasoError(409, "Esa conversación ya está abierta en la terminal propia")
        try:
            nuevo = await self._arrancar(g, entry)
        except Exception as exc:
            entry["estado"] = "pendiente"
            entry["error"] = str(exc)[:300]
            self.store.guardar(entry)
            log.warning("retomar en guardián falló: %s", exc)
            raise TraspasoError(
                502,
                f"Cerré la sesión en Herdr pero la terminal propia no pudo retomarla. "
                f"La conversación no se perdió ({sid}): usá Volver a abrir cuando la terminal propia ande.",
            )
        entry["retomado_por"] = body.id
        return self._finalizar_ok(entry, pane_viejo, nuevo)
