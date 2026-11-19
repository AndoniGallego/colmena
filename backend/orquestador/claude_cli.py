import os

from .enchufe import VARIABLES_PROPIAS


def fmt_tokens(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def headless_env() -> dict:
    # Si el server se lanzó desde un pane, herdr apuntaría a ese pane al omitir el target.
    return {k: v for k, v in os.environ.items() if k not in VARIABLES_PROPIAS}
