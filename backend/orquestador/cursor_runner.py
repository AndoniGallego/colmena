"""Trabajadores Cursor: `cursor-agent` headless en una copia aparte del repo (git worktree).

Argv fijo, sin shell y sin flags que salteen permisos; el pedido entra por stdin; la salida va a un log
privado con tope. El `await proc.wait()` es el evento de fin: nada de polling.
"""
import asyncio
import json
import logging
import math
import os
import re
import secrets
import shutil
import signal
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Callable, Literal, Optional

from .config import private_write
from .envio_sesion import bloque_datos, linea_unica
from .mensaje import MAX_TEXT
from .nueva_tarea import (_git, base_por_defecto, crear_worktree, quitar_recien_creado, ruta_libre, slug_de,
                          validar_rama)
from .nueva_terminal import es_repo_colmena, validar_carpeta
from .redaccion import redactar_basico
from .traspaso import CONTROL_RE, TraspasoError

log = logging.getLogger("orquestador.cursor")

BINARIO = "cursor-agent"
MAX_SIMULTANEOS = 2
MAX_POR_HORA = 6
VENTANA_HORA = 3600.0
DURACION_MAX = 45 * 60
GRACIA_KILL = 10
ESPERA_COPIA = 5.0  # tope para terminar de copiar el stdout tras la salida o la muerte
GRACIA_CIERRE = 3.0  # al apagar: SIGTERM, esta espera y SIGKILL al grupo
MAX_LOG = 5 * 1024 * 1024
MAX_REGISTRO = 200
MAX_ARCHIVOS = 200
MAX_RESUMEN = 1500
MAX_COLA = 8000
COLA_BYTES = 256 * 1024
MAX_PEDIDO = 4000
MAX_NOMBRE = 60
PEDIDO_CORTO = 200
TID_RE = re.compile(r"^[a-f0-9]{32}$")
MODELO_RE = re.compile(r"^[A-Za-z0-9._\-\[\]=,]{1,80}$")
ESTADOS_FIN = ("ok", "error", "vencido", "cancelado", "interrumpido")
PIE = ("Trabajás en una copia aislada del repo. Editá solo lo necesario para el pedido. No corras comandos: "
       "ni tests, ni builds, ni scripts; no hagas commits ni push; no instales dependencias. Al terminar, resumí en 5 líneas qué cambiaste.")
# Nunca pueden aparecer en el argv (E-3). El test lo verifica sobre la fábrica falsa.
FLAGS_PROHIBIDOS = frozenset({"--force", "-f", "--yolo", "--auto-review", "--approve-mcps", "--api-key", "-H",
                              "--header", "-e", "--endpoint", "--add-dir", "--plugin-dir", "-w", "--worktree"})
_ENV_PREFIJOS = ("ORQ_", "CLAUDE", "ANTHROPIC", "GITLAB", "GLAB", "AWS_", "SSH_AUTH_SOCK", "SSH_AGENT_PID")
_ENV_CONTIENE = ("TOKEN", "SECRET", "PASSWORD", "KEY", "CREDENTIAL")
_ORIGEN_CLAVES = ("tipo", "session_id", "pane_id", "nombre", "programa_id", "corrida_id")
_ORIGEN_TIPOS = frozenset({"claude", "programada", "manual"})
ESTADO_TXT = {"ok": "código 0", "vencido": "tiempo vencido (45 min)", "cancelado": "cancelación de Ando",
              "interrumpido": "el backend reiniciado en el medio"}


def _modelo_valido(modelo: str) -> bool:
    return isinstance(modelo, str) and (not modelo or (bool(MODELO_RE.fullmatch(modelo))
                                                       and not modelo.startswith("-")))


def argv_cursor(binario: str, ruta: str, modelo: str = "") -> list[str]:
    if not _modelo_valido(modelo):
        raise ValueError("modelo inválido")
    argv = [binario, "-p", "--output-format", "stream-json", "--trust", "--sandbox", "enabled", "--workspace", ruta]
    if modelo:
        argv += ["--model", modelo]
    if FLAGS_PROHIBIDOS & set(argv):
        raise ValueError("flag prohibido")
    return argv


def env_filtrado(base: Optional[dict] = None) -> dict:
    """Sin credenciales que Cursor no necesita; HOME y PATH quedan (Cursor usa su login de ~/.cursor)."""
    out = {}
    for k, v in (os.environ if base is None else base).items():
        up = k.upper()
        if up.startswith(_ENV_PREFIJOS) or any(p in up for p in _ENV_CONTIENE):
            continue
        out[k] = v
    return out


