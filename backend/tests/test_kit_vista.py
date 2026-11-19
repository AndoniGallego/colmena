import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, UNITS_FALSAS
from orquestador import kit_instalador as ki
from orquestador import kit_vista as kv
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.state import StateStore

REGLA = """# Estado de la sesión al cerrar

> Esta regla rige cuando la sesión corre en una terminal de Colmena (COLMENA_TERMINAL=1). Si no sabés, aplicala.

Ando sigue las sesiones desde la app. La tarjeta muestra en tres líneas en qué quedó.

Segundo párrafo que no va.
"""
SKILL = """---
name: diagramas
description: Formato del bloque diagrama que la app dibuja. Usar cuando Ando pide explicar algo.
---

Cuerpo de la skill.
"""
HOOK = """#!/bin/bash
# Hook Stop: pide el bloque estado al cerrar el turno.
# Segunda línea de detalle.
echo hola
"""
UNIT_PATH = "[Path]\nPathChanged=/x\n"
UNIT_SVC = "[Service]\nExecStart=/x\n"


@pytest.fixture
def mundo(tmp_path, units_en_config):
    kit = tmp_path / "kit"
    for rel, txt in {
        "reglas/colmena/estado-sesion.md": REGLA,
        "skills/diagramas/SKILL.md": SKILL,
        "ganchos/andokit-stop-bloques.sh": HOOK,
        "ganchos/lib-bloques.sh": "#!/bin/bash\n# Extractor de bloques que cargan los hooks.\n",
        "bin/kit-update-all": "#!/bin/bash\n# x\n",
        "statusline/andokit-statusline": "#!/bin/bash\n# x\n",
    }.items():
        p = kit / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
    (kit / "reglas" / "trabajo").mkdir(parents=True)
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    for u, t in zip(UNITS_FALSAS, (UNIT_PATH, UNIT_SVC)):
        (deploy / u).write_text(t, encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    env = {"ANDOKIT_NO_CONFIG_LOCAL": "1", "ANDOKIT_NO_RELOAD": "1", "ANDOKIT_REPO_VIEJO": str(tmp_path / "viejo")}
    d = ki.destinos(env, home, kit)
    return kit, deploy, home, env, d


def _instalar(kit, deploy, d):
    salida: list[str] = []
    rc = ki.instalar_kit(kit, deploy, d, "instalar", salida.append, lambda c: 0, datetime.now)
    assert rc == 0, salida


# --- chequeo estructurado ---


def test_chequear_vacio_lista_faltantes(mundo):
    kit, deploy, _, _, d = mundo
    rep = ki.chequear_kit(kit, deploy, d)
    assert rep.drift
    faltan = {(i["tipo"], i["nombre"]) for i in rep.items if i["estado"] == "falta"}
    assert ("regla", "estado-sesion.md") in faltan
    assert ("skill", "diagramas") in faltan
    assert ("hook", "andokit-stop-bloques.sh") in faltan
    assert ("unit", UNITS_FALSAS[0]) in faltan
    assert any(i["tipo"] == "settings" and i["nombre"] == "hooks" and i["estado"] == "falta" for i in rep.items)


def test_chequear_tras_instalar_todo_ok(mundo):
    kit, deploy, _, _, d = mundo
    _instalar(kit, deploy, d)
    rep = ki.chequear_kit(kit, deploy, d)
    assert not rep.drift
    assert all(i["estado"] in ("ok", "info") for i in rep.items)
    assert any(i["tipo"] == "regla" and i["estado"] == "ok" for i in rep.items)


def test_chequear_ajeno_sobra_y_distinta(mundo):
    kit, deploy, _, _, d = mundo
    _instalar(kit, deploy, d)
    (d.rules / "estado-sesion.md").unlink()
    (d.rules / "estado-sesion.md").write_text("mío", encoding="utf-8")
    os.symlink(kit / "reglas" / "colmena" / "vieja.md", d.rules / "vieja.md")
    (d.systemd / UNITS_FALSAS[1]).write_text("otra cosa", encoding="utf-8")
    rep = ki.chequear_kit(kit, deploy, d)
    est = {(i["tipo"], i["nombre"]): i["estado"] for i in rep.items}
    assert est[("regla", "estado-sesion.md")] == "ajeno"
    assert est[("regla", "vieja.md")] == "sobra"
    assert est[("unit", UNITS_FALSAS[1])] == "distinta"


# --- catálogo ---


def test_catalogo_reglas_proposito(mundo):
    kit, *_ = mundo
    reglas = kv.catalogo(kit)["reglas"]
    assert [r["id"] for r in reglas] == ["estado-sesion"]
    assert reglas[0]["proposito"] == "Ando sigue las sesiones desde la app."
    assert reglas[0]["titulo"] == "Estado de la sesión al cerrar"


def test_proposito_marcado_gana_al_primer_parrafo():
    md = "# T\n\n> banner\n\n<!-- propósito: Hace tal cosa. -->\n\nOtro texto.\n"
    assert kv.proposito_de(md) == "Hace tal cosa."
    assert kv.proposito_de("# T\n\n<!-- otro -->\n\nTexto real. Más.\n") == "Texto real."


def test_proposito_se_recorta():
    largo = "palabra " * 80
    assert len(kv.proposito_de(f"# T\n\n{largo}\n")) <= 160
    assert kv.proposito_de(f"# T\n\n{largo}\n").endswith("…")


def test_catalogo_skills_y_hooks(mundo):
    kit, *_ = mundo
    c = kv.catalogo(kit)
    assert c["skills"] == [
        {"id": "diagramas", "nombre": "diagramas", "que_hace": "Formato del bloque diagrama que la app dibuja."}
    ]
    hooks = {h["id"]: h for h in c["hooks"]}
    assert hooks["andokit-stop-bloques.sh"]["que_hace"] == "Hook Stop: pide el bloque estado al cerrar el turno."
    assert hooks["lib-bloques.sh"]["que_hace"] == "Extractor de bloques que cargan los hooks."


def test_texto_regla_valida_id(mundo):
    kit, *_ = mundo
    assert kv.texto_regla(kit, "estado-sesion") == REGLA
    for malo in ("../x", "estado-sesion/../../etc/passwd", "nada", ""):
        assert kv.texto_regla(kit, malo) is None


def test_kit_real_todas_con_proposito():
    c = kv.catalogo(ki.KIT_DIR)
    assert c["reglas"] and c["skills"] and c["hooks"]
    for r in c["reglas"]:
        md = (ki.KIT_DIR / "reglas" / "colmena" / f"{r['id']}.md").read_text(encoding="utf-8")
        assert "<!-- propósito:" in md, r["id"]
        assert r["proposito"].startswith(md.split("<!-- propósito:")[1].split("-->")[0].strip()[:20]), r
    for it in c["skills"] + c["hooks"]:
        assert it["que_hace"].strip(), it


# --- estado en lenguaje simple ---


def test_estado_al_dia(mundo):
    kit, deploy, _, _, d = mundo
    _instalar(kit, deploy, d)
    e = kv.estado(kit, deploy, d)
    assert e["al_dia"] is True and e["problemas"] == []


def test_estado_problemas_en_castellano(mundo):
    kit, deploy, _, _, d = mundo
    e = kv.estado(kit, deploy, d)
    assert e["al_dia"] is False
    assert any("regla" in p and "estado-sesion" in p for p in e["problemas"])
    assert all(isinstance(p, str) and p for p in e["problemas"])


# --- endpoints ---


@pytest.fixture
def kclient(cfg, tmp_path, handoffs, enchufe, mundo):
    kit, deploy, home, env, d = mundo
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    hub.self_pane_id = "w2:p9"
    app = create_app(
        cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests, dist=tmp_path / "nodist",
        handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads", enchufe=enchufe,
        kit_opts={"kit_dir": kit, "deploy_dir": deploy, "env": env, "home": home},
    )
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c, d


def test_endpoint_kit(kclient):
    c, _ = kclient
    r = c.get("/api/kit")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    j = r.json()
    assert j["estado"]["al_dia"] is False
    assert [x["id"] for x in j["reglas"]] == ["estado-sesion"]
    assert [x["id"] for x in j["skills"]] == ["diagramas"]


def test_endpoint_regla(kclient):
    c, _ = kclient
    assert c.get("/api/kit/regla/estado-sesion").json()["texto"] == REGLA
    assert c.get("/api/kit/regla/nada").status_code == 404
    assert c.get("/api/kit/regla/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_endpoint_arreglar(kclient):
    c, d = kclient
    r = c.post("/api/kit/arreglar")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True and j["estado"]["al_dia"] is True
    assert (d.rules / "estado-sesion.md").is_symlink()
    assert c.get("/api/kit").json()["estado"]["al_dia"] is True


def test_endpoint_arreglar_error_legible(kclient):
    c, d = kclient
    d.settings.parent.mkdir(parents=True)
    d.settings.write_text("{no es json", encoding="utf-8")
    r = c.post("/api/kit/arreglar")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is False and j["error"] and "Traceback" not in j["error"]


def test_endpoint_sin_sesion(client):
    assert client.get("/api/kit").status_code == 401
    assert client.post("/api/kit/arreglar").status_code in (401, 403)


def test_endpoint_arreglar_no_corre_dos_a_la_vez(kclient, monkeypatch):
    c, _ = kclient
    llamadas = []

    def arreglar_lento(*a, **k):
        # Mientras corre la primera, llega una segunda: se rechaza sin correr.
        llamadas.append(1)
        if len(llamadas) == 1:
            r2 = c.post("/api/kit/arreglar")
            assert r2.status_code == 409
            assert r2.json()["error"] == "Ya se está arreglando el kit: esperá a que termine."
        return True, ""

    monkeypatch.setattr(kv, "arreglar", arreglar_lento)
    r = c.post("/api/kit/arreglar")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert len(llamadas) == 1
    # Liberado el candado, se puede volver a correr.
    assert c.post("/api/kit/arreglar").status_code == 200


def test_correr_systemctl_tiene_timeout(monkeypatch):
    import subprocess

    vistos = {}

    def falso_run(cmd, **kw):
        vistos.update(kw)
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    monkeypatch.setattr(kv.subprocess, "run", falso_run)
    with pytest.raises(kv.SystemctlNoResponde):
        kv._correr_systemctl(["systemctl", "--user", "daemon-reload"])
    assert vistos.get("timeout") == kv.SYSTEMCTL_TIMEOUT


def test_arreglar_si_systemctl_no_responde_error_legible(mundo):
    kit, deploy, _, _, d = mundo

    import dataclasses

    def colgado(cmd):
        raise kv.SystemctlNoResponde(cmd)

    # Con recarga prendida (solo llama a `colgado`, nunca a systemctl real).
    ok, error = kv.arreglar(kit, deploy, dataclasses.replace(d, no_reload=False), colgado)
    assert ok is False and error == f"systemctl no respondió en {kv.SYSTEMCTL_TIMEOUT} s: probá de nuevo."
