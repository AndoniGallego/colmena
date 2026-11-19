#!/bin/bash
# Valida que los bloques de ejemplo (diagrama, opciones, estado) de rules/ y skills/ sean los que Colmena muestra,
# y que la regla de diagramas sea un recordatorio corto que apunta a la skill.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE/.."
# shellcheck source=../ganchos/lib-bloques.sh
. "$REPO/ganchos/lib-bloques.sh"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

FAIL=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: esperado '$3', obtuve '$2'"; FAIL=1; fi; }

# validar_archivos ARCHIVO...: un ok/FAIL por archivo y tipo con bloques; devuelve 1 si alguno falla.
# Deja en VALIDOS la cantidad de bloques válidos de tipo diagrama.
VALIDOS=0
validar_archivos() {
  local f tipo ok bad n rc=0
  for f in "$@"; do
    for tipo in diagrama opciones estado; do
      read -r ok bad < <(bloques_contar "$tipo" < "$f")
      n=$((ok + bad))
      [ "$tipo" = diagrama ] && VALIDOS=$((VALIDOS + ok))
      [ "$n" = 0 ] && continue
      if [ "$bad" = 0 ]; then echo "ok   $f: $n bloque(s) $tipo válidos"
      else echo "FAIL $f: $bad de $n bloque(s) $tipo inválidos"; rc=1; fi
    done
  done
  return "$rc"
}

check "reglas/colmena/diagramas.md tiene 7 líneas o menos" "$([ "$(wc -l < "$REPO/reglas/colmena/diagramas.md")" -le 7 ] && echo si || echo no)" "si"
SK="$REPO/skills/diagramas/SKILL.md"
check "skills/diagramas/SKILL.md existe" "$([ -f "$SK" ] && echo si || echo no)" "si"
check "SKILL.md empieza con ---" "$(head -1 "$SK" 2>/dev/null)" "---"
check "SKILL.md tiene name: diagramas" "$(grep -c '^name: diagramas$' "$SK" 2>/dev/null)" "1"

ES="$REPO/reglas/colmena/estado-sesion.md"
check "estado-sesion: obligatorio si usaste herramientas" "$(grep -c 'usaste herramientas' "$ES")" "1"
check "estado-sesion: no contradice al hook" "$(grep -c 'pregunta rápida que no deja nada pendiente' "$ES")" "0"

shopt -s nullglob
validar_archivos "$REPO"/reglas/*/*.md "$REPO"/skills/*/SKILL.md || FAIL=1

VALIDOS=0
validar_archivos "$SK" >/dev/null 2>&1
check "la skill tiene al menos un diagrama válido" "$([ "$VALIDOS" -ge 1 ] && echo si || echo no)" "si"

printf '# roto\n\n```diagrama\n{"nodos": [\n```\n' > "$T/roto.md"
validar_archivos "$T/roto.md" >/dev/null 2>&1
check "la fixture rota se detecta" "$?" "1"

printf '# vacio\n\n```estado\n{}\n```\n' > "$T/vacio.md"
validar_archivos "$T/vacio.md" >/dev/null 2>&1
check "un estado vacío se detecta" "$?" "1"

[ "$FAIL" = 0 ] && echo "todo ok" || echo "hay fallas"
exit "$FAIL"
