from __future__ import annotations

import codecs
from collections import deque

import pyte
from pyte.screens import Char, Margins

_BORDE_CAJA = frozenset("│╭╰─")

_FG_STD = {
    "black": 30,
    "red": 31,
    "green": 32,
    "brown": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
}
_FG_BRIGHT = {
    "brightblack": 90,
    "brightred": 91,
    "brightgreen": 92,
    "brightbrown": 93,
    "brightblue": 94,
    "brightmagenta": 95,
    "brightcyan": 96,
    "brightwhite": 97,
}
_BG_STD = {k: v + 10 for k, v in _FG_STD.items()}
_BG_BRIGHT = {k: v + 10 for k, v in _FG_BRIGHT.items()}


class _HistorialScreen(pyte.Screen):
    def __init__(self, columnas: int, filas: int, historial: int) -> None:
        super().__init__(columnas, filas)
        self._historial_texto: deque[str] = deque(maxlen=historial)
        self._historial_llena: deque[bool] = deque(maxlen=historial)

    def index(self) -> None:
        top, bottom = self.margins or Margins(0, self.lines - 1)
        if self.cursor.y == bottom:
            texto, llena = _linea_texto(self, top)
            self._historial_texto.append(texto)
            self._historial_llena.append(llena)
        super().index()


def _linea_texto(pantalla: pyte.Screen, y: int) -> tuple[str, bool]:
    chars = []
    for x in range(pantalla.columns):
        chars.append(pantalla.buffer[y][x].data)
    raw = "".join(chars)
    texto = raw.rstrip()
    llena = len(raw) == pantalla.columns and (not raw or raw[-1] != " ")
    return texto, llena


def _unwrap(lineas: list[str], llenas: list[bool]) -> list[str]:
    if not lineas:
        return []
    out: list[str] = []
    i = 0
    while i < len(lineas):
        partes = [lineas[i]]
        j = i
        while j < len(llenas) and llenas[j] and j + 1 < len(lineas):
            j += 1
            partes.append(lineas[j])
        out.append("".join(partes))
        i = j + 1
    return out


def _sin_blancos_final(lineas: list[str]) -> list[str]:
    fin = len(lineas)
    while fin > 0 and not lineas[fin - 1].strip():
        fin -= 1
    return lineas[:fin]


def _estado_celda(c: Char) -> tuple:
    return (c.bold, c.italics, c.underscore, c.reverse, c.fg, c.bg)


def _sgr_de_celda(c: Char) -> list[int]:
    partes: list[int] = []
    if c.bold:
        partes.append(1)
    if c.italics:
        partes.append(3)
    if c.underscore:
        partes.append(4)
    if c.reverse:
        partes.append(7)
    fg = c.fg
    if fg and fg != "default":
        if fg in _FG_STD:
            partes.append(_FG_STD[fg])
        elif fg in _FG_BRIGHT:
            partes.append(_FG_BRIGHT[fg])
        elif len(fg) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in fg):
            r = int(fg[0:2], 16)
            g = int(fg[2:4], 16)
            b = int(fg[4:6], 16)
            partes.extend([38, 2, r, g, b])
    bg = c.bg
    if bg and bg != "default":
        if bg in _BG_STD:
            partes.append(_BG_STD[bg])
        elif bg in _BG_BRIGHT:
            partes.append(_BG_BRIGHT[bg])
        elif len(bg) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in bg):
            r = int(bg[0:2], 16)
            g = int(bg[2:4], 16)
            b = int(bg[4:6], 16)
            partes.extend([48, 2, r, g, b])
    return partes


def _serializar_sgr(partes: list[int]) -> str:
    if not partes:
        return ""
    return "\x1b[" + ";".join(str(p) for p in partes) + "m"


class Pantalla:
    def __init__(self, columnas: int = 120, filas: int = 40, historial: int = 5000) -> None:
        self._screen = _HistorialScreen(columnas, filas, historial)
        self._stream = pyte.Stream(self._screen)
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def alimentar(self, datos: bytes) -> None:
        texto = self._decoder.decode(datos)
        if texto:
            self._stream.feed(texto)

    def redimensionar(self, columnas: int, filas: int) -> None:
        self._screen.resize(filas, columnas)

    @property
    def columnas(self) -> int:
        return self._screen.columns

    @property
    def filas(self) -> int:
        return self._screen.lines

    @property
    def titulo(self) -> str:
        return self._screen.title or ""

    def visible(self) -> list[str]:
        return [_linea_texto(self._screen, y)[0] for y in range(self._screen.lines)]

    def reciente(self, lineas: int | None = None) -> str:
        hist = list(self._screen._historial_texto)
        llenas = list(self._screen._historial_llena)
        vis: list[str] = []
        vis_llenas: list[bool] = []
        for y in range(self._screen.lines):
            texto, llena = _linea_texto(self._screen, y)
            vis.append(texto)
            vis_llenas.append(llena)
        todas = _unwrap(hist + vis, llenas + vis_llenas)
        todas = _sin_blancos_final(todas)
        if lineas is not None:
            todas = todas[-lineas:]
        return "\n".join(todas)

    def deteccion(self) -> str:
        return "\n".join(_sin_blancos_final(self.visible()))

    def ansi_filas(self) -> list[str]:
        filas_out: list[str] = []
        for y in range(self._screen.lines):
            prev: tuple | None = None
            chunks: list[str] = []
            tuvo_attr = False
            for x in range(self._screen.columns):
                c = self._screen.buffer[y][x]
                estado = _estado_celda(c)
                if estado != prev:
                    sgr = _serializar_sgr(_sgr_de_celda(c))
                    if sgr:
                        chunks.append(sgr)
                        tuvo_attr = True
                    elif prev is not None and any(prev):
                        chunks.append("\x1b[0m")
                    prev = estado
                chunks.append(c.data)
            linea = "".join(chunks)
            if tuvo_attr:
                linea += "\x1b[0m"
            filas_out.append(linea.rstrip())
        return filas_out

    def ansi(self) -> str:
        filas_out = list(self.ansi_filas())
        while filas_out and not filas_out[-1]:
            filas_out.pop()
        return "\n".join(filas_out)

    def foto(self, max_historial: int = 1000, max_bytes: int = 250_000) -> dict:
        # Tope en bytes UTF-8: la respuesta tiene que entrar en una línea del protocolo (MAX_LINEA).
        pantalla = self.ansi_filas()
        restante = max_bytes - sum(len(s.encode("utf-8")) for s in pantalla)
        historial: list[str] = []
        for linea in reversed(list(self._screen._historial_texto)[-max_historial:]):
            restante -= len(linea.encode("utf-8"))
            if restante < 0:
                break
            historial.append(linea)
        historial.reverse()
        return {
            "columnas": self.columnas,
            "filas": self.filas,
            "cursor": [self._screen.cursor.x, self._screen.cursor.y],
            "cursor_visible": not self._screen.cursor.hidden,
            "historial": historial,
            "pantalla": pantalla,
        }

    def tiene_prompt(self) -> bool:
        for linea in self.visible():
            limpia = linea.lstrip()
            while limpia and limpia[0] in _BORDE_CAJA:
                limpia = limpia[1:].lstrip()
            if limpia.startswith("❯"):
                return True
        return False

    def dialogo_confianza(self) -> bool:
        texto = self.deteccion().lower()
        return "trust" in texto and "no, exit" in texto

    def contiene_entrada(self, texto: str) -> bool:
        buscar = texto.strip().split("\n", 1)[0][:40]
        if not buscar:
            return False
        for linea in self.visible():
            if "❯" in linea and buscar in linea:
                return True
        return False
