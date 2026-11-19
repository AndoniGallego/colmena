"""Parser puro de los diálogos de Claude Code (permisos y AskUserQuestion). Falla cerrado: ante la duda, `desconocido`."""
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

TESTED_VERSION = "2.1.316"
ALLOWED_KEYS = frozenset({"1", "2", "3", "4", "5", "6", "7", "8", "9", "derecha", "enter"})
MAX_DETALLE = 4000
SCREEN_LINES = 30
HEADERS = {"Bash command": "Bash", "Create file": "Write", "Edit file": "Edit"}

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
CTRL_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f  ]")
OPTION_RE = re.compile(r"^\s*(❯\s*)?(\d+)\.\s+(.+?)\s*$")
TOP_RE = re.compile(r"^\s*─{10,}\s*$")
SEP_RE = re.compile(r"^\s*─{3,}\s*$")
DASH_RE = re.compile(r"^\s*╌{5,}\s*$")
SUBMIT_ROW_RE = re.compile(r"^(\s*)(❯)?\s*Submit$")
FOOTER_RE = re.compile(
    r"^(?:Enter to select · (?:↑/↓|Tab/Arrow keys) to navigate · )?(?:ctrl\+g to edit in Vim · )?"
    r"Esc to cancel(?: · Tab to amend)?$")
SPACES = re.compile(r"\s+")

QUESTION_RES = {
    "Bash": re.compile(r"^Do you want to proceed\?$"),
    "Write": re.compile(r"^Do you want to create (.+)\?$"),
    "Edit": re.compile(r"^Do you want to make this edit to (.+)\?$"),
}
YES_RE = re.compile(r"^Yes$")
YES_DONT_ASK_RE = re.compile(r"^Yes, and don't ask again for: (.+)$")
YES_DIR_RE = re.compile(r"^Yes, and always allow access to (.+) from this project$")
MODE_AUTO_RE = re.compile(r"^Yes, and switch to auto mode\b")
MODE_EDITS_RE = re.compile(r"^Yes, and switch to accept edits\b")
NO_RE = re.compile(r"^No$")
TYPE_SOMETHING = "Type something."
TYPE_SOMETHING_MULTI = "[ ] Type something"
CHAT_ABOUT = "Chat about this"
BOX_RE = re.compile(r"^\[( |✔)\] (.+)$")
MAX_PREGUNTAS = 4
MAX_OPCIONES = 6


def norm(text: str) -> str:
    return SPACES.sub(" ", str(text).replace("’", "'")).strip()


def squash(text: str) -> str:
    return SPACES.sub("", str(text).replace("’", "'"))


@dataclass
class Dialogo:
    tipo: str = "desconocido"
    razon: str = ""
    herramienta: str = ""
    tool_use_id: str = ""
    bloque: str = ""
    opciones: list = field(default_factory=list)
    digitos: dict = field(default_factory=dict)
    regla: Optional[str] = None
    mas_en_terminal: bool = False
    descripcion: str = ""
    detalle: str = ""
    completo: bool = True
    archivo: str = ""
    replace_all: bool = False
    pregunta: Optional[dict] = None
    cabecera: tuple = ()
    pendientes_ids: tuple = ()


def desconocido(razon: str) -> Dialogo:
    return Dialogo(tipo="desconocido", razon=razon)


@dataclass
class Fila:
    num: int
    texto: str
    extra: list
    cursor: bool
    idx: int


@dataclass
class Estructura:
    lines: list
    top: int
    first: int
    end: int
    filas: list
    sep_before: Optional[int]
    footer: str
    submit: Optional[bool] = None


def clean_screen(screen: str) -> tuple:
    """Devuelve (líneas limpias, líneas que traían ANSI o control)."""
    lines, dirty = [], []
    for raw in str(screen).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        no_ansi = ANSI_RE.sub("", raw)
        dirty.append(no_ansi != raw or bool(CTRL_RE.search(no_ansi.replace("\t", " "))))
        lines.append(CTRL_RE.sub("", no_ansi.replace("\t", " ")).rstrip())
    return lines, dirty


def screen_tail(screen: str, count: int = SCREEN_LINES) -> str:
    lines, _ = clean_screen(screen)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines[-count:])


