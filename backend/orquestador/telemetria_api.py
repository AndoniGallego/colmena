"""Endpoint de telemetría que el front usa para lo que el back no ve: el "No" de una tarjeta de comando.
Se incluye en el router `api`: exige sesión y mismo origen. La clave solo sirve para no contar dos veces."""
import logging
import time
from collections import OrderedDict
from typing import Callable, Literal

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, ConfigDict, constr

from .telemetria import Telemetria, token
from .telemetria_resumen import PropuestasStore, semana_iso

logger = logging.getLogger(__name__)

VIGENCIA = 24 * 3600
MAX_VISTAS = 1000


class ComandoNoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clave: constr(pattern=r"^[0-9a-f]{16}$")


class PropuestaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["hacer", "ignorar", "mas_adelante"]


def build_router(telemetria: Telemetria, wall: Callable[[], float] = time.time,
                 propuestas: PropuestasStore | None = None,
                 metrica_actual: Callable[[str], float | None] = lambda pid: None) -> APIRouter:
    router = APIRouter()
    vistas: OrderedDict = OrderedDict()

    @router.post("/telemetria/comando-no")
    async def comando_no(body: ComandoNoBody) -> dict:
        try:
            ahora = wall()
            for k in [k for k, ts in vistas.items() if ahora - ts >= VIGENCIA]:
                del vistas[k]
            if body.clave not in vistas:
                vistas[body.clave] = ahora
                while len(vistas) > MAX_VISTAS:
                    vistas.popitem(last=False)
                telemetria.anotar("comando_sesion", resultado="no", codigo=None, proyecto=None)
        except Exception:
            pass
        return {"ok": True}

    @router.post("/telemetria/propuestas/{pid}")
    async def marcar_propuesta(body: PropuestaBody, pid: str = Path(pattern=r"^[0-9a-f]{12}$")) -> dict:
        entrada = propuestas.cargar().get(pid) if propuestas is not None else None
        if not isinstance(entrada, dict):
            raise HTTPException(404, "propuesta inexistente")
        try:
            metrica = metrica_actual(pid)
        except Exception:
            logger.warning("No se pudo leer la métrica actual de la propuesta: %s", "error")
            metrica = None
        semana = semana_iso(propuestas.wall().astimezone().date())
        e = propuestas.decidir(pid, body.decision, semana, metrica)
        try:
            telemetria.anotar("propuesta", regla=token(entrada.get("regla")), decision=body.decision)
        except Exception:
            pass
        return {"id": pid, "estado": e["estado"], "silenciada_hasta": e["silenciada_hasta"]}

    return router
