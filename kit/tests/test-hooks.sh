#!/bin/bash
# Tests de los hooks de andokit (sin-askuser, stop-bloques) con datos sintéticos.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS="$HERE/../ganchos"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

FAIL=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: esperado '$3', obtuve '$2'"; FAIL=1; fi; }

# A1: sin-askuser
out=$(printf '{"tool_name":"AskUserQuestion"}' | "$HOOKS/andokit-sin-askuser.sh"); rc=$?
check "askuser exit 0" "$rc" "0"
check "askuser deny" "$(printf '%s' "$out" | jq -r .hookSpecificOutput.permissionDecision)" "deny"
check "askuser reason" "$(printf '%s' "$out" | jq -r .hookSpecificOutput.permissionDecisionReason)" 'Usá un bloque ```opciones en el texto (regla preguntas-con-opciones)'

# A2: stop-bloques
STOP="$HOOKS/andokit-stop-bloques.sh"
F='```'
VALIDO="Listo.
${F}estado
{\"hizo\":\"algo\"}
${F}"
SINEST="Listo, sin bloque."
OPC_MAL="${VALIDO}
${F}opciones
{no es json
${F}"
DIA_MAL="${VALIDO}
${F}diagrama
[1,2]
${F}"
# tr "<texto>" [con_tool]: transcript sintético
tr_mk() {
  local f="$T/tr.jsonl"
  jq -nc '{type:"user",message:{role:"user",content:"hacé algo"}}' > "$f"
  if [ "${2:-}" = tool ]; then
    jq -nc '{type:"assistant",message:{content:[{type:"tool_use",id:"t1",name:"Bash",input:{}}]}}' >> "$f"
    jq -nc '{type:"user",message:{content:[{type:"tool_result",tool_use_id:"t1",content:"ok"}]}}' >> "$f"
  fi
  jq -nc --arg t "$1" '{type:"assistant",message:{content:[{type:"text",text:$t}]}}' >> "$f"
  echo "$f"
}
stop() { printf '%s' "$1" | COLMENA_TERMINAL=1 "$STOP"; }
hin() { jq -nc --arg p "$1" --argjson a "${2:-false}" '{stop_hook_active:$a,transcript_path:$p}'; }

f=$(tr_mk "$SINEST" tool)
check "stop_hook_active no imprime" "$(stop "$(hin "$f" true)")" ""
f=$(tr_mk "$SINEST")
check "sin tool_use ni estado: vacío" "$(stop "$(hin "$f")")" ""
f=$(tr_mk "$SINEST" tool); out=$(stop "$(hin "$f")")
check "tool_use sin estado: block" "$(printf '%s' "$out" | jq -r .decision)" "block"
case "$(printf '%s' "$out" | jq -r .reason)" in *estado*) r=ok;; *) r=no;; esac
check "reason nombra estado" "$r" "ok"
f=$(tr_mk "$VALIDO" tool); check "tool_use y estado válido: vacío" "$(stop "$(hin "$f")")" ""
f=$(tr_mk "$(printf '%s\n%sestado\n{roto\n%s' hola "$F" "$F")" tool); out=$(stop "$(hin "$f")")
check "estado inválido: block" "$(printf '%s' "$out" | jq -r .decision)" "block"
f=$(tr_mk "$OPC_MAL" tool); out=$(stop "$(hin "$f")")
check "opciones inválido: block" "$(printf '%s' "$out" | jq -r .decision)" "block"
case "$(printf '%s' "$out" | jq -r .reason)" in *opciones*) r=ok;; *) r=no;; esac
check "reason nombra opciones" "$r" "ok"
f=$(tr_mk "$DIA_MAL" tool); out=$(stop "$(hin "$f")")
check "diagrama inválido: block" "$(printf '%s' "$out" | jq -r .decision)" "block"
case "$(printf '%s' "$out" | jq -r .reason)" in *diagrama*) r=ok;; *) r=no;; esac
check "reason nombra diagrama" "$r" "ok"