def _scan(screen: str) -> Optional[Estructura]:
    lines, dirty = clean_screen(screen)
    end = len(lines) - 1
    while end >= 0 and not lines[end].strip():
        end -= 1
    if end < 0:
        return None
    footer = ""
    footer_idx = None
    if FOOTER_RE.match(norm(lines[end])):
        footer, footer_idx = norm(lines[end]), end
        end -= 1
        while end >= 0 and not lines[end].strip():
            end -= 1
        if end < 0:
            return None
    start = end
    while start > 0 and lines[start - 1].strip():
        start -= 1
    first = next((i for i in range(start, end + 1) if OPTION_RE.match(lines[i])), None)
    if first is None:
        return None
    col = OPTION_RE.match(lines[first]).start(2)
    filas: list = []
    sep_before = None
    after_sep = False
    submit: Optional[bool] = None
    for i in range(first, end + 1):
        line = lines[i]
        match = OPTION_RE.match(line)
        if match:
            if match.start(2) != col:
                return None
            filas.append(Fila(int(match.group(2)), match.group(3).strip(), [], bool(match.group(1)), i))
            after_sep = False
        elif SEP_RE.match(line):
            if sep_before is not None or not filas:
                return None
            sep_before = len(filas)
            after_sep = True
        elif (sub := SUBMIT_ROW_RE.match(line)) and filas and not after_sep and submit is None \
                and len(line) - len(line.lstrip(" ❯")) > col:
            submit = bool(sub.group(2))
        else:
            stripped = line.strip()
            if not filas or after_sep or len(line) - len(line.lstrip()) <= col or stripped[0].isdigit() or "❯" in line:
                return None
            filas[-1].extra.append(stripped)
    if after_sep or [f.num for f in filas] != list(range(1, len(filas) + 1)) or filas[0].num != 1:
        return None
    if sum(1 for f in filas if f.cursor) + (1 if submit else 0) != 1:
        return None
    top = next((i for i in range(first - 1, -1, -1) if TOP_RE.match(lines[i])), None)
    if top is None:
        return None
    check = range(top, (footer_idx if footer_idx is not None else end) + 1)
    if any(dirty[i] for i in check):
        return None
    return Estructura(lines, top, first, end, filas, sep_before, footer, submit)


def _head(est: Estructura) -> list:
    return [norm(l) for l in est.lines[est.top + 1:est.first] if l.strip()]


def _bloque(est: Estructura) -> str:
    rows = [SPACES.sub(" ", l.replace("❯", " ").replace("’", "'")).strip() for l in est.lines[est.top:est.end + 1]]
    return "\n".join(r for r in rows if r)


def huella(pane_id: str, session_id: str, seq, dialogo: Dialogo) -> str:
    raw = "|".join([pane_id, session_id, str(seq), dialogo.tool_use_id, dialogo.bloque])
    return hashlib.sha256(raw.encode()).hexdigest()


def _file_matches(shown: str, file_path: str, cwd: str) -> bool:
    shown = norm(shown)
    if not shown or not file_path:
        return False
    if shown == file_path or shown == file_path.rsplit("/", 1)[-1]:
        return True
    if cwd:
        prefix = cwd.rstrip("/") + "/"
        return file_path.startswith(prefix) and shown == file_path[len(prefix):]
    return False


def _input(tool_use: dict) -> dict:
    data = tool_use.get("input")
    return data if isinstance(data, dict) else {}


def _str(value) -> str:
    return value if isinstance(value, str) else ""


def _diff(old: str, new: str) -> str:
    return "\n".join(["- " + l for l in old.split("\n")] + ["+ " + l for l in new.split("\n")])


def tiene_invisibles(*texts: str) -> bool:
    return any(unicodedata.category(c) == "Cf" for t in texts for c in t)


def visibles(text: str) -> str:
    """Muestra los caracteres de formato invisibles (bidi, ancho cero) como ⟨U+202E⟩."""
    return "".join(f"⟨U+{ord(c):04X}⟩" if unicodedata.category(c) == "Cf" else c for c in text)


def _clip_detail(text: str) -> tuple:
    return (text[:MAX_DETALLE], False) if len(text) > MAX_DETALLE else (text, True)


