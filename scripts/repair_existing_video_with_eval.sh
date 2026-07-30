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

ARTIFACT_DIR="${1:?Usage: ./scripts/repair_existing_video_with_eval.sh /tmp/auto_video_runs/paper2video_full_...}"
PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/bin/python}"
FPS="${FPS:-24}"
SECONDS_PER_SLIDE="${SECONDS_PER_SLIDE:-22}"
TARGET_SLIDES="${TARGET_SLIDES:-0}"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$PYTHON_BIN" scripts/repair_existing_video_with_eval.py \
  --artifact-dir "$ARTIFACT_DIR" \
  --fps "$FPS" \
  --seconds-per-slide "$SECONDS_PER_SLIDE" \
  --target-slides "$TARGET_SLIDES" \
  --use-api \
  --use-tts
