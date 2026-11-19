import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from orquestador import mrs as mrs_mod
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.digest import DigestService
from orquestador.mrs import (Gitlab, GitlabError, MrsAjustes, MrsService, actividad_despausa, _notas_resumen,
                             proyecto_de_remote, rama_valida)
from orquestador.mrs_api import Redactor
from orquestador.state import StateStore
from orquestador.uso import UsoStore

from conftest import ORIGIN, PIN, make_snapshot
from orquestador.enchufe import FakeTerminales
from terminales_support import aplicar_snapshot

SHA = "a" * 40
YO = {"id": 40215469, "username": "ana.ejemplo", "name": "Ana"}
MATI = {"id": 41638306, "username": "lucia.perez", "name": "Lucía Pérez"}


def mr(pid, iid, author=YO, pipe_status="success", pipe_id=500, notes=0, branch="feature/x"):
    return {"id": pid * 1000 + iid, "iid": iid, "project_id": pid, "title": f"feat: cosa {iid}", "state": "opened",
            "source_branch": branch, "target_branch": "main", "author": author, "draft": False,
            "has_conflicts": False, "user_notes_count": notes, "sha": SHA, "updated_at": f"2026-11-0{iid}T10:00:00Z",
            "created_at": f"2026-10-0{iid}T09:00:00Z",
            "references": {"full": f"grupo/repo{pid}!{iid}"}, "web_url": f"https://gitlab.com/grupo/repo{pid}/-/merge_requests/{iid}",
            "reviewers": [], "head_pipeline": {"id": pipe_id, "status": pipe_status,
                                               "web_url": "https://gitlab.com/p/-/pipelines/1"},
            "user": {"can_merge": True}}


class FakeGlab:
    """Respuestas por (método, ruta sin query); registra cada llamada con su entorno."""

    def __init__(self):
        self.calls = []
        self.mine = [mr(7, 1)]
        self.review = [mr(8, 2, author=MATI, branch="feature/y")]
        self.approvals = {}
        self.discussions = {}
        self.jobs = [{"id": 900, "name": "test", "stage": "test", "status": "failed"}]
        self.branches = {"feature/x"}
        self.fail = {}

    def find(self, pid, iid):
        return next(m for m in self.mine + self.review if m["project_id"] == pid and m["iid"] == iid)

    async def __call__(self, args, stdin=None, cwd=None):
        method, path = args[args.index("-X") + 1], args[-1]
        self.calls.append({"args": args, "stdin": json.loads(stdin) if stdin else None, "method": method,
                           "path": path, "env_token": "GITLAB_TOKEN" in mrs_mod.glab_env()})
        base = path.split("?")[0]
        if base in self.fail:
            code = self.fail[base]
            return 1, b'{"message":"no"}', f"glab: {code} Not Found".encode()
        parts = base.split("/")
        if path.startswith("merge_requests?") and "created_by_me" in path:
            return 0, json.dumps(self.mine).encode(), b""
        if path.startswith("merge_requests?"):
            return 0, json.dumps(self.review).encode(), b""
        if method == "GET" and len(parts) == 4 and parts[2] == "merge_requests":
            return 0, json.dumps(self.find(int(parts[1]), int(parts[3]))).encode(), b""
        if method == "GET" and base.endswith("/approvals"):
            return 0, json.dumps(self.approvals.get(base, {"approved_by": [], "approvals_required": 1,
                                                           "approvals_left": 1})).encode(), b""
        if method == "GET" and base.endswith("/discussions"):
            return 0, json.dumps(self.discussions.get(base, [])).encode(), b""
        if method == "GET" and base.endswith("/diffs"):
            return 0, b'[{"new_path":"a.py","old_path":"a.py","diff":"@@ -1 +1 @@\\n-a\\n+b"}]', b""
        if method == "GET" and base.endswith("/jobs"):
            return 0, json.dumps(self.jobs).encode(), b""
        if method == "GET" and "/repository/branches/" in base:
            name = base.split("/repository/branches/")[1].replace("%2F", "/")
            return (0, b'{"name":"x"}', b"") if name in self.branches else (1, b'{"message":"404 Branch Not Found"}', b"glab: 404 Not Found")
        if method == "GET" and parts[0] == "projects" and len(parts) == 2:
            return 0, b'{"id": 7, "default_branch": "main"}', b""
        if method == "GET" and base.endswith("/merge_requests"):
            return 0, b"[]", b""
        if method == "POST" and base.endswith("/merge_requests"):
            pid = int(parts[1]) if len(parts) > 1 and parts[0] == "projects" else 7
            nuevo = mr(pid, 9)
            if not any(m["project_id"] == pid and m["iid"] == 9 for m in self.mine):
                self.mine.append(nuevo)
            return 0, json.dumps({"iid": 9, "web_url": nuevo["web_url"], "project_id": pid,
                                    "references": nuevo["references"]}).encode(), b""
        return 0, b"{}", b""

    def writes(self):
        return [c for c in self.calls if c["method"] != "GET"]


class FakeGit:
    def __init__(self, repo):
        self.repo = str(repo)
        self.calls = []

    async def __call__(self, args, cwd=None):
        self.calls.append(args)
        if args[0] != "git":
            return 0, json.dumps({"target": "develop"}).encode(), b""
        sub = args[1:]
        if sub[:2] == ["rev-parse", "--show-toplevel"]:
            return 0, (self.repo + "\n").encode(), b""
        if sub[:2] == ["remote", "get-url"]:
            return 0, b"git@gitlab.com:grupo/repo7.git\n", b""
        if sub[:2] == ["branch", "--show-current"]:
            return 0, b"feature/x\n", b""
        if sub[0] == "for-each-ref":
            return 0, b"feature/x\nmain\n", b""
        if sub[0] == "rev-parse":
            return 0, b"abc\n", b""
        if sub[0] == "log":
            return 0, b"- feat: algo\n", b""
        return 0, b"diff --git a/a b/a\n", b""


