from __future__ import annotations

import asyncio
import gzip
import logging

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orquestador.config import Config
from orquestador.entornos import build_router
from orquestador.entornos_probador import OPCIONES_CLIENTE, Probador

ENTORNOS_FAKE = {
    "entornos": [
        {
            "nombre": "hybrid-search",
            "carpeta": "~/p/hs",
            "principal": 8095,
            "apagado": False,
            "salud": "verde",
            "servicios": [],
            "puertos": [
                {"puerto": 8095, "servicio": "hs-api", "puerto_contenedor": 8080, "abrible": True},
            ],
        },
        {
            "nombre": "viejo",
            "carpeta": "~/p/viejo",
            "principal": 9000,
            "apagado": True,
            "salud": "rojo",
            "servicios": [],
            "puertos": [{"puerto": 9000, "servicio": "web", "puerto_contenedor": 80, "abrible": True}],
        },
        {
            "nombre": "logistica",
            "carpeta": "",
            "principal": 3001,
            "apagado": False,
            "salud": None,
            "servicios": [],
            "puertos": [{"puerto": 3001, "servicio": "logistica", "puerto_contenedor": None, "abrible": True}],
        },
        {
            "nombre": "bloqueado",
            "carpeta": "~/p/b",
            "principal": 8770,
            "apagado": False,
            "salud": "verde",
            "servicios": [],
            "puertos": [{"puerto": 8770, "servicio": "api", "puerto_contenedor": 8770, "abrible": False}],
        },
    ],
    "error": None,
}


async def _listar_fake() -> dict:
    return ENTORNOS_FAKE


def _pedido(**kw):
    base = {
        "nombre": "hybrid-search",
        "puerto": 8095,
        "metodo": "GET",
        "ruta": "/",
        "confirmado": False,
    }
    base.update(kw)
    return base


def _probador(mock_requests: list, handler, *, now=None, cliente_factory=None):
    async def transport(request: httpx.Request) -> httpx.Response:
        mock_requests.append(request)
        result = handler(request)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def factory():
        return httpx.AsyncClient(
            transport=httpx.MockTransport(transport),
            **OPCIONES_CLIENTE,
        )

    return Probador(
        _listar_fake,
        cliente_factory=cliente_factory or factory,
        now=now or __import__("time").monotonic,
    )


def _ok_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"ok")


def test_puerto_no_del_entorno_404_sin_requests():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido(puerto=3001)))
    assert codigo == 404 and cuerpo == {"error": "Ese puerto no es de un entorno prendido"}
    assert requests == []


def test_entorno_apagado_404():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    codigo, _ = asyncio.run(prob.probar(_pedido(nombre="viejo", puerto=9000)))
    assert codigo == 404
    assert requests == []


def test_puerto_no_abrible_404():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    codigo, _ = asyncio.run(prob.probar(_pedido(nombre="bloqueado", puerto=8770)))
    assert codigo == 404
    assert requests == []


def test_entorno_extra_ok():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido(nombre="logistica", puerto=3001)))
    assert codigo == 200 and cuerpo["codigo"] == 200


@pytest.mark.parametrize(
    "ruta",
    [
        "x",
        "//evil.com/a",
        "http://evil.com",
        "/a b",
        "/a\r\nX: y",
        "/a\\b",
        "/a#b",
        "/" + "a" * 2048,
    ],
)
def test_rutas_invalidas_400_sin_requests(ruta):
    requests: list = []
    prob = _probador(requests, _ok_handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido(ruta=ruta)))
    assert codigo == 400 and cuerpo["error"] == "Pedido inválido"
    assert requests == []


def test_url_mock_exacta():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    asyncio.run(prob.probar(_pedido(ruta="/api/search?q=zapa")))
    assert len(requests) == 1
    assert str(requests[0].url) == "http://127.0.0.1:8095/api/search?q=zapa"


def test_302_sin_seguir():
    requests: list = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://evil.com"})

    prob = _probador(requests, handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido()))
    assert codigo == 200 and cuerpo["codigo"] == 302
    assert len(requests) == 1