def _classify_permiso(filas: list, herramienta: str) -> Optional[dict]:
    kinds: dict = {}
    for fila in filas:
        text = norm(" ".join([fila.texto] + fila.extra))
        if YES_RE.match(text):
            kind, extra = "yes", None
        elif (m := YES_DONT_ASK_RE.match(text)):
            if herramienta != "Bash" or not m.group(1).endswith(" *"):
                return None
            kind, extra = "yes_dont_ask", m.group(1)
        elif (m := YES_DIR_RE.match(text)):
            if herramienta != "Bash":
                return None
            kind, extra = "yes_dir", m.group(1)
        elif MODE_AUTO_RE.match(text):
            if herramienta != "Bash":
                return None
            kind, extra = "mode_auto", None
        elif MODE_EDITS_RE.match(text):
            if herramienta == "Bash":
                return None
            kind, extra = "mode_edits", None
        elif NO_RE.match(text):
            kind, extra = "no", None
        else:
            return None
        if kind in kinds:
            return None
        kinds[kind] = (fila.num, extra)
    if "yes" not in kinds or "no" not in kinds:
        return None
    return kinds


_SPOOF_RES = (re.compile(r"─{10,}"), re.compile(r"╌{5,}"))
_SPOOF_FIELDS = ("command", "description", "file_path")


def _imita_pantalla(tool_use: dict) -> bool:
    """Un campo que dibuja bordes, cabeceras o preguntas del diálogo puede confundir al parser."""
    for key in _SPOOF_FIELDS:
        text = _str(_input(tool_use).get(key))
        if any(r.search(text) for r in _SPOOF_RES) or "❯" in text:
            return True
        for line in text.split("\n"):
            line = norm(line)
            if line in HEADERS or OPTION_RE.match(line) or any(q.match(line) for q in QUESTION_RES.values()):
                return True
    return False


def _parse_permiso(est: Estructura, pendientes: list, cwd: str) -> Dialogo:
    head = _head(est)
    herramienta = HEADERS.get(head[0]) if head else None
    if herramienta is None:
        return desconocido("herramienta sin soporte")
    qmatch = QUESTION_RES[herramienta].match(head[-1]) if len(head) > 1 else None
    if qmatch is None:
        return desconocido("pregunta no reconocida")
    body = head[1:-1]
    if herramienta == "Bash" and body and body[-1] == "This command requires approval":
        body = body[:-1]
    dashes = [i for i, l in enumerate(body) if DASH_RE.match(l)]
    if len(dashes) != 2 or body[dashes[1] + 1:]:
        return desconocido("cuerpo del diálogo no reconocido")
    pre, middle = body[:dashes[0]], body[dashes[0] + 1:dashes[1]]
    kinds = _classify_permiso(est.filas, herramienta) if est.submit is None else None
    if kinds is None:
        return desconocido("opciones no reconocidas")
    if any(_imita_pantalla(p) for p in pendientes):
        return desconocido("un comando imita la pantalla del diálogo")
    matches = []
    for tool_use in pendientes:
        if _str(tool_use.get("name")) != herramienta or not _str(tool_use.get("id")):
            continue
        data = _input(tool_use)
        if herramienta == "Bash":
            shown_desc = squash("".join(l for l in pre if not l.startswith("Tip:")))
            ok = squash(_str(data.get("command"))) == squash("".join(middle)) and \
                squash(_str(data.get("description"))) == shown_desc
        else:
            path = _str(data.get("file_path"))
            ok = len(pre) == 1 and _file_matches(pre[0], path, cwd) and _file_matches(qmatch.group(1), path, cwd)
        if ok:
            matches.append(tool_use)
    if len(matches) != 1:
        return desconocido("no coincide con el transcript")
    tool_use = matches[0]
    data = _input(tool_use)
    offered = []
    for fila in est.filas:
        for kind, label in (("yes", "si"), ("yes_dont_ask", "si_siempre"), ("mode_auto", "si_auto"),
                            ("mode_edits", "si_ediciones"), ("no", "no")):
            if kind in kinds and kinds[kind][0] == fila.num:
                offered.append(label)
    dialogo = Dialogo(
        tipo="permiso", herramienta=herramienta, tool_use_id=tool_use["id"], bloque=_bloque(est),
        opciones=offered, digitos={k: v[0] for k, v in kinds.items()},
        regla=kinds["yes_dont_ask"][1] if "yes_dont_ask" in kinds else None,
        mas_en_terminal="yes_dir" in kinds,
        pendientes_ids=tuple(_str(p.get("id")) for p in pendientes))
    if herramienta == "Bash":
        dialogo.descripcion = _str(data.get("description"))
        full = _str(data.get("command"))
    elif herramienta == "Write":
        dialogo.archivo = _str(data.get("file_path"))
        full = _str(data.get("content"))
    else:
        dialogo.archivo = _str(data.get("file_path"))
        dialogo.replace_all = data.get("replace_all") is True
        full = _diff(_str(data.get("old_string")), _str(data.get("new_string")))
    dialogo.detalle, dialogo.completo = _clip_detail(full)
    if tiene_invisibles(full, dialogo.descripcion, dialogo.archivo, dialogo.regla or ""):
        dialogo.completo = False
    return dialogo


