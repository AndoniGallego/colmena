"""Instala el kit personal (kit/) en ~/.claude y ~/.local: symlinks, hooks y units."""

import copy
import filecmp
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import kit_trabajo

REPO_ROOT = Path(__file__).resolve().parents[2]
KIT_DIR = REPO_ROOT / "kit"

_LINEA_CONFIG = re.compile(r"^\s*(?:export\s+)?(ANDOKIT_[A-Z_]+)=(.*)$")


class KitInvalido(Exception):
    pass


@dataclass(frozen=True)
class Destinos:
    bin: Path
    skills: Path
    rules: Path
    hooks: Path
    settings: Path
    systemd: Path
    state: Path
    no_reload: bool
    repo_viejo: Path


@dataclass(frozen=True)
class Item:
    origen: Path
    destino: Path
    tipo: str


@dataclass
class Reporte:
    lineas: list[str] = field(default_factory=list)
    drift: bool = False
    fallo: bool = False
    items: list[dict] = field(default_factory=list)

    def item(self, tipo: str, nombre: str, estado: str, detalle: str = "") -> None:
        self.items.append(
            {"tipo": tipo, "nombre": nombre, "estado": estado, "detalle": detalle}
        )


_TIPO_VISTA = {"rules": "regla", "skills": "skill", "hooks": "hook", "bin": "bin"}


def _tipo_de_carpeta(p: Path, d: "Destinos") -> str:
    for tipo, carpeta in (
        ("regla", d.rules),
        ("skill", d.skills),
        ("hook", d.hooks),
        ("bin", d.bin),
    ):
        if p.parent == carpeta:
            return tipo
    return "bin"


def _expandir(valor: str, home: Path) -> str:
    valor = valor.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        valor = valor[1:-1]
    if valor == "~" or valor.startswith("~/"):
        valor = str(home) + valor[1:]
    return valor.replace("${HOME}", str(home)).replace("$HOME", str(home))


