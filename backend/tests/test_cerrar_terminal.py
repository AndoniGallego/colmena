"""Cerrar una terminal común (no Claude) desde el tablero."""
import pytest

from terminales_support import info_proceso, make_terminales, snap_de

URL = "/api/terminales/cerrar"


@pytest.fixture
def fake():
    return make_terminales({"w2:p1": ["bash"], "w1:p5": ["node", "s.js"], "w3:p1": ["bash"]})


@pytest.fixture
def enchufe(fake):
    return fake


def huella(c, pane):
    r = c.post("/api/terminales/preview", json={"pane_id": pane})
    assert r.status_code == 200, r.text
    return r.json()["huella"]


def cerrar(c, pane, n="cerrar001", h=None):
    return c.post(URL, json={"id": n, "pane_id": pane, "huella": h if h is not None else huella(c, pane)})


def pane_ids(fake):
    return {p["pane_id"] for p in snap_de(fake)["panes"]}


def auditoria(c):
    return c.get("/api/terminales/auditoria").json()["entradas"]


def test_sola_en_su_pestana_cierra_la_pestana_con_el_servicio_de_cierre(authed, fake):
    r = cerrar(authed, "w2:p1")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["cerro"] == "pestana"
    assert [c[1] for c in fake.calls_of("cerrar")] == ["w2:t1"]
    assert "w2:p1" not in pane_ids(fake)
    cierres = authed.app.state.tacciones.cierres.state.cierres()
    assert cierres[-1]["tipo"] == "tab" and cierres[-1]["target_id"] == "w2:t1"
    assert cierres[-1]["origen"] == "manual" and cierres[-1]["ok"] is True
    assert auditoria(authed)[0]["accion"] == "cerrar_terminal" and auditoria(authed)[0]["ok"] is True


def test_compartiendo_pestana_cierra_solo_ese_panel(authed, fake):
    r = cerrar(authed, "w1:p5")
    assert r.status_code == 200, r.text
    assert r.json()["cerro"] == "terminal"
    assert [c[1] for c in fake.calls_of("cerrar")] == ["w1:p5"]
    assert "w1:p5" not in pane_ids(fake) and "w1:p1" in pane_ids(fake)
    cierres = authed.app.state.tacciones.cierres.state.cierres()
    assert cierres[-1]["tipo"] == "terminal" and cierres[-1]["target_id"] == "w1:p5"
    assert cierres[-1]["origen"] == "manual"


def test_no_hace_falta_la_escritura_prendida(authed, fake):
    assert authed.app.state.tacciones.enabled() is False
    assert cerrar(authed, "w2:p1").status_code == 200


def test_nunca_cierra_una_sesion_de_claude(authed, fake):
    h = huella(authed, "w1:p5")
    assert authed.post(URL, json={"id": "cerrar002", "pane_id": "w1:p1", "huella": h}).status_code == 403
    assert authed.post(URL, json={"id": "cerrar003", "pane_id": "w3:p2", "huella": h}).status_code == 403
    # Un Claude que herdr todavía no marcó como agente: manda el proceso.
    fake.procesos["w3:p1"] = info_proceso(["claude"])
    assert authed.post(URL, json={"id": "cerrar004", "pane_id": "w3:p1", "huella": h}).status_code == 403
    assert fake.calls_of("cerrar") == []


def test_el_panel_del_orquestador_no_se_cierra(authed, fake):
    r = authed.post(URL, json={"id": "cerrar005", "pane_id": "w2:p9", "huella": "x"})
    assert r.status_code == 403 and fake.calls_of("cerrar") == []


def test_si_cambio_lo_que_corre_no_cierra(authed, fake):
    h = huella(authed, "w2:p1")
    fake.procesos["w2:p1"] = info_proceso(["vim", "notas"])
    r = cerrar(authed, "w2:p1", h=h)
    assert r.status_code == 409 and r.json()["detail"] == "la terminal cambió, revisala de nuevo"
    assert fake.calls_of("cerrar") == []
    assert auditoria(authed)[0]["ok"] is False


def test_inexistente_y_cuerpo_invalido(authed, fake):
    r = authed.post(URL, json={"id": "cerrar006", "pane_id": "w9:p9", "huella": "x"})
    assert r.status_code == 404
    assert authed.post(URL, json={"pane_id": "w2:p1"}).status_code == 400


