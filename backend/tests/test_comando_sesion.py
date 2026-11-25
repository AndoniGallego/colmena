import json

import pytest

from conftest import SID, make_snapshot
from orquestador.terminales import redactar
from orquestador.transcript import parse_file
from terminales_support import aplicar_snapshot

URL = f"/api/sessions/{SID}/comando"
PANE = "w1:p1"
MID = "aaaaaaaa-1111-2222-3333-444444444444"
CMD = "glab auth login --hostname gitlab.example"


def bloque(cmd=CMD, motivo="Para loguearte en GitLab", **extra):
    return "```comando\n" + json.dumps({"comando": cmd, "motivo": motivo, **extra}) + "\n```"


def escribir(projects, *lines):
    path = projects / "-proj" / f"{SID}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")


def asistente(text, mid=MID):
    return {"type": "assistant", "uuid": mid, "message": {"content": [{"type": "text", "text": text}]}}


def humano(text):
    return {"type": "user", "uuid": "u-" + text[:20], "message": {"content": text}}


def pedir(projects, *bloques, mid=MID):
    escribir(projects, asistente("Necesito que corras esto:\n\n" + "\n\n".join(bloques or (bloque(),)), mid))


@pytest.fixture
def on(cfg, app, enchufe):
    cfg.terminales_escritura = True
    app.state.comando_sesion.sleep = _no_sleep
    enchufe.pantallas[PANE] = lambda _op: pantalla_bash(linea_tipeada(enchufe))
    return cfg


def linea_tipeada(enchufe):
    """Lo que quedó en la entrada de la sesión según lo que se tipeó desde el último Ctrl+U."""
    linea = ""
    for c in enchufe.calls:
        if c[0] == "teclas" and "ctrl-u" in c[2]:
            linea = ""
        elif c[0] == "escribir":
            linea += c[2]
        elif c[0] == "teclas" and "enter" in c[2]:
            linea = ""
    return linea


async def _no_sleep(_s):
    return None


def escrituras(enchufe):
    return [c for c in enchufe.calls if c[0] in ("teclas", "escribir", "ejecutar", "mandar_prompt")]


def post(c, mid=MID, indice=0, comando=CMD, **headers):
    return c.post(URL, json={"mid": mid, "indice": indice, "comando": comando}, headers=headers or None)


# ---------- camino feliz ----------

def test_corre_el_comando_en_modo_bash_de_la_sesion(authed, projects, enchufe, on):
    pedir(projects)
    r = post(authed)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "comando": CMD, "cwd": "/tmp"}
    assert escrituras(enchufe) == [
        ("teclas", PANE, ("ctrl-e", "ctrl-u")),
        ("escribir", PANE, "!"),
        ("escribir", PANE, CMD),
        ("teclas", PANE, ("enter",)),
    ]


def test_corre_el_bloque_del_indice_pedido(authed, projects, enchufe, on):
    pedir(projects, bloque("echo uno"), bloque("echo dos"))
    r = post(authed, indice=1, comando="echo dos")
    assert r.status_code == 200, r.text
    assert ("escribir", PANE, "echo dos") in escrituras(enchufe)


def test_audita_y_avisa(authed, projects, on, monkeypatch):
    avisos = []

    async def notify(title, body, tag, pane_id=""):
        avisos.append((title, body, tag, pane_id))

    authed.app.state.comando_sesion.notify = notify
    pedir(projects)
    assert post(authed).status_code == 200
    audit = authed.get("/api/terminales/auditoria").json()["entradas"]
    assert audit[0]["accion"] == "comando_sesion" and audit[0]["ok"] is True
    assert audit[0]["comando"] == redactar(CMD) and audit[0]["pane_id"] == PANE and audit[0]["session_id"] == SID
    assert avisos and avisos[0][2] == "terminal-comando-sesion" and avisos[0][3] == PANE


# ---------- el backend no confía en el cliente ----------

