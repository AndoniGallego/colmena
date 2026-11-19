import asyncio
import subprocess
from pathlib import Path

import pytest

from orquestador.cambios import CambiosService


def git(cwd: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(cwd), "PATH": "/usr/bin:/bin"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / "a.txt").write_text("uno\ndos\n")
    (r / "b.txt").write_text("fijo\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "base")
    return r


def test_no_es_repo(tmp_path):
    async def cuerpo():
        out = await CambiosService().cambios(str(tmp_path))
        assert out["repo"] is False and out["archivos"] == []
    asyncio.run(cuerpo())


def test_sin_cambios_en_la_base(repo):
    async def cuerpo():
        out = await CambiosService().cambios(str(repo))
        assert out["repo"] is True
        assert out["rama"] == "main" and out["base"] == "main"
        assert out["commits"] == [] and out["archivos"] == [] and out["sin_guardar"] == 0
    asyncio.run(cuerpo())


def test_rama_con_commit_y_sin_guardar(repo):
    async def cuerpo():
        git(repo, "checkout", "-qb", "feature/x")
        (repo / "a.txt").write_text("uno\ndos\ntres\n")
        git(repo, "commit", "-qam", "feat: tres")
        (repo / "b.txt").write_text("cambiado\n")
        (repo / "nuevo con espacio.txt").write_text("hola\nmundo\n")
        out = await CambiosService().cambios(str(repo))
        assert out["rama"] == "feature/x" and out["base"] == "main"
        assert [c["titulo"] for c in out["commits"]] == ["feat: tres"]
        assert out["commits_total"] == 1
        assert out["sin_guardar"] == 2
        por = {a["path"]: a for a in out["archivos"]}
        assert set(por) == {"a.txt", "b.txt", "nuevo con espacio.txt"}
        assert por["a.txt"]["estado"] == "M" and (por["a.txt"]["adds"], por["a.txt"]["dels"]) == (1, 0)
        assert "+tres" in por["a.txt"]["diff"] and por["a.txt"]["diff"].startswith("@@")
        assert por["b.txt"]["estado"] == "M" and (por["b.txt"]["adds"], por["b.txt"]["dels"]) == (1, 1)
        assert por["nuevo con espacio.txt"]["estado"] == "A"
        assert por["nuevo con espacio.txt"]["adds"] == 2
        assert "+hola" in por["nuevo con espacio.txt"]["diff"]
    asyncio.run(cuerpo())


def test_archivo_borrado_y_binario(repo):
    async def cuerpo():
        (repo / "b.txt").unlink()
        (repo / "bin.dat").write_bytes(b"\x00\x01\x02")
        out = await CambiosService().cambios(str(repo))
        por = {a["path"]: a for a in out["archivos"]}
        assert por["b.txt"]["estado"] == "D" and por["b.txt"]["dels"] == 1
        assert por["bin.dat"]["binario"] is True and por["bin.dat"]["diff"] == ""
    asyncio.run(cuerpo())


def test_tope_por_archivo_marca_truncado(repo):
    async def cuerpo():
        (repo / "grande.txt").write_text("x\n" * 5000)
        out = await CambiosService(max_archivo=500).cambios(str(repo))
        g = out["archivos"][0]
        assert g["truncado"] is True and len(g["diff"]) <= 500 and g["adds"] == 5000
        assert out["truncado"] is True
    asyncio.run(cuerpo())


def test_tope_total_deja_sin_diff_los_siguientes(repo):
    async def cuerpo():
        for i in range(3):
            (repo / f"f{i}.txt").write_text("linea\n" * 50)
        out = await CambiosService(max_archivo=400, max_total=500).cambios(str(repo))
        assert out["truncado"] is True
        assert any(a["diff"] == "" and a["truncado"] for a in out["archivos"])
    asyncio.run(cuerpo())


def test_tope_de_commits(repo):
    async def cuerpo():
        git(repo, "checkout", "-qb", "feature/y")
        for i in range(55):
            git(repo, "commit", "-q", "--allow-empty", "-m", f"c{i}")
        out = await CambiosService().cambios(str(repo))
        assert len(out["commits"]) == 50 and out["commits_total"] == 55
    asyncio.run(cuerpo())


def test_base_por_origin_head(repo, tmp_path):
    async def cuerpo():
        clon = tmp_path / "clon"
        git(tmp_path, "clone", "-q", str(repo), str(clon))
        git(clon, "checkout", "-qb", "feature/z")
        out = await CambiosService().cambios(str(clon))
        assert out["base"] == "main"
    asyncio.run(cuerpo())


def test_cache_corto_y_refrescar(repo):
    async def cuerpo():
        ahora = [100.0]
        svc = CambiosService(ttl=5, clock=lambda: ahora[0])
        primero = await svc.cambios(str(repo))
        (repo / "a.txt").write_text("otro\n")
        assert await svc.cambios(str(repo)) == primero
        assert (await svc.cambios(str(repo), refrescar=True))["sin_guardar"] == 1
        (repo / "a.txt").write_text("otro2\n")
        ahora[0] += 6
        assert (await svc.cambios(str(repo)))["archivos"][0]["adds"] == 1
    asyncio.run(cuerpo())