@pytest.fixture
def glab():
    return FakeGlab()


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo7"
    path.mkdir()
    return path


def _ajustes_mrs():
    return MrsAjustes(
        usuario="ana.ejemplo",
        usuario_id=40215469,
        equipo={
            "tomas.diaz": (41026438, "Tomás Díaz"),
            "valeria.gomez": (42391737, "Valeria Gómez"),
            "lucia.perez": (41638306, "Lucía Pérez"),
            "diego.ramos": (44118475, "Diego Ramos"),
            "camila.torres": (42466458, "Camila Torres"),
        },
    )


@pytest.fixture
def svc(tmp_path, glab, repo):
    return MrsService(tmp_path, gitlab=Gitlab(runner=glab), local=FakeGit(repo), repos_fijos=lambda: [repo],
                      flow_bin="/fake/mi-flow.sh", ajustes=_ajustes_mrs())


class FakeClaude:
    def __init__(self, result='{"titulo": "feat: algo", "descripcion": "Cambia algo."}', subtype="success"):
        self.calls = []
        self.result = result
        self.subtype = subtype

    async def __call__(self, args, stdin, cwd, env):
        self.calls.append((args, stdin.decode()))
        out = {"type": "result", "subtype": self.subtype, "is_error": self.subtype != "success", "result": self.result,
               "usage": {"input_tokens": 100, "output_tokens": 20}}
        return 0, json.dumps(out).encode(), b""


@pytest.fixture
def claude():
    return FakeClaude()


@pytest.fixture
def enchufe():
    return FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)


@pytest.fixture
def mclient(cfg, tmp_path, handoffs, svc, claude, enchufe):
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    hub.self_pane_id = "w2:p9"
    redactor = Redactor(cfg, UsoStore(tmp_path), tmp_path, tmp_path / "rc", runner=claude)
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads", mrs=svc,
                     redactor=redactor, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        c.redactor = redactor
        yield c


def run(coro):
    return asyncio.run(coro)


# ---------- validación ----------

@pytest.mark.parametrize("name", ["feature/x", "hotfix/1.2.3.4", "main", "feat_a-b.c"])
def test_ramas_validas(name):
    assert rama_valida(name)


@pytest.mark.parametrize("name", ["a;rm -rf", "a..b", "a b", "-x", "--upload-pack=x", "a/", "a.lock", "a//b",
                                  "a@{1}", "", "a\nb", "a$(x)", "../etc", None, 5, "x" * 201])
def test_ramas_invalidas(name):
    assert not rama_valida(name)


def test_remote_solo_gitlab_com():
    assert proyecto_de_remote("git@gitlab.com:mi-grupo/development/ps9.git") == "mi-grupo/development/ps9"
    assert proyecto_de_remote("https://gitlab.com/a/b.git") == "a/b"
    assert proyecto_de_remote("git@github.com:a/b.git") is None
    assert proyecto_de_remote("git@gitlab.com:a/../b.git") is None


def test_gitlab_rechaza_rutas_raras_sin_llamar(glab):
    gl = Gitlab(runner=glab)
    for path in ("projects/7/../../x", "projects/abc/merge_requests", "users", "projects/7/merge_requests;ls"):
        with pytest.raises(GitlabError):
            run(gl.get(path))
    with pytest.raises(GitlabError):
        run(gl.call("DELETE", "projects/7/merge_requests/1"))
    assert glab.calls == []