def test_el_texto_del_cliente_tiene_que_coincidir_con_el_transcript(authed, projects, enchufe, on):
    pedir(projects)
    r = post(authed, comando="rm -rf ~")
    assert r.status_code == 409
    assert escrituras(enchufe) == []


def test_mensaje_inexistente_es_404(authed, projects, enchufe, on):
    pedir(projects)
    assert post(authed, mid="bbbbbbbb-0000").status_code == 404
    assert escrituras(enchufe) == []


def test_indice_inexistente_es_404(authed, projects, enchufe, on):
    pedir(projects)
    assert post(authed, indice=3).status_code == 404
    assert escrituras(enchufe) == []


def test_un_mensaje_del_usuario_con_ese_uuid_no_sirve(authed, projects, enchufe, on):
    escribir(projects, {"type": "user", "uuid": MID, "message": {"content": bloque()}})
    assert post(authed).status_code == 404
    assert escrituras(enchufe) == []


@pytest.mark.parametrize("cmd", ["echo a\necho b", "echo​hola", "echo\x1b[2J", " echo", "x" * 501, "-rf"])
def test_comando_invalido_en_el_transcript_es_400(authed, projects, enchufe, on, cmd):
    pedir(projects, bloque(cmd))
    assert post(authed, comando=cmd[:600]).status_code == 400
    assert escrituras(enchufe) == []


def test_pedido_viejo_tras_un_prompt_humano_es_409(authed, projects, enchufe, on):
    pedir(projects)
    escribir(projects, humano("dale, seguimos con otra cosa"), asistente("ok", "cccccccc-1"))
    r = post(authed)
    assert r.status_code == 409
    assert escrituras(enchufe) == []


def test_un_comando_local_despues_no_vuelve_viejo_el_pedido(authed, projects, enchufe, on):
    pedir(projects, bloque("echo uno"), bloque("echo dos"))
    escribir(projects, humano("<bash-input>echo uno</bash-input>"),
             humano("<bash-stdout>uno</bash-stdout><bash-stderr></bash-stderr>"))
    assert post(authed, indice=1, comando="echo dos").status_code == 200


# ---------- una sola vez ----------

def test_segundo_intento_es_409(authed, projects, enchufe, on):
    pedir(projects)
    assert post(authed).status_code == 200
    antes = len(escrituras(enchufe))
    r = post(authed)
    assert r.status_code == 409
    assert len(escrituras(enchufe)) == antes


def test_ya_corrido_segun_el_transcript_es_409(authed, projects, enchufe, on):
    pedir(projects)
    escribir(projects, humano(f"<bash-input>{CMD}</bash-input>"))
    assert post(authed).status_code == 409
    assert escrituras(enchufe) == []


# ---------- estado de la sesión ----------

def test_sesion_trabajando_es_409_con_el_mensaje(authed, projects, enchufe, on):
    pedir(projects)
    aplicar_snapshot(enchufe, make_snapshot("working"))
    r = post(authed)
    assert r.status_code == 409 and r.json()["detail"] == "La sesión está trabajando; probá cuando termine"
    assert escrituras(enchufe) == []


def test_sesion_bloqueada_es_409(authed, projects, enchufe, on):
    pedir(projects)
    aplicar_snapshot(enchufe, make_snapshot("blocked"))
    assert post(authed).status_code == 409
    assert escrituras(enchufe) == []


def test_un_fallo_tras_un_409_por_estado_no_gasta_el_bloque(authed, projects, enchufe, on):
    pedir(projects)
    aplicar_snapshot(enchufe, make_snapshot("working"))
    assert post(authed).status_code == 409
    aplicar_snapshot(enchufe, make_snapshot("idle"))
    assert post(authed).status_code == 200


def test_sesion_que_no_esta_en_el_tablero_es_404(authed, projects, enchufe, on):
    pedir(projects)
    snap = make_snapshot()
    snap["agents"] = [a for a in snap["agents"] if a["pane_id"] != PANE]
    aplicar_snapshot(enchufe, snap)
    assert post(authed).status_code == 404
    assert escrituras(enchufe) == []