def test_confirmado_y_cuerpo_metodo():
    requests: list = []
    prob = _probador(requests, _ok_handler)

    codigo, cuerpo = asyncio.run(prob.probar(_pedido(metodo="POST", ruta="/x", cuerpo="hola")))
    assert codigo == 400 and "error" in cuerpo
    assert requests == []

    codigo, _ = asyncio.run(prob.probar(_pedido(metodo="GET", cuerpo="nope")))
    assert codigo == 400
    assert requests == []

    asyncio.run(
        prob.probar(_pedido(metodo="POST", ruta="/x", cuerpo="hola", confirmado=True)),
    )
    assert requests[-1].content == b"hola"


def test_encabezados_invalidos():
    requests: list = []
    prob = _probador(requests, _ok_handler)

    for hdr in (
        [{"nombre": "Host", "valor": "x"}],
        [{"nombre": "transfer-encoding", "valor": "chunked"}],
        [{"nombre": "Proxy-Authorization", "valor": "x"}],
        [{"nombre": "X", "valor": "a\r\nb"}],
        [{"nombre": f"H{i}", "valor": "v"} for i in range(21)],
        [{"nombre": "X-A", "valor": "año"}],
    ):
        codigo, _ = asyncio.run(prob.probar(_pedido(encabezados=hdr)))
        assert codigo == 400
    assert requests == []


def test_encabezados_salientes_limpios():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    asyncio.run(
        prob.probar(
            _pedido(
                encabezados=[{"nombre": "X-Api-Key", "valor": "abc"}],
            ),
        ),
    )
    req = requests[0]
    nombres = {k.lower() for k in req.headers.keys()}
    assert "cookie" not in nombres and "authorization" not in nombres
    assert req.headers.get("x-api-key") == "abc"


def test_truncado_cuerpo_grande():
    requests: list = []
    cuerpo = b"x" * 300000

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=cuerpo)

    prob = _probador(requests, handler)
    _, resp = asyncio.run(prob.probar(_pedido(ruta="/grande")))
    assert resp["bytes"] == 262144 and resp["truncado"] is True


def test_set_cookie_oculto():
    requests: list = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"set-cookie": "a=1", "content-type": "text/plain"}, content=b"")

    prob = _probador(requests, handler)
    _, resp = asyncio.run(prob.probar(_pedido()))
    vals = {h[0].lower(): h[1] for h in resp["encabezados"]}
    assert vals.get("set-cookie") == "(oculto)"


def test_binario_sin_cuerpo_texto():
    requests: list = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG")

    prob = _probador(requests, handler)
    _, resp = asyncio.run(prob.probar(_pedido()))
    assert resp["cuerpo"] is None and resp["bytes"] > 0


def test_errores_red_y_tope(monkeypatch):
    requests: list = []

    def connect_err(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("x")

    prob = _probador(requests, connect_err)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido()))
    assert codigo == 502 and cuerpo["error"] == "El servicio no responde"

    def read_timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("x")

    prob = _probador(requests, read_timeout)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido()))
    assert codigo == 504 and cuerpo["error"] == "El servicio tardó más de 10 s"

    monkeypatch.setattr("orquestador.entornos_probador.TOPE_S", 0.05)

    async def colgado(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.0)
        return httpx.Response(200)

    prob = _probador(requests, colgado)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido()))
    assert codigo == 504 and cuerpo["error"] == "El servicio tardó más de 10 s"


def test_concurrencia_y_rate_limit():
    async def _run() -> None:
        requests: list = []
        t0 = 1000.0
        now = {"t": t0}

        def clock():
            return now["t"]

        event = asyncio.Event()

        async def transport_lento(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            await event.wait()
            return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"")

        def factory_lento():
            return httpx.AsyncClient(transport=httpx.MockTransport(transport_lento), **OPCIONES_CLIENTE)

        prob = Probador(_listar_fake, cliente_factory=factory_lento, now=clock)
        t1 = asyncio.create_task(prob.probar(_pedido(ruta="/lento")))
        await asyncio.sleep(0.01)
        codigo, cuerpo = await prob.probar(_pedido(ruta="/dos"))
        assert codigo == 429 and cuerpo["error"] == "Ya hay una prueba en curso"
        event.set()
        await t1

        prob2 = _probador([], _ok_handler, now=clock)
        for i in range(30):
            codigo, _ = await prob2.probar(_pedido(ruta=f"/ok{i}"))
            assert codigo == 200
        codigo, cuerpo = await prob2.probar(_pedido(ruta="/31"))
        assert codigo == 429 and cuerpo["error"] == "Demasiadas pruebas seguidas; esperá un minuto"

        now["t"] = t0 + 61.0
        codigo, _ = await prob2.probar(_pedido(ruta="/despues"))
        assert codigo == 200

    asyncio.run(_run())