f=$(tr_mk "$SINEST" tool)
mkdir "$T/nojq"; ln -s "$(command -v bash)" "$T/nojq/bash"; ln -s "$(command -v cat)" "$T/nojq/cat"
out=$(hin "$f" | COLMENA_TERMINAL=1 PATH="$T/nojq" "$T/nojq/bash" "$STOP"); rc=$?
check "fail-open sin jq: salida" "$out" ""; check "fail-open sin jq: rc" "$rc" "0"
out=$(stop "$(jq -nc --arg p "$T/no-existe" '{stop_hook_active:false,transcript_path:$p}')"); rc=$?
check "fail-open transcript inexistente: salida" "$out" ""; check "fail-open transcript inexistente: rc" "$rc" "0"
out=$(stop 'basura'); rc=$?
check "fail-open no JSON: salida" "$out" ""; check "fail-open no JSON: rc" "$rc" "0"

f=$(tr_mk "$SINEST" tool)
check "sin COLMENA_TERMINAL: vacío" "$(printf '%s' "$(hin "$f")" | env -u COLMENA_TERMINAL "$STOP")" ""

f=$(tr_mk "$VALIDO" tool)
out=$(stop "$(jq -nc --arg p "$f" --arg m "$SINEST" '{stop_hook_active:false,transcript_path:$p,last_assistant_message:$m}')")
check "usa last_assistant_message: block" "$(printf '%s' "$out" | jq -r .decision)" "block"

