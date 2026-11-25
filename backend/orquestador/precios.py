import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("orquestador.precios")

CAMPOS_PRECIO = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")
POR = 1_000_000
RUTA = Path(__file__).with_name("precios.json")


def _num(value) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def _modelo(raw) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    out = {k: _num(raw.get(k)) for k in CAMPOS_PRECIO}
    return out if all(v is not None for v in out.values()) else None


class Precios:
    """Tabla de precios por modelo (USD por millón de tokens), local y versionada; nunca sale a la red."""

    def __init__(self, tabla: Optional[dict] = None, override: Optional[dict] = None):
        if tabla is None:
            try:
                tabla = json.loads(RUTA.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                log.warning("no pude leer precios.json: %s", exc)
                tabla = {}
        self.version = tabla.get("version")
        self.fecha = tabla.get("fecha")
        self.modelos: dict = {}
        for name, raw in (tabla.get("modelos") or {}).items():
            if (parsed := _modelo(raw)) is not None:
                self.modelos[name] = parsed
        for name, raw in (override or {}).items():
            if (parsed := _modelo(raw)) is not None:
                self.modelos[name] = parsed
        self.alias = {k: v for k, v in (tabla.get("alias") or {}).items() if isinstance(v, str)}

    def de(self, model: str) -> Optional[dict]:
        if model in self.modelos:
            return self.modelos[model]
        destino = self.alias.get(model)
        if destino in self.modelos:
            return self.modelos[destino]
        # Con sufijo de fecha (claude-opus-5-5-20261001): el nombre más largo que sea prefijo.
        candidatos = [k for k in self.modelos if model.startswith(k + "-")]
        return self.modelos[max(candidatos, key=len)] if candidatos else None

    def usd(self, model: str, row) -> Optional[float]:
        """Costo de una fila [input, cache_write, cache_read, output, mensajes, cache_write_1h]; None si el modelo no tiene precio."""
        precio = self.de(model)
        if precio is None:
            return None
        cw_1h = row[5] if len(row) > 5 else 0
        cw_5m = max(0, row[1] - cw_1h)
        return (row[0] * precio["input"] + cw_5m * precio["cache_write_5m"] + cw_1h * precio["cache_write_1h"]
                + row[2] * precio["cache_read"] + row[3] * precio["output"]) / POR
