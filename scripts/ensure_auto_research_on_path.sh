#!/usr/bin/env bash
# Make the `auto-research` CLI reliable on macOS + Python 3.14+: pip's editable .pth may be
# skipped when the file has the UF_HIDDEN flag. We install a small bin wrapper that sets
# PYTHONPATH to the repo src/ and runs `python -m auto_research`.
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

printf '%s\n' "${ROOT}" > "${VIRTUAL_ENV}/.auto_research_repo_root"

WRAPPER="${VIRTUAL_ENV}/bin/auto-research"
cat > "${WRAPPER}" <<'WRAPPER_EOF'
#!/usr/bin/env bash
set -euo pipefail
_VENV_BIN="$(cd "$(dirname "$0")" && pwd)"
_VENV="$(cd "${_VENV_BIN}/.." && pwd)"
_REPO_ROOT="$(tr -d '\r\n' < "${_VENV}/.auto_research_repo_root")"
export PYTHONPATH="${_REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec "${_VENV_BIN}/python" -m auto_research "$@"
WRAPPER_EOF
chmod +x "${WRAPPER}"

# Still help plain `python` / tools that import without the wrapper (best-effort on Darwin).
SITE="$("${PY}" -c "import sysconfig; print(sysconfig.get_path('purelib'))")"
printf '%s\n' "${ROOT}/src" > "${SITE}/auto_research_src.pth"
if [[ "$(uname -s)" == "Darwin" ]]; then
  find "${SITE}" -maxdepth 1 -name "*.pth" -exec chflags nohidden {} + 2>/dev/null || true
fi

"${WRAPPER}" --help >/dev/null
echo "ensure_auto_research_on_path: ok (${WRAPPER})"
