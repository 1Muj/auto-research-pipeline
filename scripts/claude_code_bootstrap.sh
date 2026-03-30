#!/usr/bin/env bash
# Bootstrap for Claude Code / local dev: venv + install (main has no bundled experiment YAML).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"

export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"
auto-research version
auto-research --help >/dev/null

echo ""
echo "Core branch: add your experiment under experiments/ (see experiments/README.md), then run:"
echo "  auto-research run --cwd \"${ROOT}\" -e experiments/your_experiment.yaml"
echo ""
echo "Done. Activate with: source ${ROOT}/.venv/bin/activate"
