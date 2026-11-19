#!/bin/bash
# Librería compartida de los hooks: reconoce los bloques (estado, opciones, diagrama) igual que los dibuja Colmena.
# Qué cuenta como bloque (```estado, ```opciones, ```diagrama...): la misma regla que usa Colmena para
# dibujar las tarjetas (frontend/src/lib/segments.ts, fence.ts, estado.ts). Única definición: la usan
# el hook Stop, digest.sh y el test de ejemplos.
#  - apertura: línea con sangría opcional, 3+ ``` o ~~~, el tipo sin importar mayúsculas y lo que siga
#    (```estado json); necesita una línea después.
#  - cierre: el mismo carácter, igual o más largo, solo en su línea. Sin cierre, el bloque llega al final.
#  - JSON tolerante: si no parsea, se arreglan comillas tipográficas y comas finales y se reintenta.
#  - estado vale si tiene hizo, falta o pide con texto; pruebas, si tiene titulo con texto y algún caso con
#    nombre con texto y resultado ok|falla|omitida (pruebas.ts); los demás, si son un objeto.
BLOQUES_JQ='
def bq_lenient:
  (sub("^\\s+"; "") | sub("\\s+$"; "")) as $b
  | ((try ($b | fromjson) catch null)
     // ($b | gsub("[“”]"; "\"") | gsub("[‘’]"; "'"'"'") | gsub(",\\s*(?<c>[}\\]])"; "\(.c)")
         | try fromjson catch null));
def bq_valor($k):
  if $k == "estado" then
    (if type == "object" then with_entries(select((.key == "hizo" or .key == "falta" or .key == "pide")
       and (.value | type) == "string" and (.value | test("\\S")))) else {} end)
    | if length > 0 then . else null end
  elif $k == "pruebas" then
    (if type == "object" and ((.titulo // null) | type) == "string" and (.titulo | test("\\S"))
        and ((.casos // null) | type) == "array"
        and any(.casos[:60][]?; type == "object" and ((.nombre // null) | type) == "string" and (.nombre | test("\\S"))
            and ((.resultado // null) | type) == "string"
            and (.resultado | sub("^\\s+"; "") | sub("\\s+$"; "") | ascii_downcase | IN("ok", "falla", "omitida")))
     then . else null end)
  elif type == "object" then . else null end;
def bq_cerrar($L; $b; $fin; $cerrado):
  ($L[$b.ini + 1:$fin] | join("\n")) as $c
  | {tipo: $b.k, valor: ($c | bq_lenient | bq_valor($b.k)), cerrado: $cerrado,
     texto: ($L[$b.ini:(if $cerrado then $fin + 1 else $fin end)] | join("\n"))};
def bq_fence: index("```") != null or index("~~~") != null;
# texto -> [{md} | {tipo, valor (null si Colmena no lo mostraría), cerrado, texto}]
def bq_segmentos:
  if bq_fence | not then [{md: .}] else
  split("\n") as $L | ($L | length) as $n
  | reduce ([range(0; $n) | select($L[.][0:1] | . == "`" or . == "~" or . == " " or . == "\t")][]) as $i ({out: [], desde: 0, blk: null};
      .blk as $b
      | if $b == null then
          ([$L[$i] | capture("^[ \\t]*(?<f>`{3,}|~{3,})[ \\t]*(?<k>opciones|diagrama|pregunta|aviso|estado|pruebas|flujo)(?![A-Za-z0-9_])"; "i")] | .[0]) as $o
          | if $o != null and $i < $n - 1 then
              (if $i > .desde then .out += [{md: ($L[.desde:$i] | join("\n"))}] else . end)
              | .blk = {k: ($o.k | ascii_downcase), c: $o.f[0:1], len: ($o.f | length), ini: $i}
            else . end
        elif ($L[$i] | test("^[ \\t]*" + (if $b.c == "`" then "`" else "~" end) + "{" + ($b.len | tostring) + ",}[ \\t]*$")) then
          .out += [bq_cerrar($L; $b; $i; true)] | .blk = null | .desde = $i + 1
        else . end)
  | (if .blk != null then .out += [bq_cerrar($L; .blk; $n; false)] | .blk = null | .desde = $n else . end)
  | (if .desde < $n then .out += [{md: ($L[.desde:$n] | join("\n"))}] else . end)
  | .out end;
'

# bloques_contar TIPO: lee texto por stdin e imprime "validos invalidos" de los bloques de ese tipo.
bloques_contar() {
  jq -Rsr --arg t "$1" "$BLOQUES_JQ"'
    [bq_segmentos[] | select(.tipo == $t)]
    | "\(map(select(.valor != null)) | length) \(map(select(.valor == null)) | length)"'
}
