from orquestador.hardening import build_csp


def test_csp_sin_google_fonts():
    csp = build_csp()
    assert "fonts.googleapis.com" not in csp
    assert "fonts.gstatic.com" not in csp
    assert "font-src 'self'" in csp


def test_csp_sin_google_fonts_con_viewer():
    csp = build_csp("https://host.ts.net:8445")
    assert "fonts.googleapis.com" not in csp
    assert "fonts.gstatic.com" not in csp
