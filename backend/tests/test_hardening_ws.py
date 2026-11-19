import pytest
from asgi_support import correr
from orquestador.hardening import HardeningMiddleware

APP = "https://app.example:8444"


def ws(headers, path="/vivo/g1", origen=APP):
    return correr(lambda a: HardeningMiddleware(a, app_origin=origen), tipo="websocket", headers=headers, path=path)


@pytest.mark.parametrize("path", ["/api/x", "/vivo/g1", "/", "/v/abc"])
@pytest.mark.parametrize("headers", [
    [("origin", "https://evil.example")],
    [],
    [("origin", "null")],
    [("origin", APP), ("sec-fetch-site", "cross-site")],
    [("origin", APP), ("sec-fetch-site", "same-site")],
    [("origin", APP), ("sec-fetch-site", "none")],
    [("origin", APP), ("origin", "https://evil.example")],
    [("origin", APP), ("sec-fetch-site", "same-origin"), ("sec-fetch-site", "same-origin")],
    [("origin", APP + ".evil.com")],
    [("origin", APP + "/x")],
])
def test_ws_rechazado_sin_accept_ni_app(headers, path):
    r = ws(headers, path)
    assert (r.cierre, r.aceptado, r.llamada) == (1008, False, False)


def test_ws_sin_app_origin_siempre_rechazado():
    assert ws([("origin", APP)], origen="").llamada is False


@pytest.mark.parametrize("headers", [[("origin", APP)], [("origin", APP + "/"), ("sec-fetch-site", "same-origin")],
                                     [("origin", "HTTPS://APP.EXAMPLE:8444")]])
def test_ws_origin_exacto_pasa(headers):
    r = ws(headers)
    assert r.llamada and r.aceptado


def test_http_fuera_de_api_sigue_igual():
    r = correr(lambda a: HardeningMiddleware(a, app_origin=APP), path="/", headers=[("sec-fetch-site", "cross-site")])
    assert r.status == 200 and r.llamada
