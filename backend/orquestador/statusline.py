import fcntl
import glob
import json
import os
from . import kit_trabajo
import re
import socket
import struct
from datetime import datetime
from pathlib import Path
from typing import Optional

SIOCGIFADDR = 0x8915
DEFAULT_WINDOW = 1_000_000
SMALL_WINDOW = 200_000
DEFAULT_WARN_PCT = 25
FAMILIES = {"opus": "Opus", "sonnet": "Sonnet", "haiku": "Haiku", "fable": "Fable"}
MODEL_ID = re.compile(r"^(?:claude-)?(opus|sonnet|haiku|fable)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?(?:\[.*\])?$")
TICKET_MAX = 200
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
SNAPSHOT_TOLERANCE = 120


def model_name(model_id: str) -> str:
    raw = (model_id or "").strip()
    m = MODEL_ID.match(raw)
    if not m:
        return raw.removeprefix("claude-")
    version = f"{m.group(2)}.{m.group(3)}" if m.group(3) else m.group(2)
    return f"{FAMILIES[m.group(1)]} {version}"


def context_window(model_id: str) -> int:
    mid = model_id or ""
    if "haiku-4-5" in mid:
        return SMALL_WINDOW
    return DEFAULT_WINDOW


def warn_pct() -> int:
    try:
        value = int(kit_trabajo.variable("CTX_WARN_PCT", DEFAULT_WARN_PCT))
    except ValueError:
        return DEFAULT_WARN_PCT
    return value if value > 0 else DEFAULT_WARN_PCT


def ctx_state(tokens: Optional[int], model_id: str, window: Optional[int] = None) -> tuple:
    if not tokens or tokens <= 0:
        return None, "unknown"
    window = window or context_window(model_id)
    warn = window * warn_pct() // 100
    caution = warn * 6 // 10
    level = "warn" if tokens >= warn else "caution" if tokens >= caution else "ok"
    return round(tokens * 100 / window), level


def used_tokens(usage) -> Optional[int]:
    if not isinstance(usage, dict):
        return None
    total = 0
    for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = usage.get(key)
        total += value if isinstance(value, int) and not isinstance(value, bool) else 0
    return total


def read_ticket(title_dir: Path, session_id: str) -> str:
    try:
        with (title_dir / f"{session_id}.json").open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    ticket = data.get("ticket")
    if not isinstance(ticket, str) or not ticket.strip():
        return ""
    title = data.get("title")
    text = f"{ticket.strip()} - {title.strip()}" if isinstance(title, str) and title.strip() else ticket.strip()
    return text[:TICKET_MAX]


def _has_ipv4(iface: str) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            fcntl.ioctl(sock.fileno(), SIOCGIFADDR, struct.pack("256s", iface[:15].encode()))
        return True
    except OSError:
        return False


def vpn_state(sysfs: Optional[str] = None) -> Optional[str]:
    if kit_trabajo.variable("VPN_STATUSLINE_ENABLED") == "false":
        return None
    base = sysfs or kit_trabajo.variable("VPN_SYSFS_DIR") or "/sys/class/net"
    if not os.path.isdir(base):
        return None
    prefix = kit_trabajo.variable("VPN_INTERFACE") or "tun"
    for iface in sorted(glob.glob(os.path.join(glob.escape(base), glob.escape(prefix) + "*"))):
        if _has_ipv4(os.path.basename(iface)):
            return "up"
    return "down"


def ctx_dir() -> Path:
    return Path(os.environ.get("ORQ_CTX_DIR") or Path.home() / ".local" / "state" / "andokit" / "ctx")


def _int(value) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_timestamp(value) -> Optional[float]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_snapshot(directory: Path, session_id: str, last_assistant_ts: Optional[float]) -> Optional[dict]:
    if not isinstance(session_id, str) or not SESSION_ID.match(session_id):
        return None
    try:
        with (directory / f"{session_id}.json").open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("session_id") != session_id:
        return None
    pct, size, tokens = _int(data.get("pct")), _int(data.get("context_window_size")), _int(data.get("total_input_tokens"))
    ts = data.get("ts")
    if pct is None or pct < 0 or not size or size <= 0 or not tokens or tokens <= 0:
        return None
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return None
    if last_assistant_ts is not None and ts < last_assistant_ts - SNAPSHOT_TOLERANCE:
        return None
    model = data.get("model_id")
    return {"pct": pct, "window": size, "tokens": tokens, "model": model if isinstance(model, str) else ""}


def build(meta: dict, ticket: str, snapshot: Optional[dict] = None) -> dict:
    model_id = meta.get("model") or (snapshot or {}).get("model") or ""
    if snapshot:
        level = ctx_state(snapshot["tokens"], model_id, snapshot["window"])[1]
        pct = snapshot["pct"]
    else:
        pct, level = ctx_state(meta.get("tokens"), model_id)
    return {
        "model": model_name(model_id) if model_id else "",
        "ticket": ticket,
        "ctx_pct": pct,
        "ctx_level": level,
        "vpn": vpn_state(),
    }