def test_pane_protegido_es_400(authed, projects, enchufe, on):
    pedir(projects)
    authed.app.state.comando_sesion.protected_panes = lambda: {PANE}
    assert post(authed).status_code == 400
    assert escrituras(enchufe) == []


# ---------- interruptor, límites y protección de la ruta ----------

def test_escritura_apagada_es_403(authed, projects, enchufe):
    pedir(projects)
    r = post(authed)
    assert r.status_code == 403 and r.json()["detail"] == "escritura apagada"
    assert escrituras(enchufe) == []


def test_limite_de_frecuencia(authed, projects, enchufe, on):
    pedir(projects, *(bloque(f"echo {i}") for i in range(8)))
    codes = [post(authed, indice=i, comando=f"echo {i}").status_code for i in range(7)]
    assert codes[:6] == [200] * 6 and codes[6] == 429


def test_ruta_exige_sesion_y_mismo_origen(client, projects, on):
    pedir(projects)
    assert post(client).status_code == 401
    r = client.post(URL, json={"mid": MID, "indice": 0, "comando": CMD}, headers={"Origin": "https://evil.example"})
    assert r.status_code in (401, 403)


def test_otro_origen_autenticado_es_403(authed, projects, enchufe, on):
    pedir(projects)
    r = post(authed, Origin="https://evil.example")
    assert r.status_code == 403
    assert escrituras(enchufe) == []


def test_get_es_405_y_cuerpo_extra_400(authed, projects, on):
    assert authed.get(URL).status_code == 405
    r = authed.post(URL, json={"mid": MID, "indice": 0, "comando": CMD, "pane_id": "w2:p9"})
    assert r.status_code == 400


def test_session_id_invalido_es_400(authed, on):
    r = authed.post("/api/sessions/no%20vale/comando", json={"mid": MID, "indice": 0, "comando": CMD})
    assert r.status_code == 400


# ---------- transcript expone el id del mensaje ----------

def test_transcript_marca_mid_y_offset_de_los_bloques_comando(projects):
    path = projects / "-proj" / f"{SID}.jsonl"
    escribir(projects, {"type": "assistant", "uuid": MID, "message": {"content": [
        {"type": "text", "text": bloque("echo uno")},
        {"type": "text", "text": "y\n\n" + bloque("echo dos") + "\n\n" + bloque("echo tres")},
    ]}})
    items, _ = parse_file(path)
    claude = [i for i in items if i.get("kind") == "claude" and "cmid" in i]
    assert [(i["cmid"], i["cstart"]) for i in claude] == [(MID, 0), (MID, 1)]


def test_transcript_pagina_deja_pasar_cmid(authed, projects):
    pedir(projects)
    items = authed.get(f"/api/sessions/{SID}/transcript").json()["items"]
    last = [i for i in items if i.get("kind") == "claude"][-1]
    assert last["cmid"] == MID and last["cstart"] == 0


# ---------- servicio directo: concurrencia y cambios entre el chequeo y la escritura ----------

import asyncio  # noqa: E402
from collections import defaultdict  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from orquestador.comando_sesion import ComandoSesionBody, ComandoSesionService  # noqa: E402

DCMD = "git push origin main"
CTX = SimpleNamespace(ip="1.2.3.4", user="u", device="d")


def _tablero(status="idle", ws_label="w"):
    return {"workspaces": [{"label": ws_label, "tabs": [{"label": "t", "agents": [
        {"kind": "claude", "session_id": SID, "pane_id": "p1", "status": status, "cwd": "/tmp"}]}]}]}


class EnchufeDirecto:
    def __init__(self):
        self.calls = []
        self.linea = ""

    async def teclas(self, pane, keys):
        self.calls.append(("teclas", pane, keys))
        if "ctrl-u" in keys:
            self.linea = ""
        await asyncio.sleep(0)

    async def escribir(self, pane, text):
        self.calls.append(("escribir", pane, text))
        self.linea += text
        await asyncio.sleep(0)

    async def leer(self, pane, **_kw):
        return pantalla_bash(self.linea)


