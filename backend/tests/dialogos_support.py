import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "dialogos"
FIXTURE_SESSION = "2553341c-fd0e-4e50-ae59-1fa494a6ad9b"


def screen(name: str) -> str:
    return (FIX / f"{name}.txt").read_text(encoding="utf-8")


def meta(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def tool_use(name: str) -> dict:
    block = json.loads((FIX / f"{name}.transcript.json").read_text(encoding="utf-8"))["message"]["content"][0]
    return {"id": block["id"], "name": block["name"], "input": block["input"]}


def transcript_line(name: str) -> dict:
    return json.loads((FIX / f"{name}.transcript.json").read_text(encoding="utf-8"))


def multi_tool_use() -> dict:
    """Las capturas auq-3/auq-4 no traen su transcript (están corridos en uno): mismas preguntas que muestra la pantalla."""
    options = [("Python", "Lenguaje interpretado, versátil, muy usado en scripting, datos y backend."),
               ("PHP", "Lenguaje orientado a web, base de PrestaShop y muchos CMS."),
               ("Go", "Lenguaje compilado de Google, simple y con concurrencia nativa.")]
    return {"id": "toolu_multi_0001", "name": "AskUserQuestion", "input": {"questions": [{
        "question": "¿Qué lenguajes usás?", "header": "Lenguajes", "multiSelect": True,
        "options": [{"label": l, "description": d} for l, d in options]}]}}


def multi_transcript_line() -> dict:
    tu = multi_tool_use()
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", **tu}]}}
