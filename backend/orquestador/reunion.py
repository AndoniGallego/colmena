"""Almacén de la reunión en curso: charla, líneas detectadas, límites, diario en disco y caída de la PC."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .mostrar import PREGUNTA_MOSTRAR_MAX, Imagen
from .notas import NotasNoDisponibles

log = logging.getLogger(__name__)

TEXTO_POST_MAX = 2000
CHARLA_MAX = 400_000
LINEAS_MAX = 200
LINEAS_POR_MIN = 6
LINEA_MAX = 90
ITEMS_POR_LLAMADA = 3
TRAMO_CHARS = 3000
SOLAPE_TRAMO = 600
CONTEXTO_CHARS = 1500
ULTIMO_CHARS = 1500
RESUMEN_CHARS = 150_000
RESUMEN_INICIO_CHARS = 30_000
COLA_PREGUNTAS_MAX = 5
ABANDONO_S = 1800
RESPUESTA_MAX = 1200
ARCHIVOS_MAX = 8
ARCHIVO_MAX = 200
REPETIDAS_VENTANA = 30
JACCARD_MIN = 0.8
TIPOS_DETECTADOS = frozenset({"pregunta", "requerimiento"})
TERMINADAS = frozenset({"llena", "terminando", "guardada"})
SIN_RESUMEN = {"titulo": "Reunión sin resumen", "resumen": [], "pendientes": []}
MODELOS = ("haiku", "sonnet")


class ReunionError(Exception):
    def __init__(self, status: int, mensaje: str):
        self.status = status
        self.mensaje = mensaje
        super().__init__(mensaje)


@dataclass(frozen=True)
class AjustesReunion:
    cada_s: int
    tope_detecciones: int
    modelo: str
    modelo_resumen: str


def _entero(v: object, minimo: int, maximo: int, defecto: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        return defecto
    return max(minimo, min(maximo, v))


def _modelo(v: object) -> str:
    return v if isinstance(v, str) and v in MODELOS else "haiku"


def ajustes_reunion(raw: dict) -> AjustesReunion:
    raw = raw if isinstance(raw, dict) else {}
    return AjustesReunion(
        cada_s=_entero(raw.get("cada_s"), 10, 120, 20),
        tope_detecciones=_entero(raw.get("tope_detecciones"), 0, 2000, 180),
        modelo=_modelo(raw.get("modelo")), modelo_resumen=_modelo(raw.get("modelo_resumen")))


def normalizar_linea(texto: str) -> str:
    sin_marcas = "".join(c for c in unicodedata.normalize("NFKD", texto.casefold()) if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in sin_marcas).split())


def es_repetida(nueva: str, previas: list[str]) -> bool:
    n = normalizar_linea(nueva)
    if not n:
        return True
    pn = set(n.split())
    for p in previas[-REPETIDAS_VENTANA:]:
        np = normalizar_linea(p)
        if n == np:
            return True
        pp = set(np.split())
        if pp and len(pn & pp) / len(pn | pp) >= JACCARD_MIN:
            return True
    return False


def _limpio(texto: str) -> str:
    return " ".join("".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Cs", "Zl", "Zp") else c
                            for c in texto).split())


@dataclass
class _Linea:
    id: str
    texto: str
    tipo: str
    ts: float
    fin_chars: int
    respuesta: Optional[dict] = None
    tramo: str = ""
    descartada: bool = False
    nota_id: Optional[str] = None


@dataclass
class _Reunion:
    id: str
    device: str
    inicio: float
    repos: list
    todos: bool
    estado: str = "escuchando"
    tandas: list = field(default_factory=list)
    buffer: str = ""
    lineas: list = field(default_factory=list)
    recientes: deque = field(default_factory=deque)
    detecciones: int = 0
    ultimo_chars: int = 0
    pendiente: object = None
    corriendo: bool = False
    hay_nuevo: bool = False
    copiloto_pane: Optional[str] = None
    abriendo: bool = False
    cola: deque = field(default_factory=deque)
    en_curso: Optional[str] = None
    abandono: object = None

    @property
    def chars(self) -> int:
        return len(self.buffer)


class ReunionStore:
    """`clock` devuelve la hora de pared (epoch): sirve para el reloj de la charla y para el tope por minuto."""

    def __init__(self, *, emitir: Callable, programar: Callable, lanzar: Callable, clock: Callable[[], float],
                 detector, puente, biblioteca, journal_dir: Path, ajustes: AjustesReunion,
                 registrar_foto: Optional[Callable[[str, int, int, int], None]] = None, notas=None):
        self._emitir, self._programar, self._lanzar, self._clock = emitir, programar, lanzar, clock
        self._detector, self._puente, self._biblioteca = detector, puente, biblioteca
        self._dir = Path(journal_dir)
        self._ajustes = ajustes
        self._registrar_foto = registrar_foto
        self._notas = notas
        self._r: Optional[_Reunion] = None
        self._pcs: list[tuple[str, object]] = []
        self._n = 0

    # ---- consultas

    def _get(self, rid: str) -> _Reunion:
        if self._r is None or self._r.id != rid:
            raise ReunionError(404, "No hay una reunión con ese id.")
        return self._r

    def _tope(self, r: _Reunion) -> bool:
        t = self._ajustes.tope_detecciones
        return t > 0 and r.detecciones >= t

    def _estado_ev(self, r: _Reunion) -> dict:
        return {"reunion": r.id, "estado": r.estado, "tope": self._tope(r), "solo_a_mano": self._ajustes.tope_detecciones <= 0,
                "detecciones": r.detecciones,
                "tope_detecciones": self._ajustes.tope_detecciones,
                "copiloto": "abriendo" if r.abriendo else "listo" if r.copiloto_pane else "sin_copiloto",
                "ocupado": r.en_curso is not None}

    def _emitir_estado(self, r: _Reunion) -> None:
        self._emitir("reunion-estado", self._estado_ev(r))

    def snapshot(self) -> dict:
        r = self._r
        if r is None:
            return {}
        return {**self._estado_ev(r), "device": r.device, "repos": list(r.repos), "todos": r.todos,
                "charla_chars": r.chars,
                "lineas": [{"id": x.id, "texto": x.texto, "tipo": x.tipo, "respuesta": x.respuesta, "nota": x.nota_id}
                           for x in r.lineas if not x.descartada]}

    # ---- diario

    def _ruta(self, rid: str) -> Path:
        return self._dir / f"{rid}.jsonl"

    def _diario(self, rid: str, evento: str, **datos) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self._dir, 0o700)
            fd = os.open(self._ruta(rid), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps({"e": evento, **datos}, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            log.warning("no pude escribir el diario de la reunión %s", rid)

    def _borrar_diario(self, rid: str) -> None:
        try:
            self._ruta(rid).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            log.warning("no pude borrar el diario de la reunión %s", rid)

    # ---- empezar y texto

    async def empezar(self, device: str, repos: list[str], todos: bool) -> dict:
        if self._r is not None:
            raise ReunionError(409, "Ya hay una reunión en curso.")
        self._n += 1
        rid = f"r{int(self._clock())}-{self._n}"
        r = _Reunion(id=rid, device=device, inicio=self._clock(), repos=list(repos), todos=bool(todos), abriendo=True)
        self._r = r
        self._diario(rid, "inicio", device=device, repos=r.repos, todos=r.todos, ts=r.inicio)
        self._emitir_estado(r)
        self._lanzar(self._abrir_copiloto(r))
        return {"reunion": rid, "estado": r.estado}

    async def _abrir_copiloto(self, r: _Reunion) -> None:
        """En segundo plano: abrir la sesión tarda lo que tarda Claude en quedar listo."""
        pane = None
        try:
            pane = await self._puente.abrir(r.id, list(r.repos), r.todos)
        except Exception:
            log.exception("no pude abrir el Copiloto de la reunión %s", r.id)
        r.abriendo = False
        if self._r is not r or r.estado in ("terminando", "guardada"):
            if pane:
                await self._cerrar_copiloto(pane)
            return
        r.copiloto_pane = pane or None
        if r.copiloto_pane:
            self._diario(r.id, "copiloto", pane=r.copiloto_pane)
        self._emitir_estado(r)

    def texto(self, rid: str, device: str, texto: str) -> None:
        r = self._get(rid)
        if device != r.device:
            raise ReunionError(409, "Esa reunión es de otro dispositivo.")
        if not isinstance(texto, str) or len(texto) > TEXTO_POST_MAX:
            raise ReunionError(422, f"El texto no puede pasar de {TEXTO_POST_MAX} caracteres.")
        if r.estado not in ("escuchando", "sin_pc"):
            return
        limpio = _limpio(texto)
        if not limpio:
            return
        nuevo = ((" " if r.buffer else "") + limpio)[:max(0, CHARLA_MAX - r.chars)]
        if nuevo.strip():
            r.buffer += nuevo
            r.tandas.append((self._clock(), nuevo.strip()))
            r.hay_nuevo = True
            self._diario(r.id, "texto", ts=r.tandas[-1][0], texto=r.tandas[-1][1])
        if r.chars >= CHARLA_MAX or not nuevo.strip():
            self._cancelar(r, "pendiente")
            r.estado = "llena"
            self._emitir_estado(r)
            return
        self._programar_deteccion(r)

    # ---- detección

    def _cancelar(self, r: _Reunion, que: str) -> None:
        h = getattr(r, que)
        if h is not None:
            h.cancel()
            setattr(r, que, None)

    def _programar_deteccion(self, r: _Reunion) -> None:
        if (r.estado != "escuchando" or not r.hay_nuevo or r.pendiente is not None or r.corriendo
                or self._ajustes.tope_detecciones <= 0 or self._tope(r)):
            return
        r.pendiente = self._programar(self._ajustes.cada_s, lambda: self._arrancar(r))

    def _arrancar(self, r: _Reunion) -> None:
        r.pendiente = None
        if r.estado != "escuchando" or self._r is not r:
            return
        r.corriendo = True
        fin = min(r.chars, r.ultimo_chars + TRAMO_CHARS)
        tramo = r.buffer[max(0, r.ultimo_chars - SOLAPE_TRAMO):fin]
        r.ultimo_chars = fin
        r.hay_nuevo = fin < r.chars
        self._lanzar(self._detectar(r, tramo))

    async def _detectar(self, r: _Reunion, tramo: str) -> None:
        previas = [x.texto for x in r.lineas[-REPETIDAS_VENTANA:]]
        try:
            items = await self._detector.detectar(tramo, previas)
        except Exception:
            log.exception("falló la detección de la reunión %s", r.id)
            items = []
        r.corriendo = False
        r.detecciones += 1
        if self._r is not r or r.estado in TERMINADAS:
            return
        for item in list(items or [])[:ITEMS_POR_LLAMADA]:
            self._sumar_linea_detectada(r, item)
        if self._tope(r):
            self._emitir_estado(r)
        self._programar_deteccion(r)

    def _sumar_linea_detectada(self, r: _Reunion, item: object) -> None:
        if not isinstance(item, dict) or item.get("tipo") not in TIPOS_DETECTADOS:
            return
        texto = _limpio(str(item.get("texto") or ""))[:LINEA_MAX].strip()
        if not texto or len(r.lineas) >= LINEAS_MAX or es_repetida(texto, [x.texto for x in r.lineas]):
            return
        ahora = self._clock()
        while r.recientes and ahora - r.recientes[0] >= 60:
            r.recientes.popleft()
        if len(r.recientes) >= LINEAS_POR_MIN:
            return
        r.recientes.append(ahora)
        self._crear_linea(r, texto, item["tipo"])

    def _crear_linea(self, r: _Reunion, texto: str, tipo: str, tramo: str = "") -> _Linea:
        linea = _Linea(id=f"l{len(r.lineas) + 1}", texto=texto, tipo=tipo, ts=self._clock(),
                       fin_chars=r.chars, tramo=tramo)
        r.lineas.append(linea)
        self._diario(r.id, "linea", id=linea.id, texto=texto, tipo=tipo, ts=linea.ts, fin_chars=linea.fin_chars)
        self._emitir("reunion-linea", {"reunion": r.id, "id": linea.id, "texto": texto, "tipo": tipo})
        return linea

    # ---- pausar y seguir

    def pausar(self, rid: str) -> None:
        r = self._get(rid)
        if r.estado != "escuchando":
            return
        self._cancelar(r, "pendiente")
        r.estado = "pausada"
        self._emitir_estado(r)

    def seguir(self, rid: str) -> None:
        r = self._get(rid)
        if r.estado != "pausada":
            return
        r.estado = "escuchando"
        self._emitir_estado(r)
        self._programar_deteccion(r)

    # ---- preguntas al Copiloto

    def _emitir_respuesta(self, r: _Reunion, linea: _Linea) -> None:
        resp = linea.respuesta or {}
        self._emitir("reunion-respuesta", {"reunion": r.id, "linea": linea.id, "estado": resp.get("estado", ""),
                                           "texto": resp.get("texto", ""), "archivos": resp.get("archivos", [])})

    def _poner_respuesta(self, r: _Reunion, linea: _Linea, estado: str, texto: str = "",
                         archivos: Optional[list] = None) -> None:
        linea.respuesta = {"estado": estado, "texto": texto, "archivos": archivos or []}
        self._emitir_respuesta(r, linea)

    def _contexto(self, r: _Reunion, linea: _Linea) -> str:
        if linea.tramo:
            return linea.tramo
        ini = max(0, linea.fin_chars - CONTEXTO_CHARS * 2 // 3)
        return r.buffer[ini:min(r.chars, ini + CONTEXTO_CHARS)]

    async def tocar(self, rid: str, linea: str) -> str:
        r = self._get(rid)
        lin = next((x for x in r.lineas if x.id == linea), None)
        if lin is None:
            raise ReunionError(404, "No hay una línea con ese id.")
        if lin.descartada:
            raise ReunionError(409, "Esa línea ya se descartó.")
        if lin.tipo == "mostrar":
            raise ReunionError(409, "Volvé a tocar Mostrame.")
        estado = (lin.respuesta or {}).get("estado")
        if estado in ("buscando", "en_cola", "lista"):
            return estado
        if r.estado in TERMINADAS - {"llena"}:
            raise ReunionError(409, "La reunión ya terminó.")
        if not r.copiloto_pane:
            raise ReunionError(409, "El Copiloto no está listo.")
        if r.en_curso is None:
            return await self._enviar(r, lin)
        if len(r.cola) >= COLA_PREGUNTAS_MAX:
            raise ReunionError(429, "Hay demasiadas preguntas en cola.")
        r.cola.append(lin.id)
        self._poner_respuesta(r, lin, "en_cola")
        return "en_cola"

    def _linea(self, r: _Reunion, linea: str) -> _Linea:
        lin = next((x for x in r.lineas if x.id == linea), None)
        if lin is None:
            raise ReunionError(404, "No hay una línea con ese id.")
        return lin

    async def descartar(self, rid: str, linea: str) -> str:
        r = self._get(rid)
        lin = self._linea(r, linea)
        if lin.descartada:
            return "descartada"
        if r.en_curso == lin.id or (lin.respuesta or {}).get("estado") == "buscando":
            raise ReunionError(409, "El Copiloto está buscando esa línea. Esperá que termine para descartarla.")
        if lin.id in r.cola:
            r.cola.remove(lin.id)
        lin.descartada = True
        self._diario(r.id, "descartada", linea=lin.id)
        self._emitir("reunion-descartada", {"reunion": r.id, "linea": lin.id})
        return "descartada"

    def _origen_nota(self, r: _Reunion) -> dict:
        return {"nombre": f"Reunión de las {time.strftime('%H:%M', time.localtime(r.inicio))}"}

    async def anotar(self, rid: str, linea: str) -> dict:
        r = self._get(rid)
        lin = self._linea(r, linea)
        if lin.descartada:
            raise ReunionError(409, "Esa línea ya se descartó.")
        if lin.tipo == "mostrar":
            raise ReunionError(409, "Esa línea no se puede anotar.")
        if lin.nota_id:
            return {"nota": lin.nota_id}
        if self._notas is None:
            raise ReunionError(503, "Las notas no están disponibles.")
        tipo = "recordatorio" if lin.tipo == "requerimiento" else "apunte"
        try:
            nota = self._notas.crear(tipo, lin.texto, self._origen_nota(r))
        except NotasNoDisponibles:
            raise ReunionError(503, "Las notas no están disponibles.") from None
        except ValueError:
            raise ReunionError(422, "No pude armar la nota con esa línea.") from None
        lin.nota_id = nota["id"]
        self._diario(r.id, "anotada", linea=lin.id, nota=lin.nota_id)
        self._emitir("reunion-anotada", {"reunion": r.id, "linea": lin.id, "nota": lin.nota_id})
        return {"nota": lin.nota_id}

    async def _enviar(self, r: _Reunion, lin: _Linea) -> str:
        r.en_curso = lin.id
        self._emitir_estado(r)
        self._poner_respuesta(r, lin, "buscando")
        try:
            msg = self._puente.armar_pregunta(lin.texto, self._contexto(r, lin), list(r.repos))
            await self._puente.preguntar(r.copiloto_pane, lin.id, msg)
        except Exception:
            log.exception("no pude preguntarle al Copiloto (reunión %s)", r.id)
            if r.en_curso == lin.id:
                r.en_curso = None
                self._emitir_estado(r)
            self._poner_respuesta(r, lin, "error")
            self._siguiente(r)
            return "error"
        return "buscando"

    async def mostrar(self, rid: str, device: str, pregunta: str, foto: dict, imagen: Imagen) -> dict:
        r = self._get(rid)
        if device != r.device:
            raise ReunionError(409, "Esa reunión es de otro dispositivo.")
        if r.estado in TERMINADAS - {"llena"}:
            raise ReunionError(409, "La reunión ya terminó.")
        if not r.copiloto_pane:
            raise ReunionError(409, "El Copiloto no está listo.")
        if r.en_curso is not None or r.cola:
            raise ReunionError(409, "El Copiloto está ocupado.")
        texto = _limpio(pregunta if isinstance(pregunta, str) else "")[:PREGUNTA_MOSTRAR_MAX]
        charla = r.tandas[-1][1][:400] if r.tandas else ""
        if not texto and not charla.strip():
            raise ReunionError(422, "Escribí qué querés que te muestre.")
        if len(r.lineas) >= LINEAS_MAX:
            raise ReunionError(429, "Hay demasiadas líneas en la reunión.")
        lin = self._crear_linea(r, texto or "Mostrame", "mostrar")
        r.en_curso = lin.id
        self._emitir_estado(r)
        self._poner_respuesta(r, lin, "buscando")
        try:
            lista = foto["controles"]
            captura, ctl = await self._puente.guardar_captura(imagen.datos, imagen.extension,
                                                              self._puente.texto_controles(lista))
            if self._r is not r or r.estado in TERMINADAS - {"llena"}:
                self._puente.borrar_archivos(captura, ctl)
                raise ReunionError(409, "La reunión ya terminó.")
            if self._registrar_foto is not None:
                self._registrar_foto(r.copiloto_pane, foto["foto"], imagen.ancho, imagen.alto)
            msg = self._puente.armar_mostrar(lin.id, texto, charla, foto["ventana"], captura, ctl, len(lista),
                                             imagen.ancho, imagen.alto)
            await self._puente.preguntar(r.copiloto_pane, lin.id, msg)
        except Exception:
            log.exception("no pude mandarle la captura al Copiloto (reunión %s)", r.id)
            if r.en_curso == lin.id:
                r.en_curso = None
                self._emitir_estado(r)
            self._poner_respuesta(r, lin, "error")
            self._siguiente(r)
            return {"linea": lin.id, "estado": "error"}
        return {"linea": lin.id, "estado": "buscando"}

    def _siguiente(self, r: _Reunion) -> None:
        while r.en_curso is None and r.cola and r.estado not in TERMINADAS - {"llena"}:
            lid = r.cola.popleft()
            lin = next((x for x in r.lineas if x.id == lid), None)
            if lin is not None:
                r.en_curso = lin.id
                self._lanzar(self._enviar(r, lin))

    async def preguntar_ultimo(self, rid: str) -> str:
        r = self._get(rid)
        tramo = r.buffer[-ULTIMO_CHARS:]
        if not tramo.strip():
            raise ReunionError(422, "Todavía no hay charla.")
        if not r.copiloto_pane:
            raise ReunionError(409, "El Copiloto no está listo.")
        if len(r.lineas) >= LINEAS_MAX:
            raise ReunionError(429, "Hay demasiadas líneas en la reunión.")
        if r.en_curso is not None and len(r.cola) >= COLA_PREGUNTAS_MAX:
            raise ReunionError(429, "Hay demasiadas preguntas en cola.")
        lin = self._crear_linea(r, "Lo último de la charla", "manual", tramo)
        await self.tocar(rid, lin.id)
        return lin.id

    def al_stop(self, pane_id: str, texto: str) -> None:
        r = self._r
        if r is None or not r.copiloto_pane or pane_id != r.copiloto_pane or r.en_curso is None:
            return
        lin = next((x for x in r.lineas if x.id == r.en_curso), None)
        r.en_curso = None
        self._emitir_estado(r)
        if lin is None:
            return
        try:
            bloque = self._puente.leer_respuesta(texto, lin.id)
        except Exception:
            bloque = None
        if not isinstance(bloque, dict) or not isinstance(bloque.get("texto"), str):
            self._poner_respuesta(r, lin, "error")
        else:
            crudos = [a for a in (bloque.get("archivos") or []) if isinstance(a, str)]
            if lin.tipo == "mostrar":
                crudos = [a for a in crudos if "/capturas/" not in a.replace("\\", "/")]
            archivos = [a[:ARCHIVO_MAX] for a in crudos][:ARCHIVOS_MAX]
            self._poner_respuesta(r, lin, "lista", bloque["texto"][:RESPUESTA_MAX], archivos)
            self._diario(r.id, "respuesta", linea=lin.id, texto=lin.respuesta["texto"], archivos=archivos)
        self._siguiente(r)

    # ---- caída de la PC

    def pc_volvio(self, device: str, queue: object) -> None:
        if (device, queue) not in self._pcs:
            self._pcs.append((device, queue))
        r = self._r
        if r is None or r.device != device:
            return
        self._cancelar(r, "abandono")
        if r.estado == "sin_pc":
            r.estado = "escuchando"
            self._emitir_estado(r)
            self._programar_deteccion(r)

    def pc_caida(self, device: str, queue: object) -> None:
        self._pcs = [p for p in self._pcs if p != (device, queue)]
        r = self._r
        if r is None or r.device != device or any(d == device for d, _ in self._pcs):
            return
        if r.estado in ("terminando", "guardada") or r.abandono is not None:
            return
        self._cancelar(r, "pendiente")
        if r.estado in ("escuchando", "pausada"):
            r.estado = "sin_pc"
            self._emitir_estado(r)
        r.abandono = self._programar(ABANDONO_S, lambda: self._abandonar(r))

    def _abandonar(self, r: _Reunion) -> None:
        r.abandono = None
        if self._r is r and r.estado not in ("terminando", "guardada"):
            self._lanzar(self._terminar_seguro(r.id, "sin_pc"))

    async def _terminar_seguro(self, rid: str, motivo: str) -> None:
        try:
            await self.terminar(rid, motivo)
        except ReunionError:
            log.warning("no pude guardar la reunión %s (%s)", rid, motivo)

    # ---- terminar

    @staticmethod
    def _hora(ts: float) -> str:
        return time.strftime("%H:%M:%S", time.localtime(ts))

    def _charla(self, r: _Reunion) -> str:
        return "\n".join(f"[{self._hora(ts)}] {t}" for ts, t in r.tandas) + ("\n" if r.tandas else "")

    @staticmethod
    def _recortar(charla: str) -> tuple[str, bool]:
        if len(charla) <= RESUMEN_CHARS:
            return charla, False
        return charla[:RESUMEN_INICIO_CHARS] + "\n[…]\n" + charla[-(RESUMEN_CHARS - RESUMEN_INICIO_CHARS):], True

    def _tocadas(self, r: _Reunion) -> list[dict]:
        return [{"texto": x.texto, "tipo": x.tipo, "respuesta": (x.respuesta or {}).get("texto") or None,
                 "archivos": (x.respuesta or {}).get("archivos", [])}
                for x in r.lineas if x.respuesta and not x.descartada]

    def _datos(self, r: _Reunion, motivo: str, resumen: dict, recortada: bool, fin: float) -> dict:
        return {"v": 1, "reunion": r.id, "inicio": r.inicio, "fin": fin, "duracion_s": max(0, int(fin - r.inicio)),
                "repos": list(r.repos), "motivo": motivo, "titulo": resumen["titulo"],
                "resumen": resumen["resumen"], "pendientes": resumen["pendientes"], "tocadas": self._tocadas(r),
                "lineas": len(r.lineas), "charla_chars": r.chars, "recortada": recortada}

    @staticmethod
    def _resumen_valido(res: object) -> dict:
        if not isinstance(res, dict) or not isinstance(res.get("titulo"), str):
            return dict(SIN_RESUMEN)
        lista = lambda v: [x for x in (v if isinstance(v, list) else []) if isinstance(x, str)][:8]  # noqa: E731
        return {"titulo": res["titulo"] or SIN_RESUMEN["titulo"], "resumen": lista(res.get("resumen")),
                "pendientes": lista(res.get("pendientes"))}

    async def terminar(self, rid: str, motivo: str = "terminada") -> Optional[str]:
        r = self._get(rid)
        if r.estado in ("terminando", "guardada"):
            return None
        previo = r.estado
        self._cancelar(r, "pendiente")
        self._cancelar(r, "abandono")
        r.estado = "terminando"
        self._emitir_estado(r)
        enviada, recortada = self._recortar(self._charla(r))
        try:
            resumen = self._resumen_valido(await self._detector.resumir(enviada, self._tocadas(r)))
        except Exception:
            log.exception("falló el resumen de la reunión %s", rid)
            resumen = dict(SIN_RESUMEN)
        datos = self._datos(r, "llena" if previo == "llena" and motivo == "terminada" else motivo, resumen,
                            recortada, self._clock())
        try:
            # La Biblioteca toma su lock del índice: en un hilo, para no frenar el event loop.
            bid = await asyncio.to_thread(self._biblioteca.guardar, datos, self._charla(r))
        except Exception:
            log.exception("no pude guardar la reunión %s en la Biblioteca", rid)
            r.estado = previo
            self._emitir_estado(r)
            if r.abandono is None and not any(d == r.device for d, _ in self._pcs) and previo in (
                    "sin_pc", "llena"):
                r.abandono = self._programar(ABANDONO_S, lambda: self._abandonar(r))
            raise ReunionError(500, "No pude guardar la reunión.") from None
        self._borrar_diario(rid)
        r.estado = "guardada"
        self._emitir_estado(r)
        self._emitir("reunion-guardada", {"reunion": rid, "biblioteca": bid})
        self._r = None
        if r.copiloto_pane:
            try:
                await self._puente.cerrar(r.copiloto_pane)
            except Exception:
                log.exception("no pude cerrar el Copiloto de la reunión %s", rid)
        return bid

    # ---- recuperar tras un reinicio

    def recuperar(self) -> list[str]:
        """Guarda las reuniones que quedaron en el diario (el backend se reinició) con motivo `interrumpida`
        y sin resumen del modelo. Devuelve los ids de Biblioteca."""
        ids: list[str] = []
        try:
            archivos = sorted(self._dir.glob("*.jsonl"))
        except OSError:
            return ids
        for ruta in archivos:
            try:
                r = self._leer_diario(ruta)
            except (ValueError, TypeError, OverflowError, OSError):
                # Un diario roto no frena a los demás; se loguea solo el nombre, nunca la charla.
                log.warning("diario de reunión roto, lo salteo: %s", ruta.name)
                continue
            if r is None:
                log.warning("diario de reunión ilegible: %s", ruta.name)
                continue
            fin = r.tandas[-1][0] if r.tandas else r.inicio
            datos = self._datos(r, "interrumpida", {**SIN_RESUMEN, "titulo": "Reunión interrumpida"}, False, fin)
            try:
                ids.append(self._biblioteca.guardar(datos, self._charla(r)))
            except Exception:
                log.exception("no pude guardar la reunión recuperada %s", r.id)
                continue
            self._borrar_diario(r.id)
            if r.copiloto_pane:
                self._lanzar(self._cerrar_copiloto(r.copiloto_pane))
        return ids

    async def _cerrar_copiloto(self, pane: str) -> None:
        try:
            await self._puente.cerrar(pane)
        except Exception:
            log.exception("no pude cerrar el Copiloto %s", pane)

    def _leer_diario(self, ruta: Path) -> Optional[_Reunion]:
        r: Optional[_Reunion] = None
        try:
            lineas = ruta.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return None
        for crudo in lineas:
            try:
                ev = json.loads(crudo)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            tipo = ev.get("e")
            if tipo == "inicio" and r is None:
                r = _Reunion(id=ruta.stem, device=str(ev.get("device", "")), inicio=float(ev.get("ts", 0)),
                             repos=[x for x in ev.get("repos", []) if isinstance(x, str)],
                             todos=bool(ev.get("todos")))
            elif r is None:
                continue
            elif tipo == "copiloto" and isinstance(ev.get("pane"), str):
                r.copiloto_pane = ev["pane"]
            elif tipo == "texto" and isinstance(ev.get("texto"), str):
                r.buffer += (" " if r.buffer else "") + ev["texto"]
                r.tandas.append((float(ev.get("ts", r.inicio)), ev["texto"]))
            elif tipo == "linea" and isinstance(ev.get("texto"), str):
                r.lineas.append(_Linea(id=str(ev.get("id")), texto=ev["texto"], tipo=str(ev.get("tipo")),
                                       ts=float(ev.get("ts", r.inicio)), fin_chars=int(ev.get("fin_chars", 0))))
            elif tipo in ("descartada", "anotada"):
                lin = next((x for x in r.lineas if x.id == ev.get("linea")), None)
                if lin is not None and tipo == "descartada":
                    lin.descartada = True
                elif lin is not None and isinstance(ev.get("nota"), str):
                    lin.nota_id = ev["nota"]
            elif tipo == "respuesta":
                lin = next((x for x in r.lineas if x.id == ev.get("linea")), None)
                if lin is not None:
                    lin.respuesta = {"estado": "lista", "texto": str(ev.get("texto", "")),
                                     "archivos": [a for a in ev.get("archivos", []) if isinstance(a, str)]}
        return r