def test_glab_sin_gitlab_token_y_cuerpo_por_stdin(glab, monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-falso")
    assert "GITLAB_TOKEN" not in mrs_mod.glab_env()
    run(Gitlab(runner=glab).call("POST", "projects/7/merge_requests/1/notes", {"body": "@/etc/passwd"}))
    call = glab.calls[0]
    assert call["env_token"] is False
    assert "-F" not in call["args"] and "-f" not in call["args"]
    assert call["args"][call["args"].index("--input") + 1] == "-"
    assert call["stdin"] == {"body": "@/etc/passwd"}
    assert "--hostname" in call["args"]


def test_real_runner_sin_token(monkeypatch):
    seen = {}

    async def fake_exec(*args, **kwargs):
        seen.update(kwargs)
        raise FileNotFoundError

    monkeypatch.setenv("GITLAB_TOKEN", "glpat-falso")
    monkeypatch.setattr(mrs_mod.asyncio, "create_subprocess_exec", fake_exec)
    with pytest.raises(GitlabError):
        run(Gitlab(glab_bin="/nonexistent/glab").get("merge_requests?scope=all"))
    assert "GITLAB_TOKEN" not in seen["env"]


# ---------- lista y avisos ----------

def test_lista_arma_items(svc, glab):
    run(svc.refresh())
    refs = {i["ref"]: i for i in svc.items}
    assert set(refs) == {"7:1", "8:2"}
    assert refs["7:1"]["rol"] == "autor" and refs["8:2"]["rol"] == "revisor"
    assert refs["7:1"]["pipeline"]["estado"] == "ok"
    assert refs["7:1"]["repo"] == "grupo/repo7"
    assert glab.writes() == []


def test_avisos_siembra_y_despues_avisa(svc, glab):
    avisos = []

    async def avisar(titulo, cuerpo, ref):
        avisos.append((titulo, ref))

    svc.avisar = avisar
    run(svc.refresh())
    assert avisos == []

    glab.mine[0]["head_pipeline"]["status"] = "failed"
    glab.approvals["projects/7/merge_requests/1/approvals"] = {"approved_by": [{"user": MATI}], "approvals_left": 0}
    glab.mine[0]["user_notes_count"] = 1
    glab.discussions["projects/7/merge_requests/1/discussions"] = [
        {"id": "d1", "notes": [{"id": 50, "body": "ojo acá", "author": MATI, "resolvable": True, "resolved": False}]}]
    glab.review.append(mr(9, 3, author=MATI, branch="feature/z"))
    run(svc.refresh())
    titulos = [t for t, _ in avisos]
    assert "Falló el pipeline" in titulos
    assert "Lucía Pérez aprobó tu MR" in titulos
    assert "Lucía Pérez comentó en tu MR" in titulos
    assert "Lucía Pérez te pidió revisión" in titulos
    assert ("Lucía Pérez te pidió revisión", "9:3") in avisos

    avisos.clear()
    run(svc.refresh())
    assert avisos == []
    item = svc.item(7, 1)
    assert item["comentarios_nuevos"] == 1 and item["hilos_sin_resolver"] == 1


def test_estado_persistido_sobrevive_reinicio(tmp_path, svc, glab, repo):
    run(svc.refresh())
    otro = MrsService(tmp_path, gitlab=Gitlab(runner=glab), local=FakeGit(repo), ajustes=_ajustes_mrs())
    avisos = []

    async def avisar(titulo, cuerpo, ref):
        avisos.append(titulo)

    otro.avisar = avisar
    run(otro.refresh())
    assert avisos == []
    assert oct((tmp_path / "mrs-estado.json").stat().st_mode & 0o777) == "0o600"


def test_error_de_glab_no_borra_cache(svc, glab):
    run(svc.refresh())
    glab.fail["merge_requests"] = 500
    run(svc.refresh())
    assert len(svc.items) == 2 and svc.error


def test_timer_duerme_mas_sin_presencia(svc, monkeypatch):
    waits = []

    async def fake_wait_for(aw, timeout):
        waits.append(timeout)
        aw.close()
        raise asyncio.CancelledError

    monkeypatch.setattr(mrs_mod.asyncio, "wait_for", fake_wait_for)
    svc.presente = lambda: False
    with pytest.raises(asyncio.CancelledError):
        run(svc.run())
    svc.presente = lambda: True
    with pytest.raises(asyncio.CancelledError):
        run(svc.run())
    assert waits == [mrs_mod.INTERVALO_AUSENTE, mrs_mod.INTERVALO_PRESENTE]


# ---------- API ----------

def test_api_lista_y_sesiones(mclient, svc, repo, enchufe):
    snap = make_snapshot()
    snap["agents"][0]["cwd"] = str(repo)
    aplicar_snapshot(enchufe, snap)
    data = mclient.get("/api/mrs").json()
    assert [i["ref"] for i in data["items"]]
    assert "sesiones" in data


def test_api_requiere_sesion(client):
    assert client.get("/api/mrs").status_code == 401


def test_mergear_sin_pin_da_403_y_no_llama(mclient, glab):
    mclient.get("/api/mrs")
    for body in ({"sha": SHA}, {"pin": "", "sha": SHA}, {"pin": "00000000", "sha": SHA}):
        r = mclient.post("/api/mrs/7/1/mergear", json=body)
        assert r.status_code == 403
    for body in ({}, {"pin": "99999999"}):
        assert mclient.post("/api/mrs/7/1/cerrar", json=body).status_code == 403
    assert glab.writes() == []


def test_mergear_con_pin_valido(mclient, glab):
    mclient.get("/api/mrs")
    r = mclient.post("/api/mrs/7/1/mergear", json={"pin": PIN, "sha": SHA})
    assert r.status_code == 200
    w = glab.writes()
    assert w[0]["method"] == "PUT" and w[0]["path"] == "projects/7/merge_requests/1/merge"
    assert w[0]["stdin"] == {"sha": SHA}


def test_cerrar_con_pin_valido(mclient, glab):
    mclient.get("/api/mrs")
    assert mclient.post("/api/mrs/7/1/cerrar", json={"pin": PIN}).status_code == 200
    assert glab.writes()[0]["stdin"] == {"state_event": "close"}


def test_pin_bloquea_tras_muchos_intentos(mclient, glab):
    mclient.get("/api/mrs")
    codes = [mclient.post("/api/mrs/7/1/cerrar", json={"pin": "11111111"}).status_code for _ in range(12)]
    assert 429 in codes
    assert glab.writes() == []


def test_reviewers_fuera_de_lista(mclient, glab):
    mclient.get("/api/mrs")
    for bad in (["ana.ejemplo"], ["root"], ["tomas.diaz", "x"], "tomas.diaz", [1]):
        assert mclient.post("/api/mrs/7/1/reviewers", json={"reviewers": bad}).status_code == 422
    assert glab.writes() == []
    assert mclient.post("/api/mrs/7/1/reviewers", json={"reviewers": ["tomas.diaz", "valeria.gomez"]}).status_code == 200
    assert glab.writes()[0]["stdin"] == {"reviewer_ids": [41026438, 42391737]}


def test_acciones_solo_sobre_mrs_de_la_lista(mclient, glab):
    mclient.get("/api/mrs")
    assert mclient.post("/api/mrs/7/99/aprobar", json={"aprobar": True}).status_code == 404
    assert mclient.post("/api/mrs/abc/1/aprobar", json={"aprobar": True}).status_code == 422
    assert mclient.post("/api/mrs/7/1;ls/aprobar", json={"aprobar": True}).status_code in (404, 422)
    assert mclient.post("/api/mrs/-7/1/aprobar", json={"aprobar": True}).status_code == 422
    assert mclient.post("/api/mrs/8/2/cerrar", json={"pin": PIN}).status_code == 403
    assert glab.writes() == []


def test_aprobar_comentar_draft(mclient, glab):
    mclient.get("/api/mrs")
    assert mclient.post("/api/mrs/8/2/aprobar", json={"aprobar": True}).status_code == 200
    assert mclient.post("/api/mrs/8/2/aprobar", json={"aprobar": False}).status_code == 200
    assert mclient.post("/api/mrs/7/1/comentar", json={"texto": "dale"}).status_code == 200
    assert mclient.post("/api/mrs/7/1/comentar", json={"texto": ""}).status_code == 422
    assert mclient.post("/api/mrs/7/1/draft", json={"draft": True}).status_code == 200
    paths = [(c["method"], c["path"], c["stdin"]) for c in glab.writes()]
    assert paths[0][1] == "projects/8/merge_requests/2/approve"
    assert paths[1][1] == "projects/8/merge_requests/2/unapprove"
    assert paths[2][2] == {"body": "dale"}
    assert paths[3][2] == {"title": "Draft: feat: cosa 1"}


def test_draft_quita_prefijo():
    assert mrs_mod._titulo_draft("Draft: feat: x", False) == "feat: x"
    assert mrs_mod._titulo_draft("[Draft] feat: x", True) == "Draft: feat: x"


def test_reintentar_solo_del_pipeline_del_mr(mclient, glab):
    mclient.get("/api/mrs")
    assert mclient.post("/api/mrs/7/1/reintentar", json={"pipeline_id": 123}).status_code == 409
    assert mclient.post("/api/mrs/7/1/reintentar", json={"job_id": 1}).status_code == 409
    assert mclient.post("/api/mrs/7/1/reintentar", json={"job_id": "900"}).status_code == 422
    assert mclient.post("/api/mrs/7/1/reintentar", json={}).status_code == 422
    assert glab.writes() == []
    assert mclient.post("/api/mrs/7/1/reintentar", json={"job_id": 900}).status_code == 200
    assert mclient.post("/api/mrs/7/1/reintentar", json={"pipeline_id": 500}).status_code == 200
    assert [c["path"] for c in glab.writes()] == ["projects/7/jobs/900/retry", "projects/7/pipelines/500/retry"]


def test_detalle(mclient, glab):
    mclient.get("/api/mrs")
    data = mclient.get("/api/mrs/7/1").json()
    assert data["jobs"][0]["reintentable"] is True
    assert data["archivos"][0]["path"] == "a.py"
    assert data["actividad"] == []


def test_detalle_separa_notas_de_sistema(mclient, glab):
    glab.discussions["projects/7/merge_requests/1/discussions"] = [
        {"id": "d1", "notes": [{"id": 60, "body": "added 2 commits", "author": MATI, "system": True,
                                "created_at": "2026-11-01T10:00:00Z"}]},
        {"id": "d2", "notes": [{"id": 61, "body": "x" * 2000, "author": MATI, "system": True},
                               {"id": 62, "body": "**ojo** acá", "author": MATI}]},
    ]
    mclient.get("/api/mrs")
    data = mclient.get("/api/mrs/7/1").json()
    assert [h["id"] for h in data["hilos"]] == ["d2"]
    assert [n["id"] for n in data["hilos"][0]["notas"]] == [62]
    assert [a["id"] for a in data["actividad"]] == [60, 61]
    assert data["actividad"][0]["autor"]["username"] == MATI["username"]
    assert data["actividad"][0]["mio"] is False
    assert len(data["actividad"][1]["cuerpo"]) == mrs_mod.MAX_ACTIVIDAD_TEXTO


# ---------- crear ----------

def test_crear_opciones_y_rama(mclient, repo):
    data = mclient.get("/api/mrs/crear/opciones").json()
    assert data["repos"][0]["path"] == str(repo)
    assert {e["username"] for e in data["equipo"]} == set(_ajustes_mrs().equipo)
    info = mclient.get("/api/mrs/crear/rama", params={"repo": str(repo), "rama": "feature/x"}).json()
    assert info["pusheada"] is True and info["target"] == "develop"


def test_crear_rama_no_pusheada(mclient, glab, repo):
    body = {"repo": str(repo), "rama": "feature/local", "target": "main", "titulo": "feat: x", "reviewers": []}
    r = mclient.post("/api/mrs/crear", json=body)
    assert r.status_code == 409 and r.json()["detail"] == "La rama no está en GitLab, pusheala primero"
    assert glab.writes() == []


def test_crear_ok_con_assignee_y_reviewer(mclient, glab, repo):
    body = {"repo": str(repo), "rama": "feature/x", "target": "main", "titulo": "feat: x", "descripcion": "d",
            "reviewers": ["lucia.perez"]}
    r = mclient.post("/api/mrs/crear", json=body)
    assert r.status_code == 200, r.text
    sent = glab.writes()[0]["stdin"]
    assert sent["assignee_id"] == 40215469 and sent["reviewer_ids"] == [41638306]
    assert sent["source_branch"] == "feature/x"


@pytest.mark.parametrize("rama", ["feature/x; rm -rf ~", "a..b", "a b", "-x", "--exec=sh"])
def test_crear_inputs_maliciosos_no_llegan_a_glab(mclient, glab, repo, rama):
    body = {"repo": str(repo), "rama": rama, "target": "main", "titulo": "t", "reviewers": []}
    assert mclient.post("/api/mrs/crear", json=body).status_code == 422
    assert mclient.get("/api/mrs/crear/rama", params={"repo": str(repo), "rama": rama}).status_code == 422
    assert glab.calls == []


def test_crear_repo_fuera_de_lista(mclient, glab, tmp_path):
    body = {"repo": "/etc", "rama": "feature/x", "target": "main", "titulo": "t", "reviewers": []}
    assert mclient.post("/api/mrs/crear", json=body).status_code == 422
    body = {"repo": str(tmp_path / "repo7"), "rama": "feature/x", "target": "main", "titulo": "t",
            "reviewers": ["ana.ejemplo"]}
    assert mclient.post("/api/mrs/crear", json=body).status_code == 422
    assert glab.writes() == []


# ---------- redactar ----------

def test_redactar_con_presupuesto_y_uso(mclient, claude, repo, cfg):
    r = mclient.post("/api/mrs/crear/redactar", json={"repo": str(repo), "rama": "feature/x", "target": "main"})
    assert r.status_code == 200 and r.json()["titulo"] == "feat: algo"
    args, prompt = claude.calls[0]
    assert "--max-budget-usd" in args and "--tools" in args and args[args.index("--tools") + 1] == ""
    assert "diff --git" in prompt
    assert mclient.redactor.uso.day()["mrs"]["total"] == 120


def test_redactar_respeta_tope_diario(mclient, claude, repo):
    mclient.redactor.uso.add("mrs", {"input": 10**9})
    r = mclient.post("/api/mrs/crear/redactar", json={"repo": str(repo), "rama": "feature/x", "target": "main"})
    assert r.status_code == 429
    assert claude.calls == []


def test_aviso_mr_en_avisos_y_leidos(tmp_path):
    from orquestador.push import PushService
    push = PushService(tmp_path, sender=lambda *a: None)
    run(push.dispatch_mr("Falló el pipeline", "repo !1", "7:1"))
    entry = push.avisos.items[-1]
    assert entry["kind"] == "mr" and entry["mr"] == "7:1"
    assert push.avisos.mark_where(mr="7:1") == 0


# ---------- pausa ----------

def test_item_trae_creado(svc, glab):
    run(svc.refresh())
    assert svc.item(7, 1)["creado"] == "2026-10-01T09:00:00Z"


def test_pausa_persiste_y_sobrevive_reinicio(tmp_path, svc, glab, repo):
    run(svc.refresh())
    n_antes = len(glab.calls)
    run(svc.pausar(7, 1, True))
    assert svc.item(7, 1)["pausado"] is True
    assert svc.estado["pausas"]["7:1"]["firma"] == svc.item(7, 1)["firma"]
    otro = MrsService(tmp_path, gitlab=Gitlab(runner=glab), local=FakeGit(repo), ajustes=_ajustes_mrs())
    run(otro.refresh())
    assert otro.item(7, 1)["pausado"] is True
    for c in glab.calls[n_antes:]:
        assert c["method"] == "GET"


def test_pausa_se_va_sola_con_commit_nuevo(svc, glab):
    run(svc.refresh())
    run(svc.pausar(7, 1, True))
    glab.mine[0]["sha"] = "b" * 40
    run(svc.refresh())
    assert svc.item(7, 1)["pausado"] is False
    assert "7:1" not in svc.estado["pausas"]


def test_pausa_se_va_sola_con_comentario_de_otro(svc, glab):
    run(svc.refresh())
    run(svc.pausar(7, 1, True))
    glab.discussions["projects/7/merge_requests/1/discussions"] = [
        {"id": "d1", "notes": [{"id": 99, "body": "mirá esto", "author": MATI}]},
    ]
    glab.mine[0]["user_notes_count"] = 1
    run(svc.refresh())
    assert svc.item(7, 1)["pausado"] is False

    run(svc.pausar(7, 1, True))
    glab.discussions["projects/7/merge_requests/1/discussions"] = [
        {"id": "d1", "notes": [{"id": 99, "body": "mirá esto", "author": MATI}]},
        {"id": "d2", "notes": [{"id": 100, "body": "yo digo", "author": YO}]},
    ]
    glab.mine[0]["user_notes_count"] = 2
    run(svc.refresh())
    assert svc.item(7, 1)["pausado"] is True


def test_pausa_se_va_sola_con_reviewer_nuevo(svc, glab):
    run(svc.refresh())
    run(svc.pausar(7, 1, True))
    glab.mine[0]["reviewers"] = [MATI]
    run(svc.refresh())
    assert svc.item(7, 1)["pausado"] is False


def test_pausa_sin_actividad_sigue(svc, glab):
    run(svc.refresh())
    run(svc.pausar(7, 1, True))
    run(svc.refresh())
    run(svc.refresh())
    assert svc.item(7, 1)["pausado"] is True


def test_pausa_se_limpia_si_el_mr_se_cierra(svc, glab):
    run(svc.refresh())
    run(svc.pausar(7, 1, True))
    glab.mine.clear()
    run(svc.refresh())
    assert "7:1" not in svc.estado["pausas"]


def test_pausa_sobrevive_fallo_al_armar_mr(svc, glab):
    run(svc.refresh())
    run(svc.pausar(7, 1, True))
    svc.estado["visto"]["7:1"] = 42
    svc.estado["avisado_nota"]["7:1"] = 42
    glab.fail["projects/7/merge_requests/1/approvals"] = 502
    run(svc.refresh())
    assert svc.estado["pausas"]["7:1"]["firma"]
    assert svc.estado["visto"]["7:1"] == 42
    assert svc.estado["avisado_nota"]["7:1"] == 42
    assert svc.item(7, 1) is None


def test_pausa_no_se_va_con_nota_de_bot(svc, glab):
    run(svc.refresh())
    run(svc.pausar(7, 1, True))
    bot = {"id": 2, "username": "project_7_bot", "name": "Bot", "bot": True}
    glab.discussions["projects/7/merge_requests/1/discussions"] = [
        {"id": "d1", "notes": [{"id": 200, "body": "auto", "author": bot}]},
    ]
    glab.mine[0]["user_notes_count"] = 1
    run(svc.refresh())
    assert svc.item(7, 1)["pausado"] is True


def test_pausa_no_se_va_si_borran_nota(svc, glab):
    run(svc.refresh())
    glab.discussions["projects/7/merge_requests/1/discussions"] = [
        {"id": "d1", "notes": [{"id": 99, "body": "mirá esto", "author": MATI}]},
    ]
    glab.mine[0]["user_notes_count"] = 1
    run(svc.refresh())
    run(svc.pausar(7, 1, True))
    glab.discussions["projects/7/merge_requests/1/discussions"] = []
    glab.mine[0]["user_notes_count"] = 0
    run(svc.refresh())
    assert svc.item(7, 1)["pausado"] is True


def test_actividad_despausa_firma_vieja(svc, glab):
    guardada = f"{SHA}|99|"
    actual = f"{SHA}|50|"
    assert actividad_despausa(guardada, actual, [{"id": 50}]) is False
    assert actividad_despausa(guardada, actual, [{"id": 100}]) is True
    assert actividad_despausa(guardada, f"{'b' * 40}|99|", [{"id": 50}]) is True


def test_notas_resumen_ignora_bots():
    bot = {"id": 1, "username": "group_1_bot_x", "name": "B", "bot": True}
    out = _notas_resumen([{"notes": [{"id": 5, "body": "x", "author": bot}]}], YO["username"])
    assert out["otros"] == []


def test_api_pausa(mclient, glab, svc):
    mclient.get("/api/mrs")
    r = mclient.post("/api/mrs/7/1/pausa", json={"pausar": True})
    assert r.status_code == 200 and r.json() == {"pausado": True}
    lista = mclient.get("/api/mrs").json()
    assert next(i for i in lista["items"] if i["ref"] == "7:1")["pausado"] is True
    assert mclient.post("/api/mrs/7/1/pausa", json={"pausar": False}).json() == {"pausado": False}
    assert mclient.post("/api/mrs/7/99/pausa", json={"pausar": True}).status_code == 404
    assert mclient.post("/api/mrs/7/1/pausa", json={"pausar": "si"}).status_code == 422
    assert glab.writes() == []


@pytest.fixture
def mclient_sin_mrs(cfg, tmp_path, handoffs, glab, repo, claude, enchufe):
    svc = MrsService(tmp_path, gitlab=Gitlab(runner=glab), local=FakeGit(repo), ajustes=None)
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    redactor = Redactor(cfg, UsoStore(tmp_path), tmp_path, tmp_path / "rc", runner=claude)
    app = create_app(cfg, b"secret", StateStore(tmp_path), hub=hub, digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads", mrs=svc,
                     redactor=redactor, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def test_api_mrs_apagados_no_llama_gitlab(mclient_sin_mrs, glab):
    lista = mclient_sin_mrs.get("/api/mrs")
    assert lista.status_code == 200
    assert lista.json()["habilitado"] is False
    calls_antes = len(glab.calls)
    assert mclient_sin_mrs.get("/api/mrs/crear/opciones").status_code == 503
    assert mclient_sin_mrs.get("/api/mrs/7/1").status_code == 503
    assert mclient_sin_mrs.post("/api/mrs/crear/redactar", json={"repo": "/r", "rama": "feature/x", "target": "main"}).status_code == 503
    assert len(glab.calls) == calls_antes


# ---------- sesiones / dueño MR ----------

SID_A = "sess-a"
SID_B = "sess-b"


def _board_dos_sesiones(repo, sid_a=SID_A, sid_b=SID_B):
    return {
        "workspaces": [
            {
                "workspace_id": "w1",
                "tabs": [
                    {
                        "tab_id": "t1",
                        "agents": [
                            {"session_id": sid_a, "cwd": str(repo)},
                            {"session_id": sid_b, "cwd": str(repo)},
                        ],
                    }
                ],
            }
        ],
    }


def _write_glab_mr_transcript(path, *, glab_create=True, url="https://gitlab.com/grupo/repo7/-/merge_requests/41", cmd=None):
    cmd = cmd or ("glab mr create --title x" if glab_create else "git status")
    lines = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "tu1", "name": "Bash", "input": {"command": cmd}},
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu1", "content": url},
                ]
            },
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    return path


