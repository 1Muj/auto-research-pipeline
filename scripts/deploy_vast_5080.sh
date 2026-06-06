#!/usr/bin/env bash
# One-shot: search Vast.ai for RTX 5080 (or override), create instance, print SSH and next steps.
# Same entry: auto-research vast deploy --cwd .
# Claude Code: command "research-deploy-vast" (.claude/commands/research-deploy-vast.md)
# Prereq: pip install vastai && vastai set api-key YOUR_KEY
#
# Env:
#   VAST_GPU_QUERY   default: 'gpu_name=RTX_5080 num_gpus=1'
#   VAST_IMAGE       default: nvidia/cuda:12.4.1-runtime-ubuntu22.04
#   VAST_DISK_GB     default: 64
#
# Optional: put VAST_* (and VAST_API_KEY) in deploy/api.env — see deploy/api.env.example

set -euo pipefail

_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "${_ROOT}/deploy/api.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${_ROOT}/deploy/api.env"
  set +a
fi

: "${VAST_GPU_QUERY:=gpu_name=RTX_5080 num_gpus=1}"
: "${VAST_IMAGE:=nvidia/cuda:12.4.1-runtime-ubuntu22.04}"
: "${VAST_DISK_GB:=64}"

if ! command -v vastai &>/dev/null; then
  echo "Install CLI: pip install vastai"
  exit 1
fi

if [[ -n "${VAST_API_KEY:-}" ]]; then
  vastai set api-key "${VAST_API_KEY}" || true
fi

if [[ -n "${VAST_OFFER_ID:-}" ]]; then
  OFFER_ID="${VAST_OFFER_ID}"
  echo "Using VAST_OFFER_ID=${OFFER_ID}"
else
  echo "Searching offers: ${VAST_GPU_QUERY}"
  # First column is offer id in default table output; adjust if your CLI version differs.
  OFFER_ID="$(vastai search offers "${VAST_GPU_QUERY}" -o dph --limit 5 | awk 'NR==2 {print $1}')"
  if [[ -z "${OFFER_ID}" ]]; then
    echo "No offers found. Try loosening VAST_GPU_QUERY or set VAST_OFFER_ID manually."
    exit 1
  fi
fi
echo "Creating instance from offer ${OFFER_ID}..."
OUT="$(vastai create instance "${OFFER_ID}" --image "${VAST_IMAGE}" --disk "${VAST_DISK_GB}" --ssh --direct 2>&1)"
echo "${OUT}"

cat <<EOF

Next steps on the new instance:
  1. SSH using the connection string from Vast console or vastai show instances.
  2. Install base tools if the image does not already include them:
       apt-get update && apt-get install -y git curl tar python3 python3-pip python3-venv
  3. Clone this repo and run: bash scripts/setup_github_runner.sh OWNER/REPO
  4. In GitHub: add secrets (ANTHROPIC_API_KEY optional), dispatch workflow "GPU Research".

If RTX_5080 is not listed on Vast yet, set for example:
  export VAST_GPU_QUERY='gpu_name=RTX_4090 num_gpus=1 reliability>0.95'
  bash scripts/deploy_vast_5080.sh
EOF
