"""Vigía de sesiones trabadas: timer propio, lectura incremental y un aviso por episodio. Solo lee."""
import asyncio
import inspect
import logging
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from .jsonl_incremental import JsonlReadState, read_new_lines
from .trabas import Traba, Umbrales, detectar

log = logging.getLogger("orquestador.trabas_vigia")
INTERVALO = 30.0
MAX_LINEAS = 600
# La primera lectura arranca en el último tramo del transcript: leerlo entero frena el loop y la memoria.
LECTURA_INICIAL = 4 * 1024 * 1024


def _estado_inicial(path: Path) -> Optional[JsonlReadState]:
    """Estado que arranca en la primera línea completa del último tramo, o None si el archivo es chico."""
    st = path.stat()
    if st.st_size <= LECTURA_INICIAL:
        return None
    with path.open("rb") as fh:
        fh.seek(st.st_size - LECTURA_INICIAL)
        fh.readline()
        offset = fh.tell()
    return JsonlReadState(inode=st.st_ino, offset=offset, mtime_ns=st.st_mtime_ns)


class VigiaTrabas:
    def __init__(
        self,
        *,
        sesiones: Callable[[], list],
        ruta: Callable[[str], Optional[Path]],
        fondo: Callable[[str], list],
        subagentes_activos: Callable[[str], bool],
        avisar: Callable[[dict, Traba], Awaitable[Any]],
        silenciada: Callable[[str], bool] = lambda sid: False,
        al_cambiar: Callable[[], None] = lambda: None,
        umbrales: Optional[Umbrales] = None,
        wall: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        intervalo: float = INTERVALO,
    ):
        self._sesiones = sesiones
        self._ruta = ruta
        self._fondo = fondo
        self._subagentes = subagentes_activos
        self._avisar = avisar
        self._silenciada = silenciada
        self._al_cambiar = al_cambiar
        self._umbrales = umbrales
        self._wall = wall
        self._sleep = sleep
        self._intervalo = intervalo
        self._cache: dict = {}
        self._activas: dict = {}
        self._trabas: dict = {}

    def traba_de(self, sid: str) -> Optional[dict]:
        trabas = self._trabas.get(sid)
        if not trabas:
            return None
        t = trabas[0]
        return {"tipo": t.tipo, "desde": t.desde, "detalle": t.detalle}

    def rearmar(self, sid: str) -> None:
        self._activas.pop(sid, None)
        ent = self._cache.get(sid)
        if ent is not None:
            # El prompt nuevo puede llegar al transcript después del gancho: lo anterior no vuelve a contar.
            ent["corte"] = len(ent["lineas"])
        if self._trabas.pop(sid, None):
            self._notificar_cambio()

    def _notificar_cambio(self) -> None:
        try:
            self._al_cambiar()
        except Exception:
            log.exception("al_cambiar falló")

    def _leer(self, sid: str, path: Path) -> Optional[tuple]:
        ent = self._cache.get(sid)
        try:
            estado = ent["estado"] if ent else _estado_inicial(path)
            nuevas, estado, reset = read_new_lines(path, estado)
            mtime = path.stat().st_mtime
        except OSError:
            return None
        if ent is None or reset:
            ent = {"estado": estado, "lineas": [], "corte": 0}
            self._cache[sid] = ent
        ent["estado"] = estado
        ent["lineas"].extend(b.decode("utf-8", errors="replace") for b in nuevas)
        if len(ent["lineas"]) > MAX_LINEAS:
            sobra = len(ent["lineas"]) - MAX_LINEAS
            del ent["lineas"][:sobra]
            ent["corte"] = max(0, ent["corte"] - sobra)
        return ent["lineas"][ent["corte"]:], mtime

    def _evaluar(self, sesion: dict) -> list:
        sid = sesion["session_id"]
        path = self._ruta(sid)
        if path is None:
            return []
        leido = self._leer(sid, path)
        if leido is None:
            return []
        lineas, mtime = leido
        return detectar(lineas, self._wall(), fondo=self._fondo(sid), subagentes_activos=self._subagentes(sid),
                        mtime=mtime, umbrales=self._umbrales)

    async def revisar(self, sid: Optional[str] = None) -> None:
        cambio = False
        vistos = set()
        for sesion in self._sesiones():
            s = sesion.get("session_id")
            if not s or (sid is not None and s != sid):
                continue
            vistos.add(s)
            if sesion.get("status") != "working":
                trabas = []
                self._cache.pop(s, None)
            else:
                try:
                    trabas = self._evaluar(sesion)
                except Exception:
                    log.exception("no pude evaluar trabas")
                    trabas = []
            claves = {(t.tipo, t.firma) for t in trabas}
            previas = self._activas.get(s, set())
            nuevas = [t for t in trabas if (t.tipo, t.firma) not in previas]
            self._activas[s] = claves
            if bool(trabas) != bool(self._trabas.get(s)) or [(t.tipo, t.firma) for t in trabas] != [
                    (t.tipo, t.firma) for t in self._trabas.get(s, [])]:
                cambio = True
            if trabas:
                self._trabas[s] = trabas
            else:
                self._trabas.pop(s, None)
            if nuevas and not self._silenciada(s):
                try:
                    res = self._avisar(sesion, nuevas[0])
                    if inspect.isawaitable(res):
                        await res
                except Exception:
                    log.exception("avisar traba falló")
        if sid is None:
            for s in [k for k in self._trabas if k not in vistos]:
                del self._trabas[s]
                self._activas.pop(s, None)
                self._cache.pop(s, None)
                cambio = True
        if cambio:
            self._notificar_cambio()

    async def run(self) -> None:
        while True:
            try:
                await self.revisar()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("vigía de trabas falló")
            await self._sleep(self._intervalo)
