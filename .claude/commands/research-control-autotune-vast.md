---
description: Upload local code to an already-rented Vast instance and run the AutoTune-Control demo
---

Run the specific auto-system demo for **control system optimization**. Do not rent a Vast instance. Do not use GitHub. Use local upload with `auto-research vast push`.

## Inputs

Ask for the current Vast SSH command if missing:

```bash
ssh -p <PORT> root@<HOST>
```

## Run

```bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
CMD=".venv/bin/auto-research"
if [[ ! -x "$CMD" ]]; then CMD="python -m auto_research"; fi

$CMD vast push --cwd . \
  --ssh "ssh -p <PORT> root@<HOST>" \
  -e experiments/_demo_control_autotune.yaml

$CMD review --cwd . -e experiments/_demo_control_autotune.yaml || true
```

## Report

Show the user:

- `experiments/feedback/demo_control_autotune_*_feedback.json`
- `experiments/agent_output/control_autotune_dashboard.html`
- latest `experiments/agent_output/review_demo_control_autotune_*.md`, if generated
- `docs/AUTO_SYS_CONTROL_OPTIMIZATION_CN.md`

Remind the user to stop or destroy the Vast instance when finished.
