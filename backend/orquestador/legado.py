"""Compatibilidad con mensajes y datos viejos: el nombre de bloque anterior se lee como ```diagrama```.

Es el único lugar que lo conoce; el resto del código solo habla de diagramas.
"""
import json

LEGACY_FENCE = "flujo"
_TIPOS_PASOS = ("secuencia", "proceso")


def _tiene_actores(data: dict) -> bool:
    actores = data.get("actores")
    return isinstance(actores, list) and any(
        isinstance(a, dict) and isinstance(a.get("id"), (str, int)) and str(a["id"]).strip() for a in actores)


def diagrama_legado(data):
    """El cuerpo viejo con su "tipo" explícito (antes se infería por los actores); None si no tiene pasos."""
    if not isinstance(data, dict) or not isinstance(data.get("pasos"), list):
        return None
    if data.get("tipo") in _TIPOS_PASOS:
        return data
    return {**data, "tipo": "secuencia" if _tiene_actores(data) else "proceso"}


def migrar_items(items: dict) -> bool:
    """Pasa los ítems guardados con el formato anterior a diagrama. Idempotente; True si cambió algo."""
    cambio = False
    for item in items.values():
        if not isinstance(item, dict):
            continue
        if "flujo_raw" in item:
            item.setdefault("diagrama_raw", item["flujo_raw"])
            del item["flujo_raw"]
            cambio = True
        if item.get("source") == LEGACY_FENCE:
            item["source"] = "diagrama"
            cambio = True
        if item.get("kind") != LEGACY_FENCE:
            continue
        item["kind"] = "diagrama"
        cambio = True
        raw = item.get("diagrama_raw")
        try:
            data = json.loads(raw) if isinstance(raw, str) else None
        except ValueError:
            data = None
        nuevo = diagrama_legado(data)
        if nuevo is not None and nuevo is not data:
            item["diagrama_raw"] = json.dumps(nuevo, ensure_ascii=False)
            item["size"] = len(item["diagrama_raw"])
    return cambio
