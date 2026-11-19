"""API de tareas programadas. Se incluye en el router `api`: exige sesión y mismo origen."""
import asyncio
import logging
import re
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .programadas import ProgramaBody, Programadas
from .traspaso import TraspasoError

log = logging.getLogger("orquestador.programadas.api")
PID_RE = re.compile(r"^[a-f0-9]{32}$")
SH = {"Cache-Control": "no-store"}


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PausaBody(_Body):
    pausada: bool


class CorrerBody(_Body):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")


class HabilitarBody(_Body):
    habilitado: bool
    pin: Optional[str] = Field(None, max_length=200)


def build_router(programadas: Programadas, limiter, verify: Callable, pin_hash: str) -> APIRouter:
    router = APIRouter()

    def pid_ok(pid: str) -> str:
        if not PID_RE.match(pid):
            raise HTTPException(status_code=422, detail="id inválido")
        return pid

    async def cuerpo(request: Request, modelo):
        try:
            return modelo.model_validate(await request.json())
        except (ValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="cuerpo inválido") from exc

    def falla(exc: TraspasoError) -> JSONResponse:
        headers = {"Retry-After": str(exc.extra["retry_after"])} if "retry_after" in exc.extra else None
        return JSONResponse({"detail": exc.detail}, status_code=exc.status, headers=headers)

    async def check_pin(pin: Optional[str], request: Request) -> None:
        ip = request.client.host if request.client else "?"
        async with limiter.gate:
            wait = limiter.retry_after(ip)
            if wait:
                raise HTTPException(status_code=429, detail="Demasiados intentos", headers={"Retry-After": str(wait)})
            if not pin or not await asyncio.to_thread(verify, pin, pin_hash):
                limiter.fail(ip)
                log.warning("PIN incorrecto al prender las tareas programadas desde %s", ip)
                raise HTTPException(status_code=403, detail="PIN incorrecto")
            limiter.ok(ip)

    @router.get("/programadas")
    async def listar():
        return JSONResponse(programadas.listar(), headers=SH)

    @router.get("/programadas/historial")
    async def historial(programa: str = "", limite: int = 100):
        if programa:
            pid_ok(programa)
        return JSONResponse(programadas.historial(programa or None, limite), headers=SH)

    @router.post("/programadas")
    async def crear(request: Request):
        body = await cuerpo(request, ProgramaBody)
        try:
            return JSONResponse(programadas.crear(body), headers=SH)
        except TraspasoError as exc:
            return falla(exc)

    @router.put("/programadas/{pid}")
    async def editar(pid: str, request: Request):
        pid_ok(pid)
        body = await cuerpo(request, ProgramaBody)
        try:
            return JSONResponse(programadas.editar(pid, body), headers=SH)
        except TraspasoError as exc:
            return falla(exc)

    @router.delete("/programadas/{pid}")
    async def borrar(pid: str):
        pid_ok(pid)
        try:
            programadas.borrar(pid)
        except TraspasoError as exc:
            return falla(exc)
        return JSONResponse({"ok": True}, headers=SH)

    @router.post("/programadas/habilitar")
    async def habilitar(request: Request):
        body = await cuerpo(request, HabilitarBody)
        if body.habilitado and not programadas.habilitado:
            await check_pin(body.pin, request)
        programadas.habilitar(body.habilitado)
        return JSONResponse({"habilitado": programadas.habilitado}, headers=SH)

    @router.post("/programadas/{pid}/pausa")
    async def pausa(pid: str, request: Request):
        pid_ok(pid)
        body = await cuerpo(request, PausaBody)
        try:
            return JSONResponse(programadas.pausar(pid, body.pausada), headers=SH)
        except TraspasoError as exc:
            return falla(exc)

    @router.post("/programadas/{pid}/correr")
    async def correr(pid: str, request: Request):
        pid_ok(pid)
        body = await cuerpo(request, CorrerBody)
        try:
            return JSONResponse(await programadas.correr(pid, manual=True, ident=f"{pid[:8]}-{body.id}"), headers=SH)
        except TraspasoError as exc:
            return falla(exc)

    return router
