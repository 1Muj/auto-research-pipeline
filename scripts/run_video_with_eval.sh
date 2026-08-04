#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CALLER_DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
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
if [[ -n "$CALLER_DEEPSEEK_API_KEY" ]]; then
  export DEEPSEEK_API_KEY="$CALLER_DEEPSEEK_API_KEY"
fi

# The full demo is video-native by default. Use AUTO_VIDEO_RENDER_STYLE_OVERRIDE=arbor
# only when intentionally comparing against the legacy slide renderer.
export AUTO_VIDEO_RENDER_STYLE="${AUTO_VIDEO_RENDER_STYLE_OVERRIDE:-scene}"
export AUTO_VIDEO_VISION_ATTEMPTS="${AUTO_VIDEO_VISION_ATTEMPTS:-2}"

INPUT_PATH="${1:-inputs/papers/Automatic Video Generation.pdf}"
KIND="${KIND:-paper}"
PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/bin/python}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
RUN_ROOT="${RUN_ROOT:-/tmp/auto_video_runs}"
OUT="${OUT:-${RUN_ROOT}/paper2video_full_${RUN_ID}}"
LOG="${LOG:-${RUN_ROOT}/logs/paper2video_full_${RUN_ID}.log}"
MAX_SLIDES="${MAX_SLIDES:-10}"
SECONDS_PER_SLIDE="${SECONDS_PER_SLIDE:-22}"
FPS="${FPS:-24}"
TARGET_SCORE="${TARGET_SCORE:-0.88}"
MIN_REVISIONS="${MIN_REVISIONS:-1}"
MAX_REVISIONS="${MAX_REVISIONS:-3}"
AUTO_VIDEO_EVAL_REPAIR_ROUNDS="${AUTO_VIDEO_EVAL_REPAIR_ROUNDS:-1}"
AUTO_VIDEO_EVAL_REPAIR_THRESHOLD="${AUTO_VIDEO_EVAL_REPAIR_THRESHOLD:-7.0}"
EVAL_REPORT="$OUT/directorbench_prompt_eval_report.json"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python runner: $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -f "$INPUT_PATH" && ! -d "$INPUT_PATH" ]]; then
  echo "Input not found: $INPUT_PATH" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG")" "$OUT"

echo "ROOT=$ROOT"
echo "INPUT=$INPUT_PATH"
echo "PYTHON_BIN=$PYTHON_BIN"
echo "OUT=$OUT"
echo "LOG=$LOG"
echo "EVAL_REPORT=$EVAL_REPORT"
echo "EVAL_REPAIR_ROUNDS=$AUTO_VIDEO_EVAL_REPAIR_ROUNDS"
echo "EVAL_REPAIR_THRESHOLD=$AUTO_VIDEO_EVAL_REPAIR_THRESHOLD"
echo "RENDER_STYLE=$AUTO_VIDEO_RENDER_STYLE"
echo "TEXT_MODEL=${LUMID_MODEL:-${DEEPSEEK_MODEL:-${OPENAI_MODEL:-not_set}}}"
echo "VISION_MODEL=${OPENAI_VISION_MODEL:-${LUMID_OMNI_MODEL:-not_set}}"
echo "IMAGE_MODEL=${LUMID_IMAGE_MODEL:-not_set}"
echo "TTS_MODEL=${LUMID_TTS_MODEL:-not_set}"
echo "TTS_TEMPO=${AUTO_VIDEO_TTS_TEMPO:-1.00}"
echo "POST_SPEECH_HOLD=${AUTO_VIDEO_POST_SPEECH_HOLD_SEC:-1.20}s"
echo "DEEPSEEK_FALLBACK=${DEEPSEEK_API_KEY:+loaded}"

for module in pypdf; do
  if ! "$PYTHON_BIN" -c "import ${module}" >/dev/null 2>&1; then
    echo "Installing missing Python dependency: ${module}"
    "$PYTHON_BIN" -m pip install "${module}"
  fi
done

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$PYTHON_BIN" scripts/run_video_with_eval.py \
  --input "$INPUT_PATH" \
  --kind "$KIND" \
  --out-dir "$OUT" \
  --max-slides "$MAX_SLIDES" \
  --seconds-per-slide "$SECONDS_PER_SLIDE" \
  --fps "$FPS" \
  --use-api \
  --use-image-api \
  --use-tts \
  --use-omni-cursor \
  --target-score "$TARGET_SCORE" \
  --min-revisions "$MIN_REVISIONS" \
  --max-revisions "$MAX_REVISIONS" \
  --eval-report "$EVAL_REPORT" \
  --eval-repair-rounds "$AUTO_VIDEO_EVAL_REPAIR_ROUNDS" \
  --eval-repair-threshold "$AUTO_VIDEO_EVAL_REPAIR_THRESHOLD" \
  2>&1 | tee "$LOG"

echo ""
echo "Done."
echo "Video output: $OUT"
echo "Log: $LOG"
echo "Evaluation report: $EVAL_REPORT"

if command -v jq >/dev/null 2>&1; then
  jq '.evaluation | {
    overall_score,
    confidence,
    classification,
    major_bottlenecks,
    highest_priority_fixes
  }' "$EVAL_REPORT"
fi
