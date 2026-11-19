"""API de notas. Se incluye en el router `api`: exige sesión y mismo origen."""
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .notas import NotasNoDisponibles, NotasStore

SH = {"Cache-Control": "no-store"}
ID_RE = r"^n_[A-Za-z0-9_-]{6,20}$"


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrigenBody(_Body):
    sid: Optional[str] = Field(None, max_length=200)
    nombre: Optional[str] = Field(None, max_length=200)
    ts: Optional[str] = Field(None, max_length=64)


class CrearBody(_Body):
    tipo: str = Field(..., max_length=40)
    texto: str = Field(..., max_length=20000)
    origen: Optional[OrigenBody] = None


class EditarBody(_Body):
    texto: Optional[str] = Field(None, max_length=20000)
    tipo: Optional[str] = Field(None, max_length=40)
    hecha: Optional[bool] = None


def build_router(notas: NotasStore, emit: Callable[[str, dict], None]) -> APIRouter:
    router = APIRouter()

    def avisar() -> None:
        emit("notas", {"version": notas.version, "pendientes": notas.pendientes()})

    def accion(fn):
        try:
            return fn()
        except NotasNoDisponibles as exc:
            raise HTTPException(status_code=503, detail="las notas no están disponibles; reiniciá Colmena") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc) or "datos inválidos") from exc

    @router.get("/notas")
    async def listar():
        return JSONResponse({"notas": notas.listar(), "pendientes": notas.pendientes(), "version": notas.version},
                            headers=SH)

    @router.post("/notas", status_code=201)
    async def crear(body: CrearBody):
        origen = body.origen.model_dump(exclude_none=True) if body.origen else None
        nota = accion(lambda: notas.crear(body.tipo, body.texto, origen))
        avisar()
        return JSONResponse(nota, status_code=201, headers=SH)

    @router.patch("/notas/{nota_id}")
    async def editar(body: EditarBody, nota_id: str = Path(..., pattern=ID_RE)):
        if body.texto is None and body.tipo is None and body.hecha is None:
            raise HTTPException(status_code=422, detail="nada que cambiar")

        def aplicar():
            nota = None
            if body.texto is not None or body.tipo is not None:
                nota = notas.editar(nota_id, texto=body.texto, tipo=body.tipo)
                if nota is None:
                    return None
            if body.hecha is not None:
                nota = notas.marcar(nota_id, body.hecha)
            return nota

        nota = accion(aplicar)
        if nota is None:
            raise HTTPException(status_code=404, detail="nota inexistente")
        avisar()
        return JSONResponse(nota, headers=SH)

    @router.delete("/notas/{nota_id}", status_code=204)
    async def borrar(nota_id: str = Path(..., pattern=ID_RE)):
        if not accion(lambda: notas.borrar(nota_id)):
            raise HTTPException(status_code=404, detail="nota inexistente")
        avisar()
        return Response(status_code=204)

    return router
