import pytest

from asgi_support import correr
from orquestador import auth, cli, entrada
from orquestador.config import Config, hash_pin, load_config, save_config
from orquestador.entrada import EntradaInvalida, Listener

PROD = dict(app_origin="https://app.example:8444", viewer_origin="https://app.example:8445")

ENTRADA = {"modos": ["tailscale", "solo-local"],
           "tailscale": {"cabecera_ip": "X-Forwarded-For"},
           "solo-local": {"puerto_app": 8774, "origen_app": "http://localhost:8774"}}


def test_sin_entrada_default_vacio(tmp_path):
    (tmp_path / "config.toml").write_text('pin = ""\nport = 8770\n')
    assert load_config(tmp_path).entrada == {}


def test_entrada_ida_y_vuelta(tmp_path):
    save_config(Config(entrada=ENTRADA), tmp_path)
    assert load_config(tmp_path).entrada == ENTRADA


def test_entrada_en_tablas_toml_se_lee(tmp_path):
    (tmp_path / "config.toml").write_text(
        '[entrada]\nmodos = ["tailscale"]\n[entrada.tailscale]\ncabecera_ip = "X-Forwarded-For"\n')
    assert load_config(tmp_path).entrada == {"modos": ["tailscale"], "tailscale": {"cabecera_ip": "X-Forwarded-For"}}


def test_set_pin_conserva_entrada(tmp_path, monkeypatch):
    d = tmp_path / "d"
    d.mkdir()
    save_config(Config(pin=hash_pin("viejopin1"), entrada=ENTRADA), d)
    monkeypatch.setenv("ORQ_DATA_DIR", str(d))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "unpinlargo")
    assert cli.set_pin() == 0
    assert load_config(d).entrada == ENTRADA


def test_env_sigue_pisando_origenes(tmp_path, monkeypatch):
    save_config(Config(app_origin="https://viejo.example:8444", viewer_origin="https://viejo.example:8445"), tmp_path)
    monkeypatch.setenv("ORQ_APP_ORIGIN", "https://nuevo.example:8444/")
    monkeypatch.setenv("ORQ_VIEWER_ORIGIN", "https://nuevo.example:8445")
    cfg = load_config(tmp_path)
    assert (cfg.app_origin, cfg.viewer_origin) == ("https://nuevo.example:8444", "https://nuevo.example:8445")


def test_env_vacio_no_pisa_origenes_del_toml(tmp_path, monkeypatch):
    save_config(Config(app_origin="https://toml.example:8444", viewer_origin="https://toml.example:8445"), tmp_path)
    monkeypatch.setenv("ORQ_APP_ORIGIN", "")
    monkeypatch.setenv("ORQ_VIEWER_ORIGIN", "")
    cfg = load_config(tmp_path)
    assert (cfg.app_origin, cfg.viewer_origin) == ("https://toml.example:8444", "https://toml.example:8445")


def test_aviso_sin_app_origin_en_modo_tailscale():
    cfg = Config(**{**PROD, "app_origin": ""})
    assert any("app_origin" in a for a in entrada.avisos(cfg))


def test_sin_seccion_igual_que_hoy():
    cfg = Config(**PROD)
    assert entrada.modos(cfg) == ["tailscale"]
    assert entrada.listeners(cfg) == [Listener("tailscale", "app", "127.0.0.1", 8770),
                                      Listener("tailscale", "visor", "127.0.0.1", 8771)]
    a = entrada.ajustes("tailscale", cfg)
    assert (a.origen_app, a.origen_visor, a.cabecera_ip) == (PROD["app_origin"], PROD["viewer_origin"], "")
    assert a.hosts_app == {"app.example", "localhost", "127.0.0.1", "::1"}


def test_sin_viewer_origin_no_hay_visor():
    assert [l.rol for l in entrada.listeners(Config(app_origin=PROD["app_origin"]))] == ["app"]


def test_solo_local_por_defecto():
    cfg = Config(**PROD, entrada={"modos": ["tailscale", "solo-local"]})
    assert entrada.listeners(cfg)[-1] == Listener("solo-local", "app", "127.0.0.1", 8774)
    a = entrada.ajustes("solo-local", cfg)
    assert a.origen_app == "http://localhost:8774" and a.hosts_app == entrada.HOSTS_LOCALES


def test_listeners_solo_loopback():
    assert all(l.host == "127.0.0.1" for l in entrada.listeners(Config(**PROD, entrada={"modos": ["tailscale", "solo-local"]})))
    with pytest.raises(EntradaInvalida):
        entrada.listeners(Config(host="0.0.0.0"))


