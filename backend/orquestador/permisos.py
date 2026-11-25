from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .ganchos.mensaje import MensajeGancho, redactar_entrada
from .ganchos.motivo_rechazo import sanitizar_motivo_rechazo

if TYPE_CHECKING:
    from .ganchos.canal import Conexion

from .jsonl import append_privado
from .locks import PaneLocks
from .permisos_regla import Regla, regla_acotada

ESTADOS_ABIERTOS = ("abierto", "enviando")
_MOTIVO_GANCHO_CERRADO = "la conexión del gancho se cerró"
_MOTIVO_PANE_DESAPARECIDO = "el pane desapareció del tablero"
_MOTIVO_DIALOGO_HERDR = "el diálogo desapareció de la pantalla"
_LOG = logging.getLogger(__name__)
_MAX_TEXTO_PEDIDO = 8000
_CAMPOS_TEXTO_PEDIDO = frozenset({"content", "new_string", "old_string", "plan", "new_source"})
_CLASIFICADOS_CATEGORIAS = frozenset({"auto", "gris", "usuario"})
_CLAVES_REGISTRO_CLASIFICADO = (
    "hora",
    "categoria",
    "regla_politica",
    "motivo_politica",
    "herramienta",
    "entrada",
    "pane_id",
    "session_id",
    "tool_use_id",
)

_CLAVES_REGISTRO_DECISION = (
    "hora",
    "herramienta",
    "entrada",
    "pane_id",
    "session_id",
    "tool_use_id",
)

_ACCIONES = frozenset({"permitir", "rechazar", "siempre"})
_DECISION_POR_TIPO = {
    "app-allow": "permitir",
    "app-deny": "rechazar",
    "app-siempre": "siempre",
}
_TIPO_AUDITORIA_DECISION = {
    "permitir": "app-allow",
    "rechazar": "app-deny",
    "siempre": "app-siempre",
}


class PermisoError(Exception):
    def __init__(self, status: int, detalle: str) -> None:
        self.status = status
        self.detalle = detalle

    def __str__(self) -> str:
        return self.detalle


def _motivo_rechazo(motivo: str | None) -> str:
    limpio = sanitizar_motivo_rechazo(motivo)
    redactado = redactar_entrada(limpio)
    return redactado if isinstance(redactado, str) else limpio


def _recortar_texto_pedido(texto: str) -> str:
    if len(texto) <= _MAX_TEXTO_PEDIDO:
        return texto
    sobrante = len(texto) - _MAX_TEXTO_PEDIDO
    return texto[:_MAX_TEXTO_PEDIDO] + f"…[recortado {sobrante} caracteres]"


def _entrada_publica(entrada: object, clave: str | None = None) -> object:
    if isinstance(entrada, dict):
        return {k: _entrada_publica(v, k) for k, v in entrada.items()}
    if isinstance(entrada, list):
        return [_entrada_publica(v, clave) for v in entrada]
    if isinstance(entrada, str) and clave in _CAMPOS_TEXTO_PEDIDO:
        return _recortar_texto_pedido(entrada)
    return entrada


def _quien_auditoria(tipo: str) -> str:
    if tipo.startswith("app-"):
        return "app"
    if tipo in ("centinela-allow", "gris-subido"):
        return "centinela"
    if tipo == "objecion":
        return "usuario"
    if tipo in ("politica-allow", "clasificado"):
        return "politica"
    if tipo == "terminal":
        return "terminal"
    return "colmena"


def _motivo_nota(motivo: str | None, tope: int = 200) -> str:
    limpio = _motivo_rechazo(motivo or "")
    return limpio[:tope] if len(limpio) > tope else limpio


def _instante_iso(val: float | datetime) -> str:
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val.isoformat()
    return datetime.fromtimestamp(val, tz=timezone.utc).isoformat()


