"""Guía por atajo: una guía paso a paso a la vez, con su ayudante (un pane de Claude) y una PC dueña.

El puente (PuenteGuia) llega por inyección: abre el pane, le pega mensajes, guarda y borra capturas, y
arma/lee los mensajes del ayudante (sus staticmethods `armar_pedido`, `armar_siguiente`, `leer_bloque`,
`texto_controles`). Los tiempos van por `programar`, así los tests no duermen.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Awaitable, Callable, Optional

from .copiloto import borrar_archivos
from .mostrar import Imagen
from .terminales_acciones import TraspasoError

log = logging.getLogger(__name__)

PASOS_MAX = 15
TEXTO_PASO_MAX = 120
PREGUNTA_MAX = 300
APAGADO_S = 600.0
ARRANQUE_S = 60.0
PASO_S = 90.0

NO_ARRANCO = "El ayudante no arrancó, probá de nuevo"
SIN_RESPUESTA = "No me respondió: tocá Hecho, siguiente de nuevo"
TOPE = "Ya arrancaste muchas guías esta hora, probá en un rato"
POR_REUNION = "Empezó una reunión: terminé la guía"
INACTIVA = "La guía se cerró por inactividad: preguntá de nuevo"

REUNION = "Hay una reunión en curso: usá Mostrame del notch"
OTRA_PC = "La guía está en otra PC"
MIRANDO = "Todavía estoy mirando"
SIN_GUIA = "No hay una guía en curso"
SIN_PREGUNTA = "Escribí qué querés hacer"

_CONTROL_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f ​‎‏‪-‮⁦-⁩]")


class GuiaError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje = status, codigo, mensaje


def _limpio(texto: object) -> str:
    t = str(texto).replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return _CONTROL_RE.sub("", t)


def _entero(v: object) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def con_pasos_hechos(pregunta: str, hechos: int) -> str:
    """La pregunta original para un ayudante nuevo a mitad de guía, sin pasar de PREGUNTA_MAX."""
    if hechos <= 0:
        return pregunta[:PREGUNTA_MAX]
    if hechos == 1:
        contexto = "Ando ya hizo el paso 1 de esta guía; seguí con el paso 2."
    else:
        contexto = f"Ando ya hizo los pasos 1 a {hechos} de esta guía; seguí con el paso {hechos + 1}."
    return f"{contexto} {pregunta[:max(PREGUNTA_MAX - len(contexto) - 1, 0)]}"


def acotar(bloque: dict) -> dict:
    """Lo que dice el ayudante es solo para mostrar: paso en 1..15, total en paso..15, texto corto."""
    paso, total, fin = _entero(bloque.get("paso")), _entero(bloque.get("total")), bloque.get("fin") is True
    texto = _limpio(bloque.get("texto", ""))[:TEXTO_PASO_MAX]
    if paso <= 0 and not fin:
        return {"estado": "no_encontrado", "paso": 0, "total": 0, "texto": texto}
    paso = min(max(paso, 1), PASOS_MAX)
    total = min(max(total, paso), PASOS_MAX)
    return {"estado": "fin" if fin else "paso", "paso": paso, "total": total, "texto": texto}


class GuiaStore:
    def __init__(
        self,
        *,
        puente: Any,
        ofrecer: Callable[[object, tuple], None],
        programar: Callable[[float, Callable[[], None]], Any],
        lanzar: Callable[[Awaitable], None],
        pc_objetivo: Callable[[], Optional[str]],
        reunion_activa: Callable[[], bool],
        registrar_foto: Callable[[str, int, int, int], None],
        soltar_nudo: Callable[[str], None],
    ):
        self._puente, self._ofrecer, self._programar, self._lanzar = puente, ofrecer, programar, lanzar
        self._pc_objetivo, self._reunion_activa = pc_objetivo, reunion_activa
        self._registrar_foto, self._soltar_nudo = registrar_foto, soltar_nudo
        self._colas: list[tuple[str, object]] = []
        # Ayudante
        self._ayudante = "apagado"  # apagado | arrancando | listo
        self._pane: Optional[str] = None
        self._hubo_guia = False  # este ayudante ya llevó una guía: el próximo pedido es "Tarea nueva"
        self._arranque = 0  # número del arranque vigente; uno viejo que vuelve tarde se descarta
        self._abierto_con: Optional[str] = None  # turno del mensaje inicial del arranque vigente
        self._pendiente: Optional[dict] = None  # último pedido mientras arranca
        # Guía
        self._n = 0
        self._guia: Optional[int] = None
        self._t = 0
        self._turno: Optional[str] = None
        self._pregunta = ""  # la de la guía en curso, para relanzar un ayudante caído a mitad de guía
        self._dueno: Optional[str] = None
        self._mirando = False
        self._fin = False
        self._paso = 0
        self._total = 0
        # Timers
        self._t_arranque: Any = None
        self._t_paso: Any = None
        self._t_apagado: Any = None

    # ---- colas de la PC

    def pc_conectada(self, device: str, queue: object) -> None:
        if (device, queue) not in self._colas:
            self._colas.append((device, queue))

    def pc_desconectada(self, device: str, queue: object) -> None:
        self._colas = [c for c in self._colas if c != (device, queue)]
        if self._guia is not None and device == self._dueno and not any(d == device for d, _ in self._colas):
            pane = self._pane
            self._terminar_guia()
            if pane:
                self._soltar_nudo(pane)

    def _emitir(self, estado: str, paso: int = 0, total: int = 0, texto: str = "", sigue: bool = False) -> None:
        if self._dueno is None or self._guia is None:
            return
        ev: dict = {"guia": self._guia, "estado": estado, "paso": paso, "total": total, "texto": texto}
        if estado == "error":
            ev["sigue"] = sigue  # solo SIN_RESPUESTA deja la guía viva; el resto la terminó
        for d, q in list(self._colas):
            if d == self._dueno:
                self._ofrecer(q, ("guia", dict(ev)))

    # ---- consultas

    def es_guia(self, sesion: str) -> bool:
        return self._pane is not None and sesion == self._pane

    def snapshot(self) -> dict:
        return {"ayudante": self._ayudante, "pane": self._pane, "dueno": self._dueno, "guia": self._guia,
                "turno": self._turno, "mirando": self._mirando, "paso": self._paso, "total": self._total}

    # ---- timers

    @staticmethod
    def _cancelar(h: Any) -> None:
        if h is not None:
            h.cancel()

    def _reprogramar_apagado(self) -> None:
        self._cancelar(self._t_apagado)
        self._t_apagado = self._programar(APAGADO_S, self._apagado_vencido)

    def _apagado_vencido(self) -> None:
        self._t_apagado = None
        if self._mirando:
            self._reprogramar_apagado()
        elif self._ayudante != "apagado":
            pane = self._pane
            if self._guia is not None:
                self._emitir("error", texto=INACTIVA)
                self._terminar_guia()
                if pane:
                    self._soltar_nudo(pane)
            self._lanzar(self.apagar())

    def _armar_paso(self) -> None:
        self._cancelar(self._t_paso)
        turno = self._turno
        self._t_paso = self._programar(PASO_S, lambda: self._paso_vencido(turno))

    def _paso_vencido(self, turno: Optional[str]) -> None:
        if turno is None or turno != self._turno or not self._mirando:
            return
        self._t_paso = None
        self._mirando = False
        self._emitir("error", texto=SIN_RESPUESTA, sigue=True)

    # ---- guía

    def _terminar_guia(self) -> None:
        self._cancelar(self._t_paso)
        self._t_paso = None
        if self._pendiente is not None:
            borrar_archivos(*self._pendiente["archivos"])
            self._pendiente = None
        try:
            self._puente.borrar_capturas()
        except Exception:
            log.exception("no pude borrar las capturas de la guía")
        self._guia = self._turno = self._dueno = None
        self._pregunta = ""
        self._t = self._paso = self._total = 0
        self._mirando = self._fin = False

    async def _captura(self, foto: dict, imagen: Imagen) -> tuple:
        lista = foto["controles"]
        captura, ctl = await self._puente.guardar_captura(
            imagen.datos, imagen.extension, self._puente.texto_controles(lista))
        return captura, ctl, len(lista)

    async def pedir(self, device: str, pregunta: str, foto: dict, imagen: Imagen) -> dict:
        if self._reunion_activa():
            raise GuiaError(409, "reunion", REUNION)
        if device != self._pc_objetivo() or (self._guia is not None and self._dueno != device):
            raise GuiaError(409, "otra_pc", OTRA_PC)
        texto = _limpio(pregunta if isinstance(pregunta, str) else "").strip()[:PREGUNTA_MAX]
        if not texto:
            raise GuiaError(422, "sin_pregunta", SIN_PREGUNTA)
        self._terminar_guia()
        self._n += 1
        n = self._guia = self._n
        self._t = 1
        turno = self._turno = f"{n}.1"
        self._dueno = device
        self._pregunta = texto
        self._mirando = True
        self._reprogramar_apagado()
        try:
            captura, ctl, cantidad = await self._captura(foto, imagen)
        except Exception:
            if self._guia == n:
                self._terminar_guia()
            raise
        if self._guia != n:
            borrar_archivos(captura, ctl)
            raise GuiaError(409, "sin_guia", SIN_GUIA)

        def mensaje(nueva: bool) -> str:
            return self._puente.armar_pedido(turno, texto, foto["ventana"], captura, ctl, cantidad,
                                             imagen.ancho, imagen.alto, nueva)

        pedido = {"turno": turno, "mensaje": mensaje, "foto": (foto["foto"], imagen.ancho, imagen.alto),
                  "archivos": (captura, ctl)}
        nueva = self._hubo_guia
        self._hubo_guia = True
        return await self._mandar(n, pedido, mensaje(nueva))

    async def siguiente(self, device: str, foto: dict, imagen: Imagen) -> dict:
        if self._guia is None or self._fin:
            raise GuiaError(409, "sin_guia", SIN_GUIA)
        if device != self._dueno:
            raise GuiaError(409, "otra_pc", OTRA_PC)
        if self._mirando:
            raise GuiaError(409, "mirando", MIRANDO)
        n = self._guia
        self._t += 1
        turno = self._turno = f"{n}.{self._t}"
        paso_hecho = self._paso
        self._mirando = True
        self._reprogramar_apagado()
        try:
            captura, ctl, cantidad = await self._captura(foto, imagen)
        except Exception:
            if self._turno == turno:
                self._mirando = False
            raise
        if self._turno != turno:
            borrar_archivos(captura, ctl)
            raise GuiaError(409, "sin_guia", SIN_GUIA)
        msg = self._puente.armar_siguiente(turno, paso_hecho, foto["ventana"], captura, ctl, cantidad,
                                           imagen.ancho, imagen.alto)
        pregunta = con_pasos_hechos(self._pregunta, paso_hecho)

        def mensaje(nueva: bool) -> str:
            # Para un ayudante nuevo: no sabe de la guía, así que va la pregunta original y los pasos hechos.
            return self._puente.armar_pedido(turno, pregunta, foto["ventana"], captura, ctl, cantidad,
                                             imagen.ancho, imagen.alto, nueva)

        pedido = {"turno": turno, "mensaje": mensaje, "inicial": mensaje(False),
                  "foto": (foto["foto"], imagen.ancho, imagen.alto), "archivos": (captura, ctl)}
        return await self._mandar(n, pedido, msg)

    async def _mandar(self, n: int, pedido: dict, msg: str) -> dict:
        """Le pasa el pedido al ayudante: si está listo lo pega, si no lo arranca con el pedido como inicial."""
        if self._ayudante == "arrancando":
            if self._pendiente is not None:
                borrar_archivos(*self._pendiente["archivos"])
            self._pendiente = pedido
            return {"guia": n, "estado": "preparando"}
        if self._ayudante == "listo" and self._pane is not None:
            pane = self._pane
            self._registrar_foto(pane, *pedido["foto"])
            try:
                await self._puente.preguntar(pane, msg)
            except Exception:
                log.warning("el pane de la guía no recibió el pedido: lo vuelvo a levantar")
                if self._turno != pedido["turno"]:
                    return {"guia": n, "estado": "preparando"}
                if self._pane == pane:
                    self._pane = None
                    self._ayudante = "apagado"
            else:
                if self._turno == pedido["turno"]:
                    self._emitir("mirando")
                    self._armar_paso()
                return {"guia": n, "estado": "mirando"}
        if self._ayudante != "arrancando":
            self._arrancar(pedido, pedido.get("inicial", msg))
        return {"guia": n, "estado": "preparando"}

    # ---- arranque del ayudante

    def _arrancar(self, pedido: dict, msg: str) -> None:
        self._ayudante = "arrancando"
        self._pane = None
        self._arranque += 1
        aid = self._arranque
        self._abierto_con = pedido["turno"]
        self._pendiente = pedido
        self._emitir("preparando")
        self._cancelar(self._t_arranque)
        self._t_arranque = self._programar(ARRANQUE_S, lambda: self._arranque_vencido(aid))
        self._lanzar(self._abrir(aid, msg))

    def _al_pane(self, aid: int, pane: str) -> None:
        if aid != self._arranque or self._ayudante != "arrancando":
            return
        self._pane = pane
        if self._pendiente is not None:
            self._registrar_foto(pane, *self._pendiente["foto"])
            self._pendiente["registrada"] = pane

    def _arranque_vencido(self, aid: int) -> None:
        if aid != self._arranque or self._ayudante != "arrancando":
            return
        self._t_arranque = None
        # `abrir` sigue en vuelo: cuando vuelva (bien o con error), ve el arranque viejo y cierra el pane.
        self._fallo_arranque(NO_ARRANCO, cerrar=False)

    def _fallo_arranque(self, texto: str, cerrar: bool) -> None:
        self._cancelar(self._t_arranque)
        self._t_arranque = None
        self._arranque += 1
        pane = self._pane
        self._pane = None
        self._ayudante = "apagado"
        self._hubo_guia = False
        self._abierto_con = None
        self._emitir("error", texto=texto)
        self._terminar_guia()
        if cerrar and pane:
            self._lanzar(self._cerrar_seguro(pane))

    async def _cerrar_seguro(self, pane: str) -> None:
        try:
            await self._puente.cerrar(pane)
        except Exception:
            log.exception("no pude cerrar el pane de la guía %s", pane)

    async def _cerrar_viejo(self, pane: str) -> None:
        """Pane de un arranque viejo: se cierra sin limpiar, que las capturas son de la guía de ahora."""
        try:
            await self._puente.cerrar_pane(pane)
        except Exception:
            log.exception("no pude cerrar un pane viejo de la guía %s", pane)

    async def _abrir(self, aid: int, msg: str) -> None:
        visto: list[str] = []

        def al_pane(p: str) -> None:
            visto.append(p)
            self._al_pane(aid, p)

        try:
            pane = await self._puente.abrir(msg, al_pane)
        except Exception as e:
            if aid == self._arranque:
                if isinstance(e, TraspasoError) and e.status == 429:
                    self._fallo_arranque(TOPE, cerrar=True)
                else:
                    log.exception("no pude arrancar el ayudante de la guía")
                    self._fallo_arranque(NO_ARRANCO, cerrar=True)
            elif visto:
                await self._cerrar_viejo(visto[-1])
            return
        if aid != self._arranque or self._ayudante != "arrancando":
            await self._cerrar_viejo(pane)
            return
        self._cancelar(self._t_arranque)
        self._t_arranque = None
        self._pane = pane
        self._ayudante = "listo"
        pendiente, self._pendiente = self._pendiente, None
        if self._guia is None or pendiente is None or pendiente["turno"] != self._turno:
            return
        if pendiente["turno"] != self._abierto_con:
            # Ando cambió el pedido mientras arrancaba: le pego el último como tarea nueva.
            if pendiente.get("registrada") != pane:
                self._registrar_foto(pane, *pendiente["foto"])
            try:
                await self._puente.preguntar(pane, pendiente["mensaje"](True))
            except Exception:
                log.exception("no pude pegarle el último pedido al ayudante de la guía")
                if aid == self._arranque and self._turno == pendiente["turno"]:
                    self._fallo_arranque(NO_ARRANCO, cerrar=True)
                return
            if self._turno != pendiente["turno"]:
                return
        self._emitir("mirando")
        self._armar_paso()

    # ---- respuesta del ayudante

    def al_stop(self, pane_id: str, texto: str) -> None:
        if self._guia is None or self._pane is None or pane_id != self._pane or not self._mirando:
            return
        try:
            bloque = self._puente.leer_bloque(texto)
        except Exception:
            bloque = None
        # Sin bloque no se sabe de qué turno era: decide el timer del paso.
        if not isinstance(bloque, dict) or bloque.get("guia") != self._turno:
            return
        a = acotar(bloque)
        self._paso, self._total = a["paso"], a["total"]
        self._fin = a["estado"] == "fin"
        self._mirando = False
        self._cancelar(self._t_paso)
        self._t_paso = None
        self._reprogramar_apagado()
        self._emitir(a["estado"], a["paso"], a["total"], a["texto"])

    # ---- fin

    async def salir(self, device: str) -> None:
        if self._guia is None:
            return
        if device != self._dueno:
            raise GuiaError(409, "otra_pc", OTRA_PC)
        pane = self._pane
        self._terminar_guia()
        if pane:
            self._soltar_nudo(pane)

    async def por_reunion(self) -> None:
        pane = self._pane
        if self._guia is not None:
            self._emitir("error", texto=POR_REUNION)
            self._terminar_guia()
            if pane:
                self._soltar_nudo(pane)
        await self.apagar()

    async def apagar(self) -> None:
        for h in (self._t_arranque, self._t_paso, self._t_apagado):
            self._cancelar(h)
        self._t_arranque = self._t_paso = self._t_apagado = None
        self._arranque += 1  # un `abrir` en vuelo cierra su pane al volver
        pane = self._pane
        self._pane = None
        self._ayudante = "apagado"
        self._hubo_guia = False
        self._abierto_con = None
        self._terminar_guia()
        if pane:
            await self._cerrar_seguro(pane)
