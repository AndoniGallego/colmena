"""Rendimiento de la sección de MRs: GitLab falso con latencia simulada; se cuentan pedidos y tiempo."""
import asyncio
import json
import time

import pytest

from orquestador.mrs import Gitlab, MrsService

from test_mrs import FakeGit, FakeGlab, _ajustes_mrs, mr, run

LAT = 0.1


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo7"
    path.mkdir()
    return path


class LentoGlab(FakeGlab):
    """FakeGlab con latencia por pedido y registro de cuántos corren a la vez."""

    def __init__(self, latencia=LAT):
        super().__init__()
        self.latencia = latencia
        self.activos = 0
        self.pico = 0

    async def __call__(self, args, stdin=None, cwd=None):
        self.activos += 1
        self.pico = max(self.pico, self.activos)
        try:
            await asyncio.sleep(self.latencia)
            return await super().__call__(args, stdin, cwd)
        finally:
            self.activos -= 1

    def gets(self):
        return [c["path"] for c in self.calls if c["method"] == "GET"]


class LentoGit(FakeGit):
    def __init__(self, repo, latencia=0.05):
        super().__init__(repo)
        self.latencia = latencia

    async def __call__(self, args, cwd=None):
        await asyncio.sleep(self.latencia)
        return await super().__call__(args, cwd)


def _svc(tmp_path, glab, repo, local=None):
    return MrsService(tmp_path, gitlab=Gitlab(runner=glab), local=local or FakeGit(repo), repos_fijos=lambda: [repo],
                      flow_bin="/fake/mi-flow.sh", ajustes=_ajustes_mrs())


def _timed(coro):
    t0 = time.perf_counter()
    run(coro)
    return time.perf_counter() - t0


def test_refresh_junta_los_pedidos_de_cada_mr_en_paralelo(tmp_path, repo):
    glab = LentoGlab()
    svc = _svc(tmp_path, glab, repo)
    # 2 MRs: serial eran 5 vueltas (2 listas + detalle, aprobaciones, hilos); en paralelo son 2.
    dt = _timed(svc.refresh())
    assert {i["ref"] for i in svc.items} == {"7:1", "8:2"}
    assert dt < 5 * LAT * 0.7, dt


def test_refresh_pide_las_dos_listas_a_la_vez(tmp_path, repo):
    glab = LentoGlab()
    glab.mine, glab.review = [], []
    svc = _svc(tmp_path, glab, repo)
    run(svc.refresh())
    assert glab.pico == 2
    assert sum(1 for p in glab.gets() if p.startswith("merge_requests?")) == 2


def test_refresh_con_muchos_mrs_respeta_el_tope_de_concurrencia(tmp_path, repo):
    glab = LentoGlab(latencia=0.02)
    glab.mine = [mr(7, i, branch=f"feature/{i}") for i in range(1, 9)]
    glab.review = []
    svc = _svc(tmp_path, glab, repo)
    run(svc.refresh())
    assert len(svc.items) == 8
    assert 2 <= glab.pico <= 8


def test_refresh_no_repite_hilos_si_no_cambiaron_las_notas(tmp_path, repo):
    glab = LentoGlab(latencia=0.01)
    svc = _svc(tmp_path, glab, repo)
    run(svc.refresh())
    antes = sum(1 for p in glab.gets() if p.endswith("/discussions?per_page=100"))
    run(svc.refresh())
    assert sum(1 for p in glab.gets() if p.endswith("/discussions?per_page=100")) == antes


def test_gets_iguales_en_vuelo_hacen_un_solo_pedido(tmp_path):
    glab = LentoGlab(latencia=0.05)
    gl = Gitlab(runner=glab)

    async def dos():
        return await asyncio.gather(gl.get("projects/7/merge_requests/1"), gl.get("projects/7/merge_requests/1"))

    a, b = run(dos())
    assert a == b and len(glab.calls) == 1


def test_get_en_vuelo_que_falla_propaga_a_todos_y_no_queda_pegado(tmp_path):
    glab = LentoGlab(latencia=0.01)
    glab.fail["projects/7/merge_requests/1"] = 404
    gl = Gitlab(runner=glab)

    async def dos():
        return await asyncio.gather(gl.get("projects/7/merge_requests/1"), gl.get("projects/7/merge_requests/1"),
                                    return_exceptions=True)

    res = run(dos())
    assert all(type(r).__name__ == "GitlabError" for r in res)
    glab.fail.clear()
    assert run(gl.get("projects/7/merge_requests/1"))["iid"] == 1


def test_detalle_pide_mr_hilos_diffs_y_jobs_a_la_vez(tmp_path, repo):
    glab = LentoGlab()
    svc = _svc(tmp_path, glab, repo)
    run(svc.refresh())
    glab.calls.clear()
    dt = _timed(svc.detalle(7, 1))
    # serial eran 4 vueltas; en paralelo, 1.
    assert dt < 2 * LAT, dt
    assert len(glab.gets()) == 4


def test_sesiones_resuelve_repos_de_los_agentes_en_paralelo(tmp_path, repo):
    glab = FakeGlab()
    git = LentoGit(repo, latencia=0.05)
    svc = _svc(tmp_path, glab, repo, local=git)
    run(svc.refresh())
    dirs = []
    for n in range(6):
        d = tmp_path / f"w{n}"
        d.mkdir()
        dirs.append(d)
    svc.board = lambda: {"workspaces": [{"workspace_id": "w1", "tabs": [{"tab_id": "t1", "agents": [
        {"session_id": f"s{n}", "cwd": str(d)} for n, d in enumerate(dirs)]}]}]}
    dt = _timed(svc.sesiones())
    # serial: 6 agentes x 3 git = 18 x 0.05 = 0.9 s; en paralelo ~3 vueltas.
    assert dt < 0.45, dt


def test_listado_no_vuelve_a_llamar_a_gitlab_con_la_cache_fresca(tmp_path, repo):
    glab = LentoGlab(latencia=0.01)
    svc = _svc(tmp_path, glab, repo)
    run(svc.refresh())
    n = len(glab.calls)
    run(svc.listado())
    run(svc.listado())
    assert len(glab.calls) == n
