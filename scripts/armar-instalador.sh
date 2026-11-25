#!/usr/bin/env bash
# Arma en la notebook el instalador firmado de la app de Windows y lo deja listo para que el back lo sirva.
#
#   scripts/armar-instalador.sh [carpeta-de-salida]
#
#   carpeta-de-salida            default $COLMENA_ACTUALIZACIONES_DIR o <raíz del repo>/data/actualizaciones
#   COLMENA_CLAVE_ACTUALIZADOR   clave privada de firma (default ~/.config/colmena/actualizador.key); solo se pasa su ruta
#   COLMENA_TARGET_DIR           cache de compilación (default windows/colmena-app/src-tauri/target, ignorado por git)
#   COLMENA_AHORA                AAAAMMDDHHMM (default la hora local; los tests la fijan)
#   COLMENA_ARMAR_CMD            reemplaza el armado de Tauri (tests): recibe <app> <versión> <carpeta del .exe>
#   COLMENA_HERRAMIENTAS         herramientas que tienen que estar (tests)
#
# Arma desde lo commiteado (git archive HEAD), con versión 0.<AAAAMMDD>.<HHMM como entero>. Escribe el
# instalador y ultima.json de forma atómica, guarda la versión anterior (anterior.json) y borra las más viejas.
# Ver docs/superpowers/specs/2026-11-25-actualizador-design.md y docs/interno/armar-zips.md.
set -euo pipefail

RAIZ="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
SALIDA="${1:-${COLMENA_ACTUALIZACIONES_DIR:-$RAIZ/data/actualizaciones}}"
CLAVE="${COLMENA_CLAVE_ACTUALIZADOR:-$HOME/.config/colmena/actualizador.key}"
TARGET="${COLMENA_TARGET_DIR:-$RAIZ/windows/colmena-app/src-tauri/target}"
AHORA="${COLMENA_AHORA:-$(date +%Y%m%d%H%M)}"
HERRAMIENTAS="${COLMENA_HERRAMIENTAS:-clang lld-link llvm-lib llvm-rc makensis cargo-xwin npx git python3}"
TRIPLE="x86_64-pc-windows-msvc"
export PATH="$HOME/.cargo/bin:$PATH"

fallar() { echo "Error: $*" >&2; exit 1; }

[[ "$AHORA" =~ ^[0-9]{12}$ ]] || fallar "COLMENA_AHORA tiene que ser AAAAMMDDHHMM"
faltan=()
for h in $HERRAMIENTAS; do
  command -v "$h" >/dev/null 2>&1 || faltan+=("$h")