def pantalla_bash(linea):
    regla = "─" * 40
    return f"● listo\n\n{regla}\n{linea[:1]} {linea[1:]}\n{regla}\n  ? for shortcuts\n"


def _directo(tmp_path, tableros=None, ws_label="w", carpeta=None, al_tablero=None):
    path = tmp_path / f"{SID}.jsonl"
    extra = {"carpeta": carpeta} if carpeta else {}
    texto = "Corré esto:\n\n```comando\n" + json.dumps({"comando": DCMD, "motivo": "x", **extra}) + "\n```"
    path.write_text(json.dumps({"type": "assistant", "uuid": MID, "cwd": "/tmp",
                                "message": {"content": [{"type": "text", "text": texto}]}}) + "\n")
    locks = defaultdict(asyncio.Lock)
    enchufe = EnchufeDirecto()
    estados = list(tableros or ["idle"])

    async def board():
        if al_tablero:
            al_tablero(path)
        return _tablero(estados.pop(0) if len(estados) > 1 else estados[0], ws_label)

    async def nosleep(_s):
        await asyncio.sleep(0)

    svc = ComandoSesionService(board, SimpleNamespace(find=lambda sid: path), enchufe,
                               SimpleNamespace(get=lambda p: locks[p]), SimpleNamespace(write=lambda e: None),
                               SimpleNamespace(hit=lambda *a: 0), lambda: True, None, lambda: set(), sleep=nosleep)
    return svc, enchufe


def _escritos(enchufe):
    return [c for c in enchufe.calls if c == ("escribir", "p1", DCMD)]


def test_doble_toque_concurrente_corre_una_sola_vez(tmp_path):
    svc, enchufe = _directo(tmp_path)
    body = ComandoSesionBody(mid=MID, indice=0, comando=DCMD)

    async def go():
        return await asyncio.gather(svc.correr(SID, body, CTX), svc.correr(SID, body, CTX), return_exceptions=True)

    res = asyncio.run(go())
    assert len(_escritos(enchufe)) == 1, enchufe.calls
    oks = [r for r in res if isinstance(r, dict)]
    errs = [r for r in res if not isinstance(r, dict)]
    assert len(oks) == 1 and len(errs) == 1 and errs[0].status == 409


def test_bash_input_que_aparece_antes_de_escribir_frena(tmp_path):
    vistas = []

    def anotar(path):
        vistas.append(1)
        if len(vistas) == 1:
            with path.open("a") as fh:
                fh.write(json.dumps({"type": "user", "message": {"content": f"<bash-input>{DCMD}</bash-input>"}}) + "\n")

    svc, enchufe = _directo(tmp_path, al_tablero=anotar)
    with pytest.raises(Exception) as exc:
        asyncio.run(svc.correr(SID, ComandoSesionBody(mid=MID, indice=0, comando=DCMD), CTX))
    assert getattr(exc.value, "status", None) == 409
    assert enchufe.calls == []


def test_sesion_que_se_pone_a_trabajar_antes_de_escribir_frena(tmp_path):
    svc, enchufe = _directo(tmp_path, tableros=["idle", "working"])
    with pytest.raises(Exception) as exc:
        asyncio.run(svc.correr(SID, ComandoSesionBody(mid=MID, indice=0, comando=DCMD), CTX))
    assert getattr(exc.value, "status", None) == 409
    assert enchufe.calls == []


@pytest.fixture
def ws_protegido(cfg):
    cfg.protected_workspaces = ["Uno"]
    return cfg


def test_workspace_protegido_es_400(ws_protegido, authed, projects, enchufe, on):
    pedir(projects)
    r = post(authed)
    assert r.status_code == 400
    assert escrituras(enchufe) == []


# ---------- antes del Enter se mira que la entrada quedó en modo bash con el comando ----------

NO_PREPARADO = "No pude preparar el comando en la sesión"