def test_sesiones_mr_solo_en_creador(svc, repo, glab):
    run(svc.refresh())
    svc.board = lambda: _board_dos_sesiones(repo)
    svc.estado["creados"]["7:1"] = SID_A
    out = run(svc.sesiones())
    assert out.get(SID_A) == "7:1"
    assert SID_B not in out


def test_sesiones_misma_rama_sin_dueno_ambas(svc, repo, glab):
    run(svc.refresh())
    svc.board = lambda: _board_dos_sesiones(repo)
    out = run(svc.sesiones())
    assert out.get(SID_A) == "7:1"
    assert out.get(SID_B) == "7:1"


def test_sesiones_dueno_fuera_fallback(svc, repo, glab):
    run(svc.refresh())
    svc.board = lambda: _board_dos_sesiones(repo)
    svc.estado["creados"]["7:1"] = "sesion-ausente"
    out = run(svc.sesiones())
    assert out.get(SID_A) == "7:1"
    assert out.get(SID_B) == "7:1"


def test_crear_registra_dueno(svc, repo, glab):
    run(svc.refresh())
    out = run(svc.crear(str(repo), "feature/x", "main", "feat: x", "", [], session_id=SID_A))
    assert out["ref"] == "7:9"
    assert svc.estado["creados"]["7:9"] == SID_A


