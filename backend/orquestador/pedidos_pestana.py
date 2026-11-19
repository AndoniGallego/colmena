"""Pedidos pendientes de abrir pestaña (memoria, sin persistir)."""
import logging
import time
import uuid
from typing import Callable, Literal

log = logging.getLogger("orquestador.pedidos_pestana")

COOLDOWN = 30.0
VENCE_S = 600
MAX_TOTAL = 5
CIERRE_PUBLICO = ("objetivo", "tipo", "target_id", "label", "workspace_label", "carpeta", "sesiones", "terminales")
MAX_POR_SESION = 3
Estado = Literal["pendiente", "lanzando", "abierto", "rechazado", "vencido"]


class PedidosPestanaStore:
    def __init__(self, wall: Callable = time.time, monotonic: Callable = time.monotonic):
        self.wall = wall
        self.monotonic = monotonic
        self._items: dict[str, dict] = {}
        # Fila de pendientes por sesión, en orden de llegada (hasta MAX_POR_SESION).
        self._por_sesion: dict[str, list[str]] = {}
        self._ultimo: dict[str, float] = {}
        self._listeners: list = []
        self._descartes: list = []

    def on_change(self, fn) -> None:
        self._listeners.append(fn)

    def on_descarte(self, fn) -> None:
        """fn(origen, motivo): un pedido no se va a abrir (fila_llena, cooldown, tope o vencido)."""
        self._descartes.append(fn)

    def _emit(self, pid: str, estado: str) -> None:
        for fn in self._listeners:
            try:
                fn(pid, estado)
            except Exception as exc:
                log.warning("listener pedido_pestana falló: %s", type(exc).__name__)

    def descartar(self, origen: dict, motivo: str) -> None:
        """Un pedido que no llegó a crearse (p. ej. la terminal a cerrar no existe): se avisa igual al origen."""
        self._descartar({"pane_id": origen.get("pane_id") or "", "nombre": origen.get("nombre") or "",
                         "session_id": str(origen.get("session_id") or "")}, motivo)

    def _descartar(self, origen: dict, motivo: str) -> None:
        for fn in self._descartes:
            try:
                fn(dict(origen), motivo)
            except Exception as exc:
                log.warning("listener de descarte de pedido_pestana falló: %s", type(exc).__name__)

    def _sacar_de_fila(self, item: dict) -> None:
        sid = (item.get("origen") or {}).get("session_id") or ""
        fila = self._por_sesion.get(sid)
        if not fila or item["id"] not in fila:
            return
        fila.remove(item["id"])
        if not fila:
            del self._por_sesion[sid]

    def pendientes_de(self, sid: str) -> list[str]:
        return list(self._por_sesion.get(sid, []))

    def _vencer(self, pid: str, motivo: str = "vencido") -> None:
        item = self._items.get(pid)
        if not item or item["estado"] != "pendiente":
            return
        item["estado"] = "vencido"
        self._sacar_de_fila(item)
        self._emit(pid, "vencido")
        self._descartar(item.get("origen") or {}, motivo)

    def _limpiar_vencidos(self) -> None:
        ahora = self.wall()
        for pid, item in list(self._items.items()):
            if item["estado"] == "pendiente" and item["vence"] <= ahora:
                self._vencer(pid)

    def _cap_total(self) -> None:
        pendientes = [(pid, it["ts"]) for pid, it in self._items.items() if it["estado"] == "pendiente"]
        if len(pendientes) <= MAX_TOTAL:
            return
        pendientes.sort(key=lambda x: x[1])
        for pid, _ in pendientes[: len(pendientes) - MAX_TOTAL]:
            self._vencer(pid, "tope")

    def crear(
        self,
        carpeta: str,
        mensaje: str,
        nombre: str | None,
        origen: dict,
        *,
        tarjeta: str | None = None,
        pestanas: list | None = None,
        accion: str | None = None,
        terminal: dict | None = None,
        cursor: dict | None = None,
        cierre: dict | None = None,
        cooldown: bool = True,
    ) -> tuple[dict | None, str | None]:
        """`cooldown=False` cuando el que llama ya lo consumió con `permitir`."""
        sid = str(origen.get("session_id") or "")
        quien = {"pane_id": origen.get("pane_id") or "", "nombre": origen.get("nombre") or "", "session_id": sid}
        ahora = self.monotonic()
        if sid and cooldown and ahora - self._ultimo.get(sid, -COOLDOWN) < COOLDOWN:
            self._descartar(quien, "cooldown")
            return None, "cooldown"
        self._limpiar_vencidos()
        if sid:
            if len(self._por_sesion.get(sid, [])) >= MAX_POR_SESION:
                self._descartar(quien, "fila_llena")
                return None, "fila_llena"
            if cooldown:
                self._ultimo[sid] = ahora
        self._cap_total()
        pid = str(uuid.uuid4())
        ts = int(self.wall())
        item = {
            "id": pid,
            "carpeta": carpeta,
            "mensaje": mensaje,
            "nombre": nombre or "",
            "origen": quien,
            "ts": ts,
            "vence": ts + VENCE_S,
            "estado": "pendiente",
        }
        if tarjeta:
            item["tarjeta"] = tarjeta
        if pestanas:
            item["pestanas"] = pestanas
        if accion:
            item["accion"] = accion
            if terminal is not None:
                item["terminal"] = dict(terminal)
            if cierre is not None:
                item["cierre"] = dict(cierre)
        if cursor is not None:
            item["cursor"] = dict(cursor)
        self._items[pid] = item
        if sid:
            self._por_sesion.setdefault(sid, []).append(pid)
        self._emit(pid, "pendiente")
        return item, None

    def permitir(self, origen: dict) -> bool:
        """Consume el cooldown de la sesión antes de un trabajo caro (resolver un objetivo, armar un preview).
        Si no hay cupo, avisa `cooldown` al origen y devuelve False."""
        sid = str(origen.get("session_id") or "")
        if not sid:
            return True
        ahora = self.monotonic()
        if ahora - self._ultimo.get(sid, -COOLDOWN) < COOLDOWN:
            self.descartar(origen, "cooldown")
            return False
        self._ultimo[sid] = ahora
        return True

    def get(self, pid: str) -> dict | None:
        self._limpiar_vencidos()
        item = self._items.get(pid)
        if not item:
            return None
        if item["estado"] == "pendiente" and item["vence"] <= self.wall():
            self._vencer(pid)
            return self._items.get(pid)
        return item

    def listar_pendientes(self) -> list:
        self._limpiar_vencidos()
        out = []
        for it in sorted(self._items.values(), key=lambda x: x["ts"], reverse=True):
            if it["estado"] != "pendiente":
                continue
            if it["vence"] <= self.wall():
                self._vencer(it["id"])
                continue
            fila = {
                "id": it["id"],
                "carpeta": it["carpeta"],
                "mensaje": it["mensaje"],
                "nombre": it["nombre"],
                "origen": {
                    "pane_id": it["origen"]["pane_id"],
                    "nombre": it["origen"]["nombre"],
                    "session_id": it["origen"].get("session_id", ""),
                },
                "ts": it["ts"],
                "vence": it["vence"],
            }
            if it.get("tarjeta"):
                fila["tarjeta"] = it["tarjeta"]
            if it.get("pestanas"):
                fila["pestanas"] = it["pestanas"]
            if it.get("accion"):
                fila["accion"] = it["accion"]
                if "terminal" in it:
                    fila["terminal"] = it["terminal"]
                if "cierre" in it:
                    fila["cierre"] = {k: it["cierre"][k] for k in CIERRE_PUBLICO if k in it["cierre"]}
            if "cursor" in it:
                fila["cursor"] = it["cursor"]
            out.append(fila)
        return out

    def marcar_vista_cierre(self, pid: str, huella: str) -> bool:
        """Última huella que la vista mostró: aprobar exige esa misma huella."""
        item = self.get(pid)
        if not item or item["estado"] != "pendiente" or "cierre" not in item:
            return False
        item["cierre"]["vista_huella"] = huella
        return True

    def marcar_aviso_cierre(self, pid: str, huella: str) -> bool:
        item = self.get(pid)
        if not item or item["estado"] != "pendiente" or "cierre" not in item:
            return False
        item["cierre"]["aviso_huella"] = huella
        return True

    def marcar(self, pid: str, estado: Estado) -> dict | None:
        self._limpiar_vencidos()
        item = self._items.get(pid)
        if not item:
            return None
        if item["estado"] != "pendiente":
            return item
        if item["vence"] <= self.wall():
            self._vencer(pid)
            return self._items.get(pid)
        item["estado"] = estado
        self._sacar_de_fila(item)
        self._emit(pid, estado)
        return item

    def tomar_para_lanzar(self, pid: str) -> bool:
        """Pendiente → lanzando, sin await en el medio: una segunda aprobación o un rechazo ven que ya no
        está pendiente (409) y un vencimiento no lo toca ni avisa."""
        item = self.get(pid)
        if not item or item["estado"] != "pendiente":
            return False
        item["estado"] = "lanzando"
        return True

    def soltar_lanzamiento(self, pid: str, estado: str) -> None:
        """Fin del lanzamiento: abierto, rechazado o de vuelta a pendiente (si ya venció, vence ahí)."""
        item = self._items.get(pid)
        if not item or item["estado"] != "lanzando":
            return
        item["estado"] = "pendiente"
        if estado != "pendiente":
            item["estado"] = estado
            self._sacar_de_fila(item)
            self._emit(pid, estado)
        elif item["vence"] <= self.wall():
            self._vencer(pid)

    def idempotencia_nueva(self, pid: str) -> str:
        compact = pid.replace("-", "")
        return f"pest-{compact[:48]}"