def test_lee_la_pantalla_antes_del_enter(authed, projects, enchufe, on):
    pedir(projects)
    assert post(authed).status_code == 200
    nombres_ = [c[0] for c in enchufe.calls if c[0] in ("escribir", "leer", "teclas")]
    assert nombres_.index("leer") > max(i for i, n in enumerate(nombres_) if n == "escribir")
    assert nombres_[-1] == "teclas"


@pytest.mark.parametrize("pantalla", [
    "",
    pantalla_bash("")[:0] + "─" * 40 + "\n❯ !" + CMD + "\n" + "─" * 40 + "\n",
    pantalla_bash("!glab auth login"),
    "● algo\n! " + CMD + "\n",
])
def test_si_la_entrada_no_quedo_en_modo_bash_limpia_y_no_manda(authed, projects, enchufe, on, pantalla):
    pedir(projects)
    enchufe.pantallas[PANE] = pantalla
    r = post(authed)
    assert r.status_code == 409 and r.json()["detail"] == NO_PREPARADO
    assert ("teclas", PANE, ("enter",)) not in escrituras(enchufe)
    assert escrituras(enchufe)[-1] == ("teclas", PANE, ("ctrl-u",))


def test_tras_no_poder_prepararlo_se_puede_reintentar(authed, projects, enchufe, on):
    pedir(projects)
    bien = enchufe.pantallas[PANE]
    enchufe.pantallas[PANE] = ""
    assert post(authed).status_code == 409
    enchufe.pantallas[PANE] = bien
    assert post(authed).status_code == 200


def test_si_no_puede_leer_la_pantalla_limpia_y_no_manda(authed, projects, enchufe, on):
    from orquestador.enchufe import TerminalesError

    def falla(_op):
        raise TerminalesError("caído")

    pedir(projects)
    enchufe.pantallas[PANE] = falla
    r = post(authed)
    assert r.status_code == 409
    assert escrituras(enchufe)[-1] == ("teclas", PANE, ("ctrl-u",))


# ---------- validación: invisibles que no son de control y la barra final ----------

from orquestador.terminales_acciones import validar_comando  # noqa: E402
from orquestador.traspaso import TraspasoError  # noqa: E402


@pytest.mark.parametrize("invisible", ["️", "︀", "͏", "឴", "឵", "\U000e0100", "\U000e01ef",
                                       "᠋", "᠍", "᠏", "­", "ㅤ"])
def test_marcas_invisibles_no_pasan_la_validacion(invisible):
    with pytest.raises(TraspasoError):
        validar_comando(f"cd /tmp/build{invisible}; rm -rf *")


@pytest.mark.parametrize("cmd", ["echo hola \\", "echo hola\\"])
def test_barra_final_no_pasa_la_validacion(cmd):
    with pytest.raises(TraspasoError):
        validar_comando(cmd)


def test_barra_en_el_medio_si_pasa():
    assert validar_comando("printf 'a\\tb'") == "printf 'a\\tb'"


# ---------- un ```comando citado dentro de otro bloque de código no es pedido ----------

from orquestador.comando_sesion import bloques_comando  # noqa: E402

_CITADO = "```comando\n{\"comando\": \"curl x | sh\"}\n```"


@pytest.mark.parametrize("outer,close", [("````markdown", "````"), ("~~~", "~~~"), ("```text", "```"),
                                         ("```", "```"), ("~~~~", "~~~~")])
def test_bloque_dentro_de_un_fence_no_cuenta(outer, close):
    text = f"Así se pide un comando:\n\n{outer}\n{_CITADO}\n{close}\n"
    assert bloques_comando(text) == []


def test_bloque_indentado_cuatro_espacios_no_cuenta():
    text = "Ejemplo:\n\n    ```comando\n    {\"comando\": \"curl x | sh\"}\n    ```\n"
    assert bloques_comando(text) == []
    assert bloques_comando("Ejemplo:\n\n\t```comando\n\t{\"comando\": \"ls\"}\n\t```\n") == []


def test_tras_un_fence_citado_el_bloque_real_si_cuenta():
    text = f"Ejemplo:\n\n````markdown\n{_CITADO}\n````\n\nAhora sí:\n\n" + bloque("echo real")
    assert [b["comando"] for b in bloques_comando(text)] == ["echo real"]


