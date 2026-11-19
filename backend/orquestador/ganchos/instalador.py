"""Instalación reversible de hooks de Colmena en settings.json de Claude."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from orquestador.ganchos import definiciones as definiciones


class SettingsInvalido(Exception):
    pass


@dataclass
class Resultado:
    cambio: bool
    settings: Path
    respaldo: Path | None
    mensaje: str


def _validar_hooks(hooks: object, settings: Path) -> None:
    if hooks is None:
        return
    if not isinstance(hooks, dict):
        raise SettingsInvalido(f"{settings}: hooks debe ser un objeto")
    for _evento, bloques in hooks.items():
        if not isinstance(bloques, list):
            raise SettingsInvalido(f"{settings}: lista de hooks inválida")
        for bloque in bloques:
            if not isinstance(bloque, dict):
                raise SettingsInvalido(f"{settings}: bloque de hooks inválido")
            if "hooks" not in bloque:
                continue
            if not isinstance(bloque["hooks"], list):
                raise SettingsInvalido(f"{settings}: hooks de un bloque debe ser lista")
            for hook in bloque["hooks"]:
                if not isinstance(hook, dict):
                    raise SettingsInvalido(f"{settings}: cada hook debe ser un objeto")


def _leer_settings(settings: Path) -> tuple[dict, bool]:
    if settings.is_symlink():
        raise SettingsInvalido(f"{settings}: no se admite symlink")
    if not settings.exists():
        return {}, False
    raw = settings.read_bytes()
    if not raw.strip():
        return {}, True
    try:
        datos = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SettingsInvalido(f"{settings}: JSON inválido") from e
    if not isinstance(datos, dict):
        raise SettingsInvalido(f"{settings}: la raíz debe ser un objeto")
    if "hooks" in datos:
        _validar_hooks(datos["hooks"], settings)
    return datos, True


def _serializar(datos: dict) -> bytes:
    return (json.dumps(datos, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(datos: dict) -> str:
    return hashlib.sha256(_serializar(datos)).hexdigest()


def _bytes_sin_colmena(datos: dict) -> bytes:
    copia = copy.deepcopy(datos)
    _quitar_colmena(copia)
    return _serializar(copia)


def _tiene_colmena(datos: dict) -> bool:
    hooks = datos.get("hooks")
    if not isinstance(hooks, dict):
        return False
    for bloques in hooks.values():
        if not isinstance(bloques, list):
            continue
        for bloque in bloques:
            if not isinstance(bloque, dict):
                continue
            inner = bloque.get("hooks")
            if not isinstance(inner, list):
                continue
            for hook in inner:
                if definiciones.es_de_colmena(hook.get("command") if isinstance(hook, dict) else None):
                    return True
    return False


def _quitar_colmena(datos: dict) -> None:
    hooks = datos.get("hooks")
    if not isinstance(hooks, dict):
        return
    for evento, bloques in list(hooks.items()):
        if not isinstance(bloques, list):
            continue
        if not bloques:
            continue
        nuevos_bloques = []
        for bloque in bloques:
            if not isinstance(bloque, dict) or "hooks" not in bloque:
                nuevos_bloques.append(bloque)
                continue
            inner = bloque["hooks"]
            if not isinstance(inner, list):
                nuevos_bloques.append(bloque)
                continue
            filtrados = [
                h for h in inner if not definiciones.es_de_colmena(h.get("command") if isinstance(h, dict) else None)
            ]
            had_colmena = len(filtrados) < len(inner)
            if not filtrados:
                if had_colmena:
                    continue
                nuevos_bloques.append(bloque)
                continue
            if len(filtrados) == len(inner):
                nuevos_bloques.append(bloque)
                continue
            copia = dict(bloque)
            copia["hooks"] = filtrados
            nuevos_bloques.append(copia)
        if nuevos_bloques:
            hooks[evento] = nuevos_bloques
        else:
            del hooks[evento]
    if hooks == {}:
        datos.pop("hooks", None)


def _restaurar_eventos_vacios_respaldo(nuevo: dict, orig: dict) -> None:
    hooks_orig = orig.get("hooks")
    if not isinstance(hooks_orig, dict):
        return
    for evento, bloques in hooks_orig.items():
        if bloques != []:
            continue
        hooks = nuevo.get("hooks")
        if not isinstance(hooks, dict):
            nuevo["hooks"] = {evento: []}
            continue
        if evento not in hooks:
            hooks[evento] = []


def _fusionar_definiciones(datos: dict, script: Path, espera: int) -> None:
    defs = definiciones.definiciones_hooks(script, espera)
    hooks = datos.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SettingsInvalido("hooks debe ser un objeto")
    for evento, bloques in defs.items():
        hooks.setdefault(evento, [])
        hooks[evento].extend(copy.deepcopy(bloques))


def _respaldar_archivo(respaldos: Path, ahora: Callable[[], datetime], contenido: bytes) -> Path:
    respaldos.mkdir(parents=True, mode=0o700, exist_ok=True)
    stamp = ahora().strftime("%Y%m%dT%H%M%S")
    destino = respaldos / f"settings-{stamp}.json"
    n = 0
    while destino.exists():
        n += 1
        destino = respaldos / f"settings-{stamp}-{n}.json"
    fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, contenido)
        os.fsync(fd)
    finally:
        os.close(fd)
    return destino


def _respaldar(settings: Path, respaldos: Path, ahora: Callable[[], datetime]) -> Path | None:
    if not settings.exists():
        return None
    return _respaldar_archivo(respaldos, ahora, settings.read_bytes())


def _escribir_atomico(path: Path, contenido: bytes) -> None:
    modo = 0o600
    if path.exists():
        modo = stat.S_IMODE(path.stat().st_mode)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, modo)
        try:
            os.fchmod(fd, modo)
            os.write(fd, contenido)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _manifest(
    respaldos: Path,
    *,
    settings: Path,
    respaldo: Path | None,
    existia: bool,
    sha_instalado: str,
) -> None:
    respaldos.mkdir(parents=True, mode=0o700, exist_ok=True)
    datos = {
        "settings": str(settings.resolve()),
        "respaldo": str(respaldo.resolve()) if respaldo else None,
        "existia": existia,
        "sha_instalado": sha_instalado,
    }
    ruta = respaldos / "ultimo.json"
    _escribir_atomico(ruta, _serializar(datos))


def _leer_manifest(respaldos: Path) -> dict | None:
    ruta = respaldos / "ultimo.json"
    if not ruta.exists():
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, dict):
        return None
    return datos


def instalar(
    settings: Path,
    respaldos: Path,
    *,
    script: Path,
    espera: int,
    ahora: Callable[[], datetime],
) -> Resultado:
    datos, existia = _leer_settings(settings)
    nuevo = copy.deepcopy(datos)
    _quitar_colmena(nuevo)
    _fusionar_definiciones(nuevo, script, espera)
    if nuevo == datos:
        return Resultado(
            cambio=False,
            settings=settings,
            respaldo=None,
            mensaje="Sin cambios",
        )

    sha = _sha256(nuevo)
    contenido = _serializar(nuevo)
    manifest_prev = _leer_manifest(respaldos)
    settings_resuelto = str(settings.resolve())
    respaldo: Path | None
    existia_manifest = existia
    respaldo_nuevo = False
    sin_colmena_actual = _bytes_sin_colmena(datos)
    if manifest_prev and manifest_prev.get("settings") == settings_resuelto:
        respaldo_str = manifest_prev.get("respaldo")
        respaldo = Path(respaldo_str) if respaldo_str else None
        existia_manifest = bool(manifest_prev.get("existia", existia))
        if respaldo is not None and respaldo.exists():
            try:
                datos_respaldo, _ = _leer_settings(respaldo)
                sin_colmena_respaldo = _bytes_sin_colmena(datos_respaldo)
            except (SettingsInvalido, OSError):
                sin_colmena_respaldo = None
            else:
                if sin_colmena_actual != sin_colmena_respaldo:
                    respaldo = _respaldar_archivo(respaldos, ahora, sin_colmena_actual)
                    respaldo_nuevo = True
        elif respaldo is None and existia:
            respaldo = _respaldar(settings, respaldos, ahora)
            respaldo_nuevo = respaldo is not None
    else:
        respaldo = _respaldar(settings, respaldos, ahora)
        respaldo_nuevo = respaldo is not None
        existia_manifest = existia

    manifest_path = respaldos / "ultimo.json"
    try:
        _manifest(
            respaldos,
            settings=settings,
            respaldo=respaldo,
            existia=existia_manifest,
            sha_instalado=sha,
        )
        _escribir_atomico(settings, contenido)
    except BaseException:
        try:
            if manifest_prev is None:
                manifest_path.unlink(missing_ok=True)
            else:
                _escribir_atomico(manifest_path, _serializar(manifest_prev))
        except Exception:
            pass
        if respaldo_nuevo and respaldo is not None:
            try:
                respaldo.unlink(missing_ok=True)
            except Exception:
                pass
        raise

    return Resultado(
        cambio=True,
        settings=settings,
        respaldo=respaldo,
        mensaje="Hooks de Colmena instalados",
    )


def _datos_respaldo(manifest: dict | None) -> dict:
    if not manifest:
        return {}
    respaldo_str = manifest.get("respaldo")
    if not respaldo_str:
        return {}
    respaldo = Path(respaldo_str)
    if not respaldo.exists():
        return {}
    try:
        orig, _ = _leer_settings(respaldo)
    except (SettingsInvalido, OSError):
        return {}
    return orig


def desinstalar(settings: Path, respaldos: Path) -> Resultado:
    datos, existia_ahora = _leer_settings(settings)
    manifest = _leer_manifest(respaldos)
    manifest_path = respaldos / "ultimo.json"
    settings_resuelto = str(settings.resolve())
    manifest_aplica = manifest is not None and manifest.get("settings") == settings_resuelto

    if not _tiene_colmena(datos):
        if not manifest_aplica:
            return Resultado(
                cambio=False,
                settings=settings,
                respaldo=None,
                mensaje="Sin cambios",
            )
        manifest_path.unlink(missing_ok=True)
        return Resultado(
            cambio=False,
            settings=settings,
            respaldo=None,
            mensaje="Manifest retirado",
        )

    respaldo: Path | None = None
    existia_antes = existia_ahora

    if manifest_aplica:
        existia_antes = bool(manifest.get("existia", existia_ahora))
        respaldo_str = manifest.get("respaldo")
        respaldo = Path(respaldo_str) if respaldo_str else None
        sha_instalado = manifest.get("sha_instalado")
        if isinstance(sha_instalado, str) and _sha256(datos) == sha_instalado:
            if not existia_antes:
                settings.unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)
                return Resultado(
                    cambio=True,
                    settings=settings,
                    respaldo=respaldo,
                    mensaje="Hooks de Colmena desinstalados",
                )
            if respaldo and respaldo.exists():
                try:
                    _leer_settings(respaldo)
                except (SettingsInvalido, OSError):
                    pass
                else:
                    _escribir_atomico(settings, respaldo.read_bytes())
                    manifest_path.unlink(missing_ok=True)
                    return Resultado(
                        cambio=True,
                        settings=settings,
                        respaldo=respaldo,
                        mensaje="Hooks de Colmena desinstalados",
                    )

    nuevo = copy.deepcopy(datos)
    _quitar_colmena(nuevo)
    orig = _datos_respaldo(manifest) if manifest_aplica else {}
    if orig:
        _restaurar_eventos_vacios_respaldo(nuevo, orig)

    if not existia_antes and nuevo == {}:
        settings.unlink(missing_ok=True)
    else:
        contenido = _serializar(nuevo)
        if not settings.exists() or settings.read_bytes() != contenido:
            _escribir_atomico(settings, contenido)
    if manifest_aplica and manifest_path.exists():
        manifest_path.unlink(missing_ok=True)

    return Resultado(
        cambio=True,
        settings=settings,
        respaldo=respaldo,
        mensaje="Hooks de Colmena desinstalados",
    )
