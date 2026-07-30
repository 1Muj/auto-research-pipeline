#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-deploy/video_api.env}"

printf "Paste Lumid/OpenAI-compatible API key (input hidden): "
IFS= read -r -s NEW_LUM_API_KEY
printf "\n"

if [[ -z "${NEW_LUM_API_KEY}" ]]; then
  echo "No key entered; nothing changed." >&2
  exit 1
fi

export NEW_LUM_API_KEY ENV_FILE
python3 - <<'PY'
from __future__ import annotations

import os
import shlex
from pathlib import Path

path = Path(os.environ["ENV_FILE"])
key = os.environ["NEW_LUM_API_KEY"]
quoted = shlex.quote(key)
updates = {
    "LUM_API_KEY": quoted,
    "OPENAI_API_KEY": quoted,
    "OPENAI_VISION_API_KEY": quoted,
}

lines = path.read_text(encoding="utf-8").splitlines()
seen: set[str] = set()
out: list[str] = []
for line in lines:
    stripped = line.strip()
    prefix = ""
    body = stripped
    if body.startswith("export "):
        prefix = "export "
        body = body[len("export "):].lstrip()
    if "=" in body:
        name = body.split("=", 1)[0].strip()
        if name in updates:
            out.append(f"{prefix}{name}={updates[name]}")
            seen.add(name)
            continue
    out.append(line)

if updates.keys() - seen:
    out.append("")
    out.append("# API key aliases used by the video pipeline.")
    for name in updates.keys() - seen:
        out.append(f"{name}={updates[name]}")

path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

chmod 600 "$ENV_FILE"

echo "Updated $ENV_FILE"
echo "Check:"
zsh -lc "cd '$ROOT'; set -a; source '$ENV_FILE'; set +a; echo LUM_API_KEY=\${LUM_API_KEY:+loaded}; echo OPENAI_API_KEY=\${OPENAI_API_KEY:+loaded}; echo OPENAI_VISION_API_KEY=\${OPENAI_VISION_API_KEY:+loaded}"
