from orquestador.guardian.pantalla import Pantalla


def test_historial_acotado():
    p = Pantalla(columnas=10, filas=3, historial=5)
    for i in range(20):
        p.alimentar(f"L{i:02d}\n".encode())
    assert len(p._screen._historial_texto) == 5
    rec = p.reciente()
    assert "L00" not in rec and "L19" in rec


def test_union_lineas_cortadas():
    p = Pantalla(columnas=8, filas=4, historial=50)
    p.alimentar(b"12345678continuacion\n")
    assert "12345678continuacion" in p.reciente()


def test_titulo_osc():
    p = Pantalla()
    p.alimentar(b"\x1b]0;Mi titulo\x07")
    assert p.titulo == "Mi titulo"


def test_ansi_negrita_color():
    p = Pantalla(columnas=20, filas=3)
    p.alimentar(b"\x1b[1;31mrojo\x1b[0m\n")
    out = p.ansi()
    assert "\x1b[1;" in out and "31" in out and "rojo" in out


def test_tiene_prompt():
    p = Pantalla(columnas=40, filas=5)
    p.alimentar("  ❯ hola\n".encode())
    assert p.tiene_prompt()


def test_dialogo_confianza():
    p = Pantalla(columnas=60, filas=10)
    texto = "Do you trust this folder?\n  1. Yes\n  2. No, exit\n"
    p.alimentar(texto.encode())
    assert p.dialogo_confianza()


def test_utf8_partido():
    p = Pantalla(columnas=20, filas=3)
    raw = "añ".encode()
    p.alimentar(raw[:1])
    p.alimentar(raw[1:] + b"\n")
    assert "añ" in p.reciente()


def test_contiene_entrada():
    p = Pantalla(columnas=40, filas=5)
    p.alimentar(b"  \xe2\x9d\xaf escribir esto aca\n")
    assert p.contiene_entrada("escribir esto aca")
    assert not p.contiene_entrada("")


def test_ansi_filas_mantiene_filas_vacias_al_final():
    p = Pantalla(columnas=20, filas=5)
    p.alimentar(b"hola\n")
    filas = p.ansi_filas()
    assert len(filas) == p.filas
    assert filas[0] == "hola"
    assert p.ansi() == "hola"


def test_foto_cursor_y_dimensiones():
    p = Pantalla(columnas=40, filas=10)
    p.alimentar(b"hola\r\nmundo")
    f = p.foto()
    assert f["columnas"] == 40
    assert f["filas"] == 10
    assert f["cursor"] == [5, 1]
    assert f["cursor_visible"] is True
    assert len(f["pantalla"]) == 10
    assert "hola" in f["pantalla"][0]
    assert "mundo" in f["pantalla"][1]


def test_foto_cursor_oculto():
    p = Pantalla(columnas=20, filas=3)
    p.alimentar(b"\x1b[?25l")
    assert p.foto()["cursor_visible"] is False


def test_foto_historial_max_historial():
    p = Pantalla(columnas=10, filas=3, historial=100)
    for i in range(30):
        p.alimentar(f"L{i:02d}\n".encode())
    full = list(p._screen._historial_texto)
    f = p.foto(max_historial=5)
    assert len(f["historial"]) == 5
    assert f["historial"] == full[-5:]


def test_foto_historial_max_bytes():
    p = Pantalla(columnas=10, filas=3, historial=50)
    for i in range(20):
        p.alimentar(f"{'x' * 8}\n".encode())
    costo_pantalla = sum(len(s) for s in p.ansi_filas())
    f = p.foto(max_historial=50, max_bytes=costo_pantalla + 25)
    assert sum(len(s) for s in f["historial"]) <= 25
    assert len(f["historial"]) >= 1


def test_foto_historial_vacio_si_pantalla_supera_max_bytes():
    p = Pantalla(columnas=20, filas=5, historial=20)
    p.alimentar(b"x\n")
    for i in range(10):
        p.alimentar(f"h{i}\n".encode())
    f = p.foto(max_bytes=1)
    assert f["historial"] == []


def test_foto_tope_en_bytes_utf8():
    p = Pantalla(columnas=10, filas=2, historial=50)
    for _ in range(20):
        p.alimentar("─────\n".encode())
    costo = sum(len(s.encode()) for s in p.ansi_filas())
    f = p.foto(max_bytes=costo + 40)
    assert sum(len(s.encode()) for s in f["historial"]) <= 40
    assert f["historial"]
