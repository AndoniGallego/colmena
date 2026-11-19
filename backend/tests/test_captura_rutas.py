from orquestador.captura_rutas import (
    local_paths_en_markdown,
    quitar_imagenes_locales,
    ruta_desde_tool_result,
)


def test_ruta_desde_tool_result_texto():
    block = {"content": [{"type": "text", "text": "Screenshot saved to: /tmp/foo/bar.jpg\nok"}]}
    assert ruta_desde_tool_result(block) == "/tmp/foo/bar.jpg"


def test_ruta_desde_tool_result_sin_linea():
    assert ruta_desde_tool_result({"content": [{"type": "text", "text": "done"}]}) is None


def test_local_paths_en_markdown():
    t = "Antes ![Búsqueda](/tmp/x/a.jpg) medio ![ok](https://x/y.png) fin"
    assert local_paths_en_markdown(t) == [("/tmp/x/a.jpg", "Búsqueda")]


def test_local_paths_ignora_data_y_relativas():
    t = "![](data:image/png;base64,xx) ![r](rel.png)"
    assert local_paths_en_markdown(t) == []


def test_quitar_imagenes_locales_resueltas():
    t = "A ![alt](/tmp/x.jpg) B ![otra](/tmp/y.jpg) C"
    out = quitar_imagenes_locales(t, {"/tmp/x.jpg"})
    assert "/tmp/x.jpg" not in out
    assert "alt" not in out
    assert "otra" in out
    assert "/tmp/y.jpg" not in out


def test_quitar_imagenes_locales_muestra_alt_si_no_resuelta():
    t = "Texto ![solo alt](/tmp/desconocida.jpg) fin"
    out = quitar_imagenes_locales(t, set())
    assert "solo alt" in out
    assert "/tmp/desconocida" not in out
