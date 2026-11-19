#!/bin/bash
# Hook Stop: en terminales de Colmena, pide el bloque ```estado y corrige ```opciones/```diagrama rotos (una sola vez).
LIB="${BASH_SOURCE[0]%/*}/lib-bloques.sh"

main() {
  [ "${COLMENA_TERMINAL:-}" = 1 ] || exit 0
  command -v jq >/dev/null 2>&1 || exit 0
  local in; in=$(cat)
  printf '%s' "$in" | jq -e 'type=="object"' >/dev/null 2>&1 || exit 0
  [ "$(printf '%s' "$in" | jq -r '.stop_hook_active // false')" = true ] && exit 0
  local tp msg; tp=$(printf '%s' "$in" | jq -r '.transcript_path // empty')
  msg=$(printf '%s' "$in" | jq -r '.last_assistant_message // empty')
  [ -n "$tp" ] && [ -r "$tp" ] || exit 0
  source "$LIB" || exit 0

  local to=(); command -v timeout >/dev/null 2>&1 && to=(timeout 8)
  local st; st=$("${to[@]}" jq -n -c 'reduce inputs as $e ({tools:false,text:""};
    if $e.type=="user" and ($e.isMeta|not) and ($e.isSidechain|not)
       and (($e.message.content|type)=="string" or any($e.message.content[]?; .type!="tool_result"))
    then .tools=false | .text=""
    elif $e.type=="assistant" and ($e.isSidechain|not) then
      (if any($e.message.content[]?; .type=="tool_use") then .tools=true else . end)
      | ([$e.message.content[]? | select(.type=="text") | .text] | join("\n")) as $t
      | (if $t=="" then . else .text=$t end)
    else . end)' "$tp" 2>/dev/null) || exit 0
  [ "$(printf '%s' "$st" | jq -r '.tools' 2>/dev/null)" = true ] || exit 0

  local texto="$msg"
  [ -n "$texto" ] || texto=$(printf '%s' "$st" | jq -r '.text')

  local ok mal falta=()
  read -r ok mal <<<"$(printf '%s' "$texto" | bloques_contar estado)"
  [ -n "$mal" ] || exit 0
  [ "$ok" -ge 1 ] && [ "$mal" -eq 0 ] || falta+=("estado")
  read -r ok mal <<<"$(printf '%s' "$texto" | bloques_contar opciones)"
  [ -n "$mal" ] || exit 0
  [ "$mal" -eq 0 ] || falta+=("opciones")
  read -r ok mal <<<"$(printf '%s' "$texto" | bloques_contar diagrama)"
  [ -n "$mal" ] || exit 0
  [ "$mal" -eq 0 ] || falta+=("diagrama")
  [ "${#falta[@]}" -gt 0 ] || exit 0

  local lista; lista=$(IFS=,; echo "${falta[*]}"); lista=${lista//,/, }
  jq -nc --arg l "$lista" '{decision:"block",reason:("Falta o está roto el bloque: " + $l + ". Agregá o corregí el bloque al final del mensaje, con JSON válido (reglas estado-sesion, preguntas-con-opciones, diagramas).")}'
}

main || exit 0
exit 0
