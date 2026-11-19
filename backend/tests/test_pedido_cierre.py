import pytest

from orquestador.cierre import CierreService
from orquestador.pedido_cierre import motivo_fin_lote, resolver_objetivo, resumen_cierre, vista_cierre


def tablero(pinned=False):
    return {"workspaces": [
        {"id": "w1", "label": "Uno", "pinned": False, "tabs": [
            {"id": "w1:t1", "label": "api", "agents": [{"pane_id": "w1:p1", "session_id": "s1", "title": "Sesión api"}],
             "terminales": []}]},
        {"id": "w2", "label": "Dos", "pinned": pinned, "tabs": [
            {"id": "w2:t1", "label": "Vacío", "agents": [], "terminales": [{"pane_id": "w2:p1"}]},
            {"id": "w2:t2", "label": "mixta", "agents": [{"pane_id": "w2:p9", "session_id": "s9", "title": "Otra"}],
             "terminales": [{"pane_id": "w2:p3"}]}]}]}


@pytest.mark.parametrize("objetivo,sel,esperado", [
    ("tarjeta", "w2", ("workspace", "w2")), ("tarjeta", "  dos ", ("workspace", "w2")),
    ("pestana", "w2:t1", ("tab", "w2:t1")), ("pestana", "  Vacío ", ("tab", "w2:t1")),
    ("sesion", "w1:p1", ("tab", "w1:t1")), ("sesion", "sesión API", ("tab", "w1:t1")),
])
def test_resolver_por_id_o_nombre(objetivo, sel, esperado):
    hallado, motivo = resolver_objetivo(tablero(), objetivo, sel)
    assert motivo is None and (hallado["tipo"], hallado["target_id"]) == esperado and hallado["objetivo"] == objetivo


def test_resolver_no_encontrado_y_ambiguo():
    b = tablero()
    assert resolver_objetivo(b, "pestana", "nada") == (None, "cierre_no_encontrado")
    assert resolver_objetivo(None, "pestana", "nada") == (None, "cierre_no_encontrado")
    b["workspaces"][0]["tabs"][0]["label"] = "vacío"
    assert resolver_objetivo(b, "pestana", "VACÍO") == (None, "cierre_ambiguo")


def test_resolver_sesion_compartida():
    assert resolver_objetivo(tablero(), "sesion", "w2:p9") == (None, "sesion_compartida")


def test_resolver_espacio_protegido():
    assert resolver_objetivo(tablero(pinned=True), "pestana", "w2:t1") == (None, "cierre_protegido")
    assert resolver_objetivo(tablero(pinned=True), "tarjeta", "w2") == (None, "cierre_protegido")
    assert resolver_objetivo(tablero(pinned=True), "sesion", "w2:p9") == (None, "cierre_protegido")


def test_ambiguo_gana_aunque_una_coincidencia_sea_protegida():
    b = tablero(pinned=True)
    b["workspaces"][0]["tabs"][0]["label"] = "Vacío"
    assert resolver_objetivo(b, "pestana", "vacío") == (None, "cierre_ambiguo")


def test_resumen_y_vista():
    preview = {"tipo": "tab", "target_id": "w2:t2", "label": "mixta", "workspace_label": "Dos", "cierra_workspace": False,
               "tab_count": 1, "huella": "h", "bloqueantes": [{"pane_id": "w2:p9", "status": "working"}],
               "panes": [{"pane_id": "w2:p3", "kind": None, "cwd": "/tmp/b", "titulo": "logs"},
                         {"pane_id": "w2:p9", "kind": "claude", "cwd": "/tmp/a", "titulo": "Otra"}]}
    r = resumen_cierre("pestana", preview)
    assert (r["label"], r["carpeta"], r["sesiones"], r["terminales"]) == ("mixta", "/tmp/a", 1, 1)
    assert r["estructura"] == CierreService.estructura(preview)
    assert resumen_cierre("sesion", preview)["label"] == "Otra"
    assert vista_cierre(preview) == {"trabajando": True, "estados": ["working"], "huella": "h"}
    assert vista_cierre({**preview, "bloqueantes": []})["trabajando"] is False


def test_motivo_fin_lote():
    assert motivo_fin_lote({"vencido": True, "targets": []}) == "cierre_no_hecho"
    assert motivo_fin_lote({"vencido": False, "targets": [{"estado": "error"}]}) == "cierre_no_hecho"
    assert motivo_fin_lote({"vencido": False, "targets": [{"estado": "guardando"}]}) is None
