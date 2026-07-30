#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

set -a
if [[ -f "/tmp/lumid.env" ]]; then
  # shellcheck disable=SC1091
  source "/tmp/lumid.env"
fi
if [[ -f "deploy/video_api.env" ]]; then
  # shellcheck disable=SC1091
  source "deploy/video_api.env"
fi
set +a

PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/bin/python}"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$PYTHON_BIN" -B scripts/check_video_models.py
