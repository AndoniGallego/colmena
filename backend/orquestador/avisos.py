import json
import logging
import re
import time
from pathlib import Path
from typing import Callable

from .config import private_write
from .enchufe.ids import PANE_RE, valido

log = logging.getLogger("orquestador.avisos")
RETENTION = 30 * 86400
MAX_ITEMS = 500
MAX_PAGE = 100
KINDS_BASE = ("asks", "blocked", "done", "terminal", "cierre", "encadenar", "vigia", "mr", "entorno", "test", "progreso", "pestana", "trabada")
# Kinds que suma una pieza opcional (registrar_kind): mismo formato que las prefs extra de push.
KIND_RE = re.compile(r"^[a-z]{1,20}$")
PEDIDO_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)
FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SESSION_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
MR_RE = re.compile(r"^\d{1,12}:\d{1,9}$")
MENSAJE_RE = re.compile(r"^[0-9a-f]{32}$")
TAG_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def _clean(raw, kinds=KINDS_BASE) -> dict:
    """Entrada válida o None: un archivo editado a mano no rompe el servicio."""
    if not isinstance(raw, dict):
        return {}
    rid, ts, kind = raw.get("id"), raw.get("ts"), raw.get("kind")
    if not (isinstance(rid, int) and not isinstance(rid, bool) and rid > 0) or kind not in kinds:
        return {}
    if not isinstance(ts, (int, float)) or isinstance(ts, bool):
        return {}
    sid, pane, fecha, mr = raw.get("session_id"), raw.get("pane_id"), raw.get("fecha"), raw.get("mr")
    msg, tag = raw.get("mensaje"), raw.get("tag")
    pedido = raw.get("pedido")
    return {"id": rid, "ts": int(ts), "kind": kind, "titulo": str(raw.get("titulo") or "")[:200],
            "cuerpo": str(raw.get("cuerpo") or "")[:400],
            "session_id": sid if isinstance(sid, str) and SESSION_RE.match(sid) else "",
            "pane_id": pane if valido(PANE_RE, pane) else "",
            "fecha": fecha if isinstance(fecha, str) and FECHA_RE.match(fecha) else "",
            "mr": mr if isinstance(mr, str) and MR_RE.match(mr) else "",
            "mensaje": msg if isinstance(msg, str) and MENSAJE_RE.match(msg) else "",
            "pedido": pedido if isinstance(pedido, str) and PEDIDO_RE.match(pedido) else "",
            "tag": tag if isinstance(tag, str) and TAG_RE.match(tag) else "",
            "entregado": raw.get("entregado") is True, "leido": raw.get("leido") is True,
            "motivo": str(raw.get("motivo") or "")[:40],
            "prueba": raw.get("prueba") is True}


