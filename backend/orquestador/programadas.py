"""Tareas programadas: pedidos que corren solos en un repo con Claude o Cursor.

Un solo bucle asyncio duerme hasta la próxima corrida (siesta máxima de 15 min y chequeo contra el reloj de pared
al despertar, por si la notebook se suspendió). Las corridas perdidas no se recuperan: se anotan como salteadas.
Colmena nunca aprueba permisos: Claude arranca en modo `default` y Cursor lo decide su propio runner.
"""
import asyncio
import json
import math
import shutil
import logging
import os
import secrets
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from datetime import time as hora_del_dia
from pathlib import Path
from typing import Awaitable, Callable, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError, ConfigDict, Field, field_validator, model_validator

from .config import private_write
from .nueva_tarea import es_raiz_repo
from .cursor_runner import _modelo_valido
from .nueva_terminal import es_repo_colmena, validar_carpeta
from .traspaso import CONTROL_RE, TraspasoError

log = logging.getLogger("orquestador.programadas")

ESTADO_FILE = "programadas.json"
HISTORIAL_FILE = "programadas-historial.jsonl"
# El mensaje lleva un prefijo de hasta ~150 caracteres y NuevaTareaBody.tarea admite 4000.
MAX_PEDIDO = 3800
MAX_PROGRAMAS = 30
MAX_HISTORIAL = 500
MAX_SIMULTANEAS = 2
VENTANA_CLAUDE = 30 * 60
A_TIEMPO = 10 * 60
SIESTA_MAX = 900
MAX_SALTEADAS = 7
MAX_ATRAS = 60
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
DIAS_PLURAL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]
MOTIVO_APAGADA = "la notebook estaba apagada o suspendida"


class Cuando(BaseModel):
    tipo: Literal["diaria", "dias", "semanal"]
    hora: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    dias: list[int] = Field(default_factory=list)
    dia: Optional[int] = Field(None, ge=0, le=6)

    @model_validator(mode="after")
    def _forma(self):
        if self.tipo == "dias":
            if not 1 <= len(self.dias) <= 7 or len(set(self.dias)) != len(self.dias) \
                    or any(isinstance(d, bool) or not 0 <= d <= 6 for d in self.dias) or self.dia is not None:
                raise ValueError("días inválidos")
        elif self.tipo == "semanal":
            if self.dia is None or self.dias:
                raise ValueError("falta el día")
        elif self.dias or self.dia is not None:
            raise ValueError("la diaria no lleva días")
        return self


class ProgramaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(..., min_length=1, max_length=60)
    repo: str = Field(..., max_length=1024)
    pedido: str = Field(..., min_length=1, max_length=MAX_PEDIDO)
    agente: Literal["claude", "cursor"]
    modelo: str = Field("", max_length=80)
    cuando: Cuando

    @field_validator("modelo")
    @classmethod
    def _modelo(cls, v: str) -> str:
        if not _modelo_valido(v):
            raise ValueError("modelo inválido")
        return v


def cuando_texto(c: "Cuando | dict") -> str:
    c = c if isinstance(c, Cuando) else Cuando(**c)
    if c.tipo == "diaria":
        return f"Todos los días a las {c.hora}"
    if c.tipo == "semanal":
        return f"Los {DIAS_PLURAL[c.dia or 0]} a las {c.hora}"
    nombres = [DIAS_CORTOS[d] for d in sorted(c.dias)]
    union = nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
    return f"{union} a las {c.hora}"


def _a_local(naive: datetime, ref: datetime) -> datetime:
    """Instante de una hora de pared local. Hora inexistente: se corre a la válida siguiente; repetida: la primera."""
    zona = ref.tzinfo
    if isinstance(zona, ZoneInfo):
        return naive.replace(tzinfo=zona, fold=0).astimezone(timezone.utc).astimezone(zona)
    return naive.astimezone()


def _coincide(c: Cuando, weekday: int) -> bool:
    if c.tipo == "diaria":
        return True
    if c.tipo == "dias":
        return weekday in c.dias
    return weekday == c.dia


def proxima(cuando: Cuando, desde: datetime) -> datetime:
    """Primer instante estrictamente posterior a `desde` que cumple `cuando`."""
    base = desde if isinstance(desde.tzinfo, ZoneInfo) else desde.astimezone()
    h, m = int(cuando.hora[:2]), int(cuando.hora[3:])
    dia = base.date()
    for _ in range(9):
        if _coincide(cuando, dia.weekday()):
            candidato = _a_local(datetime.combine(dia, hora_del_dia(h, m)), base)
            if candidato > desde:
                return candidato
        dia += timedelta(days=1)
    raise ValueError("sin próxima corrida")


