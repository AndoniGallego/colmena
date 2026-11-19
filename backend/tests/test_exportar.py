"""Exportar copia limpia de Colmena: git archive, repo nuevo, revisión de datos personales."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from orquestador.exportar import (
    DatosRevision,
    ExportarCtx,
    buscar_datos_personales,
    ejecutar_exportar,
    terminos_revision,
    terminos_desde_config,
    _quitar_docs_internos,
    _terminos_desde_maquina,
    validar_destino,
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        check=True,
    )


def _repo_minimo(tmp_path: Path) -> Path:
    repo = tmp_path / "origen"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / ".gitignore").write_text("data/\n")
    (repo / "versionado.txt").write_text("solo en git\n")
    (repo / "sin_commit.txt").write_text("no debería ir\n")
    repo.mkdir(exist_ok=True)
    data = repo / "data"
    data.mkdir()
    (data / "secreto.txt").write_text("local\n")
    _git(repo, "add", ".gitignore", "versionado.txt")
    _git(repo, "commit", "-m", "init")
    return repo


class CtxReal(ExportarCtx):
    def __init__(
        self,
        repo_root: Path,
        *,
        home: Path | None = None,
        revision: DatosRevision | None = None,
        git_email: str | None = None,
    ):
        self.repo_root = repo_root
        self._home = home or Path("/home/usuario-test")
        self._revision = revision
        self._git_email = git_email
        self.impresiones: list[str] = []

    def home_path(self) -> Path:
        return self._home

    def datos_revision(self) -> DatosRevision:
        if self._revision is not None:
            return self._revision
        return terminos_revision(
            nombre="",
            app_origin="",
            viewer_origin="",
            home=self._home,
            git_user_email=self._git_email or "",
        )

    def imprimir(self, linea: str) -> None:
        self.impresiones.append(linea)

    def correr(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            cmd,
            cwd=cwd or self.repo_root,
            env=merged,
            capture_output=True,
            input=input_bytes,
            check=False,
        )


def test_exporta_solo_commiteado(tmp_path):
    repo = _repo_minimo(tmp_path)
    dest = tmp_path / "export"
    ctx = CtxReal(repo)
    assert ejecutar_exportar(ctx, str(dest)) == 0
    assert (dest / "versionado.txt").is_file()
    assert not (dest / "sin_commit.txt").exists()
    assert not (dest / "data").exists()


def test_copia_un_solo_commit_colmena(tmp_path):
    repo = _repo_minimo(tmp_path)
    dest = tmp_path / "export"
    ctx = CtxReal(repo)
    assert ejecutar_exportar(ctx, str(dest)) == 0
    log = subprocess.run(
        ["git", "log", "--format=%an <%ae>", "-1"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.strip() == "Colmena <colmena@example.com>"
    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=True,
    )
    assert count.stdout.strip() == "1"


def test_destino_existente_error_sin_tocar(tmp_path):
    repo = _repo_minimo(tmp_path)
    dest = tmp_path / "export"
    dest.mkdir()
    marcador = dest / "quedo"
    marcador.write_text("x")
    ctx = CtxReal(repo)
    assert ejecutar_exportar(ctx, str(dest)) == 1
    assert marcador.read_text() == "x"
    assert any("Ya existe" in l for l in ctx.impresiones)


def test_destino_dentro_del_repo_error(tmp_path):
    repo = _repo_minimo(tmp_path)
    dest = repo / "sub" / "export"
    ctx = CtxReal(repo)
    assert ejecutar_exportar(ctx, str(dest)) == 1
    assert not dest.exists()


def test_reporte_datos_personales_sin_contenido_linea(tmp_path):
    repo = _repo_minimo(tmp_path)
    nombre = "Fulano"
    host = "mi.maquina.ts.net"
    home = "/home/fulano"
    (repo / "leak.txt").write_text(f"Hola {nombre} en {host} y {home}\n")
    _git(repo, "add", "leak.txt")
    _git(repo, "commit", "-m", "leak")
    bin_path = repo / "blob.bin"
    bin_path.write_bytes(b"\x00" + nombre.encode())
    _git(repo, "add", "blob.bin")
    _git(repo, "commit", "-m", "bin")
    dest = tmp_path / "export"
    rev = terminos_revision(
        nombre=nombre,
        app_origin=f"https://{host}:8444",
        viewer_origin="",
        home=home,
        git_user_email="fulano@mail.com",
    )
    ctx = CtxReal(repo, home=Path(home), revision=rev)
    assert ejecutar_exportar(ctx, str(dest), permitir_hallazgos=True) == 0
    texto = "\n".join(ctx.impresiones)
    assert "Ojo:" in texto
    assert "leak.txt:" in texto
    assert nombre in texto or host in texto
    assert "Hola" not in texto
    assert "blob.bin: Fulano (binario)" in texto


def test_buscar_datos_personales_inyectable(tmp_path):
    root = tmp_path / "copia"
    root.mkdir()
    (root / "a.txt").write_text("linea con Fulano acá\n")
    hits = buscar_datos_personales(root, ["Fulano"], nombre="Fulano")
    assert hits[0] == ("a.txt", 1, "Fulano")


def test_sin_coincidencias_mensaje_listo(tmp_path):
    repo = _repo_minimo(tmp_path)
    dest = tmp_path / "export"
    ctx = CtxReal(repo, revision=DatosRevision(nombre="", terminos=[]))
    assert ejecutar_exportar(ctx, str(dest)) == 0
    assert any("Listo:" in l and "sin datos tuyos" in l for l in ctx.impresiones)


def test_validar_destino_existente():
    p = Path("/tmp/ya")
    err = validar_destino(p, Path("/repo"), existe=True)
    assert err and "Ya existe" in err


def _commit_archivo(repo: Path, rel: str, texto: str) -> None:
    ruta = repo / rel
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto)
    _git(repo, "add", rel)
    _git(repo, "commit", "-m", f"add {rel}")


def test_hallazgos_terminan_con_codigo_distinto_de_cero(tmp_path):
    repo = _repo_minimo(tmp_path)
    _commit_archivo(repo, "notas.txt", "pasó por Zorbalandia ayer\n")
    ctx = CtxReal(repo, revision=DatosRevision(nombre="", terminos=["zorbalandia"]))
    assert ejecutar_exportar(ctx, str(tmp_path / "export")) == 1
    texto = "\n".join(ctx.impresiones)
    assert "notas.txt:1: zorbalandia" in texto
    assert "pasó por" not in texto


def test_permitir_hallazgos_avisa_pero_sale_cero(tmp_path):
    repo = _repo_minimo(tmp_path)
    _commit_archivo(repo, "notas.txt", "pasó por Zorbalandia ayer\n")
    ctx = CtxReal(repo, revision=DatosRevision(nombre="", terminos=["zorbalandia"]))
    assert ejecutar_exportar(ctx, str(tmp_path / "export"), permitir_hallazgos=True) == 0
    assert any("Ojo:" in l for l in ctx.impresiones)


def test_no_exporta_docs_internos(tmp_path):
    repo = _repo_minimo(tmp_path)
    for d in ("specs", "plans", "research"):
        _commit_archivo(repo, f"docs/{d}/x.md", "Zorbalandia\n")
    _commit_archivo(repo, "docs/otro.md", "limpio\n")
    dest = tmp_path / "export"
    ctx = CtxReal(repo, revision=DatosRevision(nombre="", terminos=["zorbalandia"]))
    assert ejecutar_exportar(ctx, str(dest)) == 0
    for d in ("specs", "plans", "research"):
        assert not (dest / "docs" / d).exists()
    assert (dest / "docs" / "otro.md").is_file()


def test_terminos_desde_config_suma_equipo_y_demas():
    cfg = {
        "tailscale_user": "usuario-falso@ejemplo.test",
        "plan_cwds": ["/srv/trabajo/tienda-inventada", "/srv/trabajo/api-x"],
        "mrs": {
            "usuario": "ana.ejemplo",
            "usuario_id": 99000001,
            "equipo": [{"usuario": "beto.falso", "id": 99000002, "nombre": "Beto Falso"}],
            "repos": ["/srv/trabajo/repo-ficticio"],
        },
        "exportar": {"terminos": ["Empresa Inventada", "ab", "  ", 5]},
    }
    t = [x.casefold() for x in terminos_desde_config(cfg)]
    for esperado in (
        "usuario-falso@ejemplo.test", "ana.ejemplo", "99000001", "beto.falso",
        "99000002", "beto falso", "tienda-inventada", "api-x", "repo-ficticio", "empresa inventada",
    ):
        assert esperado in t
    assert "ab" not in t
    assert all(len(x) >= 3 for x in t)


def test_terminos_revision_incluye_extra_sin_cortos_ni_duplicados():
    rev = terminos_revision(extra=["Acme Falsa", "acme falsa", "ab", ""])
    assert [t for t in rev.terminos if t.casefold() == "acme falsa"] == ["Acme Falsa"]
    assert "ab" not in rev.terminos


def test_busqueda_sin_distinguir_mayusculas(tmp_path):
    root = tmp_path / "copia"
    root.mkdir()
    (root / "a.txt").write_text("EMPRESA INVENTADA\n")
    assert buscar_datos_personales(root, ["empresa inventada"]) == [("a.txt", 1, "empresa inventada")]


def test_binarios_se_buscan_en_bytes_utf8_y_utf16(tmp_path):
    root = tmp_path / "copia"
    root.mkdir()
    (root / "a.sqlite").write_bytes(b"\x00\x01 xx Zorbalandia yy")
    (root / "b.md").write_bytes("Zorbalandia".encode("utf-16"))
    (root / "c.bin").write_bytes(b"\x00\x00limpio")
    hits = buscar_datos_personales(root, ["zorbalandia"])
    assert {h[0] for h in hits} == {"a.sqlite", "b.md"}
    assert all(h[1] == 0 for h in hits)


def test_reporte_binario_dice_binario(tmp_path):
    repo = _repo_minimo(tmp_path)
    (repo / "x.dat").write_bytes(b"\x00zorbalandia")
    _git(repo, "add", "x.dat")
    _git(repo, "commit", "-m", "bin")
    ctx = CtxReal(repo, revision=DatosRevision(nombre="", terminos=["zorbalandia"]))
    assert ejecutar_exportar(ctx, str(tmp_path / "e")) == 1
    assert any("x.dat" in l for l in ctx.impresiones)
    assert any("binario" in l for l in ctx.impresiones)


def test_busca_en_nombres_de_ruta(tmp_path):
    root = tmp_path / "copia"
    (root / "Zorbalandia-docs").mkdir(parents=True)
    (root / "Zorbalandia-docs" / "a.txt").write_text("limpio\n")
    (root / "informe-zorbalandia.txt").write_text("limpio\n")
    hits = buscar_datos_personales(root, ["zorbalandia"])
    assert {h[0] for h in hits} == {"Zorbalandia-docs", "Zorbalandia-docs/a.txt", "informe-zorbalandia.txt"}


def test_config_ilegible_avisa_y_falla(tmp_path, monkeypatch):
    d = tmp_path / "datos"
    d.mkdir()
    (d / "config.toml").write_text("esto = = no es toml\n")
    monkeypatch.setenv("ORQ_DATA_DIR", str(d))
    rev = _terminos_desde_maquina(tmp_path, tmp_path)
    assert "No pude leer la config" in rev.error
    repo = _repo_minimo(tmp_path)
    ctx = CtxReal(repo, revision=rev)
    assert ejecutar_exportar(ctx, str(tmp_path / "e1")) == 1
    assert any("No pude leer la config" in l for l in ctx.impresiones)
    ctx2 = CtxReal(repo, revision=rev)
    assert ejecutar_exportar(ctx2, str(tmp_path / "e2"), permitir_hallazgos=True) == 0
    assert any("No pude leer la config" in l for l in ctx2.impresiones)


def test_config_ausente_cuenta_como_error(tmp_path, monkeypatch):
    d = tmp_path / "datos"
    d.mkdir()
    monkeypatch.setenv("ORQ_DATA_DIR", str(d))
    assert "No pude leer la config" in _terminos_desde_maquina(tmp_path, tmp_path).error
    assert not (d / "config.toml").exists()
    (d / "config.toml").write_text("")
    monkeypatch.setattr("orquestador.exportar.load_config", lambda _d: (_ for _ in ()).throw(RuntimeError("x")))
    rev = _terminos_desde_maquina(tmp_path, tmp_path)
    assert "No pude leer la config" in rev.error


def test_carpetas_genericas_y_origen_se_excluyen():
    cfg = {
        "plan_cwds": ["/x/src", "/x/Proyectos", "/x/mi-repo-propio", "/x/tienda-rara"],
        "mrs": {"repos": ["/x/backend", "/x/otra-rara"]},
    }
    t = [x.casefold() for x in terminos_desde_config(cfg, excluir=["mi-repo-propio"])]
    assert "tienda-rara" in t and "otra-rara" in t
    for no in ("src", "proyectos", "backend", "mi-repo-propio"):
        assert no not in t


def test_reporte_agrupa_por_termino_con_cantidad(tmp_path):
    repo = _repo_minimo(tmp_path)
    for i in range(3):
        _commit_archivo(repo, f"f{i}.txt", "Zorbalandia\n")
    ctx = CtxReal(repo, revision=DatosRevision(nombre="", terminos=["zorbalandia"]))
    ejecutar_exportar(ctx, str(tmp_path / "e"))
    assert any(l.startswith("zorbalandia") and "3 archivos" in l for l in ctx.impresiones)


def test_ids_int_o_string_de_digitos_no_bool():
    cfg = {"mrs": {"usuario_id": "99000011", "equipo": [
        {"usuario": "x", "id": "99000012"}, {"usuario": "y", "id": True}]}}
    t = terminos_desde_config(cfg)
    assert "99000011" in t and "99000012" in t
    assert "True" not in t and "1" not in t
    assert "99000013" not in terminos_desde_config({"mrs": {"usuario_id": True}})


def test_quitar_docs_borra_symlink_y_avisa_error(tmp_path):
    dest = tmp_path / "c"
    (dest / "docs").mkdir(parents=True)
    afuera = tmp_path / "afuera"
    afuera.mkdir()
    (afuera / "k.txt").write_text("x")
    (dest / "docs" / "specs").symlink_to(afuera)
    assert _quitar_docs_internos(dest) == []
    assert not (dest / "docs" / "specs").is_symlink()
    assert (afuera / "k.txt").exists()
    (dest / "docs" / "plans").mkdir()
    (dest / "docs" / "plans" / "a").write_text("x")
    os.chmod(dest / "docs" / "plans", 0o500)
    try:
        if os.geteuid() != 0:
            assert _quitar_docs_internos(dest)
    finally:
        os.chmod(dest / "docs" / "plans", 0o700)


def test_cli_pasa_permitir_hallazgos(monkeypatch, tmp_path):
    import sys
    from orquestador import cli, exportar as ex

    visto = {}
    monkeypatch.setattr(ex, "exportar", lambda d, p=False: visto.update(d=d, p=p) or 0)
    monkeypatch.setattr(sys, "argv", ["orquestador", "exportar", str(tmp_path / "z"), "--permitir-hallazgos"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0 and visto["p"] is True
