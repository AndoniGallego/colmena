import json
import re
from dataclasses import dataclass

from ..digest import SESSION_ID
from ..enchufe.ids import GUARDIAN_RE, ID_RE, PANE_RE, valido
from ..redaccion import redactar
from .colmena_gancho import EVENTOS

_MAX_ID = 128
_TOOL_USE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_ORIGENES = frozenset({"global", "settings"})
_CAMPOS_IDS = ("colmena", "herdr_pane", "herdr_tab", "herdr_workspace", "claude")
_VALIDADORES = {
    "colmena": GUARDIAN_RE,
    "herdr_pane": PANE_RE,
    "herdr_tab": ID_RE,
    "herdr_workspace": ID_RE,
    "claude": SESSION_ID,
}


@dataclass(frozen=True)
class Ids:
    colmena: str | None
    herdr_pane: str | None
    herdr_tab: str | None
    herdr_workspace: str | None
    claude: str | None


@dataclass(frozen=True)
class MensajeGancho:
    evento: str
    origen: str
    ids: Ids
    datos: dict

    @property
    def tool_use_id(self) -> str | None:
        valor = self.datos.get("tool_use_id")
        return valor if isinstance(valor, str) else None

    @property
    def herramienta(self) -> str | None:
        valor = self.datos.get("tool_name")
        return valor if isinstance(valor, str) else None


def _id_valido(campo: str, valor: object) -> bool:
    if valor is None:
        return True
    if not isinstance(valor, str) or len(valor) > _MAX_ID:
        return False
    return valido(_VALIDADORES[campo], valor)


def _tool_use_id_valido(valor: object) -> bool:
    if valor is None:
        return True
    if not isinstance(valor, str) or len(valor) > _MAX_ID:
        return False
    return _TOOL_USE_ID.fullmatch(valor) is not None


def parsear(linea: bytes) -> MensajeGancho | None:
    try:
        texto = linea.decode("utf-8").rstrip("\n")
        raw = json.loads(texto)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(raw, dict):
        return None
    v = raw.get("v")
    if type(v) is not int or v != 1:
        return None
    evento = raw.get("evento")
    if not isinstance(evento, str) or evento not in EVENTOS:
        return None
    origen = raw.get("origen")
    if not isinstance(origen, str) or origen not in _ORIGENES:
        return None
    datos = raw.get("datos")
    if not isinstance(datos, dict):
        return None
    ids_raw = raw.get("ids")
    if not isinstance(ids_raw, dict):
        return None
    for campo in _CAMPOS_IDS:
        if campo not in ids_raw or not _id_valido(campo, ids_raw.get(campo)):
            return None
    if not _tool_use_id_valido(datos.get("tool_use_id")):
        return None
    ids = Ids(
        colmena=ids_raw.get("colmena"),
        herdr_pane=ids_raw.get("herdr_pane"),
        herdr_tab=ids_raw.get("herdr_tab"),
        herdr_workspace=ids_raw.get("herdr_workspace"),
        claude=ids_raw.get("claude"),
    )
    return MensajeGancho(evento=evento, origen=origen, ids=ids, datos=datos)


def redactar_entrada(valor: object) -> object:
    if isinstance(valor, str):
        return redactar(valor)
    if isinstance(valor, dict):
        return {k: redactar_entrada(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [redactar_entrada(v) for v in valor]
    return valor
