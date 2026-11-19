import json
import os
import stat

from orquestador.memoria_indice import MAX_TURNO, IndiceMemoria, buscar, leer, titulo_de

SID = "aaaaaaaa-1111-2222-3333-444444444444"


def linea(kind, content, **extra):
    base = {"type": kind, "cwd": "/home/u/proj", "gitBranch": "main", "timestamp": "2026-10-20T10:00:00Z",
            "sessionId": SID, "message": {"content": content}}
    base.update(extra)
    return json.dumps(base)


def escribir(path, lineas, modo="w"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(modo, encoding="utf-8") as fh:
        fh.write("".join(l + "\n" for l in lineas))


def textos(indice):
    conn = indice.lectura()
    rows = conn.execute("SELECT t.rol, f.texto FROM turnos t JOIN turnos_fts f ON f.rowid = t.id ORDER BY t.idx").fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]


def make(tmp_path, **kw):
    projects = tmp_path / "projects"
    projects.mkdir(exist_ok=True)
    return projects, IndiceMemoria(tmp_path / "data" / "memoria", projects, **kw)


def test_que_entra_y_que_no(tmp_path):
    projects, indice = make(tmp_path)
    escribir(projects / "-home-u-proj" / f"{SID}.jsonl", [
        json.dumps({"type": "ai-title", "aiTitle": "Entorno local"}),
        linea("user", "<system-reminder>no</system-reminder>"),
        linea("user", "meta oculto", isMeta=True),
        linea("user", "de sistema", promptSource="system"),
        linea("user", "<command-name>/x</command-name>"),
        linea("user", "<task-notification>t</task-notification>"),
        linea("user", [{"type": "tool_result", "content": "salida de tool"}]),
        linea("user", "pregunta humana"),
        linea("assistant", [{"type": "thinking", "thinking": "pensando"},
                            {"type": "tool_use", "name": "Bash", "input": {"command": "ls secreto"}},
                            {"type": "text", "text": "respuesta de claude"}]),
        linea("assistant", [{"type": "text", "text": "de un subagente"}], isSidechain=True),
        linea("user", "Resumen de la compactación previa", isCompactSummary=True),
        json.dumps({"type": "attachment", "timestamp": "2026-10-20T10:01:00Z", "cwd": "/home/u/proj",
                    "attachment": {"type": "queued_command", "commandMode": "prompt", "humanTurn": True,
                                   "prompt": "mensaje encolado"}}),
    ])
    escribir(projects / "-home-u-proj" / SID / "subagents" / "agent-1.jsonl", [linea("user", "subagente")])
    escribir(projects / "-home-usuario-Proyectos-orquestador-data-context" / "bbbb.jsonl", [linea("user", "turno de dios")])
    escribir(projects / "-tmp-scratch" / "cccc.jsonl", [linea("user", "scratch")])
    assert indice.actualizar() is True
    assert textos(indice) == [("usuario", "pregunta humana"), ("claude", "respuesta de claude"),
                              ("resumen", "Resumen de la compactación previa"), ("usuario", "mensaje encolado")]
    conn = indice.lectura()
    assert titulo_de(conn, SID)["titulo"] == "Entorno local"
    assert conn.execute("SELECT COUNT(*) FROM archivos").fetchone()[0] == 1


def test_incremental_por_offset_y_linea_a_medio_escribir(tmp_path):
    projects, indice = make(tmp_path)
    path = projects / "-p" / f"{SID}.jsonl"
    escribir(path, [linea("user", "uno")])
    with path.open("a") as fh:
        fh.write(linea("user", "dos")[:20])
    indice.actualizar()
    assert textos(indice) == [("usuario", "uno")]
    with path.open("a") as fh:
        fh.write(linea("user", "dos")[20:] + "\n")
    indice.actualizar()
    assert textos(indice) == [("usuario", "uno"), ("usuario", "dos")]
    escribir(path, [linea("user", "tres")], modo="a")
    indice.actualizar()
    assert [t for _, t in textos(indice)] == ["uno", "dos", "tres"]
    conn = indice.lectura()
    assert [r[0] for r in conn.execute("SELECT idx FROM turnos ORDER BY idx")] == [0, 1, 2]


def test_truncado_o_reemplazado_reindexa(tmp_path):
    projects, indice = make(tmp_path)
    path = projects / "-p" / f"{SID}.jsonl"
    escribir(path, [linea("user", "original largo largo"), linea("user", "otro")])
    indice.actualizar()
    escribir(path, [linea("user", "nuevo")])
    indice.actualizar()
    assert textos(indice) == [("usuario", "nuevo")]
    otro = path.with_name("tmp.jsonl")
    escribir(otro, [linea("user", "reemplazo"), linea("user", "con más líneas que antes"),
                    linea("user", "y otra")])
    os.replace(otro, path)
    indice.actualizar()
    assert [t for _, t in textos(indice)] == ["reemplazo", "con más líneas que antes", "y otra"]


