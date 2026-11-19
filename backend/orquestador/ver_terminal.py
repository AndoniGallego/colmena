"""Engancharse a una terminal del guardián desde la notebook (como tmux attach)."""
from __future__ import annotations

import asyncio
import codecs
import contextlib
import json
import os
import re
import sys
import termios
import tty
from collections.abc import Sequence
from pathlib import Path

from orquestador.guardian.protocolo import VERSION, leer_mensaje
from orquestador.terminales import short_cwd

_ESCAPE_SALIR = "\x1d"  # Ctrl+]
_ESCAPE_BYTES = b"\x1d"


def ruta_guardian_socket(environ: dict | None = None) -> Path | None:
    base = (environ if environ is not None else os.environ).get("XDG_RUNTIME_DIR")
    if not base:
        return None
    return Path(base) / "colmena-guardian" / "guardian.sock"


def filas_de_tablero(tab: dict) -> list[dict]:
    espacios: dict[str, str] = {}
    for e in tab.get("espacios") or []:
        if isinstance(e, dict) and isinstance(e.get("id"), str):
            espacios[e["id"]] = str(e.get("nombre") or e["id"])
    lineas: dict[str, tuple[str, str]] = {}
    for lin in tab.get("lineas") or []:
        if not isinstance(lin, dict):
            continue
        lid = lin.get("id")
        eid = lin.get("espacio_id")
        if isinstance(lid, str) and isinstance(eid, str):
            lineas[lid] = (eid, str(lin.get("nombre") or lid))
    out: list[dict] = []
    for s in tab.get("sesiones") or []:
        if not isinstance(s, dict):
            continue
        sid = s.get("id")
        lid = s.get("linea_id")
        eid = s.get("espacio_id")
        if not isinstance(sid, str):
            continue
        tarjeta = espacios.get(eid or "", eid or "?")
        pestana = lineas.get(lid or "", ("", "?"))[1] if lid else "?"
        prog = s.get("programa")
        tipo = "claude" if prog == "claude" else "terminal"
        cwd = str(s.get("cwd") or "")
        out.append(
            {
                "sesion_id": sid,
                "tarjeta": tarjeta,
                "pestana": pestana,
                "tipo": tipo,
                "carpeta": cwd,
            }
        )
    return out


_ES_ID = re.compile(r"g\d+:p\d+")


def buscar_indice(filas: Sequence[dict], sel: str) -> int | None:
    if not sel:
        return None
    if sel.isdigit():
        n = int(sel)
        if 1 <= n <= len(filas):
            return n - 1
        return None
    q = sel.casefold()
    if _ES_ID.fullmatch(q):
        for i, f in enumerate(filas):
            if f["sesion_id"].casefold() == q:
                return i
    for i, f in enumerate(filas):
        if f["pestana"].casefold() == q or f["sesion_id"].casefold() == q:
            return i
    return None


def imprimir_listado(filas: Sequence[dict]) -> None:
    if not filas:
        print("No hay terminales del guardián abiertas.")
        return
    for i, f in enumerate(filas, start=1):
        carp = short_cwd(f["carpeta"])
        sid = f.get("sesion_id") or ""
        print(f"{i:>3}  {f['tarjeta']} / {f['pestana']}  [{f['tipo']}]  {carp}" + (f"  ({sid})" if sid else ""))


def _linea_entrada(foto: dict | None) -> str:
    base = "Ctrl+] para salir"
    if isinstance(foto, dict):
        cols = foto.get("columnas")
        filas = foto.get("filas")
        if isinstance(cols, int) and isinstance(filas, int) and cols > 0 and filas > 0:
            return f"{base} · se usa el tamaño de la terminal de Colmena ({cols}x{filas})"
    return base


async def _pedir(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, pid: int, op: str, args: dict) -> dict:
    linea = json.dumps({"id": pid, "op": op, "args": args}, ensure_ascii=False, separators=(",", ":")) + "\n"
    writer.write(linea.encode())
    await writer.drain()
    while True:
        raw = await reader.readline()
        if not raw:
            raise ConnectionError("guardián cerró la conexión")
        msg = leer_mensaje(raw)
        if msg.get("id") == pid:
            return msg


async def _tablero_remoto(ruta: Path) -> dict:
    reader, writer = await asyncio.open_unix_connection(str(ruta))
    try:
        h = await _pedir(reader, writer, 1, "hola", {})
        if not h.get("ok"):
            raise RuntimeError("no pude saludar al guardián")
        res = h.get("res") or {}
        if res.get("protocolo") != VERSION:
            raise RuntimeError("versión del guardián incompatible")
        t = await _pedir(reader, writer, 2, "tablero", {})
        if not t.get("ok"):
            err = t.get("error") or {}
            raise RuntimeError(err.get("mensaje") if isinstance(err, dict) else "tablero falló")
        return t.get("res") if isinstance(t.get("res"), dict) else {}
    finally:
        writer.close()
        await writer.wait_closed()


