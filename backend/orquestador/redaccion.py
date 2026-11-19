import re

OCULTO = "«oculto»"
ENV_OMITIDO = "«contenido de .env omitido»"

_KEY_VALUE = re.compile(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|authorization|auth)"
                        r"(\s*[=:]\s*|\s+)(\"[^\"]*\"|'[^']*'|\S+)")
_BEARER = re.compile(r"(?i)bearer\s+\S+")
_URL_CREDS = re.compile(r"://[^/\s:@]+:[^@\s]+@")
_KNOWN = re.compile(r"AKIA[0-9A-Z]{16}|ghp_\S+|github_pat_\S+|glpat-\S+|sk-[A-Za-z0-9_-]{10,}|xox[abpr]-\S+")
_MYSQL = re.compile(r"(?i)(\b(?:mysql|mariadb)\b[^|;&\n]*?\s)-p\S+")
_SSHPASS = re.compile(r"(?i)(\bsshpass\s+-p\s*)\S+")
_PASSWORD_FLAG = re.compile(r'(?i)(--password(?:\s+|=))("[^"]*"|\'[^\']*\'|\S+)')
_USER_PASS = re.compile(r"(\s(?:-u|--user)[\s=]+)([^\s:]+):\S+")

_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)")
_JWT = re.compile(r"eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}")
_AWS_SECRET = re.compile(r"(?i)(aws_secret_access_key[\"']?\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)")
_UPPER_ASSIGN = re.compile(r"\b([A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASS|PWD)[A-Z0-9_]*)(\s*=\s*)(\"[^\"]*\"|'[^']*'|\S+)")
_QUOTED_P = re.compile(r"(?<![\w-])-p('[^'\n]*'|\"[^\"\n]*\")")
_WORDS = r"(?:password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|authorization|auth)"
# En prosa ("el token de diseño") no se tapa nada: hace falta `=`, o `:` con un valor que parezca secreto.
_ASSIGN = re.compile(r"(?i)(\b\w*" + _WORDS + r"\w*[\"']?)(\s*=\s*)(\"[^\"]*\"|'[^']*'|\S+)")
_COLON = re.compile(r"(?i)(\b\w*" + _WORDS + r"\w*[\"']?)(\s*:\s*)(\"[^\"\n]{6,}\"|'[^'\n]{6,}'|(?=\S*\d)[^\s,;\"'}]{8,})")
_LONG_BLOB = re.compile(r"(?i)(\b\w*" + _WORDS + r"\w*[\"']?\s*[=:]\s*[\"']?)([A-Fa-f0-9]{40,}|[A-Za-z0-9+/_-]{40,}={0,2})")
_ENV_LINE = re.compile(r"^[A-Z][A-Z0-9_]{2,}=", re.M)


def redactar_basico(text: str) -> str:
    """Best-effort: solo para auditoría, avisos y títulos del tablero; lo que se ejecuta no se toca."""
    text = _BEARER.sub(OCULTO, text or "")
    text = _URL_CREDS.sub(f"://{OCULTO}@", text)
    text = _KNOWN.sub(OCULTO, text)
    text = _MYSQL.sub(lambda m: f"{m.group(1)}-p{OCULTO}", text)
    text = _SSHPASS.sub(lambda m: f"{m.group(1)}{OCULTO}", text)
    text = _USER_PASS.sub(lambda m: f"{m.group(1)}{m.group(2)}:{OCULTO}", text)
    return _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{OCULTO}", text)


def parece_env(text: str) -> bool:
    return len(_ENV_LINE.findall(text or "")) >= 3


def redactar(text: str) -> str:
    """Redacción para memoria (índice, Engram y citas). Best-effort: tapa formatos conocidos."""
    text = _PRIVATE_KEY.sub(OCULTO, text or "")
    text = _JWT.sub(OCULTO, text)
    text = _BEARER.sub(OCULTO, text)
    text = _URL_CREDS.sub(f"://{OCULTO}@", text)
    text = _KNOWN.sub(OCULTO, text)
    text = _PASSWORD_FLAG.sub(lambda m: f"{m.group(1)}{OCULTO}", text)
    text = _QUOTED_P.sub(f"-p{OCULTO}", text)
    text = _MYSQL.sub(lambda m: f"{m.group(1)}-p{OCULTO}", text)
    text = _SSHPASS.sub(lambda m: f"{m.group(1)}{OCULTO}", text)
    text = _USER_PASS.sub(lambda m: f"{m.group(1)}{m.group(2)}:{OCULTO}", text)
    text = _AWS_SECRET.sub(lambda m: f"{m.group(1)}{OCULTO}", text)
    text = _LONG_BLOB.sub(lambda m: f"{m.group(1)}{OCULTO}", text)
    text = _UPPER_ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}{OCULTO}", text)
    text = _ASSIGN.sub(_keep_hidden, text)
    return _COLON.sub(_keep_hidden, text)


def _keep_hidden(m: re.Match) -> str:
    return m.group(0) if OCULTO in m.group(3) else f"{m.group(1)}{m.group(2)}{OCULTO}"