class AvisosStore:
    """Historial de avisos: una entrada por evento, no por dispositivo."""

    def __init__(self, directory: Path, wall: Callable = time.time):
        self.path = directory / "avisos.json"
        self.wall = wall
        self.kinds: list = list(KINDS_BASE)
        self.items: list = []
        # Entradas de un kind que ninguna pieza registró (todavía): no se muestran, pero se conservan en disco.
        self.ocultos: list = []
        self.next_id = 1
        self.leidos = 0
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for raw in data.get("items", []):
                    entry = _clean(raw, self.kinds)
                    if entry:
                        self.items.append(entry)
                    elif isinstance(raw, dict) and isinstance(raw.get("kind"), str) and KIND_RE.match(raw["kind"]):
                        oculto = _clean(raw, (raw["kind"],))
                        if oculto:
                            self.ocultos.append(oculto)
                self.leidos = data["leidos"] if isinstance(data.get("leidos"), int) and data["leidos"] >= 0 else 0
                nxt = data.get("next")
                self.next_id = nxt if isinstance(nxt, int) and nxt > 0 else 1
            except (ValueError, AttributeError, TypeError, OSError):
                log.warning("avisos.json ilegible, arranco vacío")
        self.next_id = max([self.next_id] + [e["id"] + 1 for e in self.items + self.ocultos])
        self._prune()

    def registrar_kind(self, kind: str) -> None:
        """Suma un kind de aviso (lo llama una pieza al montarse) y recupera sus entradas guardadas."""
        if not isinstance(kind, str) or not KIND_RE.match(kind):
            raise ValueError(kind)
        if kind in self.kinds:
            return
        self.kinds.append(kind)
        vuelven = [e for e in self.ocultos if e["kind"] == kind]
        if vuelven:
            self.ocultos = [e for e in self.ocultos if e["kind"] != kind]
            self.items = sorted(self.items + vuelven, key=lambda e: e["id"])

    def _prune(self) -> None:
        limit = self.wall() - RETENTION
        self.items = [e for e in self.items if e["ts"] >= limit][-MAX_ITEMS:]
        self.ocultos = [e for e in self.ocultos if e["ts"] >= limit][-MAX_ITEMS:]

    def _save(self) -> None:
        guardar = sorted(self.items + self.ocultos, key=lambda e: e["id"])
        try:
            private_write(self.path, json.dumps({"next": self.next_id, "leidos": self.leidos, "items": guardar},
                                                ensure_ascii=False))
        except OSError as exc:
            log.warning("no pude guardar avisos.json: %s", type(exc).__name__)

    def add(self, kind: str, titulo: str, cuerpo: str, entregado: bool, session_id: str = "", pane_id: str = "",
            fecha: str = "", motivo: str = "", mr: str = "", mensaje: str = "", pedido: str = "", tag: str = "",
            prueba: bool = False) -> dict:
        entry = _clean({"id": self.next_id, "ts": self.wall(), "kind": kind, "titulo": titulo, "cuerpo": cuerpo,
                        "session_id": session_id, "pane_id": pane_id, "fecha": fecha, "mr": mr, "mensaje": mensaje,
                        "pedido": pedido, "tag": tag, "entregado": bool(entregado), "motivo": motivo, "prueba": prueba},
                       self.kinds)
        if not entry:
            raise ValueError(kind)
        self.next_id += 1
        self.items.append(entry)
        self._prune()
        self._save()
        return entry

    @property
    def no_leidos(self) -> int:
        return sum(1 for e in self.items if self._unread(e))

    def _unread(self, entry: dict) -> bool:
        if entry.get("prueba"):
            return False
        return entry["id"] > self.leidos and not entry["leido"]

    def page(self, limit: int = 50, before: int = 0, incluir_prueba: bool = False) -> dict:
        limit = min(max(limit, 1), MAX_PAGE)
        self._prune()
        pool = [e for e in reversed(self.items) if (incluir_prueba or not e.get("prueba")) and (not before or e["id"] < before)]
        return {"items": pool[:limit], "hay_mas": len(pool) > limit, "no_leidos": self.no_leidos,
                "leidos_hasta": self.leidos}

    def _tags_cerrables(self, changed: list) -> list:
        candidatos = {e["tag"] for e in changed if e.get("tag")}
        pendientes = {e["tag"] for e in self.items if self._unread(e) and e.get("tag")}
        return sorted(t for t in candidatos if t not in pendientes)

    def marcar_donde(self, session_id: str = "", pane_id: str = "", kind: str = "", mr: str = "", mensaje: str = "",
                     pedido: str = "", tag: str = "") -> dict:
        changed = []
        for e in self.items:
            hit = (session_id and e["session_id"] == session_id) or (pane_id and e["pane_id"] == pane_id) \
                or (kind and e["kind"] == kind) or (mr and e["mr"] == mr) \
                or (mensaje and e["mensaje"] == mensaje) or (pedido and e.get("pedido") == pedido) \
                or (tag and e["tag"] == tag)
            if hit and self._unread(e):
                e["leido"] = True
                changed.append(e)
        if changed:
            self._save()
        return {"no_leidos": self.no_leidos, "cambiados": len(changed), "tags": self._tags_cerrables(changed)}

    def marcar_hasta(self, hasta: int) -> dict:
        top = self.next_id - 1
        value = min(max(hasta, 0), top)
        old = self.leidos
        changed = []
        if value > old:
            changed = [e for e in self.items if old < e["id"] <= value and not e["leido"]]
            self.leidos = value
            self._save()
        return {"no_leidos": self.no_leidos, "cambiados": len(changed), "tags": self._tags_cerrables(changed)}

    def mark_where(self, session_id: str = "", pane_id: str = "", kind: str = "", mr: str = "", mensaje: str = "",
                   pedido: str = "", tag: str = "") -> int:
        return self.marcar_donde(session_id, pane_id, kind, mr, mensaje, pedido, tag)["no_leidos"]

    def mark_read(self, hasta: int) -> int:
        return self.marcar_hasta(hasta)["no_leidos"]
