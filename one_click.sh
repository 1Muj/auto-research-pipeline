#!/usr/bin/env bash
# 一键入口：本地（Claude Code / venv）或 Vast.ai 搜索建实例
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"

usage() {
  echo "Usage: $0 {local|vast}"
  echo "  local  — venv + 依赖 + 示例实验（适合本机 / Claude Code）"
  echo "  vast   — 调用 vastai 搜索并创建实例（需 pip install vastai 与 API key）"
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
