#!/bin/bash
# Tests de scripts/revisar-publicable.sh en un repo git temporal, con listas de palabras sintéticas.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../../scripts/revisar-publicable.sh"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

FAIL=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: esperado '$3', obtuve '$2'"; FAIL=1; fi; }

mkrepo() {
  rm -rf "$T/repo" && mkdir -p "$T/repo/scripts"
  cp "$SCRIPT" "$T/repo/scripts/revisar-publicable.sh"
  printf '%s\n' "$1" > "$T/repo/dato.txt"
  git -C "$T/repo" init -q
  git -C "$T/repo" add -A
  git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m x
}
correr() {
  COLMENA_PALABRAS_PROHIBIDAS="$1" COLMENA_EXCEPCIONES="${2:-$T/sin-excepciones}" bash "$T/repo/scripts/revisar-publicable.sh" >"$T/out" 2>"$T/err"
  echo $?
}

mkrepo "nada raro"
printf 'orz\n' > "$T/lista"
check "sin hallazgos: exit 0" "$(correr "$T/lista")" "0"
check "falta la lista: exit 2" "$(correr "$T/no-existe")" "2"

: > "$T/vacia"
check "lista vacía: exit 2" "$(correr "$T/vacia")" "2"
grep -q "vacía" "$T/err" && r=si || r=no
check "lista vacía: mensaje claro" "$r" "si"

printf '# solo comentarios\n\n   \n# otro\n' > "$T/comentarios"
check "solo comentarios: exit 2" "$(correr "$T/comentarios")" "2"

mkrepo "hay un orz acá"
check "hallazgo: exit 1" "$(correr "$T/lista")" "1"
check "hallazgo: muestra archivo:línea" "$(cat "$T/out")" "dato.txt:1"
grep -qi "orz" "$T/out" "$T/err" && r=si || r=no
check "no imprime la palabra prohibida" "$r" "no"

printf 'zorzal\\w*\n' > "$T/excepciones"
mkrepo "un zorzal y dos zorzales"
check "token genérico entero se exime" "$(correr "$T/lista" "$T/excepciones")" "0"
mkrepo "el xzorzalx"
check "token más largo que contiene la genérica no se exime" "$(correr "$T/lista" "$T/excepciones")" "1"
mkrepo "ZorZal y zor_zal"
check "palabra que cruza el borde camelCase/snake_case no cuenta" "$(correr "$T/lista" "$T/excepciones")" "0"
mkrepo "MiOrzKit"
check "palabra dentro de una parte del identificador sí cuenta" "$(correr "$T/lista" "$T/excepciones")" "1"

exit "$FAIL"