@dataclass
class Pedido:
    id: str
    session_id: str
    tool_use_id: str
    pane_id: str
    herramienta: str
    entrada: dict
    cwd: str | None
    regla: Regla | None
    creado: float
    estado: str
    conexion: Conexion
    visto_bloqueado: bool = False
    permission_mode: str | None = None
    categoria: str | None = None
    regla_politica: str | None = None
    motivo_politica: str | None = None
    avisado: bool = False

    def publico(self) -> dict:
        regla = None
        if self.regla is not None:
            regla = {
                "herramienta": self.regla.herramienta,
                "contenido": self.regla.contenido,
                "archivo": self.regla.archivo,
                "huella": self.regla.huella(),
            }
        return {
            "id": self.id,
            "session_id": self.session_id,
            "pane_id": self.pane_id,
            "herramienta": self.herramienta,
            "entrada": _entrada_publica(self.entrada),
            "estado": self.estado,
            "creado": _instante_iso(self.creado),
            "regla": regla,
            "categoria": self.categoria,
            "regla_politica": self.regla_politica,
            "motivo_politica": self.motivo_politica,
        }


class AuditoriaPermisos:
    def __init__(self, path: Path, wall: Callable[[], datetime | float] | None = None) -> None:
        self.path = path
        self._wall = wall or (lambda: datetime.now(timezone.utc))

    def _hora_iso(self) -> str:
        w = self._wall()
        if isinstance(w, datetime):
            if w.tzinfo is None:
                w = w.replace(tzinfo=timezone.utc)
            return w.isoformat()
        return datetime.fromtimestamp(w, tz=timezone.utc).isoformat()

    def registrar(self, tipo: str, pedido: Pedido | None, **extra) -> bool:
        try:
            linea: dict = {
                "hora": self._hora_iso(),
                "tipo": tipo,
                "quien": _quien_auditoria(tipo),
            }
            if pedido is not None:
                linea["session_id"] = pedido.session_id
                linea["tool_use_id"] = pedido.tool_use_id
                linea["herramienta"] = pedido.herramienta
                linea["entrada"] = _entrada_publica(pedido.entrada)
            else:
                for clave in ("session_id", "tool_use_id", "herramienta", "entrada"):
                    if clave in extra:
                        linea[clave] = extra[clave]
            if "motivo" in extra and extra["motivo"] is not None:
                linea["motivo"] = extra["motivo"]
            if "encargo_id" in extra and extra["encargo_id"] is not None:
                linea["encargo_id"] = extra["encargo_id"]
            if "regla" in extra and extra["regla"] is not None:
                linea["regla"] = extra["regla"]
            for clave in (
                "categoria",
                "regla_politica",
                "motivo_politica",
                "resultado",
                "pane_id",
            ):
                if clave in extra and extra[clave] is not None:
                    linea[clave] = extra[clave]
            return append_privado(self.path, linea)
        except Exception as exc:
            _LOG.warning("No se pudo registrar en la auditoría de permisos: %s", exc)
            return False

    def leer_clasificados(self, limite: int = 200, max_bytes: int = 2_000_000) -> list[dict]:
        try:
            if not self.path.is_file():
                return []
            size = self.path.stat().st_size
            start = max(0, size - max_bytes)
            with self.path.open("rb") as f:
                f.seek(start)
                raw = f.read()
        except Exception:
            return []

        if start > 0:
            corte = raw.find(b"\n")
            if corte == -1:
                return []
            raw = raw[corte + 1 :]

        aprobados_politica: set[tuple[str, str]] = set()
        centinela_por_clave: dict[tuple[str, str], dict] = {}
        subidos: set[tuple[str, str]] = set()
        objeciones: dict[tuple[str, str], dict] = {}
        filas: list[tuple[dict, str | None, str | None]] = []
        por_clave_fila: dict[tuple[str, str], dict] = {}
        for linea in raw.decode("utf-8", errors="replace").splitlines():
            if not linea.strip():
                continue
            try:
                obj = json.loads(linea)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            tipo = obj.get("tipo")
            sid_raw = obj.get("session_id")
            tid_raw = obj.get("tool_use_id")
            clave_aud = (
                (sid_raw, tid_raw)
                if isinstance(sid_raw, str) and isinstance(tid_raw, str)
                else None
            )
            if tipo == "politica-allow" and clave_aud is not None:
                aprobados_politica.add(clave_aud)
                continue
            if tipo == "centinela-allow" and clave_aud is not None:
                motivo_c = obj.get("motivo")
                centinela_por_clave[clave_aud] = {
                    "motivo_centinela": (
                        motivo_c[:200] if isinstance(motivo_c, str) else ""
                    ),
                    "encargo_id": obj.get("encargo_id")
                    if isinstance(obj.get("encargo_id"), str)
                    else None,
                }
                continue
            if tipo == "gris-subido" and clave_aud is not None:
                subidos.add(clave_aud)
                continue
            if tipo == "objecion" and clave_aud is not None:
                nota = obj.get("motivo")
                objeciones[clave_aud] = {
                    "nota": nota if isinstance(nota, str) else "",
                    "hora": obj.get("hora") if isinstance(obj.get("hora"), str) else "",
                }
                continue
            if tipo in _DECISION_POR_TIPO:
                decision = _DECISION_POR_TIPO[tipo]
                existente = por_clave_fila.get(clave_aud) if clave_aud is not None else None
                if existente is not None:
                    existente["decision"] = decision
                    continue
                fila: dict = {"decision": decision}
                for clave in _CLAVES_REGISTRO_DECISION:
                    if clave not in obj:
                        continue
                    valor = obj[clave]
                    if clave == "entrada":
                        valor = _entrada_publica(valor)
                    elif not isinstance(valor, str):
                        continue
                    else:
                        valor = valor[:200]
                    fila[clave] = valor
                sid_f = sid_raw if isinstance(sid_raw, str) else None
                tid_f = tid_raw if isinstance(tid_raw, str) else None
                filas.append((fila, sid_f, tid_f))
                if sid_f is not None and tid_f is not None:
                    por_clave_fila[(sid_f, tid_f)] = fila
                continue
            if tipo != "clasificado":
                continue
            if obj.get("categoria") not in _CLASIFICADOS_CATEGORIAS:
                continue
            sid = obj.get("session_id") if isinstance(obj.get("session_id"), str) else None
            tid = obj.get("tool_use_id") if isinstance(obj.get("tool_use_id"), str) else None
            item: dict = {}
            for clave in _CLAVES_REGISTRO_CLASIFICADO:
                if clave not in obj:
                    continue
                valor = obj[clave]
                if clave == "entrada":
                    valor = _entrada_publica(valor)
                elif clave in ("regla_politica", "motivo_politica") and isinstance(valor, str):
                    valor = valor[:200]
                item[clave] = valor
            filas.append((item, sid, tid))
            if sid is not None and tid is not None:
                por_clave_fila[(sid, tid)] = item

        out: list[dict] = []
        for item, sid, tid in reversed(filas):
            clave_fila = (sid, tid) if sid is not None and tid is not None else None
            if clave_fila is not None and clave_fila in centinela_por_clave:
                item = {**item, "quien": "centinela", **centinela_por_clave[clave_fila]}
            elif clave_fila is not None and clave_fila in aprobados_politica:
                item = {**item, "quien": "politica"}
            else:
                item = {**item, "quien": "usuario"}
            if clave_fila is not None and clave_fila in subidos:
                item["subido"] = True
            if clave_fila is not None and clave_fila in objeciones:
                item["objecion"] = objeciones[clave_fila]
            out.append(item)
            if len(out) >= limite:
                break
        return out


