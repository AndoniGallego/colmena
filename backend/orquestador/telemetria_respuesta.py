"""Mide cuánto tarda Ando en responder a un aviso de sesión (puro, sin contenido)."""
import time
from typing import Callable

from .push import EN_APP

VENTANA_COLMENA_S = 10
SIN_RESPUESTA_S = 24 * 3600


class SeguidorRespuestas:
    def __init__(self, anotar: Callable[..., object], wall: Callable[[], float] = time.time):
        self._anotar = anotar
        self._wall = wall
        self._pendientes: dict[str, tuple[float, str, bool, str | None]] = {}
        self._colmena: dict[str, float] = {}

    def al_aviso(self, entry: dict) -> None:
        try:
            sid = entry.get("session_id")
            if entry.get("kind") not in ("asks", "blocked") or not sid or entry.get("prueba"):
                return
            if sid in self._pendientes:
                return
            self._pendientes[sid] = (
                entry.get("ts") or self._wall(), entry["kind"],
                entry.get("motivo") == EN_APP, entry.get("pane_id"),
            )
        except Exception:
            pass

    def escribio_colmena(self, pane_id: str) -> None:
        try:
            self._colmena[pane_id] = self._wall()
        except Exception:
            pass

    def al_prompt(self, sid: str, pane_id: str | None) -> None:
        self._responder(sid, pane_id, "prompt")

    def al_permiso(self, sid: str) -> None:
        # Un permiso aprobado desde Colmena es un toque de Ando: cuenta aunque caiga en la ventana.
        self._responder(sid, None, "permiso")

    def _responder(self, sid: str, pane_id: str | None, via: str) -> None:
        try:
            pend = self._pendientes.get(sid)
            if pend is None:
                return
            ts, kind, en_app, pane_aviso = pend
            ahora = self._wall()
            pane = pane_id or pane_aviso
            if via == "prompt" and pane is not None:
                escrito = self._colmena.get(pane)
                if escrito is not None and ahora - escrito <= VENTANA_COLMENA_S:
                    return
            del self._pendientes[sid]
            self._anotar("respuesta", aviso=kind, resultado="respondio",
                         segundos=int(ahora - ts), via=via, en_app=en_app)
        except Exception:
            pass

    def revisar(self, sids_vivos: set[str]) -> None:
        try:
            ahora = self._wall()
            for sid, (ts, kind, en_app, _) in list(self._pendientes.items()):
                if sid in sids_vivos and ahora - ts <= SIN_RESPUESTA_S:
                    continue
                del self._pendientes[sid]
                try:
                    self._anotar("respuesta", aviso=kind, resultado="sin_respuesta",
                                 segundos=None, via=None, en_app=en_app)
                except Exception:
                    pass
        except Exception:
            pass
