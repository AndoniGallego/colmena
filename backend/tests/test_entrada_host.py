import pytest
from asgi_support import correr
from orquestador import entrada
from orquestador.config import Config

CFG = Config(app_origin="https://app.example:8444", viewer_origin="https://visor.example:8445")


def host(h, rol="app", tipo="http"):
    a = entrada.ajustes("tailscale", CFG)
    hosts = a.hosts_app if rol == "app" else a.hosts_visor
    headers = [("host", x) for x in (h if isinstance(h, list) else [h])]
    return correr(lambda app: entrada.HostPermitidoMiddleware(app, hosts), tipo=tipo, headers=headers)


def test_host_ajeno_400():
    r = host("evil.example")
    assert (r.status, r.llamada) == (400, False)


def test_con_puerto_y_mayusculas_pasa():
    assert host("APP.Example:8444").llamada


def test_visor_solo_su_host():
    assert host("visor.example:8445", rol="visor").llamada
    assert host("app.example:8444", rol="visor").status == 400


def test_websocket_host_ajeno_se_rechaza():
    r = host("evil.example", tipo="websocket")
    assert (r.cierre, r.llamada) == (1008, False)


def test_host_ipv6_y_vite_pasan():
    assert host("[::1]:8770").llamada and host("127.0.0.1:5173").llamada and host("localhost").llamada


def test_host_ausente_o_duplicado_400():
    assert host([]).status == 400
    assert host(["app.example", "evil.example"]).status == 400


def test_solo_local_no_acepta_el_de_tailscale():
    cfg = Config(**{"app_origin": "https://app.example:8444"}, entrada={"modos": ["tailscale", "solo-local"]})
    hosts = entrada.ajustes("solo-local", cfg).hosts_app
    r = correr(lambda app: entrada.HostPermitidoMiddleware(app, hosts), headers=[("host", "app.example")])
    assert r.status == 400


@pytest.mark.parametrize(
    "valor",
    ["[::1", "", "app.example:8444/x", "user@app.example", "app.example\\x", "::1", "::1:80",
     "app.example:8444:1", " app.example", "app.example\x00", "app.example:abc", "app.example:123456",
     "app.ex ample", "[]:80", ":8444"],
)
def test_host_malformado_400(valor):
    r = host(valor)
    assert r.status == 400 and not r.llamada
