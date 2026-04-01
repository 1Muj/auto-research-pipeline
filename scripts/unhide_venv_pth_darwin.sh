#!/usr/bin/env bash
# Python 3.14+ site.py skips .pth files that have the macOS "hidden" flag (UF_HIDDEN).
# pip/setuptools sometimes create editable-install .pth files with that flag set, which
# breaks `import auto_research` even though `pip install -e .` succeeded.
set -euo pipefail
if [[ "$(uname -s)" != "Darwin" ]]; then
  exit 0
fi
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  exit 0
fi
find "${VIRTUAL_ENV}/lib" -name "*.pth" -exec chflags nohidden {} + 2>/dev/null || true