async def _enganchar(ruta: Path, sesion_id: str, *, stdin=None) -> int:
    reader, writer = await asyncio.open_unix_connection(str(ruta))
    eventos: asyncio.Queue[dict | None] = asyncio.Queue()
    pendientes: dict[int, asyncio.Future] = {}
    pid = 0
    linea_entrada = "Ctrl+] para salir"
    entrada_lista = asyncio.Event()
    loop = asyncio.get_running_loop()

    async def pedir(op: str, args: dict) -> dict:
        nonlocal pid
        pid += 1
        req_id = pid
        fut = loop.create_future()
        pendientes[req_id] = fut
        linea = json.dumps({"id": req_id, "op": op, "args": args}, ensure_ascii=False, separators=(",", ":")) + "\n"
        writer.write(linea.encode())
        await writer.drain()
        return await fut

    def _fallar_pendientes() -> None:
        for fut in pendientes.values():
            if not fut.done():
                fut.set_exception(ConnectionError("guardián cerró la conexión"))
        pendientes.clear()

    async def lector_unico() -> None:
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                try:
                    msg = leer_mensaje(raw)
                except Exception:
                    continue
                req_id = msg.get("id")
                if req_id is not None:
                    fut = pendientes.pop(req_id, None)
                    if fut is not None and not fut.done():
                        fut.set_result(msg)
                    continue
                if msg.get("evento") == "salida" and msg.get("sesion") == sesion_id:
                    await eventos.put({"tipo": "salida", "texto": str(msg.get("texto") or "")})
        finally:
            _fallar_pendientes()
            entrada_lista.set()
            await eventos.put(None)

    async def preparar_sesion() -> None:
        nonlocal linea_entrada
        try:
            h = await pedir("hola", {})
            if not h.get("ok"):
                await eventos.put({"tipo": "error", "texto": "guardián no respondió"})
                return
            sub = await pedir(
                "suscribir",
                {"salida": [sesion_id], "foto": True},
            )
            if not sub.get("ok"):
                await eventos.put({"tipo": "error", "texto": "no pude suscribirme a la salida"})
                return
            res = sub.get("res") if isinstance(sub.get("res"), dict) else {}
            fotos = res.get("fotos") if isinstance(res.get("fotos"), dict) else {}
            foto = fotos.get(sesion_id) if isinstance(fotos, dict) else None
            linea_entrada = _linea_entrada(foto if isinstance(foto, dict) else None)
            entrada_lista.set()
            if isinstance(foto, dict):
                pant = foto.get("pantalla")
                if isinstance(pant, list):
                    await eventos.put({"tipo": "salida", "texto": "\n".join(str(x) for x in pant)})
        except ConnectionError:
            await eventos.put({"tipo": "error", "texto": "guardián cerró la conexión"})
        finally:
            entrada_lista.set()

    salir = asyncio.Event()
    entrada = stdin if stdin is not None else sys.stdin
    fd = entrada.fileno() if hasattr(entrada, "fileno") else sys.stdin.fileno()
    cola_envio: asyncio.Queue[str | None] = asyncio.Queue()
    decoder = codecs.getincrementaldecoder("utf-8")()

    async def emisor() -> None:
        try:
            while True:
                texto = await cola_envio.get()
                if texto is None:
                    break
                await pedir("escribir", {"sesion_id": sesion_id, "texto": texto})
        except asyncio.CancelledError:
            raise
        except ConnectionError:
            pass

    def _stdin_ready() -> None:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            salir.set()
            return
        if not chunk:
            salir.set()
            return
        partes = chunk.split(_ESCAPE_BYTES)
        for i, raw in enumerate(partes):
            if i < len(partes) - 1:
                if raw:
                    t = decoder.decode(raw)
                    if t:
                        cola_envio.put_nowait(t)
                salir.set()
                return
            if raw:
                t = decoder.decode(raw)
                if t:
                    cola_envio.put_nowait(t)

    tarea_red = asyncio.create_task(lector_unico())
    tarea_prep = asyncio.create_task(preparar_sesion())
    tarea_emisor = asyncio.create_task(emisor())
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        loop.add_reader(fd, _stdin_ready)
        listo_task = asyncio.create_task(entrada_lista.wait())
        salir_task = asyncio.create_task(salir.wait())
        await asyncio.wait({listo_task, salir_task}, return_when=asyncio.FIRST_COMPLETED)
        for t in (listo_task, salir_task):
            if not t.done():
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t
        print(linea_entrada, flush=True)

        while not salir.is_set():
            get_task = asyncio.create_task(eventos.get())
            salir_task = asyncio.create_task(salir.wait())
            done, pending = await asyncio.wait({get_task, salir_task}, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            if salir.is_set():
                break
            if get_task not in done:
                continue
            ev = get_task.result()
            if ev is None:
                break
            if ev.get("tipo") == "salida":
                sys.stdout.write(ev.get("texto") or "")
                sys.stdout.flush()
            elif ev.get("tipo") == "error":
                sys.stdout.write(f"\n{ev.get('texto')}\n")
                sys.stdout.flush()
                return 1
    finally:
        loop.remove_reader(fd)
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        cola_envio.put_nowait(None)
        with contextlib.suppress(asyncio.CancelledError):
            await tarea_emisor
        tarea_prep.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarea_prep
        tarea_red.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarea_red
        writer.close()
        await writer.wait_closed()
    return 0


def ver_terminal(sel: str | None) -> int:
    ruta = ruta_guardian_socket()
    if ruta is None or not ruta.is_socket():
        print("No encuentro el socket del guardián (¿está corriendo?).", file=sys.stderr)
        return 1
    try:
        tab = asyncio.run(_tablero_remoto(ruta))
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    filas = filas_de_tablero(tab)
    if not sel:
        imprimir_listado(filas)
        return 0
    idx = buscar_indice(filas, sel)
    if idx is None:
        print(f"No hay terminal «{sel}».", file=sys.stderr)
        imprimir_listado(filas)
        return 1
    sid = filas[idx]["sesion_id"]
    return asyncio.run(_enganchar(ruta, sid))
