#!/usr/bin/env bash
# Arma la entrega de Colmena en la notebook: ZIP público limpio + mensaje de commit para GitHub + tag local.
#
#   scripts/entregar.sh             arma el ZIP y el mensaje y crea el tag entrega/<nombre>
#   scripts/entregar.sh --ensayo    muestra qué haría, sin crear ZIP, mensaje ni tag
#
#   COLMENA_ENTREGAS_DIR  directorio de entregas (default ~/Desktop)
#   COLMENA_FECHA         fecha AAAA-MM-DD (default hoy; los tests la fijan)
#
# Falla si hay cambios sin commitear o si revisar-publicable.sh no da 0 hallazgos. Ver docs/interno/armar-zips.md.
set -euo pipefail

ENSAYO=0
case "${1:-}" in
  "") ;;
  --ensayo) ENSAYO=1 ;;
  *) echo "Uso: entregar.sh [--ensayo]" >&2; exit 2 ;;
esac

RAIZ="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
ENTREGAS="${COLMENA_ENTREGAS_DIR:-$HOME/Desktop}"
FECHA="${COLMENA_FECHA:-$(date +%F)}"

fallar() { echo "Error: $*" >&2; exit 1; }

if [[ -n "$(git -C "$RAIZ" status --porcelain)" ]]; then
  fallar "hay cambios sin commitear; commiteá o descartá antes de entregar (git status)."
fi

if ! bash "$RAIZ/scripts/revisar-publicable.sh" >/dev/null 2>&1; then
  fallar "revisar-publicable.sh no dio 0 hallazgos; corrélo a mano para ver cuáles."
fi

[[ -d "$ENTREGAS" ]] || fallar "no existe el directorio de entregas: $ENTREGAS"

# Letra: sin letra si es la primera del día; si no, la siguiente a la más alta (la sin letra cuenta como "a").
mayor=0
for f in "$ENTREGAS"/colmena-"$FECHA"*.zip; do
  [[ -e "$f" ]] || continue
  resto="${f##*/colmena-$FECHA}"
  resto="${resto%.zip}"
  if [[ -z "$resto" ]]; then
    rango=1
  elif [[ "$resto" =~ ^[a-z]$ ]]; then
    rango=$(( $(printf '%d' "'$resto") - 96 ))
  else
    continue
  fi
  (( rango > mayor )) && mayor=$rango
done
if (( mayor == 0 )); then
  LETRA=""
else
  LETRA="$(printf "\\x$(printf '%x' $((96 + mayor + 1)))")"
fi
NOMBRE="colmena-$FECHA$LETRA"
ZIP="$ENTREGAS/$NOMBRE.zip"
MENSAJE="$ENTREGAS/$NOMBRE.mensaje.txt"
TAG="entrega/$NOMBRE"

# Mensaje: asuntos feat/fix/perf/docs desde la entrega anterior (tag entrega/* más cercano) o los últimos 30 commits.
if PREVIA="$(git -C "$RAIZ" describe --tags --match 'entrega/*' --abbrev=0 HEAD 2>/dev/null)"; then
  RANGO=("$PREVIA..HEAD")
  DESDE="desde $PREVIA"
else
  RANGO=(-30)
  DESDE="últimos 30 commits"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git -C "$RAIZ" log --no-merges --format=%s "${RANGO[@]}" HEAD \
  | { grep -E '^(feat|fix|perf|docs)(\([^)]*\))?!?: ' || true; } \
  | sed -E 's/^[a-z]+(\([^)]*\))?!?: //' \
  | awk '!visto[$0]++' \
  | sed 's/^/- /' > "$TMP/viñetas"

# Descarta las líneas que den hallazgo con los patrones de revisar-publicable (sin duplicarlos acá).
if [[ -s "$TMP/viñetas" ]]; then
  rc=0
  bash "$RAIZ/scripts/revisar-publicable.sh" --texto "$TMP/viñetas" >"$TMP/malas" 2>/dev/null || rc=$?
  if (( rc == 1 )); then
    awk 'NR==FNR { mala[$1]=1; next } !(FNR in mala)' "$TMP/malas" "$TMP/viñetas" > "$TMP/viñetas.ok"
    mv "$TMP/viñetas.ok" "$TMP/viñetas"
  elif (( rc != 0 )); then
    fallar "no pude revisar el mensaje con revisar-publicable.sh (código $rc)."
  fi
fi
[[ -s "$TMP/viñetas" ]] || echo "- Mejoras menores" > "$TMP/viñetas"
{ echo "Actualización $FECHA"; echo; cat "$TMP/viñetas"; } > "$TMP/mensaje.txt"

if (( ENSAYO )); then
  echo "Ensayo: no se crea nada."
  echo "ZIP:     $ZIP"
  echo "Mensaje: $MENSAJE ($DESDE)"
  echo "Tag:     $TAG"
  echo "--- mensaje ---"
  cat "$TMP/mensaje.txt"
  exit 0
fi

git -C "$RAIZ" archive --format=zip -o "$ZIP" HEAD

# Verificación del ZIP, lo mismo que documenta armar-zips.md.
VER="$TMP/zip"
mkdir -p "$VER"
unzip -q "$ZIP" -d "$VER"
errores=0
[[ -e "$VER/docs/interno" ]] && { echo "Error: el ZIP trae docs/interno." >&2; errores=1; }
if [[ -n "$(find "$VER" -path '*piezas/horas*' -print -quit)" ]]; then
  echo "Error: el ZIP trae piezas de horas." >&2; errores=1
fi
if grep -rqE '192\.168\.1\.4([^0-9]|$)' "$VER"; then
  echo "Error: el ZIP trae la IP privada de la notebook." >&2; errores=1
fi
if (( errores )); then
  rm -f "$ZIP"
  fallar "la verificación del ZIP falló; se borró $ZIP."
fi

cp "$TMP/mensaje.txt" "$MENSAJE"
git -C "$RAIZ" tag "$TAG"

echo "ZIP:     $ZIP"
echo "Mensaje: $MENSAJE"
echo "Tag:     $TAG"
echo
echo "En la PC (PowerShell):"
echo "  colmena.ps1 instalar    # compila e instala la app de Windows"
echo "  colmena.ps1 publicar    # sube el ZIP al repo público de GitHub"
