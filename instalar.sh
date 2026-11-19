#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

falta=0
need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Falta $1: $2"
    falta=1
  fi
}

need uv 'curl -LsSf https://astral.sh/uv/install.sh | sh'
need node 'instalalo desde https://nodejs.org o con el gestor de tu sistema'
need npm 'viene con node; reinstalá node si no está'
need claude 'npm install -g @anthropic-ai/claude-code'
need python3 'instalá Python 3.10+ con el gestor de tu sistema'
need systemctl 'systemd no está disponible en esta máquina'

if [[ "$falta" -ne 0 ]]; then
  exit 1
fi

uv sync
exec uv run orquestador instalar "$@"