@pytest.mark.parametrize("modos", [[], ["nada"], ["tailscale", "tailscale"], [""]])
def test_modos_invalidos_dan_error(modos):
    with pytest.raises(EntradaInvalida) as exc:
        entrada.listeners(Config(entrada={"modos": modos}))
    assert str(exc.value)


def test_entrada_invalida_mensaje_nombra_clave():
    with pytest.raises(EntradaInvalida) as exc:
        entrada.modos(Config(entrada={"modos": []}))
    assert "modos" in str(exc.value).lower()
    with pytest.raises(EntradaInvalida) as exc:
        entrada.listeners(
            Config(entrada={"modos": ["solo-local"], "solo-local": {"puerto_app": "8774"}})
        )
    assert "puerto_app" in str(exc.value)


@pytest.mark.parametrize("valor", ["tailscale", {"modos": "tailscale"},
                                   {"modos": ["solo-local"], "solo-local": {"puerto_app": "8774"}},
                                   {"tailscale": {"cabecera_ip": "X Forwarded"}},
                                   {"modos": ["solo-local"], "solo-local": {"origen_app": "http://evil.example:8774"}}])
def test_tipos_incorrectos_dan_error(valor):
    with pytest.raises(EntradaInvalida):
        entrada.listeners(Config(entrada=valor))


def test_puerto_repetido_da_error():
    with pytest.raises(EntradaInvalida):
        entrada.listeners(Config(entrada={"modos": ["tailscale", "solo-local"], "solo-local": {"puerto_app": 8770}}))


def test_avisos():
    assert any("tailscale_user" in a for a in entrada.avisos(Config(**PROD)))
    assert not any("tailscale_user" in a for a in entrada.avisos(Config(**PROD, tailscale_user="yo@example.com")))


def test_valores_header():
    scope = {"headers": [(b"x-test", b"a"), (b"x-test", b"b"), (b"other", b"c")]}
    assert auth.valores_header(scope, "X-Test") == ["a", "b"]
    assert auth.valores_header(scope, "missing") == []


def test_cidr_cierra_websocket_sin_llamar_a_la_app():
    r = correr(lambda a: auth.CidrMiddleware(a, auth.parse_networks(["10.0.0.0/8"])), tipo="websocket")
    assert (r.cierre, r.aceptado, r.llamada) == (1008, False, False)


_SOLO_LOCAL_ORIGEN_INVALIDO = [
    "http://evil.example\\@localhost:8774",
    "http:///evil.example",
    "//localhost",
    "http://localhost:8774/x",
    "http://localhost:8774?a",
    "http://user@localhost:8774",
]

_SOLO_LOCAL_ORIGEN_VALIDO = [
    "http://localhost:8774",
    "http://127.0.0.1:8774",
    "http://[::1]:8774",
]


@pytest.mark.parametrize("origen_app", _SOLO_LOCAL_ORIGEN_INVALIDO)
def test_solo_local_origen_app_rechaza_origenes_malformados(origen_app):
    cfg = Config(
        entrada={"modos": ["solo-local"], "solo-local": {"origen_app": origen_app}},
    )
    with pytest.raises(EntradaInvalida):
        entrada.listeners(cfg)


@pytest.mark.parametrize("origen_app", _SOLO_LOCAL_ORIGEN_VALIDO)
def test_solo_local_origen_app_acepta_loopback(origen_app):
    cfg = Config(
        entrada={"modos": ["solo-local"], "solo-local": {"origen_app": origen_app}},
    )
    entrada.listeners(cfg)


def test_tailscale_app_origin_rechaza_backslash_en_host():
    cfg = Config(app_origin="https://evil.example\\@app.example:8444")
    with pytest.raises(EntradaInvalida):
        entrada.listeners(cfg)


def test_host_de_ipv6_incompleto_da_entrada_invalida():
    with pytest.raises(EntradaInvalida):
        entrada.host_de("http://[::1")


def test_modo_cloudflare_rechazado():
    cfg = Config(entrada={"modos": ["cloudflare"]})
    with pytest.raises(EntradaInvalida, match="el modo cloudflare ya no existe"):
        entrada.listeners(cfg)


def test_origenes_principales():
    ts = Config(app_origin="https://ts.app", viewer_origin="https://ts.vis", entrada={"modos": ["tailscale"]})
    assert entrada.origenes_principales(ts) == ("https://ts.app", "https://ts.vis")
    solo = Config(app_origin="https://x", viewer_origin="", entrada={"modos": ["solo-local"]})
    assert entrada.origenes_principales(solo) == ("https://x", "")


def test_cabecera_ip_no_string_da_entrada_invalida():
    cfg = Config(
        **PROD,
        entrada={"modos": ["tailscale"], "tailscale": {"cabecera_ip": 0}},
    )
    with pytest.raises(EntradaInvalida):
        entrada.listeners(cfg)
