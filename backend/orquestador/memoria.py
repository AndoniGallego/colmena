import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .config import Config
from .engram import HERRAMIENTAS as ENGRAM_LECTURA, EngramCliente, EngramError, argv_docker
from .memoria_indice import SESSION_RE, IndiceMemoria, leer, titulo_de
from .redaccion import redactar

THROTTLE_TABLERO = 60.0
REINDEXAR_CADA = 600.0
ENGRAM_TTL = 300.0
MAX_CITA = 2000


class Demasiado(RuntimeError):
    pass


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


class MemoriaService:
    def __init__(self, cfg: Config, data_directory: Path, clock: Callable[[], float] = time.monotonic,
                 engram_factory: Optional[Callable[[], Optional[EngramCliente]]] = None):
        self.cfg = cfg
        self.clock = clock
        self.indice = IndiceMemoria(data_directory / "memoria", cfg.projects_dir(),
                                    excluir=lambda: cfg.memoria_excluir if isinstance(cfg.memoria_excluir, list) else [],
                                    retencion_dias=lambda: cfg.memoria_retencion_dias)
        self._engram_factory = engram_factory or self._engram_docker
        self._ultimo_tablero: Optional[float] = None
        self._ultimo_reindex: Optional[float] = None
        self._engram_cache: Optional[tuple] = None

    @property
    def habilitada(self) -> bool:
        return self.cfg.memoria_habilitada is True

    def docker_bin(self) -> str:
        return self.cfg.docker_bin or shutil.which("docker") or ""

    def _engram_params(self) -> tuple[str, str, str]:
        docker = self.docker_bin()
        raw = self.cfg.engram if isinstance(self.cfg.engram, dict) else {}
        cont = str(raw.get("contenedor") or "").strip()
        proj = str(raw.get("proyecto") or "").strip()
        return docker, cont, proj

    def _engram_docker(self) -> Optional[EngramCliente]:
        docker, cont, proj = self._engram_params()
        if not docker or not cont or not proj:
            return None
        return EngramCliente(argv_docker(docker, cont, proj))

    def fondo(self) -> None:
        if self.habilitada and not self.indice.ocupado:
            threading.Thread(target=self.indice.actualizar, name="memoria-indice", daemon=True).start()

    def on_board(self, previous, board) -> None:
        now = self.clock()
        if self._ultimo_tablero is not None and now - self._ultimo_tablero < THROTTLE_TABLERO:
            return
        self._ultimo_tablero = now
        self.fondo()

    def reindexar(self) -> None:
        now = self.clock()
        if self._ultimo_reindex is not None and now - self._ultimo_reindex < REINDEXAR_CADA:
            raise Demasiado()
        self._ultimo_reindex = now
        threading.Thread(target=self._rehacer, name="memoria-reindex", daemon=True).start()

    def _rehacer(self) -> None:
        self.indice.borrar()
        self.indice.actualizar(esperar=True)

    def borrar(self) -> None:
        self.indice.borrar()

    def estado_engram(self) -> str:
        if not self.habilitada:
            return "deshabilitado"
        now = self.clock()
        if self._engram_cache and now - self._engram_cache[0] < ENGRAM_TTL:
            return self._engram_cache[1]
        cliente = self._engram_factory()
        valor = "caido"
        if cliente is not None:
            try:
                valor = "ok" if set(ENGRAM_LECTURA) <= set(cliente.herramientas()) else "caido"
            except EngramError:
                valor = "caido"
            finally:
                cliente.cerrar()
        self._engram_cache = (now, valor)
        return valor

    def estado(self) -> dict:
        return {"habilitada": self.habilitada, **self.indice.estado(), "actualizando": self.indice.ocupado,
                "engram": self.estado_engram()}

    def titulo(self, session_id: str) -> Optional[dict]:
        conn = self.indice.lectura() if SESSION_RE.match(session_id or "") else None
        if conn is None:
            return None
        try:
            return titulo_de(conn, session_id)
        except Exception:
            return None
        finally:
            conn.close()

    def cita_sesion(self, session_id: str, turno: int) -> Optional[dict]:
        conn = self.indice.lectura() if SESSION_RE.match(session_id or "") else None
        if conn is None:
            return None
        try:
            data = leer(conn, session_id, turno, 0)
        finally:
            conn.close()
        if not data or not data["turnos"]:
            return None
        t = data["turnos"][0]
        return {"tipo": "sesion", "session_id": session_id, "turno": turno, "titulo": redactar(data["titulo"]),
                "fecha": t["fecha"], "rol": t["rol"], "texto": _clip(redactar(t["texto"]), MAX_CITA)}

    def cita_engram(self, ident: int) -> Optional[dict]:
        cliente = self._engram_factory() if self.habilitada else None
        if cliente is None:
            return None
        try:
            texto = cliente.llamar("mem_get_observation", {"id": ident})
        except EngramError:
            return None
        finally:
            cliente.cerrar()
        return {"tipo": "engram", "id": ident, "texto": _clip(redactar(texto), MAX_CITA)}
