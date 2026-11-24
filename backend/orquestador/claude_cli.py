import json
import os

from .enchufe import VARIABLES_PROPIAS


def fmt_tokens(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def headless_env() -> dict:
    # Si el server se lanzó desde un pane, herdr apuntaría a ese pane al omitir el target.
    return {k: v for k, v in os.environ.items() if k not in VARIABLES_PROPIAS}


def args_headless(binary: str, modelo: str, budget: float) -> list:
    flag = ["--max-budget-usd", f"{budget:g}"] if budget > 0 else []
    return [binary, "-p", "--model", modelo, *flag, "--output-format", "json", "--tools", "", "--strict-mcp-config"]


def parse_headless(out: bytes) -> dict:
    """El objeto JSON que imprime `claude -p --output-format json`; {} si no es utilizable."""
    try:
        obj = json.loads(out or b"null")
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def resultado_headless(rc: int, obj: dict) -> "str | None":
    """El texto del resultado, o None si salió mal (rc, is_error, sin texto)."""
    if rc != 0 or obj.get("is_error") or not isinstance(obj.get("result"), str):
        return None
    return obj["result"]
