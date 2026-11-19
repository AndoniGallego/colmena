import pytest
from fastapi.testclient import TestClient
from asgi_support import correr
from biblioteca_support import SECRET, Env
from conftest import ORIGIN, PIN, SID
from orquestador import auth
from orquestador.biblioteca_viewer import create_viewer_app

YO = "yo@example.com"


def ts(headers, tipo="http"):
    return correr(lambda a: auth.TailscaleUserMiddleware(a, YO), tipo=tipo, headers=headers)


def test_sin_header_403():
    r = ts([])
    assert (r.status, r.llamada) == (403, False)


def test_distinto_403():
    assert ts([("tailscale-user-login", "otro@example.com")]).status == 403


def test_correcto_pasa():
    assert ts([("tailscale-user-login", YO)]).llamada


def test_duplicado_distinto_403():
    assert ts([("tailscale-user-login", YO), ("tailscale-user-login", "otro@example.com")]).status == 403


def test_websocket_sin_header_cierra_sin_llamar():
    r = ts([], tipo="websocket")
    assert (r.cierre, r.llamada) == (1008, False)


def test_sin_usuario_configurado_pasa():
    assert correr(lambda a: auth.TailscaleUserMiddleware(a, ""), headers=[]).llamada


def test_visor_tambien_exige_header(tmp_path):
    env = Env(tmp_path, tailscale_user=YO)
    c = TestClient(create_viewer_app(env.lib, SECRET, lambda: 0, env.cfg), base_url="https://h.example:8445",
                   client=("127.0.0.1", 1))
    assert c.get("/v/x/1/y/").status_code == 403
    assert c.get("/v/x/1/y/", headers={"Tailscale-User-Login": YO}).status_code == 404


@pytest.mark.parametrize("valor", [" " + YO, YO + " ", YO.upper()])
def test_comparacion_exacta(valor):
    assert ts([("tailscale-user-login", valor)]).status == 403


def laxo(headers):
    return correr(lambda a: auth.TailscaleUserMiddleware(a, YO, estricto=False), headers=headers)


def test_laxo_sin_header_pasa():
    assert laxo([]).llamada


@pytest.mark.parametrize("headers", [[("tailscale-user-login", "otro@example.com")],
                                     [("tailscale-user-login", YO), ("tailscale-user-login", "otro@example.com")]])
def test_laxo_rechaza_valor_distinto(headers):
    r = laxo(headers)
    assert (r.status, r.llamada) == (403, False)


XFF = "x-forwarded-for"


def ip_vista(headers, cabecera=XFF, client=("127.0.0.1", 9)):
    r = correr(lambda a: auth.IpRealMiddleware(a, cabecera), headers=headers, client=client)
    return r.scope["client"][0]


def ip_real_loopback(headers, *, tipo="http", client=("127.0.0.1", 9)):
    return correr(lambda a: auth.IpRealMiddleware(a, XFF), headers=headers, client=client, tipo=tipo)


def test_sin_cabecera_configurada_xff_no_cambia():
    assert ip_vista([(XFF, "1.2.3.4")], cabecera="") == "127.0.0.1"


def test_toma_la_de_mas_a_la_derecha():
    assert ip_vista([(XFF, "9.9.9.9, 100.64.0.7")]) == "100.64.0.7"
    assert ip_vista([(XFF, "9.9.9.9"), (XFF, "100.64.0.8")]) == "100.64.0.8"


def test_solo_si_viene_de_127():
    assert ip_vista([(XFF, "100.64.0.7")], client=("100.64.0.5", 9)) == "100.64.0.5"


@pytest.mark.parametrize("valor", ["basura", "1.2.3.4, basura", "", "100.64.0.7:443"])
def test_valor_invalido_403(valor):
    r = ip_real_loopback([(XFF, valor)])
    assert (r.status, r.llamada) == (403, False)


def test_ip_real_sin_header_403():
    r = ip_real_loopback([])
    assert (r.status, r.llamada) == (403, False)


def test_ip_real_ultimo_vacio_403():
    r = ip_real_loopback([(XFF, "1.2.3.4, ")])
    assert (r.status, r.llamada) == (403, False)


def test_ip_real_scope_id_403():
    r = ip_real_loopback([(XFF, "fe80::1%eth0")])
    assert (r.status, r.llamada) == (403, False)


def test_ip_real_websocket_sin_ip_usable_cierra():
    r = ip_real_loopback([], tipo="websocket")
    assert (r.cierre, r.llamada) == (1008, False)


def test_ip_real_fuera_de_cidr_403():
    nets = auth.parse_networks(["127.0.0.0/8", "100.64.0.0/10"])
    r = correr(lambda a: auth.IpRealMiddleware(auth.CidrMiddleware(a, nets), XFF), headers=[(XFF, "8.8.8.8")])
    assert (r.status, r.llamada) == (403, False)


@pytest.fixture
def cfg(cfg):
    cfg.terminales_escritura = True
    return cfg


@pytest.fixture
def real(app):
    with TestClient(auth.IpRealMiddleware(app, XFF), base_url="https://testserver", headers=ORIGIN,
                    client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}, headers={XFF: "100.64.0.1"}).status_code == 200
        yield c


MALO = "00000000"
CAMINOS = {
    "login": lambda c, i, h: c.post("/api/login", json={"pin": MALO}, headers=h),
    "dialogo": lambda c, i, h: c.post("/api/sessions/dialog/answer", headers=h, json={
        "id": f"bad-pin-{i:03d}", "session_id": SID, "pane_id": "w1:p1", "huella": "x",
        "tipo": "permiso", "permiso": "si_siempre", "pin": MALO}),
    "terminal": lambda c, i, h: c.post("/api/terminales/ventana", json={"pin": MALO}, headers=h),
    "mr": lambda c, i, h: c.post("/api/mrs/7/1/cerrar", json={"pin": MALO}, headers=h),
}


@pytest.mark.parametrize("camino", CAMINOS)
def test_rotar_xff_no_esquiva_el_bloqueo(real, camino):
    pedir = CAMINOS[camino]
    codes = [pedir(real, i, {XFF: f"9.9.9.{i}, 100.64.0.7"}).status_code for i in range(6)]
    assert 429 not in codes[:5] and codes[5] == 429
    assert pedir(real, 99, {XFF: "100.64.0.8"}).status_code != 429


@pytest.mark.parametrize("camino", ["login", "dialogo", "mr"])
def test_tope_global_cuenta_entre_ips(real, camino):
    pedir = CAMINOS[camino]
    for i in range(21):
        assert pedir(real, i, {XFF: f"100.64.1.{i}"}).status_code != 429
    assert pedir(real, 50, {XFF: "100.64.2.1"}).status_code == 429


def test_ip_real_conserva_puerto_y_canoniza():
    r = correr(lambda a: auth.IpRealMiddleware(a, XFF), headers=[(XFF, "::ffff:100.64.0.7")], client=("127.0.0.1", 9))
    assert r.scope["client"] == ("100.64.0.7", 9)


def test_ip_real_en_websocket():
    r = correr(lambda a: auth.IpRealMiddleware(a, XFF), tipo="websocket", headers=[(XFF, "100.64.0.7")])
    assert r.scope["client"][0] == "100.64.0.7"