def test_crear_api_session_id_registra_dueno(mclient, svc, repo, glab):
    body = {"repo": str(repo), "rama": "feature/x", "target": "main", "titulo": "feat: x", "descripcion": "",
            "reviewers": [], "session_id": SID_A}
    assert mclient.post("/api/mrs/crear", json=body).status_code == 200
    assert svc.estado["creados"]["7:9"] == SID_A


def test_estado_viejo_sin_creados(tmp_path, glab, repo):
    (tmp_path / "mrs-estado.json").write_text('{"sembrado": true, "pausas": {}}', encoding="utf-8")
    svc = MrsService(tmp_path, gitlab=Gitlab(runner=glab), local=FakeGit(repo), repos_fijos=lambda: [repo],
                     flow_bin="/fake/mi-flow.sh", ajustes=_ajustes_mrs())
    assert svc.estado["creados"] == {}


def _svc_con_estado(tmp_path, glab, repo, estado):
    (tmp_path / "mrs-estado.json").write_text(json.dumps(estado), encoding="utf-8")
    return MrsService(tmp_path, gitlab=Gitlab(runner=glab), local=FakeGit(repo), repos_fijos=lambda: [repo],
                      flow_bin="/fake/mi-flow.sh", ajustes=_ajustes_mrs())


def test_estado_sin_creados_v_descarta_creados_y_conserva_el_resto(tmp_path, glab, repo):
    svc = _svc_con_estado(tmp_path, glab, repo, {"sembrado": True, "creados": {"7:1": SID_A},
                                                  "aprobadores": {"7:1": ["ana"]}})
    assert svc.estado["creados"] == {}
    assert svc.estado["aprobadores"] == {"7:1": ["ana"]}
    assert svc.estado["sembrado"] is True
    svc._save()
    assert json.loads((tmp_path / "mrs-estado.json").read_text())["creados_v"] == 2