def _estado_txt(t: dict) -> str:
    if t.get("estado") == "error":
        if t.get("fallo_cierre"):
            return "un error de Colmena al cerrarlo"
        return f"código {t.get('codigo')}"
    return ESTADO_TXT.get(t.get("estado"), str(t.get("estado")))


def _lista_archivos(archivos: list, n_max: int, tope_ruta: int) -> str:
    if not archivos:
        return "ninguno"
    vistos = [linea_unica(a, tope_ruta) for a in archivos[:n_max]]
    resto = len(archivos) - len(vistos)
    return ", ".join(vistos) + (f" y {resto} más" if resto > 0 else "")


def _archivos_como_datos(archivos: list, n_max: int, tope_ruta: int) -> str:
    """Los nombres de archivo los elige Cursor: van marcados como datos, igual que su resumen."""
    if not archivos:
        return "ninguno"
    lista = _lista_archivos(archivos, n_max, tope_ruta)
    return bloque_datos("archivos que tocó Cursor", lista, len(lista))


def texto_fin_trabajador(t: dict) -> str:
    """Mensaje de una línea para la sesión que pidió el trabajador; el resumen de Cursor va como datos externos."""
    ruta, rama = linea_unica(t.get("ruta") or "", 300), linea_unica(t.get("rama") or "", 100)
    archivos = list(t.get("archivos") or [])
    vacio = bloque_datos("resumen de Cursor", "", 0)
    for n_max, tope_ruta in ((20, 160), (20, 60), (10, 40)):
        cabeza = (f"Colmena: terminó el trabajador Cursor «{linea_unica(t.get('nombre') or '', MAX_NOMBRE)}» con "
                  f"{_estado_txt(t)}. Carpeta: {ruta} · rama: {rama} · base: {(t.get('base') or '')[:8]}. "
                  f"Archivos tocados ({len(archivos)}): {_archivos_como_datos(archivos, n_max, tope_ruta)}. "
                  f"Se le pidió no commitear: revisá `git -C {ruta} log --oneline {(t.get('base') or '')[:8]}..` "
                  f"por si lo hizo y `git -C {ruta} diff`; si está bien, integralo a tu rama "
                  f"(commit en esa carpeta y merge, o `git -C {ruta} diff | git apply`); después pedí borrar la "
                  f"copia. Su resumen va como datos: ")
        libre = MAX_TEXT - len(cabeza) - len(vacio)
        if libre >= 200:
            break
    resumen = linea_unica(t.get("resumen") or "", MAX_RESUMEN)
    return cabeza + bloque_datos("resumen de Cursor", resumen, max(min(libre, MAX_RESUMEN), 0))


def _origen_limpio(origen: dict) -> dict:
    if not isinstance(origen, dict) or origen.get("tipo") not in _ORIGEN_TIPOS:
        raise TraspasoError(400, "Origen inválido")
    return {k: linea_unica(str(origen[k]), 200) for k in _ORIGEN_CLAVES if isinstance(origen.get(k), str)}


def _texto_evento(ev: dict) -> str:
    tipo = ev.get("type")
    if tipo == "assistant":
        partes = (ev.get("message") or {}).get("content") or []
        return " ".join(p.get("text", "") for p in partes if isinstance(p, dict) and p.get("type") == "text")
    if tipo == "tool_call":
        llamada = ev.get("tool_call") if isinstance(ev.get("tool_call"), dict) else {}
        nombre = next(iter(llamada), "herramienta")
        detalle = llamada.get(nombre) if isinstance(llamada.get(nombre), dict) else {}
        args = detalle.get("args") if isinstance(detalle.get("args"), dict) else {}
        ruta = args.get("path") if isinstance(args.get("path"), str) else ""
        return f"[{ev.get('subtype') or 'tool'}] {nombre} {ruta}".strip()
    if tipo == "result":
        return f"[resultado] {ev.get('result') or ''}"
    return ""


def _eventos(raw: str):
    for linea in raw.splitlines():
        try:
            ev = json.loads(linea)
        except ValueError:
            continue
        if isinstance(ev, dict):
            yield ev


