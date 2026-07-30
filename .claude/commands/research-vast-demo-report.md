---
description: Run Auto Research agent demos on an already-rented Vast instance, then generate reviews and visualization for professor reporting
---

You run the local auto-research project on an **already-rented Vast.ai instance** and prepare report artifacts. Do **not** create or rent a Vast instance. Do **not** push to GitHub or clone from GitHub. Use local upload via `auto-research vast push`.

Vast bills while the instance is running. Remind the user at the end to stop or destroy the instance.

## 1. Inputs

Ask for the Vast SSH command if missing. Use the simplified SSH form when possible:

```bash
ssh -p <PORT> root@<HOST>
```

If the user gives `-L 8080:localhost:8080`, it is okay to keep it, but it is not needed for code upload.

Default demos:

```text
experiments/_demo_ai_scientist_lite.yaml
experiments/_demo_co_scientist_lite.yaml
experiments/_demo_paperbench_lite.yaml
experiments/_demo_ml_intern_lite.yaml
```

## 2. Local Checks

From repo root:

```bash
pwd
test -f scripts/deploy_existing_vast.sh
test -f experiments/_demo_ai_scientist_lite.yaml
test -f experiments/_demo_co_scientist_lite.yaml
test -f experiments/_demo_paperbench_lite.yaml
test -f experiments/_demo_ml_intern_lite.yaml
test -f src/auto_research/reviewer.py
```

If `auto-research` is unavailable, use `.venv/bin/auto-research`.

## 3. Run On Vast

Replace the SSH command before running:

```bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
CMD=".venv/bin/auto-research"
if [[ ! -x "$CMD" ]]; then CMD="python -m auto_research"; fi

$CMD vast push --cwd . \
  --ssh "ssh -p <PORT> root@<HOST>" \
  -e experiments/_demo_ai_scientist_lite.yaml

$CMD vast push --cwd . \
  --ssh "ssh -p <PORT> root@<HOST>" \
  -e experiments/_demo_co_scientist_lite.yaml \
  --skip-install

$CMD vast push --cwd . \
  --ssh "ssh -p <PORT> root@<HOST>" \
  -e experiments/_demo_paperbench_lite.yaml \
  --skip-install

$CMD vast push --cwd . \
  --ssh "ssh -p <PORT> root@<HOST>" \
  -e experiments/_demo_ml_intern_lite.yaml \
  --skip-install
```

The first command uploads and installs. Later commands sync local edits, skip install, and run the remaining demos.

## 4. Generate Local Report Artifacts

After Vast results are pulled back:

```bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
CMD=".venv/bin/auto-research"
if [[ ! -x "$CMD" ]]; then CMD="python -m auto_research"; fi

$CMD review --cwd . -e experiments/_demo_ai_scientist_lite.yaml
$CMD review --cwd . -e experiments/_demo_co_scientist_lite.yaml
$CMD review --cwd . -e experiments/_demo_paperbench_lite.yaml
$CMD review --cwd . -e experiments/_demo_ml_intern_lite.yaml
$CMD visualize --cwd .
$CMD compare-systems --cwd .
```

## 5. Summarize For The User

Report:

- Whether all four Vast runs completed.
- The GPU/device reported in metrics.
- Pass/fail status for each demo.
- Paths to the four `review_*.md` files.
- Path to `experiments/agent_output/vast_demo_dashboard.html`.
- Path to `docs/comparison_auto_research_agents.md`.

## 6. Failure Handling

If direct SSH closes, ask for the current Vast proxy SSH command and retry.

If host key prompt appears, answer `yes` or use:

```bash
ssh -o StrictHostKeyChecking=accept-new -p <PORT> root@<HOST>
```

If PyTorch is unavailable, the demo still runs with a Python-only fallback, but note that the GPU probe did not use CUDA.

If disk is full, ask the user to re-rent with at least 64GB disk for real experiments.

## 7. Guardrails

- Do not run `auto-research vast deploy`.
- Do not commit secrets.
- Do not destroy or stop the instance automatically unless explicitly asked.
- Always remind the user to stop or destroy Vast after the report artifacts are generated.
