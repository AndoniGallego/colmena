"""Rutas de los trabajadores Cursor. Se incluyen en el router `api` (sesión + CSRF).

Estas rutas no lanzan trabajadores. Salen de un pedido que Ando aprueba o de una tarea programada, que lanza con
el texto que Ando escribió (autenticado y con CSRF).
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .cursor_runner import TID_RE

NO_STORE = {"Cache-Control": "no-store"}
PEDIDO_CORTO = 200


def build_router(runner) -> APIRouter:
    router = APIRouter()

    def _tid(tid: str) -> dict:
        t = runner.get(tid) if TID_RE.fullmatch(tid or "") else None
        if not t:
            raise HTTPException(status_code=404, detail="trabajador no encontrado")
        return t

    @router.get("/cursor/estado")
    async def cursor_estado():
        return JSONResponse({"disponible": runner.disponible(), "corriendo": runner.corriendo(),
                             "max_simultaneos": runner.MAX_SIMULTANEOS}, headers=NO_STORE)

    @router.get("/cursor/trabajadores")
    async def cursor_trabajadores():
        lista = [{**t, "pedido": (t.get("pedido") or "")[:PEDIDO_CORTO]} for t in runner.listar()]
        return JSONResponse({"trabajadores": lista}, headers=NO_STORE)

    @router.get("/cursor/trabajadores/{tid}/log")
    async def cursor_log(tid: str):
        _tid(tid)
        return JSONResponse({"texto": runner.cola_log(tid)}, headers=NO_STORE)

    @router.post("/cursor/trabajadores/{tid}/cancelar")
    async def cursor_cancelar(tid: str):
        _tid(tid)
        if not runner.cancelar(tid):
            raise HTTPException(status_code=409, detail="el trabajador ya no está corriendo")
        return JSONResponse({"ok": True}, headers=NO_STORE)

    return router
