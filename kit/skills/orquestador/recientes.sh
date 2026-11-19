#!/usr/bin/env bash
# Sesiones de Claude con actividad reciente: session id, carpeta, última actividad y título.
# Uso: recientes.sh [horas=24] [max=20]
set -euo pipefail

horas="${1:-24}"
max="${2:-20}"
[[ "$horas" =~ ^[0-9]{1,4}$ && "$max" =~ ^[0-9]{1,3}$ ]] || { echo "uso: recientes.sh [horas] [max]" >&2; exit 2; }

find "$HOME/.claude/projects" -mindepth 2 -maxdepth 2 -name '*.jsonl' -mmin "-$((horas * 60))" -printf '%T@ %p\n' 2>/dev/null \
  | sort -rn | head -n "$max" | while read -r _ f; do
    sid=$(basename "$f" .jsonl)
    [[ "$sid" =~ ^[0-9a-f-]{8,64}$ ]] || continue
    cwd=$(jq -r 'select(.cwd != null) | .cwd' "$f" 2>/dev/null | tail -1)
    title=$(jq -r 'select(.type=="ai-title") | .aiTitle' "$f" 2>/dev/null | tail -1)
    case "$cwd" in */data/centinela) continue ;; esac
    corto="~${cwd#"$HOME"}"; [[ "$cwd" == "$HOME"* ]] || corto="$cwd"
    printf '%s\t%s\t%s\t%s\n' "$sid" "$(date -r "$f" '+%m-%d %H:%M')" "$corto" "${title:-(sin título)}"
  done