def test_mismo_id_no_cierra_dos_veces(authed, fake):
    h = huella(authed, "w1:p5")
    assert cerrar(authed, "w1:p5", n="cerrar007", h=h).status_code == 200
    r = authed.post(URL, json={"id": "cerrar007", "pane_id": "w3:p1", "huella": huella(authed, "w3:p1")})
    assert r.status_code == 409
    assert [c[1] for c in fake.calls_of("cerrar")] == ["w1:p5"]


def test_error_de_las_terminales_es_502(authed, fake):
    from orquestador.enchufe import NoDisponible

    fake.fallas["cerrar"] = NoDisponible("herdr salió con 1")
    r = cerrar(authed, "w1:p5")
    assert r.status_code == 502


def test_el_origen_pedido_no_entra_por_el_cierre_publico(authed):
    r = authed.post("/api/close/execute", json={"id": "abcdefgh9", "tipo": "tab", "target_id": "w2:t1",
                                                 "huella": "x", "origen": "pedido-pestana"})
    assert r.status_code == 400


def _antes_del_segundo_chequeo(tacciones, monkeypatch, hacer):
    """Corre `hacer` justo antes del segundo _check_target (el de adentro del lock)."""
    orig = tacciones._check_target
    n = {"v": 0}

    async def envuelto(op, h):
        n["v"] += 1
        if n["v"] == 2:
            hacer()
        return await orig(op, h)

    monkeypatch.setattr(tacciones, "_check_target", envuelto)


def test_si_quedo_sola_en_la_pestana_dentro_del_lock_no_cierra_el_panel(authed, fake, monkeypatch):
    from terminales_support import aplicar_snapshot

    def sacar_hermano():
        snap = snap_de(fake)
        snap["panes"] = [p for p in snap["panes"] if p["pane_id"] != "w1:p1"]
        snap["agents"] = [a for a in snap["agents"] if a["pane_id"] != "w1:p1"]
        for t in snap["tabs"]:
            if t["tab_id"] == "w1:t1":
                t["pane_count"] = 1
        aplicar_snapshot(fake, snap)

    h = huella(authed, "w1:p5")
    _antes_del_segundo_chequeo(authed.app.state.tacciones, monkeypatch, sacar_hermano)
    r = cerrar(authed, "w1:p5", h=h)
    assert r.status_code == 409 and r.json()["detail"] == "la terminal quedó sola en su pestaña: revisala de nuevo"
    assert fake.calls_of("cerrar") == []
    assert auditoria(authed)[0]["ok"] is False


def test_error_inesperado_se_audita_y_gasta_el_id_si_toco(authed, fake):
    fake.fallas["cerrar"] = RuntimeError("raro")
    h = huella(authed, "w1:p5")
    with pytest.raises(RuntimeError):
        cerrar(authed, "w1:p5", n="cerrar010", h=h)
    entrada = auditoria(authed)[0]
    assert entrada["accion"] == "cerrar_terminal" and entrada["ok"] is False and entrada["error"] == "error interno"
    fake.fallas.pop("cerrar")
    r = authed.post(URL, json={"id": "cerrar010", "pane_id": "w1:p5", "huella": huella(authed, "w1:p5")})
    assert r.status_code == 409 and r.json()["detail"] == "ya se hizo"


@pytest.mark.parametrize("pane,cierra", [("w1:p5", "terminal"), ("w2:p1", "pestana"), ("w3:p1", "terminal")])
def test_preview_dice_que_se_lleva_el_cierre(authed, pane, cierra):
    r = authed.post("/api/terminales/preview", json={"pane_id": pane})
    assert r.status_code == 200 and r.json()["cierra"] == cierra


def test_preview_dice_espacio_si_es_la_unica_pestana(authed, fake):
    from terminales_support import aplicar_snapshot

    snap = snap_de(fake)
    snap["tabs"] = [t for t in snap["tabs"] if t["tab_id"] != "w2:t2"]
    snap["panes"] = [p for p in snap["panes"] if p["tab_id"] != "w2:t2"]
    snap["agents"] = [a for a in snap["agents"] if a["tab_id"] != "w2:t2"]
    aplicar_snapshot(fake, snap)
    r = authed.post("/api/terminales/preview", json={"pane_id": "w2:p1"})
    assert r.status_code == 200 and r.json()["cierra"] == "espacio"