def test_log_no_filtra_secretos(caplog):
    caplog.set_level(logging.INFO)
    caplog.set_level(logging.INFO, logger="orquestador.entornos_probador")
    requests: list = []
    prob = _probador(requests, _ok_handler)
    asyncio.run(
        prob.probar(
            _pedido(
                ruta="/secreto?token=XYZ",
                encabezados=[{"nombre": "X-Api-Key", "valor": "CLAVE"}],
                metodo="POST",
                cuerpo="CUERPO",
                confirmado=True,
            ),
        ),
    )
    texto = caplog.text
    for prohibido in ("secreto", "XYZ", "CLAVE", "CUERPO"):
        assert prohibido not in texto


def test_opciones_cliente():
    assert OPCIONES_CLIENTE["follow_redirects"] is False
    assert OPCIONES_CLIENTE["trust_env"] is False


def test_cliente_factory_por_defecto():
    prob = Probador(_listar_fake)

    async def _run() -> None:
        async with prob._cliente_factory() as client:
            assert client.follow_redirects is False
            assert client._trust_env is False

    asyncio.run(_run())


def test_ruta_del_127_400():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido(ruta="/a\x7fb")))
    assert codigo == 400 and cuerpo["error"] == "Pedido inválido"
    assert requests == []


def test_cuerpo_surrogate_400():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    codigo, cuerpo = asyncio.run(
        prob.probar(_pedido(metodo="POST", ruta="/x", cuerpo="\ud800", confirmado=True)),
    )
    assert codigo == 400 and cuerpo["error"] == "Pedido inválido"
    assert requests == []


def test_connect_timeout_504():
    requests: list = []

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("x")

    prob = _probador(requests, handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido()))
    assert codigo == 504 and cuerpo["error"] == "El servicio tardó más de 10 s"


def test_runtime_error_502_sin_ruta_en_log(caplog):
    caplog.set_level(logging.WARNING, logger="orquestador.entornos_probador")

    requests: list = []

    def handler(_request: httpx.Request) -> httpx.Response:
        raise RuntimeError("boom /secreto")

    prob = _probador(requests, handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido()))
    assert codigo == 502 and cuerpo["error"] == "El servicio no responde"
    assert "secreto" not in caplog.text


def _probador_listar(listar, mock_requests: list, handler):
    async def transport(request: httpx.Request) -> httpx.Response:
        mock_requests.append(request)
        result = handler(request)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def factory():
        return httpx.AsyncClient(
            transport=httpx.MockTransport(transport),
            **OPCIONES_CLIENTE,
        )

    return Probador(listar, cliente_factory=factory)


def test_listar_error_docker_503():
    requests: list = []

    async def listar_err() -> dict:
        return {"entornos": [], "error": "Docker no responde"}

    prob = _probador_listar(listar_err, requests, _ok_handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido()))
    assert codigo == 503 and cuerpo == {"error": "Docker no responde"}
    assert requests == []


def test_listar_colgado_libera_lock(monkeypatch):
    monkeypatch.setattr("orquestador.entornos_probador.TOPE_S", 0.05)
    requests: list = []
    llamadas = {"n": 0}

    async def listar_colgado() -> dict:
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            await asyncio.Event().wait()
        return ENTORNOS_FAKE

    prob = _probador_listar(listar_colgado, requests, _ok_handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido()))
    assert codigo == 504 and cuerpo == {"error": "Docker no responde"}
    assert not prob._mutex.locked()
    codigo2, cuerpo2 = asyncio.run(prob.probar(_pedido()))
    assert codigo2 == 200 and cuerpo2["codigo"] == 200


