#!/usr/bin/env bash
# Load deploy/api.env into the current shell (ANTHROPIC_*, VAST_*, OPENAI_*, etc.).
# Create the file first: cp deploy/api.env.example deploy/api.env
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/deploy/api.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "load_api_env: missing ${ENV_FILE}" >&2
  echo "  cp deploy/api.env.example deploy/api.env  # then fill keys" >&2
  return 1 2>/dev/null || exit 1
fi
set -a
# shellcheck disable=SC1091
source "${ENV_FILE}"
set +a
echo "load_api_env: sourced ${ENV_FILE}"