class PermisosService:
    def __init__(
        self,
        auditoria: AuditoriaPermisos,
        locks: PaneLocks,
        *,
        espera: Callable[[], float],
        desde_app: Callable[[], bool],
        avisar: Callable[[Pedido], None] = lambda p: None,
        al_cambiar: Callable[[], None] = lambda: None,
        al_cerrar: Callable[[Pedido], None] = lambda p: None,
        al_decidir: Callable[[str], None] = lambda sid: None,
        realpath=os.path.realpath,
        wall: Callable[[], float] = time.time,
        responder_timeout: float = 2.0,
        estado_pane: Callable[[str], str | None] | None = None,
    ) -> None:
        self.auditoria = auditoria
        self.locks = locks
        self.espera = espera
        self.desde_app = desde_app
        self.avisar = avisar
        self.al_cambiar = al_cambiar
        self.al_cerrar = al_cerrar
        self.al_decidir = al_decidir
        self.realpath = realpath
        self._wall = wall
        self.responder_timeout = responder_timeout
        self._estado_pane = estado_pane
        self._por_clave: dict[tuple[str, str], Pedido] = {}
        self._por_id: dict[str, Pedido] = {}
        self._cerrados: deque[Pedido] = deque(maxlen=20)
        self._vigilancias: set[asyncio.Task] = set()

    def _programar_vigilancia(self, p: Pedido) -> None:
        tarea = asyncio.create_task(self._vigilar(p))
        self._vigilancias.add(tarea)
        tarea.add_done_callback(self._vigilancias.discard)

    def _finalizar_pedido_resuelto(
        self,
        p: Pedido,
        estado: str,
        tipo_aud: str,
        *,
        motivo: str | None = None,
        **extra_aud,
    ) -> None:
        p.estado = estado
        try:
            p.conexion.cerrar()
            self.auditoria.registrar(tipo_aud, p, motivo=motivo, **extra_aud)
        finally:
            self._cerrar_pedido(p)

    def _pedidos_abiertos_sesion(self, session_id: str) -> list[Pedido]:
        return [
            ped
            for ped in self._por_id.values()
            if ped.session_id == session_id and ped.estado == "abierto"
        ]

    def _pedidos_abiertos_pane(self, pane_id: str) -> list[Pedido]:
        return [
            ped
            for ped in self._por_id.values()
            if ped.pane_id == pane_id and ped.estado == "abierto"
        ]

    @staticmethod
    def _senal_resuelve_pedido(
        p: Pedido, evento: str, tool_use_id: str | None
    ) -> bool:
        if evento in ("PostToolUse", "PostToolUseFailure") and tool_use_id == p.tool_use_id:
            return True
        return evento in ("Stop", "UserPromptSubmit")

    async def resolver_en_terminal(self, p: Pedido, motivo: str, avisar: bool = True) -> None:
        cambio = False
        async with self.locks.get(p.pane_id):
            if p.estado != "abierto":
                return
            self._finalizar_pedido_resuelto(p, "terminal", "terminal", motivo=motivo)
            cambio = True
        if cambio:
            self.al_cambiar()
            if avisar:
                self._avisar_decidido(p.session_id)

    def _avisar_decidido(self, session_id: str) -> None:
        try:
            self.al_decidir(session_id)
        except Exception:
            _LOG.warning("al_decidir falló", exc_info=True)

    async def senal(
        self, session_id: str, evento: str, tool_use_id: str | None
    ) -> None:
        for p in self._pedidos_abiertos_sesion(session_id):
            if self._senal_resuelve_pedido(p, evento, tool_use_id):
                await self.resolver_en_terminal(
                    p, motivo=f"señal {evento}",
                    avisar=evento not in ("Stop", "UserPromptSubmit"),
                )

    async def observar_herdr(
        self, pane_id: str, status_herdr: str | None
    ) -> None:
        pedidos = self._pedidos_abiertos_pane(pane_id)
        if not pedidos:
            return
        if status_herdr is None:
            for p in pedidos:
                await self.resolver_en_terminal(
                    p, motivo=_MOTIVO_PANE_DESAPARECIDO, avisar=False
                )
            return
        if status_herdr == "blocked":
            for p in pedidos:
                p.visto_bloqueado = True
            return
        for p in pedidos:
            if p.visto_bloqueado and status_herdr != "blocked":
                await self.resolver_en_terminal(p, motivo=_MOTIVO_DIALOGO_HERDR)

    async def _vigilar(self, p: Pedido) -> None:
        try:
            try:
                timeout = self.espera()
            except Exception:
                _LOG.warning(
                    "permisos.espera() falló; se usa 120 s para la vigilancia",
                    exc_info=True,
                )
                timeout = 120.0
            await asyncio.wait_for(p.conexion.cerrada.wait(), timeout)
        except asyncio.TimeoutError:
            cambio = False
            async with self.locks.get(p.pane_id):
                if p.estado != "abierto":
                    return
                self._finalizar_pedido_resuelto(p, "vencido", "vencido")
                cambio = True
            if cambio:
                self.al_cambiar()
            return

        cambio = False
        async with self.locks.get(p.pane_id):
            if p.estado != "abierto":
                return
            self._finalizar_pedido_resuelto(
                p, "terminal", "terminal", motivo=_MOTIVO_GANCHO_CERRADO
            )
            cambio = True
        if cambio:
            self.al_cambiar()

    async def cerrar_todo(self) -> None:
        cambio = False
        for p in list(self._por_id.values()):
            if p.estado != "abierto":
                continue
            self._finalizar_pedido_resuelto(p, "dialogo", "reinicio")
            cambio = True
        tareas = list(self._vigilancias)
        for t in tareas:
            t.cancel()
        if tareas:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tareas, return_exceptions=True),
                    2.0,
                )
            except asyncio.TimeoutError:
                pass
        if cambio:
            self.al_cambiar()

    def _avisar_una_vez(self, p: Pedido) -> None:
        if p.avisado:
            return
        p.avisado = True
        self.avisar(p)

    def _cerrar_pedido(self, p: Pedido) -> None:
        clave = (p.session_id, p.tool_use_id)
        self._por_clave.pop(clave, None)
        if p.estado not in ESTADOS_ABIERTOS:
            if len(self._cerrados) == self._cerrados.maxlen:
                desalojado = self._cerrados[0]
                self._por_id.pop(desalojado.id, None)
            self._cerrados.append(p)
        try:
            self.al_cerrar(p)
        except Exception:
            _LOG.debug("al_cerrar falló", exc_info=True)

    def ver(self, pedido_id: str) -> Pedido | None:
        return self._por_id.get(pedido_id)

    def abierto_para(self, session_id: str) -> Pedido | None:
        for p in self._por_id.values():
            if p.session_id == session_id and p.estado in ESTADOS_ABIERTOS:
                return p
        return None

    def listar(self) -> list[dict]:
        abiertos = [
            p.publico()
            for p in self._por_id.values()
            if p.estado in ESTADOS_ABIERTOS
        ]
        cerrados = [p.publico() for p in self._cerrados]
        return abiertos + cerrados

    async def atender(
        self,
        msg: MensajeGancho,
        pane_id: str | None,
        conexion: Conexion,
    ) -> Pedido | None:
        herramienta = msg.herramienta or ""
        if not self.desde_app() or herramienta == "AskUserQuestion":
            conexion.cerrar()
            return None

        session_id = msg.ids.claude
        tool_use_id = msg.tool_use_id
        if not session_id or not tool_use_id:
            conexion.cerrar()
            return None

        tool_input = msg.datos.get("tool_input")
        if not isinstance(tool_input, dict):
            conexion.cerrar()
            return None

        if pane_id is None:
            self.auditoria.registrar(
                "sin-dueno",
                None,
                session_id=session_id,
                tool_use_id=tool_use_id,
                herramienta=herramienta,
                entrada=redactar_entrada(tool_input),
            )
            conexion.cerrar()
            return None

        clave = (session_id, tool_use_id)
        cwd = msg.datos.get("cwd")
        cwd_str = cwd if isinstance(cwd, str) else None
        entrada_redactada = redactar_entrada(tool_input)
        regla = regla_acotada(
            herramienta, tool_input, cwd_str, realpath=self.realpath
        )

        async with self.locks.get(pane_id):
            existente = self._por_clave.get(clave)
            if existente is not None:
                conexion.cerrar()
                return existente

            visto_bloqueado = False
            if self._estado_pane is not None:
                estado_inicial = self._estado_pane(pane_id)
                if estado_inicial == "blocked":
                    visto_bloqueado = True

            pm = msg.datos.get("permission_mode")
            permission_mode = pm if isinstance(pm, str) else None

            p = Pedido(
                id=secrets.token_urlsafe(12),
                session_id=session_id,
                tool_use_id=tool_use_id,
                pane_id=pane_id,
                herramienta=herramienta,
                entrada=entrada_redactada,
                cwd=cwd_str,
                regla=regla,
                creado=self._wall(),
                estado="abierto",
                conexion=conexion,
                visto_bloqueado=visto_bloqueado,
                permission_mode=permission_mode,
            )

            if not self.auditoria.registrar("pedido", p):
                conexion.cerrar()
                return None

            self._por_clave[clave] = p
            self._por_id[p.id] = p

        self._programar_vigilancia(p)
        self.al_cambiar()
        self._avisar_una_vez(p)
        return p

    async def decidir(
        self,
        pedido_id: str,
        accion: str,
        motivo: str | None = None,
        huella_regla: str | None = None,
        quien: str = "app",
    ) -> dict:
        if quien != "app":
            raise PermisoError(400, "Solo el usuario decide permisos")
        if accion not in _ACCIONES:
            raise PermisoError(422, "acción inválida")

        p = self.ver(pedido_id)
        if p is None:
            raise PermisoError(404, "pedido no encontrado")

        if not self.desde_app():
            raise PermisoError(409, "permisos desde la app apagados")

        async with self.locks.get(p.pane_id):
            if p.estado != "abierto":
                raise PermisoError(409, p.estado)

            if accion == "siempre":
                if p.regla is None:
                    raise PermisoError(409, "sin regla acotada")
                if huella_regla != p.regla.huella():
                    raise PermisoError(409, "la regla cambió")

            tipo_aud = _TIPO_AUDITORIA_DECISION[accion]
            extra_aud: dict = {"pane_id": p.pane_id}
            if accion == "rechazar":
                extra_aud["motivo"] = _motivo_rechazo(motivo)
            if accion == "siempre" and p.regla is not None:
                extra_aud["regla"] = {
                    "herramienta": p.regla.herramienta,
                    "contenido": p.regla.contenido,
                    "archivo": p.regla.archivo,
                }

            if not self.auditoria.registrar(tipo_aud, p, **extra_aud):
                p.conexion.cerrar()
                p.estado = "dialogo"
                self._cerrar_pedido(p)
                self.al_cambiar()
                raise PermisoError(503, "sin auditoría: se contesta en el diálogo")

            p.estado = "enviando"
            payload = self._payload_decision(p, accion, motivo)
            try:
                ok = await asyncio.wait_for(
                    p.conexion.responder(payload), self.responder_timeout
                )
            except asyncio.CancelledError:
                p.estado = "terminal"
                p.conexion.cerrar()
                self._cerrar_pedido(p)
                self.al_cambiar()
                raise
            except Exception:
                ok = False

            if ok:
                p.estado = {"permitir": "permitido", "rechazar": "rechazado", "siempre": "siempre"}[
                    accion
                ]
                self._cerrar_pedido(p)
                self.al_cambiar()
                self._avisar_decidido(p.session_id)
                return p.publico()

            p.estado = "terminal"
            p.conexion.cerrar()
            self._cerrar_pedido(p)
            self.al_cambiar()
            raise PermisoError(409, "el pedido ya no espera")

    def _payload_decision(self, p: Pedido, accion: str, motivo: str | None) -> dict:
        if accion == "permitir":
            return {"v": 1, "decision": "allow"}
        if accion == "rechazar":
            return {"v": 1, "decision": "deny", "mensaje": _motivo_rechazo(motivo)}
        assert p.regla is not None
        return {
            "v": 1,
            "decision": "siempre",
            "reglas": [p.regla.como_permiso()],
        }