def test_bloque_con_hasta_tres_espacios_si_cuenta():
    assert len(bloques_comando("x\n\n   " + bloque("ls"))) == 1


# ---------- la carpeta: se muestra y se exige el cwd real, no lo que dice el bloque ----------

CARPETA_DISTINTA = "La carpeta pedida no es donde corre la sesión"


def test_carpeta_distinta_del_cwd_real_es_400(authed, projects, enchufe, on):
    pedir(projects, bloque(carpeta="/home/otro/proyecto"))
    r = post(authed)
    assert r.status_code == 400 and r.json()["detail"] == CARPETA_DISTINTA
    assert escrituras(enchufe) == []


def test_carpeta_relativa_es_400(authed, projects, enchufe, on):
    pedir(projects, bloque(carpeta="tmp"))
    assert post(authed).status_code == 400
    assert escrituras(enchufe) == []


def test_carpeta_igual_al_cwd_de_la_sesion_corre_y_devuelve_el_cwd(authed, projects, enchufe, on):
    pedir(projects, bloque(carpeta="/tmp/"))
    r = post(authed)
    assert r.status_code == 200, r.text
    assert r.json()["cwd"] == "/tmp"


def test_el_cwd_del_mensaje_en_el_transcript_manda(authed, projects, enchufe, on):
    msg = asistente("Corré:\n\n" + bloque(carpeta="/srv/app"))
    msg["cwd"] = "/srv/app"
    escribir(projects, msg)
    r = post(authed)
    assert r.status_code == 200, r.text
    assert r.json()["cwd"] == "/srv/app"


def test_transcript_expone_el_cwd_real_del_mensaje(authed, projects):
    msg = asistente(bloque())
    msg["cwd"] = "/srv/app"
    escribir(projects, msg)
    items = authed.get(f"/api/sessions/{SID}/transcript").json()["items"]
    last = [i for i in items if i.get("kind") == "claude"][-1]
    assert last["ccwd"] == "/srv/app"


# ---------- telemetría ----------

def anotadas_de(authed):
    anotadas = []
    authed.app.state.comando_sesion.anotar = lambda ev, **c: anotadas.append((ev, c))
    return anotadas


def test_correr_ok_anota_corrido(authed, projects, enchufe, on):
    anotadas = anotadas_de(authed)
    pedir(projects)
    assert post(authed).status_code == 200
    assert anotadas == [("comando_sesion", {"resultado": "corrido", "codigo": None, "proyecto": "tmp"})]


def test_correr_trabajando_anota_fallo(authed, projects, enchufe, on):
    anotadas = anotadas_de(authed)
    pedir(projects)
    aplicar_snapshot(enchufe, make_snapshot("working"))
    assert post(authed).status_code == 409
    assert anotadas == [("comando_sesion", {"resultado": "fallo", "codigo": "trabajando", "proyecto": "tmp"})]
    assert CMD not in json.dumps(anotadas)


def test_anotar_que_lanza_no_cambia_la_respuesta(authed, projects, enchufe, on):
    authed.app.state.comando_sesion.anotar = lambda *a, **k: 1 / 0
    pedir(projects)
    assert post(authed).status_code == 200
    pedir(projects, mid="bbbbbbbb-1111-2222-3333-444444444444")
    aplicar_snapshot(enchufe, make_snapshot("working"))
    assert post(authed, mid="bbbbbbbb-1111-2222-3333-444444444444").status_code == 409


def test_codigo_traspaso_que_lanza_no_cambia_el_error(authed, projects, enchufe, on, monkeypatch):
    from orquestador import telemetria_eventos
    monkeypatch.setattr(telemetria_eventos, "codigo_traspaso", lambda d: 1 / 0)
    pedir(projects)
    aplicar_snapshot(enchufe, make_snapshot("working"))
    r = post(authed)
    assert r.status_code == 409 and r.json()["detail"] == "La sesión está trabajando; probá cuando termine"