def ocurrencias(cuando: Cuando, desde: datetime, hasta: datetime, maximo: int) -> list[datetime]:
    """Las últimas `maximo` ocurrencias en (desde, hasta], en orden cronológico."""
    desde = max(desde, hasta - timedelta(days=MAX_ATRAS))
    out: list[datetime] = []
    t = proxima(cuando, desde)
    while t <= hasta:
        out.append(t)
        t = proxima(cuando, t)
    return out[-maximo:] if maximo > 0 else []


class Programadas:
    def __init__(self, directorio, *, lanzar_claude: Callable[..., Awaitable[dict]],
                 cursor_runner: Callable[[], Optional[object]], plan_cwds: Callable[[], list],
                 sesion_abierta: Callable[[str], bool], emit: Callable[[str, dict], None],
                 avisar: Optional[Callable[..., Awaitable[None]]] = None,
                 reloj: Callable[[], float] = time.time,
                 ahora: Callable[[], datetime] = lambda: datetime.now().astimezone()):
        self.dir = Path(directorio)
        self.lanzar_claude = lanzar_claude
        self.cursor_runner = cursor_runner
        self.plan_cwds = plan_cwds
        self.sesion_abierta = sesion_abierta
        self.emit = emit
        self.avisar = avisar
        self.reloj = reloj
        self._ahora = ahora
        self._evento = asyncio.Event()
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._enganchados: set[int] = set()
        self._en_vuelo: dict[str, str] = {}
        self._contador_vuelo = 0
        self._ident_en_vuelo: set[str] = set()
        self._estado = self._cargar()
        self._hist = self._cargar_historial()

    # ---------- persistencia ----------

    def _copiar_corrupto(self) -> None:
        try:
            shutil.copy2(self.dir / ESTADO_FILE, self.dir / f"{ESTADO_FILE}.corrupto-{int(time.time())}")
        except OSError:
            log.warning("no pude copiar programadas.json ilegible")

    def _cargar(self) -> dict:
        vacio = {"v": 1, "habilitado": False, "ultimo_chequeo": 0.0, "programas": []}
        try:
            data = json.loads((self.dir / ESTADO_FILE).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return vacio
        except (OSError, ValueError):
            log.warning("programadas.json ilegible: arranco vacío y apagado")
            self._copiar_corrupto()
            return vacio
        if not isinstance(data, dict) or not isinstance(data.get("programas"), list):
            self._copiar_corrupto()
            return vacio
        try:
            ultimo = float(data.get("ultimo_chequeo") or 0)
        except (TypeError, ValueError):
            ultimo = 0.0
        if not math.isfinite(ultimo) or ultimo < 0:
            ultimo = 0.0
        return {"v": 1, "habilitado": data.get("habilitado") is True, "ultimo_chequeo": ultimo,
                "programas": [p for p in data["programas"] if isinstance(p, dict) and p.get("id")]}

    def _guardar(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        private_write(self.dir / ESTADO_FILE, json.dumps(self._estado, ensure_ascii=False))

    def _cargar_historial(self) -> list[dict]:
        out: list[dict] = []
        try:
            for linea in (self.dir / HISTORIAL_FILE).read_text(encoding="utf-8").splitlines():
                try:
                    fila = json.loads(linea)
                except ValueError:
                    continue
                if isinstance(fila, dict) and fila.get("id"):
                    out.append(fila)
        except OSError:
            pass
        return out[-MAX_HISTORIAL:]

    def _guardar_historial(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        del self._hist[:-MAX_HISTORIAL]
        private_write(self.dir / HISTORIAL_FILE, "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in self._hist))

    def _registrar(self, corrida: dict) -> dict:
        self._hist.append(corrida)
        self._guardar_historial()
        self.emit("programadas", {})
        return corrida

    def _actualizar(self, corrida: dict, **cambios) -> None:
        corrida.update(cambios)
        self._guardar_historial()
        self.emit("programadas", {})

    # ---------- lectura ----------

    @property
    def habilitado(self) -> bool:
        return self._estado["habilitado"]

    def _programa(self, pid: str) -> dict:
        for p in self._estado["programas"]:
            if p["id"] == pid:
                return p
        raise TraspasoError(404, "No encuentro esa tarea programada")

    def _con_proxima(self, p: dict) -> dict:
        out = dict(p)
        try:
            out["proxima"] = None if p.get("pausada") else int(proxima(Cuando(**p["cuando"]), self._ahora()).timestamp())
        except (ValueError, TypeError):
            out["proxima"] = None
        return out

    def listar(self) -> dict:
        runner = self.cursor_runner()
        return {"habilitado": self.habilitado,
                "programas": [self._con_proxima(p) for p in self._estado["programas"]],
                "cursor_disponible": bool(runner is not None and runner.disponible())}

    def historial(self, programa_id: Optional[str] = None, limite: int = 100) -> list[dict]:
        limite = max(1, min(int(limite), 200))
        filas = [c for c in reversed(self._hist) if not programa_id or c.get("programa_id") == programa_id]
        return filas[:limite]

    # ---------- altas, bajas y cambios ----------

    def _validar_repo(self, repo: str) -> str:
        real = validar_carpeta(repo, self.plan_cwds())
        if not es_raiz_repo(real):
            raise TraspasoError(400, "Esa carpeta no es la raíz de un repo de git")
        if es_repo_colmena(real):
            raise TraspasoError(400, "Colmena no programa tareas en su propio repo")
        return real

    @staticmethod
    def _limpio(texto: str) -> str:
        return " ".join(CONTROL_RE.sub(" ", texto).split())

    def crear(self, body: ProgramaBody) -> dict:
        if len(self._estado["programas"]) >= MAX_PROGRAMAS:
            raise TraspasoError(409, f"Hay demasiadas tareas programadas (máximo {MAX_PROGRAMAS})")
        repo = self._validar_repo(body.repo)
        ahora = self.reloj()
        p = {**body.model_dump(), "repo": repo, "nombre": self._limpio(body.nombre) or "Tarea",
             "id": secrets.token_hex(16), "pausada": True, "creada": ahora, "actualizada": ahora}
        self._estado["programas"].append(p)
        self._guardar()
        self._cambio()
        return self._con_proxima(p)

    def editar(self, pid: str, body: ProgramaBody) -> dict:
        p = self._programa(pid)
        repo = self._validar_repo(body.repo)
        p.update({**body.model_dump(), "repo": repo, "nombre": self._limpio(body.nombre) or "Tarea",
                  "actualizada": self.reloj()})
        self._guardar()
        self._cambio()
        return self._con_proxima(p)

    def borrar(self, pid: str) -> None:
        p = self._programa(pid)
        self._estado["programas"].remove(p)
        self._guardar()
        self._cambio()

    def pausar(self, pid: str, pausada: bool) -> dict:
        p = self._programa(pid)
        if p["pausada"] != pausada:
            p["pausada"] = pausada
            p["actualizada"] = self.reloj()
            self._guardar()
        self._cambio()
        return self._con_proxima(p)

    def habilitar(self, valor: bool) -> None:
        self._estado["habilitado"] = bool(valor)
        self._estado["ultimo_chequeo"] = max(self._estado["ultimo_chequeo"], self.reloj())
        self._guardar()
        self._cambio()

    def _cambio(self) -> None:
        self.despertar()
        self.emit("programadas", {})

    def despertar(self) -> None:
        self._evento.set()

    # ---------- corridas ----------

    def _abierta(self, c: dict) -> bool:
        if c.get("estado") == "en_curso":
            return True
        if c.get("agente") == "claude" and c.get("estado") == "ok" and c.get("pane_id"):
            return self.reloj() - c.get("inicio", 0) < VENTANA_CLAUDE and bool(self.sesion_abierta(c["pane_id"]))
        return False

    def _motivo_bloqueo(self, programa_id: str) -> Optional[str]:
        abiertas = [c for c in self._hist if self._abierta(c)]
        if any(c.get("programa_id") == programa_id for c in abiertas):
            return "la corrida anterior sigue abierta"
        if programa_id in self._en_vuelo:
            return "la corrida anterior sigue abierta"
        if len(abiertas) + self._contador_vuelo >= MAX_SIMULTANEAS:
            return f"ya hay {MAX_SIMULTANEAS} corridas en curso"
        return None

    def _nueva_corrida(self, p: dict, previsto: float, manual: bool, estado: str, motivo: str = "") -> dict:
        return {"id": secrets.token_hex(16), "programa_id": p["id"], "nombre": p["nombre"], "previsto": previsto,
                "inicio": self.reloj(), "estado": estado, "motivo": motivo, "agente": p["agente"], "manual": manual}

    async def correr(self, programa_id: str, *, manual: bool, ident: Optional[str] = None,
                     previsto: Optional[float] = None) -> dict:
        if ident and ident in self._cache:
            return self._cache[ident]
        if ident and ident in self._ident_en_vuelo:
            raise TraspasoError(409, "Ya la estoy corriendo")
        p = self._programa(programa_id)
        if not manual and (p.get("pausada") or not self.habilitado):
            return self._nueva_corrida(p, previsto or self.reloj(), manual, "salteada", "la tarea ya no está activa")
        motivo = self._motivo_bloqueo(p["id"])
        if motivo:
            if manual:
                raise TraspasoError(409, f"No la corro: {motivo}")
            return self._registrar(self._nueva_corrida(p, previsto or self.reloj(), manual, "salteada", motivo))
        # Reserva síncrona (antes del primer await): el bucle y "Correr ahora" no pueden colarse a la vez.
        self._en_vuelo[p["id"]] = ident or ""
        self._contador_vuelo += 1
        if ident:
            self._ident_en_vuelo.add(ident)
        try:
            corrida = self._nueva_corrida(p, previsto or self.reloj(), manual, "en_curso")
            try:
                self._validar_repo(p["repo"])
                if p["agente"] == "claude":
                    await self._correr_claude(p, corrida)
                else:
                    await self._correr_cursor(p, corrida)
            except TraspasoError as exc:
                corrida.update(estado="fallo", motivo=exc.detail)
            except ValidationError:
                corrida.update(estado="fallo", motivo="El pedido no entra para abrir la tarea: acortalo")
            except Exception as exc:
                log.warning("tarea programada %s falló: %s", p["id"][:8], type(exc).__name__)
                corrida.update(estado="fallo", motivo="No pude abrirla")
            self._registrar(corrida)
        finally:
            self._en_vuelo.pop(p["id"], None)
            self._contador_vuelo -= 1
            if ident:
                self._ident_en_vuelo.discard(ident)
        await self._avisar(p, corrida)
        if ident:
            self._cache[ident] = corrida
            while len(self._cache) > 64:
                self._cache.popitem(last=False)
        return corrida

    async def _correr_claude(self, p: dict, corrida: dict) -> None:
        mensaje = f"Tarea programada «{p['nombre']}» ({cuando_texto(p['cuando'])}). {p['pedido']}"
        creado = await self.lanzar_claude(p["repo"], mensaje, p["nombre"], f"prog{corrida['id'][:20]}")
        corrida.update(estado="ok", pane_id=creado.get("pane_id"), ruta=creado.get("ruta"), rama=creado.get("rama"))
        if creado.get("pegado") is False:
            corrida["motivo"] = "No pude pegar el mensaje: pegalo a mano"

    async def _correr_cursor(self, p: dict, corrida: dict) -> None:
        runner = self.cursor_runner()
        if runner is None or not runner.disponible():
            corrida.update(estado="fallo", motivo="Cursor no está disponible")
            return
        self._enganchar(runner)
        origen = {"tipo": "programada", "programa_id": p["id"], "corrida_id": corrida["id"]}
        t = await runner.lanzar(carpeta=p["repo"], pedido=p["pedido"], nombre=p["nombre"], origen=origen,
                                base="defecto", modelo=p.get("modelo", ""))
        corrida.update(estado="en_curso", trabajador_id=t.get("id"), ruta=t.get("ruta"), rama=t.get("rama"))
        actual = runner.get(t["id"]) if t.get("id") else None
        if actual and actual.get("estado") not in (None, "corriendo"):
            self._cerrar_por_trabajador(corrida, actual)

    def _enganchar(self, runner) -> None:
        if id(runner) not in self._enganchados:
            self._enganchados.add(id(runner))
            runner.al_terminar.append(self._al_terminar)

    @staticmethod
    def _cerrar_por_trabajador(corrida: dict, t: dict) -> None:
        textos = {"vencido": "Cursor tardó demasiado", "cancelado": "Cancelaron el trabajador",
                  "interrumpido": "Se interrumpió"}
        if t.get("estado") == "ok":
            corrida.update(estado="ok", motivo="")
        else:
            corrida.update(estado="error", motivo=textos.get(t.get("estado"), "Cursor terminó con error"))

    def _al_terminar(self, t: dict) -> None:
        for c in self._hist:
            if c.get("estado") == "en_curso" and c.get("trabajador_id") == t.get("id"):
                self._cerrar_por_trabajador(c, t)
                self._guardar_historial()
                self.emit("programadas", {})
                return

    async def _avisar(self, p: dict, c: dict) -> None:
        if self.avisar is None:
            return
        if c["estado"] == "fallo":
            titulo, cuerpo = f"No pude correr «{p['nombre']}»", c["motivo"]
        elif c["estado"] in ("ok", "en_curso"):
            titulo, cuerpo = f"Arrancó la tarea programada «{p['nombre']}»", p["repo"].rsplit(os.sep, 1)[-1]
        else:
            return
        try:
            await self.avisar(titulo, cuerpo, "programada", c.get("pane_id") or "")
        except Exception as exc:
            log.warning("no pude avisar la tarea programada: %s", type(exc).__name__)

    # ---------- bucle ----------

    def _reconciliar(self) -> None:
        """Corridas de Cursor que quedaron `en_curso` de antes de un reinicio: se cierran con lo que diga el runner."""
        pendientes = [c for c in self._hist if c.get("estado") == "en_curso"]
        if not pendientes:
            return
        runner = self.cursor_runner()
        for c in pendientes:
            tid = c.get("trabajador_id")
            t = runner.get(tid) if runner is not None and tid else None
            if t is None:
                self._actualizar(c, estado="error", motivo="Se perdió el rastro del trabajador")
            elif t.get("estado") != "corriendo":
                self._cerrar_por_trabajador(c, t)
                self._actualizar(c)
        if runner is not None:
            self._enganchar(runner)

    async def tick(self) -> None:
        self._reconciliar()
        ahora = self._ahora()
        t_ahora = ahora.timestamp()
        if self._estado["ultimo_chequeo"] > t_ahora + 86400:
            self._estado["ultimo_chequeo"] = t_ahora
        ultimo = self._estado["ultimo_chequeo"] or t_ahora
        if not self.habilitado:
            self._estado["ultimo_chequeo"] = max(self._estado["ultimo_chequeo"], t_ahora)
            self._guardar()
            return
        pendientes: list[tuple[dict, datetime]] = []
        for p in list(self._estado["programas"]):
            if p.get("pausada"):
                continue
            desde = datetime.fromtimestamp(max(ultimo, p.get("actualizada", 0)), tz=ahora.tzinfo)
            try:
                for previsto in ocurrencias(Cuando(**p["cuando"]), desde, ahora, MAX_SALTEADAS):
                    pendientes.append((p, previsto))
            except (ValueError, TypeError):
                log.warning("tarea programada %s con horario inválido", p["id"][:8])
        self._estado["ultimo_chequeo"] = max(self._estado["ultimo_chequeo"], t_ahora)
        self._guardar()
        for p, previsto in sorted(pendientes, key=lambda x: x[1]):
            if t_ahora - previsto.timestamp() > A_TIEMPO:
                self._registrar(self._nueva_corrida(p, previsto.timestamp(), False, "salteada", MOTIVO_APAGADA))
                continue
            try:
                await self.correr(p["id"], manual=False, previsto=previsto.timestamp())
            except Exception as exc:
                log.warning("tarea programada %s: %s", p["id"][:8], type(exc).__name__)

    def _espera(self) -> float:
        if not self.habilitado:
            return SIESTA_MAX
        ahora = self._ahora()
        proximas = []
        for p in self._estado["programas"]:
            if not p.get("pausada"):
                try:
                    proximas.append(proxima(Cuando(**p["cuando"]), ahora))
                except (ValueError, TypeError):
                    continue
        if not proximas:
            return SIESTA_MAX
        return max(1.0, min((min(proximas) - ahora).total_seconds(), SIESTA_MAX))

    async def bucle(self) -> None:
        while True:
            self._evento.clear()
            try:
                await self.tick()
            except Exception as exc:
                log.warning("el bucle de tareas programadas falló: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(self._evento.wait(), timeout=self._espera())
            except asyncio.TimeoutError:
                pass
