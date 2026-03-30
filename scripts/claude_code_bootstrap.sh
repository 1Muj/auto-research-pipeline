#!/usr/bin/env bash
# Bootstrap for Claude Code / local dev: fresh venv per machine, install, smoke run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

# Each developer gets their own .venv under the repo root (not committed to git).
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e .

# Editable install may need src on PYTHONPATH for some setups.
export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"
auto-research run --cwd "${ROOT}" -e experiments/linear_regression.yaml

echo "Done. Activate with: source ${ROOT}/.venv/bin/activate"

