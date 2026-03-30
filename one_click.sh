#!/usr/bin/env bash
# 一键入口：本地（Claude Code / venv）或 Vast.ai 搜索建实例
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"

usage() {
  echo "Usage: $0 {local|vast}"
  echo "  local — venv + install + verify CLI (add your own experiments/*.yaml on main)"
  echo "  vast  — Vast.ai search/create instance (needs: pip install vastai + API key)"
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