def _tabs(preguntas: list, marcas: list) -> str:
    """Barra de pestañas esperada: una pregunta simple lleva solo su cabecera; si no, flechas y "Submit"."""
    if len(preguntas) == 1 and not preguntas[0]["multi"]:
        return f"☐ {norm(preguntas[0]['header'])}"
    cuerpo = " ".join(f"{'☒' if m else '☐'} {norm(q['header'])}" for q, m in zip(preguntas, marcas))
    return f"← {cuerpo} ✔ Submit →"


def _preguntas_del_transcript(ask: dict) -> Optional[list]:
    raw = _input(ask).get("questions")
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_PREGUNTAS or not all(isinstance(q, dict) for q in raw):
        return None
    out = []
    for q in raw:
        text, header = _str(q.get("question")), _str(q.get("header"))
        options, multi = q.get("options"), q.get("multiSelect")
        if not text or not header or not isinstance(multi, bool) or not isinstance(options, list) \
                or not 1 <= len(options) <= MAX_OPCIONES:
            return None
        labels, descs = [], []
        for option in options:
            if not isinstance(option, dict) or not _str(option.get("label")):
                return None
            labels.append(option["label"])
            descs.append(_str(option.get("description")))
        if len({norm(l) for l in labels}) != len(labels):
            return None
        if multi and any("," in l for l in labels):
            return None
        out.append({"question": text, "header": header, "multi": multi, "labels": labels, "descs": descs})
    if len({norm(q["question"]) for q in out}) != len(out) or len({norm(q["header"]) for q in out}) != len(out):
        return None
    return out


def _filas_pregunta(est: Estructura, q: dict) -> Optional[frozenset]:
    """Casillas marcadas de la pantalla de esa pregunta (vacío en las simples); None si no coincide exacto."""
    count, filas, labels = len(q["labels"]), est.filas, q["labels"]
    if len(filas) != count + 2 or est.sep_before != count + 1 or filas[count + 1].texto != CHAT_ABOUT \
            or filas[count + 1].extra or filas[count].extra:
        return None
    if not q["multi"]:
        if est.submit is not None or filas[count].texto != TYPE_SOMETHING:
            return None
        return frozenset() if all(norm(filas[i].texto) == norm(labels[i]) for i in range(count)) else None
    if est.submit is None or norm(filas[count].texto) != TYPE_SOMETHING_MULTI:
        return None
    marcadas = set()
    for i, label in enumerate(labels):
        box = BOX_RE.match(norm(filas[i].texto))
        if not box or box.group(2) != norm(label):
            return None
        if box.group(1) == "✔":
            marcadas.add(i)
    return frozenset(marcadas)


def _pestania(est: Estructura, preguntas: list) -> Optional[tuple]:
    head = _head(est)
    if len(head) < 2:
        return None
    texto = norm(" ".join(head[1:]))
    for i, q in enumerate(preguntas):
        if texto != norm(q["question"]):
            continue
        marcadas = _filas_pregunta(est, q)
        if marcadas is None:
            return None
        marcas = [True] * i + [bool(marcadas)] + [False] * (len(preguntas) - i - 1)
        return (i, marcadas) if head[0] == _tabs(preguntas, marcas) else None
    return None


def _revision(est: Estructura, preguntas: list) -> Optional[list]:
    head = _head(est)
    if len(preguntas) == 1 and not preguntas[0]["multi"]:
        return None
    if est.sep_before is not None or est.submit is not None or len(est.filas) != 2 or any(f.extra for f in est.filas) \
            or [f.texto for f in est.filas] != ["Submit answers", "Cancel"]:
        return None
    if len(head) < 3 or head[0] != _tabs(preguntas, [True] * len(preguntas)) or head[1] != "Review your answers" \
            or head[-1] != "Ready to submit your answers?":
        return None
    pares: list = []
    campo = None
    for line in head[2:-1]:
        if line.startswith("● "):
            pares.append([line[2:].strip(), None])
            campo = 0
        elif line.startswith("→ ") and pares and pares[-1][1] is None:
            pares[-1][1] = line[2:].strip()
            campo = 1
        elif pares and campo is not None:
            pares[-1][campo] = f"{pares[-1][campo]} {line}"
        else:
            return None
    return [(q, a) for q, a in pares] if pares and all(a is not None for _, a in pares) else None


