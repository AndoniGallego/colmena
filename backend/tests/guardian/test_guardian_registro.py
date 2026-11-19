import json
import os
import stat

from orquestador.guardian.registro import Registro


def test_ids_no_se_reusan(tmp_path):
    ruta = tmp_path / "registro.json"
    r = Registro(ruta)
    e = r.nuevo_espacio("E", "/tmp")
    n1 = int(e.id[1:])
    l = r.nueva_linea(e.id, "L")
    n2 = int(l.id.split(":t")[1])
    r.quitar_espacio(e.id)
    e2 = r.nuevo_espacio("E2", "/tmp")
    assert int(e2.id[1:]) > n1
    r2 = Registro(ruta)
    r2.cargar()
    assert r2.contador == r.contador


def test_archivo_0600(tmp_path):
    ruta = tmp_path / "registro.json"
    Registro(ruta).nuevo_espacio("E", "/tmp")
    assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600


def test_recarga_identica(tmp_path):
    ruta = tmp_path / "registro.json"
    r = Registro(ruta)
    e = r.nuevo_espacio("Esp", "/cwd")
    l = r.nueva_linea(e.id, "Lin")
    s = r.nueva_sesion(l.id, "Ses", "/cwd", "claude", "00000000-0000-0000-0000-000000000001")
    r2 = Registro(ruta)
    r2.cargar()
    assert r2.contador == r.contador
    assert r2.espacios[e.id].nombre == "Esp"
    assert r2.sesiones[s.id].claude_session_id == s.claude_session_id


def test_corrupto_renombrado(tmp_path):
    ruta = tmp_path / "registro.json"
    ruta.write_text("{no json", encoding="utf-8")
    r = Registro(ruta)
    r.cargar()
    assert not r.espacios
    rotos = list(tmp_path.glob("registro.json.roto-*"))
    assert len(rotos) == 1


def test_modo_permisos_persiste_y_falla_cerrado(tmp_path):
    ruta = tmp_path / "registro.json"
    r = Registro(ruta)
    e = r.nuevo_espacio("Esp", "/cwd")
    l = r.nueva_linea(e.id, "Lin")
    s = r.nueva_sesion(l.id, "Ses", "/cwd", "claude", "00000000-0000-0000-0000-000000000001")
    s2 = r.nueva_sesion(l.id, "Ses2", "/cwd", "claude", "00000000-0000-0000-0000-000000000002")
    assert s.modo_permisos is None
    r.actualizar_sesion(s.id, modo_permisos="default")
    datos = json.loads(ruta.read_text())
    for raw in datos["sesiones"]:
        if raw["id"] == s2.id:
            raw["modo_permisos"] = "bypassPermissions"
    viejo = next(raw for raw in datos["sesiones"] if raw["id"] == s.id)
    ruta.write_text(json.dumps(datos))
    r2 = Registro(ruta)
    r2.cargar()
    assert r2.sesiones[s.id].modo_permisos == "default"
    assert r2.sesiones[s2.id].modo_permisos == "default"
    del viejo["modo_permisos"]
    ruta.write_text(json.dumps(datos))
    r3 = Registro(ruta)
    r3.cargar()
    assert r3.sesiones[s.id].modo_permisos is None


def test_modos_por_conversacion_persisten_con_tope_y_validan(tmp_path):
    from orquestador.guardian import registro as mod

    r = mod.Registro(tmp_path / "r.json")
    r.recordar_modo_claude("c1", "plan")
    r.recordar_modo_claude("c2", "default")
    r2 = mod.Registro(tmp_path / "r.json")
    r2.cargar()
    assert r2.modo_de_claude("c1") == "plan" and r2.modo_de_claude("c2") == "default"
    assert r2.modo_de_claude("nada") is None and r2.modo_de_claude(None) is None
    datos = json.loads((tmp_path / "r.json").read_text())
    datos["modos_claude"]["c3"] = "bypassPermissions"
    (tmp_path / "r.json").write_text(json.dumps(datos))
    r3 = mod.Registro(tmp_path / "r.json")
    r3.cargar()
    assert r3.modo_de_claude("c3") == "default"
    for i in range(mod.MAX_MODOS_CLAUDE + 5):
        r2.recordar_modo_claude(f"x{i}", "default")
    assert len(r2.modos_claude) == mod.MAX_MODOS_CLAUDE and r2.modo_de_claude("c1") is None
