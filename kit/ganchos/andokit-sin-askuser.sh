#!/bin/bash
# Hook PreToolUse (AskUserQuestion): lo niega, desde el celu no se puede contestar.
cat >/dev/null
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Usá un bloque ```opciones en el texto (regla preguntas-con-opciones)"}}'
exit 0