def test_estado_con_creados_v_2_conserva_creados(tmp_path, glab, repo):
    svc = _svc_con_estado(tmp_path, glab, repo, {"sembrado": True, "creados_v": 2, "creados": {"7:1": SID_A}})
    assert svc.estado["creados"] == {"7:1": SID_A}


def test_sesion_que_solo_busco_glab_mr_create_no_se_asocia(svc, repo, glab, tmp_path):
    glab.mine = [mr(7, 41)]
    run(svc.refresh())
    path = tmp_path / "t" / f"{SID_A}.jsonl"
    _write_glab_mr_transcript(path, cmd='grep -c "glab mr create" f.jsonl; grep -oE "merge_requests/[0-9]+" f.jsonl')
    svc.find_transcript = lambda sid: path if sid == SID_A else None
    svc.board = lambda: _board_dos_sesiones(repo, sid_a=SID_A, sid_b=SID_B)
    run(svc.sesiones())
    assert "7:41" not in svc.estado["creados"]


def test_transcript_glab_mr_registra_dueno(svc, repo, glab, tmp_path):
    glab.mine = [mr(7, 41)]
    run(svc.refresh())
    path = tmp_path / "t" / f"{SID_A}.jsonl"
    _write_glab_mr_transcript(path)
    svc.find_transcript = lambda sid: path if sid == SID_A else None
    svc.board = lambda: _board_dos_sesiones(repo, sid_a=SID_A, sid_b=SID_B)
    out = run(svc.sesiones())
    assert svc.estado["creados"].get("7:41") == SID_A
    assert out.get(SID_A) == "7:41"
    assert SID_B not in out


