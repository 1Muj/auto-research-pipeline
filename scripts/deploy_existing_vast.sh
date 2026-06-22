#!/usr/bin/env bash
# Sync this local project to an already-rented Vast.ai instance, then optionally run an experiment.
#
# Typical use:
#   bash scripts/deploy_existing_vast.sh \
#     --ssh "ssh -p 12345 root@23.158.136.85" \
#     -e experiments/_demo_mnist_cnn.yaml
#
# This script does not create or rent a Vast instance. It only uses SSH/rsync.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

SSH_CMD_RAW="${VAST_SSH_CMD:-}"
SSH_TARGET="${VAST_SSH_TARGET:-}"
SSH_PORT="${VAST_SSH_PORT:-}"
SSH_KEY="${VAST_SSH_KEY:-}"
REMOTE_DIR="${VAST_REMOTE_DIR:-/root/auto-research}"
EXPERIMENT="${VAST_EXPERIMENT:-experiments/_demo_mnist_cnn.yaml}"
EXTRAS="${VAST_INSTALL_EXTRAS:-.[dev,anthropic,demo]}"
RUN_EXPERIMENT=1
PULL_RESULTS=1
SKIP_INSTALL=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy_existing_vast.sh --ssh "ssh -p PORT root@HOST" [options]
  scripts/deploy_existing_vast.sh --target root@HOST --port PORT [options]

Options:
  --ssh, --ssh-cmd CMD       Full Vast SSH command, for example: ssh -p 12345 root@23.158.136.85
  --target USER@HOST         SSH target if not using --ssh
  --port PORT                SSH port if not using --ssh
  --identity-file PATH       SSH private key path
  --remote-dir PATH          Remote project directory (default: /root/auto-research)
  -e, --experiment PATH      Experiment YAML to run after upload
  --extras SPEC              pip editable extras (default: .[dev,anthropic,demo])
  --no-run                   Upload and install only; do not run an experiment
  --skip-install             Upload only; skip remote venv/pip install
  --no-pull-results          Do not pull experiments/runs and experiments/feedback back
  --dry-run                  Print actions without changing the remote
  -h, --help                 Show this help

Environment equivalents:
  VAST_SSH_CMD, VAST_SSH_TARGET, VAST_SSH_PORT, VAST_SSH_KEY,
  VAST_REMOTE_DIR, VAST_EXPERIMENT, VAST_INSTALL_EXTRAS
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh|--ssh-cmd)
      SSH_CMD_RAW="${2:-}"
      shift 2
      ;;
    --target)
      SSH_TARGET="${2:-}"
      shift 2
      ;;
    --port)
      SSH_PORT="${2:-}"
      shift 2
      ;;
    --identity-file|-i)
      SSH_KEY="${2:-}"
      shift 2
      ;;
    --remote-dir)
      REMOTE_DIR="${2:-}"
      shift 2
      ;;
    --experiment|-e)
      EXPERIMENT="${2:-}"
      shift 2
      ;;
    --extras)
      EXTRAS="${2:-}"
      shift 2
      ;;
    --no-run)
      RUN_EXPERIMENT=0
      shift
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --no-pull-results)
      PULL_RESULTS=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SSH_OPTS=()