# K1 menores: reset por prompt, sidechain, opciones/diagrama válidos
J() { jq -nc "$@"; }
OPC_OK="${VALIDO}
${F}opciones
{\"pregunta\":\"x\",\"opciones\":[]}
${F}
${F}diagrama
{\"titulo\":\"x\"}
${F}"
f=$(tr_mk "$OPC_OK" tool)
check "opciones y diagrama válidos: vacío" "$(stop "$(hin "$f")")" ""

f="$T/m1.jsonl"
{ J '{type:"user",message:{content:"uno"}}'
  J '{type:"assistant",message:{content:[{type:"tool_use",id:"a",name:"Bash",input:{}}]}}'
  J --arg t "$VALIDO" '{type:"assistant",message:{content:[{type:"text",text:$t}]}}'
  J '{type:"user",message:{content:"dos"}}'
  J '{type:"assistant",message:{content:[{type:"tool_use",id:"b",name:"Bash",input:{}}]}}'; } > "$f"
check "M1: texto de turno anterior no cubre el actual" "$(stop "$(hin "$f")" | jq -r .decision)" "block"

f="$T/m5.jsonl"
{ J '{type:"user",message:{content:"uno"}}'
  J '{type:"assistant",message:{content:[{type:"tool_use",id:"a",name:"Bash",input:{}}]}}'
  J '{type:"user",message:{content:"dos"}}'
  J --arg t "$SINEST" '{type:"assistant",message:{content:[{type:"text",text:$t}]}}'; } > "$f"
check "M5: prompt nuevo resetea el flag de herramientas" "$(stop "$(hin "$f")")" ""

f="$T/m2a.jsonl"
{ J '{type:"user",message:{content:"uno"}}'
  J '{type:"assistant",message:{content:[{type:"tool_use",id:"a",name:"Bash",input:{}}]}}'
  J --arg t "$SINEST" '{type:"assistant",message:{content:[{type:"text",text:$t}]}}'
  J --arg t "$VALIDO" '{type:"assistant",isSidechain:true,message:{content:[{type:"text",text:$t}]}}'; } > "$f"
check "M2: sidechain no pisa el texto" "$(stop "$(hin "$f")" | jq -r .decision)" "block"

f="$T/m2b.jsonl"
{ J '{type:"user",message:{content:"uno"}}'
  J '{type:"assistant",isSidechain:true,message:{content:[{type:"tool_use",id:"a",name:"Bash",input:{}}]}}'
  J --arg t "$SINEST" '{type:"assistant",message:{content:[{type:"text",text:$t}]}}'; } > "$f"
check "M2: sidechain no prende el flag de herramientas" "$(stop "$(hin "$f")")" ""

# I-2: lo que cuenta como bloque es lo que Colmena muestra (segments.ts, fence.ts, estado.ts)
caso() { # nombre texto esperado(""|block)
  local f; f=$(tr_mk "$2" tool)
  check "colmena: $1" "$(stop "$(hin "$f")" | jq -r '.decision // empty' 2>/dev/null)" "$3"
}
T3='~~~'
caso "~~~estado se acepta" "Listo.
${T3}estado
{\"hizo\":\"algo\"}
${T3}" ""
caso "estado con info string se acepta" "Listo.
${F}estado json
{\"hizo\":\"algo\"}
${F}" ""
caso "cuatro backticks se aceptan" "Listo.
${F}\`estado
{\"hizo\":\"algo\"}
${F}\`" ""
caso "tipo en mayúsculas se acepta" "Listo.
${F}Estado
{\"hizo\":\"algo\"}
${F}" ""
caso "coma final se acepta" "Listo.
${F}estado
{\"hizo\":\"algo\",}
${F}" ""
caso "comillas tipográficas se aceptan" "Listo.
${F}estado
{“hizo”: “algo”}
${F}" ""
caso "estado final sin cerrar se acepta" "Listo.
${F}estado
{\"hizo\":\"algo\"}" ""
caso "fence con sangría se acepta" "Listo.
  ${F}estado
  {\"hizo\":\"algo\"}
  ${F}" ""
caso "cierre más largo se acepta" "Listo.
${F}estado
{\"hizo\":\"algo\"}
${F}\`" ""
caso "opciones con coma final se acepta" "${VALIDO}
${F}opciones
{\"pregunta\":\"x\",\"opciones\":[],}
${F}" ""
caso "pruebas válido + estado válido no bloquea" "Listo.
${F}pruebas
{\"titulo\":\"Login\",\"casos\":[{\"nombre\":\"entra\",\"resultado\":\"ok\"}]}
${F}
${F}estado
{\"hizo\":\"algo\"}
${F}" ""
caso "pruebas inválido no se exige ni bloquea" "Listo.
${F}pruebas
{roto
${F}
${F}estado
{\"hizo\":\"algo\"}
${F}" ""
caso "un estado dentro de pruebas no cuenta como estado" "Listo.
\`\`\`\`pruebas
{\"titulo\":\"X\",\"casos\":[{\"nombre\":\"n\",\"resultado\":\"ok\",\"detalle\":\"x\"}]}
${F}estado
{\"hizo\":\"falso\"}
${F}
\`\`\`\`" "block"
caso "estado vacío {} bloquea" "Listo.
${F}estado
{}
${F}" "block"
caso "estado sin hizo/falta/pide bloquea" "Listo.
${F}estado
{\"foo\":1}
${F}" "block"
caso "estado con campos en blanco bloquea" "Listo.
${F}estado
{\"hizo\":\"  \",\"falta\":\"\"}
${F}" "block"
caso "estado con hizo no texto bloquea" "Listo.
${F}estado
{\"hizo\":1}
${F}" "block"
caso "cierre más corto no cierra: bloquea" "Listo.
${F}\`estado
{\"hizo\":\"algo\"}
${F}" "block"
caso "cierre con otro carácter no cierra: bloquea" "Listo.
${T3}estado
{\"hizo\":\"algo\"}
${F}" "block"
caso "estadox no es estado: bloquea" "Listo.
${F}estadox
{\"hizo\":\"algo\"}
${F}" "block"

[ "$FAIL" = 0 ] && echo "todo ok" || echo "hay fallas"
exit "$FAIL"