def test_transcript_sin_glab_mr_create_no_registra(svc, repo, glab, tmp_path):
    glab.mine = [mr(7, 41)]
    run(svc.refresh())
    path = tmp_path / "t" / f"{SID_A}.jsonl"
    _write_glab_mr_transcript(path, glab_create=False)
    svc.find_transcript = lambda sid: path if sid == SID_A else None
    svc.board = lambda: _board_dos_sesiones(repo)
    run(svc.sesiones())
    assert "7:41" not in svc.estado["creados"]


# ---------- redactor: modelo y topes propios que heredan los de Centinela ----------

def test_mrs_hereda_del_ajuste_viejo_incluido_sin_tope(tmp_path, cfg):
    (tmp_path / "dios-ajustes.json").write_text('{"modelo": "opus", "tope_diario_tokens": 0}')
    r = Redactor(cfg, UsoStore(tmp_path), tmp_path, tmp_path / "rc")
    assert r.modelo() == "opus" and r.tope_diario() == 0


def test_mrs_propio_gana(tmp_path, cfg):
    cfg.mrs_modelo, cfg.mrs_tope_diario_tokens = "sonnet", 5000
    (tmp_path / "dios-ajustes.json").write_text('{"modelo": "opus", "tope_diario_tokens": 0}')
    r = Redactor(cfg, UsoStore(tmp_path), tmp_path, tmp_path / "rc")
    assert r.modelo() == "sonnet" and r.tope_diario() == 5000


def test_mrs_sin_json_usa_config_vieja(tmp_path, cfg):
    cfg.dios_modelo = "haiku"
    cfg.dios_tope_mensaje_usd = 3.0
    r = Redactor(cfg, UsoStore(tmp_path), None, tmp_path / "rc")
    assert r.tope_mensaje_usd() == 3.0 and r.tope_diario() == cfg.dios_tope_diario_tokens
    cfg.dios_modelo = "opus"
    assert r.modelo() == "opus"


def test_mrs_json_ilegible_es_ausente(tmp_path, cfg):
    (tmp_path / "dios-ajustes.json").write_text("{no es json")
    r = Redactor(cfg, UsoStore(tmp_path), tmp_path, tmp_path / "rc")
    assert r.tope_diario() == cfg.dios_tope_diario_tokens


@pytest.mark.parametrize("raro", ["5000", "abc", None, 1.5, True, [3]])
def test_mrs_tope_diario_no_int_cae_al_heredado(tmp_path, cfg, raro):
    cfg.mrs_tope_diario_tokens = raro
    r = Redactor(cfg, UsoStore(tmp_path), None, tmp_path / "rc")
    assert r.tope_diario() == cfg.dios_tope_diario_tokens
    cfg.dios_tope_diario_tokens = raro
    assert r.tope_diario() == 0


def test_redactar_con_tope_no_int_no_da_500(mclient, claude, repo):
    mclient.redactor.cfg.mrs_tope_diario_tokens = "abc"
    r = mclient.post("/api/mrs/crear/redactar", json={"repo": str(repo), "rama": "feature/x", "target": "main"})
    assert r.status_code != 500


