from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .estado_sesiones import EstadoSesiones
from .jsonl import append_privado


def _agentes(board: dict):
    for ws in board.get("workspaces", []):
        for tab in ws.get("tabs", []):
            yield from tab.get("agents", [])


def _duracion_valida(valor) -> bool:
    if isinstance(valor, bool):
        return False
    return isinstance(valor, (int, float))


class Sombra:
    def __init__(
        self,
        directorio: Path,
        clock=time.monotonic,
        wall=lambda: datetime.now(timezone.utc),
        umbral: float = 2.0,
    ):
        self.archivo = directorio / "ganchos-sombra.jsonl"
        self._clock = clock
        self._wall = wall
        self._umbral = umbral
        self._abiertas: dict[str, dict] = {}

    def _ahora(self) -> datetime:
        w = self._wall()
        if not isinstance(w, datetime):
            w = datetime.fromtimestamp(w, tz=timezone.utc)
        elif w.tzinfo is None:
            w = w.replace(tzinfo=timezone.utc)
        return w

    def _hora_iso(self) -> str:
        return self._ahora().isoformat()

    @staticmethod
    def _solo_done_idle(herdr: str, ganchos: str) -> bool:
        return herdr != ganchos and {herdr, ganchos} <= {"done", "idle"}

    def _registro_discrepancia(
        self,
        pane: str,
        session_id: str | None,
        herdr: str,
        ganchos: str,
    ) -> dict:
        return {
            "inicio": self._clock(),
            "hora_inicio": self._hora_iso(),
            "pane_id": pane,
            "session_id": session_id,
            "herdr": herdr,
            "ganchos": ganchos,
            "solo_done_idle": self._solo_done_idle(herdr, ganchos),
        }

    def _escribir_discrepancia(self, abierta: dict) -> None:
        duracion = self._clock() - abierta["inicio"]
        if duracion <= self._umbral:
            return
        append_privado(
            self.archivo,
            {
                "hora": abierta["hora_inicio"],
                "pane_id": abierta["pane_id"],
                "session_id": abierta.get("session_id"),
                "herdr": abierta["herdr"],
                "ganchos": abierta["ganchos"],
                "duracion": round(duracion, 1),
                "solo_done_idle": abierta["solo_done_idle"],
            },
        )

    def _consumir_ignorados(self, estados: EstadoSesiones) -> None:
        while estados.ignorados:
            estados.ignorados.popleft()
            append_privado(
                self.archivo,
                {
                    "hora": self._hora_iso(),
                    "evento": "idle_prompt",
                    "ignorado": True,
                },
            )

    def observar(self, board_herdr: dict, estados: EstadoSesiones | None) -> None:
        if estados is None:
            return
        self._consumir_ignorados(estados)
        panes_board: set[str] = set()
        for agent in _agentes(board_herdr):
            pane = agent.get("pane_id")
            if not pane:
                continue
            panes_board.add(pane)
            abierta = self._abiertas.get(pane)
            reg = estados.estado_de(pane)
            if reg is None:
                if abierta is not None:
                    self._escribir_discrepancia(abierta)
                    del self._abiertas[pane]
                continue
            herdr = agent.get("status") or "unknown"
            ganchos = reg.estado
            if herdr == ganchos:
                if abierta is not None:
                    self._escribir_discrepancia(abierta)
                    del self._abiertas[pane]
            elif abierta is None:
                sid = agent.get("session_id") or reg.session_id
                self._abiertas[pane] = self._registro_discrepancia(pane, sid, herdr, ganchos)
            elif abierta["herdr"] != herdr or abierta["ganchos"] != ganchos:
                self._escribir_discrepancia(abierta)
                sid = agent.get("session_id") or reg.session_id
                self._abiertas[pane] = self._registro_discrepancia(pane, sid, herdr, ganchos)
        for pane in list(self._abiertas):
            if pane not in panes_board:
                self._escribir_discrepancia(self._abiertas[pane])
                del self._abiertas[pane]

    def cerrar(self) -> None:
        for pane in list(self._abiertas):
            self._escribir_discrepancia(self._abiertas[pane])
            del self._abiertas[pane]

    def resumen(self, dias: int = 7) -> list[dict]:
        if not self.archivo.is_file():
            return []
        ahora = self._ahora()
        min_dia = ahora.date() - timedelta(days=dias - 1)
        buckets: dict[str, dict] = {}
        try:
            with self.archivo.open(encoding="utf-8") as f:
                for linea in f:
                    linea = linea.strip()
                    if not linea:
                        continue
                    try:
                        obj = json.loads(linea)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if obj.get("evento") == "idle_prompt":
                        continue
                    duracion = obj.get("duracion")
                    if not _duracion_valida(duracion):
                        continue
                    hora = obj.get("hora")
                    if not isinstance(hora, str):
                        continue
                    try:
                        dt = datetime.fromisoformat(hora.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt > ahora:
                        continue
                    if dt.date() < min_dia:
                        continue
                    dia = dt.date().isoformat()
                    bucket = buckets.setdefault(
                        dia, {"discrepancias": 0, "mayores_10s": 0, "solo_done_idle": 0}
                    )
                    bucket["discrepancias"] += 1
                    if duracion > 10:
                        bucket["mayores_10s"] += 1
                    if obj.get("solo_done_idle"):
                        bucket["solo_done_idle"] += 1
        except OSError:
            return []
        return [{"dia": dia, **buckets[dia]} for dia in sorted(buckets)]
