#!/bin/bash
# Tests de skills/orquestador/digest.sh con HOME temporal y transcripts sintéticos.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIGEST="$HERE/../skills/orquestador/digest.sh"
SKILL="$HERE/../skills/orquestador/SKILL.md"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
export HOME="$T/home"
mkdir -p "$HOME/.claude/projects/p"

FAIL=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: esperado '$3', obtuve '$2'"; FAIL=1; fi; }
has() { if printf '%s' "$2" | grep -qF -- "$3"; then echo "ok   $1"; else echo "FAIL $1: falta '$3'"; FAIL=1; fi; }
hasnt() { if printf '%s' "$2" | grep -qF -- "$3"; then echo "FAIL $1: no debía estar '$3'"; FAIL=1; else echo "ok   $1"; fi; }

F='```'
txt() { jq -nc --arg t "$1" --arg cwd "${2:-}" '{type:"assistant",cwd:$cwd,message:{content:[{type:"text",text:$t}]}}'; }
tool() { jq -nc --arg n "$1" --arg k "$2" --arg v "$3" --arg cwd "$4" '{type:"assistant",cwd:$cwd,message:{content:[{type:"tool_use",name:$n,input:{($k):$v}}]}}'; }
mk() { local sid=$1; shift; { jq -nc '{type:"ai-title",aiTitle:"Titulo"}'; jq -nc '{type:"last-prompt",lastPrompt:"hola"}'; cat; } > "$HOME/.claude/projects/p/$sid.jsonl"; }

