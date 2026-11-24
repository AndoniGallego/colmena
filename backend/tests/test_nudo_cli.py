import json
import socket
import sys
import threading

import pytest

from orquestador import nudo_cli
from orquestador.nudo_cli import main_nudo, parsear_marca, timeout_para

pytestmark = pytest.mark.unix


class Falso:
    def __init__(self, tmp_path, respuesta):
        self.env = {"XDG_RUNTIME_DIR": str(tmp_path), "COLMENA_SESION": "w1:p1"}
        d = tmp_path / "colmena"
        d.mkdir()
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(str(d / "nudo.sock"))
        self.srv.listen(4)
        self.pedido = None
        self.conexiones = 0
        self.respuesta = respuesta
        self.hilo = threading.Thread(target=self._servir, daemon=True)
        self.hilo.start()

    def _servir(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            self.conexiones += 1
            buf = b""
            while b"\n" not in buf:
                trozo = c.recv(4096)
                if not trozo:
                    break
                buf += trozo
            self.pedido = json.loads(buf.split(b"\n")[0])
            c.sendall(json.dumps(self.respuesta).encode() + b"\n")
            c.close()

    def cerrar(self):
        self.srv.close()


@pytest.fixture
def falso(tmp_path):
    creados = []

    def crear(respuesta):
        f = Falso(tmp_path, respuesta)
        creados.append(f)
        return f

    yield crear
    for f in creados:
        f.cerrar()


def test_controles_imprime_json(falso, capsys):
    datos = {"ventana": "Notepad", "monitor": 1, "controles": [{"n": 1, "nombre": "ñ"}]}
    f = falso({"ok": True, "datos": datos})
    rc = main_nudo(["controles"], f.env)
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == datos
    assert f.pedido == {"op": "controles", "sesion": "w1:p1", "args": {}}


def test_senalar_con_esperar_imprime_resultado(falso, capsys):
    f = falso({"ok": True, "datos": {"resultado": "listo"}})
    rc = main_nudo(["senalar", "12", "Tocá Guardar", "--esperar"], f.env)
    assert rc == 0
    assert f.pedido == {"op": "senalar", "sesion": "w1:p1", "args": {"n": 12, "texto": "Tocá Guardar", "esperar": 120}}
    assert capsys.readouterr().out == "listo\n"


def test_esperar_con_segundos(falso):
    f = falso({"ok": True, "datos": {"resultado": "ok"}})
    main_nudo(["senalar", "3", "x", "--esperar", "30"], f.env)
    assert f.pedido["args"]["esperar"] == 30


def test_esperar_cero_se_manda_al_backend(falso):
    f = falso({"ok": True, "datos": {"resultado": "ok"}})
    main_nudo(["senalar", "3", "x", "--esperar", "0"], f.env)
    assert f.pedido["args"]["esperar"] == 0


def test_mensaje_de_en_curso_no_invita_a_reintentar():
    from orquestador.nudo_cli import MENSAJES
    assert "probá" not in MENSAJES["en_curso"]


def test_senalar_sin_esperar_no_manda_esperar(falso):
    f = falso({"ok": True, "datos": {"resultado": "ok"}})
    main_nudo(["senalar", "3", "x"], f.env)
    assert f.pedido["args"] == {"n": 3, "texto": "x"}


def test_marcar_parsea_pares(falso, capsys):
    f = falso({"ok": True, "datos": {"resultado": "ok"}})
    assert main_nudo(["marcar", "3:Nombre", "5:Precio"], f.env) == 0
    assert f.pedido["args"] == {"marcas": [{"n": 3, "etiqueta": "Nombre"}, {"n": 5, "etiqueta": "Precio"}]}
    assert capsys.readouterr().out == "ok\n"


def test_limpiar_ajeno_dice_que_no_habia_nada(falso, capsys):
    f = falso({"ok": True, "datos": {"resultado": "ok", "nada": True}})
    assert main_nudo(["limpiar"], f.env) == 0
    assert capsys.readouterr().out == "no había nada tuyo\n"


def test_estado_imprime_json(falso, capsys):
    datos = {"prendido": True, "se_ve_al_compartir": False}
    f = falso({"ok": True, "datos": datos})
    assert main_nudo(["estado"], f.env) == 0
    assert json.loads(capsys.readouterr().out) == datos


def test_marcar_mas_de_8_falla_sin_conectar(falso):
    f = falso({"ok": True, "datos": {}})
    marcas = [f"{i}:a" for i in range(1, 10)]
    assert main_nudo(["marcar", *marcas], f.env) == 2
    assert f.conexiones == 0


def test_marca_sin_dos_puntos_falla(falso):
    f = falso({"ok": True, "datos": {}})
    assert main_nudo(["marcar", "3"], f.env) == 2
    assert f.conexiones == 0


def test_error_imprime_mensaje_y_codigo(falso, capsys):
    f = falso({"ok": False, "error": "apagado", "mensaje": "x"})
    assert main_nudo(["estado"], f.env) == 3
    cap = capsys.readouterr()
    assert cap.err.strip() == nudo_cli.MENSAJES["apagado"]
    assert cap.out == ""


@pytest.mark.parametrize("codigo", sorted(set(nudo_cli.CODIGOS_SALIDA) - {"offline", "invalido"}))
def test_cada_codigo_tiene_su_salida_y_mensaje(falso, capsys, codigo):
    f = falso({"ok": False, "error": codigo, "mensaje": "del backend"})
    assert main_nudo(["estado"], f.env) == nudo_cli.CODIGOS_SALIDA[codigo]
    cap = capsys.readouterr()
    esperado = "del backend" if codigo == "ocupado" else nudo_cli.MENSAJES[codigo]
    assert cap.err.strip() == esperado
    assert cap.out == ""


def test_ocupado_usa_el_mensaje_del_backend(falso, capsys):
    f = falso({"ok": False, "error": "ocupado", "mensaje": "Ocupado por Ana."})
    assert main_nudo(["estado"], f.env) == 9
    assert capsys.readouterr().err.strip() == "Ocupado por Ana."


def test_invalido_usa_el_mensaje_del_backend(falso, capsys):
    f = falso({"ok": False, "error": "invalido", "mensaje": "n fuera de rango"})
    assert main_nudo(["estado"], f.env) == 2
    assert capsys.readouterr().err.strip() == "n fuera de rango"


def test_sin_colmena_sesion_falla(tmp_path, capsys):
    assert main_nudo(["estado"], {"XDG_RUNTIME_DIR": str(tmp_path)}) == 2
    assert "solo desde una sesión de Colmena" in capsys.readouterr().err


def test_sin_socket_dice_que_colmena_no_anda(tmp_path, capsys):
    env = {"XDG_RUNTIME_DIR": str(tmp_path), "COLMENA_SESION": "w1:p1"}
    assert main_nudo(["estado"], env) == 1
    assert "Colmena no está andando" in capsys.readouterr().err


def test_timeout_del_cliente_es_vencido(tmp_path, capsys, monkeypatch):
    d = tmp_path / "colmena"
    d.mkdir()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(d / "nudo.sock"))
    srv.listen(1)
    monkeypatch.setattr(nudo_cli, "timeout_para", lambda op, args: 0.2)
    try:
        env = {"XDG_RUNTIME_DIR": str(tmp_path), "COLMENA_SESION": "w1:p1"}
        assert main_nudo(["estado"], env) == 10
        assert "no respondió a tiempo" in capsys.readouterr().err
    finally:
        srv.close()


