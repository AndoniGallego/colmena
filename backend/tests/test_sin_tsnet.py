from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRS = ["backend/orquestador", "frontend/src", "tools", "deploy"]
# Texto de ejemplo Tailscale para el usuario en el instalador guiado, no config del repo.
SIN_TSNET_OK = frozenset({"backend/orquestador/instalador.py"})


def archivos():
    for d in DIRS:
        for p in (ROOT / d).rglob("*"):
            if p.is_file() and not p.name.endswith(".test.ts") and "__pycache__" not in p.parts:
                yield p


def test_ningun_tsnet():
    malos = [
        str(p.relative_to(ROOT))
        for p in archivos()
        if "ts.net" in p.read_text("utf-8", errors="ignore").lower()
        and str(p.relative_to(ROOT)) not in SIN_TSNET_OK
    ]
    assert malos == []


def test_unit_usa_environment_file():
    unit = (ROOT / "deploy/orquestador.service").read_text()
    assert "EnvironmentFile=%h/.config/orquestador/orquestador.env" in unit
    assert "ORQ_APP_ORIGIN" not in unit and "ORQ_VIEWER_ORIGIN" not in unit and "ORQ_VAPID_SUB" not in unit


def test_env_example_sin_valores():
    lineas = [l for l in (ROOT / "deploy/orquestador.env.example").read_text().splitlines()
              if l.strip() and not l.lstrip().startswith("#")]
    assert sorted(l.split("=", 1)[0] for l in lineas) == ["ORQ_APP_ORIGIN", "ORQ_VAPID_SUB", "ORQ_VIEWER_ORIGIN"]
    assert all(l.split("=", 1)[1] == "" for l in lineas)