def test_mrs_tope_mensaje_propio_gana(tmp_path, cfg):
    cfg.mrs_tope_mensaje_usd = 0.5
    r = Redactor(cfg, UsoStore(tmp_path), tmp_path, tmp_path / "rc")
    assert r.tope_mensaje_usd() == 0.5


def test_mrs_api_no_importa_chat():
    from pathlib import Path

    from orquestador import mrs_api
    assert "from .chat" not in Path(mrs_api.__file__).read_text()


# ---------- sesiones: MR de otra rama asociado a la sesión creadora ----------

class FakeGitPorCwd(FakeGit):
    """Como FakeGit pero la rama depende del nombre del cwd (main/feature) y 'sinrepo' no es un repo."""

    async def __call__(self, args, cwd=None):
        sub = args[1:]
        if args[0] == "git" and str(cwd).endswith("sinrepo"):
            return 1, b"", b"fatal: not a git repository"
        if args[0] == "git" and sub[:2] == ["rev-parse", "--show-toplevel"]:
            return 0, (str(cwd) + "\n").encode(), b""
        if args[0] == "git" and sub[:2] == ["branch", "--show-current"]:
            self.calls.append(args)
            return 0, (b"main\n" if str(cwd).endswith("enmain") else b"feature/x\n"), b""
        return await super().__call__(args, cwd=cwd)


def _board_cwds(**sid_cwd):
    return {"workspaces": [{"workspace_id": "w1", "tabs": [{"tab_id": "t1", "agents": [
        {"session_id": sid, "cwd": str(cwd)} for sid, cwd in sid_cwd.items()]}]}]}


@pytest.fixture
def svc_cwd(tmp_path, glab, repo):
    glab.mine = [mr(7, 1, branch="feature/x"), mr(7, 3, branch="feature/z")]
    glab.review = []
    s = MrsService(tmp_path, gitlab=Gitlab(runner=glab), local=FakeGitPorCwd(repo), repos_fijos=lambda: [repo],
                   flow_bin="/fake/mi-flow.sh", ajustes=_ajustes_mrs())
    run(s.refresh())
    return s


def _dir(tmp_path, nombre):
    d = tmp_path / nombre
    d.mkdir(exist_ok=True)
    return d


def test_creador_en_main_recibe_su_mr_de_otra_rama(svc_cwd, tmp_path):
    svc_cwd.board = lambda: _board_cwds(**{SID_A: _dir(tmp_path, "enmain")})
    svc_cwd.estado["creados"]["7:3"] = SID_A
    assert run(svc_cwd.sesiones()) == {SID_A: "7:3"}


def test_creador_con_varios_mr_del_mismo_proyecto_gana_mayor_iid(svc_cwd, tmp_path):
    svc_cwd.board = lambda: _board_cwds(**{SID_A: _dir(tmp_path, "enmain")})
    svc_cwd.estado["creados"].update({"7:1": SID_A, "7:3": SID_A})
    assert run(svc_cwd.sesiones()) == {SID_A: "7:3"}


def test_creador_con_mr_de_distintos_proyectos_gana_el_mas_reciente(svc_cwd, glab, tmp_path):
    glab.mine = [mr(7, 1, branch="feature/x"), mr(8, 2, branch="feature/w")]
    run(svc_cwd.refresh())
    svc_cwd.board = lambda: _board_cwds(**{SID_A: _dir(tmp_path, "enmain")})
    svc_cwd.estado["creados"].update({"7:1": SID_A, "8:2": SID_A})
    # updated_at: 7:1 -> 2026-11-01, 8:2 -> 2026-11-02
    assert run(svc_cwd.sesiones()) == {SID_A: "8:2"}


def test_creador_que_coincide_por_rama_conserva_el_de_rama(svc_cwd, tmp_path):
    svc_cwd.board = lambda: _board_cwds(**{SID_A: _dir(tmp_path, "enfeature")})
    svc_cwd.estado["creados"].update({"7:1": SID_A, "7:3": SID_A})
    assert run(svc_cwd.sesiones()) == {SID_A: "7:1"}


def test_otra_sesion_por_rama_no_se_lleva_el_mr_de_un_creador_presente(svc_cwd, tmp_path):
    svc_cwd.board = lambda: _board_cwds(**{SID_A: _dir(tmp_path, "enmain"), SID_B: _dir(tmp_path, "enfeature")})
    svc_cwd.estado["creados"]["7:1"] = SID_A
    out = run(svc_cwd.sesiones())
    assert out.get(SID_A) == "7:1"
    assert SID_B not in out


def test_creador_con_cwd_sin_repo_recibe_su_mr(svc_cwd, tmp_path):
    svc_cwd.board = lambda: _board_cwds(**{SID_A: _dir(tmp_path, "sinrepo")})
    svc_cwd.estado["creados"]["7:3"] = SID_A
    assert run(svc_cwd.sesiones()) == {SID_A: "7:3"}


def test_creador_ausente_del_tablero_no_asocia_a_nadie_mas(svc_cwd, tmp_path):
    svc_cwd.board = lambda: _board_cwds(**{SID_B: _dir(tmp_path, "enmain")})
    svc_cwd.estado["creados"]["7:3"] = SID_A
    assert run(svc_cwd.sesiones()) == {}


def test_ref_viejo_en_creados_que_ya_no_esta_en_items_no_se_asocia(svc_cwd, tmp_path):
    svc_cwd.board = lambda: _board_cwds(**{SID_A: _dir(tmp_path, "enmain")})
    svc_cwd.estado["creados"]["7:99"] = SID_A
    assert run(svc_cwd.sesiones()) == {}
    svc_cwd.estado["creados"]["7:3"] = SID_A
    assert run(svc_cwd.sesiones()) == {SID_A: "7:3"}
