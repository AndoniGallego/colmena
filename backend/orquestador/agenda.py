"""Agenda de avisos diarios: hora "HH:MM", días de la semana (0 = lunes) y cuánto falta para la próxima vez."""
import re
from datetime import datetime, timedelta
from typing import Optional

HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
DIAS_DEFAULT = [0, 1, 2, 3, 4]


def parse_hora(value: str) -> Optional[tuple]:
    found = HORA.match((value or "").strip()) if isinstance(value, str) else None
    return (int(found.group(1)), int(found.group(2))) if found else None


def parse_dias(value) -> list:
    """Días de la semana (0 = lunes) en que avisa; una lista inválida cae al default lun-vie."""
    if isinstance(value, list) and value and all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in value):
        return sorted(set(value))
    return list(DIAS_DEFAULT)


def seconds_until_next(hora: tuple, dias: list, now: datetime) -> float:
    for offset in range(8):
        target = (now + timedelta(days=offset)).replace(hour=hora[0], minute=hora[1], second=0, microsecond=0)
        if target > now and target.weekday() in dias:
            return max(1.0, (target - now).total_seconds())
    return 24 * 3600.0
