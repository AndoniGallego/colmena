#!/bin/bash
# La regla nudo explica cómo usar el nudo (señalar controles en la PC de Ando) sin proponer prenderlo.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE/.."
REGLA="$REPO/reglas/colmena/nudo.md"
LINEA='> Esta regla rige cuando la sesión corre en una terminal de Colmena (COLMENA_TERMINAL=1). Si no sabés, aplicala.'

FAIL=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: esperado '$3', obtuve '$2'"; FAIL=1; fi; }

if [ -f "$REGLA" ]; then r=si; else r=no; fi
check "la regla existe" "$r" "si"
[ -f "$REGLA" ] || { echo "FAIL no hay regla, se corta"; exit 1; }

check "línea 3 de aviso" "$(sed -n 3p "$REGLA")" "$LINEA"
check "tiene propósito" "$(grep -c '^<!-- propósito: .* -->$' "$REGLA")" "1"

for frase in "orquestador nudo controles" "orquestador nudo senalar <n>" "--esperar" "orquestador nudo marcar 12:" \
             "orquestador nudo limpiar" "orquestador nudo estado" "foto vieja" "ocupado" "en_curso" "apagado" \
             "vencido" "fallo_pc" "celu"; do
  case "$(cat "$REGLA")" in *"$frase"*) r=si;; *) r=no;; esac
  check "menciona '$frase'" "$r" "si"
done

n=$(grep -ciE 'prend[eéa]|activ[aáe]' "$REGLA")
p=$(grep -iE 'prend[eéa]|activ[aáe]' "$REGLA" | grep -c 'Nunca')
check "prender/activar solo en una prohibición con Nunca" "$([ "$n" = "$p" ] && echo si || echo no)" "si"

# Los límites que la regla le dice a la sesión tienen que ser los del código.
NUDO_PY="$REPO/../backend/orquestador/nudo.py"
if [ ! -f "$NUDO_PY" ]; then
  check "existe backend/orquestador/nudo.py para comparar límites" "no" "si"
else
  texto_max=$(sed -n 's/^TEXTO_MAX = \([0-9]*\)$/\1/p' "$NUDO_PY")
  marcas_max=$(sed -n 's/^MARCAS_MAX = \([0-9]*\)$/\1/p' "$NUDO_PY")
  case "$(cat "$REGLA")" in *"hasta $texto_max caracteres"*) r=si;; *) r=no;; esac
  check "el límite de texto de la regla es TEXTO_MAX ($texto_max)" "$r" "si"
  case "$(cat "$REGLA")" in *"hasta $marcas_max por vez"*) r=si;; *) r=no;; esac
  check "el límite de marcas de la regla es MARCAS_MAX ($marcas_max)" "$r" "si"
fi

lineas=$(wc -l < "$REGLA")
check "la regla tiene 30 líneas o menos" "$([ "$lineas" -le 30 ] && echo si || echo no)" "si"

case "$(cat "$REPO/README.md")" in *'`reglas/colmena/nudo.md`'*) r=si;; *) r=no;; esac
check "README tiene la fila de la regla" "$r" "si"

exit $FAIL