def _leer_config_local(path: Path, home: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    vals: dict[str, str] = {}
    for linea in path.read_text(encoding="utf-8").splitlines():
        m = _LINEA_CONFIG.match(linea)
        if m:
            vals[m.group(1)] = _expandir(m.group(2), home)
    return vals


def destinos(env: Mapping[str, str], home: Path, kit_dir: Path) -> Destinos:
    vals = dict(env)
    if not env.get("ANDOKIT_NO_CONFIG_LOCAL"):
        vals.update(_leer_config_local(kit_dir / "config.local", home))

    def ruta(clave: str, default: Path) -> Path:
        v = vals.get(clave)
        return Path(v) if v else default

    return Destinos(
        bin=ruta("ANDOKIT_BIN_DIR", home / ".local" / "bin"),
        skills=ruta("ANDOKIT_SKILLS_DIR", home / ".claude" / "skills"),
        rules=ruta("ANDOKIT_RULES_DIR", home / ".claude" / "rules"),
        hooks=ruta("ANDOKIT_HOOKS_DIR", home / ".claude" / "hooks"),
        settings=ruta("ANDOKIT_SETTINGS", home / ".claude" / "settings.json"),
        systemd=ruta("ANDOKIT_SYSTEMD_DIR", home / ".config" / "systemd" / "user"),
        state=ruta("ANDOKIT_STATE_DIR", home / ".local" / "state" / "andokit"),
        no_reload=bool(vals.get("ANDOKIT_NO_RELOAD")),
        repo_viejo=ruta("ANDOKIT_REPO_VIEJO", home / "Proyectos" / "andokit"),
    )


def items_kit(kit_dir: Path, d: Destinos) -> list[Item]:
    items: list[Item] = []
    for sub in ("bin", "statusline"):
        items += [
            Item(f, d.bin / f.name, "bin")
            for f in sorted((kit_dir / sub).glob("*"))
            if f.is_file()
        ]
    items += [
        Item(p, d.skills / p.name, "skills")
        for p in sorted((kit_dir / "skills").glob("*"))
        if p.is_dir()
    ]
    items += [
        Item(f, d.rules / f.name, "rules")
        for f in sorted((kit_dir / "reglas").glob("*/*.md"))
    ]
    items += [
        Item(f, d.hooks / f.name, "hooks")
        for f in sorted((kit_dir / "ganchos").glob("*.sh"))
    ]
    vistos: dict[Path, Path] = {}
    for it in items:
        if it.destino in vistos:
            raise KitInvalido(
                f"{it.origen} y {vistos[it.destino]} van al mismo destino {it.destino}"
            )
        vistos[it.destino] = it.origen
    return items


def _es_nuestro(objetivo: str, raices: tuple[Path, ...]) -> bool:
    p = Path(objetivo)
    return any(p == r or r in p.parents for r in raices)


def _respaldar(destino: Path, tipo: str, respaldo: Path, rep: Reporte) -> bool:
    carpeta = respaldo / tipo
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        shutil.move(str(destino), str(carpeta / destino.name))
    except OSError as e:
        rep.lineas.append(f"  ERROR: no pude respaldar {destino}: {e}")
        rep.fallo = True
        return False
    rep.lineas.append(f"  respaldo: {destino} -> {carpeta}/")
    return True


def _enlazar_atomico(origen: Path, destino: Path) -> None:
    tmp = destino.parent / f".{destino.name}.kit-tmp"
    if os.path.lexists(tmp):
        tmp.unlink()
    os.symlink(origen, tmp)
    os.replace(tmp, destino)


def _huerfanos(items: list[Item], d: Destinos, raices: tuple[Path, ...]) -> list[Path]:
    esperados = {it.destino for it in items}
    sobran: list[Path] = []
    for carpeta in (d.bin, d.skills, d.rules, d.hooks):
        if not carpeta.is_dir():
            continue
        for p in sorted(carpeta.iterdir()):
            if (
                p.is_symlink()
                and p not in esperados
                and _es_nuestro(os.readlink(p), raices)
            ):
                sobran.append(p)
    return sobran


def aplicar_links(
    items: list[Item],
    d: Destinos,
    modo: str,
    reporte: Reporte,
    respaldo: Path,
    kit_dir: Path = KIT_DIR,
) -> None:
    raices = (kit_dir, d.repo_viejo)
    for it in items:
        actual = os.readlink(it.destino) if it.destino.is_symlink() else None
        if actual == str(it.origen):
            if modo == "check":
                reporte.lineas.append(f"OK       {it.destino}")
                reporte.item(_TIPO_VISTA.get(it.tipo, it.tipo), it.destino.name, "ok")
            continue
        existe = os.path.lexists(it.destino)
        if modo == "check":
            reporte.lineas.append(
                f"{'AJENO   ' if existe else 'FALTA   '} {it.destino}"
            )
            reporte.drift = True
            reporte.item(
                _TIPO_VISTA.get(it.tipo, it.tipo),
                it.destino.name,
                "ajeno" if existe else "falta",
            )
            continue
        reporte.lineas.append(f"link     {it.destino} -> {it.origen}")
        if modo == "ensayo":
            continue
        it.destino.parent.mkdir(parents=True, exist_ok=True)
        if actual is not None and _es_nuestro(actual, raices):
            _enlazar_atomico(it.origen, it.destino)
            continue
        if existe and not _respaldar(it.destino, it.tipo, respaldo, reporte):
            continue
        os.symlink(it.origen, it.destino)
    for p in _huerfanos(items, d, raices):
        if modo == "check":
            reporte.lineas.append(f"SOBRA    {p}")
            reporte.drift = True
            reporte.item(_tipo_de_carpeta(p, d), p.name, "sobra")
        else:
            reporte.lineas.append(f"saco     {p}")
            if modo == "instalar":
                p.unlink()


# --- settings.json, statusline y units ---

MARCA_HOOK = "/andokit-"


def units_kit() -> tuple:
    return tuple(kit_trabajo.valor("units"))


_STATUSLINE = "andokit-statusline"


def hooks_deseados(hooks_dir: Path) -> dict:
    return {
        "PreToolUse": [
            {
                "matcher": "AskUserQuestion",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{hooks_dir}/andokit-sin-askuser.sh",
                        "timeout": 5,
                    }
                ],
            }
        ],
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{hooks_dir}/andokit-stop-bloques.sh",
                        "timeout": 10,
                    }
                ]
            }
        ],
    }


def _es_grupo_kit(grupo: dict) -> bool:
    return any(MARCA_HOOK in str(h.get("command", "")) for h in grupo.get("hooks", []))


def fusionar_hooks(settings: dict, deseados: dict) -> dict:
    nuevo = copy.deepcopy(settings)
    hooks = nuevo.setdefault("hooks", {})
    for evento, grupos in deseados.items():
        ajenos = [g for g in hooks.get(evento, []) if not _es_grupo_kit(g)]
        hooks[evento] = ajenos + copy.deepcopy(grupos)
    return nuevo