def test_transcript_borrado_se_olvida(tmp_path):
    projects, indice = make(tmp_path)
    path = projects / "-p" / f"{SID}.jsonl"
    escribir(path, [linea("user", "algo")])
    indice.actualizar()
    path.unlink()
    indice.actualizar()
    assert textos(indice) == []
    assert indice.estado()["indexados"] == 0


def test_acentos_recorte_y_env(tmp_path):
    projects, indice = make(tmp_path)
    escribir(projects / "-p" / f"{SID}.jsonl", [
        json.dumps({"type": "ai-title", "aiTitle": "Sesión de prueba"}),
        linea("user", "Hablemos de la compactación del contexto"),
        linea("assistant", [{"type": "text", "text": "x" * (MAX_TURNO + 500)}]),
        linea("user", [{"type": "text", "text": "API_URL=http://x\nDB_USER=root\nDB_PASSWORD=hunter22\n"},
                       {"type": "text", "text": "mirá este env"}]),
        linea("user", "conectá con password=hunter22 y token: ab12cd34ef56"),
    ])
    indice.actualizar()
    conn = indice.lectura()
    hits = buscar(conn, "compactacion")
    assert hits and hits[0]["turno"] == 0 and hits[0]["titulo"]
    rows = textos(indice)
    assert len(rows[1][1]) <= MAX_TURNO + 1
    assert "«contenido de .env omitido»" in rows[2][1] and "mirá este env" in rows[2][1]
    dump = (tmp_path / "data" / "memoria" / "indice.sqlite").read_bytes()
    assert b"hunter22" not in dump and b"ab12cd34ef56" not in dump


def test_permisos(tmp_path):
    projects, indice = make(tmp_path)
    escribir(projects / "-p" / f"{SID}.jsonl", [linea("user", "hola")])
    indice.actualizar()
    assert stat.S_IMODE((tmp_path / "data" / "memoria").stat().st_mode) == 0o700
    for f in (tmp_path / "data" / "memoria").iterdir():
        assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_excluir_por_cwd(tmp_path):
    projects, indice = make(tmp_path, excluir=lambda: ["/home/u/privado"])
    escribir(projects / "-p" / f"{SID}.jsonl", [linea("user", "visible"),
                                               linea("user", "privado", cwd="/home/u/privado/x"),
                                               linea("user", "temporal", cwd="/tmp/x")])
    indice.actualizar()
    assert textos(indice) == [("usuario", "visible")]


def test_presupuesto_corta_y_completa_despues(tmp_path):
    projects, indice = make(tmp_path)
    for n in range(3):
        escribir(projects / "-p" / f"s{n}.jsonl", [linea("user", f"sesion {n}")])
    reloj = iter([0.0, 0.0, 5.0, 5.0, 5.0])
    indice.clock = lambda: next(reloj)
    assert indice.actualizar(presupuesto=1.5) is False
    assert indice.estado()["indexados"] == 1
    indice.clock = lambda: 0.0
    assert indice.actualizar() is True
    assert indice.estado()["indexados"] == 3


def test_buscar_filtros_y_leer(tmp_path):
    projects, indice = make(tmp_path)
    escribir(projects / "-p" / f"{SID}.jsonl", [
        json.dumps({"type": "ai-title", "aiTitle": "Bug de permisos"}),
        linea("user", "categorizador permisos", timestamp="2026-10-01T10:00:00Z"),
        linea("assistant", [{"type": "text", "text": "el categorizador usa Access::isGranted"}],
              timestamp="2026-10-02T10:00:00Z"),
        linea("user", "otra cosa", timestamp="2026-10-03T10:00:00Z", cwd="/otro"),
    ])
    indice.actualizar()
    conn = indice.lectura()
    assert {h["turno"] for h in buscar(conn, "categorizador")} == {0, 1}
    assert [h["turno"] for h in buscar(conn, "categorizador", desde="2026-10-02")] == [1]
    assert [h["turno"] for h in buscar(conn, "categorizador", hasta="2026-10-01")] == [0]
    assert buscar(conn, "otra", proyecto="/home/u") == []
    assert [h["turno"] for h in buscar(conn, 'categorizador" OR NEAR(')] != []
    assert buscar(conn, "") == []
    assert {h["turno"] for h in buscar(conn, "bug")} == {0, 1, 2}
    leido = leer(conn, SID, 1, 1)
    assert [t["turno"] for t in leido["turnos"]] == [0, 1, 2]
    assert leer(conn, "nope", 0, 1) is None


def test_borrar(tmp_path):
    projects, indice = make(tmp_path)
    escribir(projects / "-p" / f"{SID}.jsonl", [linea("user", "hola")])
    indice.actualizar()
    indice.borrar()
    assert not indice.path.exists()
    assert indice.estado()["indexados"] == 0
    indice.actualizar()
    assert indice.estado()["indexados"] == 1