parse_ssh_cmd() {
  local raw="$1"
  local -a parts=()
  read -r -a parts <<<"${raw}"
  local i=0
  if [[ "${parts[0]:-}" == "ssh" ]]; then
    i=1
  fi
  while [[ $i -lt ${#parts[@]} ]]; do
    local token="${parts[$i]}"
    case "${token}" in
      -p|-i|-o|-F|-J|-l)
        SSH_OPTS+=("${token}")
        i=$((i + 1))
        if [[ $i -ge ${#parts[@]} ]]; then
          echo "Malformed SSH command: missing value after ${token}" >&2
          exit 2
        fi
        SSH_OPTS+=("${parts[$i]}")
        ;;
      -*)
        SSH_OPTS+=("${token}")
        ;;
      *)
        if [[ -z "${SSH_TARGET}" ]]; then
          SSH_TARGET="${token}"
        else
          SSH_OPTS+=("${token}")
        fi
        ;;
    esac
    i=$((i + 1))
  done
}

if [[ -n "${SSH_CMD_RAW}" ]]; then
  parse_ssh_cmd "${SSH_CMD_RAW}"
fi

if [[ -n "${SSH_PORT}" ]]; then
  SSH_OPTS+=("-p" "${SSH_PORT}")
fi
if [[ -n "${SSH_KEY}" ]]; then
  SSH_OPTS+=("-i" "${SSH_KEY}")
fi

if [[ -z "${SSH_TARGET}" ]]; then
  echo "Missing SSH target. Pass --ssh \"ssh -p PORT root@HOST\" or --target root@HOST --port PORT." >&2
  exit 2
fi

if [[ ! -f "${ROOT}/${EXPERIMENT}" && "${RUN_EXPERIMENT}" -eq 1 ]]; then
  echo "Experiment file not found locally: ${EXPERIMENT}" >&2
  exit 1
fi

quote() {
  printf "%q" "$1"
}

ssh_display="ssh"
rsync_ssh="ssh"
for opt in "${SSH_OPTS[@]}"; do
  ssh_display+=" $(quote "${opt}")"
  rsync_ssh+=" $(quote "${opt}")"
done
ssh_display+=" $(quote "${SSH_TARGET}")"

remote_exec() {
  local script="$1"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] ${ssh_display} < remote script"
    echo "${script}"
    return 0
  fi
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "bash -s" <<<"${script}"
}

echo "Local project: ${ROOT}"
echo "Remote target: ${SSH_TARGET}"
echo "Remote dir:    ${REMOTE_DIR}"
echo "Experiment:    ${EXPERIMENT}"

remote_exec "
set -euo pipefail
if command -v apt-get >/dev/null 2>&1; then
  missing=()
  for bin in rsync git curl tar python3; do
    command -v \"\$bin\" >/dev/null 2>&1 || missing+=(\"\$bin\")
  done
  if [[ \${#missing[@]} -gt 0 ]] || ! python3 -m venv --help >/dev/null 2>&1; then
    apt-get update
    apt-get install -y rsync git curl tar python3 python3-pip python3-venv
  fi
fi
mkdir -p $(quote "${REMOTE_DIR}")
"

RSYNC_ARGS=(
  -az
  --delete
  --exclude ".git/"
  --exclude ".venv/"
  --exclude ".pytest_cache/"
  --exclude ".ruff_cache/"
  --exclude "*.egg-info/"
  --exclude "__pycache__/"
  --exclude ".DS_Store"
  --exclude ".data/"
  --exclude "metrics.json"
  --exclude "experiments/runs/"
  --exclude "experiments/feedback/"
  --exclude "experiments/agent_output/"
  --exclude "deploy/api.env"
  --exclude "deploy/vast.env"
)

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "[dry-run] rsync ${ROOT}/ -> ${SSH_TARGET}:${REMOTE_DIR}/"
else
  rsync "${RSYNC_ARGS[@]}" -e "${rsync_ssh}" "${ROOT}/" "${SSH_TARGET}:${REMOTE_DIR}/"
fi

if [[ "${SKIP_INSTALL}" -eq 0 ]]; then
  remote_exec "
set -euo pipefail
cd $(quote "${REMOTE_DIR}")
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e $(quote "${EXTRAS}")
export PYTHONPATH=\"\${PWD}/src\"
python -m auto_research version
nvidia-smi || true
"
fi

if [[ "${RUN_EXPERIMENT}" -eq 1 ]]; then
  remote_exec "
set -euo pipefail
cd $(quote "${REMOTE_DIR}")
source .venv/bin/activate
export PYTHONPATH=\"\${PWD}/src\"
python -m auto_research run --cwd . -e $(quote "${EXPERIMENT}")
"
fi

if [[ "${RUN_EXPERIMENT}" -eq 1 && "${PULL_RESULTS}" -eq 1 ]]; then
  mkdir -p "${ROOT}/experiments/runs" "${ROOT}/experiments/feedback" \
    "${ROOT}/experiments/agent_output"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[dry-run] pull remote results back to local experiments/runs, feedback, agent_output"
  else
    rsync -az -e "${rsync_ssh}" "${SSH_TARGET}:${REMOTE_DIR}/experiments/runs/" \
      "${ROOT}/experiments/runs/" || true
    rsync -az -e "${rsync_ssh}" "${SSH_TARGET}:${REMOTE_DIR}/experiments/feedback/" \
      "${ROOT}/experiments/feedback/" || true
    rsync -az -e "${rsync_ssh}" "${SSH_TARGET}:${REMOTE_DIR}/experiments/agent_output/" \
      "${ROOT}/experiments/agent_output/" || true
  fi
fi

cat <<EOF

Done.
Remote project:
  ${ssh_display}
  cd ${REMOTE_DIR}

Reminder: stop or destroy the Vast instance when you are done to avoid ongoing charges.
EOF
