"""Ningún archivo del núcleo importa una pieza: cada pieza se puede quitar sin romper el resto."""
import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "orquestador"
PIEZAS = "orquestador.piezas."


def _importados(codigo: str, paquete: list) -> list:
    """Módulos (y módulo.nombre) que importa `codigo`, con los relativos resueltos contra `paquete`."""
    out = []
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Import):
            out += [a.name for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom):
            modulo = nodo.module or ""
            if nodo.level:
                padre = paquete[: len(paquete) - (nodo.level - 1)]
                modulo = ".".join([*padre, *([modulo] if modulo else [])])
            out.append(modulo)
            out += [f"{modulo}.{a.name}" for a in nodo.names]
    return out


def _pieza_de(path: Path):
    partes = path.relative_to(RAIZ).parts
    return partes[1] if len(partes) > 2 and partes[0] == "piezas" else None


def test_el_nucleo_no_importa_piezas():
    culpables = []
    for path in RAIZ.rglob("*.py"):
        paquete = ["orquestador", *path.relative_to(RAIZ).parent.parts]
        propia = _pieza_de(path)
        for nombre in _importados(path.read_text(encoding="utf-8"), paquete):
            if nombre.startswith(PIEZAS) and nombre[len(PIEZAS):].split(".")[0] != propia:
                culpables.append(f"{path.relative_to(RAIZ)} -> {nombre}")
    assert culpables == []


def test_resuelve_imports_relativos_y_absolutos():
    codigo = "from .piezas.demo import x\nfrom .piezas import otra\nimport orquestador.piezas.tercera\n"
    nombres = _importados(codigo, ["orquestador"])
    assert {"orquestador.piezas.demo", "orquestador.piezas.otra", "orquestador.piezas.tercera"} <= set(nombres)
    assert "orquestador.agenda" in _importados("from ...agenda import y\n", ["orquestador", "piezas", "demo"])