def test_timeout_contempla_la_espera():
    assert timeout_para("senalar", {"esperar": 120}) == 140.0
    assert timeout_para("controles", {}) == 20.0
    assert timeout_para("estado", {}) == 15.0


def test_parsear_marca():
    assert parsear_marca("12:Guardar") == {"n": 12, "etiqueta": "Guardar"}
    assert parsear_marca("1:a:b") == {"n": 1, "etiqueta": "a:b"}
    for malo in ("12", "x:Guardar", "3:"):
        with pytest.raises(ValueError):
            parsear_marca(malo)


def test_cli_main_despacha_nudo(monkeypatch):
    from orquestador import cli

    visto = {}

    def falso_main(argv):
        visto["argv"] = argv
        return 0

    monkeypatch.setattr(nudo_cli, "main_nudo", falso_main)
    monkeypatch.setattr(sys, "argv", ["orquestador", "nudo", "estado"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0
    assert visto["argv"] == ["estado"]


def test_timeout_con_esperar_cero_cubre_la_espera_por_defecto():
    assert timeout_para("senalar", {"esperar": 0}) == 140.0


def test_respuesta_que_no_es_un_objeto_es_offline(falso, capsys):
    f = falso([1, 2])
    assert main_nudo(["estado"], f.env) == 1
    assert "Colmena no está andando" in capsys.readouterr().err


def test_error_con_codigo_desconocido_sale_con_2(falso, capsys):
    f = falso({"ok": False, "error": "raro", "mensaje": "x"})
    assert main_nudo(["estado"], f.env) == 2
    assert capsys.readouterr().out == ""


def test_argumentos_invalidos_salen_con_2_sin_conectar(falso):
    f = falso({"ok": True, "datos": {}})
    for argv in (["senalar", "abc", "x"], ["senalar", "3", "x", "--esperar", "mucho"], ["borrar"], []):
        assert main_nudo(argv, f.env) == 2
    assert f.conexiones == 0


def test_marca_sin_etiqueta_explica_el_formato(falso, capsys):
    f = falso({"ok": True, "datos": {}})
    assert main_nudo(["marcar", "3:"], f.env) == 2
    assert "número:etiqueta" in capsys.readouterr().err


def test_senalar_zona_arma_pedido(falso, capsys):
    f = falso({"ok": True, "datos": {"resultado": "ok"}})
    assert main_nudo(["senalar-zona", "10", "20", "200", "40", "Acá"], f.env) == 0
    assert f.pedido == {"op": "senalar_zona", "sesion": "w1:p1",
                        "args": {"zona": {"x": 10, "y": 20, "ancho": 200, "alto": 40}, "texto": "Acá"}}
    assert capsys.readouterr().out == "ok\n"


def test_marcar_zonas_parsea_tokens(falso, capsys):
    f = falso({"ok": True, "datos": {"resultado": "ok"}})
    assert main_nudo(["marcar-zonas", "10,20,200,40:Menú", "1,2,3,4:Otro: más"], f.env) == 0
    assert f.pedido["op"] == "marcar_zonas"
    assert f.pedido["args"] == {"zonas": [
        {"x": 10, "y": 20, "ancho": 200, "alto": 40, "etiqueta": "Menú"},
        {"x": 1, "y": 2, "ancho": 3, "alto": 4, "etiqueta": "Otro: más"}]}


def test_parsear_zona_invalida():
    from orquestador.nudo_cli import parsear_zona
    assert parsear_zona("10,20,200,40:Menú") == {"x": 10, "y": 20, "ancho": 200, "alto": 40, "etiqueta": "Menú"}
    for malo in ("10,20,200:Menú", "a,b,c,d:x", "1,2,3,4", "1,2,3,4:  "):
        with pytest.raises(ValueError, match="10,20,200,40:Menú"):
            parsear_zona(malo)


def test_foto_vieja_en_zona_pide_mostrame(falso, capsys):
    f = falso({"ok": False, "error": "foto_vieja", "mensaje": "x"})
    assert main_nudo(["senalar-zona", "1", "2", "3", "4", "a"], f.env) == 5
    assert capsys.readouterr().err.strip() == (
        'Foto vieja: la ventana cambió o pasaron 5 minutos. Pedile a Ando que vuelva a tocar "Mostrame".')


def test_foto_vieja_por_numero_menciona_mostrame():
    from orquestador import nudo_cli
    assert "Mostrame" in nudo_cli.MENSAJES["foto_vieja"]