def test_accept_encoding_saliente_identity():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    asyncio.run(prob.probar(_pedido()))
    assert requests[0].headers.get("accept-encoding") == "identity"


def test_listar_runtime_error_503():
    requests: list = []

    async def listar_boom() -> dict:
        raise RuntimeError("x")

    prob = _probador_listar(listar_boom, requests, _ok_handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido()))
    assert codigo == 503 and cuerpo == {"error": "Docker no responde"}
    assert requests == []


def test_autorizado_entradas_basura_404():
    requests: list = []

    async def listar_basura() -> dict:
        return {
            "entornos": [
                "basura",
                {"nombre": "hybrid-search", "apagado": False, "puertos": ["mal"]},
            ],
        }

    prob = _probador_listar(listar_basura, requests, _ok_handler)
    codigo, cuerpo = asyncio.run(prob.probar(_pedido()))
    assert codigo == 404 and cuerpo == {"error": "Ese puerto no es de un entorno prendido"}
    assert requests == []


class _BytesStream(httpx.AsyncByteStream):
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aiter__(self):
        yield self._data


def test_respuesta_gzip_sin_descomprimir():
    requests: list = []
    comprimido = gzip.compress(b"a" * 1_000_000)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip", "content-type": "text/plain"},
            stream=_BytesStream(comprimido),
        )

    prob = _probador(requests, handler)
    _, resp = asyncio.run(prob.probar(_pedido()))
    assert resp["cuerpo"] is None
    assert resp["bytes"] == len(comprimido)
    assert resp["truncado"] is False


def test_httpx_log_fuera_probador(caplog):
    caplog.set_level(logging.INFO)

    async def _run() -> None:
        transport = httpx.MockTransport(lambda _r: httpx.Response(200))
        async with httpx.AsyncClient(transport=transport) as client:
            await client.get("http://127.0.0.1:9/")

    asyncio.run(_run())
    assert "HTTP Request" in caplog.text


def test_accept_encoding_usuario_400():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    codigo, _ = asyncio.run(
        prob.probar(_pedido(encabezados=[{"nombre": "Accept-Encoding", "valor": "gzip"}])),
    )
    assert codigo == 400
    assert requests == []


def test_router_probar():
    requests: list = []
    prob = _probador(requests, _ok_handler)
    app = FastAPI()
    app.include_router(build_router(Config(), runner=None, probador=prob), prefix="/api")
    with TestClient(app) as client:
        r = client.post(
            "/api/entornos/probar",
            json=_pedido(ruta="/api/hola"),
        )
        assert r.status_code == 200 and r.headers.get("cache-control") == "no-store"
        r2 = client.post("/api/entornos/probar", content=b"no-json", headers={"content-type": "application/json"})
        assert r2.status_code == 400 and r2.json()["error"] == "Pedido inválido"
        r3 = client.post(
            "/api/entornos/probar",
            content=b"x" * 300_000,
            headers={"content-type": "application/json"},
        )
        assert r3.status_code == 413 and r3.json()["error"] == "Pedido demasiado grande"
        assert r3.headers.get("cache-control") == "no-store"
        pedido_max = _pedido(
            metodo="POST",
            ruta="/max",
            confirmado=True,
            cuerpo="x" * 65536,
            encabezados=[{"nombre": f"X-H{i}", "valor": "v" * 4096} for i in range(20)],
        )
        r4 = client.post("/api/entornos/probar", json=pedido_max)
        assert r4.status_code == 200 and r4.headers.get("cache-control") == "no-store"

        class _PedidoStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                bloque = b"y" * 65536
                emitidos = 0
                while emitidos < 320_000:
                    yield bloque
                    emitidos += len(bloque)

        async def _post_stream():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                req = httpx.Request(
                    "POST",
                    "http://test/api/entornos/probar",
                    headers={"content-type": "application/json"},
                    stream=_PedidoStream(),
                )
                assert "content-length" not in req.headers
                return await ac.send(req)

        r5 = asyncio.run(_post_stream())
        assert r5.status_code == 413 and r5.json()["error"] == "Pedido demasiado grande"
