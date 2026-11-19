"""Comentarios sobre líneas del diff de una sesión, mandados a esa sesión en un solo mensaje."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from .avisos import SESSION_RE
from .board import find_session_agent
from .enchufe import TerminalesError
from .envio_sesion import bloque_datos, linea_unica, mandar
from .mensaje import MAX_TEXT
from .nueva_terminal import validar_carpeta
from .traspaso import TraspasoError

MAX_FRAGMENTO = 300
TOPE_DATOS = MAX_TEXT
MAX_RANGO = 200
LADOS = {"nuevo": "líneas nuevas", "viejo": "líneas borradas"}


class Comentario(BaseModel):
    path: str = Field(..., min_length=1, max_length=400)
    lado: Literal["nuevo", "viejo"]
    desde: int = Field(..., ge=1, le=10_000_000)
    hasta: int = Field(..., ge=1, le=10_000_000)
    fragmento: str = Field("", max_length=4000)
    texto: str = Field(..., min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _rango(self):
        if not self.desde <= self.hasta <= self.desde + MAX_RANGO - 1:
            raise ValueError("rango de líneas inválido")
        return self


class ComentariosBody(BaseModel):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$")
    comentarios: list[Comentario] = Field(..., min_length=1, max_length=10)


def _item(n: int, c: Comentario) -> str:
    rango = f"L{c.desde}" if c.desde == c.hasta else f"L{c.desde}-{c.hasta}"
    return f"{n}) {rango} ({LADOS[c.lado]}) → {linea_unica(c.texto, 1000)}"


def _neutro(texto: str, tope: int) -> str:
    return linea_unica(texto, tope).replace("«", "‹").replace("»", "›").replace("→", "->")


def _dato(n: int, c: Comentario) -> str:
    ruta = _neutro(c.path, 400)
    frag = _neutro(c.fragmento, MAX_FRAGMENTO)
    return f"{n}) {ruta} «{frag}»" if frag else f"{n}) {ruta}"


def armar_mensaje(comentarios: list[Comentario]) -> str:
    n = len(comentarios)
    if n == 1:
        cab = ("Ando revisó tus cambios y te deja 1 comentario. Aplicalo en esta rama; si no te cierra o choca "
               "con otra cosa, preguntale antes de seguir.")
    else:
        cab = (f"Ando revisó tus cambios y te deja {n} comentarios. Aplicalos en esta rama; si alguno no te cierra "
               "o choca con otro, preguntale antes de seguir.")
    partes = [cab, *(_item(i, c) for i, c in enumerate(comentarios, 1))]
    datos = [_dato(i, c) for i, c in enumerate(comentarios, 1)]
    partes.append(bloque_datos("archivos y fragmentos del diff", " ".join(datos), TOPE_DATOS))
    return " ".join(partes)


def _norm(linea: str) -> str:
    return " ".join(linea.split())


def _lineas_del_diff(diff: str) -> list[str]:
    out = []
    for raw in (diff or "").splitlines():
        if raw.startswith("@@") or raw.startswith("\\"):
            continue
        out.append(_norm(raw[1:] if raw[:1] in "+- " else raw))
    return out


def fragmento_en_diff(fragmento: str, diff: str) -> bool:
    """Cada línea del fragmento aparece, en orden, entre las líneas del diff (sin prefijo +/-/espacio)."""
    if not fragmento.strip():
        return True
    lineas = iter(_lineas_del_diff(diff))
    return all(any(l == q for l in lineas) for q in (_norm(x) for x in fragmento.splitlines()))


def build_router(*, hub, cambios_svc, mensajes, cfg) -> APIRouter:
    router = APIRouter()

    @router.post("/sesiones/{sid}/cambios/comentarios")
    async def comentarios_a_la_sesion(sid: str, body: ComentariosBody):
        if not SESSION_RE.match(sid):
            raise HTTPException(status_code=400, detail="sid inválido")
        try:
            agent = find_session_agent(await hub.current(), sid)
        except (TerminalesError, OSError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"Las terminales no responden: {exc}")
        if not agent:
            raise HTTPException(status_code=404, detail="sesión no encontrada")
        try:
            carpeta = validar_carpeta(agent.get("cwd") or "", cfg.plan_cwds_con_self())
        except TraspasoError:
            raise HTTPException(status_code=403, detail="La carpeta de la sesión no está entre las permitidas")
        datos = await cambios_svc.cambios(carpeta)
        diffs = {a["path"]: a.get("diff") or "" for a in datos.get("archivos", [])}
        if any(c.path not in diffs for c in body.comentarios):
            raise HTTPException(status_code=409, detail="Ese archivo ya no está entre los cambios: tocá Actualizar")
        if any(not fragmento_en_diff(c.fragmento, diffs[c.path]) for c in body.comentarios):
            raise HTTPException(status_code=400, detail="El fragmento ya no está en el diff: actualizá")
        texto = armar_mensaje(body.comentarios)
        if len(texto) > MAX_TEXT:
            raise HTTPException(status_code=400,
                                detail="Es mucho para un solo mensaje: mandá menos comentarios por vez")
        try:
            await mandar(mensajes, pane_id=agent["pane_id"], texto=texto, origen="comentario-diff",
                         ident=f"cd-{body.id}", destino=agent.get("doing") or "")
        except TraspasoError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail)
        return {"ok": True, "enviados": len(body.comentarios)}

    return router
