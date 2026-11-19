import re
from typing import Optional

SCREENSHOT_SAVED_RE = re.compile(r"Screenshot saved to:\s*(\S+)")
SCREENSHOT_ID_RE = re.compile(r"\bID:\s*(ss_[a-z0-9]{4,40})\b")
EVIDENCIA_ID_RE = re.compile(r"^ss_[a-z0-9]{4,40}$")
LOCAL_IMG_RE = re.compile(r"!\[([^\]]*)\]\((/[^)\s]+)\)")


def ruta_desde_tool_result(block: dict) -> Optional[str]:
    content = block.get("content")
    if not isinstance(content, list):
        return None
    for piece in content:
        if not isinstance(piece, dict) or piece.get("type") != "text":
            continue
        text = piece.get("text")
        if not isinstance(text, str):
            continue
        m = SCREENSHOT_SAVED_RE.search(text)
        if m:
            return m.group(1)
    return None


def id_desde_tool_result(block: dict) -> Optional[str]:
    content = block.get("content")
    if not isinstance(content, list):
        return None
    for piece in content:
        if not isinstance(piece, dict) or piece.get("type") != "text":
            continue
        text = piece.get("text")
        if isinstance(text, str) and text.startswith("Successfully captured screenshot"):
            m = SCREENSHOT_ID_RE.search(text)
            if m:
                return m.group(1)
    return None


def local_paths_en_markdown(text: str) -> list[tuple[str, str]]:
    if not text:
        return []
    out: list[tuple[str, str]] = []
    for m in LOCAL_IMG_RE.finditer(text):
        path = m.group(2)
        if path.startswith("//") or path.startswith("/http"):
            continue
        out.append((path, m.group(1)))
    return out


def quitar_imagenes_locales(text: str, resueltas: set[str]) -> str:
    if not text:
        return text

    def repl(m: re.Match) -> str:
        path, alt = m.group(2), m.group(1)
        if path in resueltas:
            return ""
        return alt.strip() if alt.strip() else ""

    return LOCAL_IMG_RE.sub(repl, text)
