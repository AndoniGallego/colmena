"""Ficha e instalador de la app de Windows que arma scripts/armar-instalador.sh (sin PIN: los pide la parte Rust)."""
import json
import re
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

FICHA = "ultima.json"
RUTA = "/app/actualizacion"
RUTA_INSTALADOR = RUTA + "/instalador"
_ARCHIVO = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,199}")


def nombre_valido(archivo: object) -> bool:
    return isinstance(archivo, str) and bool(_ARCHIVO.fullmatch(archivo)) and ".." not in archivo


def leer_ultima(carpeta: Path) -> Optional[dict]:
    """La ficha si está entera y nombra un archivo sin barras ni `..`; si no, None."""
    try:
        ficha = json.loads((carpeta / FICHA).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(ficha, dict):
        return None
    if not all(isinstance(ficha.get(k), str) and ficha[k] for k in ("version", "firma")):
        return None
    if not nombre_valido(ficha.get("archivo")):
        return None
    if not all(isinstance(ficha.get(k, ""), str) for k in ("notas", "fecha")):
        return None
    return ficha


def manifiesto(ficha: dict, origen: str) -> dict:
    datos = {"version": ficha["version"]}
    if ficha.get("notas"):
        datos["notes"] = ficha["notas"]
    if ficha.get("fecha"):
        datos["pub_date"] = ficha["fecha"]
    datos["platforms"] = {"windows-x86_64": {"signature": ficha["firma"],
                                             "url": f"{origen}/api{RUTA_INSTALADOR}"}}
    return datos


def build_router(carpeta: Path, app_origin: Callable[[], str]) -> APIRouter:
    router = APIRouter()

    def origen_de(request: Request) -> str:
        # Detrás de Tailscale serve el pedido llega por http: el origen configurado es el que ve la PC.
        configurado = app_origin()
        if configurado:
            return configurado.rstrip("/")
        return f"{request.url.scheme}://{request.url.netloc}"

    @router.get(RUTA)
    async def actualizacion(request: Request):
        ficha = leer_ultima(carpeta)
        if ficha is None:
            return Response(status_code=204)
        return manifiesto(ficha, origen_de(request))

    @router.get(RUTA_INSTALADOR)
    async def instalador():
        ficha = leer_ultima(carpeta)
        ruta = carpeta / ficha["archivo"] if ficha else None
        if ruta is None or not ruta.is_file():
            raise HTTPException(status_code=404, detail="no hay instalador")
        return FileResponse(ruta, media_type="application/octet-stream", filename=ficha["archivo"])

    return router
