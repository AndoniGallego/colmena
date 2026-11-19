import json
import os
from pathlib import Path

from orquestador.biblioteca import Library
from orquestador.config import Config

SID = "aaaaaaaa-0000-4000-8000-000000000001"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
SECRET = b"secreto-de-prueba"
ARTIFACT_URL = "https://claude.ai/artifact/AbCdEf123456"


class Env:
    def __init__(self, tmp: Path, **cfg_over):
        self.tmp = tmp
        self.home = tmp / "home"
        self.home.mkdir(exist_ok=True)
        self.base = tmp / "claude-scratch"
        self.scratch = self.base / "proj" / "uuid-1" / "scratchpad"
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.projects = tmp / "projects"
        (self.projects / "-proj").mkdir(parents=True, exist_ok=True)
        self.data = tmp / "data"
        self.data.mkdir(exist_ok=True)
        self.cfg = Config(claude_projects_dir=str(self.projects), viewer_origin="https://h.ts.net:8445",
                          app_origin="https://h.ts.net:8444", **cfg_over)
        self.epoch = [0]
        self.lib = Library(self.cfg, self.data, SECRET, epoch=lambda: self.epoch[0], scratch_base=self.base,
                           home=self.home)
        self.n = 0

    def reload(self) -> Library:
        self.lib.flush()
        self.lib = Library(self.cfg, self.data, SECRET, epoch=lambda: self.epoch[0], scratch_base=self.base,
                           home=self.home)
        return self.lib

    def file(self, name: str, data=b"<html><title>Hola</title></html>", where=None) -> str:
        path = (where or self.scratch) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return str(path)

    def transcript_path(self, sid=SID, sub=None) -> Path:
        if sub:
            p = self.projects / "-proj" / sid / "subagents" / f"agent-{sub}.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        return self.projects / "-proj" / f"{sid}.jsonl"

    def append(self, lines: list, sid=SID, sub=None, dup=False) -> None:
        path = self.transcript_path(sid, sub)
        with path.open("a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(json.dumps(line) + "\n")
                if dup:
                    fh.write(json.dumps(line) + "\n")

    def tid(self) -> str:
        self.n += 1
        return f"toolu_{self.n:04d}"


def use(tid, name, inp, ts="2026-11-01T10:00:00Z"):
    return {"type": "assistant", "timestamp": ts, "cwd": "/home/x", "uuid": f"u-{tid}",
            "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def result(tid, text="ok", tur=None, error=False, ts="2026-11-01T10:00:05Z"):
    line = {"type": "user", "timestamp": ts,
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": text,
                                     **({"is_error": True} if error else {})}]}}
    if tur is not None:
        line["toolUseResult"] = tur
    return line


def artifact(env: Env, path, tur=True, ts="2026-11-01T10:00:00Z", error=False, version=1, **inp):
    tid = env.tid()
    body = {"file_path": path, **inp}
    res = {"url": ARTIFACT_URL, "path": path, "artifact_id": "AbCdEf123456", "title": "Mi página",
           "version": version} if tur else None
    text = f"Published {path} at {ARTIFACT_URL} (Version {version}, ok)"
    return [use(tid, "Artifact", body, ts), result(tid, text, res, error, ts=ts)], tid


def text_msg(text, uuid="m1", ts="2026-11-01T10:00:00Z"):
    return {"type": "assistant", "timestamp": ts, "uuid": uuid, "message": {"content": [{"type": "text", "text": text}]}}


PROCESO = '```diagrama\n{"titulo": "Login", "tipo": "proceso", "pasos": [{"texto": "uno"}]}\n```'
