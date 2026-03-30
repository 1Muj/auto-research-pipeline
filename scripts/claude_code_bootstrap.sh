#!/usr/bin/env bash
# Bootstrap project for Claude Code / local dev: venv, deps, smoke run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"

export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"
auto-research run --cwd "${ROOT}" -e experiments/example.yaml

echo "Done. Activate with: source ${ROOT}/.venv/bin/activate"
