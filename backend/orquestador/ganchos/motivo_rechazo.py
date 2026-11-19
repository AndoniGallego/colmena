"""Motivo de rechazo de permisos (solo stdlib; compartido con colmena_gancho.py)."""

import re

MOTIVO_RECHAZO_DEFAULT = "Rechazado desde Colmena"
_DENY_DESCARTAR = frozenset({"\u2028", "\u2029"})
_MAX_MOTIVO = 500


def sanitizar_motivo_rechazo(motivo: str | None) -> str:
    if motivo is None:
        return MOTIVO_RECHAZO_DEFAULT
    limpio = re.sub(r"[\x00-\x1f\x7f]", "", motivo)
    limpio = "".join(ch for ch in limpio if ch not in _DENY_DESCARTAR).strip()
    if not limpio:
        return MOTIVO_RECHAZO_DEFAULT
    return limpio[:_MAX_MOTIVO]
