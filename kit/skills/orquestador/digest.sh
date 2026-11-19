#!/usr/bin/env bash
# Resumen compacto de una sesión de Claude: título, último prompt y los últimos N turnos de texto.
# Uso: digest.sh <session-id> [turnos=12] [max_chars_por_turno=1200] [completo]
# Con `completo` suma los archivos tocados y los cambios del repo de la sesión.
set -euo pipefail

sid="${1:?session-id requerido}"
n="${2:-12}"
max="${3:-1200}"
modo="${4:-}"

# Qué cuenta como bloque: la misma definición que el hook Stop y Colmena (ganchos/lib-bloques.sh).
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../ganchos/lib-bloques.sh"

[[ "$sid" =~ ^[0-9a-f-]{8,64}$ ]] || { echo "session-id inválido (solo [0-9a-f-], 8-64 chars)" >&2; exit 2; }

file=""
for f in "$HOME"/.claude/projects/*/"$sid".jsonl; do
  [ -f "$f" ] && file="$f" && break
done
[ -n "$file" ] || { echo "transcript no encontrado para $sid" >&2; exit 1; }

title=$(jq -r 'select(.type=="ai-title") | .aiTitle' "$file" | tail -1)
last=$(jq -r 'select(.type=="last-prompt") | .lastPrompt' "$file" | tail -1)
mtime=$(date -r "$file" '+%Y-%m-%d %H:%M')

printf '# %s\nsession: %s · última actividad: %s\núltimo prompt: %s\n' "$title" "$sid" "$mtime" "${last:0:400}"

# último bloque estado que Colmena mostraría, de todo el transcript
estado=$(jq -rn "$BLOQUES_JQ"'
  [inputs | select(.type == "assistant")
   | (.message.content | if type == "array" then map(select(.type == "text") | .text) | join("\n") else "" end)
   | select(test("estado"; "i"))]
  | first(reverse[] | [bq_segmentos[] | select(.tipo == "estado" and .valor != null) | .valor] | last // empty)
  | (if .falta then "falta: " + .falta else empty end), (if .pide then "pide: " + .pide else empty end)
' "$file")
[ -z "$estado" ] || printf '%s\n' "$estado"
printf '\n'

cwd=$(jq -rn 'first(inputs | select((.cwd // "") != "") | .cwd) // empty' "$file")

if [ "$modo" = "completo" ]; then
  tocados=$(jq -r '
    select(.type == "assistant") | .message.content | arrays | .[]
    | select(.type == "tool_use")
    | if (.name == "Edit" or .name == "Write" or .name == "MultiEdit") then .input.file_path
      elif .name == "NotebookEdit" then .input.notebook_path else empty end
    | select(. != null and . != "")
  ' "$file" | awk -v cwd="$cwd" '
    !seen[$0]++ { p = $0
      if (cwd != "" && index(p, cwd "/") == 1) p = substr(p, length(cwd) + 2)
      if (++k <= 30) print p }
    END { if (k > 30) printf "…(+%d)\n", k - 30 }')
  if [ -n "$tocados" ]; then
    printf '## Archivos tocados\n%s\n\n' "$tocados"
  fi
  if [ -n "$cwd" ] && [ -d "$cwd" ]; then
    stat=$(timeout 5 git -C "$cwd" diff --stat HEAD 2>/dev/null || true)
    st=$(timeout 5 git -C "$cwd" status --short 2>/dev/null || true)
    if [ -n "$stat$st" ]; then
      printf '## Cambios en el repo\n```\n'
      [ -z "$stat" ] || printf '%s\n' "$stat"
      [ -z "$st" ] || printf '%s\n' "$st"
      printf '```\n\n'
    fi
  fi
fi

jq -nr --argjson max "$max" --arg n "$n" "$BLOQUES_JQ"'
  def clip: if length > $max then .[0:$max] + " …[recortado]" else . end;
  def resumen:
    if has("md") then .md
    elif .tipo == "estado" then "[estado omitido]"
    elif .tipo == "diagrama" then
      ((.valor.titulo // "") | tostring) as $x | if $x != "" then "[diagrama: " + $x + "]" else "[diagrama]" end
    elif .tipo == "pruebas" then
      ((.valor.titulo // "") | tostring) as $x | if $x != "" then "[pruebas: " + $x + "]" else "[pruebas]" end
    elif .tipo == "opciones" then
      ((.valor.pregunta // "") | tostring) as $x | if $x != "" then "[opciones: " + $x + "]" else "[opciones]" end
    else .texto end;
  (try ($n | tonumber) catch 12) as $n
  | [inputs
     | if .type == "user" then
         (.message.content
           | if type == "string" then .
             else (map(select(.type == "text") | .text) | join("\n")) end) as $t
         | select($t != "" and ($t | test("^(<(command-|local-command|system-reminder)|Another Claude session sent a message)") | not))
         | {k: "USER", t: $t}
       elif .type == "assistant" then
         (.message.content | map(select(.type == "text") | .text) | join("\n")) as $t
         | select($t != "")
         | {k: "CLAUDE", t: $t}
       else empty end]
  | if $n < 1 then empty else .[-$n:][] end
  | if .k == "USER" then "## USER\n" + (.t | clip)
    else "## CLAUDE\n" + ([.t | bq_segmentos[] | resumen | select(. != "")] | join("\n") | clip) end
' "$file" | awk -v n="$n" '
  /^## (USER|CLAUDE)$/ { c++ }
  { buf[c] = buf[c] $0 "\n" }
  END { s = c - n + 1; if (s < 1) s = 1; for (i = s; i <= c; i++) printf "%s\n", buf[i] }
'
