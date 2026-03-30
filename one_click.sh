#!/usr/bin/env bash
# One-click entry: local bootstrap (Claude Code / dev) or Vast.ai instance creation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"

usage() {
  echo "Usage: $0 {local|vast}"
  echo "  local — create .venv, install deps, run linear regression experiment"
  echo "  vast  — search/create Vast instance (needs: pip install vastai + API key)"
}

case "${1:-}" in
  local)
    bash scripts/claude_code_bootstrap.sh
    ;;
  vast)
    bash scripts/deploy_vast_5080.sh
    ;;
  *)
    usage
    exit 1
    ;;
esac

