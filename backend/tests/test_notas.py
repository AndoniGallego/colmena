import pytest

from orquestador.notas import NotasNoDisponibles, NotasStore


def test_crear_y_listar_mas_nuevas_primero(tmp_path):
    s = NotasStore(tmp_path)
    a = s.crear("apunte", "  primera  ")
    b = s.crear("recordatorio", "segunda", {"sid": "s1", "nombre": "tienda-ps9", "ts": "2026-11-18T10:00:00Z"})
    assert [n["id"] for n in s.listar()] == [b["id"], a["id"]]
    assert a["texto"] == "primera" and a["origen"] is None and a["hecha_at"] is None
    assert b["origen"] == {"sid": "s1", "nombre": "tienda-ps9", "ts": "2026-11-18T10:00:00Z"}

def test_persiste_entre_reinicios(tmp_path):
    s = NotasStore(tmp_path); n = s.crear("apunte", "x"); s.flush()
    assert NotasStore(tmp_path).listar()[0]["id"] == n["id"]

@pytest.mark.parametrize("texto", ["", "   ", "a" * 4001])
def test_texto_invalido(tmp_path, texto):
    with pytest.raises(ValueError): NotasStore(tmp_path).crear("apunte", texto)

def test_tipo_invalido(tmp_path):
    with pytest.raises(ValueError): NotasStore(tmp_path).crear("tarea", "x")

def test_marcar_solo_recordatorios_e_idempotente(tmp_path):
    s = NotasStore(tmp_path); r = s.crear("recordatorio", "r"); a = s.crear("apunte", "a")
    h1 = s.marcar(r["id"], True); h2 = s.marcar(r["id"], True)
    assert h1["hecha_at"] and h2["hecha_at"] == h1["hecha_at"]
    assert s.marcar(r["id"], False)["hecha_at"] is None
    with pytest.raises(ValueError): s.marcar(a["id"], True)

def test_pendientes_cuenta_solo_recordatorios_sin_hacer(tmp_path):
    s = NotasStore(tmp_path); s.crear("apunte", "a"); r = s.crear("recordatorio", "r"); s.crear("recordatorio", "q")
    s.marcar(r["id"], True)
    assert s.pendientes() == 1

def test_editar_borrar_y_desconocida(tmp_path):
    s = NotasStore(tmp_path); n = s.crear("apunte", "a")
    assert s.editar(n["id"], texto="b", tipo="recordatorio")["texto"] == "b"
    assert s.editar("n_nope") is None and s.marcar("n_nope", True) is None
    assert s.borrar(n["id"]) is True and s.borrar(n["id"]) is False

def test_cambiar_a_apunte_limpia_hecha(tmp_path):
    s = NotasStore(tmp_path); r = s.crear("recordatorio", "r"); s.marcar(r["id"], True)
    assert s.editar(r["id"], tipo="apunte")["hecha_at"] is None

def test_archivo_roto_va_a_cuarentena(tmp_path):
    (tmp_path / "notas.json").write_text("{no es json", encoding="utf-8")
    assert NotasStore(tmp_path).listar() == []
    assert list(tmp_path.glob("notas.json.roto-*"))

def test_version_sube_en_cada_cambio(tmp_path):
    s = NotasStore(tmp_path); v = s.version; s.crear("apunte", "a")
    assert s.version == v + 1


def test_editada_at_se_inicia_y_cambia_al_editar(tmp_path):
    s = NotasStore(tmp_path); n = s.crear("apunte", "a")
    assert n["editada_at"] == n["creada_at"]
    s._notas[0]["editada_at"] = "2000-01-01T00:00:00Z"
    assert s.editar(n["id"], texto="b")["editada_at"] != "2000-01-01T00:00:00Z"
    s._notas[0]["editada_at"] = "2000-01-01T00:00:00Z"
    assert s.editar(n["id"], texto="b")["editada_at"] == "2000-01-01T00:00:00Z"
    assert s.editar(n["id"], tipo="recordatorio")["editada_at"] != "2000-01-01T00:00:00Z"


def test_nota_vieja_sin_editada_at_usa_creada_at(tmp_path):
    (tmp_path / "notas.json").write_text(
        '{"notas": [{"id": "n_x", "tipo": "apunte", "texto": "t", "creada_at": "2026-01-01T00:00:00Z", "hecha_at": null, "origen": null}]}',
        encoding="utf-8")
    assert NotasStore(tmp_path).listar()[0]["editada_at"] == "2026-01-01T00:00:00Z"


def test_error_de_lectura_arranca_vacio_sin_mover_el_archivo(tmp_path):
    (tmp_path / "notas.json").mkdir()
    assert NotasStore(tmp_path).listar() == []
    assert (tmp_path / "notas.json").is_dir()
    assert not list(tmp_path.glob("notas.json.roto-*"))


def test_no_disponible_tras_error_de_lectura_no_pisa_el_archivo(tmp_path):
    (tmp_path / "notas.json").mkdir()
    s = NotasStore(tmp_path)
    assert s.listar() == [] and s.pendientes() == 0
    for llamada in (lambda: s.crear("apunte", "x"), lambda: s.editar("n_x", texto="y"),
                    lambda: s.marcar("n_x", True), lambda: s.borrar("n_x")):
        with pytest.raises(NotasNoDisponibles):
            llamada()
    s.flush()
    assert (tmp_path / "notas.json").is_dir()
    assert s.version == 0
