import json
import os
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

from .digest import is_system_text, queued_prompt
from .redaccion import ENV_OMITIDO, parece_env, redactar

MAX_TURNO = 8000
MAX_FRAGMENTO = 300
MAX_LEIDO = 2000
MAX_LECTURA = 12 * 1024
MAX_TERMINOS = 8
MAX_POR_SESION = 3
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Turnos de contexto interno, sesiones lanzadas en scratchpads y las de las reuniones (la charla es privada):
# no son trabajo del usuario.
DIR_EXCLUIDO = re.compile(r"(-data-context$|-data-reunion-claude$|-orquestador-reunion-copiloto$|-orquestador-guia$|^-tmp-)")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS archivos(path TEXT PRIMARY KEY, ino INTEGER, size INTEGER, offset INTEGER,
    mtime_ns INTEGER, session_id TEXT, proyecto TEXT, titulo TEXT, primera_ts TEXT, ultima_ts TEXT,
    siguiente INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS turnos(id INTEGER PRIMARY KEY, archivo TEXT, session_id TEXT, idx INTEGER, ts TEXT,
    rol TEXT, rama TEXT, cwd TEXT);
CREATE INDEX IF NOT EXISTS turnos_sesion ON turnos(session_id, idx);
CREATE INDEX IF NOT EXISTS turnos_archivo ON turnos(archivo);
CREATE VIRTUAL TABLE IF NOT EXISTS turnos_fts USING fts5(texto, titulo, tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS meta(clave TEXT PRIMARY KEY, valor TEXT);
"""


def _bloques(content) -> list:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return []


def _texto(bloques: list) -> str:
    partes = [ENV_OMITIDO if parece_env(b) else b for b in bloques if b and b.strip()]
    return "\n".join(partes)


def turno_de(obj: dict) -> Optional[tuple]:
    """(rol, texto) indexable de una línea del transcript, o None."""
    kind = obj.get("type")
    if kind == "attachment":
        texto = queued_prompt(obj)
        return ("usuario", _texto([texto])) if texto.strip() else None
    if kind not in ("user", "assistant") or obj.get("isSidechain") is True:
        return None
    content = (obj.get("message") or {}).get("content")
    if kind == "user":
        if obj.get("isCompactSummary"):
            texto = _texto(_bloques(content))
            return ("resumen", texto) if texto else None
        bloques = _bloques(content)
        texto = "\n".join(b for b in bloques if b)
        if not texto.strip() or is_system_text(obj, texto):
            return None
        return ("usuario", _texto(bloques))
    if not isinstance(content, list):
        return None
    texto = _texto(_bloques(content))
    return ("claude", texto) if texto else None


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _fecha(ts: str) -> str:
    return ts[:10] if isinstance(ts, str) and FECHA_RE.match(ts[:10]) else ""


def conectar_lectura(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=2, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def consulta_fts(consulta: str, modo: str = "AND") -> str:
    terminos = re.findall(r"\w+", (consulta or "").casefold())[:MAX_TERMINOS]
    # Cada término va entre comillas: el texto del usuario nunca se interpreta como sintaxis FTS.
    partes = [f'"{t}"*' if len(t) >= 4 else f'"{t}"' for t in terminos]
    return f" {modo} ".join(partes)


def buscar(conn: sqlite3.Connection, consulta: str, desde: str = "", hasta: str = "", proyecto: str = "",
           limite: int = 5) -> list:
    filtros, params = [], []
    if desde and FECHA_RE.match(desde):
        filtros.append("t.ts >= ?")
        params.append(desde)
    if hasta and FECHA_RE.match(hasta):
        filtros.append("t.ts < ?")
        params.append((date.fromisoformat(hasta) + timedelta(days=1)).isoformat())
    if proyecto:
        filtros.append("t.cwd LIKE ? ESCAPE '\\'")
        params.append(proyecto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    extra = "".join(f" AND {f}" for f in filtros)
    sql = ("SELECT t.session_id, t.idx, t.ts, t.rol, t.rama, t.cwd, a.titulo, "
           "snippet(turnos_fts, 0, '', '', '…', 40) AS frag FROM turnos_fts "
           "JOIN turnos t ON t.id = turnos_fts.rowid JOIN archivos a ON a.path = t.archivo "
           f"WHERE turnos_fts MATCH ?{extra} ORDER BY bm25(turnos_fts, 1.0, 0.5), t.ts DESC LIMIT ?")
    for modo in ("AND", "OR"):
        match = consulta_fts(consulta, modo)
        if not match:
            return []
        rows = conn.execute(sql, [match, *params, limite * 4]).fetchall()
        if rows:
            break
    por_sesion: dict = {}
    elegidos = []
    for r in rows:
        # Si el título coincide, todos los turnos de esa sesión coinciden: no dejar que una sola tape al resto.
        if por_sesion.get(r["session_id"], 0) >= MAX_POR_SESION:
            continue
        por_sesion[r["session_id"]] = por_sesion.get(r["session_id"], 0) + 1
        elegidos.append(r)
        if len(elegidos) >= limite:
            break
    return [{"session_id": r["session_id"], "turno": r["idx"], "fecha": _fecha(r["ts"]), "titulo": r["titulo"] or "",
             "cwd": r["cwd"] or "", "rama": r["rama"] or "", "rol": r["rol"],
             "fragmento": _clip(r["frag"] or "", MAX_FRAGMENTO)} for r in elegidos]


def leer(conn: sqlite3.Connection, session_id: str, turno: int, alrededor: int = 1) -> Optional[dict]:
    rows = conn.execute(
        "SELECT t.idx, t.ts, t.rol, t.rama, t.cwd, f.texto, a.titulo FROM turnos t "
        "JOIN turnos_fts f ON f.rowid = t.id JOIN archivos a ON a.path = t.archivo "
        "WHERE t.session_id = ? AND t.idx BETWEEN ? AND ? ORDER BY t.idx",
        (session_id, turno - alrededor, turno + alrededor)).fetchall()
    if not rows:
        return None
    turnos, total = [], 0
    for r in rows:
        texto = _clip(r["texto"] or "", MAX_LEIDO)
        if total + len(texto) > MAX_LECTURA:
            break
        total += len(texto)
        turnos.append({"turno": r["idx"], "fecha": _fecha(r["ts"]), "rol": r["rol"], "texto": texto})
    first = rows[0]
    return {"session_id": session_id, "titulo": first["titulo"] or "", "cwd": first["cwd"] or "",
            "rama": first["rama"] or "", "turnos": turnos}


def titulo_de(conn: sqlite3.Connection, session_id: str) -> Optional[dict]:
    row = conn.execute("SELECT titulo, ultima_ts FROM archivos WHERE session_id = ? ORDER BY ultima_ts DESC LIMIT 1",
                       (session_id,)).fetchone()
    return {"titulo": row["titulo"] or "", "fecha": _fecha(row["ultima_ts"])} if row else None


class IndiceMemoria:
    """Índice FTS5 de los transcripts. Solo este objeto escribe; el MCP lo abre en modo lectura."""

    def __init__(self, directorio: Path, projects_dir: Path, excluir: Callable[[], list] = lambda: [],
                 retencion_dias: Callable[[], int] = lambda: 0, clock: Callable[[], float] = time.monotonic):
        self.directorio = directorio
        self.path = directorio / "indice.sqlite"
        self.projects_dir = projects_dir
        self.excluir = excluir
        self.retencion_dias = retencion_dias
        self.clock = clock
        self._lock = threading.Lock()

    @property
    def ocupado(self) -> bool:
        return self._lock.locked()

    def _conectar(self) -> sqlite3.Connection:
        self.directorio.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directorio, 0o700)
        if not self.path.exists():
            os.close(os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600))
        os.chmod(self.path, 0o600)
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.executescript(ESQUEMA)
        return conn

    def lectura(self) -> Optional[sqlite3.Connection]:
        return conectar_lectura(self.path) if self.path.exists() else None

    def _archivos(self) -> list:
        if not self.projects_dir.is_dir():
            return []
        out = []
        for path in self.projects_dir.glob("*/*.jsonl"):
            if DIR_EXCLUIDO.search(path.parent.name) or not SESSION_RE.match(path.stem):
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            out.append((path, st))
        out.sort(key=lambda item: item[1].st_mtime_ns, reverse=True)
        return out

    def actualizar(self, presupuesto: Optional[float] = None, esperar: bool = False) -> bool:
        """True si quedó al día. Con presupuesto (s) corta entre archivos y deja el resto para otra pasada."""
        if not self._lock.acquire(blocking=esperar):
            return False
        try:
            inicio = self.clock()
            conn = self._conectar()
            try:
                archivos = self._archivos()
                self._olvidar(conn, {str(p) for p, _ in archivos})
                for path, st in archivos:
                    if presupuesto is not None and self.clock() - inicio > presupuesto:
                        return False
                    self._procesar(conn, path, st)
                self._retencion(conn)
                conn.execute("INSERT OR REPLACE INTO meta(clave, valor) VALUES ('ultima', ?)",
                             (datetime.now(timezone.utc).isoformat(),))
                conn.commit()
                return True
            finally:
                conn.close()
        finally:
            self._lock.release()

    def borrar(self) -> None:
        with self._lock:
            for suffix in ("", "-journal", "-wal", "-shm"):
                try:
                    os.unlink(f"{self.path}{suffix}")
                except FileNotFoundError:
                    pass

    def _borrar_archivo(self, conn: sqlite3.Connection, path: str) -> None:
        conn.execute("DELETE FROM turnos_fts WHERE rowid IN (SELECT id FROM turnos WHERE archivo = ?)", (path,))
        conn.execute("DELETE FROM turnos WHERE archivo = ?", (path,))
        conn.execute("DELETE FROM archivos WHERE path = ?", (path,))

    def _olvidar(self, conn: sqlite3.Connection, vivos: set) -> None:
        # Misma retención que Claude Code: si borró el transcript, el índice lo olvida.
        for row in conn.execute("SELECT path FROM archivos").fetchall():
            if row["path"] not in vivos:
                self._borrar_archivo(conn, row["path"])
        conn.commit()

    def _retencion(self, conn: sqlite3.Connection) -> None:
        dias = self.retencion_dias()
        if not isinstance(dias, int) or isinstance(dias, bool) or dias <= 0:
            return
        corte = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
        conn.execute("DELETE FROM turnos_fts WHERE rowid IN (SELECT id FROM turnos WHERE ts < ?)", (corte,))
        conn.execute("DELETE FROM turnos WHERE ts < ?", (corte,))

    def _excluido(self, cwd: str) -> bool:
        if cwd.startswith("/tmp/"):
            return True
        return any(isinstance(p, str) and p and cwd.startswith(p) for p in self.excluir())

    def _procesar(self, conn: sqlite3.Connection, path: Path, st: os.stat_result) -> None:
        key = str(path)
        prev = conn.execute("SELECT * FROM archivos WHERE path = ?", (key,)).fetchone()
        if prev is not None and (prev["ino"] != st.st_ino or st.st_size < prev["offset"]):
            self._borrar_archivo(conn, key)
            prev = None
        if prev is not None and prev["size"] == st.st_size and prev["mtime_ns"] == st.st_mtime_ns:
            return
        offset = prev["offset"] if prev else 0
        info = {"titulo": prev["titulo"] if prev else "", "proyecto": prev["proyecto"] if prev else "",
                "primera_ts": prev["primera_ts"] if prev else "", "ultima_ts": prev["ultima_ts"] if prev else "",
                "siguiente": prev["siguiente"] if prev else 0}
        nuevos = []
        try:
            with path.open("rb") as fh:
                fh.seek(offset)
                for raw in fh:
                    if not raw.endswith(b"\n"):
                        break  # Línea a medio escribir: se relee en la próxima pasada.
                    offset += len(raw)
                    try:
                        obj = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if obj.get("type") == "ai-title" and isinstance(obj.get("aiTitle"), str):
                        info["titulo"] = obj["aiTitle"][:200]
                        continue
                    turno = turno_de(obj)
                    if turno is None:
                        continue
                    cwd = obj.get("cwd") if isinstance(obj.get("cwd"), str) else ""
                    if self._excluido(cwd):
                        continue
                    rol, texto = turno
                    ts = obj.get("timestamp") if isinstance(obj.get("timestamp"), str) else ""
                    texto = _clip(redactar(texto), MAX_TURNO)
                    if not info["titulo"] and rol == "usuario":
                        info["titulo"] = _clip(" ".join(texto.split()), 80)
                    info["proyecto"] = info["proyecto"] or cwd
                    if ts:
                        info["primera_ts"] = info["primera_ts"] or ts
                        info["ultima_ts"] = max(info["ultima_ts"] or "", ts)
                    rama = obj.get("gitBranch") if isinstance(obj.get("gitBranch"), str) else ""
                    nuevos.append((info["siguiente"], ts, rol, rama[:120], cwd[:300], texto))
                    info["siguiente"] += 1
        except OSError:
            return
        titulo = info["titulo"]
        for idx, ts, rol, rama, cwd, texto in nuevos:
            cur = conn.execute("INSERT INTO turnos(archivo, session_id, idx, ts, rol, rama, cwd) VALUES (?,?,?,?,?,?,?)",
                               (key, path.stem, idx, ts, rol, rama, cwd))
            conn.execute("INSERT INTO turnos_fts(rowid, texto, titulo) VALUES (?, ?, ?)", (cur.lastrowid, texto, titulo))
        if prev is not None and titulo != prev["titulo"]:
            conn.execute("UPDATE turnos_fts SET titulo = ? WHERE rowid IN (SELECT id FROM turnos WHERE archivo = ?)",
                         (titulo, key))
        conn.execute("INSERT OR REPLACE INTO archivos(path, ino, size, offset, mtime_ns, session_id, proyecto, titulo, "
                     "primera_ts, ultima_ts, siguiente) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (key, st.st_ino, st.st_size, offset, st.st_mtime_ns, path.stem, info["proyecto"], titulo,
                      info["primera_ts"], info["ultima_ts"], info["siguiente"]))
        conn.commit()

    def estado(self) -> dict:
        vacio = {"indexados": 0, "turnos": 0, "tamano_mb": 0.0, "ultima_actualizacion": None}
        if not self.path.exists():
            return vacio
        try:
            conn = conectar_lectura(self.path)
            try:
                indexados = conn.execute("SELECT COUNT(*) FROM archivos").fetchone()[0]
                turnos = conn.execute("SELECT COUNT(*) FROM turnos").fetchone()[0]
                row = conn.execute("SELECT valor FROM meta WHERE clave = 'ultima'").fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            return vacio
        return {"indexados": indexados, "turnos": turnos, "tamano_mb": round(self.path.stat().st_size / 1048576, 1),
                "ultima_actualizacion": row[0] if row else None}
