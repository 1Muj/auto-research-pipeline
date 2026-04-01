#!/usr/bin/env bash
# Ensure `import auto_research` works in the active venv.
#
# 1) Writes site-packages/auto_research_src.pth → repo src/ (works even when pip's
#    editable __editable__*.pth is ignored by Python 3.14+ on macOS hidden-flag files).
# 2) On Darwin: chflags nohidden on every *.pth in that site-packages (pip may
#    recreate hidden-flagged editables on each install).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "ensure_auto_research_on_path: no active venv (VIRTUAL_ENV empty). Activate .venv first." >&2
  exit 1
fi

PY="${VIRTUAL_ENV}/bin/python"
if [[ ! -x "${PY}" ]]; then
  echo "ensure_auto_research_on_path: missing ${PY}" >&2
  exit 1
fi

SITE="$("${PY}" -c "import site; print(site.getsitepackages()[0])")"
printf '%s\n' "${ROOT}/src" > "${SITE}/auto_research_src.pth"

if [[ "$(uname -s)" == "Darwin" ]]; then
  find "${SITE}" -maxdepth 1 -name "*.pth" -exec chflags nohidden {} + 2>/dev/null || true
fi
