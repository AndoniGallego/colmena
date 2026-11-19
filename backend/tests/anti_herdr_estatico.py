import ast
from pathlib import Path

_MOTIVOS_HERDR = frozenset({"HerdrClient", "HerdrError"})


def _rel(raiz: Path, path: Path) -> str:
    return path.relative_to(raiz).as_posix()


def _import_violacion(node: ast.Import | ast.ImportFrom, rel: str) -> list[str]:
    out: list[str] = []
    msg = f"{rel}:{node.lineno}: import prohibido de herdr"
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "orquestador.herdr" or alias.name.split(".")[-1] in _MOTIVOS_HERDR:
                out.append(msg)
        return out
    mod = node.module
    if not node.level and mod and (mod == "orquestador.herdr" or mod.startswith("orquestador.herdr.")):
        out.append(msg)
        return out
    if node.level and mod and (mod == "herdr" or mod.startswith("herdr.")):
        out.append(msg)
        return out
    if node.level and mod is None and any(a.name == "herdr" for a in node.names):
        out.append(msg)
        return out
    if mod == "orquestador" and any(a.name == "herdr" for a in node.names):
        out.append(msg)
        return out
    for alias in node.names:
        if alias.name in _MOTIVOS_HERDR:
            out.append(msg)
    return out


def _literal_herdr(node) -> bool:
    return isinstance(node, ast.Constant) and node.value == "herdr"


def _lista_o_tupla_herdr(node: ast.List | ast.Tuple) -> bool:
    return bool(node.elts) and _literal_herdr(node.elts[0])


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel = rel
        self.out: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.out.extend(_import_violacion(node, self.rel))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.out.extend(_import_violacion(node, self.rel))

    def visit_Call(self, node: ast.Call) -> None:
        if node.args and _literal_herdr(node.args[0]):
            self.out.append(f"{self.rel}:{node.lineno}: invocación con binario herdr")
        self.generic_visit(node)

    def visit_List(self, node: ast.List) -> None:
        if _lista_o_tupla_herdr(node):
            self.out.append(f"{self.rel}:{node.lineno}: lista con herdr como primer elemento")
        self.generic_visit(node)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        if _lista_o_tupla_herdr(node):
            self.out.append(f"{self.rel}:{node.lineno}: tupla con herdr como primer elemento")
        self.generic_visit(node)


def violaciones(raiz: Path, excluir: frozenset[str]) -> list[str]:
    raiz = raiz.resolve()
    enchufe = raiz / "enchufe"
    found: list[str] = []
    for path in sorted(raiz.rglob("*.py")):
        if enchufe in path.parents or path.parent == enchufe:
            continue
        if path.name in excluir:
            continue
        rel = _rel(raiz, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            found.append(f"{rel}:{exc.lineno or 0}: archivo no parseable")
            continue
        vis = _Visitor(rel)
        vis.visit(tree)
        found.extend(vis.out)
    return found
