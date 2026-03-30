#!/usr/bin/env bash
# Configure a GitHub Actions self-hosted runner on Linux (CUDA host / Vast instance).
# Usage:
#   export GITHUB_TOKEN=...   # use runner registration token from GitHub UI
#   export RUNNER_VERSION=2.321.0   # optional, see https://github.com/actions/runner/releases
#   ./scripts/setup_github_runner.sh OWNER/REPO

set -euo pipefail

REPO="${1:-}"
if [[ -z "${REPO}" ]]; then
  echo "Usage: $0 OWNER/REPO"
  exit 1
fi

RUNNER_VERSION="${RUNNER_VERSION:-2.321.0}"
LABELS="${RUNNER_LABELS:-self-hosted,gpu}"

WORKDIR="${HOME}/actions-runner"
mkdir -p "${WORKDIR}"
cd "${WORKDIR}"

ARCH="x64"
case "$(uname -m)" in
  aarch64|arm64) ARCH="arm64" ;;
esac

# Download official GitHub Actions runner binary for this CPU architecture.
TARBALL="actions-runner-linux-${ARCH}-${RUNNER_VERSION}.tar.gz"
if [[ ! -f "${TARBALL}" ]]; then
  curl -fsSL -o "${TARBALL}" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}"
fi

tar xzf "${TARBALL}"

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "Set GITHUB_TOKEN to a registration token from:"
  echo "  Repo → Settings → Actions → Runners → New self-hosted runner"
  exit 1
fi

./config.sh --url "https://github.com/${REPO}" --token "${GITHUB_TOKEN}" --labels "${LABELS}" --unattended --replace

echo "Runner configured. Start with:"
echo "  cd ${WORKDIR} && ./run.sh"
echo "Or install as a service: sudo ./svc.sh install && sudo ./svc.sh start"