def fusionar_statusline(settings: dict, bin_dir: Path) -> dict:
    nuevo = copy.deepcopy(settings)
    if "statusLine" not in nuevo:
        base = (
            "$HOME/.local/bin"
            if bin_dir == Path.home() / ".local" / "bin"
            else str(bin_dir)
        )
        nuevo["statusLine"] = {"type": "command", "command": f"{base}/{_STATUSLINE}"}
    return nuevo


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def escribir_settings(
    path: Path, nuevo: dict, respaldo: Path, reporte: Reporte
) -> None:
    real = path.resolve()
    existe = real.exists()
    tmp = None
    try:
        antes = _sha256(real) if existe else None
        modo = (real.stat().st_mode & 0o777) if existe else 0o600
        if existe:
            carpeta = respaldo / "settings"
            carpeta.mkdir(parents=True, exist_ok=True)
            shutil.copy2(real, carpeta / real.name)
            reporte.lineas.append(f"  respaldo: {real} -> {carpeta}/")
        real.parent.mkdir(parents=True, exist_ok=True)
        texto = json.dumps(nuevo, indent=2, ensure_ascii=False) + "\n"
        json.loads(texto)
        fd, tmp = tempfile.mkstemp(
            dir=real.parent, prefix=f".{real.name}.", suffix=".kit-tmp"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.chmod(tmp, modo)
        despues = _sha256(real) if real.exists() else None
        if despues != antes:
            raise OSError("cambió mientras lo escribía; no lo piso")
        os.replace(tmp, real)
        tmp = None
    except (OSError, ValueError) as e:
        reporte.lineas.append(f"FAILED   {path}: {e}")
        reporte.fallo = True
    finally:
        if tmp is not None and os.path.lexists(tmp):
            os.unlink(tmp)


def _estado_hooks(actual: dict, deseados: dict) -> str:
    hooks = actual.get("hooks", {})
    nuestros = {
        ev: [g for g in hooks.get(ev, []) if _es_grupo_kit(g)] for ev in deseados
    }
    if nuestros == deseados:
        return "OK      "
    return "DISTINTA" if any(nuestros.values()) else "FALTA   "


def _settings(d: Destinos, modo: str, respaldo: Path, rep: Reporte) -> None:
    real = d.settings.resolve()
    try:
        actual = json.loads(real.read_text(encoding="utf-8")) if real.exists() else {}
        if not isinstance(actual, dict):
            raise ValueError("no es un objeto JSON")
    except (OSError, ValueError) as e:
        rep.lineas.append(f"FAILED   {d.settings}: no lo puedo leer, no lo toco ({e})")
        rep.fallo = True
        rep.item("settings", "settings", "error", str(e))
        return
    deseados = hooks_deseados(d.hooks)
    nuevo = fusionar_statusline(fusionar_hooks(actual, deseados), d.bin)
    if modo == "check":
        estado = _estado_hooks(actual, deseados)
        rep.lineas.append(f"{estado} {d.settings} (hooks)")
        rep.drift |= estado.strip() != "OK"
        rep.item("settings", "hooks", estado.strip().lower())
        linea = actual.get("statusLine")
        if linea is None:
            rep.lineas.append(f"FALTA    {d.settings} (statusLine)")
            rep.drift = True
            rep.item("settings", "statusLine", "falta")
        elif _STATUSLINE not in str(
            linea.get("command", "") if isinstance(linea, dict) else linea
        ):
            rep.lineas.append(f"INFO     {d.settings} (statusLine ajeno, no lo toco)")
            rep.item("settings", "statusLine", "info")
        else:
            rep.item("settings", "statusLine", "ok")
        return
    if nuevo == actual:
        return
    rep.lineas.append(f"settings {d.settings}")
    if modo == "instalar":
        escribir_settings(d.settings, nuevo, respaldo, rep)


def _units(
    deploy_dir: Path, d: Destinos, modo: str, respaldo: Path, rep: Reporte
) -> bool:
    cambio = False
    for u in units_kit():
        origen, destino = deploy_dir / u, d.systemd / u
        if destino.is_file() and filecmp.cmp(origen, destino, shallow=False):
            if modo == "check":
                rep.lineas.append(f"OK       {destino}")
                rep.item("unit", u, "ok")
            continue
        existe = os.path.lexists(destino)
        if modo == "check":
            rep.lineas.append(f"{'DISTINTA' if existe else 'FALTA   '} {destino}")
            rep.drift = True
            rep.item("unit", u, "distinta" if existe else "falta")
            continue
        rep.lineas.append(f"unit     {destino}")
        if modo == "ensayo":
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        if existe and not _respaldar(destino, "systemd", respaldo, rep):
            continue
        shutil.copyfile(origen, destino)
        cambio = True
    return cambio


def chequear_kit(
    kit_dir: Path, deploy_dir: Path, d: Destinos, units: bool = True
) -> Reporte:
    rep = Reporte()
    try:
        aplicar_links(items_kit(kit_dir, d), d, "check", rep, d.state / "backup", kit_dir=kit_dir)
    except KitInvalido as e:
        rep.lineas.append(f"ERROR: {e}")
        rep.fallo = True
        rep.item("kit", "kit", "error", str(e))
        return rep
    _settings(d, "check", d.state / "backup", rep)
    if units:
        _units(deploy_dir, d, "check", d.state / "backup", rep)
    return rep


def instalar_kit(
    kit_dir: Path,
    deploy_dir: Path,
    d: Destinos,
    modo: str,
    imprimir: Callable[[str], None],
    correr: Callable[[list[str]], int],
    ahora: Callable[[], datetime],
    units: bool = True,
) -> int:
    rep = Reporte()
    respaldo = d.state / "backup" / ahora().strftime("%Y%m%d-%H%M%S")
    aplicar_links(items_kit(kit_dir, d), d, modo, rep, respaldo, kit_dir=kit_dir)
    _settings(d, modo, respaldo, rep)
    cambio = _units(deploy_dir, d, modo, respaldo, rep) if units else False
    if cambio and modo == "instalar" and not d.no_reload:
        if correr(["systemctl", "--user", "daemon-reload"]) != 0:
            rep.lineas.append(
                "AVISO    systemctl --user daemon-reload falló; correlo a mano"
            )
    for linea in rep.lineas:
        imprimir(linea)
    if modo == "check":
        imprimir("hay drift" if rep.drift else "sin drift")
        return 1 if rep.drift or rep.fallo else 0
    return 1 if rep.fallo else 0


def _statusline_en_uso(settings: dict) -> bool:
    linea = settings.get("statusLine")
    return isinstance(linea, dict) and str(linea.get("command", "")).endswith(
        _STATUSLINE
    )


def desinstalar_kit(kit_dir: Path, d: Destinos, imprimir: Callable[[str], None]) -> int:
    rep = Reporte()
    respaldo = d.state / "backup" / datetime.now().strftime("%Y%m%d-%H%M%S")
    real = d.settings.resolve()
    try:
        actual = json.loads(real.read_text(encoding="utf-8")) if real.exists() else {}
        if not isinstance(actual, dict):
            raise ValueError("no es un objeto JSON")
    except (OSError, ValueError) as e:
        imprimir(f"FAILED   {d.settings}: no lo puedo leer, no lo toco ({e})")
        return 1
    nuevo = copy.deepcopy(actual)
    for evento, grupos in list(nuevo.get("hooks", {}).items()):
        quedan = [g for g in grupos if not _es_grupo_kit(g)]
        if len(quedan) != len(grupos):
            if quedan:
                nuevo["hooks"][evento] = quedan
            else:
                del nuevo["hooks"][evento]
    if nuevo != actual:
        rep.lineas.append(f"settings {d.settings} (saco los hooks del kit)")
        escribir_settings(d.settings, nuevo, respaldo, rep)
        if rep.fallo:
            rep.lineas.append(
                "No saqué ningún link: settings.json sigue registrando los hooks del kit."
            )
            for linea in rep.lineas:
                imprimir(linea)
            return 1
    conservar = d.bin / _STATUSLINE if _statusline_en_uso(actual) else None
    for p in _huerfanos([], d, (kit_dir, d.repo_viejo)):
        if p == conservar:
            rep.lineas.append(
                f"queda    {p} (la usa statusLine de {d.settings}; sacala a mano si no la querés)"
            )
            continue
        rep.lineas.append(f"saco     {p}")
        p.unlink()
    for u in units_kit():
        if (d.systemd / u).exists():
            rep.lineas.append(
                f"queda    {d.systemd / u} (si no la querés: systemctl --user disable --now {units_kit()[0]} y borrala)"
            )
    for linea in rep.lineas:
        imprimir(linea)
    return 1 if rep.fallo else 0
