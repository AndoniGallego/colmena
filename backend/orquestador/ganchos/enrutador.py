from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..estado_sesiones import dueno_de

if TYPE_CHECKING:
    from ..board import BoardHub
    from ..estado_sesiones import EstadoSesiones
    from ..permisos import PermisosService
    from .canal import Conexion
    from .mensaje import MensajeGancho

_LOG = logging.getLogger(__name__)
_EVENTOS_DETECTOR = frozenset({"PreToolUse", "PostToolUse", "PostToolUseFailure", "UserPromptSubmit"})


class Enrutador:
    def __init__(
        self,
        estados: EstadoSesiones,
        permisos: PermisosService,
        hub: BoardHub,
        *,
        post_tool_use=None,
        al_evento=None,
    ) -> None:
        self.estados = estados
        self.permisos = permisos
        self.hub = hub
        self.post_tool_use = post_tool_use
        self.al_evento = al_evento

    async def manejar(self, msg: MensajeGancho, conexion: Conexion) -> None:
        try:
            pane = dueno_de(msg.ids, self.hub.board)
            nuevo = self.estados.recibir(msg, pane)
            if msg.evento == "PostToolUse" and self.post_tool_use is not None:
                try:
                    self.post_tool_use(msg, pane)
                except Exception as exc:
                    _LOG.warning("aviso de sesión falló: %s", type(exc).__name__)
            if msg.evento in _EVENTOS_DETECTOR and self.al_evento is not None:
                try:
                    self.al_evento(msg, pane)
                except Exception as exc:
                    _LOG.warning("detector de trabas falló: %s", type(exc).__name__)
            if msg.evento != "PermissionRequest" and msg.ids.claude:
                await self.permisos.senal(msg.ids.claude, msg.evento, msg.tool_use_id)
            pedido = None
            if msg.evento == "PermissionRequest":
                if nuevo:
                    pedido = await self.permisos.atender(msg, pane, conexion)
                else:
                    conexion.cerrar()
            if nuevo:
                self.hub.reaplicar()
            if pedido is not None:
                if pedido.conexion is not conexion:
                    _LOG.debug("PermissionRequest duplicado")
                else:
                    await conexion.cerrada.wait()
        except Exception as exc:
            _LOG.warning(
                "enrutador no pudo manejar %s: %s", msg.evento, type(exc).__name__
            )
            conexion.cerrar()