class CursorRunner:
    MAX_SIMULTANEOS: int = MAX_SIMULTANEOS

    def __init__(self, directory, worktrees, plan_cwds: Callable[[], list], *, spawn: Callable,
                 emit: Optional[Callable] = None, avisar: Optional[Callable] = None,
                 proceso: Optional[Callable] = None, buscar: Optional[Callable[[], Optional[str]]] = None,
                 matar: Optional[Callable] = None, reloj: Callable[[], float] = time.monotonic,
                 wait_for: Callable = asyncio.wait_for, loop: Optional[Callable] = None):
        self.dir = Path(directory) / "cursor"
        self.path = self.dir / "trabajadores.json"
        self.worktrees = worktrees
        self.plan_cwds = plan_cwds
        self.spawn = spawn
        self.emit = emit
        self.avisar = avisar
        self.proceso = proceso
        self.buscar = buscar or self._buscar
        self.matar = matar or os.killpg
        self.reloj = reloj
        self.wait_for = wait_for
        self.loop = loop or asyncio.get_running_loop
        self.al_terminar: list[Callable[[dict], None]] = []
        self._lanzamientos: deque = deque()
        self._preparando = 0
        self._lock = threading.Lock()
        self._procs: dict[str, object] = {}
        self._cancelados: set[str] = set()
        self._kills: dict[str, object] = {}
        self._items: dict[str, dict] = self._cargar()

    # ---- registro ----
    def _cargar(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        items = data.get("trabajadores") if isinstance(data, dict) else None
        return {t["id"]: t for t in items or [] if isinstance(t, dict) and TID_RE.fullmatch(str(t.get("id", "")))}

    def _guardar(self) -> None:
        with self._lock:
            items = sorted(self._items.values(), key=lambda t: t.get("inicio") or 0)
            sobran = len(items) - MAX_REGISTRO
            if sobran > 0:
                viejos = [t["id"] for t in items if t.get("estado") in ESTADOS_FIN][:sobran]
                for tid in viejos:
                    self._items.pop(tid, None)
                items = [t for t in items if t["id"] not in viejos]
            self._mkdir(self.dir)
            private_write(self.path, json.dumps({"v": 1, "trabajadores": items}, ensure_ascii=False))

    @staticmethod
    def _mkdir(d: Path) -> None:
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(d, 0o700)

    def listar(self) -> list[dict]:
        return [dict(t) for t in sorted(self._items.values(), key=lambda t: t.get("inicio") or 0, reverse=True)]

    def get(self, tid: str) -> Optional[dict]:
        t = self._items.get(tid) if isinstance(tid, str) else None
        return dict(t) if t else None

    def corriendo(self) -> int:
        return sum(1 for t in self._items.values() if t.get("estado") == "corriendo")

    # ---- disponibilidad y topes ----
    @staticmethod
    def _buscar() -> Optional[str]:
        hallado = shutil.which(BINARIO)
        if hallado:
            return hallado
        local = Path.home() / ".local" / "bin" / BINARIO
        return str(local) if local.is_file() and os.access(local, os.X_OK) else None

    def disponible(self) -> bool:
        return bool(self.buscar())

    def _chequear_topes(self) -> None:
        ahora = self.reloj()
        while self._lanzamientos and ahora - self._lanzamientos[0] >= VENTANA_HORA:
            self._lanzamientos.popleft()
        if self.corriendo() + self._preparando >= MAX_SIMULTANEOS:
            raise TraspasoError(429, f"Ya hay {MAX_SIMULTANEOS} trabajadores Cursor corriendo: esperá que termine uno",
                                {"retry_after": 60})
        if len(self._lanzamientos) + self._preparando >= MAX_POR_HORA:
            falta = math.ceil(VENTANA_HORA - (ahora - self._lanzamientos[0]))
            raise TraspasoError(429, f"Ya se lanzaron {MAX_POR_HORA} trabajadores Cursor en la última hora",
                                {"retry_after": max(falta, 1)})

    # ---- lanzar ----
    @staticmethod
    def _validar(pedido, nombre, modelo, base) -> tuple[str, str, str]:
        if not isinstance(pedido, str) or not (1 <= len(pedido.strip()) <= MAX_PEDIDO):
            raise TraspasoError(400, f"El pedido tiene que tener entre 1 y {MAX_PEDIDO} caracteres")
        nombre_ok = linea_unica(nombre, 1000) if isinstance(nombre, str) else ""
        if not (1 <= len(nombre_ok) <= MAX_NOMBRE):
            raise TraspasoError(400, "Falta un nombre corto para el trabajador")
        if not _modelo_valido(modelo):
            raise TraspasoError(400, "Ese modelo no sirve")
        if base not in ("head", "defecto"):
            raise TraspasoError(400, "Base inválida")
        return pedido.strip(), nombre_ok, modelo

    def _preparar_copia(self, carpeta: str, nombre: str, base: str) -> dict:
        """Git sincrónico (va en un hilo): worktree nuevo desde HEAD de la carpeta o la rama por defecto."""
        top = _git(carpeta, "rev-parse", "--show-toplevel").stdout.strip()
        comun = _git(carpeta, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        top_principal = str(Path(comun).parent)
        if base == "head":
            base_ref = _git(carpeta, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            base_sha = _git(carpeta, "rev-parse", "HEAD").stdout.strip()
            if base_ref == "HEAD":
                base_ref = base_sha
        else:
            base_ref = base_por_defecto(top)
            base_sha = _git(top, "rev-parse", f"{base_ref}^{{commit}}").stdout.strip()
        slug = slug_de(nombre)
        rama = validar_rama(f"cursor/{slug}-{secrets.token_hex(2)}")
        ruta = ruta_libre(top_principal, "cursor-" + slug)
        crear_worktree(top, rama, ruta, base_sha)
        return {"repo": top, "rama": rama, "ruta": ruta, "base": base_sha, "base_ref": base_ref}

    def _validar_copia(self, ruta: str) -> None:
        """La copia (y el --workspace) también tiene que caer en una carpeta permitida y fuera de Colmena."""
        try:
            real = validar_carpeta(ruta, self.plan_cwds())
        except TraspasoError:
            raise TraspasoError(400, "La copia quedaría fuera de las carpetas permitidas") from None
        if real != os.path.realpath(ruta) or es_repo_colmena(real):
            raise TraspasoError(400, "La copia quedaría fuera de las carpetas permitidas")

    def _deshacer_copia(self, copia: dict) -> None:
        try:
            self.worktrees.quitar(copia["ruta"])
            quitar_recien_creado(copia["repo"], copia["rama"], copia["ruta"], copia["base"])
        except (TraspasoError, OSError) as exc:
            log.warning("cursor: no pude deshacer la copia (%s)", type(exc).__name__)

    async def lanzar(self, *, carpeta: str, pedido: str, nombre: str, origen: dict,
                     base: Literal["head", "defecto"] = "head", modelo: str = "") -> dict:
        binario = self.buscar()
        if not binario:
            raise TraspasoError(503, "No encuentro cursor-agent en la notebook")
        pedido, nombre, modelo = self._validar(pedido, nombre, modelo, base)
        origen = _origen_limpio(origen)
        # Sin await entre el chequeo y la reserva de `_preparando`: en asyncio esto ya es atómico.
        self._chequear_topes()
        self._preparando += 1
        try:
            real = validar_carpeta(carpeta, self.plan_cwds())
            if es_repo_colmena(real):
                raise TraspasoError(400, "Colmena no lanza trabajadores en su propio repo")
            copia = await asyncio.to_thread(self._preparar_copia, real, nombre, base)
            try:
                self._validar_copia(copia["ruta"])
                # El cupo por hora se gasta recién con la carpeta y git validados.
                self._lanzamientos.append(self.reloj())
                return await self._arrancar(binario, copia, pedido, nombre, origen, modelo)
            except BaseException:
                await asyncio.to_thread(self._deshacer_copia, copia)
                raise
        finally:
            self._preparando -= 1

    async def _arrancar(self, binario: str, copia: dict, pedido: str, nombre: str, origen: dict,
                        modelo: str) -> dict:
        self.worktrees.agregar({"ruta": copia["ruta"], "repo": copia["repo"], "rama": copia["rama"],
                                "base": copia["base_ref"]})
        tid = uuid.uuid4().hex
        d = self.dir / tid
        self._mkdir(self.dir)
        self._mkdir(d)
        private_write(d / "pedido.md", f"{pedido}\n\n{PIE}\n")
        private_write(d / "salida.jsonl", "")
        errores = os.open(d / "errores.log", os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        proceso = self.proceso or asyncio.create_subprocess_exec
        try:
            with open(d / "pedido.md", "r", encoding="utf-8") as entrada:
                proc = await proceso(*argv_cursor(binario, copia["ruta"], modelo), cwd=copia["ruta"],
                                     stdin=entrada, stdout=asyncio.subprocess.PIPE, stderr=errores,
                                     env=env_filtrado(), start_new_session=True)
        except (OSError, ValueError) as exc:
            log.warning("cursor: no pude arrancar cursor-agent (%s)", type(exc).__name__)
            raise TraspasoError(503, "No pude arrancar cursor-agent") from exc
        finally:
            os.close(errores)
        t = {"id": tid, "nombre": nombre, "estado": "corriendo", "ruta": copia["ruta"], "rama": copia["rama"],
             "base": copia["base"], "inicio": int(time.time()), "origen": origen, "pedido": pedido[:PEDIDO_CORTO],
             "modelo": modelo, "codigo": None, "fin": None, "archivos": [], "resumen": "", "log_recortado": False}
        self._items[tid] = t
        self._procs[tid] = proc
        self._guardar()
        self._emitir(tid)
        self.spawn(self._esperar(tid, proc))
        return {k: t[k] for k in ("id", "nombre", "estado", "ruta", "rama", "base", "inicio", "origen")}

    def _emitir(self, tid: str) -> None:
        if self.emit:
            try:
                self.emit("cursor", {"id": tid, "estado": self._items[tid]["estado"]})
            except Exception as exc:
                log.warning("cursor: emit falló (%s)", type(exc).__name__)

    # ---- esperar el fin ----
    async def _copiar_salida(self, tid: str, stdout) -> bool:
        """Copia la salida al log hasta MAX_LOG; el resto se lee y se descarta para no trabar al proceso."""
        escritos, recortado = 0, False
        fd = os.open(self.dir / tid / "salida.jsonl", os.O_WRONLY | os.O_APPEND)
        try:
            while chunk := await stdout.read(65536):
                libre = MAX_LOG - escritos
                if libre <= 0:
                    recortado = True
                    continue
                parte = chunk[:libre]
                recortado = recortado or len(parte) < len(chunk)
                os.write(fd, parte)
                escritos += len(parte)
        finally:
            os.close(fd)
        return recortado

    def _senal(self, proc, sig) -> None:
        """Siempre al grupo (start_new_session): un nieto puede seguir vivo aunque el principal ya salió."""
        try:
            self.matar(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _terminar(self, tid: str, proc) -> None:
        self._senal(proc, signal.SIGTERM)
        if tid not in self._kills:
            self._kills[tid] = self.loop().call_later(GRACIA_KILL, self._senal, proc, signal.SIGKILL)

    async def _esperar(self, tid: str, proc) -> None:
        copia = asyncio.ensure_future(self._copiar_salida(tid, proc.stdout)) if proc.stdout else None
        vencido, codigo, recortado, fallo_cierre = False, None, False, False
        estado, archivos, resumen = "error", [], ""
        try:
            try:
                codigo = await self.wait_for(proc.wait(), DURACION_MAX)
            except asyncio.TimeoutError:
                vencido = True
                self._terminar(tid, proc)
                codigo = await proc.wait()
            # El principal salió: lo que quede del grupo se va igual, y la copia del stdout tiene tope.
            self._senal(proc, signal.SIGTERM)
            if copia:
                recortado = await self._fin_de_copia(copia)
            self._senal(proc, signal.SIGKILL)
            if tid in self._cancelados:
                estado = "cancelado"
            elif vencido:
                estado = "vencido"
            else:
                estado = "ok" if codigo == 0 else "error"
            archivos = await asyncio.to_thread(self._archivos, self._items[tid]["ruta"])
            resumen = self._resumen(tid)
        except asyncio.CancelledError:
            # Se apaga el backend: queda "corriendo" en el registro y al arrancar pasa a "interrumpido".
            if copia and not copia.done():
                copia.cancel()
            raise
        except Exception as exc:
            log.warning("cursor: falló el cierre del trabajador (%s)", type(exc).__name__)
            estado, fallo_cierre = "error", True
        self._fin_trabajador(tid, copia, estado=estado, codigo=codigo, archivos=archivos, resumen=resumen,
                             recortado=recortado, fallo_cierre=fallo_cierre)
        await self._cerrar_trabajador(tid)

    def _fin_trabajador(self, tid: str, copia, *, estado, codigo, archivos, resumen, recortado,
                        fallo_cierre=False) -> None:
        self._procs.pop(tid, None)
        # El grupo ya se mató: el SIGKILL agendado podría caer sobre un pgid reusado.
        kill = self._kills.pop(tid, None)
        if kill is not None and hasattr(kill, "cancel"):
            kill.cancel()
        self._cancelados.discard(tid)
        if copia and not copia.done():
            copia.cancel()
        self._items[tid].update(estado=estado, codigo=codigo, fin=int(time.time()), archivos=archivos,
                                resumen=resumen, log_recortado=recortado, fallo_cierre=fallo_cierre)
        try:
            self._guardar()
        except Exception as exc:
            log.warning("cursor: no pude guardar el registro (%s)", type(exc).__name__)

    async def _fin_de_copia(self, copia) -> bool:
        hecho, _ = await asyncio.wait({copia}, timeout=ESPERA_COPIA)
        if copia not in hecho:
            log.warning("cursor: la salida quedó abierta tras el fin; dejo de copiarla")
            copia.cancel()
            try:
                await copia
            except (asyncio.CancelledError, Exception):
                pass
            return True
        try:
            return copia.result()
        except Exception as exc:
            log.warning("cursor: falló copiar la salida (%s)", type(exc).__name__)
            return False

    async def _cerrar_trabajador(self, tid: str) -> None:
        t = self._items[tid]
        self._emitir(tid)
        if self.avisar:
            try:
                await self.avisar(f"Terminó el trabajador Cursor «{t['nombre']}»", f"Terminó con {_estado_txt(t)}.")
            except Exception as exc:
                log.info("cursor: no pude mandar el push (%s)", type(exc).__name__)
        for fn in list(self.al_terminar):
            try:
                fn(dict(t))
            except Exception as exc:
                log.warning("cursor: al_terminar falló (%s)", type(exc).__name__)

    @staticmethod
    def _archivos(ruta: str) -> list[str]:
        try:
            raw = _git(ruta, "status", "--porcelain", "-z", "--untracked-files=all").stdout
        except TraspasoError:
            return []
        out, partes, i = [], raw.split("\0"), 0
        while i < len(partes) and len(out) < MAX_ARCHIVOS:
            entrada = partes[i]
            i += 1
            if len(entrada) < 4:
                continue
            if entrada[0] in "RC":
                i += 1
            out.append(CONTROL_RE.sub("?", entrada[3:]))
        return out

    def _leer_cola(self, tid: str) -> str:
        try:
            with open(self.dir / tid / "salida.jsonl", "rb") as fh:
                tam = fh.seek(0, os.SEEK_END)
                fh.seek(max(tam - COLA_BYTES, 0))
                return fh.read().decode("utf-8", "replace")
        except OSError:
            return ""

    def _resumen(self, tid: str) -> str:
        ultimo = ""
        for ev in _eventos(self._leer_cola(tid)):
            if ev.get("type") == "result" and isinstance(ev.get("result"), str):
                ultimo = ev["result"]
        return linea_unica(redactar_basico(ultimo), MAX_RESUMEN)

    def cola_log(self, tid: str) -> str:
        if not TID_RE.fullmatch(tid or "") or tid not in self._items:
            return ""
        lineas = [linea_unica(_texto_evento(ev), 1000) for ev in _eventos(self._leer_cola(tid))]
        texto = redactar_basico("\n".join(x for x in lineas if x))
        return texto if len(texto) <= MAX_COLA else "…" + texto[-(MAX_COLA - 1):]

    # ---- cancelar, arranque y apagado ----
    def cancelar(self, tid: str) -> bool:
        proc = self._procs.get(tid)
        if not proc or self._items.get(tid, {}).get("estado") != "corriendo":
            return False
        self._cancelados.add(tid)
        self._terminar(tid, proc)
        return True

    async def al_arrancar(self) -> None:
        """Lo que figuraba corriendo es de un backend anterior: no se puede re-adoptar (E-6)."""
        sueltos = [tid for tid, t in self._items.items() if t.get("estado") == "corriendo" and tid not in self._procs]
        for tid in sueltos:
            self._items[tid].update(estado="interrumpido", codigo=None, fin=int(time.time()))
        if sueltos:
            self._guardar()
        for tid in sueltos:
            await self._cerrar_trabajador(tid)

    async def cerrar(self) -> None:
        procs = list(self._procs.values())
        for proc in procs:
            self._senal(proc, signal.SIGTERM)
        if procs:
            esperas = [asyncio.ensure_future(p.wait()) for p in procs]
            await asyncio.wait(esperas, timeout=GRACIA_CIERRE)
            for e in esperas:
                if not e.done():
                    e.cancel()
        for proc in procs:
            self._senal(proc, signal.SIGKILL)