done
if (( ${#faltan[@]} )); then
  fallar "faltan herramientas: ${faltan[*]} (clang, lld, llvm y nsis de apt; cargo install cargo-xwin)"
fi

if [[ ! -f "$CLAVE" ]]; then
  echo "Error: no está la clave de firma en $CLAVE." >&2
  echo "Generala una vez, sin contraseña, y copiá la pública (.pub) a plugins.updater.pubkey" >&2
  echo "de windows/colmena-app/src-tauri/tauri.conf.json:" >&2
  echo "  cd windows/colmena-app && npm install && npx tauri signer generate -w $CLAVE" >&2
  echo "  chmod 600 $CLAVE" >&2
  exit 1
fi
if [[ "$(stat -c %a "$CLAVE")" != "600" ]]; then
  echo "Aviso: la clave $CLAVE no tiene permisos 600 (chmod 600 $CLAVE)." >&2
fi

VERSION="0.${AHORA:0:8}.$((10#${AHORA:8:4}))"
FECHA="$(date -d "${AHORA:0:8} ${AHORA:8:2}:${AHORA:10:2}" +%Y-%m-%dT%H:%M:00%:z)"
NOTAS="$(git -C "$RAIZ" log -1 --format='%s (%h)' HEAD)"
NOMBRE="Colmena_${VERSION}_x64-setup.exe"

if [[ -n "$(git -C "$RAIZ" status --porcelain -- windows/colmena-app)" ]]; then
  echo "Aviso: hay cambios sin commitear en windows/colmena-app; el instalador sale de lo commiteado (HEAD)." >&2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git -C "$RAIZ" archive HEAD windows/colmena-app | tar -x -C "$TMP"
APP="$TMP/windows/colmena-app"
BUNDLE="$TARGET/$TRIPLE/release/bundle/nsis"
rm -f "$BUNDLE/$NOMBRE" "$BUNDLE/$NOMBRE.sig"

echo "Armando la versión $VERSION…"
if [[ -n "${COLMENA_ARMAR_CMD:-}" ]]; then
  "$COLMENA_ARMAR_CMD" "$APP" "$VERSION" "$BUNDLE"
else
  # tauri-cli en Linux busca appindicator aunque arme para Windows: un .pc falso lo conforma.
  mkdir -p "$TMP/pc" "$TMP/bin"
  # tauri-cli recorta el -L de la salida de pkg-config: libdir tiene que estar.
  cat > "$TMP/pc/ayatana-appindicator3-0.1.pc" <<'PC'
libdir=/usr/lib/x86_64-linux-gnu
includedir=/usr/include
Name: ayatana-appindicator3-0.1
Description: falso para armar el instalador de Windows
Version: 0.5.90
Libs: -L${libdir} -layatana-appindicator3
Cflags:
PC
  # El NSIS de Ubuntu no trae Win/RestartManager.nsh e ignora NSISDIR: se suma la copia versionada.
  printf '#!/bin/sh\nexec %q %q "$@"\n' "$(command -v makensis)" "-X!addincludedir $APP/nsis-extra" > "$TMP/bin/makensis"
  chmod +x "$TMP/bin/makensis"
  CONFIG="{\"version\":\"$VERSION\",\"bundle\":{\"createUpdaterArtifacts\":true}}"
  (
    cd "$APP"
    npm install --no-audit --no-fund --loglevel=error >"$TMP/npm.log" 2>&1 || { cat "$TMP/npm.log" >&2; exit 1; }
    export PATH="$TMP/bin:$PATH" PKG_CONFIG_PATH="$TMP/pc${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
    export CARGO_TARGET_DIR="$TARGET" XWIN_ACCEPT_LICENSE=1
    # Solo la ruta: el contenido de la clave nunca pasa por el script.
    export TAURI_SIGNING_PRIVATE_KEY="$CLAVE" TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
    if ! npx tauri build --ci --runner cargo-xwin --target "$TRIPLE" --bundles nsis --config "$CONFIG"; then
      [[ -f "$TARGET/$TRIPLE/release/colmena.exe" ]] || exit 1
      echo "El build dio el .exe pero no el instalador: pruebo solo el empaquetado…" >&2
      npx tauri bundle --ci --target "$TRIPLE" --bundles nsis --config "$CONFIG"
    fi
  )
fi

[[ -f "$BUNDLE/$NOMBRE" ]] || fallar "el armado no dejó $BUNDLE/$NOMBRE"
[[ -s "$BUNDLE/$NOMBRE.sig" ]] || fallar "el armado no dejó la firma $NOMBRE.sig (¿falta createUpdaterArtifacts o la clave?)"

mkdir -p "$SALIDA"
cp "$BUNDLE/$NOMBRE" "$SALIDA/.$NOMBRE.tmp"
mv -f "$SALIDA/.$NOMBRE.tmp" "$SALIDA/$NOMBRE"
python3 - "$SALIDA" "$NOMBRE" "$VERSION" "$NOTAS" "$FECHA" "$BUNDLE/$NOMBRE.sig" <<'PY'
import json, os, re, sys
from pathlib import Path

salida, nombre, version, notas, fecha, sig = sys.argv[1:]
salida = Path(salida)
firma = Path(sig).read_text(encoding="utf-8").strip()
ficha = {"version": version, "notas": notas, "fecha": fecha, "archivo": nombre, "firma": firma}


def escribir(ruta: Path, datos: dict) -> None:
    tmp = ruta.with_name(f".{ruta.name}.tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, ruta)


def leer(ruta: Path):
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else None
    except (OSError, ValueError):
        return None


previa = leer(salida / "ultima.json")
if previa and previa.get("archivo") != nombre and (salida / str(previa.get("archivo"))).is_file():
    escribir(salida / "anterior.json", previa)
escribir(salida / "ultima.json", ficha)

anterior = leer(salida / "anterior.json")
quedan = {nombre, (anterior or {}).get("archivo")}
for f in salida.iterdir():
    if re.fullmatch(r"Colmena_[0-9.]+_x64-setup\.exe", f.name) and f.name not in quedan:
        f.unlink()
PY

echo "Listo: $SALIDA/$NOMBRE"
echo "Ficha: $SALIDA/ultima.json (versión $VERSION)"
