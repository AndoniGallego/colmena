#!/bin/bash
# Tests de scripts/entregar.sh en repos git de juguete (mktemp), con datos sintéticos y sin red.
# Nunca escriben en ~/Desktop: COLMENA_ENTREGAS_DIR apunta a un directorio temporal.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$HERE/../../scripts"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

FAIL=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: esperado '$3', obtuve '$2'"; FAIL=1; fi; }

FECHA="2031-05-24"
export COLMENA_FECHA="$FECHA"
printf 'zzprohibidozz\n' > "$T/lista"
export COLMENA_PALABRAS_PROHIBIDAS="$T/lista" COLMENA_EXCEPCIONES="$T/sin-excepciones"
R="$T/repo"
E="$T/entregas"

git_() { git -C "$R" -c user.name=t -c user.email=t@t "$@"; }
commit() { printf '%s\n' "$1" >> "$R/dato.txt"; git_ add -A; git_ commit -q -m "$1"; }
vacio() { git_ commit -q --allow-empty -m "$1"; }
mkrepo() {
  rm -rf "$R" "$E" && mkdir -p "$R/scripts" "$E"
  cp "$SCRIPTS/entregar.sh" "$SCRIPTS/revisar-publicable.sh" "$R/scripts/"
  git -C "$R" init -q
  vacio "chore: inicio"
  git_ add -A
  git_ commit -q -m "chore: scripts"
}
entregar() { COLMENA_ENTREGAS_DIR="$E" bash "$R/scripts/entregar.sh" "$@" >"$T/out" 2>"$T/err"; echo $?; }

# 1. primera entrega: sin letra, ZIP + mensaje + tag
mkrepo
vacio "feat: pantalla nueva de tareas"
vacio "fix(ui): el botón ya no se corta"
check "primera entrega: exit 0" "$(entregar)" "0"
check "primera entrega: ZIP sin letra" "$(ls "$E"/*.zip | xargs -n1 basename)" "colmena-$FECHA.zip"
[ -f "$E/colmena-$FECHA.mensaje.txt" ] && r=si || r=no
check "mensaje al lado del ZIP" "$r" "si"
unzip -l "$E/colmena-$FECHA.zip" | grep -q 'mensaje.txt' && r=si || r=no
check "mensaje no va adentro del ZIP" "$r" "no"
check "tag creado" "$(git -C "$R" tag -l 'entrega/*')" "entrega/colmena-$FECHA"
check "título del mensaje" "$(head -1 "$E/colmena-$FECHA.mensaje.txt")" "Actualización $FECHA"
check "segunda línea en blanco" "$(sed -n 2p "$E/colmena-$FECHA.mensaje.txt")" ""
grep -q 'colmena.ps1 publicar' "$T/out" && r=si || r=no
check "imprime comandos de la PC" "$r" "si"

# 2. letra siguiente: existe la sin letra -> b; con b..f -> g
check "segunda del día: exit 0" "$(entregar)" "0"
[ -f "$E/colmena-${FECHA}b.zip" ] && r=si || r=no
check "segunda del día: letra b" "$r" "si"
for l in c d e f; do : > "$E/colmena-$FECHA$l.zip"; done
check "tras f: exit 0" "$(entregar)" "0"
[ -f "$E/colmena-${FECHA}g.zip" ] && r=si || r=no
check "tras f: letra g" "$r" "si"

# 3. mensaje desde el tag anterior: solo lo nuevo, sin prefijo, sin merges ni duplicados ni chore
mkrepo
vacio "feat: base"
git_ tag "entrega/colmena-2031-05-01"
vacio "feat: ventana de reunión más clara"
vacio "fix: no se perdía el texto"
vacio "fix: no se perdía el texto"
vacio "chore: limpieza interna"
vacio "docs: guía de entrega"
git_ checkout -q -b rama
vacio "feat: cosa en rama"
git_ checkout -q -
git_ merge -q --no-ff rama -m "Merge: rama de prueba"
check "con tag previo: exit 0" "$(entregar)" "0"
M="$E/colmena-$FECHA.mensaje.txt"
grep -q '^- ventana de reunión más clara$' "$M" && r=si || r=no
check "mensaje: feat sin prefijo" "$r" "si"
check "mensaje: fix sin duplicado" "$(grep -c 'no se perdía el texto' "$M")" "1"
grep -q 'limpieza interna' "$M" && r=si || r=no
check "mensaje: sin chore" "$r" "no"
grep -q 'guía de entrega' "$M" && r=si || r=no
check "mensaje: con docs" "$r" "si"
grep -q 'Merge' "$M" && r=si || r=no
check "mensaje: sin merges" "$r" "no"
grep -q 'base' "$M" && r=si || r=no
check "mensaje: no incluye lo anterior al tag" "$r" "no"
check "tag nuevo apunta a HEAD" "$(git -C "$R" rev-parse "entrega/colmena-$FECHA")" "$(git -C "$R" rev-parse HEAD)"

# 4. una línea del mensaje con palabra prohibida se descarta (el árbol queda limpio)
mkrepo
git_ tag "entrega/colmena-2031-05-01"
vacio "feat: algo con zzprohibidozz adentro"
vacio "feat: algo limpio"
check "mensaje con prohibida: exit 0" "$(entregar)" "0"
M="$E/colmena-$FECHA.mensaje.txt"
grep -q 'zzprohibidozz' "$M" && r=si || r=no
check "mensaje: línea prohibida descartada" "$r" "no"
grep -q 'algo limpio' "$M" && r=si || r=no
check "mensaje: línea limpia queda" "$r" "si"

# 5. cambios sin commitear: rechazo, nada creado
mkrepo
echo suelto > "$R/suelto.txt"
check "cambios sin commitear: exit 1" "$(entregar)" "1"
check "sin commitear: sin ZIP" "$(ls "$E" | wc -l)" "0"
check "sin commitear: sin tag" "$(git -C "$R" tag -l | wc -l)" "0"
grep -qi 'cambios' "$T/err" && r=si || r=no
check "sin commitear: mensaje claro" "$r" "si"

# 6. verificación del ZIP: docs/interno adentro lo borra y falla
mkrepo
mkdir -p "$R/docs/interno"
echo x > "$R/docs/interno/a.md"
git_ add -A
git_ commit -q -m "feat: x"
check "docs/interno dentro del ZIP: exit 1" "$(entregar)" "1"
check "verificación fallida: sin ZIP" "$(ls "$E" | wc -l)" "0"
check "verificación fallida: sin tag" "$(git -C "$R" tag -l | wc -l)" "0"
printf 'docs/interno/ export-ignore\n' > "$R/.gitattributes"
git_ add -A
git_ commit -q -m "chore: ignora"
check "con export-ignore: exit 0" "$(entregar)" "0"

# 7. --ensayo no crea nada
mkrepo
vacio "feat: algo"
check "ensayo: exit 0" "$(entregar --ensayo)" "0"
check "ensayo: sin ZIP ni mensaje" "$(ls "$E" | wc -l)" "0"
check "ensayo: sin tag" "$(git -C "$R" tag -l | wc -l)" "0"
grep -q "colmena-$FECHA.zip" "$T/out" && r=si || r=no
check "ensayo: dice qué haría" "$r" "si"

exit $FAIL
