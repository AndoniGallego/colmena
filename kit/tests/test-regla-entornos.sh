#!/bin/bash
# La regla entornos-pc tiene que mandar a Ando al túnel de la app Entornos (no al navegador de la notebook),
# y no proponer exponer puertos. Que el instalador la linkee lo cubre test_kit_instalador.py.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE/.."
REGLA="$REPO/reglas/colmena/entornos-pc.md"

FAIL=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: esperado '$3', obtuve '$2'"; FAIL=1; fi; }

# La regla existe
if [ -f "$REGLA" ]; then r=si; else r=no; fi
check "la regla existe" "$r" "si"
[ -f "$REGLA" ] || { echo "FAIL no hay regla, se corta"; exit 1; }

# Contenido mínimo
for frase in "Entornos" "ssh -N -L" "localhost"; do
  case "$(cat "$REGLA")" in *"$frase"*) r=si;; *) r=no;; esac
  check "menciona '$frase'" "$r" "si"
done

# funnel solo aparece en una línea que lo prohíbe con "Nunca"
n_funnel=$(grep -c 'funnel' "$REGLA")
n_prohibido=$(grep 'funnel' "$REGLA" | grep -c 'Nunca')
check "funnel aparece solo dentro de una prohibición" "$([ "$n_funnel" = "$n_prohibido" ] && echo si || echo no)" "si"
check "funnel aparece al menos una vez" "$([ "$n_funnel" -ge 1 ] && echo si || echo no)" "si"

# Longitud
lineas=$(wc -l < "$REGLA")
check "la regla tiene 25 líneas o menos" "$([ "$lineas" -le 25 ] && echo si || echo no)" "si"

# README tiene la fila
case "$(cat "$REPO/README.md")" in *'`reglas/colmena/entornos-pc.md`'*) r=si;; *) r=no;; esac
check "README tiene la fila de la regla" "$r" "si"

exit $FAIL
