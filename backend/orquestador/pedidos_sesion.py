"""Pedidos de una sesión a Colmena (abrir, cerrar, Cursor): misma lógica para la marca `[colmena-pestana]` y el MCP.

Cada método valida, crea el pedido en el store y manda el push. Devuelve `(item, motivo)`: el item creado, o el
motivo por el que no se creó. La marca ignora el resultado (el aviso al origen lo da el store); el MCP lo devuelve.
"""
import logging
import re
from typing import Any, Callable, Optional

from .cierre import PreviewBody
from .mensaje import MAX_TEXT
from .nueva_terminal import es_repo_colmena, validar_carpeta
from .pedido_cierre import resolver_objetivo, resumen_cierre
from .traspaso import TraspasoError

log = logging.getLogger("orquestador.app")

_TICKET_RE = re.compile(r"^[A-Z][A-Z0-9]{0,9}-\d{1,7}$")

Resultado = tuple[Optional[dict], Optional[str]]


class PedidosSesion:
    def __init__(self, store, board: Callable[[], Optional[dict]], cfg, push, spawn: Callable, cierres) -> None:
        self.store = store
        self.board = board
        self.cfg = cfg
        self.push = push
        self.spawn = spawn
        self.cierres = cierres

    @staticmethod
    def _origen(pane: str, sid: str, nombre: str, via: Optional[str] = None) -> dict:
        origen = {"pane_id": pane, "nombre": nombre, "session_id": sid}
        if via:
            origen["via"] = via
        return origen

    # --- cerrar ---

    def terminal_comun(self, sel: str) -> dict | None:
        """Busca en el tablero una terminal común por pane_id o, sin distinguir mayúsculas, por su título o
        el nombre de su pestaña. Las sesiones de Claude no están en esa lista; si hay más de una, no elige."""
        clave = sel.strip().casefold()
        halladas: dict = {}
        for ws in (self.board() or {}).get("workspaces") or []:
            for tab in ws.get("tabs") or []:
                for t in tab.get("terminales") or []:
                    if t.get("protegida") or not t.get("pane_id"):
                        continue
                    nombres = {(t.get("titulo") or "").strip().casefold(), (tab.get("label") or "").strip().casefold()}
                    if t["pane_id"] == sel.strip() or clave in nombres - {""}:
                        donde = " / ".join(x for x in (ws.get("label"), tab.get("label")) if x)
                        halladas[t["pane_id"]] = {
                            "pane_id": t["pane_id"],
                            # Para comparar al aprobar: si el pane pasó a ser otra terminal o se movió, no se cierra.
                            "terminal_id": t.get("terminal_id") or "",
                            "workspace_id": ws.get("id") or "",
                            "tab_id": tab.get("id") or "",
                            "titulo": t.get("titulo") or "",
                            "cwd": t.get("cwd") or "",
                            "proceso": t.get("proceso") or "",
                            "estado": t.get("estado") or "",
                            "donde": donde,
                        }
        return next(iter(halladas.values())) if len(halladas) == 1 else None

    def cerrar_terminal(self, sel: str, pane: str, sid: str, nombre: str, via: Optional[str] = None,
                        **extra: Any) -> Resultado:
        origen = self._origen(pane, sid, nombre, via)
        term = self.terminal_comun(sel)
        if term is None:
            log.info("colmena-pestana: terminal a cerrar no encontrada (%s)", pane)
            self.store.descartar(origen, "terminal_no_encontrada")
            return None, "terminal_no_encontrada"
        item, motivo = self.store.crear("", "", None, origen, accion="cerrar", terminal=term, **extra)
        if item is None:
            return None, motivo
        label = term["titulo"] or term["cwd"] or term["pane_id"]
        self.spawn(self.push.dispatch_pestana(item["id"], "Pedido para cerrar una terminal",
                                              f"{nombre} quiere cerrar la terminal {label}", session_id=sid,
                                              pane_id=pane))
        return item, None

    async def crear_cierre(self, hallado: dict, origen: dict, nombre: str, **extra: Any) -> Resultado:
        objetivo = hallado["objetivo"]
        try:
            preview = await self.cierres.preview(PreviewBody(tipo=hallado["tipo"], target_id=hallado["target_id"]))
        except TraspasoError as exc:
            motivo = {400: "cierre_protegido", 403: "cierre_protegido", 404: "cierre_no_encontrado"}.get(
                exc.status, "cierre_no_posible")
            log.info("colmena-pestana: pedido de cierre rechazado (%s)", motivo)
            self.store.descartar(origen, motivo)
            return None, motivo
        except Exception:
            log.exception("colmena-pestana: falló el preview del pedido de cierre")
            self.store.descartar(origen, "cierre_no_posible")
            return None, "cierre_no_posible"
        if preview.get("protegido"):
            self.store.descartar(origen, "cierre_protegido")
            return None, "cierre_protegido"
        resumen = resumen_cierre(objetivo, preview)
        item, motivo = self.store.crear("", "", None, origen, accion="cerrar", cierre=resumen, cooldown=False,
                                        **extra)
        if item is None:
            return None, motivo
        titulos = {"sesion": "Pedido para cerrar una sesión", "pestana": "Pedido para cerrar una pestaña",
                   "tarjeta": "Pedido para cerrar una tarjeta"}
        await self.push.dispatch_pestana(item["id"], titulos[objetivo], f"{nombre} quiere cerrar «{resumen['label']}»",
                                         session_id=origen["session_id"], pane_id=origen["pane_id"])
        return item, None

    def preparar_cierre(self, payload: dict, origen: dict) -> Resultado:
        """Cooldown y objetivo de un pedido de cierre. Devuelve (hallado, motivo)."""
        if not self.store.permitir(origen):
            return None, "cooldown"
        hallado, motivo = resolver_objetivo(self.board(), payload["objetivo"], payload["sel"])
        if motivo:
            log.info("colmena-pestana: pedido de cierre descartado (%s)", motivo)
            self.store.descartar(origen, motivo)
            return None, motivo
        return hallado, None

    def cerrar_objetivo(self, payload: dict, pane: str, sid: str, nombre: str) -> None:
        origen = self._origen(pane, sid, nombre)
        hallado, motivo = self.preparar_cierre(payload, origen)
        if hallado is None:
            return
        self.spawn(self.crear_cierre(hallado, origen, nombre))

    # --- abrir ---

    def abrir(self, payload: dict, pane: str, sid: str, nombre: str, via: Optional[str] = None,
              **extra: Any) -> Resultado:
        try:
            carpeta = validar_carpeta(payload["carpeta"], self.cfg.plan_cwds)
        except TraspasoError:
            log.info("colmena-pestana carpeta no permitida: %s", pane)
            return None, "carpeta_no_permitida"
        pestanas = payload.get("pestanas")
        carpetas = [carpeta]
        if pestanas:
            for p in pestanas:
                try:
                    carpetas.append(validar_carpeta(p["carpeta"], self.cfg.plan_cwds))
                except TraspasoError:
                    log.info("colmena-pestana carpeta no permitida (pestaña): %s", pane)
                    return None, "carpeta_no_permitida"

        origen_pedido = self._origen(pane, sid, nombre, via)
        if any(es_repo_colmena(c) for c in carpetas):
            log.info("colmena-pestana carpeta de Colmena: %s", pane)
            self.store.descartar(origen_pedido, "carpeta_colmena")
            return None, "carpeta_colmena"
        nombre_tab = payload.get("nombre") or ""
        item, motivo = self.store.crear(
            carpeta,
            payload.get("mensaje") or "",
            nombre_tab or None,
            origen_pedido,
            tarjeta=payload.get("tarjeta"),
            pestanas=pestanas,
            **extra,
        )
        if item is None:
            return None, motivo
        titulo = "Pedido de pestañas" if pestanas and len(pestanas) > 1 else "Pedido de pestaña"
        tarjeta_nom = (payload.get("tarjeta") or "").strip()
        if pestanas:
            cuerpo = f"{nombre} quiere abrir {len(pestanas)} pestañas"
            if tarjeta_nom:
                cuerpo += f" en la tarjeta «{tarjeta_nom}»"
            else:
                cuerpo += f" en {carpeta}"
        else:
            cuerpo = f"{nombre} quiere abrir una pestaña en {carpeta}"
        cuerpo += self.resumen_mensajes(pestanas or [{"tipo": "claude", "mensaje": payload.get("mensaje") or ""}])
        self.spawn(self.push.dispatch_pestana(item["id"], titulo, cuerpo, session_id=sid, pane_id=pane))
        return item, None

    def cursor(self, payload: dict, pane: str, sid: str, nombre: str, via: Optional[str] = None,
               **extra: Any) -> Resultado:
        try:
            carpeta = validar_carpeta(payload["carpeta"], self.cfg.plan_cwds)
        except TraspasoError:
            log.info("colmena-pestana cursor carpeta no permitida: %s", pane)
            return None, "carpeta_no_permitida"
        origen_pedido = self._origen(pane, sid, nombre, via)
        if es_repo_colmena(carpeta):
            log.info("colmena-pestana cursor carpeta de Colmena: %s", pane)
            self.store.descartar(origen_pedido, "carpeta_colmena")
            return None, "carpeta_colmena"
        item, motivo = self.store.crear(carpeta, payload["pedido"], payload["nombre"], origen_pedido,
                                        accion="cursor", cursor={"modelo": payload.get("modelo") or ""}, **extra)
        if item is None:
            return None, motivo
        self.spawn(self.push.dispatch_pestana(item["id"], "Pedido de trabajador Cursor",
                                              f"{nombre} quiere que Cursor haga: {payload['nombre']}",
                                              session_id=sid, pane_id=pane))
        return item, None

    @staticmethod
    def resumen_mensajes(pestanas: list) -> str:
        """` · {k} con mensaje para Claude: «…»`: el push dice que el pedido le va a escribir a Claude."""
        from .envio_sesion import linea_unica

        mensajes_claude = [p["mensaje"] for p in pestanas if p.get("tipo") == "claude" and p.get("mensaje")]
        if not mensajes_claude:
            return ""
        primero = linea_unica(mensajes_claude[0], MAX_TEXT)
        muestra = primero[:80] + ("…" if len(primero) > 80 else "")
        return f" · {len(mensajes_claude)} con mensaje para Claude: «{muestra}»"

    # --- MCP ---

    async def desde_mcp(self, payload: dict, pane: str, sid: str, nombre: str) -> Resultado:
        """Un payload ya normalizado con `pedido_desde_dict`: mismo camino que la marca, pero esperando el
        resultado y con `via="mcp"` (el descarte no avisa al origen: lo recibe el MCP)."""
        via = "mcp"
        if payload.get("accion") == "cerrar":
            if not payload.get("objetivo"):
                return self.cerrar_terminal(payload["terminal"], pane, sid, nombre, via=via)
            origen = self._origen(pane, sid, nombre, via)
            hallado, motivo = self.preparar_cierre(payload, origen)
            if hallado is None:
                return None, motivo
            return await self.crear_cierre(hallado, origen, nombre)
        if payload.get("accion") == "cursor":
            return self.cursor(payload, pane, sid, nombre, via=via)
        return self.abrir(payload, pane, sid, nombre, via=via)

    def mensaje(self, destino: dict, texto: str, pane: str, sid: str, nombre: str,
                via: Optional[str] = None) -> Resultado:
        """Mensaje a otra sesión: siempre un pedido pendiente, con `PREFIJO_PEDIDO` (aunque la destino la haya
        abierto la misma sesión)."""
        from .colmena_pestana import PREFIJO_PEDIDO, _norm_mensaje

        limpio = _norm_mensaje(texto)
        if not limpio:
            return None, "mensaje_invalido"
        envio = {"pane_id": destino["pane_id"], "nombre": destino.get("nombre") or destino["pane_id"],
                 "texto": PREFIJO_PEDIDO + limpio}
        item, motivo = self.store.crear("", limpio, None, self._origen(pane, sid, nombre, via), accion="mensaje",
                                        envio=envio, via=via)
        if item is None:
            return None, motivo
        self.spawn(self.push.dispatch_pestana(item["id"], "Pedido de mensaje",
                                              f"{nombre} quiere mandarle un mensaje a {envio['nombre']}",
                                              session_id=sid, pane_id=pane))
        return item, None

    def programada(self, texto: str, cuando: str, destino: dict, pane: str, sid: str, nombre: str,
                   via: Optional[str] = None) -> Resultado:
        """Mensaje programado de una sola vez (HH:MM, la próxima vez que llegue esa hora) a una sesión."""
        from .agenda import parse_hora
        from .colmena_pestana import _norm_mensaje

        if parse_hora(cuando) is None:
            return None, "cuando_invalido"
        limpio = _norm_mensaje(texto)
        if not limpio:
            return None, "mensaje_invalido"
        datos = {"cuando": cuando.strip(), "pane_id": destino["pane_id"],
                 "nombre": destino.get("nombre") or destino["pane_id"]}
        item, motivo = self.store.crear("", limpio, None, self._origen(pane, sid, nombre, via), accion="programada",
                                        programada=datos, via=via)
        if item is None:
            return None, motivo
        self.spawn(self.push.dispatch_pestana(item["id"], "Pedido de mensaje programado",
                                              f"{nombre} quiere programar un mensaje a las {datos['cuando']}",
                                              session_id=sid, pane_id=pane))
        return item, None

    def tarea(self, ticket: str, carpeta: str, nota: str, pane: str, sid: str, nombre: str,
              via: Optional[str] = None) -> Resultado:
        """Nueva tarea para un ticket (copia del repo con rama propia), como `POST /terminales/nueva-tarea`."""
        from .colmena_pestana import _norm_mensaje

        if not isinstance(ticket, str) or not _TICKET_RE.fullmatch(ticket.strip()):
            return None, "ticket_invalido"
        try:
            real = validar_carpeta(carpeta, self.cfg.plan_cwds)
        except TraspasoError:
            return None, "carpeta_no_permitida"
        origen = self._origen(pane, sid, nombre, via)
        if es_repo_colmena(real):
            self.store.descartar(origen, "carpeta_colmena")
            return None, "carpeta_colmena"
        nota_limpia = _norm_mensaje(nota) if nota and nota.strip() else ""
        if nota_limpia is None:
            return None, "mensaje_invalido"
        ticket = ticket.strip()
        item, motivo = self.store.crear(real, nota_limpia, ticket, origen, accion="tarea", tarea={"ticket": ticket},
                                        via=via)
        if item is None:
            return None, motivo
        self.spawn(self.push.dispatch_pestana(item["id"], "Pedido de tarea",
                                              f"{nombre} quiere abrir una tarea para {ticket} en {real}",
                                              session_id=sid, pane_id=pane))
        return item, None

    # --- marca ---

    def desde_marca(self, payload: dict, pane: str, sid: str, nombre: str) -> None:
        """Un payload ya parseado de `[colmena-pestana]`: mismo camino que tenía app.py."""
        if payload.get("accion") == "cerrar":
            if payload.get("objetivo"):
                self.cerrar_objetivo(payload, pane, sid, nombre)
            else:
                self.cerrar_terminal(payload["terminal"], pane, sid, nombre)
            return
        if payload.get("accion") == "cursor":
            self.cursor(payload, pane, sid, nombre)
            return
        self.abrir(payload, pane, sid, nombre)