def _parse_pregunta(est: Estructura, pendientes: list) -> Dialogo:
    asks = [p for p in pendientes if _str(p.get("name")) == "AskUserQuestion"]
    if len(pendientes) != 1 or len(asks) != 1 or not _str(asks[0].get("id")):
        return desconocido("no hay un único AskUserQuestion pendiente")
    preguntas = _preguntas_del_transcript(asks[0])
    if preguntas is None:
        return desconocido("transcript ilegible")
    if any(tiene_invisibles(q["question"], q["header"], *q["labels"], *q["descs"]) for q in preguntas):
        return desconocido("caracteres invisibles en la pregunta")
    actual = _pestania(est, preguntas)
    if actual is None or actual[0] != 0 or actual[1]:
        return desconocido("la pantalla no está en la primera pregunta, o ya hay respuestas")
    primera = preguntas[0]
    count = len(primera["labels"])
    solo = len(preguntas) == 1 and not primera["multi"]
    return Dialogo(
        tipo="pregunta", herramienta="AskUserQuestion", tool_use_id=asks[0]["id"], bloque=_bloque(est),
        digitos={"labels": [f.num for f in est.filas[:count]], "type_something": est.filas[count].num},
        mas_en_terminal=True, cabecera=tuple(_head(est)), pendientes_ids=(asks[0]["id"],),
        pregunta={"preguntas": [{"header": q["header"], "texto": q["question"], "multi": q["multi"], "otro": solo,
                                 "opciones": [{"label": l, "descripcion": d} for l, d in zip(q["labels"], q["descs"])]}
                                for q in preguntas]})


def _preguntas_de(dialogo: Dialogo) -> list:
    return [{"question": q["texto"], "header": q["header"], "multi": q["multi"],
             "labels": [o["label"] for o in q["opciones"]]} for q in dialogo.pregunta["preguntas"]]


def estado_pregunta(screen: str, dialogo: Dialogo) -> Optional[dict]:
    """Dónde está la pantalla dentro de un cuestionario: una pestaña (con sus casillas) o la revisión. Solo para verificar pasos."""
    try:
        if dialogo.tipo != "pregunta":
            return None
        est = _scan(screen)
        if est is None:
            return None
        preguntas = _preguntas_de(dialogo)
        actual = _pestania(est, preguntas)
        if actual is not None:
            return {"kind": "pestania", "i": actual[0], "casillas": actual[1]}
        pares = _revision(est, preguntas)
        return {"kind": "revision", "pares": pares} if pares is not None else None
    except Exception:
        return None


def parse_dialog(screen: str, pendientes: list, cwd: str = "") -> Dialogo:
    """Nunca lanza: cualquier cosa rara es `desconocido`."""
    try:
        est = _scan(screen)
        if est is None:
            return desconocido("formato no reconocido")
        pend = [p for p in (pendientes or []) if isinstance(p, dict)]
        if not pend:
            return desconocido("sin herramienta pendiente en el transcript")
        head = _head(est)
        if not head:
            return desconocido("formato no reconocido")
        if "☐" in head[0] or "☒" in head[0]:
            return _parse_pregunta(est, pend)
        return _parse_permiso(est, pend, cwd)
    except Exception:
        return desconocido("error al interpretar la pantalla")


def campo_abierto(screen: str, dialogo: Dialogo) -> Optional[str]:
    """Si el campo de "Type something" está abierto, el texto de esa fila (la etiqueta si no se tipeó nada)."""
    try:
        if dialogo.tipo != "pregunta":
            return None
        est = _scan(screen)
        if est is None or "ctrl+g to edit in Vim" not in est.footer or tuple(_head(est)) != dialogo.cabecera:
            return None
        labels = [o["label"] for o in dialogo.pregunta["preguntas"][0]["opciones"]]
        count = len(labels)
        filas = est.filas
        if len(filas) != count + 2 or est.sep_before != count + 1 or filas[count].num != dialogo.digitos["type_something"]:
            return None
        if not filas[count].cursor or any(f.cursor for i, f in enumerate(filas) if i != count):
            return None
        if any(norm(filas[i].texto) != norm(labels[i]) for i in range(count)) or filas[count + 1].texto != CHAT_ABOUT:
            return None
        return norm(" ".join([filas[count].texto] + filas[count].extra))
    except Exception:
        return None