# C1/C2
S1=aaaaaaaa1111
{
  txt "antes
${F}diagrama
{\"titulo\":\"Mapa X\",\"nodos\":[{\"id\":\"SECRETO1\"}]}
${F}
medio
${F}opciones
{\"pregunta\":\"Cual P?\",\"opciones\":[{\"label\":\"SECRETO2\"}]}
${F}
${F}diagrama
{roto SECRETO3
${F}
${F}estado
{\"hizo\":\"a\",\"falta\":\"viejo\",\"pide\":\"viejo2\"}
${F}"
  txt "${F}estado
{\"hizo\":\"b\",\"falta\":\"lo nuevo\",\"pide\":\"decidir\"}
${F}"
} | mk $S1
out=$("$DIGEST" $S1 12 5000)
has "diagrama con titulo" "$out" "[diagrama: Mapa X]"
hasnt "json diagrama oculto" "$out" "SECRETO1"
has "opciones con pregunta" "$out" "[opciones: Cual P?]"
hasnt "json opciones oculto" "$out" "SECRETO2"
has "estado omitido" "$out" "[estado omitido]"
has "diagrama invalido" "$out" "[diagrama]"
hasnt "json invalido oculto" "$out" "SECRETO3"
has "falta del ultimo estado" "$out" "falta: lo nuevo"
has "pide del ultimo estado" "$out" "pide: decidir"
hasnt "estado viejo no gana" "$out" "falta: viejo"
out=$("$DIGEST" $S1 1 5000)
check "turnos: solo el último" "$(printf '%s\n' "$out" | grep -c '^## CLAUDE$')" "1"
hasnt "turnos: el primero no está" "$out" "[diagrama: Mapa X]"

# K5: bloque pruebas
S3=aaaaaaaa3333
{
  txt "${F}pruebas
{\"titulo\":\"Login X\",\"casos\":[{\"nombre\":\"SECRETO4\",\"resultado\":\"ok\"}]}
${F}
${F}pruebas
{\"titulo\":\"SECRETO5\",\"casos\":[]}
${F}
${F}pruebas
{roto SECRETO6
${F}"
} | mk $S3
out=$("$DIGEST" $S3 12 5000)
has "pruebas con titulo" "$out" "[pruebas: Login X]"
hasnt "json pruebas oculto" "$out" "SECRETO4"
hasnt "titulo de pruebas sin casos oculto" "$out" "SECRETO5"
hasnt "json roto de pruebas oculto" "$out" "SECRETO6"
check "pruebas sin titulo valido: [pruebas]" "$(printf '%s\n' "$out" | grep -cx '\[pruebas\]')" "2"

S2=aaaaaaaa2222
txt "sin estado" | mk $S2
hasnt "sin estado no hay falta" "$("$DIGEST" $S2)" "falta:"
hasnt "sin estado no hay pide" "$("$DIGEST" $S2)" "pide:"

# C3
S3=aaaaaaaa3333
CW="$T/proj"; mkdir -p "$CW"
{
  tool Edit file_path "$CW/src/a.php" "$CW"
  tool Write file_path "$CW/b.txt" "$CW"
  tool Bash command "rm $CW/nada" "$CW"
  tool Edit file_path "$CW/src/a.php" "$CW"
  tool MultiEdit file_path "/otro/lugar/c.md" "$CW"
  tool NotebookEdit notebook_path "$CW/n.ipynb" "$CW"
} | mk $S3
out=$("$DIGEST" $S3)
hasnt "sin completo no hay archivos" "$out" "## Archivos tocados"
hasnt "sin completo no hay cambios" "$out" "## Cambios en el repo"
out=$("$DIGEST" $S3 12 1200 completo)
has "seccion archivos" "$out" "## Archivos tocados"
sec=$(printf '%s\n' "$out" | sed -n '/^## Archivos tocados/,/^$/p' | tail -n +2 | sed '/^$/d')
check "archivos orden, dedupe, relativos, sin Bash" "$sec" "$(printf 'src/a.php\nb.txt\n/otro/lugar/c.md\nn.ipynb')"

S4=aaaaaaaa4444
for i in $(seq 1 32); do tool Write file_path "$CW/f$i.txt" "$CW"; done | mk $S4
out=$("$DIGEST" $S4 12 1200 completo)
sec=$(printf '%s\n' "$out" | sed -n '/^## Archivos tocados/,/^$/p' | tail -n +2 | sed '/^$/d')
check "tope 30 + resto" "$(printf '%s\n' "$sec" | wc -l)" "31"
check "ultima linea del tope" "$(printf '%s\n' "$sec" | tail -1)" "…(+2)"

# C4
R="$T/repo"; mkdir -p "$R"
git -C "$R" init -q
echo uno > "$R/tracked.txt"
git -C "$R" add tracked.txt
git -C "$R" -c user.name=t -c user.email=t@t commit -q -m init
echo dos >> "$R/tracked.txt"
echo nuevo > "$R/untracked.txt"
S5=aaaaaaaa5555
tool Edit file_path "$R/tracked.txt" "$R" | mk $S5
out=$("$DIGEST" $S5 12 1200 completo)
has "seccion cambios" "$out" "## Cambios en el repo"
has "cambios menciona modificado" "$out" "tracked.txt |"
has "cambios menciona sin trackear" "$out" "?? untracked.txt"
S6=aaaaaaaa6666
tool Edit file_path "$CW/x" "$CW" | mk $S6
out=$("$DIGEST" $S6 12 1200 completo); rc=$?
check "no repo: exit 0" "$rc" "0"
hasnt "no repo: sin seccion cambios" "$out" "## Cambios en el repo"
S7=aaaaaaaa7777
tool Edit file_path "/no/existe/x" "/no/existe" | mk $S7
out=$("$DIGEST" $S7 12 1200 completo); rc=$?
check "cwd inexistente: exit 0" "$rc" "0"
hasnt "cwd inexistente: sin seccion" "$out" "## Cambios en el repo"

# Transcripts grandes: sin SIGPIPE (pipefail) ni con cwd repetido ni con lista de archivos > 64 KB
S8=aaaaaaaa8888
jq -nc --arg cwd "$CW" 'range(0;4000) | {type:"assistant",cwd:$cwd,message:{content:[{type:"text",text:("relleno " + (tostring) + (" x" * 250))}]}}' | mk $S8
check "transcript grande >= 2MB" "$([ "$(stat -c %s "$HOME/.claude/projects/p/$S8.jsonl")" -ge 1000000 ] && echo si)" "si"
out=$("$DIGEST" $S8 2 100); rc=$?
check "grande sin completo: exit 0" "$rc" "0"
has "grande sin completo: cabecera" "$out" "último prompt: hola"
out=$("$DIGEST" $S8 2 100 completo); rc=$?
check "grande con completo: exit 0" "$rc" "0"
has "grande con completo: cabecera" "$out" "último prompt: hola"
S9=aaaaaaaa9999
jq -nc --arg cwd "$CW" 'range(0;3000) | {type:"assistant",cwd:$cwd,message:{content:[{type:"tool_use",name:"Write",input:{file_path:($cwd + "/d/" + ("p" * 40) + (tostring) + ".txt")}}]}}' | mk $S9
out=$("$DIGEST" $S9 2 100 completo); rc=$?
check "lista > 64KB: exit 0" "$rc" "0"
has "lista > 64KB: resto" "$out" "…(+2970)"

# I-2: misma noción de bloque que Colmena y que el hook
T3='~~~'
SA=bbbbbbbb0001
{
  txt "  ${F}estado
  {\"hizo\":\"a\",\"falta\":\"con sangria\"}
  ${F}"
} | mk $SA
out=$("$DIGEST" $SA)
has "estado con sangría: falta" "$out" "falta: con sangria"
hasnt "estado con sangría: json oculto" "$out" '"falta"'
SB=bbbbbbbb0002
txt "${T3}Estado json
{\"hizo\":\"a\",\"pide\":\"tilde\",}
${T3}" | mk $SB
out=$("$DIGEST" $SB)
has "~~~Estado con info y coma final: pide" "$out" "pide: tilde"
has "~~~Estado: omitido" "$out" "[estado omitido]"
SC=bbbbbbbb0003
{
  txt "${F}estado
{\"hizo\":\"a\",\"falta\":\"el bueno\"}
${F}"
  txt "${F}estado
{\"foo\":1}
${F}"
  txt "${F}estado
{}
${F}"
} | mk $SC
out=$("$DIGEST" $SC)
has "estado vacío no pisa al último válido" "$out" "falta: el bueno"
SD=bbbbbbbb0004
txt "texto
${F}estado
{\"hizo\":\"a\",\"falta\":\"sin cerrar\"}" | mk $SD
out=$("$DIGEST" $SD)
has "estado sin cerrar: falta" "$out" "falta: sin cerrar"
has "estado sin cerrar: omitido" "$out" "[estado omitido]"
SE=bbbbbbbb0005
txt "${F}\`diagrama
{\"titulo\":\"Cuatro\",\"nodos\":[{\"id\":\"SECRETO4\"}]}
${F}\`
despues ${F} suelto" | mk $SE
out=$("$DIGEST" $SE)
has "cuatro backticks: diagrama con titulo" "$out" "[diagrama: Cuatro]"
hasnt "cuatro backticks: json oculto" "$out" "SECRETO4"
has "cuatro backticks: texto posterior" "$out" "despues"

# C5
has "SKILL menciona completo" "$(cat "$SKILL")" "completo"
has "SKILL tiene seccion Engram" "$(cat "$SKILL")" "## Engram"
has "SKILL pide mem_search" "$(cat "$SKILL")" "mem_search"
has "SKILL traspaso lee 30 turnos de 2500 completo" "$(cat "$SKILL")" 'digest.sh <sid> 30 2500 completo'
check "SKILL mensaje destino sin backticks anidados" "$(grep '^`Te traspaso' "$SKILL" | tr -cd '`' | wc -c)" "2"

exit $FAIL
